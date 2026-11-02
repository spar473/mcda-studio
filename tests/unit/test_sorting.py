"""Value-based sorting: the boundary rule, validation, distances, audit sample and MAVT parity."""

import hashlib
from pathlib import Path

import pytest

from mcda_studio.domain.criteria import LinearValueFunction
from mcda_studio.domain.errors import ValidationFailed
from mcda_studio.domain.preferences import AnalysisConfiguration, Scenario
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import MavtResult, MavtSortingResult, ValueModelResult
from mcda_studio.domain.scales import AnchorMode
from mcda_studio.domain.sorting import SortingAudit, SortingClass, SortingModel
from mcda_studio.methods.base import validate_analysis
from mcda_studio.methods.mavt import MavtMethod
from mcda_studio.methods.sorting import MavtSortingMethod
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository

from builders import scored_project, with_classes

ROOT = Path(__file__).parents[2]
EXAMPLES = ROOT / "examples"
SORTING = AnalysisConfiguration(method="mavt_sorting")
TOL = 1e-12
THREE = [("Upper", 0.7), ("Middle", 0.4), ("Lower", None)]


def sort(project: Project, cfg: AnalysisConfiguration = SORTING) -> MavtSortingResult:
    result = svc.evaluate_project(project, cfg)
    assert isinstance(result, MavtSortingResult)
    return result


def classes_of(values: dict[str, float], classes: list[tuple[str, float | None]]) -> dict[str, str]:
    result = sort(with_classes(scored_project(values), classes))
    return {a.alternative_id: a.class_id for a in result.assignments}


def codes(project: Project, cfg: AnalysisConfiguration = SORTING) -> list[str]:
    return [i.code for i in validate_analysis(project, cfg).issues]


# ---- the boundary rule -------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.7, "upper"),  # exactly on the boundary: the higher class
        (0.7 + 2 * TOL, "upper"),
        (0.7 - 2 * TOL, "middle"),
        (0.7 + 0.5 * TOL, "upper"),  # inside the tolerance band, either side
        (0.7 - 0.5 * TOL, "upper"),
        (0.4, "middle"),
        (0.4 - 0.5 * TOL, "middle"),
        (0.4 - 2 * TOL, "lower"),
        (1.0, "upper"),
        (0.0, "lower"),
    ],
)
def test_a_value_on_or_within_tolerance_of_a_boundary_goes_to_the_higher_class(
    value: float, expected: str
) -> None:
    assert classes_of({"a": value}, THREE) == {"a": expected}


def test_classes_are_listed_best_first_with_their_ranges_and_members_in_rank_order() -> None:
    result = sort(with_classes(scored_project({"a": 0.5, "b": 0.9, "c": 0.45, "d": 0.1}), THREE))
    summary = [
        (c.class_id, c.rank, c.lower_boundary, c.upper_boundary, c.alternative_ids)
        for c in result.classes
    ]
    assert summary == [
        ("upper", 1, 0.7, None, ["b"]),
        ("middle", 2, 0.4, 0.7, ["a", "c"]),
        ("lower", 3, None, 0.4, ["d"]),
    ]
    assert [a.alternative_id for a in result.assignments] == ["b", "a", "c", "d"]
    assert [a.class_rank for a in result.assignments] == [1, 2, 2, 3]


def test_empty_and_single_classes_are_valid() -> None:
    empty = sort(with_classes(scored_project({"a": 0.2, "b": 0.3}), THREE))
    assert [c.alternative_ids for c in empty.classes] == [[], [], ["b", "a"]]  # rank order
    single = sort(with_classes(scored_project({"a": 0.2, "b": 0.9}), [("All", None)]))
    assert [c.class_id for c in single.classes] == ["all"]
    assert single.classes[0].lower_boundary is None and single.classes[0].upper_boundary is None
    assert all(
        a.class_id == "all"
        and a.distance_to_nearest_boundary is None
        and a.nearest_boundary_class_id is None
        and not a.on_boundary
        for a in single.assignments
    )


def test_distance_names_the_nearest_boundary_and_ties_go_to_the_higher_one() -> None:
    result = sort(with_classes(scored_project({"a": 0.55, "b": 0.69, "c": 0.4}), THREE))
    nearest = {
        a.alternative_id: (a.nearest_boundary_class_id, a.distance_to_nearest_boundary)
        for a in result.assignments
    }
    assert nearest["a"][0] == "upper" and nearest["a"][1] == pytest.approx(0.15)  # tie: 0.15 each
    assert nearest["b"] == ("upper", pytest.approx(0.01))
    assert nearest["c"] == ("middle", 0.0)
    on = {a.alternative_id for a in result.assignments if a.on_boundary}
    assert on == {"c"}
    infos = [d for d in result.diagnostics if d.code == "ON_CLASS_BOUNDARY"]
    assert len(infos) == 1 and infos[0].path == "sorting.classes[middle].lower_boundary"
    assert "assigned to Middle" in infos[0].message


# ---- validation ----------------------------------------------------------------------------------
def test_sorting_without_a_section_or_classes_is_refused() -> None:
    plain = scored_project({"a": 0.5, "b": 0.4})
    assert codes(plain) == ["NO_SORTING_MODEL"]
    with pytest.raises(ValidationFailed, match="NO_SORTING_MODEL"):
        svc.evaluate_project(plain, SORTING)
    assert codes(ps.set_sorting_model(plain, SortingModel())) == ["NO_CLASSES"]


def section(*classes: SortingClass, audit: SortingAudit | None = None) -> Project:
    model = SortingModel(classes=list(classes), audit=audit)
    return ps.set_sorting_model(scored_project({"a": 0.5, "b": 0.2}), model)


def c(class_id: str, boundary: float | None, name: str | None = None) -> SortingClass:
    return SortingClass(id=class_id, name=name or class_id.title(), lower_boundary=boundary)


@pytest.mark.parametrize(
    ("project", "expected"),
    [
        (section(c("a", 0.5, "One"), c("a", None, "Two")), ["DUPLICATE_CLASS_ID"]),
        (section(c("a", 0.5, "Same"), c("b", None, "same ")), ["DUPLICATE_CLASS_NAME"]),
        (section(c("a", None), c("b", None)), ["MISSING_CLASS_BOUNDARY"]),
        (section(c("a", 0.5), c("b", 0.2)), ["UNEXPECTED_CLASS_BOUNDARY"]),
        (section(c("a", 1.5), c("b", None)), ["BOUNDARY_OUT_OF_RANGE"]),
        (section(c("a", -0.1), c("b", None)), ["BOUNDARY_OUT_OF_RANGE"]),
        (section(c("a", 0.4), c("b", 0.6), c("c", None)), ["BOUNDARIES_NOT_DECREASING"]),
        (section(c("a", 0.5), c("b", 0.5), c("c", None)), ["BOUNDARIES_NOT_DECREASING"]),
        # exactly representable gaps either side of 2e-12: 2**-39 (1.8e-12) and 2**-38 (3.6e-12)
        (section(c("a", 0.5), c("b", 0.5 - 2**-39), c("c", None)), ["BOUNDARIES_NOT_DECREASING"]),
        (section(c("a", 0.5), c("b", 0.5 - 2**-38), c("c", None)), []),
        (section(c("a", 1.0), c("b", 0.0), c("c", None)), []),
        (
            section(
                c("a", 0.5),
                c("b", None),
                audit=SortingAudit(below_class_id="x", sample_size=1, seed=0),
            ),
            ["UNKNOWN_AUDIT_CLASS"],
        ),
        (
            section(
                c("a", 0.5),
                c("b", None),
                audit=SortingAudit(below_class_id="b", sample_size=1, seed=0),
            ),
            ["AUDIT_BELOW_LOWEST_CLASS"],
        ),
        (
            section(
                c("a", 0.5),
                c("b", None),
                audit=SortingAudit(below_class_id="a", sample_size=0, seed=0),
            ),
            ["INVALID_AUDIT_SAMPLE_SIZE"],
        ),
    ],
)
def test_every_sorting_rule_has_its_own_code(project: Project, expected: list[str]) -> None:
    assert codes(project) == expected


def test_out_of_order_boundaries_are_refused_never_reordered() -> None:
    project = section(c("a", 0.4), c("b", 0.6), c("c", None))
    issue = validate_analysis(project, SORTING).issues[0]
    assert issue.path == "sorting.classes[b].lower_boundary"
    assert "never reordered automatically" in issue.message and "'A'" in issue.message
    with pytest.raises(ValidationFailed):
        svc.evaluate_project(project, SORTING)
    assert project.sorting is not None
    assert [k.lower_boundary for k in project.sorting.classes] == [0.4, 0.6, None]


def test_mavt_checks_run_unchanged_and_first_under_sorting() -> None:
    supplier = JsonProjectRepository().load(EXAMPLES / "supplier_selection" / "project.json")
    project = with_classes(supplier, THREE)
    mavt = MavtMethod().validate(project, project.analysis)
    sorting = MavtSortingMethod().validate(
        project, project.analysis.model_copy(update={"method": "mavt_sorting"})
    )
    assert sorting[: len(mavt)] == mavt
    assert [i.code for i in sorting[len(mavt) :]] == ["SORTING_LOCAL_ANCHORS"]
    assert "logistics_cost" in sorting[-1].message and "fixed anchors" in sorting[-1].message


def test_a_scenario_that_introduces_local_anchors_warns_only_when_viewed() -> None:
    qualification = JsonProjectRepository().load(
        EXAMPLES / "supplier_qualification" / "project.json"
    )
    assert "SORTING_LOCAL_ANCHORS" not in codes(qualification, qualification.analysis)
    local = qualification.model_copy(deep=True)
    node = next(n for n in local.criteria if n.id == "unit_price")
    assert node.scale is not None
    node.scale.anchor_mode = AnchorMode.LOCAL
    local.scenarios.append(
        Scenario(
            id="local", name="Local", value_function_overrides={"unit_price": LinearValueFunction()}
        )
    )
    viewed = qualification.analysis.model_copy(update={"scenario_id": "local"})
    assert codes(local, viewed).count("SORTING_LOCAL_ANCHORS") == 1


# ---- audit sample --------------------------------------------------------------------------------
def audit_project(order: list[str], sample_size: int = 2, seed: int = 7) -> Project:
    values = {"a": 0.9, "b": 0.5, "c": 0.45, "d": 0.3, "e": 0.1, "f": 0.05}
    audit = SortingAudit(below_class_id="upper", sample_size=sample_size, seed=seed)
    return with_classes(scored_project({k: values[k] for k in order}), THREE, audit)


def expected_sample(pool: list[str], seed: int, size: int) -> list[str]:
    key = {a: hashlib.sha256(f"{seed}:{a}".encode()).hexdigest() for a in pool}
    return sorted(pool, key=lambda a: (key[a], a))[:size]


def test_the_audit_sample_is_seed_keyed_from_below_the_cut_off_only() -> None:
    result = sort(audit_project(list("abcdef")))
    sample = result.audit_sample
    assert sample is not None and sample.pool_size == 5  # "a" is in the cut-off class itself
    assert sample.alternative_ids == expected_sample(list("bcdef"), 7, 2)
    assert sample.selection_rule == "sha256(seed:alternative_id) ascending, then id"
    other = sort(audit_project(list("abcdef"), seed=8)).audit_sample
    assert other is not None and other.alternative_ids == expected_sample(list("bcdef"), 8, 2)


def test_the_audit_sample_does_not_depend_on_alternative_order() -> None:
    forward = sort(audit_project(list("abcdef"))).audit_sample
    backward = sort(audit_project(list("fedcba"))).audit_sample
    assert forward == backward


def test_a_small_or_empty_pool_is_reported() -> None:
    whole = sort(audit_project(list("abcdef"), sample_size=9))
    assert whole.audit_sample is not None and len(whole.audit_sample.alternative_ids) == 5
    assert "AUDIT_SAMPLE_IS_WHOLE_POOL" in [d.code for d in whole.diagnostics]
    empty = sort(audit_project(["a"]))
    assert empty.audit_sample is not None and empty.audit_sample.alternative_ids == []
    assert [d.code for d in empty.diagnostics if d.code.startswith("AUDIT")] == ["AUDIT_POOL_EMPTY"]


# ---- MAVT parity ---------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "name", ["supplier_selection", "infrastructure_procurement", "nz_deeptech_vc"]
)
def test_sorting_carries_every_mavt_field_unchanged(name: str) -> None:
    project = with_classes(JsonProjectRepository().load(EXAMPLES / name / "project.json"), THREE)
    contexts = [{"scenario_id": None}] + [{"scenario_id": s.id} for s in project.scenarios]
    for update in contexts:
        cfg = project.analysis.model_copy(update=update)
        mavt = svc.evaluate_project(project, cfg)
        sorted_ = sort(project, cfg.model_copy(update={"method": "mavt_sorting"}))
        assert isinstance(mavt, MavtResult)
        for field in ValueModelResult.model_fields:
            if field in {"method", "configuration", "diagnostics", "assumptions"}:
                continue
            assert getattr(sorted_, field) == getattr(mavt, field), field
        own = [
            d
            for d in sorted_.diagnostics
            if d.code in {"SORTING_LOCAL_ANCHORS", "ON_CLASS_BOUNDARY"}
        ]
        assert [d for d in sorted_.diagnostics if d not in own] == mavt.diagnostics
        assert sorted_.assumptions[:-1] == mavt.assumptions
        assert sorted_.schema_version == 2 and mavt.schema_version == 2  # the project has classes


def test_mavt_ignores_the_sorting_section() -> None:
    supplier = JsonProjectRepository().load(EXAMPLES / "supplier_selection" / "project.json")
    plain = svc.evaluate_project(supplier)
    with_section = svc.evaluate_project(with_classes(supplier, THREE))
    assert isinstance(plain, MavtResult) and isinstance(with_section, MavtResult)
    differs = {f for f in MavtResult.model_fields if getattr(plain, f) != getattr(with_section, f)}
    assert differs == {
        "schema_version",
        "project_fingerprint",
    }  # the file changed, not the analysis


# ---- saved method --------------------------------------------------------------------------------
def test_changing_the_saved_method_clears_its_parameters_and_unknown_methods_are_refused() -> None:
    project = scored_project({"a": 0.5})
    project = project.model_copy(
        update={
            "analysis": project.analysis.model_copy(
                update={"parameters": {"dominance_check": False}}
            )
        }
    )
    same = ps.set_analysis_method(project, "mavt")
    assert same.analysis.parameters == {"dominance_check": False}
    moved = ps.set_analysis_method(project, "mavt_sorting")
    assert moved.analysis.method == "mavt_sorting" and moved.analysis.parameters == {}
    with pytest.raises(Exception, match="unknown MCDA method"):
        ps.set_analysis_method(project, "nope")
