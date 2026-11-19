"""Exact class changes along a one-way weight sensitivity (specification §7).

Boundaries are fixed on the value scale and every V_a(t) is affine in the varied weight t, so for
a boundary b the gap  g(t) = V_a(t) - (b - tol)  is affine too, and the alternative is in the
boundary's class or better exactly when g(t) >= 0. Where g(0) and g(1) fall on different sides,
the class changes at  t* = g(0) / (g(0) - g(1)),  the weight at which the engine's own boundary rule
switches. At t* the alternative is in the higher class. No grid search is involved.
"""

from mcda_studio.domain.common import Issue, Severity
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.previews import SensitivityProbe, SortingSensitivityProbe
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import (
    AlternativeClassChanges,
    ClassChange,
    SensitivityResult,
    SortingSensitivityResult,
)
from mcda_studio.domain.sorting import SortingModel
from mcda_studio.methods.mavt.aggregation import TIE_TOL, prepare_mavt
from mcda_studio.methods.mavt.sensitivity import endpoint_values
from mcda_studio.methods.sorting.classes import class_bands, class_index, lower_boundaries


def class_changes(
    alternative_id: str,
    v0: float,
    v1: float,
    base_weight: float,
    base_value: float,
    model: SortingModel,
) -> AlternativeClassChanges:
    """Every class change of one alternative over t in [0, 1], and the first change either way."""
    ids = [c.id for c in model.classes]
    points: list[ClassChange] = []
    for k, b in enumerate(lower_boundaries(model)):
        threshold = b - TIE_TOL
        g0, g1 = v0 - threshold, v1 - threshold
        if (g0 >= 0.0) != (g1 >= 0.0):
            falling = g0 >= 0.0
            points.append(
                ClassChange(
                    weight=g0 / (g0 - g1),
                    boundary_class_id=ids[k],
                    class_before=ids[k] if falling else ids[k + 1],
                    class_after=ids[k + 1] if falling else ids[k],
                )
            )
    points.sort(key=lambda p: p.weight)
    base_class = ids[class_index(base_value, lower_boundaries(model))]
    up = next(
        (p for p in points if p.weight >= base_weight - TIE_TOL and p.class_after != base_class),
        None,
    )
    down = next(
        (
            p
            for p in reversed(points)
            if p.weight <= base_weight + TIE_TOL and p.class_before != base_class
        ),
        None,
    )
    return AlternativeClassChanges(
        alternative_id=alternative_id,
        base_class_id=base_class,
        change_points=points,
        first_change_up=up,
        first_change_down=down,
        class_stable_range=(down.weight if down else 0.0, up.weight if up else 1.0),
    )


def sorting_sensitivity(
    project: Project, configuration: AnalysisConfiguration, result: SensitivityResult
) -> SortingSensitivityResult:
    """Add exact class changes to a completed MAVT sweep of the same project and configuration."""
    model = project.sorting
    assert model is not None  # the sweep already validated through the sorting method
    prep = prepare_mavt(project, configuration)
    v0, v1 = endpoint_values(prep, result.node_id)
    index = {a: i for i, a in enumerate(prep.alt_ids)}
    names = {a.id: a.name for a in project.alternatives}
    changes = [
        class_changes(
            alt,
            float(v0[index[alt]]),
            float(v1[index[alt]]),
            result.base_weight,
            result.baseline_values[alt],
            model,
        )
        for alt in result.baseline_ranking
    ]
    diagnostics = list(result.diagnostics)
    boundaries = lower_boundaries(model)
    for c in changes:
        base_value = result.baseline_values[c.alternative_id]
        if any(abs(base_value - b) <= TIE_TOL for b in boundaries):
            diagnostics.append(
                Issue(
                    severity=Severity.WARNING,
                    code="BASELINE_ON_CLASS_BOUNDARY",
                    message=f"{names[c.alternative_id]} is exactly on a class boundary at the "
                    "baseline weight: its class changes on one side of it",
                )
            )
    shared = {name: getattr(result, name) for name in SensitivityResult.model_fields}
    return SortingSensitivityResult(
        **shared | {"diagnostics": diagnostics},
        boundary_tolerance=TIE_TOL,
        classes=class_bands(model),
        class_changes=changes,
    )


def sorting_probe(project: Project, probe: SensitivityProbe) -> SortingSensitivityProbe:
    """Add each alternative's class at the probed weight, from the same boundary rule."""
    model = project.sorting
    assert model is not None  # the probe already validated through the sorting method
    ids = [c.id for c in model.classes]
    boundaries = lower_boundaries(model)
    shared = {name: getattr(probe, name) for name in SensitivityProbe.model_fields}
    return SortingSensitivityProbe(
        **shared,
        boundary_tolerance=TIE_TOL,
        classes=class_bands(model),
        class_by_alternative={
            a.alternative_id: ids[class_index(a.value, boundaries)] for a in probe.alternatives
        },
        baseline_class_by_alternative={
            a.alternative_id: ids[class_index(a.baseline_value, boundaries)]
            for a in probe.alternatives
        },
    )
