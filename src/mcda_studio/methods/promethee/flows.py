"""PROMETHEE II's calculation: preference degrees, outranking flows and the PROMETHEE I partial
order (design note §2).

Every number comes from the measurements (or a labelled leaf's codes) and the section's
directions, weights and preference functions; MAVT's value functions and swing weights are never
read. Every sum uses ``math.fsum``.
"""

import math
from dataclasses import dataclass

from mcda_studio.domain.common import Issue
from mcda_studio.domain.errors import AnalysisLimitError, ValidationFailed
from mcda_studio.domain.outranking import (
    AnyPreferenceFunction,
    PrometheeCriterion,
    UShapeFunction,
    UsualFunction,
    VShapeFunction,
)
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import (
    PartialOrderPair,
)
from mcda_studio.methods.base import validate_analysis
from mcda_studio.methods.mavt.aggregation import TIE_TOL, rank_values
from mcda_studio.methods.promethee.validation import coded_measurements, threshold_tolerance

#: Preference degrees (alternatives^2 x leaves) per request: the results limits' worst case.
MAX_DEGREES = 1_000_000


def preference_degree(function: AnyPreferenceFunction, d: float, tol: float) -> float:
    """F(d): 0 for a difference at or below 0, then the function's shape. ``d`` is compared with
    0, q and p as equal within ``tol``."""
    if d <= tol:
        return 0.0
    if isinstance(function, UsualFunction):
        return 1.0
    if isinstance(function, UShapeFunction):
        return 0.0 if d <= function.q + tol else 1.0
    if isinstance(function, VShapeFunction):
        return 1.0 if d >= function.p - tol else d / function.p
    q, p = function.q, function.p
    if d <= q + tol:
        return 0.0
    if d >= p - tol:
        return 1.0
    return (d - q) / (p - q)


@dataclass(frozen=True)
class PreparedPromethee:
    """The section in leaf order, the coded measurements and every preference degree."""

    project: Project
    configuration: AnalysisConfiguration
    alt_ids: list[str]
    names: dict[str, str]
    leaf_ids: list[str]
    criteria: list[PrometheeCriterion]  # in leaf order
    measurements: list[list[float]]  # [leaf][alternative], codes on a labelled leaf
    signs: list[int]  # +1 to maximise, -1 to minimise
    weights: list[float]  # normalised
    degrees: list[list[list[float]]]  # [leaf][a][b] = P_j(a, b)
    warnings: list[Issue]

    def difference(self, j: int, a: int, b: int) -> float:
        """d_j(a, b) = s_j (x_a - x_b)."""
        x = self.measurements[j]
        return self.signs[j] * (x[a] - x[b])

    def tolerance(self, j: int, a: int, b: int) -> float:
        x = self.measurements[j]
        return threshold_tolerance(x[a], x[b])


@dataclass(frozen=True)
class Flows:
    preference: list[list[float]]  # pi(a, b); 0 on the diagonal
    positive: list[float]
    negative: list[float]
    net: list[float]
    criterion: list[list[float]]  # [leaf][alternative], single-criterion net flows
    ranks: list[int]


def prepare_promethee(project: Project, configuration: AnalysisConfiguration) -> PreparedPromethee:
    report = validate_analysis(project, configuration)
    if not report.ok:
        raise ValidationFailed(report)
    assert project.promethee is not None  # guaranteed by validation (PROMETHEE_NOT_STATED)
    tree = project.tree()
    leaf_ids = tree.leaves()
    alt_ids = project.alternative_ids()
    if len(alt_ids) ** 2 * len(leaf_ids) > MAX_DEGREES:
        raise AnalysisLimitError(
            "PROMETHEE II computes at most 10^6 preference degrees (alternatives^2 x leaves) per "
            "request; reduce the alternatives or criteria."
        )
    stated = {c.criterion_id: c for c in project.promethee.criteria}
    criteria = [stated[leaf] for leaf in leaf_ids]
    measurements = []
    for entry in criteria:
        values = coded_measurements(project, entry)
        assert values is not None  # guaranteed by validation (measurements and codings)
        measurements.append(values)
    total = math.fsum(c.weight for c in criteria)
    weights = [c.weight / total for c in criteria]
    signs = [1 if c.direction == "maximise" else -1 for c in criteria]
    n = len(alt_ids)
    degrees = [
        [
            [
                preference_degree(
                    entry.function, s * (x[a] - x[b]), threshold_tolerance(x[a], x[b])
                )
                for b in range(n)
            ]
            for a in range(n)
        ]
        for entry, x, s in zip(criteria, measurements, signs, strict=True)
    ]
    return PreparedPromethee(
        project=project,
        configuration=configuration,
        alt_ids=alt_ids,
        names={a.id: a.name for a in project.alternatives},
        leaf_ids=leaf_ids,
        criteria=criteria,
        measurements=measurements,
        signs=signs,
        weights=weights,
        degrees=degrees,
        warnings=report.warnings,
    )


def compute_flows(prep: PreparedPromethee) -> Flows:
    n = len(prep.alt_ids)
    others = n - 1
    leaves = range(len(prep.leaf_ids))
    preference = [
        [
            0.0 if a == b else math.fsum(prep.weights[j] * prep.degrees[j][a][b] for j in leaves)
            for b in range(n)
        ]
        for a in range(n)
    ]
    positive = [math.fsum(preference[a][b] for b in range(n) if b != a) / others for a in range(n)]
    negative = [math.fsum(preference[b][a] for b in range(n) if b != a) / others for a in range(n)]
    net = [positive[a] - negative[a] for a in range(n)]
    criterion = [
        [
            math.fsum(
                [P[a][b] for b in range(n) if b != a] + [-P[b][a] for b in range(n) if b != a]
            )
            / others
            for a in range(n)
        ]
        for P in prep.degrees
    ]
    flows = Flows(preference, positive, negative, net, criterion, rank_values(net, TIE_TOL))
    _check_invariants(prep, flows)
    return flows


def _check_invariants(prep: PreparedPromethee, flows: Flows) -> None:
    """Design note §2: bounds, a zero sum, and both decompositions of the net flow."""
    n = len(prep.alt_ids)
    for a in range(n):
        assert -TIE_TOL <= flows.positive[a] <= 1 + TIE_TOL
        assert -TIE_TOL <= flows.negative[a] <= 1 + TIE_TOL
        assert -1 - TIE_TOL <= flows.net[a] <= 1 + TIE_TOL
        assert flows.net[a] == flows.positive[a] - flows.negative[a]
        by_criterion = math.fsum(w * flows.criterion[j][a] for j, w in enumerate(prep.weights))
        assert abs(flows.net[a] - by_criterion) <= TIE_TOL
    assert abs(math.fsum(flows.net)) <= n * TIE_TOL


def partial_order(prep: PreparedPromethee, flows: Flows) -> list[PartialOrderPair]:
    """PROMETHEE I: a is preferred to b when it is at least as good on both flows and better on
    one; indifferent when both are equal; otherwise incomparable. Equal means within 1e-12."""
    out: list[PartialOrderPair] = []
    plus, minus = flows.positive, flows.negative

    def preferred(a: int, b: int) -> bool:
        at_least = plus[a] >= plus[b] - TIE_TOL and minus[a] <= minus[b] + TIE_TOL
        better = plus[a] > plus[b] + TIE_TOL or minus[a] < minus[b] - TIE_TOL
        return at_least and better

    ids = prep.alt_ids
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            if preferred(a, b):
                out.append(
                    PartialOrderPair(
                        alternative_a=ids[a], alternative_b=ids[b], relation="preferred"
                    )
                )
            elif preferred(b, a):
                out.append(
                    PartialOrderPair(
                        alternative_a=ids[b], alternative_b=ids[a], relation="preferred"
                    )
                )
            elif abs(plus[a] - plus[b]) <= TIE_TOL and abs(minus[a] - minus[b]) <= TIE_TOL:
                out.append(
                    PartialOrderPair(
                        alternative_a=ids[a], alternative_b=ids[b], relation="indifferent"
                    )
                )
            else:
                out.append(
                    PartialOrderPair(
                        alternative_a=ids[a], alternative_b=ids[b], relation="incomparable"
                    )
                )
    return out
