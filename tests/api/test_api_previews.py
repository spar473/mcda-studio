"""New read-only endpoints preserve existing contracts and never write project data."""

import json

import pytest
from conftest import dump

from mcda_studio.services import analysis_service as svc

from builders import tiny_project


@pytest.mark.parametrize("endpoint", ["weights", "value-functions"])
def test_http_preview_equals_service_and_never_modifies_library(client, endpoint):
    p = tiny_project()
    before = p.model_dump_json(), p.fingerprint()
    imported = client.post("/api/projects/import", json=dump(p))
    assert imported.status_code == 201
    original = client.get(f"/api/projects/{p.id}/file").content
    body = {
        "project": dump(p),
        "configuration": {
            "scenario_id": None,
            "weight_profile_id": None,
            "parameters": {},
            "method": "mavt",
        },
    }
    if endpoint == "weights":
        direct = svc.preview_weights(p)
    else:
        body["criterion_id"] = "cost"
        direct = svc.preview_value_function(p, "cost")
    r = client.post(f"/api/{endpoint}/preview", json=body)
    assert r.status_code == 200 and r.json() == direct.model_dump(mode="json")
    assert client.get(f"/api/projects/{p.id}/file").content == original
    assert client.get(f"/api/projects/{p.id}").headers["etag"] == imported.headers["etag"]
    assert (p.model_dump_json(), p.fingerprint()) == before


def test_candidate_is_scoped_to_request_and_echoed_with_original_snapshot_fingerprint(client):
    p = tiny_project()
    r = client.post(
        "/api/value-functions/preview",
        json={
            "project": dump(p),
            "criterion_id": "cost",
            "candidate": {"scale": {"type": "ratio", "lower": 0, "upper": 200}},
        },
    )
    assert r.status_code == 200
    candidate = r.json()
    assert candidate["project_fingerprint"] == p.fingerprint()
    assert candidate["resolved_domain"]["upper"] == 200
    base = client.post(
        "/api/value-functions/preview", json={"project": dump(p), "criterion_id": "cost"}
    ).json()
    assert base["resolved_domain"]["upper"] == 100
    assert base["candidate_fingerprint"] != candidate["candidate_fingerprint"]
    assert client.get("/api/projects").json()["projects"] == []


def test_incomplete_data_is_reported_without_a_successful_full_evaluation(client):
    p = tiny_project()
    p.performances = []
    body = {"project": dump(p), "criterion_id": "cost"}
    fixed = client.post("/api/value-functions/preview", json=body)
    assert fixed.status_code == 200 and fixed.json()["curve_ready"]
    assert not fixed.json()["measurements_complete"]
    assert client.post("/api/weights/preview", json={"project": dump(p)}).json()["weights_ready"]
    assert client.post("/api/evaluate", json={"project": dump(p)}).status_code == 422
    body["candidate"] = {"scale": {"type": "ratio", "anchor_mode": "local"}}
    local = client.post("/api/value-functions/preview", json=body).json()
    assert not local["curve_ready"] and local["resolved_domain"] is None and local["samples"] == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("sample_count", 1),
        ("sample_count", 502),
        ("sample_count", float("inf")),
        ("criterion_id", "../outside"),
    ],
)
def test_preview_input_bounds_use_standard_error_shape(client, field, value):
    body = {"project": dump(tiny_project()), "criterion_id": "cost", field: value}
    # JSON itself cannot carry infinity; send the raw malformed/non-finite number deliberately.
    r = client.post(
        "/api/value-functions/preview",
        content=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"


def test_unknown_references_and_methods_are_rejected_consistently(client):
    for cfg in [
        {"scenario_id": "missing"},
        {"weight_profile_id": "missing"},
        {"method": "promethee"},
    ]:
        r = client.post(
            "/api/weights/preview", json={"project": dump(tiny_project()), "configuration": cfg}
        )
        assert r.status_code == 422 and r.json()["error"]["code"] == "UNKNOWN_REFERENCE"


@pytest.mark.parametrize(
    "local,missing,state",
    [
        (False, False, "ready"),
        (False, True, "ready"),
        (True, False, "ready"),
        (True, True, "incomplete"),
    ],
)
def test_scoped_readiness_matrix_through_http(client, local, missing, state):
    p = tiny_project()
    if local:
        p.criteria[0].scale.anchor_mode = "local"
    if missing:
        p.performances = [
            m for m in p.performances if not (m.alternative_id == "a" and m.criterion_id == "cost")
        ]
    # An unrelated selected profile reference is not a dependency of a criterion curve.
    r = client.post(
        "/api/value-functions/preview",
        json={
            "project": dump(p),
            "criterion_id": "cost",
            "configuration": {"weight_profile_id": "missing"},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["readiness"] == state
    assert body["measurement_readiness"] == ("incomplete" if missing else "ready")
    if local and missing:
        assert body["resolved_domain"] is None and body["samples"] == []
