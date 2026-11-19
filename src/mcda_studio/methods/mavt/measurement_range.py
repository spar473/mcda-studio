"""Single-measurement range screening with fixed value-function anchors.

For a piecewise-linear value function, extrema occur at an interval endpoint or an
included control point. Other alternatives' scores remain fixed. This establishes
whether the selected alternative's rank or class differs anywhere in the interval;
it does not establish global robustness. Boundary contacts are solved algebraically
using exact rational representations of the stored floats, then the ordinary engine
evaluates witnesses. A rounded contact is not used to decide boundary membership.
"""

import math
from fractions import Fraction
from typing import Literal

from mcda_studio.domain.common import DomainModel, Severity
from mcda_studio.domain.criteria import (
    Direction,
    LinearValueFunction,
    PiecewiseLinearValueFunction,
)
from mcda_studio.domain.errors import SensitivityError, ValidationFailed
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.scales import AnchorMode
from mcda_studio.domain.validation import ValidationReport
from mcda_studio.methods.mavt.aggregation import TIE_TOL, overall_values, prepare_mavt, rank_values
from mcda_studio.methods.mavt.value_functions import build_evaluator
from mcda_studio.methods.sorting.classes import check_sorting, class_index, lower_boundaries


class BoundaryContact(DomainModel):
    kind: Literal["rank", "class"]
    reference_id: str
    # A flat segment can lie on a boundary over a closed interval.
    lower: float
    upper: float
    exact_lower: str
    exact_upper: str
    score_threshold: float


class MeasurementState(DomainModel):
    measurement: float
    score: float
    rank: int
    class_id: str | None


class MeasurementRangeResult(DomainModel):
    alternative_id: str
    criterion_id: str
    lower: float
    upper: float
    baseline_rank: int
    rank_can_change: bool
    baseline_class_id: str | None
    class_can_change: bool | None
    minimum_score_at: float
    maximum_score_at: float
    boundary_contacts: list[BoundaryContact]
    witnesses: list[MeasurementState]
    limitations: list[str]


def _contacts(
    points: list[tuple[Fraction, Fraction]],
    target: Fraction,
    lower: float,
    upper: float,
) -> list[tuple[Fraction, Fraction]]:
    """Closed solution sets of a piecewise affine function, clipped to the range."""
    lo, hi = Fraction(lower), Fraction(upper)
    found: list[tuple[Fraction, Fraction]] = []
    for (x0, v0), (x1, v1) in zip(points, points[1:], strict=False):
        left, right = max(lo, x0), min(hi, x1)
        if left > right:
            continue
        if v0 == v1:
            if target != v0:
                continue
            a, b = left, right
        else:
            root = x0 + (target - v0) * (x1 - x0) / (v1 - v0)
            if not left <= root <= right:
                continue
            a = b = root
        if found and a <= found[-1][1]:
            found[-1] = (found[-1][0], max(b, found[-1][1]))
        else:
            found.append((a, b))
    return found


def assess_measurement_range(
    project: Project,
    configuration: AnalysisConfiguration,
    alternative_id: str,
    criterion_id: str,
    lower: float,
    upper: float,
) -> MeasurementRangeResult:
    if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper:
        raise SensitivityError("RANGE_INVALID: bounds must be finite and ordered")
    cfg = configuration.model_copy(update={"method": "mavt", "parameters": {}})
    prep = prepare_mavt(project, cfg)
    if alternative_id not in prep.alt_ids or criterion_id not in prep.leaf_ids:
        raise SensitivityError("RANGE_UNKNOWN_CELL: select a known alternative and leaf")
    node = prep.tree.node(criterion_id)
    vf = (
        prep.scenario.value_function_overrides.get(criterion_id, node.value_function)
        if prep.scenario
        else node.value_function
    )
    if node.scale is None or not node.scale.is_numeric or vf is None:
        raise SensitivityError("RANGE_UNSUPPORTED_FUNCTION: a numeric value function is required")
    if isinstance(vf, LinearValueFunction) and node.scale.anchor_mode is AnchorMode.LOCAL:
        raise SensitivityError("RANGE_LOCAL_ANCHORS: fixed anchors are required")
    domain = prep.domains[criterion_id]
    if domain is None or lower < domain.lower or upper > domain.upper:
        raise SensitivityError("RANGE_OUTSIDE_DOMAIN: bounds must be inside fixed anchors")
    measurement = prep.raw[(alternative_id, criterion_id)]
    if isinstance(measurement, str) or not lower <= measurement <= upper:
        raise SensitivityError(
            "RANGE_EXCLUDES_BASELINE: the range must contain the entered measurement"
        )
    points = [lower, upper]
    if isinstance(vf, PiecewiseLinearValueFunction):
        points.extend(point.x for point in vf.points if lower < point.x < upper)
    evaluator = build_evaluator(vf, domain)
    i, j = prep.alt_ids.index(alternative_id), prep.leaf_ids.index(criterion_id)
    weights = prep.global_vector()
    baseline = overall_values(prep.partial, weights)
    baseline_rank = rank_values(baseline)[i]
    candidates = []
    for x in points:
        partial = prep.partial.copy()
        partial[i, j] = evaluator(x)[0]
        candidates.append((x, overall_values(partial, weights)))
    minimum = min(candidates, key=lambda item: item[1][i])
    maximum = max(candidates, key=lambda item: item[1][i])
    rank_change = any(rank_values(item[1])[i] != baseline_rank for item in (minimum, maximum))
    baseline_class = None
    class_change = None
    boundaries: list[float] = []
    ids: list[str] = []
    if project.sorting is not None:
        report = ValidationReport(issues=check_sorting(project, []))
        if any(issue.severity is Severity.ERROR for issue in report.issues):
            raise ValidationFailed(report)
        boundaries = lower_boundaries(project.sorting)
        ids = [c.id for c in project.sorting.classes]
        index = class_index(baseline[i], boundaries)
        baseline_class = ids[index]
        class_change = any(
            class_index(item[1][i], boundaries) != index for item in (minimum, maximum)
        )
    # On each segment U(x) = constant + weight * v(x). Solve U(x) = threshold.
    # Fraction avoids cancellation around ties and preserves closed/flat contacts.
    constant = sum(
        (
            Fraction(float(weights[k])) * Fraction(float(prep.partial[i, k]))
            for k in range(len(weights))
            if k != j
        ),
        Fraction(0),
    )
    weight = Fraction(float(weights[j]))
    if isinstance(vf, PiecewiseLinearValueFunction):
        control = [(Fraction(p.x), Fraction(p.value)) for p in vf.points]
    else:
        decreasing = isinstance(vf, LinearValueFunction) and vf.direction is Direction.DECREASING
        control = [
            (Fraction(domain.lower), Fraction(int(decreasing))),
            (Fraction(domain.upper), Fraction(int(not decreasing))),
        ]
    score_points = [(x, constant + weight * v) for x, v in control]
    thresholds: list[tuple[Literal["rank", "class"], str, Fraction]] = [
        ("rank", alt, Fraction(baseline[k]) - Fraction(TIE_TOL))
        for k, alt in enumerate(prep.alt_ids)
        if k != i
    ]
    thresholds.extend(
        ("class", ids[k], Fraction(b) - Fraction(TIE_TOL)) for k, b in enumerate(boundaries)
    )
    contacts = [
        BoundaryContact(
            kind=kind,
            reference_id=reference,
            lower=float(a),
            upper=float(b),
            exact_lower=str(a),
            exact_upper=str(b),
            score_threshold=float(threshold),
        )
        for kind, reference, threshold in thresholds
        for a, b in _contacts(score_points, threshold, lower, upper)
    ]
    contacts.sort(key=lambda c: (c.lower, c.upper, c.kind, c.reference_id))
    witnesses = [
        MeasurementState(
            measurement=x,
            score=values[i],
            rank=rank_values(values)[i],
            class_id=ids[class_index(values[i], boundaries)] if ids else None,
        )
        for x, values in (minimum, maximum)
    ]
    return MeasurementRangeResult(
        alternative_id=alternative_id,
        criterion_id=criterion_id,
        lower=lower,
        upper=upper,
        baseline_rank=baseline_rank,
        rank_can_change=rank_change,
        baseline_class_id=baseline_class,
        class_can_change=class_change,
        minimum_score_at=minimum[0],
        maximum_score_at=maximum[0],
        boundary_contacts=contacts,
        witnesses=witnesses,
        limitations=[
            "Only one measurement varies with fixed anchors and other inputs fixed.",
            "Boundary contacts solve the piecewise-linear model using exact stored-float ratios; "
            "displayed coordinates are rounded. Witness ranks and classes use ordinary engine "
            "arithmetic and its 1e-12 tolerance. A contact alone need not change rank or class.",
            "Shared factors and changes in multiple measurements are not propagated.",
        ],
    )
