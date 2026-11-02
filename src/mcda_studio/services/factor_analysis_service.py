"""Separate, replayable factor-based runs; ordinary MAVT/sorting and SMAA-2 counting rules.

No project schema changes and no cell/weight uncertainty is combined with factor uncertainty.
The original project, accepted inputs and distribution sidecar travel with each sealed record.
"""

import hashlib
import json
import math
import platform
from collections.abc import Callable
from fractions import Fraction
from typing import Any, Final, Literal, NoReturn

import numpy as np
from numpy.typing import NDArray
from pydantic import Field, ValidationError

from mcda_studio.domain.common import DomainModel, Issue, Severity
from mcda_studio.domain.decision import DecisionDetails
from mcda_studio.domain.derived import DerivedModel
from mcda_studio.domain.errors import DomainError, ModelEditError, ValidationFailed
from mcda_studio.domain.factor_uncertainty import FactorUncertaintyModel
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import (
    AcceptabilityEstimate,
    AlternativeAcceptability,
    MavtResult,
    MavtSortingResult,
)
from mcda_studio.domain.scales import AnchorMode
from mcda_studio.domain.validation import ValidationReport
from mcda_studio.methods.mavt.aggregation import build_mavt_result, prepare_mavt
from mcda_studio.methods.mavt.value_functions import build_evaluator
from mcda_studio.methods.smaa.engine import _estimate, _evaluate, _Plan
from mcda_studio.methods.sorting.classes import build_sorting_result, lower_boundaries
from mcda_studio.services import decision_record_service as decisions
from mcda_studio.services import derived_service as derived
from mcda_studio.services import factor_uncertainty_service as factors
from mcda_studio.services.questions_service import Question

ALGORITHM: Final = "factor-mavt-smaa2.v1"
TRACE_ROWS = 16
MAX_WORK = 2_000_000
Run = Literal["mavt", "mavt_sorting", "smaa2_factors"]


class FactorRunParameters(DomainModel):
    run: Run = "smaa2_factors"
    evaluation: Literal["sampled", "exact_enumeration"] = "sampled"
    draws: int = Field(default=1000, ge=1, le=factors.MAX_DRAWS)
    seed: int = Field(default=7, ge=0, lt=2**63)
    confidence: float = Field(default=0.95, gt=0, lt=1)
    configuration: AnalysisConfiguration = Field(default_factory=AnalysisConfiguration)


class FactorDraw(DomainModel):
    index: int
    probability: str | None
    factors: dict[str, float]
    formulas: dict[str, float]
    measurements: dict[str, dict[str, float | str]]
    values: dict[str, float]
    ranks: dict[str, int]
    classes: dict[str, str]


class FactorRunResult(DomainModel):
    run: Run
    algorithm: Literal["factor-mavt-smaa2.v1"] = ALGORITHM
    sampler_algorithm: Literal["factor-sampling.v1"] = "factor-sampling.v1"
    rng: str
    seed: int
    draw_count: int
    evaluation: Literal["sampled", "exact_enumeration"]
    confidence: float
    project_fingerprint: str
    model_digest: str
    uncertainty_digest: str
    environment: dict[str, str]
    dependency_order: list[str]
    draw_columns: list[str]
    deterministic_inputs: dict[str, float]
    # The reference is explicitly the separate, deterministically compiled project.
    reference: MavtResult | MavtSortingResult
    feasibility: decisions.FeasibilitySnapshot
    acceptability: list[AlternativeAcceptability]
    trace: list[FactorDraw]
    draws_digest: str
    questions: list[Question]
    warnings: list[Issue]
    limitations: list[str]


class FactorRunRecord(DomainModel):
    artifact_kind: Literal["factor_uncertainty_run"] = "factor_uncertainty_run"
    version: Literal[1] = 1
    source_project: Project
    model: DerivedModel
    uncertainty: FactorUncertaintyModel
    parameters: FactorRunParameters
    result: FactorRunResult
    decision: decisions.DecisionRecordV2 | None = None
    digest: str


def _fail(code: str, message: str) -> NoReturn:
    raise ValidationFailed(
        ValidationReport(issues=[Issue(severity=Severity.ERROR, code=code, message=message)])
    )


def _configuration(project: Project, parameters: FactorRunParameters) -> AnalysisConfiguration:
    cfg = parameters.configuration.model_copy(deep=True)
    if cfg.method not in {"mavt", "mavt_sorting"}:
        _fail(
            "FACTOR_CONFIGURATION", "factor runs require a MAVT or sorting reference configuration"
        )
    cfg.method = (
        "mavt_sorting"
        if parameters.run == "mavt_sorting"
        or (parameters.run == "smaa2_factors" and project.sorting)
        else "mavt"
    )
    return cfg


def input_questions(
    project: Project, model: DerivedModel, uncertainty: FactorUncertaintyModel
) -> list[Question]:
    """Dependency questions retain IDs and source classifications, without a quality score."""
    preview = derived.preview(project, model)
    if (
        model.project_fingerprint != project.fingerprint()
        or uncertainty.project_fingerprint != project.fingerprint()
        or uncertainty.model_digest != preview.model_digest
    ):
        _fail("UNCERTAINTY_STALE_MODEL", "review factor questions against their exact bound inputs")
    distributed = {d.factor_id: d for d in uncertainty.distributions}
    questions = []
    for source in model.sources:
        uses = [c for c in preview.calculations if source.id in c.source_ids and c.alternative_id]
        if not uses:
            continue
        dist = distributed.get(source.id)
        reviewed = dist is not None and dist.review is not None and dist.review.status == "accepted"
        for target in uses:
            questions.append(
                Question(
                    group="evidence_quality",
                    code="DERIVED_FACTOR_ASSUMPTION",
                    question=f"Are assumptions for factor {source.id} adequate for {target.id}?",
                    why=f"Source {source.source.reference} ({source.source.classification}); "
                    + (
                        "accepted distribution"
                        if reviewed
                        else "distribution pending review"
                        if dist
                        else "held at its accepted deterministic value"
                    )
                    + f"; feeds {', '.join(c.id for c in uses)}. Shared identity is retained.",
                    evidence="Review the source, support and any declared quantile coupling; "
                    "no distribution is inferred from a range.",
                    alternative_id=target.alternative_id,
                    criterion_id=target.criterion_id,
                )
            )
    return questions


def _prepare(
    project: Project,
    model: DerivedModel,
    uncertainty: FactorUncertaintyModel,
    parameters: FactorRunParameters,
) -> tuple[factors.FactorPlan, Project, AnalysisConfiguration]:
    # This gate also refuses cell uncertainty on any derived target, before the general
    # combination guard. Never strip the section to make an ambiguous model pass.
    plan = factors.plan(project, model, uncertainty)
    targets = {(alternative, leaf) for _, alternative, leaf in plan.targets}
    if project.smaa and (
        any((c.alternative_id, c.criterion_id) not in targets for c in project.smaa.cells)
        or project.smaa.groups
        or project.smaa.shared_draws
        or project.smaa.dependence != "independent"
    ):
        _fail(
            "FACTOR_COMBINATION_UNSUPPORTED",
            "factor runs support fixed weights and no additional cell uncertainty; "
            "use a separate run",
        )
    if not plan.targets:
        _fail("FACTOR_NO_TARGETS", "at least one reviewed formula must target a measurement")
    preview = derived.preview(project, model)
    compiled = derived.compile_copy(project, model, preview.review_digest)
    cfg = _configuration(project, parameters)
    prep = prepare_mavt(compiled, cfg)  # non-derived missing inputs still block the whole run
    for formula, _, leaf in plan.targets:
        node = prep.tree.node(leaf)
        assert node.scale is not None
        vf = (
            prep.scenario.value_function_overrides.get(leaf, node.value_function)
            if prep.scenario
            else node.value_function
        )
        assert vf is not None
        # Linear local anchors move on each draw; those draws are validated individually.
        if node.scale.anchor_mode is AnchorMode.LOCAL and vf.kind == "linear":
            continue
        evaluator = build_evaluator(vf, prep.domains[leaf])
        try:
            for endpoint in plan.target_supports[formula]:
                evaluator(endpoint)
        except DomainError as exc:
            _fail("UNCERTAINTY_VALUE_DOMAIN_SUPPORT", f"formula {formula}: {exc}")
    return plan, compiled, cfg


def evaluate_draw(
    project: Project,
    configuration: AnalysisConfiguration,
    plan: factors.FactorPlan,
    values: dict[str, float],
    index: int,
) -> MavtResult | MavtSortingResult:
    """Populate declared targets, then use ordinary MAVT, including local anchors."""
    temporary = project.model_copy(deep=True)
    cells = {(m.alternative_id, m.criterion_id): m for m in temporary.performances}
    for formula, alternative, criterion in plan.targets:
        value = values[formula]
        if not math.isfinite(value):
            raise factors.DrawError(
                "UNCERTAINTY_NONFINITE", index, formula, "nonfinite target", sorted(plan.fixed)
            )
        cells[alternative, criterion].value = value
    try:
        base = build_mavt_result(prepare_mavt(temporary, configuration))
    except (DomainError, ValidationFailed) as exc:
        raise factors.DrawError(
            "UNCERTAINTY_VALUE_DOMAIN",
            index,
            ",".join(f for f, _, _ in plan.targets),
            str(exc),
            sorted(plan.fixed),
        ) from exc
    if configuration.method == "mavt_sorting":
        assert temporary.sorting is not None
        return build_sorting_result(base, temporary.sorting)
    return base


def run(
    project: Project,
    model: DerivedModel,
    uncertainty: FactorUncertaintyModel,
    parameters: FactorRunParameters,
    decision: DecisionDetails | None = None,
) -> FactorRunRecord:
    return execute(project, model, uncertainty, parameters, decision)


def execute(
    project: Project,
    model: DerivedModel,
    uncertainty: FactorUncertaintyModel,
    parameters: FactorRunParameters,
    decision: DecisionDetails | None = None,
    *,
    check_plan: Callable[[factors.FactorPlan], None] | None = None,
    check_draw: Callable[[dict[str, float], int], None] | None = None,
) -> FactorRunRecord:
    """Shared execution; optional validators abort, never alter or resample a realization."""
    plan, compiled, cfg = _prepare(project, model, uncertainty, parameters)
    if check_plan is not None:
        check_plan(plan)
    prep = prepare_mavt(compiled, cfg)
    exact = parameters.evaluation == "exact_enumeration"
    if not exact and parameters.draws * len(prep.alt_ids) * len(prep.leaf_ids) > MAX_WORK:
        _fail("UNCERTAINTY_LIMIT", "factor analysis work limit exceeded before sampling")
    sample = None if exact else factors.sample(plan, parameters.seed, parameters.draws)
    enumeration = factors.enumerate_outcomes(plan) if exact else None
    n = len(enumeration.outcomes) if enumeration else parameters.draws
    if n * len(prep.alt_ids) * len(prep.leaf_ids) > MAX_WORK:
        _fail(
            "UNCERTAINTY_LIMIT",
            "at most 2,000,000 draw x alternative x leaf evaluations per factor run",
        )
    # The same SMAA-2 rank/class path is used after raw measurements have passed ordinary MAVT.
    partial = np.empty((n, len(prep.alt_ids), len(prep.leaf_ids)))
    trace: list[FactorDraw] = []
    rows_digest = hashlib.sha256()
    probabilities: list[Fraction | int] = []
    probability: Fraction | int
    for index in range(n):
        if enumeration is not None:
            outcome = enumeration.outcomes[index]
            values, probability = outcome.values, outcome.probability
        else:
            assert sample is not None
            values = {name: float(column[index]) for name, column in sample.values.items()}
            probability = 1
        if check_draw is not None:
            check_draw(values, index)
        probabilities.append(probability)
        evaluated = evaluate_draw(compiled, cfg, plan, values, index)
        by_id = {a.alternative_id: a for a in evaluated.alternatives}
        for a, alternative in enumerate(prep.alt_ids):
            partial[index, a] = [by_id[alternative].partial_values[leaf] for leaf in prep.leaf_ids]
        row = FactorDraw(
            index=index,
            probability=str(probability) if exact else None,
            factors={s: values[s] for s in sorted(plan.fixed)},
            formulas={f: values[f] for f in plan.order},
            measurements={a: by_id[a].raw_measurements for a in prep.alt_ids},
            values={a: by_id[a].overall_value for a in prep.alt_ids},
            ranks={a: by_id[a].rank for a in prep.alt_ids},
            classes={a.alternative_id: a.class_id for a in evaluated.assignments}
            if isinstance(evaluated, MavtSortingResult)
            else {},
        )
        rows_digest.update((derived._digest(row.model_dump(mode="json")) + "\n").encode())
        if index < TRACE_ROWS:
            trace.append(row)
    bands = compiled.sorting if cfg.method == "mavt_sorting" else None
    smaa_plan = _Plan(
        prep,
        [],
        [],
        [],
        lower_boundaries(bands) if bands else [],
        [c.id for c in bands.classes] if bands else [],
    )
    ranks, classes, _ = _evaluate(
        smaa_plan, partial, np.broadcast_to(prep.global_vector(), (n, len(prep.leaf_ids)))
    )
    accepts = []
    for a, alternative in enumerate(prep.alt_ids):

        def estimate(mask: NDArray[np.bool_]) -> AcceptabilityEstimate:
            count = sum(
                (probabilities[i] for i in range(n) if mask[i]), Fraction(0) if exact else 0
            )
            return _estimate(count, None if exact else n, parameters.confidence)

        firsts = (ranks == 1).sum(axis=1)
        accepts.append(
            AlternativeAcceptability(
                alternative_id=alternative,
                name=next(x.name for x in project.alternatives if x.id == alternative),
                ranks=[estimate(ranks[:, a] == r) for r in range(1, len(prep.alt_ids) + 1)],
                sole_first=estimate((ranks[:, a] == 1) & (firsts == 1)),
                tied_first=estimate((ranks[:, a] == 1) & (firsts > 1)),
                classes={
                    cid: estimate(classes[:, a] == k) for k, cid in enumerate(smaa_plan.class_ids)
                },
            )
        )
    reference = build_mavt_result(prep)
    reference_result = build_sorting_result(reference, bands) if bands else reference
    # The deterministic decision and the stochastic run are distinct snapshots in this envelope.
    decision_record = None
    if decision is not None:
        preview = derived.preview(project, model)
        bundle = derived.compilation_bundle(project, model, preview.review_digest)
        decision_record = decisions.create(
            compiled, decision, [decisions.SupportingArtifact(artifact=bundle)]
        )
    if sample is None:
        environment = {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "system": f"{platform.system()} {platform.machine()}",
        }
    else:
        environment = sample.environment
    record = FactorRunRecord(
        source_project=project.model_copy(deep=True),
        model=model.model_copy(deep=True),
        uncertainty=uncertainty.model_copy(deep=True),
        parameters=parameters.model_copy(deep=True),
        result=FactorRunResult(
            run=parameters.run,
            rng=factors.RNG if not exact else "none: exact discrete enumeration",
            seed=parameters.seed,
            draw_count=n,
            evaluation=parameters.evaluation,
            confidence=parameters.confidence,
            project_fingerprint=project.fingerprint(),
            model_digest=plan.model_digest,
            uncertainty_digest=plan.uncertainty_digest,
            environment=environment,
            dependency_order=plan.order,
            draw_columns=[c for c, _ in plan.columns],
            deterministic_inputs=plan.fixed,
            reference=reference_result,
            feasibility=decisions._feasibility(compiled),
            acceptability=accepts,
            trace=trace,
            draws_digest=rows_digest.hexdigest(),
            questions=input_questions(project, model, uncertainty),
            warnings=[*plan.warnings, *prep.warnings],
            limitations=[
                *factors.LIMITATIONS,
                "Value-function support checks use conservative interval enclosures too; "
                "they can refuse a reused-factor expression whose true image fits the domain.",
                "Feasibility is checked on the deterministic reference only. Rank/class draw "
                "counts are not conditioned on feasibility and cannot offset a failed requirement.",
                "Weights are fixed. Cell uncertainty, weight uncertainty and other "
                "dependence combinations are refused.",
                "The reference ranking uses deterministically compiled measurements. "
                "Frequencies never replace preference values.",
                "Only the first 16 draws are shown; the digest covers every draw and raw "
                "measurement. Replay requires the recorded environment.",
                "Local anchors are recomputed for each temporary draw using ordinary MAVT; "
                "clamp is used only when the value function explicitly declares it.",
            ],
        ),
        decision=decision_record,
        digest="",
    )
    record.digest = derived._digest(record.model_dump(mode="json", exclude={"digest"}))
    return record


def verify(document: dict[str, Any], replay: bool = False) -> FactorRunRecord:
    try:
        json.dumps(document, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ModelEditError(
            "FACTOR_RECORD_NONFINITE: record contains unsupported numbers"
        ) from exc
    try:
        record = FactorRunRecord.model_validate(document)
    except ValidationError as exc:
        raise ModelEditError(f"FACTOR_RECORD_INVALID: {exc}") from exc
    if record.digest != derived._digest(record.model_dump(mode="json", exclude={"digest"})):
        raise ModelEditError("FACTOR_RECORD_CHANGED: record digest does not match")
    plan, compiled, cfg = _prepare(
        record.source_project, record.model, record.uncertainty, record.parameters
    )
    result, params = record.result, record.parameters
    if (
        result.project_fingerprint,
        result.model_digest,
        result.uncertainty_digest,
        result.deterministic_inputs,
        result.seed,
        result.run,
        result.evaluation,
        result.confidence,
    ) != (
        plan.project_fingerprint,
        plan.model_digest,
        plan.uncertainty_digest,
        plan.fixed,
        params.seed,
        params.run,
        params.evaluation,
        params.confidence,
    ):
        raise ModelEditError("FACTOR_RECORD_MISMATCH: inputs or parameters differ")
    n = (
        len(factors.enumerate_outcomes(plan).outcomes)
        if params.evaluation == "exact_enumeration"
        else params.draws
    )
    if (
        result.draw_count != n
        or result.reference.project_fingerprint != compiled.fingerprint()
        or result.reference.configuration != cfg
    ):
        raise ModelEditError("FACTOR_RECORD_MISMATCH: reference or denominator differs")
    expected_reference = build_mavt_result(prepare_mavt(compiled, cfg))
    if cfg.method == "mavt_sorting":
        assert compiled.sorting is not None
        rebuilt: MavtResult | MavtSortingResult = build_sorting_result(
            expected_reference, compiled.sorting
        )
    else:
        rebuilt = expected_reference
    if result.reference != rebuilt or result.feasibility != decisions._feasibility(compiled):
        raise ModelEditError("FACTOR_RECORD_MISMATCH: deterministic reference does not reproduce")
    if record.decision is not None:
        decisions.verify(record.decision)
        if record.decision.project_fingerprint != compiled.fingerprint():
            raise ModelEditError("FACTOR_RECORD_MISMATCH: decision belongs to another project")
    if replay:
        expected = run(record.source_project, record.model, record.uncertainty, params)
        if expected.result != result:
            raise ModelEditError(
                "FACTOR_REPLAY_MISMATCH: stochastic run does not reproduce in this environment"
            )
    return record


class FactorInspection(DomainModel):
    uncertainty: FactorUncertaintyModel
    uncertainty_digest: str
    issues: list[Issue]
    questions: list[Question]


def inspect(
    project: Project, model: DerivedModel, uncertainty: FactorUncertaintyModel
) -> FactorInspection:
    try:
        planned = factors.plan(project, model, uncertainty)
        issues = planned.warnings
    except ValidationFailed as exc:
        issues = exc.report.issues
    try:
        questions = input_questions(project, model, uncertainty)
    except ValidationFailed:
        questions = []
    return FactorInspection(
        uncertainty=uncertainty,
        uncertainty_digest=derived._digest(uncertainty.model_dump(mode="json")),
        issues=issues,
        questions=questions,
    )
