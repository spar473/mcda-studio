"""The arbitrary-weight sensitivity probe: exact scores and competition ranks, read-only.

The probe exists so the GUI can read values at a point the server grid does not contain - most
importantly an exact crossover - without interpolating or ranking in the browser. These tests
pin that it reuses the engine rather than approximating it.
"""

import math

import pytest

from mcda_studio.domain.errors import SensitivityError
from mcda_studio.domain.preferences import Scenario
from mcda_studio.methods.mavt.sensitivity import sensitivity_probe, weight_sensitivity
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps

from builders import flat_project, tiny_project

VC = "examples/nz_deeptech_vc/project.json"


def vc():
    from mcda_studio.storage.json_repository import JsonProjectRepository

    return JsonProjectRepository().load(VC)


# ---- redistribution -----------------------------------------------------------------------
def test_three_siblings_redistribute_proportionally_and_keep_their_ratio() -> None:
    """50:30:20 baseline; forcing the first to 0.7 leaves 0.18 and 0.12, still 3:2."""
    p = flat_project([[0.2, 0.9, 0.5], [0.8, 0.1, 0.4]], [50.0, 30.0, 20.0])
    probe = sensitivity_probe(p, None, "c0", 0.7)
    assert probe.local_weights["c0"] == pytest.approx(0.7, abs=1e-15)
    assert probe.local_weights["c1"] == pytest.approx(0.18, abs=1e-15)
    assert probe.local_weights["c2"] == pytest.approx(0.12, abs=1e-15)
    # the untouched pair keeps exactly its original 30:20 ratio
    assert probe.local_weights["c1"] / probe.local_weights["c2"] == pytest.approx(30 / 20)
    assert math.fsum(probe.local_weights.values()) == pytest.approx(1.0, abs=1e-15)


@pytest.mark.parametrize("t", [0.0, 1e-9, 0.5, 1 - 1e-9, 1.0])
def test_global_weights_stay_normalised_at_and_near_the_boundaries(t: float) -> None:
    p = flat_project([[0.2, 0.9, 0.5], [0.8, 0.1, 0.4]], [50.0, 30.0, 20.0])
    probe = sensitivity_probe(p, None, "c0", t)
    assert math.fsum(probe.global_weights.values()) == pytest.approx(1.0, abs=1e-12)
    assert probe.weight == t


def test_an_unaffected_branch_keeps_its_share_when_a_leaf_is_varied() -> None:
    """Varying a leaf redistributes inside its own group only; the parent's share is preserved."""
    p = vc()
    probe = sensitivity_probe(p, None, "market_size", 0.9)
    assert probe.path_shares["market"] == pytest.approx(probe.base_weight * 0 + 4 / 17, abs=1e-12)
    # Team's branch, and its leaves, are untouched by a change inside Market.
    base = svc.preview_weights(p)
    for node in ["team", "founder_expertise", "team_coverage", "problem_solution", "traction"]:
        assert probe.path_shares[node] == pytest.approx(base.path_shares[node], abs=1e-15)
    # Inside Market the split follows the probe, and the branch still sums to its parent share.
    assert probe.global_weights["market_size"] + probe.global_weights["market_growth"] == (
        pytest.approx(probe.path_shares["market"], abs=1e-15)
    )
    assert probe.global_weights["market_size"] == pytest.approx(0.9 * 4 / 17, abs=1e-15)


def test_path_shares_come_from_the_engine_not_from_rounded_leaf_weights() -> None:
    p = vc()
    probe = sensitivity_probe(p, None, "team", 0.5688552162065278)
    leaves_under = {
        "team": ["founder_expertise", "team_coverage"],
        "problem_solution": ["problem_significance", "solution_viability"],
        "market": ["market_size", "market_growth"],
        "traction": ["customer_validation", "execution_maturity"],
    }
    for objective, leaves in leaves_under.items():
        children = math.fsum(probe.global_weights[leaf] for leaf in leaves)
        assert children == pytest.approx(probe.path_shares[objective], abs=1e-15)
    assert math.fsum(probe.global_weights.values()) == pytest.approx(1.0, abs=1e-15)


# ---- agreement with the rest of the engine ------------------------------------------------
def test_at_the_baseline_the_probe_reproduces_the_real_evaluation_exactly() -> None:
    """The probe must agree with the Results screen bit for bit, not merely closely.

    It uses `overall_values` (math.fsum), the same summation the real evaluation uses. The sweep
    grid uses a numpy matmul and can differ in the last bit; see the probe/sweep test below.
    """
    p = vc()
    base = {r.alternative_id: r.value for r in svc.evaluate_project(p).ranking}
    probe = sensitivity_probe(p, None, "team", weight_sensitivity(p, None, "team").base_weight)
    for a in probe.alternatives:
        assert a.value == base[a.alternative_id]
        assert a.baseline_value == base[a.alternative_id]
    assert probe.ranking == probe.baseline_ranking
    assert not probe.ranking_differs_from_baseline and not probe.winner_differs_from_baseline
    assert "PROBE_AT_BASELINE" in {d.code for d in probe.diagnostics}


def test_the_probe_matches_the_sweep_grid_to_within_one_ulp() -> None:
    p = vc()
    sweep = weight_sensitivity(p, None, "team")
    for i, t in enumerate(sweep.grid):
        probe = sensitivity_probe(p, None, "team", t)
        for a in probe.alternatives:
            assert a.value == pytest.approx(sweep.values[a.alternative_id][i], abs=2.3e-16)


@pytest.mark.regression
def test_the_vc_winner_change_is_an_exact_tie_at_the_crossover() -> None:
    """At the crossover the top two are tied; the probe must not invent a unique winner."""
    p = vc()
    sweep = weight_sensitivity(p, None, "team")
    assert sweep.first_winner_change_up is not None
    t = sweep.first_winner_change_up.weight
    assert t == pytest.approx(0.569, abs=5e-4)
    probe = sensitivity_probe(p, None, "team", t)
    top = [a for a in probe.alternatives if a.rank == 1]
    assert {a.alternative_id for a in top} == {"forever_harvest", "outlier_space"}
    assert top[0].value == pytest.approx(top[1].value, abs=1e-12)
    assert "TIED_ALTERNATIVES" in {d.code for d in probe.diagnostics}
    # Competition ranks, not array positions: the next alternative is rank 3, never rank 2.
    assert [a.rank for a in probe.alternatives] == [1, 1, 3, 4]
    # Just past the crossover the winner really does change.
    after = sensitivity_probe(p, None, "team", t + 1e-6)
    assert after.ranking[0] == "outlier_space" and after.winner_differs_from_baseline


@pytest.mark.regression
@pytest.mark.parametrize(
    ("node", "expected"), [("team", 0.569), ("market", 0.674), ("market_size", 0.873)]
)
def test_documented_first_winner_change_thresholds(node: str, expected: float) -> None:
    sweep = weight_sensitivity(vc(), None, node)
    assert sweep.first_winner_change_up is not None
    assert sweep.first_winner_change_up.weight == pytest.approx(expected, abs=5e-4)


def test_the_hand_checkable_cost_quality_crossover_probes_as_a_tie() -> None:
    probe = sensitivity_probe(tiny_project(), None, "cost", 3 / 7)
    assert [a.rank for a in probe.alternatives] == [1, 1]
    assert probe.alternatives[0].value == pytest.approx(probe.alternatives[1].value, abs=1e-15)


# ---- ranking semantics --------------------------------------------------------------------
def test_coincident_alternatives_share_a_rank_everywhere() -> None:
    p = flat_project([[0.4, 0.6], [0.4, 0.6]], [50.0, 50.0])
    for t in [0.0, 0.25, 0.5, 1.0]:
        probe = sensitivity_probe(p, None, "c0", t)
        assert [a.rank for a in probe.alternatives] == [1, 1]
        assert "TIED_ALTERNATIVES" in {d.code for d in probe.diagnostics}


def test_a_single_alternative_is_always_rank_one() -> None:
    p = flat_project([[0.3, 0.7]], [50.0, 50.0])
    probe = sensitivity_probe(p, None, "c0", 0.8)
    assert [a.rank for a in probe.alternatives] == [1]
    assert not probe.ranking_differs_from_baseline


def test_a_rank_swap_below_the_winner_is_not_a_winner_change() -> None:
    p = flat_project([[0.9, 0.9], [0.1, 0.8], [0.8, 0.1]], [50.0, 50.0])
    low = sensitivity_probe(p, None, "c0", 0.1)
    high = sensitivity_probe(p, None, "c0", 0.9)
    assert low.ranking[0] == high.ranking[0] == "a0"  # the leader never changes
    assert low.ranking != high.ranking  # but the pair below it swaps
    assert low.ranking_differs_from_baseline or high.ranking_differs_from_baseline
    assert not (low.winner_differs_from_baseline or high.winner_differs_from_baseline)


def test_a_zero_weight_criterion_with_eligible_siblings_can_still_be_probed() -> None:
    p = flat_project([[0.2, 0.9], [0.8, 0.1]], [0.0, 50.0])
    probe = sensitivity_probe(p, None, "c0", 0.6)
    assert probe.base_weight == 0.0
    assert probe.local_weights["c0"] == pytest.approx(0.6)
    assert probe.local_weights["c1"] == pytest.approx(0.4)


# ---- refusals -----------------------------------------------------------------------------
@pytest.mark.parametrize("weight", [-1e-9, 1.0000001, float("inf"), float("nan"), -0.5, 2.0])
def test_weights_outside_the_unit_interval_are_refused(weight: float) -> None:
    with pytest.raises(SensitivityError, match="finite number"):
        sensitivity_probe(tiny_project(), None, "cost", weight)


def test_ineligible_nodes_are_refused_with_the_same_rules_as_the_sweep() -> None:
    p = tiny_project()
    with pytest.raises(SensitivityError, match="unknown criterion"):
        sensitivity_probe(p, None, "ghost", 0.5)
    # A real only child in a valid model: the sweep and the probe refuse for the same reason.
    from mcda_studio.storage.json_repository import JsonProjectRepository

    infra = JsonProjectRepository().load("examples/infrastructure_procurement/project.json")
    assert infra.tree().child_ids("delivery") == ["track_record"]
    for call in (
        lambda: sensitivity_probe(infra, None, "track_record", 0.5),
        lambda: weight_sensitivity(infra, None, "track_record"),
    ):
        with pytest.raises(SensitivityError, match="no siblings"):
            call()


def test_a_unit_weight_group_is_refused_because_redistribution_is_undefined() -> None:
    p = flat_project([[0.2, 0.9], [0.8, 0.1]], [50.0, 0.0])
    with pytest.raises(SensitivityError, match="local weight 1"):
        sensitivity_probe(p, None, "c0", 0.5)


# ---- read-only ----------------------------------------------------------------------------
def test_probing_never_changes_the_project_or_its_fingerprint() -> None:
    p = vc()
    before, fingerprint = p.model_dump_json(), p.fingerprint()
    for t in [0.0, 0.25, 0.5688552162065278, 0.9, 1.0]:
        probe = sensitivity_probe(p, None, "team", t)
        assert probe.project_fingerprint == fingerprint
    assert p.model_dump_json() == before and p.fingerprint() == fingerprint
    # The raw swing judgements in particular are untouched: a probe is not an elicitation.
    assert p.weight_profiles[0].judgements["team"] == 100.0


def test_the_probe_reports_the_context_it_actually_resolved() -> None:
    p = ps.add_scenario(
        ps.duplicate_weight_profile(tiny_project(), "default", "Other", "other"),
        Scenario(id="s", name="S", weight_profile_id="other"),
    )
    probe = sensitivity_probe(p, p.analysis.model_copy(update={"scenario_id": "s"}), "cost", 0.5)
    assert probe.weight_profile_id == "other" and probe.scenario_id == "s"
    explicit = p.analysis.model_copy(update={"scenario_id": "s", "weight_profile_id": "default"})
    assert sensitivity_probe(p, explicit, "cost", 0.5).weight_profile_id == "default"
    assert probe.node_path == ["cost"] and probe.node_name == "Cost"


def test_different_profiles_give_different_probes_for_the_same_weight() -> None:
    p = ps.set_judgement(
        ps.duplicate_weight_profile(vc(), "default", "Other", "other"), "team", 10.0, "other"
    )
    a = sensitivity_probe(p, None, "market_size", 0.9)
    b = sensitivity_probe(
        p, p.analysis.model_copy(update={"weight_profile_id": "other"}), "market_size", 0.9
    )
    assert a.weight_profile_id == "default" and b.weight_profile_id == "other"
    assert a.global_weights["market_size"] != b.global_weights["market_size"]


@pytest.mark.parametrize(
    ("matrix", "ratings", "weight", "winner_changed"),
    [
        ([[0.8, 0.2], [0.2, 0.8]], [80.0, 20.0], 0.5, True),
        ([[0.8, 0.2], [0.2, 0.8]], [50.0, 50.0], 0.8, True),
        ([[0.9, 0.9], [0.8, 0.2], [0.2, 0.8]], [80.0, 20.0], 0.5, False),
    ],
)
def test_change_flags_detect_ties_without_a_sorted_id_order_change(
    matrix: list[list[float]], ratings: list[float], weight: float, winner_changed: bool
) -> None:
    project = flat_project(matrix, ratings)
    before = project.fingerprint()
    probe = sensitivity_probe(project, None, "c0", weight)
    assert probe.ranking == probe.baseline_ranking
    assert probe.ranking_differs_from_baseline
    assert probe.winner_differs_from_baseline is winner_changed
    assert project.fingerprint() == before
