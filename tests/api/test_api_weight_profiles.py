"""Atomic profile commands never write until Save, and preserve reference integrity."""

import json

import pytest
from conftest import dump

from mcda_studio.domain.preferences import Scenario
from mcda_studio.services import project_service as ps

from builders import tiny_project


def edit(client, p, ops):
    return client.post(
        "/api/edit", json={"project": dump(p) if hasattr(p, "model_dump") else p, "operations": ops}
    )


def test_profile_transaction_preview_save_and_reopen(client):
    p = ps.add_scenario(tiny_project(), Scenario(id="auto", name="Automatic"))
    created = client.post("/api/projects/import", json=dump(p))
    original = client.get(f"/api/projects/{p.id}/file").content
    response = edit(
        client,
        p,
        [
            {
                "op": "duplicate_weight_profile",
                "profile_id": "default",
                "name": "Other",
                "new_profile_id": "other",
            },
            {"op": "set_judgement", "profile_id": "other", "node_id": "cost", "rating": 250},
            {"op": "rename_weight_profile", "profile_id": "other", "name": "Independent analyst"},
            {
                "op": "remove_weight_profile",
                "profile_id": "default",
                "replacement_profile_id": "other",
            },
        ],
    )
    assert response.status_code == 200
    draft = response.json()["project"]
    assert draft["analysis"]["weight_profile_id"] == "other"
    assert draft["scenarios"][0]["weight_profile_id"] == "other"
    assert draft["weight_profiles"][0]["judgements"]["cost"] == 250
    preview = client.post("/api/weights/preview", json={"project": draft}).json()
    assert preview["weights_ready"] and preview["weight_profile_id"] == "other"
    assert client.get(f"/api/projects/{p.id}/file").content == original
    saved = client.put(
        f"/api/projects/{p.id}", json=draft, headers={"If-Match": created.headers["etag"]}
    )
    assert saved.status_code == 200
    assert client.get(f"/api/projects/{p.id}").json()["project"] == draft
    assert p.analysis.weight_profile_id is None and p.scenarios[0].weight_profile_id is None


def test_failed_reference_replacement_refuses_the_entire_batch_and_library_is_unchanged(client):
    p = tiny_project()
    client.post("/api/projects/import", json=dump(p))
    before = client.get(f"/api/projects/{p.id}/file").content
    result = edit(
        client,
        p,
        [
            {"op": "create_weight_profile", "name": "Other", "profile_id": "other"},
            {"op": "remove_weight_profile", "profile_id": "default"},
        ],
    )
    assert result.status_code == 409 and result.json()["error"]["code"] == "EDIT_REFUSED"
    assert result.json()["error"]["details"][0]["path"] == "operations[1]"
    assert client.get(f"/api/projects/{p.id}/file").content == before
    assert client.get(f"/api/projects/{p.id}").json()["fingerprint"] == p.fingerprint()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_judgements_are_rejected_at_http_boundary(client, value):
    body = {
        "project": dump(tiny_project()),
        "operations": [{"op": "set_judgement", "node_id": "cost", "rating": value}],
    }
    response = client.post(
        "/api/edit", content=json.dumps(body), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "INVALID_REQUEST"


def test_blank_new_profile_keeps_weight_readiness_distinct_from_missing_measurements(client):
    p = tiny_project()
    p.performances = []
    r = edit(
        client,
        p,
        [{"op": "create_weight_profile", "name": "Incomplete", "profile_id": "incomplete"}],
    )
    assert r.status_code == 200
    draft = r.json()["project"]
    first = client.post(
        "/api/weights/preview",
        json={"project": draft, "configuration": {"weight_profile_id": "default"}},
    ).json()
    other = client.post(
        "/api/weights/preview",
        json={"project": draft, "configuration": {"weight_profile_id": "incomplete"}},
    ).json()
    assert first["weights_ready"] and not other["weights_ready"]
    assert other["local_weights"] == other["global_weights"] == {}
    assert "MISSING_JUDGEMENT" in {i["code"] for i in other["diagnostics"]}
    assert first["swing_ranges"]["cost"]["readiness"] == "ready"
