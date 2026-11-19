from typing import Any

import pytest

from mcda_studio.domain.criteria import LinearValueFunction
from mcda_studio.domain.errors import ModelEditError, UnknownReferenceError
from mcda_studio.domain.preferences import Scenario
from mcda_studio.domain.project import Project
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.domain.validation import validate_project
from mcda_studio.methods.mavt.aggregation import evaluate_mavt
from mcda_studio.services import project_service as ps
from mcda_studio.services import templates

from builders import tiny_project


def snapshot(p: Project) -> dict[str, Any]:
    return p.model_dump(mode="json")


def test_editing_never_mutates_the_input() -> None:
    p = tiny_project()
    before = snapshot(p)
    for edit in (
        lambda q: ps.add_alternative(q, "C"),
        lambda q: ps.remove_alternative(q, "a"),
        lambda q: ps.rename_alternative(q, "a", "Renamed"),
        lambda q: ps.add_criterion(q, "New", parent_id=None),
        lambda q: ps.remove_criterion(q, "cost"),
        lambda q: ps.rename_criterion(q, "cost", "Price"),
        lambda q: ps.move_criterion(q, "quality", None, 0),
        lambda q: ps.set_performance(q, "a", "cost", 1.0),
        lambda q: ps.set_judgement(q, "cost", 5.0),
        lambda q: ps.set_scale(q, "cost", Scale(type=ScaleType.RATIO, lower=0, upper=1)),
        lambda q: ps.set_value_function(q, "cost", LinearValueFunction()),
        lambda q: ps.rename_project(q, "other"),
    ):
        edit(p)
        assert snapshot(p) == before


def test_duplicate_is_independent_and_has_a_new_id() -> None:
    p = tiny_project()
    d = ps.duplicate_project(p)
    assert d.id != p.id and d.title.endswith("(copy)")
    d2 = ps.set_performance(d, "a", "cost", 99.0)
    assert d2.performance_index()[("a", "cost")] == 99.0
    assert p.performance_index()[("a", "cost")] == 20.0  # original untouched
    assert [x.alternative_id for x in evaluate_mavt(d2).ranking] == ["b", "a"]
    assert evaluate_mavt(d).ranking == evaluate_mavt(p).ranking


def test_ids_are_stable_so_renaming_does_not_corrupt_measurements() -> None:
    p = ps.rename_criterion(ps.rename_alternative(tiny_project(), "a", "Alpha"), "cost", "Price")
    assert validate_project(p).ok
    r = evaluate_mavt(p)
    assert r.ranking[0].name == "Alpha"


def test_adding_alternatives_generates_unique_ids() -> None:
    p = ps.add_alternative(ps.add_alternative(tiny_project(), "Acme"), "Acme")
    ids = p.alternative_ids()
    assert len(set(ids)) == len(ids) == 4
    with pytest.raises(ModelEditError):
        ps.add_alternative(p, "x", alt_id="a")


def test_remove_alternative_removes_its_measurements() -> None:
    p = ps.remove_alternative(tiny_project(), "a")
    assert all(m.alternative_id != "a" for m in p.performances)
    with pytest.raises(UnknownReferenceError):
        ps.remove_alternative(p, "a")


def test_add_child_to_measured_leaf_requires_confirmation() -> None:
    p = tiny_project()
    with pytest.raises(ModelEditError, match="discard"):
        ps.add_criterion(p, "Sub", parent_id="cost")
    q = ps.add_criterion(p, "Sub", parent_id="cost", crit_id="sub", discard_leaf_data=True)
    cost = next(n for n in q.criteria if n.id == "cost")
    assert cost.scale is None and cost.value_function is None
    assert all(m.criterion_id != "cost" for m in q.performances)


def test_siblings_get_consecutive_orders_and_position_is_honoured() -> None:
    p = ps.add_criterion(tiny_project(), "Third", crit_id="third", position=0)
    assert [n.id for n in sorted(p.criteria, key=lambda n: n.order)] == ["third", "cost", "quality"]
    assert sorted(n.order for n in p.criteria) == [0, 1, 2]


def test_move_criterion_reparents_and_drops_stale_ratings() -> None:
    p = ps.add_criterion(tiny_project(), "Group", crit_id="group")
    p = ps.set_judgement(p, "group", 40.0)
    q = ps.move_criterion(p, "quality", "group", discard_leaf_data=False)
    assert next(n for n in q.criteria if n.id == "quality").parent_id == "group"
    assert "quality" not in q.weight_profiles[0].judgements  # relative to old siblings: dropped
    assert "cost" in q.weight_profiles[0].judgements


def test_move_into_own_subtree_is_refused() -> None:
    p = ps.add_criterion(
        tiny_project(), "Child", parent_id="cost", crit_id="child", discard_leaf_data=True
    )
    with pytest.raises(ModelEditError, match="own subtree"):
        ps.move_criterion(p, "cost", "child")
    with pytest.raises(ModelEditError):
        ps.move_criterion(p, "cost", "cost")


def test_reorder_among_siblings() -> None:
    p = ps.move_criterion(tiny_project(), "quality", None, 0)
    assert [n.id for n in sorted(p.criteria, key=lambda n: n.order)] == ["quality", "cost"]
    assert validate_project(p).ok  # ratings unchanged because the parent did not change


def test_remove_criterion_cleans_up_and_weights_renormalise() -> None:
    p = ps.add_criterion(
        tiny_project(),
        "Extra",
        crit_id="extra",
        scale=Scale(type=ScaleType.INTERVAL, lower=0, upper=1),
        value_function=LinearValueFunction(),
    )
    for alt in ("a", "b"):
        p = ps.set_performance(p, alt, "extra", 0.5)
    p = ps.set_judgement(p, "extra", 50.0)
    p = ps.add_scenario(
        p, Scenario(id="s", name="s", value_function_overrides={"extra": LinearValueFunction()})
    )
    q = ps.remove_criterion(p, "extra")
    assert all(m.criterion_id != "extra" for m in q.performances)
    assert "extra" not in q.weight_profiles[0].judgements
    assert q.scenarios[0].value_function_overrides == {}
    assert validate_project(q).ok
    assert evaluate_mavt(q).global_weights == {
        "cost": pytest.approx(2 / 3),
        "quality": pytest.approx(1 / 3),
    }


def test_remove_criterion_removes_the_whole_subtree() -> None:
    p = ps.add_criterion(tiny_project(), "Group", crit_id="group")
    p = ps.add_criterion(p, "Inner", parent_id="group", crit_id="inner")
    q = ps.remove_criterion(p, "group")
    assert {n.id for n in q.criteria} == {"cost", "quality"}


def test_only_leaves_can_be_measured_or_scaled() -> None:
    p = ps.add_criterion(tiny_project(), "Group", crit_id="group")
    p = ps.add_criterion(p, "Inner", parent_id="group", crit_id="inner")
    with pytest.raises(ModelEditError, match="only leaf"):
        ps.set_performance(p, "a", "group", 1.0)
    with pytest.raises(ModelEditError):
        ps.set_scale(p, "group", Scale(type=ScaleType.RATIO))
    with pytest.raises(UnknownReferenceError):
        ps.set_performance(p, "ghost", "inner", 1.0)


def test_a_model_of_any_depth_can_be_built_and_evaluated() -> None:
    p = ps.new_project("deep")
    p = ps.add_alternative(p, "X", alt_id="x")
    p = ps.add_alternative(p, "Y", alt_id="y")
    parent = None
    for i in range(8):
        p = ps.add_criterion(p, f"L{i}", parent_id=parent, crit_id=f"l{i}")
        p = ps.add_criterion(
            p,
            f"leaf{i}",
            parent_id=parent,
            crit_id=f"leaf{i}",
            scale=Scale(type=ScaleType.INTERVAL, lower=0, upper=1),
            value_function=LinearValueFunction(),
        )
        p = ps.set_judgement(p, f"l{i}", 1.0)
        p = ps.set_judgement(p, f"leaf{i}", 1.0)
        parent = f"l{i}"
    # last chain node l7 has no children yet: make it a measured leaf
    p = ps.set_scale(p, "l7", Scale(type=ScaleType.INTERVAL, lower=0, upper=1))
    p = ps.set_value_function(p, "l7", LinearValueFunction())
    for alt, v in (("x", 0.2), ("y", 0.9)):
        for i in range(8):
            p = ps.set_performance(p, alt, f"leaf{i}", v)
        p = ps.set_performance(p, alt, "l7", v)
    r = evaluate_mavt(p)
    assert sum(r.global_weights.values()) == pytest.approx(1.0, abs=1e-14)
    assert r.ranking[0].alternative_id == "y"


def test_templates_give_structure_without_judgements() -> None:
    assert set(templates.TEMPLATES) == {"blank", "supplier-selection"}
    t = templates.from_template("supplier-selection", "My suppliers")
    assert len(t.criteria) == 7  # 3 parents + 4 leaves
    assert not t.alternatives and not t.performances
    assert t.weight_profiles[0].judgements == {}
    codes = {i.code for i in validate_project(t).errors}
    assert "NO_ALTERNATIVES" in codes and "MISSING_JUDGEMENT" in codes
    other = templates.from_template("supplier-selection", "Other")
    assert other.id != t.id
    ps.add_alternative(t, "New")  # editing one project cannot change another from the template
    assert not other.alternatives
    with pytest.raises(UnknownReferenceError):
        templates.from_template("nope", "x")


# ---- Stage 2A additions: the GUI's clearing and detail-editing operations ----------------------
class TestClearingAndDetails:
    def test_update_project_details_changes_only_what_it_is_given(self) -> None:
        p = tiny_project()
        out = ps.update_project_details(p, description="why", decision_maker="Alex")
        assert (out.title, out.description, out.decision_maker) == (p.title, "why", "Alex")
        out2 = ps.update_project_details(out, title="New title")
        assert (out2.title, out2.description, out2.decision_maker) == ("New title", "why", "Alex")
        assert ps.update_project_details(out2).model_dump() == out2.model_dump()
        assert out2.id == p.id  # identity never changes

    def test_update_criterion_keeps_the_id_and_everything_else(self) -> None:
        p = tiny_project()
        out = ps.update_criterion(p, "cost", name="Price", description="all-in")
        node = out.tree().node("cost")
        assert (node.id, node.name, node.description) == ("cost", "Price", "all-in")
        assert node.scale == p.tree().node("cost").scale
        assert out.performances == p.performances
        assert (
            ps.update_criterion(out, "cost", name="Price").tree().node("cost").description
            == "all-in"
        )
        with pytest.raises(UnknownReferenceError):
            ps.update_criterion(p, "ghost", name="x")

    def test_clear_performance_removes_exactly_one_cell_and_is_idempotent(self) -> None:
        p = tiny_project()
        out = ps.clear_performance(p, "a", "cost")
        cells = {(x.alternative_id, x.criterion_id) for x in out.performances}
        assert cells == {("a", "quality"), ("b", "cost"), ("b", "quality")}
        assert ps.clear_performance(out, "a", "cost").performances == out.performances
        with pytest.raises(UnknownReferenceError):
            ps.clear_performance(p, "ghost", "cost")
        with pytest.raises(UnknownReferenceError):
            ps.clear_performance(p, "a", "ghost")

    def test_clearing_a_cell_makes_the_model_incomplete_not_invalid_structure(self) -> None:
        out = ps.clear_performance(tiny_project(), "a", "cost")
        codes = {i.code for i in validate_project(out).issues}
        assert "MISSING_MEASUREMENT" in codes

    def test_clear_criterion_performances_removes_a_whole_column_only(self) -> None:
        out = ps.clear_criterion_performances(tiny_project(), "cost")
        assert {x.criterion_id for x in out.performances} == {"quality"}
        assert len(out.performances) == 2
        with pytest.raises(UnknownReferenceError):
            ps.clear_criterion_performances(tiny_project(), "ghost")

    def test_clear_judgement_removes_the_rating_and_is_idempotent(self) -> None:
        p = tiny_project()
        out = ps.clear_judgement(p, "cost")
        assert "cost" not in out.weight_profiles[0].judgements
        assert out.weight_profiles[0].judgements["quality"] == 50.0
        assert (
            ps.clear_judgement(out, "cost").weight_profiles[0].judgements
            == out.weight_profiles[0].judgements
        )
        with pytest.raises(UnknownReferenceError):
            ps.clear_judgement(p, "cost", profile_id="no-such-profile")
        with pytest.raises(UnknownReferenceError):
            ps.clear_judgement(p, "ghost")

    def test_none_of_the_clearing_operations_mutates_its_input(self) -> None:
        p = tiny_project()
        before = snapshot(p)
        ps.update_project_details(p, title="x")
        ps.update_criterion(p, "cost", name="x")
        ps.clear_performance(p, "a", "cost")
        ps.clear_criterion_performances(p, "cost")
        ps.clear_judgement(p, "cost")
        assert snapshot(p) == before
