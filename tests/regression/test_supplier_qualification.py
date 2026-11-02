"""The supplier qualification example against the independent sorting oracle.

``sorting_oracle`` reads the project file as JSON and never imports ``mcda_studio`` (checked below
in a clean interpreter); only this comparison module calls the engine.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import sorting_oracle as oracle

from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.results import MavtSortingResult, SortingSensitivityResult
from mcda_studio.domain.sorting import SortingModel
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples" / "supplier_qualification"
FILE = EXAMPLE / "project.json"
CONTEXTS = [(None, None), (None, "cost_focus"), ("linear_defects", None)]


def _build_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("qualification_build", EXAMPLE / "build.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def engine(scenario: str | None, profile: str | None) -> MavtSortingResult:
    project = JsonProjectRepository().load(FILE)
    cfg = project.analysis.model_copy(
        update={"scenario_id": scenario, "weight_profile_id": profile}
    )
    result = svc.evaluate_project(project, cfg)
    assert isinstance(result, MavtSortingResult)
    return result


def test_the_oracle_imports_nothing_from_mcda_studio() -> None:
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import sorting_oracle; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] == 'mcda_studio'))"
    )
    run = subprocess.run(
        [sys.executable, "-I", "-c", code, str(Path(__file__).parent)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert run.stdout.strip() == "[]"


def test_the_shipped_file_matches_its_build_script() -> None:
    built = _build_module().build_project()
    assert to_json_text(built) == FILE.read_text(encoding="utf-8")


@pytest.mark.parametrize(("scenario", "profile"), CONTEXTS)
def test_values_classes_distances_and_the_audit_sample_match_the_oracle(
    scenario: str | None, profile: str | None
) -> None:
    raw = oracle.load(FILE)
    values = oracle.overall_values(raw, scenario, profile)
    result = engine(scenario, profile)
    for r in result.ranking:
        assert r.value == pytest.approx(values[r.alternative_id], abs=1e-12)
    for a in result.assignments:
        assert a.class_id == oracle.class_of(values[a.alternative_id], raw)
        nearest = oracle.nearest_boundary(values[a.alternative_id], raw)
        assert nearest is not None and a.nearest_boundary_class_id == nearest[0]
        assert a.distance_to_nearest_boundary == pytest.approx(nearest[1], abs=1e-12)
    assert result.audit_sample is not None
    assert result.audit_sample.alternative_ids == oracle.audit_sample(values, raw)


def test_the_documented_classes_hold() -> None:
    classes = {
        context: {a.alternative_id: a.class_id for a in engine(*context).assignments}
        for context in CONTEXTS
    }
    assert classes[(None, None)] == {
        "apex": "qualified",
        "delta": "qualified",
        "evergreen": "conditional",
        "brightline": "not_qualified",
        "cobalt": "not_qualified",
    }
    assert "qualified" not in classes[(None, "cost_focus")].values()  # an empty class
    assert classes[("linear_defects", None)]["brightline"] == "conditional"
    base = engine(None, None)
    assert base.audit_sample is not None and base.audit_sample.alternative_ids == ["cobalt"]


@pytest.mark.parametrize("offset", [0.0, 0.5e-12, -0.5e-12, 2e-12, -2e-12])
def test_classes_match_the_oracle_at_just_above_and_just_below_every_alternative(
    offset: float,
) -> None:
    """Place a boundary at each alternative's own value, shifted by ``offset``, and compare."""
    raw = oracle.load(FILE)
    values = oracle.overall_values(raw)
    project = JsonProjectRepository().load(FILE)
    for alt, value in values.items():
        top = min(value + offset, 1.0)
        model = SortingModel(
            classes=ps.sorting_classes([("Above", top), ("Below", None)]), audit=None
        )
        moved = ps.set_sorting_model(project, model)
        raw["sorting"] = model.model_dump(mode="json")
        result = svc.evaluate_project(moved)
        assert isinstance(result, MavtSortingResult)
        got = next(a.class_id for a in result.assignments if a.alternative_id == alt)
        assert got == oracle.class_of(value, raw), (alt, offset)
        assert got == ("above" if offset <= 0.5e-12 else "below"), (alt, offset)


@pytest.mark.parametrize(("scenario", "profile"), CONTEXTS)
def test_class_change_weights_match_the_oracle_for_every_criterion(
    scenario: str | None, profile: str | None
) -> None:
    raw = oracle.load(FILE)
    project = JsonProjectRepository().load(FILE)
    cfg = project.analysis.model_copy(
        update={"scenario_id": scenario, "weight_profile_id": profile}
    )
    compared = 0
    for result in svc.sensitivity_all(project, cfg):
        assert isinstance(result, SortingSensitivityResult)
        expected = oracle.class_change_weights(raw, result.node_id, scenario, profile)
        for alt in result.class_changes:
            got = [(c.weight, c.boundary_class_id) for c in alt.change_points]
            want = expected[alt.alternative_id]
            assert [b for _, b in got] == [b for _, b in want]
            for (w_got, _), (w_want, _) in zip(got, want, strict=True):
                assert w_got == pytest.approx(w_want, abs=1e-12)
            compared += len(got)
    assert compared > 0


def test_mavt_values_are_untouched_by_the_classes() -> None:
    project = JsonProjectRepository().load(FILE)
    mavt = svc.evaluate_project(project, AnalysisConfiguration(method="mavt"))
    sorting = engine(None, None)
    assert [(r.alternative_id, r.value, r.rank) for r in mavt.ranking] == [
        (r.alternative_id, r.value, r.rank) for r in sorting.ranking
    ]
