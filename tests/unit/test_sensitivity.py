import numpy as np
import pytest
from scipy.optimize import brentq

from mcda_studio.domain.errors import SensitivityError
from mcda_studio.domain.preferences import Scenario
from mcda_studio.domain.project import Project
from mcda_studio.methods.mavt.aggregation import evaluate_mavt, prepare_mavt
from mcda_studio.methods.mavt.sensitivity import (
    _global_with,
    compare_scenarios,
    sensitivity_all,
    weight_sensitivity,
)
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps

from builders import flat_project, tiny_project


def test_tiny_project_crossover_is_exact() -> None:
    r = weight_sensitivity(tiny_project(), None, "cost")
    assert r.base_weight == pytest.approx(2 / 3)
    assert len(r.crossovers) == 1
    c = r.crossovers[0]
    assert c.weight == pytest.approx(3 / 7, abs=1e-15)  # exact, not grid-limited
    assert (c.leader_before, c.leader_after) == ("b", "a")
    assert r.first_winner_change_up is None
    assert r.first_winner_change_down is not None
    assert r.first_winner_change_down.weight == pytest.approx(3 / 7)
    assert (r.first_winner_change_down.from_winner, r.first_winner_change_down.to_winner) == (
        "a",
        "b",
    )
    assert r.ranking_stable_range == (pytest.approx(3 / 7), 1.0)
    assert r.winner_stable_range == (pytest.approx(3 / 7), 1.0)


def test_baseline_is_in_the_grid_and_matches_the_unchanged_evaluation() -> None:
    p = tiny_project()
    r = weight_sensitivity(p, None, "cost", steps=11)
    base = evaluate_mavt(p)
    i = r.grid.index(r.base_weight)
    for alt in base.ranking:
        assert r.values[alt.alternative_id][i] == pytest.approx(alt.value, abs=1e-12)
        assert r.baseline_values[alt.alternative_id] == pytest.approx(alt.value, abs=1e-15)
    assert r.baseline_ranking == [a.alternative_id for a in base.ranking]


def test_grid_rankings_agree_with_the_exact_crossover() -> None:
    r = weight_sensitivity(tiny_project(), None, "cost", steps=101)
    for t, ranking in zip(r.grid, r.rankings, strict=True):
        assert ranking[0] == ("b" if t < 3 / 7 else "a")


def _values_with_weight(values: list[list[float]], ratings: list[float], t: float) -> list[float]:
    """Independent route: bake the redistributed weights into the ratings and evaluate."""
    rest = sum(ratings[1:])
    new = [t] + [(1 - t) * r / rest for r in ratings[1:]]
    r = evaluate_mavt(flat_project(values, new))
    by_id = {x.alternative_id: x.value for x in r.ranking}
    return [by_id[f"a{i}"] for i in range(len(values))]


def test_crossovers_agree_with_brentq_on_an_independent_evaluation_path() -> None:
    values = [[0.9, 0.2, 0.5], [0.3, 0.8, 0.6], [0.6, 0.6, 0.1], [0.1, 0.4, 0.9]]
    ratings = [50.0, 30.0, 20.0]
    r = weight_sensitivity(flat_project(values, ratings), None, "c0")
    assert r.crossovers, "fixture should produce crossovers"
    for c in r.crossovers:
        i, k = int(c.alternative_a[1:]), int(c.alternative_b[1:])

        def diff(t: float, i: int = i, k: int = k) -> float:
            v = _values_with_weight(values, ratings, t)
            return v[i] - v[k]

        root = brentq(diff, 0.0, 1.0, xtol=1e-14)
        assert c.weight == pytest.approx(root, abs=1e-9)


def test_weights_stay_normalised_at_every_grid_point() -> None:
    p = flat_project([[0.2, 0.9], [0.8, 0.1]], [60.0, 40.0])
    prep = prepare_mavt(p, p.analysis)
    for t in np.linspace(0, 1, 21):
        w = _global_with(prep, "c0", float(t))
        assert w.sum() == pytest.approx(1.0, abs=1e-14)
        assert w[0] == pytest.approx(t)


def test_other_siblings_keep_their_relative_ratios() -> None:
    p = flat_project([[0.2, 0.9, 0.5], [0.8, 0.1, 0.4]], [60.0, 30.0, 10.0])
    prep = prepare_mavt(p, p.analysis)
    for t in (0.0, 0.25, 0.9):
        w = _global_with(prep, "c0", t)
        assert w[1] / w[2] == pytest.approx(3.0)


def test_parent_and_leaf_sensitivity_both_work_on_a_hierarchy() -> None:
    from pathlib import Path

    from mcda_studio.storage.json_repository import JsonProjectRepository

    path = Path(__file__).parents[2] / "examples" / "supplier_selection" / "project.json"
    p = JsonProjectRepository().load(path)
    parent = weight_sensitivity(p, None, "performance")
    leaf = weight_sensitivity(p, None, "unit_price")
    assert parent.node_id == "performance" and leaf.node_id == "unit_price"
    # structural invariant: ranking constant between consecutive crossovers
    for res in (parent, leaf):
        by_segment: dict[int, list[list[str]]] = {}
        for t, ranking in zip(res.grid, res.rankings, strict=True):
            segment = sum(1 for b in res.rank_change_points if b < t - 1e-9)
            by_segment.setdefault(segment, []).append(ranking)
        for rankings in by_segment.values():
            assert all(rk == rankings[0] for rk in rankings)
        # and the ranking really differs across consecutive segments
        firsts = [v[0] for _, v in sorted(by_segment.items())]
        assert all(a != b for a, b in zip(firsts, firsts[1:], strict=False))


def test_sensitivity_all_skips_nodes_with_no_siblings() -> None:
    p = ps.add_criterion(
        tiny_project(),
        "Extra",
        crit_id="extra",
        scale=tiny_project().criteria[0].scale,
        value_function=tiny_project().criteria[0].value_function,
    )
    ids = {r.node_id for r in sensitivity_all(_complete(p))}
    assert ids == {"cost", "quality", "extra"}
    single = ps.remove_criterion(tiny_project(), "quality")
    assert sensitivity_all(single) == []


def _complete(p: Project) -> Project:
    for alt, cost in (("a", 20.0), ("b", 60.0)):
        p = ps.set_performance(p, alt, "extra", cost)
    return ps.set_judgement(p, "extra", 25.0)


def test_error_cases() -> None:
    p = tiny_project()
    with pytest.raises(SensitivityError, match="unknown criterion"):
        weight_sensitivity(p, None, "ghost")
    with pytest.raises(SensitivityError, match="at least 2"):
        weight_sensitivity(p, None, "cost", steps=1)
    only = ps.remove_criterion(p, "quality")
    with pytest.raises(SensitivityError, match="no siblings"):
        weight_sensitivity(only, None, "cost")
    degenerate = ps.set_judgement(ps.set_judgement(p, "quality", 0.0), "cost", 10.0)
    with pytest.raises(SensitivityError, match="local weight 1"):
        weight_sensitivity(degenerate, None, "cost")


def test_zero_weight_node_can_still_be_varied() -> None:
    p = ps.set_judgement(tiny_project(), "quality", 0.0)
    r = weight_sensitivity(p, None, "quality")
    assert r.base_weight == 0.0
    assert r.baseline_ranking == ["a", "b"]  # a wins on cost alone
    # V_a(t) = 0.8(1-t) + 0.6t, V_b(t) = 0.4(1-t) + 0.9t  ->  equal at t = 4/7
    assert r.first_winner_change_up is not None
    assert r.first_winner_change_up.weight == pytest.approx(4 / 7, abs=1e-15)
    assert r.first_winner_change_up.to_winner == "b"
    assert r.first_winner_change_down is None


def test_compare_scenarios_reports_changes_against_baseline() -> None:
    from mcda_studio.domain.criteria import Direction, LinearValueFunction

    p = ps.add_scenario(
        tiny_project(),
        Scenario(
            id="flip",
            name="Flip cost preference",
            value_function_overrides={"cost": LinearValueFunction(direction=Direction.INCREASING)},
        ),
    )
    cmp = compare_scenarios(p)
    assert cmp.baseline.ranking == ["a", "b"]
    (s,) = cmp.scenarios
    assert (
        s.ranking == ["b", "a"]
        and s.ranking_differs_from_baseline
        and s.winner_differs_from_baseline
    )
    assert s.rank_by_alternative == {"a": 2, "b": 1}
    with pytest.raises(SensitivityError, match="unknown scenario"):
        compare_scenarios(p, ["nope"])


def test_baseline_exactly_on_a_crossover_is_reported_as_a_tie() -> None:
    """Cost rated 3 vs Quality 4 puts the local Cost weight at 3/7, exactly the flip point of the
    hand-checked 2x2 case: A and B are tied at baseline, share rank 1 and the result says so."""
    p = ps.set_judgement(ps.set_judgement(tiny_project(), "cost", 3.0), "quality", 4.0)
    ranking = svc.evaluate_project(p).ranking
    assert [r.rank for r in ranking] == [1, 1]
    res = svc.sensitivity(p, "cost")
    assert res.base_weight == pytest.approx(3 / 7, abs=1e-15)
    assert [d.code for d in res.diagnostics] == ["BASELINE_ON_CROSSOVER"]
    assert res.ranking_stable_range == (res.base_weight, res.base_weight)
    assert [c.weight for c in res.crossovers] == [pytest.approx(3 / 7, abs=1e-12)]


@pytest.mark.parametrize("ratings", [[453.0, 0.015625], [1e6, 1.0], [1.0, 1e-9, 1e-9]])
def test_redistribution_keeps_weights_summing_to_one_when_a_weight_is_close_to_one(
    ratings: list[float],
) -> None:
    """Regression (found by a Hypothesis counter-example): with local weight wk ~ 0.99997,
    computing ``1 - wk`` by subtraction lost ~4 digits and the weights summed to 1 + 1.1e-12.
    The rest of the sibling group must be summed, not obtained by cancellation."""
    p = flat_project([[0.0] * len(ratings), [0.0] * len(ratings)], ratings)
    prep = prepare_mavt(p, p.analysis)
    for t in (0.0, 1e-6, 0.25, 0.5, 0.999999, 1.0):
        assert _global_with(prep, "c0", t).sum() == pytest.approx(1.0, abs=1e-14)
