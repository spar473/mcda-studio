"""Exact class changes along a one-way weight sensitivity, cross-checked independently."""

from pathlib import Path

import pytest
from scipy.optimize import brentq

from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.previews import SortingSensitivityProbe
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import SensitivityResult, SortingSensitivityResult
from mcda_studio.services import analysis_service as svc
from mcda_studio.storage.json_repository import JsonProjectRepository

from builders import tiny_project, with_classes

ROOT = Path(__file__).parents[2]
SORTING = AnalysisConfiguration(method="mavt_sorting")
TOL = 1e-12


def sweep(
    project: Project, node: str, cfg: AnalysisConfiguration = SORTING
) -> SortingSensitivityResult:
    result = svc.sensitivity(project, node, cfg)
    assert isinstance(result, SortingSensitivityResult)
    return result


def test_the_tiny_project_changes_class_at_its_hand_derived_weights() -> None:
    """V_a(t) = 0.6 + 0.2 t and V_b(t) = 0.9 - 0.5 t; the boundary is 0.7, so the engine's rule
    switches where V = 0.7 - 1e-12: a at t = 0.5 - 5e-12 (rising), b at 0.4 + 2e-12 (falling)."""
    result = sweep(with_classes(tiny_project(), [("Upper", 0.7), ("Lower", None)]), "cost")
    a, b = sorted(result.class_changes, key=lambda c: c.alternative_id)
    assert (a.base_class_id, b.base_class_id) == ("upper", "lower")
    (ca,) = a.change_points
    assert ca.weight == pytest.approx(0.5 - 5 * TOL, abs=1e-15)
    assert (ca.boundary_class_id, ca.class_before, ca.class_after) == ("upper", "lower", "upper")
    assert a.first_change_down == ca and a.first_change_up is None
    assert a.class_stable_range == (ca.weight, 1.0)
    (cb,) = b.change_points
    assert cb.weight == pytest.approx(0.4 + 2 * TOL, abs=1e-15)
    assert (cb.class_before, cb.class_after) == ("upper", "lower")
    assert b.first_change_down == cb and b.first_change_up is None
    assert [c.class_id for c in result.classes] == ["upper", "lower"]


def test_class_changes_match_brentq_on_the_independent_probe_path_and_the_probed_classes() -> None:
    project = JsonProjectRepository().load(
        ROOT / "examples" / "supplier_qualification" / "project.json"
    )
    checked = 0
    for result in svc.sensitivity_all(project):
        assert isinstance(result, SortingSensitivityResult)
        bounds = {c.class_id: c.lower_boundary for c in result.classes}
        for alt in result.class_changes:
            for change in alt.change_points:
                threshold = bounds[change.boundary_class_id]
                assert threshold is not None

                def gap(
                    t: float,
                    a: str = alt.alternative_id,
                    b: float = threshold,
                    node: str = result.node_id,
                ) -> float:
                    probe = svc.sensitivity_probe(project, node, t)
                    value = next(x.value for x in probe.alternatives if x.alternative_id == a)
                    return value - (b - TOL)

                lo, hi = max(0.0, change.weight - 0.05), min(1.0, change.weight + 0.05)
                assert brentq(gap, lo, hi, xtol=1e-14) == pytest.approx(change.weight, abs=1e-9)
                for t, expected in [
                    (change.weight - 1e-9, change.class_before),
                    (change.weight + 1e-9, change.class_after),
                ]:
                    if 0.0 <= t <= 1.0:
                        probe = svc.sensitivity_probe(project, result.node_id, t)
                        assert isinstance(probe, SortingSensitivityProbe)
                        assert probe.class_by_alternative[alt.alternative_id] == expected
                checked += 1
    assert checked >= 5  # the example has real class changes to check


def test_the_first_change_either_way_brackets_the_baseline_class() -> None:
    project = JsonProjectRepository().load(
        ROOT / "examples" / "supplier_qualification" / "project.json"
    )
    for result in svc.sensitivity_all(project):
        assert isinstance(result, SortingSensitivityResult)
        for alt in result.class_changes:
            lo, hi = alt.class_stable_range
            assert lo <= result.base_weight <= hi
            if alt.first_change_up:
                assert alt.first_change_up.weight >= result.base_weight
                assert alt.first_change_up.class_after != alt.base_class_id
            if alt.first_change_down:
                assert alt.first_change_down.weight <= result.base_weight
                assert alt.first_change_down.class_before != alt.base_class_id


def test_a_baseline_exactly_on_a_boundary_is_flagged() -> None:
    project = tiny_project()
    value = next(r.value for r in svc.evaluate_project(project).ranking if r.alternative_id == "a")
    result = sweep(with_classes(project, [("Upper", value), ("Lower", None)]), "cost")
    assert "BASELINE_ON_CLASS_BOUNDARY" in [d.code for d in result.diagnostics]
    a = next(c for c in result.class_changes if c.alternative_id == "a")
    assert a.base_class_id == "upper"
    assert a.first_change_down is not None
    assert a.first_change_down.weight == pytest.approx(2 / 3, abs=1e-9)


def test_sorting_sensitivity_keeps_every_mavt_field_and_mavt_gains_none() -> None:
    project = with_classes(tiny_project(), [("Upper", 0.7), ("Lower", None)])
    mavt = svc.sensitivity(project, "cost")
    assert type(mavt) is SensitivityResult
    assert "class_changes" not in mavt.model_dump()
    sorting = sweep(project, "cost")
    for field in SensitivityResult.model_fields:
        assert getattr(sorting, field) == getattr(mavt, field), field
    probe = svc.sensitivity_probe(project, "cost", 0.3, SORTING)  # a = 0.66, b = 0.75
    assert isinstance(probe, SortingSensitivityProbe)
    assert probe.class_by_alternative == {"a": "lower", "b": "upper"}
    assert probe.baseline_class_by_alternative == {"a": "upper", "b": "lower"}
