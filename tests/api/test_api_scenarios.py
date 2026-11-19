"""B5 commands and comparisons are atomic; only explicit Save writes project files."""

import pytest
from conftest import dump

from mcda_studio.services import project_service as ps

from builders import tiny_project


def test_scenario_commands_comparison_and_save_roundtrip_do_not_modify_base(client):
    p = tiny_project()
    created = client.post("/api/projects/import", json=dump(p))
    original = client.get(f"/api/projects/{p.id}/file").content
    ops = [
        {"op": "create_scenario", "name": "Scenario", "scenario_id": "s"},
        {
            "op": "set_scenario_override",
            "scenario_id": "s",
            "criterion_id": "cost",
            "value_function": {"kind": "linear", "direction": "increasing"},
        },
        {"op": "duplicate_scenario", "scenario_id": "s", "name": "Copy", "new_scenario_id": "copy"},
        {"op": "rename_scenario", "scenario_id": "copy", "name": "Renamed"},
        {"op": "clear_scenario_override", "scenario_id": "copy", "criterion_id": "cost"},
        {"op": "set_default_scenario", "scenario_id": "s"},
    ]
    response = client.post("/api/edit", json={"project": dump(p), "operations": ops})
    assert response.status_code == 200
    draft = response.json()["project"]
    assert (
        draft["criteria"] == dump(p)["criteria"]
        and draft["performances"] == dump(p)["performances"]
    )
    assert draft["scenarios"][1]["value_function_overrides"] == {}
    compared = client.post(
        "/api/scenarios/compare",
        json={"project": draft, "scenario_ids": ["s"], "configuration": {"scenario_id": "s"}},
    )
    assert compared.status_code == 200
    assert compared.json()["baseline"]["configuration"]["scenario_id"] is None
    assert compared.json()["scenarios"][0]["applied_overrides"]["cost"]["kind"] == "linear"
    assert client.get(f"/api/projects/{p.id}/file").content == original
    saved = client.put(
        f"/api/projects/{p.id}", json=draft, headers={"If-Match": created.headers["etag"]}
    )
    assert saved.status_code == 200
    assert client.get(f"/api/projects/{p.id}").json()["project"] == draft
    assert (
        client.put(
            f"/api/projects/{p.id}", json=draft, headers={"If-Match": created.headers["etag"]}
        ).status_code
        == 412
    )


def test_failed_scenario_batch_is_atomic_and_default_repair_is_explicit(client):
    p = ps.set_default_scenario(ps.create_scenario(tiny_project(), "S", "s"), "s")
    before = p.fingerprint()
    result = client.post(
        "/api/edit",
        json={
            "project": dump(p),
            "operations": [
                {"op": "rename_scenario", "scenario_id": "s", "name": "Changed"},
                {"op": "remove_scenario", "scenario_id": "s"},
            ],
        },
    )
    assert (
        result.status_code == 409
        and result.json()["error"]["details"][0]["path"] == "operations[1]"
    )
    repaired = client.post(
        "/api/edit",
        json={
            "project": dump(p),
            "operations": [
                {
                    "op": "remove_scenario",
                    "scenario_id": "s",
                    "repair_default": True,
                    "replacement_scenario_id": None,
                }
            ],
        },
    )
    assert (
        repaired.status_code == 200
        and repaired.json()["project"]["analysis"]["scenario_id"] is None
    )
    assert p.fingerprint() == before


@pytest.mark.parametrize(
    "op",
    [
        {"op": "set_scenario_profile", "scenario_id": "s", "profile_id": "missing"},
        {
            "op": "set_scenario_override",
            "scenario_id": "missing",
            "criterion_id": "cost",
            "value_function": {"kind": "linear"},
        },
    ],
)
def test_invalid_references_have_structured_errors(client, op):
    p = ps.create_scenario(tiny_project(), "S", "s")
    r = client.post("/api/edit", json={"project": dump(p), "operations": [op]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "UNKNOWN_REFERENCE"


def test_effective_validation_is_read_only_and_has_complete_provenance(client):
    p = tiny_project()
    before = p.fingerprint()
    r = client.post(
        "/api/analysis/validate",
        json={
            "project": dump(p),
            "configuration": {"scenario_id": None, "weight_profile_id": None},
        },
    )
    assert r.status_code == 200 and r.json()["validation"]["issues"] == []
    assert r.json()["project_fingerprint"] == before and r.json()["weight_profile_id"] == "default"
    assert p.fingerprint() == before
