"""B5 immutable lifecycle, sparse overrides and protected saved defaults."""

import pytest

from mcda_studio.domain.criteria import (
    ControlPoint,
    LinearValueFunction,
    PiecewiseLinearValueFunction,
    QualitativeValueFunction,
)
from mcda_studio.domain.errors import ModelEditError, UnknownReferenceError, ValidationFailed
from mcda_studio.domain.preferences import AnalysisConfiguration, Scenario, WeightProfile
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps

from builders import flat_project, tiny_project


def scenario_project():
    return ps.create_scenario(tiny_project(), "Experiment", "experiment")


def test_create_duplicate_rename_and_clear_are_sparse_independent_and_immutable():
    p = scenario_project()
    before = p.fingerprint()
    q = ps.set_scenario_override(p, "experiment", "cost", LinearValueFunction())
    r = ps.duplicate_scenario(q, "experiment", "Copy", "copy")
    r = ps.rename_scenario(r, "copy", "Renamed")
    assert r.scenarios[1].id == "copy" and r.scenarios[1].name == "Renamed"
    r.scenarios[1].value_function_overrides["cost"].direction = "decreasing"
    assert q.scenarios[0].value_function_overrides["cost"].direction == "increasing"
    cleared = ps.clear_scenario_override(r, "copy", "cost")
    assert "cost" not in cleared.scenarios[1].value_function_overrides
    assert "cost" in cleared.scenarios[0].value_function_overrides
    assert p.fingerprint() == before
    for modified in [q, r, cleared]:
        assert modified.criteria == p.criteria and modified.performances == p.performances
        assert modified.weight_profiles == p.weight_profiles
    assert ps.create_scenario(p, "Experiment").scenarios[-1].id == "experiment_2"


def test_default_deletion_requires_explicit_atomic_repair_including_base():
    p = ps.set_default_scenario(scenario_project(), "experiment")
    before = p.fingerprint()
    with pytest.raises(ModelEditError, match="repair"):
        ps.remove_scenario(p, "experiment")
    with pytest.raises(UnknownReferenceError):
        ps.remove_scenario(p, "experiment", repair_default=True, replacement_scenario_id="missing")
    with pytest.raises(ModelEditError):
        ps.remove_scenario(
            p, "experiment", repair_default=True, replacement_scenario_id="experiment"
        )
    base = ps.remove_scenario(p, "experiment", repair_default=True)
    assert base.analysis.scenario_id is None and base.scenarios == []
    assert p.fingerprint() == before
    p = ps.create_scenario(p, "Other", "other")
    q = ps.remove_scenario(p, "experiment", repair_default=True, replacement_scenario_id="other")
    assert q.analysis.scenario_id == "other" and len(q.scenarios) == 1
    assert q.analysis.weight_profile_id == p.analysis.weight_profile_id


def test_profiles_resolve_explicit_then_scenario_then_first_and_preserve_saved_parameters():
    p = ps.add_weight_profile(
        scenario_project(),
        WeightProfile(id="other", name="Other", judgements={"cost": 1, "quality": 10}),
    )
    p.analysis.parameters = {"nested": {"keep": [1, 2]}}
    p = ps.set_scenario_profile(p, "experiment", "other")
    assert (
        svc.evaluate_project(p, AnalysisConfiguration(scenario_id="experiment")).weight_profile_id
        == "other"
    )
    assert (
        svc.evaluate_project(
            p, AnalysisConfiguration(scenario_id="experiment", weight_profile_id="default")
        ).weight_profile_id
        == "default"
    )
    q = ps.set_scenario_profile(p, "experiment", None)
    assert (
        svc.evaluate_project(q, AnalysisConfiguration(scenario_id="experiment")).weight_profile_id
        == "default"
    )
    assert ps.set_default_scenario(q, "experiment").analysis.parameters == p.analysis.parameters
    with pytest.raises(ModelEditError):
        ps.remove_weight_profile(p, "other")
    assert (
        ps.remove_weight_profile(p, "other", "default").scenarios[0].weight_profile_id == "default"
    )


@pytest.mark.parametrize(
    "operation",
    [
        lambda p: ps.rename_scenario(p, "absent", "Name"),
        lambda p: ps.duplicate_scenario(p, "absent", "Name"),
        lambda p: ps.set_scenario_profile(p, "experiment", "absent"),
        lambda p: ps.set_default_scenario(p, "absent"),
        lambda p: ps.clear_scenario_override(p, "experiment", "absent"),
    ],
)
def test_unknown_references_fail_without_mutating_project(operation):
    p = scenario_project()
    before = p.fingerprint()
    with pytest.raises(UnknownReferenceError):
        operation(p)
    assert p.fingerprint() == before


def test_bad_definitions_and_group_overrides_are_refused_but_local_data_are_not_imputed():
    p = scenario_project()
    before = p.fingerprint()
    for vf in [
        QualitativeValueFunction(mapping={"a": 0, "b": 1}),
        PiecewiseLinearValueFunction(
            points=[ControlPoint(x=1, value=0), ControlPoint(x=1, value=1)]
        ),
    ]:
        with pytest.raises(ModelEditError):
            ps.set_scenario_override(p, "experiment", "cost", vf)
    assert p.fingerprint() == before
    p = ps.add_criterion(p, "Group", crit_id="group")
    p = ps.add_criterion(p, "Child", crit_id="child", parent_id="group")
    with pytest.raises(ModelEditError):
        ps.set_scenario_override(p, "experiment", "group", LinearValueFunction())


def test_unselected_invalid_scenario_or_profile_does_not_block_base_or_sensitivity():
    p = tiny_project()
    expected = svc.evaluate_project(p)
    p = ps.add_weight_profile(p, WeightProfile(id="unfinished", name="Unfinished"))
    p = ps.add_scenario(
        p,
        Scenario(
            id="bad",
            name="Bad",
            weight_profile_id="unfinished",
            value_function_overrides={
                "cost": PiecewiseLinearValueFunction(
                    points=[ControlPoint(x=0, value=0), ControlPoint(x=100, value=0)]
                )
            },
        ),
    )
    assert not svc.validate(p).ok  # full Problems report still exposes the unrelated failures
    base = svc.evaluate_project(p, AnalysisConfiguration())
    assert base.ranking == expected.ranking
    assert svc.sensitivity_probe(p, "cost", 0.5, AnalysisConfiguration()).scenario_id is None
    with pytest.raises(ValidationFailed):
        svc.evaluate_project(p, AnalysisConfiguration(scenario_id="bad"))
    assert svc.validate_effective(p, AnalysisConfiguration()).validation.ok
    assert not svc.validate_effective(p, AnalysisConfiguration(scenario_id="bad")).validation.ok


def test_comparison_detects_tie_changes_without_reordering_ids_and_retains_profile_context():
    p = flat_project([[0.8, 0.2], [0.2, 0.8]], [2, 1])
    p = ps.add_weight_profile(
        p, WeightProfile(id="equal", name="Equal", judgements={"c0": 1, "c1": 1})
    )
    p = ps.add_scenario(p, Scenario(id="tie", name="Tie", weight_profile_id="equal"))
    before = p.fingerprint()
    r = svc.compare_scenarios(p, ["tie"], AnalysisConfiguration())
    outcome = r.scenarios[0]
    assert outcome.ranking == r.baseline.ranking
    assert outcome.rank_by_alternative == {"a0": 1, "a1": 1}
    assert outcome.ranking_differs_from_baseline and outcome.winner_differs_from_baseline
    assert outcome.weight_profile_id == "equal" and r.baseline.weight_profile_id == "default"
    assert outcome.delta_from_baseline == pytest.approx({"a0": -0.1, "a1": 0.1})
    assert "TIED_ALTERNATIVES" in {i.code for i in outcome.diagnostics}
    explicit = svc.compare_scenarios(
        p, ["tie"], AnalysisConfiguration(weight_profile_id="default", scenario_id="tie")
    )
    assert explicit.baseline.configuration.scenario_id is None
    assert explicit.scenarios[0].weight_profile_id == "default"
    assert not explicit.scenarios[0].winner_differs_from_baseline
    assert p.fingerprint() == before


def test_exact_baseline_is_not_lost_next_to_a_neighbouring_sweep_grid_point():
    p = flat_project([[0, 0], [0, 0]], [0.5, 1 / 3])
    sweep = svc.sensitivity(p, "c0", steps=21)
    assert sweep.base_weight == 0.6000000000000001
    assert sweep.base_weight in sweep.grid
    assert sweep.grid[0] == 0 and sweep.grid[-1] == 1


def test_reset_inherits_future_base_changes_and_criterion_deletion_cleans_scenarios():
    p = ps.set_scenario_override(scenario_project(), "experiment", "cost", LinearValueFunction())
    p = ps.duplicate_scenario(p, "experiment", "Copy", "copy")
    p = ps.clear_scenario_override(p, "copy", "cost")
    p = ps.set_value_function(p, "cost", LinearValueFunction())
    assert (
        svc.evaluate_project(p, AnalysisConfiguration(scenario_id="copy")).ranking
        == svc.evaluate_project(p).ranking
    )
    removed = ps.remove_criterion(p, "cost")
    assert all("cost" not in s.value_function_overrides for s in removed.scenarios)
    assert "cost" in p.scenarios[0].value_function_overrides


def test_selected_override_can_supply_a_missing_base_function_without_changing_base():
    p = ps.set_scenario_override(scenario_project(), "experiment", "cost", LinearValueFunction())
    p.criteria[0].value_function = None
    assert not svc.validate_effective(p, AnalysisConfiguration()).validation.ok
    result = svc.evaluate_project(p, AnalysisConfiguration(scenario_id="experiment"))
    assert len(result.ranking) == 2 and p.criteria[0].value_function is None


def test_scenario_local_domain_missing_data_and_fixed_outside_domain_fail_without_fallback():
    from mcda_studio.domain.scales import AnchorMode

    p = ps.set_scenario_override(scenario_project(), "experiment", "cost", LinearValueFunction())
    scale = p.tree().node("cost").scale.model_copy(update={"anchor_mode": AnchorMode.LOCAL})
    p = ps.set_scale(p, "cost", scale)
    p = ps.clear_performance(p, "a", "cost")
    preview = svc.preview_value_function(p, "cost", AnalysisConfiguration(scenario_id="experiment"))
    assert preview.readiness == "incomplete" and preview.resolved_domain is None
    with pytest.raises(ValidationFailed):
        svc.evaluate_project(p, AnalysisConfiguration(scenario_id="experiment"))
    p = ps.set_scale(
        p,
        "cost",
        scale.model_copy(update={"anchor_mode": AnchorMode.FIXED, "lower": 30, "upper": 50}),
    )
    p = ps.set_performance(p, "a", "cost", 20)
    with pytest.raises(ValidationFailed):
        svc.compare_scenarios(p, ["experiment"])


def test_probe_uses_selected_scenario_partial_values_against_independent_oracle():
    p = ps.set_scenario_override(scenario_project(), "experiment", "cost", LinearValueFunction())
    before = p.fingerprint()
    probe = svc.sensitivity_probe(p, "cost", 0.37, AnalysisConfiguration(scenario_id="experiment"))
    expected = {"a": 0.37 * 0.2 + 0.63 * 0.6, "b": 0.37 * 0.6 + 0.63 * 0.9}
    assert {a.alternative_id: a.value for a in probe.alternatives} == pytest.approx(expected)
    assert probe.scenario_id == "experiment" and p.fingerprint() == before


def test_duplicate_has_no_alias_to_source_even_before_a_followup_rebuild():
    p = ps.set_scenario_override(scenario_project(), "experiment", "cost", LinearValueFunction())
    before = p.fingerprint()
    copy = ps.duplicate_scenario(p, "experiment", "Copy", "copy")
    copy.scenarios[1].value_function_overrides["cost"].direction = "decreasing"
    assert p.fingerprint() == before
    assert copy.scenarios[0].value_function_overrides["cost"].direction == "increasing"
    assert p.scenarios[0].value_function_overrides["cost"].direction == "increasing"
