import pytest

from mcda_studio.domain.criteria import Direction, LinearValueFunction
from mcda_studio.domain.errors import ValidationFailed
from mcda_studio.domain.results import MavtResult
from mcda_studio.domain.scales import AnchorMode, Scale, ScaleType
from mcda_studio.methods.mavt.aggregation import evaluate_mavt, rank_values
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps

from builders import tiny_project


def test_hand_computed_scores_and_structure() -> None:
    r = evaluate_mavt(tiny_project())
    assert [x.alternative_id for x in r.ranking] == ["a", "b"]
    assert r.ranking[0].value == pytest.approx(0.8 * 2 / 3 + 0.6 / 3)
    assert r.ranking[1].value == pytest.approx(0.4 * 2 / 3 + 0.9 / 3)
    assert r.global_weights == {"cost": pytest.approx(2 / 3), "quality": pytest.approx(1 / 3)}
    top = r.alternatives[0]
    assert top.raw_measurements == {"cost": 20.0, "quality": 6.0}
    assert top.partial_values == {"cost": pytest.approx(0.8), "quality": pytest.approx(0.6)}
    assert sum(top.weighted_contributions.values()) == pytest.approx(top.overall_value)
    assert r.weight_basis and r.assumptions and r.leaf_order == ["cost", "quality"]


def test_contributions_sum_to_overall_for_every_alternative() -> None:
    r = evaluate_mavt(tiny_project())
    for alt in r.alternatives:
        assert sum(alt.weighted_contributions.values()) == pytest.approx(
            alt.overall_value, abs=1e-15
        )


def test_result_records_provenance() -> None:
    p = tiny_project()
    r = evaluate_mavt(p)
    assert r.project_id == p.id and r.project_fingerprint == p.fingerprint()
    assert r.weight_profile_id == "default" and r.scenario_id is None
    changed = ps.set_performance(p, "a", "cost", 25.0)
    assert evaluate_mavt(changed).project_fingerprint != r.project_fingerprint


def test_one_call_through_the_service_returns_a_mavt_result() -> None:
    r = svc.evaluate_project(tiny_project())
    assert isinstance(r, MavtResult) and r.method == "mavt"


def test_dominance_is_reported_not_applied() -> None:
    p = tiny_project()
    p = ps.set_performance(p, "b", "cost", 90.0)
    p = ps.set_performance(p, "b", "quality", 1.0)  # b now worse than a on both criteria
    r = evaluate_mavt(p)
    assert [(d.dominator_id, d.dominated_id) for d in r.dominance] == [("a", "b")]
    assert len(r.ranking) == 2  # nothing removed
    assert any(d.code == "DOMINANCE" for d in r.diagnostics)


def test_dominance_check_can_be_switched_off() -> None:
    p = tiny_project()
    cfg = p.analysis.model_copy(update={"parameters": {"dominance_check": False}})
    p = ps.set_performance(ps.set_performance(p, "b", "cost", 90.0), "b", "quality", 1.0)
    assert evaluate_mavt(p, cfg).dominance == []


def test_ties_share_a_rank() -> None:
    assert rank_values([0.5, 0.5, 0.2]) == [1, 1, 3]
    p = tiny_project()
    p = ps.set_performance(ps.set_performance(p, "b", "cost", 20.0), "b", "quality", 6.0)
    r = evaluate_mavt(p)
    assert [x.rank for x in r.ranking] == [1, 1]
    assert any(d.code == "TIED_ALTERNATIVES" for d in r.diagnostics)


def test_evaluation_refuses_an_invalid_model() -> None:
    p = ps.new_project("empty")
    with pytest.raises(ValidationFailed, match="NO_ALTERNATIVES|no alternatives"):
        evaluate_mavt(p)


def test_clamp_policy_is_reported_never_silent() -> None:
    p = tiny_project()
    p = ps.set_value_function(
        p, "cost", LinearValueFunction(direction=Direction.DECREASING, out_of_domain="clamp")
    )
    p = ps.set_performance(p, "a", "cost", 130.0)  # outside [0, 100]
    r = evaluate_mavt(p)
    a = next(x for x in r.alternatives if x.alternative_id == "a")
    assert a.partial_values["cost"] == 0.0 and a.clamped_criteria == ["cost"]
    assert any(d.code == "CLAMPED_MEASUREMENT" for d in r.diagnostics)


class TestFixedVersusLocalAnchors:
    """Adding an alternative must not move existing scores unless anchors were declared local."""

    @staticmethod
    def _with_mode(mode: AnchorMode) -> tuple[float, float]:
        p = tiny_project()
        scale = Scale(type=ScaleType.RATIO, lower=0.0, upper=100.0, anchor_mode=mode)
        p = ps.set_scale(p, "cost", scale)
        before = evaluate_mavt(p)
        p = ps.add_alternative(p, "C", alt_id="c")
        p = ps.set_performance(p, "c", "cost", 10.0)  # new minimum cost
        p = ps.set_performance(p, "c", "quality", 5.0)
        after = evaluate_mavt(p)
        pick = lambda r: next(x.overall_value for x in r.alternatives if x.alternative_id == "a")  # noqa: E731
        return pick(before), pick(after)

    def test_fixed_anchors_are_independent_of_the_alternative_set(self) -> None:
        before, after = self._with_mode(AnchorMode.FIXED)
        assert before == after

    def test_local_anchors_do_depend_and_are_recorded(self) -> None:
        before, after = self._with_mode(AnchorMode.LOCAL)
        assert before != after
        p = tiny_project()
        p = ps.set_scale(p, "cost", Scale(type=ScaleType.RATIO, anchor_mode=AnchorMode.LOCAL))
        r = evaluate_mavt(p)
        dom = r.resolved_domains["cost"]
        assert dom is not None and (dom.lower, dom.upper, dom.source) == (20.0, 60.0, "local")
        assert any(d.code == "LOCAL_ANCHORS" for d in r.diagnostics)


def test_scenario_value_function_override_changes_scores_only_for_that_scenario() -> None:
    from mcda_studio.domain.preferences import Scenario

    p = tiny_project()
    p = ps.add_scenario(
        p,
        Scenario(
            id="no_cost_pref",
            name="x",
            value_function_overrides={"cost": LinearValueFunction(direction=Direction.INCREASING)},
        ),
    )
    base = evaluate_mavt(p)
    cfg = p.analysis.model_copy(update={"scenario_id": "no_cost_pref"})
    scen = evaluate_mavt(p, cfg)
    assert [x.alternative_id for x in base.ranking] == ["a", "b"]
    assert [x.alternative_id for x in scen.ranking] == ["b", "a"]  # reversed preference on cost
    assert scen.scenario_id == "no_cost_pref"
    assert evaluate_mavt(p).ranking == base.ranking  # base unaffected
