"""Explicit quantity bounds and scoped formula-output runs, using the existing sampler."""

import hashlib
import math
import platform
from collections import Counter
from dataclasses import dataclass
from typing import Literal, NoReturn

import numpy as np
from pydantic import Field

from mcda_studio.domain.common import FiniteFloat, Issue, Severity
from mcda_studio.domain.derived import DerivedModel
from mcda_studio.domain.errors import ModelEditError, ValidationFailed
from mcda_studio.domain.evidence import Review
from mcda_studio.domain.factor_uncertainty import FactorUncertaintyModel
from mcda_studio.domain.model_comparison import (
    ExactRange,
    ModelChecks,
    ModelOutputSpec,
    QuantityCheck,
    SampledRange,
    SourceRange,
)
from mcda_studio.domain.project import Project
from mcda_studio.domain.sidecar_common import SidecarModel
from mcda_studio.domain.validation import ValidationReport
from mcda_studio.methods.formulas import FormulaError, parse
from mcda_studio.services import derived_service as derived
from mcda_studio.services import factor_uncertainty_service as factors


class QuantityRange(SidecarModel):
    kind: Literal[
        "source_interval", "support_enclosure", "exact_discrete_support", "sampled_central95"
    ]
    lower: FiniteFloat
    upper: FiniteFloat
    interpretation: str
    quantile_algorithm: str | None = None


class ModelOutputRun(SidecarModel):
    artifact_kind: Literal["model_output_run"] = "model_output_run"
    version: Literal[1] = 1
    source_project: Project
    specification: ModelOutputSpec
    scoped_model: DerivedModel
    scoped_uncertainty: FactorUncertaintyModel
    omitted_quantity_ids: list[str]
    value: FiniteFloat
    unit: str
    range: QuantityRange
    model_digest: str
    checks_digest: str | None
    draw_count: int
    seed: int | None
    algorithm: Literal["checked-model-output.v1"] = "checked-model-output.v1"
    environment: dict[str, str]
    first_draws: list[dict[str, float]] = Field(default_factory=list)
    draws_digest: str
    source_classifications: dict[str, str]
    limitations: list[str]
    digest: str


@dataclass(frozen=True)
class ScopedModel:
    model: DerivedModel
    uncertainty: FactorUncertaintyModel
    omitted: list[str]


def fail(code: str, message: str, path: str = "") -> NoReturn:
    raise ValidationFailed(
        ValidationReport(
            issues=[Issue(severity=Severity.ERROR, code=code, message=message, path=path)]
        )
    )


def accepted(review: Review | None, code: str, message: str) -> None:
    if review is None or review.status != "accepted" or not review.reviewer.strip():
        fail(code, message)


def checks_digest(checks: ModelChecks) -> str:
    return derived._digest(checks.model_dump(mode="json", exclude={"digest"}))


def validate_checks(project: Project, model: DerivedModel, checks: ModelChecks | None) -> None:
    if checks is None:
        return
    if (
        checks.project_fingerprint != project.fingerprint()
        or checks.model_digest != derived._digest(model.model_dump(mode="json"))
        or checks.digest != checks_digest(checks)
    ):
        fail(
            "MODEL_CHECKS_BINDING",
            "quantity checks require their exact reviewed project/model/digest",
        )
    accepted(checks.review, "MODEL_CHECKS_REVIEW", "accept the declared quantity checks explicitly")
    if len({c.id for c in checks.checks}) != len(checks.checks):
        fail("MODEL_CHECKS_DUPLICATE", "quantity check IDs must be unique")
    sources = {s.id: s.unit for s in model.sources}
    formulas = {f.id: f.unit for f in model.formulas}
    for check in checks.checks:
        quantities = sources if check.quantity_kind == "source" else formulas
        if check.quantity_id not in quantities or quantities[check.quantity_id] != check.unit:
            fail("MODEL_CHECKS_QUANTITY", "quantity kind, ID and exact unit must resolve", check.id)


def scope_model(
    project: Project,
    specification: ModelOutputSpec,
    additional_roots: list[str] | None = None,
    detach_targets: bool = True,
) -> ScopedModel:
    """Materialize only declared output/check dependencies; preserve the original in the record."""
    model, uncertainty = specification.model, specification.uncertainty
    if model.project_fingerprint != project.fingerprint():
        fail("MODEL_STALE_PROJECT", "model output belongs to another project revision")
    names = [s.id for s in model.sources] + [f.id for f in model.formulas]
    if any(n > 1 for n in Counter(names).values()):
        fail("MODEL_DUPLICATE_QUANTITY", "source and formula IDs must be unambiguous")
    sources = {s.id: s for s in model.sources}
    formulas = {f.id: f for f in model.formulas}
    if specification.formula_id not in formulas:
        fail("MODEL_OUTPUT_ID", "select an existing formula output")
    targets = [(f.alternative_id, f.criterion_id) for f in model.formulas if f.alternative_id]
    if len(targets) != len(set(targets)):
        fail(
            "MODEL_DUPLICATE_TARGET", "competing estimates must be intermediates or separate models"
        )
    validate_checks(project, model, specification.checks)
    model_digest = derived._digest(model.model_dump(mode="json"))
    if uncertainty is not None:
        if (
            uncertainty.project_fingerprint != project.fingerprint()
            or uncertainty.model_digest != model_digest
        ):
            fail("MODEL_STALE_UNCERTAINTY", "factor declarations do not match the original model")
        if any(d.factor_id not in sources for d in uncertainty.distributions):
            fail(
                "MODEL_DISTRIBUTION_TARGET",
                "only fundamental source factors may have distributions",
            )
        if len({d.factor_id for d in uncertainty.distributions}) != len(uncertainty.distributions):
            fail("MODEL_DISTRIBUTION_DUPLICATE", "a factor may have only one distribution")
    needed: set[str] = set()
    active: set[str] = set()

    def visit(name: str) -> None:
        if name in active:
            fail("MODEL_CYCLE", "output dependencies contain a cycle")
        if name in needed:
            return
        if name not in sources and name not in formulas:
            fail("MODEL_UNKNOWN_QUANTITY", f"unknown referenced quantity {name}")
        active.add(name)
        if name in formulas:
            try:
                references = factors._names(parse(formulas[name].expression))
            except FormulaError as exc:
                fail(exc.code, str(exc), name)
            for referenced in references:
                visit(referenced)
        active.remove(name)
        needed.add(name)

    visit(specification.formula_id)
    for root in additional_roots or []:
        visit(root)
    if specification.checks:
        for check in specification.checks.checks:
            visit(check.quantity_id)
    # Probability runs retain a whole required quantile group. Source bounds do not use groups.
    if uncertainty and not isinstance(specification.range, SourceRange):
        changed = True
        while changed:
            before = set(needed)
            for group in uncertainty.groups:
                if set(group.factor_ids) & needed:
                    for member in group.factor_ids:
                        visit(member)
            changed = before != needed
    scoped = model.model_copy(deep=True)
    scoped.sources = [s.model_copy(deep=True) for s in model.sources if s.id in needed]
    scoped.formulas = [f.model_copy(deep=True) for f in model.formulas if f.id in needed]
    # This is a quantity run, not measurement compilation. The original targets remain
    # in specification.
    if detach_targets:
        for formula in scoped.formulas:
            formula.alternative_id = None
            formula.criterion_id = None
    spec = FactorUncertaintyModel(
        project_fingerprint=project.fingerprint(),
        model_digest=derived._digest(scoped.model_dump(mode="json")),
        distributions=[
            d.model_copy(deep=True) for d in uncertainty.distributions if d.factor_id in needed
        ]
        if uncertainty
        else [],
        groups=[g.model_copy(deep=True) for g in uncertainty.groups if set(g.factor_ids) & needed]
        if uncertainty
        else [],
    )
    return ScopedModel(scoped, spec, sorted(set(names) - needed))


def supports(plan: factors.FactorPlan) -> dict[str, tuple[float, float]]:
    known = {
        name: plan.marginals[name].support if name in plan.marginals else (value, value)
        for name, value in plan.fixed.items()
    }
    for formula in plan.order:
        known[formula] = factors._interval(plan.trees[formula].body, known, formula)
    return known


def _contains(check: QuantityCheck, value: float) -> bool:
    return (
        math.isfinite(value)
        and (
            check.lower is None or value >= check.lower
            if check.lower_inclusive
            else check.lower is None or value > check.lower
        )
        and (
            check.upper is None or value <= check.upper
            if check.upper_inclusive
            else check.upper is None or value < check.upper
        )
    )


def check_values(
    checks: ModelChecks | None, values: dict[str, float], draw: int | None = None
) -> None:
    if checks is None:
        return
    for check in checks.checks:
        if check.quantity_id not in values:
            fail("MODEL_CHECKS_MISSING", "a checked quantity is unavailable", check.id)
        if not _contains(check, values[check.quantity_id]):
            if draw is not None:
                raise factors.DrawError(
                    "MODEL_CHECK_VIOLATION",
                    draw,
                    check.quantity_id,
                    f"quantity check {check.id} failed",
                    [check.quantity_id],
                )
            fail("MODEL_CHECK_VIOLATION", f"quantity check {check.id} failed", check.quantity_id)


def preflight(checks: ModelChecks | None, plan: factors.FactorPlan) -> None:
    check_values(checks, factors._evaluate(plan, plan.fixed, -1))
    bounds = supports(plan)
    if checks is not None:
        for check in checks.checks:
            lo, hi = bounds[check.quantity_id]
            if not _contains(check, lo) or not _contains(check, hi):
                fail(
                    "MODEL_CHECK_SUPPORT",
                    f"declared support violates check {check.id}",
                    check.quantity_id,
                )


def run_output(project: Project, specification: ModelOutputSpec) -> ModelOutputRun:
    scoped = scope_model(project, specification)
    request = specification.range
    if isinstance(request, ExactRange | SampledRange) and specification.uncertainty is None:
        fail(
            "MODEL_EXPLICIT_DISTRIBUTIONS",
            "supply explicit factor distributions; source bounds are not distributions",
        )
    # Reviewed source intervals have no probability semantics and do not use retained marginals.
    planning = scoped.uncertainty
    if isinstance(request, SourceRange):
        planning = FactorUncertaintyModel(
            project_fingerprint=project.fingerprint(), model_digest=scoped.uncertainty.model_digest
        )
    plan = factors.plan(project, scoped.model, planning)
    if (
        isinstance(request, SampledRange)
        and request.draws * (len(plan.fixed) + len(plan.order)) > 2_000_000
    ):
        fail("MODEL_RUN_LIMIT", "at most 2000000 quantity-by-draw evaluations")
    preflight(specification.checks, plan)
    reference = factors._evaluate(plan, plan.fixed, -1)
    value = reference[specification.formula_id]
    bounds = supports(plan)
    trace: list[dict[str, float]] = []
    digest = hashlib.sha256()
    seed, count = None, 0
    if isinstance(request, SourceRange):
        seen: set[str] = set()
        units = {s.id: s.unit for s in specification.model.sources}
        for interval in request.intervals:
            if interval.factor_id in seen or units.get(interval.factor_id) != interval.unit:
                fail(
                    "MODEL_SOURCE_INTERVAL", "source bounds need a unique factor ID and exact unit"
                )
            seen.add(interval.factor_id)
            accepted(
                interval.review,
                "MODEL_SOURCE_INTERVAL_REVIEW",
                "review source bounds separately from a value",
            )
            if interval.factor_id in bounds:
                bounds[interval.factor_id] = (interval.lower, interval.upper)
        for formula in plan.order:
            try:
                bounds[formula] = factors._interval(plan.trees[formula].body, bounds, formula)
            except FormulaError as exc:
                fail(exc.code, str(exc), formula)
        if specification.checks:
            for check in specification.checks.checks:
                lo, hi = bounds[check.quantity_id]
                if not _contains(check, lo) or not _contains(check, hi):
                    fail("MODEL_CHECK_SUPPORT", f"source bounds violate check {check.id}")
        lo, hi = bounds[specification.formula_id]
        interpretation = (
            "Reviewed source bounds propagated conservatively; no probability "
            "distribution or confidence interval."
        )
    elif isinstance(request, ExactRange | SampledRange):
        if isinstance(request, ExactRange):
            outcomes = factors.enumerate_outcomes(plan).outcomes
            rows = [o.values for o in outcomes]
            interpretation = "Reachable exact discrete extrema under the declared dependence."
        else:
            sample = factors.sample(plan, request.seed, request.draws)
            rows = [{k: float(v[i]) for k, v in sample.values.items()} for i in range(sample.draws)]
            seed = request.seed
            interpretation = (
                "Central 95% of the declared model draws; not source accuracy or an "
                "outcome probability."
            )
        for index, row in enumerate(rows):
            check_values(specification.checks, row, index)
            digest.update((derived._digest(row) + "\n").encode())
            if index < 16:
                trace.append(row)
        count = len(rows)
        values = [row[specification.formula_id] for row in rows]
        if isinstance(request, ExactRange):
            lo, hi = min(values), max(values)
        else:
            lo, hi = (float(v) for v in np.quantile(values, [0.025, 0.975], method="linear"))
    else:
        lo, hi = bounds[specification.formula_id]
        interpretation = (
            "Conservative support enclosure, not proven extrema or a confidence interval."
        )
    result = ModelOutputRun(
        source_project=project.model_copy(deep=True),
        specification=specification.model_copy(deep=True),
        scoped_model=scoped.model,
        scoped_uncertainty=planning,
        omitted_quantity_ids=scoped.omitted,
        value=value,
        unit=next(f.unit for f in scoped.model.formulas if f.id == specification.formula_id),
        range=QuantityRange(
            kind=request.kind,
            lower=lo,
            upper=hi,
            interpretation=interpretation,
            quantile_algorithm=request.quantile_algorithm
            if isinstance(request, SampledRange)
            else None,
        ),
        model_digest=derived._digest(specification.model.model_dump(mode="json")),
        checks_digest=specification.checks.digest if specification.checks else None,
        draw_count=count,
        seed=seed,
        environment={
            "python": platform.python_version(),
            "numpy": np.__version__,
            "system": f"{platform.system()} {platform.machine()}",
        },
        first_draws=trace,
        draws_digest=digest.hexdigest(),
        source_classifications={s.id: s.source.classification for s in scoped.model.sources},
        limitations=[
            *factors.LIMITATIONS,
            (
                "Only explicitly required quantities and quantile-group members are "
                "run; original drafts and omitted IDs remain retained."
            ),
            (
                "Quantity-check preflight uses conservative support enclosures; a "
                "reused-factor image may fit when its enclosure does not."
            ),
            "No bounds are inferred from a unit, source classification or template name.",
        ],
        digest="",
    )
    result.digest = derived._digest(result.model_dump(mode="json", exclude={"digest"}))
    return result


def verify_output(run: ModelOutputRun) -> ModelOutputRun:
    if run.digest != derived._digest(run.model_dump(mode="json", exclude={"digest"})):
        raise ModelEditError("MODEL_RUN_CHANGED: output digest does not match")
    if run_output(run.source_project, run.specification) != run:
        raise ModelEditError("MODEL_RUN_MISMATCH: output does not reproduce in this environment")
    return run
