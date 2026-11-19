"""Property-based tests (Hypothesis): invariants that must hold for *all* valid inputs."""

import math
import random
from bisect import bisect_right
from fractions import Fraction

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from mcda_studio.domain.criteria import CriterionNode, CriterionTree
from mcda_studio.methods.mavt.aggregation import evaluate_mavt, prepare_mavt
from mcda_studio.methods.mavt.sensitivity import _global_with, weight_sensitivity
from mcda_studio.methods.mavt.value_functions import linear, piecewise_linear
from mcda_studio.methods.mavt.weighting import compute_weights
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text

from builders import flat_project

SLOW = settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
unit = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
rating = st.floats(min_value=0.01, max_value=1000.0, allow_nan=False)


# ---- value functions ---------------------------------------------------------------------
def exact_interp(x: float, xs: list[float], vs: list[float]) -> float:
    """Independent oracle: piecewise interpolation in exact rational arithmetic.

    np.interp is not used because it overflows to inf on a subnormal span (1 / 2.2e-313).
    """
    if x <= xs[0]:
        return vs[0]
    if x >= xs[-1]:
        return vs[-1]
    i = bisect_right(xs, x) - 1
    x0, x1, v0, v1 = (Fraction(t) for t in (xs[i], xs[i + 1], vs[i], vs[i + 1]))
    return float(v0 + (v1 - v0) * (Fraction(x) - x0) / (x1 - x0))


@given(lo=st.floats(-1e6, 1e6), width=st.floats(1e-3, 1e6), frac=unit)
def test_linear_is_in_unit_interval_and_monotone(lo: float, width: float, frac: float) -> None:
    hi = lo + width
    x = lo + frac * width
    inc, dec = linear(x, lo, hi), linear(x, lo, hi, increasing=False)
    assert 0.0 <= inc <= 1.0 and 0.0 <= dec <= 1.0
    assert inc + dec == pytest.approx(1.0, abs=1e-9)
    assert linear(lo, lo, hi) == 0.0 and linear(hi, lo, hi) == 1.0


@given(st.data())
def test_piecewise_increasing_is_monotone_and_interpolates_control_points(
    data: st.DataObject,
) -> None:
    n = data.draw(st.integers(2, 7))
    xs = sorted(data.draw(st.lists(st.floats(-1e3, 1e3), min_size=n, max_size=n, unique=True)))
    inner = sorted(data.draw(st.lists(unit, min_size=n - 2, max_size=n - 2)))
    vs = [0.0, *inner, 1.0]
    for x, v in zip(xs, vs, strict=True):
        assert piecewise_linear(x, xs, vs) == pytest.approx(v, abs=1e-9)
    probes = sorted(data.draw(st.lists(unit, min_size=2, max_size=8)))
    ys = [piecewise_linear(xs[0] + p * (xs[-1] - xs[0]), xs, vs) for p in probes]
    assert all(b >= a - 1e-9 for a, b in zip(ys, ys[1:], strict=False))
    assert all(0.0 <= y <= 1.0 for y in ys)
    for p, y in zip(probes, ys, strict=True):
        x = xs[0] + p * (xs[-1] - xs[0])
        assert y == pytest.approx(exact_interp(x, xs, vs), abs=1e-9)


def test_piecewise_interpolates_across_a_subnormal_span() -> None:
    # Regression: Hypothesis found this span; the engine is right and np.interp returns inf.
    xs, vs = [0.0, 2.2250738585e-313], [0.0, 1.0]
    x = 0.5 * xs[1]
    assert piecewise_linear(x, xs, vs) == exact_interp(x, xs, vs) == 0.5


# ---- weighting on random trees ------------------------------------------------------------
@st.composite
def random_tree(draw: st.DrawFn) -> tuple[list[CriterionNode], dict[str, float]]:
    n = draw(st.integers(1, 25))
    nodes: list[CriterionNode] = []
    ratings: dict[str, float] = {}
    for i in range(n):
        parent = None if i == 0 else draw(st.one_of(st.none(), st.integers(0, i - 1)))
        nodes.append(
            CriterionNode(
                id=f"n{i}",
                name=f"n{i}",
                parent_id=None if parent is None else f"n{parent}",
                order=draw(st.integers(0, 3)),
            )
        )
        ratings[f"n{i}"] = draw(rating)
    return nodes, ratings


@given(random_tree())
def test_weights_are_normalised_products_on_any_tree(
    case: tuple[list[CriterionNode], dict[str, float]],
) -> None:
    nodes, ratings = case
    tree = CriterionTree(nodes)
    ws = compute_weights(tree, ratings)
    parents = {n.id: n.parent_id for n in nodes}
    # every sibling group sums to one
    groups: dict[str | None, list[str]] = {}
    for n in nodes:
        groups.setdefault(n.parent_id, []).append(n.id)
    for members in groups.values():
        assert math.fsum(ws.local[m] for m in members) == pytest.approx(1.0, abs=1e-12)
    # global weight = product along the path, computed independently here
    for leaf, w in ws.global_.items():
        prod, cur = 1.0, leaf
        while cur is not None:
            prod *= ws.local[cur]
            cur = parents[cur]
        assert w == pytest.approx(prod, rel=1e-12)
    assert math.fsum(ws.global_.values()) == pytest.approx(1.0, abs=1e-12)
    assert all(w > 0 for w in ws.global_.values())


@given(random_tree(), st.floats(0.01, 100.0), st.randoms(use_true_random=False))
def test_weights_invariant_to_rating_scale_and_list_order(
    case: tuple[list[CriterionNode], dict[str, float]], factor: float, rnd: random.Random
) -> None:
    nodes, ratings = case
    for parent in {n.parent_id for n in nodes}:  # distinct sibling orders: list order is moot
        for i, n in enumerate([m for m in nodes if m.parent_id == parent]):
            n.order = i
    base = compute_weights(CriterionTree(nodes), ratings).global_
    scaled = compute_weights(CriterionTree(nodes), {k: v * factor for k, v in ratings.items()})
    shuffled = list(nodes)
    rnd.shuffle(shuffled)
    again = compute_weights(CriterionTree(shuffled), ratings).global_
    for leaf, w in base.items():
        assert again[leaf] == pytest.approx(w, rel=1e-12)
        assert scaled.global_[leaf] == pytest.approx(w, rel=1e-9)


# ---- whole-model properties ----------------------------------------------------------------
@st.composite
def flat_case(draw: st.DrawFn) -> tuple[list[list[float]], list[float]]:
    n_alt, n_crit = draw(st.integers(2, 5)), draw(st.integers(2, 4))
    values = [[draw(unit) for _ in range(n_crit)] for _ in range(n_alt)]
    return values, [draw(rating) for _ in range(n_crit)]


@SLOW
@given(flat_case())
def test_overall_value_is_a_convex_combination_and_ranking_is_sorted(
    case: tuple[list[list[float]], list[float]],
) -> None:
    values, ratings = case
    r = evaluate_mavt(flat_project(values, ratings))
    for alt in r.alternatives:
        i = int(alt.alternative_id[1:])
        assert min(values[i]) - 1e-12 <= alt.overall_value <= max(values[i]) + 1e-12
        w = [ratings[j] / sum(ratings) for j in range(len(ratings))]
        assert alt.overall_value == pytest.approx(
            sum(wj * v for wj, v in zip(w, values[i], strict=True))
        )
    vs = [a.value for a in r.ranking]
    assert vs == sorted(vs, reverse=True)
    assert [a.rank for a in r.ranking] == sorted(a.rank for a in r.ranking)


@SLOW
@given(flat_case(), st.randoms(use_true_random=False))
def test_alternative_order_does_not_change_scores(
    case: tuple[list[list[float]], list[float]], rnd: random.Random
) -> None:
    values, ratings = case
    base = {
        a.alternative_id: a.overall_value
        for a in evaluate_mavt(flat_project(values, ratings)).alternatives
    }
    order = list(range(len(values)))
    rnd.shuffle(order)
    permuted = flat_project([values[i] for i in order], ratings)
    # relabel: permuted alternative k carries the data of original alternative order[k]
    got = {
        f"a{order[int(a.alternative_id[1:])]}": a.overall_value
        for a in evaluate_mavt(permuted).alternatives
    }
    for alt, v in base.items():
        assert got[alt] == pytest.approx(v, abs=1e-12)


@SLOW
@given(flat_case(), st.lists(unit, min_size=4, max_size=4))
def test_fixed_anchors_make_scores_independent_of_other_alternatives(
    case: tuple[list[list[float]], list[float]], extra: list[float]
) -> None:
    values, ratings = case
    before = {
        a.alternative_id: a.overall_value
        for a in evaluate_mavt(flat_project(values, ratings)).alternatives
    }
    bigger = flat_project(values + [(extra * 2)[: len(ratings)]], ratings)
    after = {a.alternative_id: a.overall_value for a in evaluate_mavt(bigger).alternatives}
    for alt, v in before.items():
        assert after[alt] == v


@SLOW
@given(flat_case())
def test_sensitivity_invariants(case: tuple[list[list[float]], list[float]]) -> None:
    values, ratings = case
    p = flat_project(values, ratings)
    res = weight_sensitivity(p, None, "c0", steps=21)
    base = evaluate_mavt(p)
    i = res.grid.index(res.base_weight)
    for a in base.ranking:  # the unchanged baseline is reproduced inside the sweep
        assert res.values[a.alternative_id][i] == pytest.approx(a.value, abs=1e-12)
    prep = prepare_mavt(p, p.analysis)
    for t in res.grid:
        assert _global_with(prep, "c0", t).sum() == pytest.approx(1.0, abs=1e-12)
    # every reported crossover is a genuine tie, and ranking is constant between crossovers
    for c in res.crossovers:
        w = _global_with(prep, "c0", c.weight)
        v = prep.partial @ w
        ia, ib = int(c.alternative_a[1:]), int(c.alternative_b[1:])
        assert v[ia] == pytest.approx(v[ib], abs=1e-9)
    # completeness: no pairwise order flip between neighbouring grid points is missed
    names = [a.alternative_id for a in base.alternatives]
    known = {frozenset((c.alternative_a, c.alternative_b)): [] for c in res.crossovers}
    for c in res.crossovers:
        known[frozenset((c.alternative_a, c.alternative_b))].append(c.weight)
    vecs = [prep.partial @ _global_with(prep, "c0", t) for t in res.grid]
    for g in range(len(res.grid) - 1):
        for x in range(len(names)):
            for y in range(x + 1, len(names)):
                ia, ib = int(names[x][1:]), int(names[y][1:])
                d1, d2 = vecs[g][ia] - vecs[g][ib], vecs[g + 1][ia] - vecs[g + 1][ib]
                if d1 > 1e-9 and d2 < -1e-9 or d1 < -1e-9 and d2 > 1e-9:
                    ws = known.get(frozenset((names[x], names[y])), [])
                    assert any(res.grid[g] - 1e-12 <= w <= res.grid[g + 1] + 1e-12 for w in ws)
    lo, hi = res.ranking_stable_range
    assert 0.0 <= lo <= res.base_weight <= hi <= 1.0


@SLOW
@given(flat_case())
def test_save_load_round_trip_reproduces_results(
    case: tuple[list[list[float]], list[float]],
) -> None:
    values, ratings = case
    p = flat_project(values, ratings)
    q = JsonProjectRepository().from_dict(__import__("json").loads(to_json_text(p)))
    assert q == p
    assert evaluate_mavt(q) == evaluate_mavt(p)


@SLOW
@given(st.integers(2, 6), st.integers(0, 5))
def test_removing_a_criterion_keeps_a_valid_normalised_model(n_crit: int, drop: int) -> None:
    values = [[0.1 * (j + 1) for j in range(n_crit)], [0.9 - 0.1 * j for j in range(n_crit)]]
    p = flat_project(values, [10.0 * (j + 1) for j in range(n_crit)])
    q = ps.remove_criterion(p, f"c{drop % n_crit}")
    assert sum(evaluate_mavt(q).global_weights.values()) == pytest.approx(1.0, abs=1e-12)
