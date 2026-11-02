import math

import pytest

from mcda_studio.domain.criteria import CriterionNode, CriterionTree
from mcda_studio.domain.errors import ModelStructureError, WeightError
from mcda_studio.methods.mavt.weighting import (
    compute_weights,
    global_weights,
    local_weights,
    path_shares,
)


def tree(*spec: tuple[str, str | None]) -> CriterionTree:
    return CriterionTree([CriterionNode(id=i, name=i, parent_id=p) for i, p in spec])


def test_parent_ratings_100_90_80_70_normalise() -> None:
    t = tree(("p1", None), ("p2", None), ("p3", None), ("p4", None))
    w = local_weights(t, {"p1": 100, "p2": 90, "p3": 80, "p4": 70})
    assert w == {
        k: pytest.approx(v / 340) for k, v in {"p1": 100, "p2": 90, "p3": 80, "p4": 70}.items()
    }
    assert math.fsum(w.values()) == pytest.approx(1.0, abs=1e-15)


def test_two_level_global_weights_are_products() -> None:
    t = tree(
        ("team", None),
        ("market", None),
        ("exp", "team"),
        ("size", "team"),
        ("tam", "market"),
        ("growth", "market"),
    )
    r = {"team": 100, "market": 50, "exp": 100, "size": 50, "tam": 100, "growth": 100}
    ws = compute_weights(t, r)
    assert ws.global_["exp"] == pytest.approx(2 / 3 * 2 / 3)
    assert ws.global_["size"] == pytest.approx(2 / 3 * 1 / 3)
    assert ws.global_["tam"] == pytest.approx(1 / 3 * 1 / 2)
    assert math.fsum(ws.global_.values()) == pytest.approx(1.0, abs=1e-15)


def test_arbitrarily_deep_tree() -> None:
    # chain of 12 levels with one extra leaf hanging off each level
    spec: list[tuple[str, str | None]] = [("n0", None), ("x0", None)]
    ratings = {"n0": 1.0, "x0": 1.0}
    for i in range(1, 12):
        spec += [(f"n{i}", f"n{i - 1}"), (f"x{i}", f"n{i - 1}")]
        ratings |= {f"n{i}": 1.0, f"x{i}": 1.0}
    ws = compute_weights(tree(*spec), ratings)
    # x_k sits below k halvings, then one more halving; the chain end n11 has no siblings below
    assert ws.global_["x0"] == pytest.approx(0.5)
    assert ws.global_["x5"] == pytest.approx(0.5**6)
    assert ws.global_["n11"] == pytest.approx(0.5**12)
    assert math.fsum(ws.global_.values()) == pytest.approx(1.0, abs=1e-14)


def test_only_child_needs_no_rating() -> None:
    t = tree(("a", None), ("a1", "a"), ("b", None), ("b1", "b"), ("b2", "b"))
    ws = compute_weights(t, {"a": 1, "b": 3, "b1": 1, "b2": 1})
    assert ws.local["a1"] == 1.0
    assert ws.global_["a1"] == pytest.approx(0.25)


def test_modifying_one_judgement_updates_only_the_affected_descendants() -> None:
    t = tree(("a", None), ("b", None), ("a1", "a"), ("a2", "a"), ("b1", "b"), ("b2", "b"))
    base = {"a": 100, "b": 100, "a1": 100, "a2": 100, "b1": 100, "b2": 100}
    before = compute_weights(t, base).global_
    after = compute_weights(t, {**base, "a1": 300}).global_
    assert after["b1"] == pytest.approx(before["b1"])  # other branch untouched
    assert after["b2"] == pytest.approx(before["b2"])
    assert after["a1"] > before["a1"] and after["a2"] < before["a2"]
    assert after["a1"] + after["a2"] == pytest.approx(
        before["a1"] + before["a2"]
    )  # parent share fixed


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf"), float("-inf")])
def test_negative_or_non_finite_ratings_rejected(bad: float) -> None:
    t = tree(("a", None), ("b", None))
    with pytest.raises(WeightError, match="finite"):
        local_weights(t, {"a": bad, "b": 1.0})


def test_all_zero_siblings_rejected() -> None:
    t = tree(("a", None), ("b", None))
    with pytest.raises(WeightError, match="zero"):
        local_weights(t, {"a": 0.0, "b": 0.0})


def test_zero_rating_for_one_sibling_is_allowed() -> None:
    t = tree(("a", None), ("b", None))
    assert local_weights(t, {"a": 0.0, "b": 5.0}) == {"a": 0.0, "b": 1.0}


def test_missing_and_unknown_judgements_rejected() -> None:
    t = tree(("a", None), ("b", None))
    with pytest.raises(WeightError, match="no swing rating"):
        local_weights(t, {"a": 1.0})
    with pytest.raises(WeightError, match="unknown criterion"):
        local_weights(t, {"a": 1.0, "b": 1.0, "ghost": 1.0})


def test_global_weights_cover_exactly_the_leaves() -> None:
    t = tree(("a", None), ("a1", "a"), ("b", None))
    g = global_weights(t, local_weights(t, {"a": 1, "b": 1}))
    assert set(g) == {"a1", "b"}


def test_path_shares_explain_a_global_weight_without_changing_it() -> None:
    """The GUI shows an objective's branch share; it must come from the engine, not the browser."""
    t = tree(("a", None), ("a1", "a"), ("a2", "a"), ("b", None))
    local = local_weights(t, {"a": 100, "b": 300, "a1": 65, "a2": 35})
    shares = path_shares(t, local)
    # An objective's share is its own local weight at the top level.
    assert shares["a"] == pytest.approx(0.25) and shares["b"] == pytest.approx(0.75)
    # A leaf's share is the product down its path, and equals its global weight exactly.
    assert shares["a1"] == pytest.approx(0.25 * 0.65) and shares["a2"] == pytest.approx(0.25 * 0.35)
    assert {k: shares[k] for k in global_weights(t, local)} == global_weights(t, local)
    # Objectives are not extra weight; only the leaves sum to one.
    assert math.fsum(global_weights(t, local).values()) == pytest.approx(1.0, abs=1e-15)
    assert set(shares) == {"a", "a1", "a2", "b"}


def test_path_shares_split_each_objective_among_its_own_children() -> None:
    """Deep trees: every group's shares sum to that group's own share, not to one."""
    t = tree(("r", None), ("m", "r"), ("m1", "m"), ("m2", "m"), ("n", "r"), ("s", None))
    local = local_weights(t, {"r": 80, "s": 20, "m": 30, "n": 70, "m1": 1, "m2": 3})
    shares = path_shares(t, local)
    assert shares["r"] == pytest.approx(0.8)
    assert shares["m"] + shares["n"] == pytest.approx(shares["r"])
    assert shares["m1"] + shares["m2"] == pytest.approx(shares["m"])
    assert shares["m1"] == pytest.approx(0.8 * 0.3 * 0.25)
    assert shares["s"] == pytest.approx(0.2) and local["s"] == pytest.approx(0.2)


def test_only_child_share_repeats_its_parent_share_without_a_rating() -> None:
    t = tree(("a", None), ("a1", "a"), ("b", None))
    shares = path_shares(t, local_weights(t, {"a": 1, "b": 1}))
    assert shares["a1"] == pytest.approx(shares["a"]) == pytest.approx(0.5)


class TestTreeStructure:
    def test_cycle_detected(self) -> None:
        with pytest.raises(ModelStructureError, match="cycle"):
            tree(("a", "b"), ("b", "a"))

    def test_unknown_parent(self) -> None:
        with pytest.raises(ModelStructureError, match="unknown parent"):
            tree(("a", "ghost"))

    def test_duplicate_id(self) -> None:
        with pytest.raises(ModelStructureError, match="duplicate"):
            tree(("a", None), ("a", None))

    def test_self_parent(self) -> None:
        with pytest.raises(ModelStructureError):
            tree(("a", "a"))
