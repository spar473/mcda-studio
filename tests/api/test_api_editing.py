"""``POST /api/edit``: every operation goes through the services layer, is atomic, and never
stores anything. Invalid tree operations are refused with a stable code and a clear message."""

from typing import Any

import pytest
from conftest import SUPPLIER_FILE, dump, errors, repo
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from mcda_studio.domain.criteria import ControlPoint, Direction, LinearValueFunction
from mcda_studio.domain.criteria import PiecewiseLinearValueFunction as Piecewise
from mcda_studio.domain.outranking import PrometheeModel
from mcda_studio.domain.pairwise import AhpModel
from mcda_studio.domain.project import Project
from mcda_studio.domain.requirements import AnyRequirement, Requirement
from mcda_studio.domain.scales import AnchorMode, Scale, ScaleType
from mcda_studio.domain.sorting import SortingModel
from mcda_studio.domain.uncertainty import SmaaModel
from mcda_studio.services import project_service as ps


@pytest.fixture
def base() -> Project:
    return repo.load(SUPPLIER_FILE)


def edit(client: TestClient, project: Project | dict[str, Any], *ops: dict[str, Any]) -> Any:
    body = project if isinstance(project, dict) else dump(project)
    return client.post("/api/edit", json={"project": body, "operations": list(ops)})


def edited(client: TestClient, project: Project, *ops: dict[str, Any]) -> Project:
    resp = edit(client, project, *ops)
    assert resp.status_code == 200, resp.text
    return repo.from_dict(resp.json()["project"])


# ---- every operation equals the direct service call -----------------------------------------
NEW_SCALE = Scale(type=ScaleType.RATIO, unit="days", lower=0.0, upper=30.0)
NEW_VF = LinearValueFunction(direction=Direction.INCREASING)  # unit_price is decreasing
CASES: list[tuple[str, dict[str, Any], Any]] = [
    (
        "update_project",
        {"op": "update_project", "title": "T2", "description": "d", "decision_maker": "me"},
        lambda p: ps.update_project_details(p, "T2", "d", "me"),
    ),
    (
        "add_alternative",
        {"op": "add_alternative", "name": "Fresh Co"},
        lambda p: ps.add_alternative(p, "Fresh Co"),
    ),
    (
        "rename_alternative",
        {"op": "rename_alternative", "alternative_id": "apex", "name": "Apex Ltd"},
        lambda p: ps.rename_alternative(p, "apex", "Apex Ltd"),
    ),
    (
        "remove_alternative",
        {"op": "remove_alternative", "alternative_id": "delta"},
        lambda p: ps.remove_alternative(p, "delta"),
    ),
    (
        "add_criterion",
        {"op": "add_criterion", "name": "Support", "parent_id": "risk", "position": 0},
        lambda p: ps.add_criterion(p, "Support", parent_id="risk", position=0),
    ),
    (
        "update_criterion",
        {"op": "update_criterion", "criterion_id": "cost", "name": "Money", "description": "all"},
        lambda p: ps.update_criterion(p, "cost", "Money", "all"),
    ),
    (
        "move_criterion",
        {"op": "move_criterion", "criterion_id": "lead_time", "new_parent_id": "cost"},
        lambda p: ps.move_criterion(p, "lead_time", "cost"),
    ),
    (
        "remove_criterion",
        {"op": "remove_criterion", "criterion_id": "quality"},
        lambda p: ps.remove_criterion(p, "quality"),
    ),
    (
        "set_scale",
        {
            "op": "set_scale",
            "criterion_id": "lead_time",
            "scale": NEW_SCALE.model_dump(mode="json"),
        },
        lambda p: ps.set_scale(p, "lead_time", NEW_SCALE),
    ),
    (
        "set_value_function",
        {
            "op": "set_value_function",
            "criterion_id": "unit_price",
            "value_function": NEW_VF.model_dump(mode="json"),
        },
        lambda p: ps.set_value_function(p, "unit_price", NEW_VF),
    ),
    (
        "set_performance",
        {
            "op": "set_performance",
            "alternative_id": "apex",
            "criterion_id": "unit_price",
            "value": 7,
        },
        lambda p: ps.set_performance(p, "apex", "unit_price", 7.0),
    ),
    (
        "clear_performance",
        {"op": "clear_performance", "alternative_id": "apex", "criterion_id": "unit_price"},
        lambda p: ps.clear_performance(p, "apex", "unit_price"),
    ),
    (
        "clear_criterion_performances",
        {"op": "clear_criterion_performances", "criterion_id": "unit_price"},
        lambda p: ps.clear_criterion_performances(p, "unit_price"),
    ),
    (
        "set_judgement",
        {"op": "set_judgement", "node_id": "cost", "rating": 55.5},
        lambda p: ps.set_judgement(p, "cost", 55.5),
    ),
    (
        "clear_judgement",
        {"op": "clear_judgement", "node_id": "cost"},
        lambda p: ps.clear_judgement(p, "cost"),
    ),
]


CASES.extend(
    [
        (
            "create_weight_profile",
            {"op": "create_weight_profile", "name": "New", "profile_id": "new"},
            lambda p: ps.create_weight_profile(p, "New", "new"),
        ),
        (
            "duplicate_weight_profile",
            {
                "op": "duplicate_weight_profile",
                "profile_id": "default",
                "name": "Copy",
                "new_profile_id": "copy",
            },
            lambda p: ps.duplicate_weight_profile(p, "default", "Copy", "copy"),
        ),
        (
            "rename_weight_profile",
            {"op": "rename_weight_profile", "profile_id": "default", "name": "Renamed"},
            lambda p: ps.rename_weight_profile(p, "default", "Renamed"),
        ),
        (
            "remove_weight_profile",
            {
                "op": "remove_weight_profile",
                "profile_id": "cost_focus",
                "replacement_profile_id": "default",
            },
            lambda p: ps.remove_weight_profile(p, "cost_focus", "default"),
        ),
        (
            "set_default_weight_profile",
            {"op": "set_default_weight_profile", "profile_id": "cost_focus"},
            lambda p: ps.set_default_weight_profile(p, "cost_focus"),
        ),
    ]
)


CASES.extend(
    [
        (
            "create_scenario",
            {"op": "create_scenario", "name": "New", "scenario_id": "new"},
            lambda p: ps.create_scenario(p, "New", "new"),
        ),
        (
            "duplicate_scenario",
            {
                "op": "duplicate_scenario",
                "scenario_id": "linear_defects",
                "name": "Copy",
                "new_scenario_id": "copy",
            },
            lambda p: ps.duplicate_scenario(p, "linear_defects", "Copy", "copy"),
        ),
        (
            "rename_scenario",
            {"op": "rename_scenario", "scenario_id": "linear_defects", "name": "Renamed"},
            lambda p: ps.rename_scenario(p, "linear_defects", "Renamed"),
        ),
        (
            "remove_scenario",
            {"op": "remove_scenario", "scenario_id": "linear_defects"},
            lambda p: ps.remove_scenario(p, "linear_defects"),
        ),
        (
            "set_scenario_profile",
            {
                "op": "set_scenario_profile",
                "scenario_id": "linear_defects",
                "profile_id": "cost_focus",
            },
            lambda p: ps.set_scenario_profile(p, "linear_defects", "cost_focus"),
        ),
        (
            "set_scenario_override",
            {
                "op": "set_scenario_override",
                "scenario_id": "linear_defects",
                "criterion_id": "unit_price",
                "value_function": {"kind": "linear", "direction": "increasing"},
            },
            lambda p: ps.set_scenario_override(
                p, "linear_defects", "unit_price", LinearValueFunction()
            ),
        ),
        (
            "clear_scenario_override",
            {
                "op": "clear_scenario_override",
                "scenario_id": "linear_defects",
                "criterion_id": "defect_rate",
            },
            lambda p: ps.clear_scenario_override(p, "linear_defects", "defect_rate"),
        ),
        (
            "set_default_scenario",
            {"op": "set_default_scenario", "scenario_id": "linear_defects"},
            lambda p: ps.set_default_scenario(p, "linear_defects"),
        ),
    ]
)

_CLASSES = {
    "classes": [
        {"id": "go", "name": "Go", "description": "", "lower_boundary": 0.6},
        {"id": "stop", "name": "Stop", "description": "", "lower_boundary": None},
    ],
    "audit": None,
}
_SMAA = {
    "dependence": "independent",
    "cells": [
        {
            "alternative_id": "apex",
            "criterion_id": "unit_price",
            "distribution": {"kind": "uniform", "lower": 38.0, "upper": 46.0},
        }
    ],
    "groups": [{"parent_id": None, "kind": "unknown", "intervals": {}}],
    "shared_draws": [],
}
_PROMETHEE = {
    "criteria": [
        {
            "criterion_id": "unit_price",
            "direction": "minimise",
            "weight": 3.0,
            "function": {"kind": "linear", "q": 2.0, "p": 10.0},
        }
    ]
}
_AHP = {
    "criteria": [
        {
            "parent_id": None,
            "judgements": [{"row": "cost", "column": "performance", "value": 3.0}],
        }
    ],
    "alternatives": [],
}
_REQUIREMENTS: list[dict[str, Any]] = [
    {"kind": "bound", "id": "price_cap", "name": "Within budget", "criterion_id": "unit_price",
     "unit": "NZD", "maximum": 45},
]  # fmt: skip
_REQUIREMENT_ADAPTER: TypeAdapter[AnyRequirement] = TypeAdapter(Requirement)
CASES.extend(
    [
        (
            "set_sorting_model",
            {"op": "set_sorting_model", "sorting": _CLASSES},
            lambda p: ps.set_sorting_model(p, SortingModel.model_validate(_CLASSES)),
        ),
        (
            "clear_sorting_model",
            {"op": "clear_sorting_model"},
            lambda p: ps.clear_sorting_model(p),
        ),
        (
            "set_smaa_model",
            {"op": "set_smaa_model", "smaa": _SMAA},
            lambda p: ps.set_smaa_model(p, SmaaModel.model_validate(_SMAA)),
        ),
        (
            "clear_smaa_model",
            {"op": "clear_smaa_model"},
            lambda p: ps.clear_smaa_model(p),
        ),
        (
            "set_promethee_model",
            {"op": "set_promethee_model", "promethee": _PROMETHEE},
            lambda p: ps.set_promethee_model(p, PrometheeModel.model_validate(_PROMETHEE)),
        ),
        (
            "clear_promethee_model",
            {"op": "clear_promethee_model"},
            lambda p: ps.clear_promethee_model(p),
        ),
        (
            "set_ahp_model",
            {"op": "set_ahp_model", "ahp": _AHP},
            lambda p: ps.set_ahp_model(p, AhpModel.model_validate(_AHP)),
        ),
        (
            "clear_ahp_model",
            {"op": "clear_ahp_model"},
            lambda p: ps.clear_ahp_model(p),
        ),
        (
            "set_requirements",
            {"op": "set_requirements", "requirements": _REQUIREMENTS},
            lambda p: ps.set_requirements(
                p, [_REQUIREMENT_ADAPTER.validate_python(r) for r in _REQUIREMENTS]
            ),
        ),
        (
            "clear_requirements",
            {"op": "clear_requirements"},
            lambda p: ps.clear_requirements(p),
        ),
        (
            "set_analysis_method",
            {"op": "set_analysis_method", "method": "mavt_sorting"},
            lambda p: ps.set_analysis_method(p, "mavt_sorting"),
        ),
    ]
)


@pytest.mark.parametrize(("name", "op", "direct"), CASES, ids=[c[0] for c in CASES])
def test_each_operation_gives_exactly_the_services_result(
    client: TestClient, base: Project, name: str, op: dict[str, Any], direct: Any
) -> None:
    if name == "clear_sorting_model":  # needs a section to clear
        base = ps.set_sorting_model(base, SortingModel.model_validate(_CLASSES))
    if name == "clear_smaa_model":
        base = ps.set_smaa_model(base, SmaaModel.model_validate(_SMAA))
    if name == "clear_promethee_model":
        base = ps.set_promethee_model(base, PrometheeModel.model_validate(_PROMETHEE))
    if name == "clear_ahp_model":
        base = ps.set_ahp_model(base, AhpModel.model_validate(_AHP))
    if name == "clear_requirements":
        base = ps.set_requirements(
            base, [_REQUIREMENT_ADAPTER.validate_python(r) for r in _REQUIREMENTS]
        )
    via_api = edited(client, base, op)
    assert dump(via_api) == dump(direct(base)), name
    assert dump(via_api) != dump(base), f"{name} should change something"


def test_every_operation_class_has_a_case() -> None:
    from typing import get_args

    from mcda_studio.api.operations import Operation

    ops_in_union = {t.model_fields["op"].default for t in get_args(get_args(Operation)[0])}
    assert ops_in_union == {c[1]["op"] for c in CASES}


def test_operations_apply_in_order_and_the_response_carries_fresh_validation(
    client: TestClient,
) -> None:
    blank = ps.new_project("Fresh")
    resp = edit(
        client,
        blank,
        {"op": "add_alternative", "name": "Option A", "alternative_id": "a"},
        {"op": "add_alternative", "name": "Option B", "alternative_id": "b"},
        {"op": "add_criterion", "name": "Cost", "criterion_id": "cost"},
        {
            "op": "set_scale",
            "criterion_id": "cost",
            "scale": {"type": "ratio", "unit": "NZD", "lower": 0, "upper": 100},
        },
        {
            "op": "set_value_function",
            "criterion_id": "cost",
            "value_function": {"kind": "linear", "direction": "decreasing"},
        },
        {"op": "set_performance", "alternative_id": "a", "criterion_id": "cost", "value": 20},
        {"op": "set_performance", "alternative_id": "b", "criterion_id": "cost", "value": 60},
    )
    assert resp.status_code == 200, resp.text
    doc = resp.json()
    assert doc["validation"]["issues"] == []  # a complete, valid two-alternative model
    assert doc["fingerprint"] == repo.from_dict(doc["project"]).fingerprint()
    assert [a["id"] for a in doc["project"]["alternatives"]] == ["a", "b"]


def test_the_request_project_is_never_stored_or_changed(client: TestClient, store_dir: Any) -> None:
    before = dump(ps.new_project("x"))
    edit(client, before, {"op": "add_alternative", "name": "A"})
    assert not list(store_dir.glob("*.json"))
    assert client.get("/api/projects").json()["projects"] == []


# ---- all-or-nothing ---------------------------------------------------------------------------
def test_a_refused_operation_returns_no_partial_result_and_names_its_index(
    client: TestClient, base: Project
) -> None:
    resp = edit(
        client,
        base,
        {"op": "add_alternative", "name": "Fine"},
        {"op": "remove_alternative", "alternative_id": "no_such_alternative"},
        {"op": "add_alternative", "name": "Never reached"},
    )
    assert resp.status_code == 422
    err = errors(resp)
    assert err["code"] == "UNKNOWN_REFERENCE"
    assert err["details"] == [{"path": "operations[1]", "message": err["details"][0]["message"]}]
    assert "project" not in resp.json()


# ---- invalid tree operations ------------------------------------------------------------------
def test_adding_a_child_to_a_measured_leaf_needs_explicit_confirmation(
    client: TestClient, base: Project
) -> None:
    op = {"op": "add_criterion", "name": "Sub", "parent_id": "unit_price"}
    resp = edit(client, base, op)
    assert resp.status_code == 409
    err = errors(resp)
    assert err["code"] == "EDIT_REFUSED"
    assert "discard" in err["message"].lower()
    ok = edited(client, base, {**op, "discard_leaf_data": True})
    parent = next(n for n in ok.criteria if n.id == "unit_price")
    assert parent.scale is None and parent.value_function is None
    assert not [p for p in ok.performances if p.criterion_id == "unit_price"]


@pytest.mark.parametrize("new_parent", ["cost", "unit_price", "logistics_cost"])
def test_a_criterion_cannot_move_into_itself_or_its_own_subtree(
    client: TestClient, base: Project, new_parent: str
) -> None:
    resp = edit(
        client, base, {"op": "move_criterion", "criterion_id": "cost", "new_parent_id": new_parent}
    )
    assert resp.status_code == 409, resp.text
    err = errors(resp)
    assert err["code"] == "EDIT_REFUSED"
    assert "itself or its own subtree" in err["message"]


def test_moving_a_child_under_its_own_parent_is_a_legal_reorder(
    client: TestClient, base: Project
) -> None:
    out = edited(
        client,
        base,
        {
            "op": "move_criterion",
            "criterion_id": "logistics_cost",
            "new_parent_id": "cost",
            "position": 0,
        },
    )
    assert out.tree().child_ids("cost") == ["logistics_cost", "unit_price"]


def test_moving_to_an_unknown_parent_is_an_unknown_reference(
    client: TestClient, base: Project
) -> None:
    resp = edit(
        client, base, {"op": "move_criterion", "criterion_id": "cost", "new_parent_id": "ghost"}
    )
    assert resp.status_code == 422
    assert errors(resp)["code"] == "UNKNOWN_REFERENCE"


def test_duplicate_criterion_and_alternative_ids_are_refused(
    client: TestClient, base: Project
) -> None:
    dup_c = edit(client, base, {"op": "add_criterion", "name": "x", "criterion_id": "cost"})
    assert dup_c.status_code == 409 and errors(dup_c)["code"] == "EDIT_REFUSED"
    dup_a = edit(client, base, {"op": "add_alternative", "name": "x", "alternative_id": "apex"})
    assert dup_a.status_code == 409 and errors(dup_a)["code"] == "EDIT_REFUSED"


def test_generated_ids_are_unique_when_names_collide(client: TestClient, base: Project) -> None:
    out = edited(
        client,
        base,
        {"op": "add_criterion", "name": "Cost"},
        {"op": "add_criterion", "name": "Cost"},
        {"op": "add_alternative", "name": "Apex"},
    )
    ids = [n.id for n in out.criteria]
    assert len(ids) == len(set(ids)) and {"cost_2", "cost_3"} <= set(ids)
    assert len(set(out.alternative_ids())) == len(out.alternatives)


def test_measuring_a_parent_criterion_is_refused(client: TestClient, base: Project) -> None:
    resp = edit(
        client,
        base,
        {"op": "set_performance", "alternative_id": "apex", "criterion_id": "cost", "value": 1},
    )
    assert resp.status_code == 409
    assert errors(resp)["code"] == "EDIT_REFUSED"
    scale = edit(
        client,
        base,
        {
            "op": "set_scale",
            "criterion_id": "cost",
            "scale": {"type": "ratio", "lower": 0, "upper": 1},
        },
    )
    assert scale.status_code == 409


def test_removing_a_criterion_removes_its_whole_subtree_and_everything_about_it(
    client: TestClient, base: Project
) -> None:
    out = edited(client, base, {"op": "remove_criterion", "criterion_id": "performance"})
    gone = {
        "performance",
        "quality",
        "delivery",
        "defect_rate",
        "certification",
        "on_time",
        "lead_time",
    }
    assert gone.isdisjoint({n.id for n in out.criteria})
    assert gone.isdisjoint({p.criterion_id for p in out.performances})
    assert gone.isdisjoint(set(out.weight_profiles[0].judgements))
    assert gone.isdisjoint({k for s in out.scenarios for k in s.value_function_overrides})
    assert out.tree().leaves() == ["unit_price", "logistics_cost", "financial_stability", "region"]


def test_arbitrary_depth_trees_can_be_built_and_stay_valid(client: TestClient) -> None:
    ops: list[dict[str, Any]] = [{"op": "add_criterion", "name": "L0", "criterion_id": "n0"}]
    for depth in range(1, 12):
        ops.append(
            {
                "op": "add_criterion",
                "name": f"L{depth}",
                "criterion_id": f"n{depth}",
                "parent_id": f"n{depth - 1}",
            }
        )
    out = edited(client, ps.new_project("Deep"), *ops)
    tree = out.tree()
    assert tree.depth("n11") == 12 and tree.leaves() == ["n11"]
    flat = edited(
        client, out, {"op": "move_criterion", "criterion_id": "n11", "new_parent_id": None}
    )
    assert flat.tree().depth("n11") == 1


# ---- invalid requests --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "op",
    [
        {"op": "teleport"},
        {"op": "add_alternative"},
        {"op": "add_alternative", "name": ""},
        {"op": "add_alternative", "name": "x", "alternative_id": "bad id"},
        {"op": "add_criterion", "name": "x", "position": -1},
        {"op": "set_judgement", "node_id": "cost", "rating": "lots"},
        {"op": "set_performance", "alternative_id": "apex", "criterion_id": "cost", "value": None},
        {"op": "set_scale", "criterion_id": "cost", "scale": {"type": "cardinal"}},
        {"op": "add_alternative", "name": "x", "colour": "red"},
    ],
    ids=[
        "unknown-op",
        "missing-name",
        "empty-name",
        "illegal-id",
        "negative-position",
        "non-numeric-rating",
        "null-value",
        "unknown-scale-type",
        "unknown-field",
    ],
)
def test_malformed_operations_are_rejected_before_anything_runs(
    client: TestClient, base: Project, op: dict[str, Any]
) -> None:
    resp = edit(client, base, op)
    assert resp.status_code == 422
    assert errors(resp)["code"] == "INVALID_REQUEST"


def test_an_empty_operation_list_is_rejected(client: TestClient, base: Project) -> None:
    resp = client.post("/api/edit", json={"project": dump(base), "operations": []})
    assert resp.status_code == 422 and errors(resp)["code"] == "INVALID_REQUEST"


def test_non_finite_numbers_cannot_enter_the_model(client: TestClient, base: Project) -> None:
    for bad in ("NaN", "Infinity"):
        raw = (
            f'{{"project": {base.model_dump_json()}, "operations": '
            f'[{{"op": "set_judgement", "node_id": "cost", "rating": {bad}}}]}}'
        )
        resp = client.post("/api/edit", content=raw, headers={"Content-Type": "application/json"})
        assert resp.status_code == 422, bad


# ---- measurement settings: invalid combinations are reported, not hidden ------------------
def test_an_incompatible_scale_and_value_function_is_flagged_by_validation(
    client: TestClient, base: Project
) -> None:
    resp = edit(
        client,
        base,
        {
            "op": "set_scale",
            "criterion_id": "unit_price",
            "scale": {"type": "ordinal", "labels": ["low", "high"]},
        },
    )
    assert resp.status_code == 200
    issues = resp.json()["validation"]["issues"]
    hit = [i for i in issues if i["code"] == "INCOMPATIBLE_VALUE_FUNCTION"]
    assert hit and hit[0]["path"] == "criteria[unit_price]"


def test_switching_a_scale_and_function_together_leaves_a_consistent_leaf(
    client: TestClient, base: Project
) -> None:
    vf = Piecewise(points=[ControlPoint(x=0, value=1), ControlPoint(x=50, value=0)])
    resp = edit(
        client,
        base,
        {"op": "clear_criterion_performances", "criterion_id": "logistics_cost"},
        {
            "op": "set_scale",
            "criterion_id": "logistics_cost",
            "scale": Scale(
                type=ScaleType.INTERVAL, unit="pts", lower=0, upper=50, anchor_mode=AnchorMode.FIXED
            ).model_dump(mode="json"),
        },
        {
            "op": "set_value_function",
            "criterion_id": "logistics_cost",
            "value_function": vf.model_dump(mode="json"),
        },
    )
    assert resp.status_code == 200
    issues = [i for i in resp.json()["validation"]["issues"] if "logistics_cost" in i["path"]]
    assert {i["code"] for i in issues} == {"MISSING_MEASUREMENT"}
