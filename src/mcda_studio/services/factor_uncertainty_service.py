"""Fundamental-factor uncertainty: validated, seeded sampling and exact discrete enumeration.

The sampler for separate factor-based analysis runs. Each draw realises every sampled factor once
and evaluates every reviewed formula once, in a deterministic dependency order, with the bounded
interpreter; shared factors and intermediates are therefore one value per draw across all
alternatives. No derived output is ever given a distribution of its own. Marginal quantiles follow
SMAA-2's uniform, triangular and discrete semantics. Nothing here infers a distribution.
"""

import ast
import itertools
import math
import platform
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction

import numpy as np
from numpy.typing import NDArray

from mcda_studio.domain.common import Issue, Severity
from mcda_studio.domain.derived import DerivedModel
from mcda_studio.domain.errors import DomainError, ValidationFailed
from mcda_studio.domain.factor_uncertainty import FactorUncertaintyModel
from mcda_studio.domain.project import Project
from mcda_studio.domain.scales import ScaleType
from mcda_studio.domain.uncertainty import (
    DiscreteDistribution,
    TriangularDistribution,
    UniformDistribution,
)
from mcda_studio.domain.validation import ValidationReport
from mcda_studio.methods.formulas import FormulaError, Quantity, calculate, parse
from mcda_studio.methods.smaa.validation import _probabilities_issue
from mcda_studio.services import derived_service as derived

ALGORITHM = "factor-sampling.v1"
#: Row-major uniforms, one column per independent factor (sorted IDs) then per quantile group
#: (sorted IDs). PCG64 yields doubles in sequence, so the realisations do not depend on the chunk
#: size; tests check that claim.
RNG = "numpy.random.Generator(numpy.random.PCG64(seed)).random((rows, columns))"
MAX_DRAWS = 100_000
MAX_EVALUATIONS = 2_000_000
MAX_OUTCOMES = 100_000
CHUNK_ROWS = 4096
LIMITATIONS = [
    "Frequencies describe the stated factor distributions, not the probability of any outcome "
    "in the world; no distribution is inferred from evidence or ranges.",
    "Distinct factors are independent unless a quantile group states perfectly shared "
    "quantiles; no correlation coefficient, covariance or copula is supported.",
    "Preflight intervals are conservative and not outward-rounded: a support that could reach a "
    "zero denominator or a negative ratio target is refused even at probability zero.",
]


class DrawError(DomainError):
    """A draw whose arithmetic is invalid; the whole run is refused, never thinned."""

    def __init__(
        self,
        code: str,
        draw: int,
        formula_id: str,
        message: str,
        factor_ids: list[str] | None = None,
    ) -> None:
        self.code, self.draw, self.formula_id = code, draw, formula_id
        self.factor_ids = factor_ids or []
        super().__init__(f"{code}: draw {draw}: formula {formula_id}: {message}")


@dataclass(frozen=True)
class _Marginal:
    quantile: Callable[[NDArray[np.float64]], NDArray[np.float64]]
    support: tuple[float, float]
    # Exact outcomes in quantile order, for discrete marginals only.
    atoms: list[tuple[Fraction, float]] | None


@dataclass(frozen=True)
class FactorPlan:
    project_fingerprint: str
    model_digest: str
    uncertainty_digest: str
    order: list[str]
    trees: dict[str, ast.Expression]
    dimensions: dict[str, dict[str, int]]
    fixed: dict[str, float]
    columns: list[tuple[str, list[str]]]
    marginals: dict[str, _Marginal]
    targets: list[tuple[str, str, str]]
    ratio_targets: frozenset[str]
    warnings: list[Issue]
    target_supports: dict[str, tuple[float, float]]


@dataclass(frozen=True)
class FactorSample:
    algorithm: str
    rng: str
    seed: int
    draws: int
    project_fingerprint: str
    model_digest: str
    uncertainty_digest: str
    environment: dict[str, str]
    columns: list[str]
    # Every factor and formula, one value per draw; deterministic factors are repeated.
    values: dict[str, NDArray[np.float64]]
    targets: list[tuple[str, str, str]]
    warnings: list[Issue]
    limitations: list[str]


@dataclass(frozen=True)
class Outcome:
    probability: Fraction
    values: dict[str, float]


@dataclass(frozen=True)
class FactorEnumeration:
    project_fingerprint: str
    model_digest: str
    uncertainty_digest: str
    outcomes: list[Outcome]
    targets: list[tuple[str, str, str]]


def _refuse(issues: list[Issue]) -> None:
    errors = [i for i in issues if i.severity is Severity.ERROR]
    if errors:
        raise ValidationFailed(ValidationReport(issues=errors))


def _names(tree: ast.Expression) -> list[str]:
    called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    return sorted({n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and id(n) not in called})


def _marginal(
    distribution: UniformDistribution | TriangularDistribution | DiscreteDistribution,
) -> _Marginal:
    if isinstance(distribution, UniformDistribution):
        lo, hi = distribution.lower, distribution.upper
        return _Marginal(lambda u: lo + u * (hi - lo), (lo, hi), None)
    if isinstance(distribution, TriangularDistribution):
        a, m, b = distribution.lower, distribution.mode, distribution.upper
        split = (m - a) / (b - a)

        def triangular(u: NDArray[np.float64]) -> NDArray[np.float64]:
            rising = a + np.sqrt(u * (b - a) * (m - a))
            falling = b - np.sqrt((1.0 - u) * (b - a) * (b - m))
            return np.where(u < split, rising, falling)

        return _Marginal(triangular, (a, b), None)
    pairs = sorted(zip(distribution.values, distribution.probabilities, strict=True))
    exact = [Fraction(p) for _, p in pairs]
    total = sum(exact, Fraction(0))
    atoms = [(p / total, v) for (v, _), p in zip(pairs, exact, strict=True)]
    cumulative = np.cumsum(np.array([float(p) for p, _ in atoms]))
    cumulative[-1] = 1.0
    table = np.array([v for _, v in atoms], dtype=float)

    def discrete(u: NDArray[np.float64]) -> NDArray[np.float64]:
        index = np.minimum(np.searchsorted(cumulative, u, side="right"), len(table) - 1)
        return table[index]

    possible = [v for p, v in atoms if p > 0]
    return _Marginal(discrete, (min(possible), max(possible)), atoms)


def _distribution_issue(
    distribution: UniformDistribution | TriangularDistribution | DiscreteDistribution,
) -> str | None:
    if isinstance(distribution, UniformDistribution):
        return None if distribution.lower < distribution.upper else "needs lower < upper"
    if isinstance(distribution, TriangularDistribution):
        d = distribution
        if d.lower <= d.mode <= d.upper and d.lower < d.upper:
            return None
        return "needs lower <= mode <= upper and lower < upper"
    if len(distribution.values) != len(distribution.probabilities):
        return "needs one probability per value"
    if len(set(distribution.values)) != len(distribution.values):
        return "lists a value twice"
    if len(distribution.values) > 64:
        return "lists more than 64 values"
    return _probabilities_issue(distribution.probabilities)


def _interval(
    node: ast.AST, known: dict[str, tuple[float, float]], formula_id: str
) -> tuple[float, float]:
    """Conservative range of an already validated expression over the factor supports."""

    def finite(lo: float, hi: float) -> tuple[float, float]:
        if not (math.isfinite(lo) and math.isfinite(hi)):
            raise FormulaError("UNCERTAINTY_NONFINITE", "the support can overflow")
        return lo, hi

    if isinstance(node, ast.Constant):
        assert isinstance(node.value, int | float)  # the interpreter has accepted this tree
        value = float(node.value)
        return value, value
    if isinstance(node, ast.Name):
        return known[node.id]
    if isinstance(node, ast.UnaryOp):
        lo, hi = _interval(node.operand, known, formula_id)
        return (-hi, -lo) if isinstance(node.op, ast.USub) else (lo, hi)
    if isinstance(node, ast.BinOp):
        a, b = _interval(node.left, known, formula_id), _interval(node.right, known, formula_id)
        if isinstance(node.op, ast.Add):
            return finite(a[0] + b[0], a[1] + b[1])
        if isinstance(node.op, ast.Sub):
            return finite(a[0] - b[1], a[1] - b[0])
        if isinstance(node.op, ast.Div):
            if b[0] <= 0 <= b[1]:
                raise FormulaError("UNCERTAINTY_DENOMINATOR", "a denominator's support includes 0")
            b = (1 / b[1], 1 / b[0])
        corners = [x * y for x in a for y in b]
        return finite(min(corners), max(corners))
    assert isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    spans = [_interval(arg, known, formula_id) for arg in node.args]
    pick = min if node.func.id == "min" else max
    return pick(s[0] for s in spans), pick(s[1] for s in spans)


def plan(project: Project, model: DerivedModel, uncertainty: FactorUncertaintyModel) -> FactorPlan:
    """Validate everything before any draw; a usable plan has no error."""
    report = derived.preview(project, model)
    _refuse(report.issues)
    issues: list[Issue] = []

    def add(code: str, message: str, path: str, severity: Severity = Severity.ERROR) -> None:
        issues.append(Issue(severity=severity, code=code, message=message, path=path))

    if uncertainty.project_fingerprint != project.fingerprint():
        add("UNCERTAINTY_STALE_PROJECT", "uncertainty is for another project revision", "")
    if uncertainty.model_digest != report.model_digest:
        add("UNCERTAINTY_STALE_MODEL", "uncertainty is for another calculation model", "")
    sources = {s.id: s for s in model.sources}
    formulas = {f.id for f in model.formulas}
    fixed: dict[str, float] = {}
    for s in model.sources:
        if s.review is None or s.review.status == "rejected":
            add(
                "DERIVED_UNREVIEWED_SOURCE",
                f"factor {s.id!r} requires acceptance",
                f"sources[{s.id}]",
            )
            continue
        value = s.review.corrected_value if s.review.status == "corrected" else s.value
        if not isinstance(value, float | int):
            add(
                "DERIVED_MISSING_INPUT",
                f"factor {s.id!r} needs an accepted number",
                f"sources[{s.id}]",
            )
            continue
        if s.unit != "1" and s.unit not in model.units:
            add(
                "DERIVED_UNKNOWN_UNIT",
                f"unit {s.unit!r} needs explicit dimensions",
                f"sources[{s.id}]",
            )
            continue
        fixed[s.id] = float(value)
    _refuse(issues)
    marginals: dict[str, _Marginal] = {}
    for factor, count in sorted(Counter(d.factor_id for d in uncertainty.distributions).items()):
        if count > 1:
            add("UNCERTAINTY_DUPLICATE", f"factor {factor!r} has {count} distributions", "")
    for d in uncertainty.distributions:
        path = f"distributions[{d.factor_id}]"
        if d.factor_id in formulas:
            add(
                "UNCERTAINTY_DERIVED_OUTPUT",
                f"{d.factor_id!r} is a formula; it is recalculated from its factors, never sampled",
                path,
            )
            continue
        if d.factor_id not in fixed:
            add("UNCERTAINTY_UNKNOWN_FACTOR", f"no accepted factor {d.factor_id!r}", path)
            continue
        if d.review is None or d.review.status != "accepted":
            add("UNCERTAINTY_UNREVIEWED", "the distribution requires acceptance", path)
        if problem := _distribution_issue(d.distribution):
            add("UNCERTAINTY_INVALID_DISTRIBUTION", f"the distribution {problem}", path)
            continue
        marginal = _marginal(d.distribution)
        marginals.setdefault(d.factor_id, marginal)
        lo, hi = marginal.support
        if not lo <= fixed[d.factor_id] <= hi:
            add(
                "UNCERTAINTY_VALUE_OUTSIDE_SUPPORT",
                "the accepted value lies outside the stated distribution",
                path,
                Severity.WARNING,
            )
    grouped: Counter[str] = Counter()
    for gid, count in sorted(Counter(g.id for g in uncertainty.groups).items()):
        if count > 1 or gid in sources or gid in formulas:
            add("UNCERTAINTY_DUPLICATE_GROUP", f"group id {gid!r} is not unique", "")
    for g in uncertainty.groups:
        path = f"groups[{g.id}]"
        grouped.update(g.factor_ids)
        if g.review is None or g.review.status != "accepted":
            add("UNCERTAINTY_UNREVIEWED", "the stated coupling requires acceptance", path)
        for factor in g.factor_ids:
            if factor not in marginals:
                add(
                    "UNCERTAINTY_GROUP_MEMBER",
                    f"coupled factor {factor!r} needs its own valid accepted distribution",
                    path,
                )
    for factor, count in sorted(grouped.items()):
        if count > 1:
            add("UNCERTAINTY_GROUP_OVERLAP", f"factor {factor!r} is in more than one group", "")
    _refuse(issues)
    trees = {f.id: parse(f.expression) for f in model.formulas}
    order: list[str] = []

    def visit(formula_id: str) -> None:
        if formula_id in order:
            return
        for name in _names(trees[formula_id]):
            if name in trees:
                visit(name)
        order.append(formula_id)

    for formula_id in sorted(trees):
        visit(formula_id)
    known = {
        name: marginals[name].support if name in marginals else (value, value)
        for name, value in fixed.items()
    }
    targets = [
        (c.id, c.alternative_id, c.criterion_id)
        for c in report.calculations
        if c.alternative_id is not None and c.criterion_id is not None
    ]
    tree = project.tree()
    ratio = frozenset(
        formula
        for formula, _, criterion in targets
        if (scale := tree.node(criterion).scale) is not None and scale.type is ScaleType.RATIO
    )
    for formula_id in order:
        try:
            known[formula_id] = _interval(trees[formula_id].body, known, formula_id)
        except FormulaError as exc:
            add(exc.code, str(exc), f"formulas[{formula_id}]")
            break
        if formula_id in ratio and known[formula_id][0] < 0:
            add(
                "UNCERTAINTY_TARGET_NEGATIVE",
                "the support can give a negative ratio measurement",
                f"formulas[{formula_id}]",
            )
    _refuse(issues)
    independent = sorted(f for f in marginals if f not in grouped)
    columns = [(f, [f]) for f in independent] + [
        (g.id, list(g.factor_ids)) for g in sorted(uncertainty.groups, key=lambda g: g.id)
    ]

    def dimension(unit: str) -> dict[str, int]:
        return {} if unit == "1" else {k: e for k, e in model.units[unit].items() if e}

    units = {s.id: s.unit for s in model.sources}
    calculations = {c.id: c for c in report.calculations}
    return FactorPlan(
        project_fingerprint=project.fingerprint(),
        model_digest=report.model_digest,
        uncertainty_digest=derived._digest(uncertainty.model_dump(mode="json")),
        order=order,
        trees=trees,
        dimensions={
            **{name: dimension(units[name]) for name in fixed},
            **{f: calculations[f].dimension for f in order},
        },
        fixed=fixed,
        columns=columns,
        marginals=marginals,
        targets=targets,
        ratio_targets=ratio,
        warnings=issues,
        target_supports={f: known[f] for f, _, _ in targets},
    )


def _evaluate(plan: FactorPlan, factors: dict[str, float], draw: int) -> dict[str, float]:
    """One draw: each factor and formula once, in dependency order; nothing is resampled."""
    for name, value in factors.items():
        if not math.isfinite(value):
            raise DrawError("UNCERTAINTY_FACTOR_NONFINITE", draw, name, "nonfinite factor", [name])
    cache = {name: Quantity(value, plan.dimensions[name]) for name, value in factors.items()}
    for formula_id in plan.order:
        try:
            result = calculate(plan.trees[formula_id], cache.__getitem__)
        except FormulaError as exc:
            raise DrawError(exc.code, draw, formula_id, str(exc), sorted(plan.fixed)) from exc
        if formula_id in plan.ratio_targets and result.value < 0:
            raise DrawError(
                "UNCERTAINTY_TARGET_NEGATIVE", draw, formula_id, "negative ratio measurement"
            )
        cache[formula_id] = result
    return {name: quantity.value for name, quantity in cache.items()}


def sample(plan: FactorPlan, seed: int, draws: int) -> FactorSample:
    if not 1 <= draws <= MAX_DRAWS or draws * max(1, len(plan.order)) > MAX_EVALUATIONS:
        raise ValidationFailed(
            ValidationReport(
                issues=[
                    Issue(
                        severity=Severity.ERROR,
                        code="UNCERTAINTY_LIMIT",
                        message=f"draws must be 1 to {MAX_DRAWS} and at most "
                        f"{MAX_EVALUATIONS} formula evaluations",
                    )
                ]
            )
        )
    if not 0 <= seed < 2**63:
        raise ValidationFailed(
            ValidationReport(
                issues=[Issue(severity=Severity.ERROR, code="UNCERTAINTY_SEED", message="bad seed")]
            )
        )
    rng = np.random.Generator(np.random.PCG64(seed))
    width = len(plan.columns)
    chunks = []
    for start in range(0, draws, CHUNK_ROWS):
        chunks.append(rng.random((min(CHUNK_ROWS, draws - start), width)))
    uniforms = np.concatenate(chunks) if chunks else np.zeros((draws, width))
    realised = {name: np.full(draws, value) for name, value in plan.fixed.items()}
    for column, (_, members) in enumerate(plan.columns):
        for factor in members:
            realised[factor] = plan.marginals[factor].quantile(uniforms[:, column])
    values = {name: np.empty(draws) for name in [*plan.fixed, *plan.order]}
    for draw in range(draws):
        row = _evaluate(plan, {name: float(realised[name][draw]) for name in plan.fixed}, draw)
        for name, value in row.items():
            values[name][draw] = value
    return FactorSample(
        algorithm=ALGORITHM,
        rng=RNG,
        seed=seed,
        draws=draws,
        project_fingerprint=plan.project_fingerprint,
        model_digest=plan.model_digest,
        uncertainty_digest=plan.uncertainty_digest,
        environment={
            "python": platform.python_version(),
            "numpy": np.__version__,
            "system": f"{platform.system()} {platform.machine()}",
        },
        columns=[name for name, _ in plan.columns],
        values=values,
        targets=plan.targets,
        warnings=plan.warnings,
        limitations=LIMITATIONS,
    )


def _segments(plan: FactorPlan, members: list[str]) -> list[tuple[Fraction, dict[str, float]]]:
    """Exact joint outcomes of one shared uniform passed through each member's quantiles."""
    atoms = {m: plan.marginals[m].atoms for m in members}
    cumulative: dict[str, list[Fraction]] = {}
    for m, listed in atoms.items():
        assert listed is not None
        running, points = Fraction(0), []
        for p, _ in listed:
            running += p
            points.append(running)
        cumulative[m] = points
    cuts = sorted({Fraction(0), Fraction(1), *(c for cs in cumulative.values() for c in cs)})
    out = []
    for left, right in itertools.pairwise(cuts):
        if right <= left or left >= 1:
            continue
        chosen = {}
        for m in members:
            listed = atoms[m]
            assert listed is not None
            index = min(sum(c <= left for c in cumulative[m]), len(listed) - 1)
            chosen[m] = listed[index][1]
        out.append((right - left, chosen))
    return out


def enumerate_outcomes(plan: FactorPlan) -> FactorEnumeration:
    """Every joint outcome with its exact probability, for discrete factors only."""
    if any(m.atoms is None for m in plan.marginals.values()):
        raise ValidationFailed(
            ValidationReport(
                issues=[
                    Issue(
                        severity=Severity.ERROR,
                        code="UNCERTAINTY_NOT_ENUMERABLE",
                        message="exact enumeration needs discrete factor distributions",
                    )
                ]
            )
        )
    blocks: list[list[tuple[Fraction, dict[str, float]]]] = []
    for _, members in plan.columns:
        if len(members) == 1:
            listed = plan.marginals[members[0]].atoms
            assert listed is not None
            blocks.append([(p, {members[0]: v}) for p, v in listed if p > 0])
        else:
            blocks.append(_segments(plan, members))
    if math.prod(len(b) for b in blocks) > MAX_OUTCOMES:
        raise ValidationFailed(
            ValidationReport(
                issues=[
                    Issue(
                        severity=Severity.ERROR,
                        code="UNCERTAINTY_LIMIT",
                        message=f"more than {MAX_OUTCOMES} joint outcomes",
                    )
                ]
            )
        )
    outcomes = []
    for index, combination in enumerate(itertools.product(*blocks)):
        probability = math.prod((p for p, _ in combination), start=Fraction(1))
        factors = dict(plan.fixed)
        for _, chosen in combination:
            factors.update(chosen)
        outcomes.append(Outcome(probability, _evaluate(plan, factors, index)))
    return FactorEnumeration(
        project_fingerprint=plan.project_fingerprint,
        model_digest=plan.model_digest,
        uncertainty_digest=plan.uncertainty_digest,
        outcomes=outcomes,
        targets=plan.targets,
    )
