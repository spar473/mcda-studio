"""The sensitivity-probe endpoints: equal to the service, strictly read-only, clearly refused."""

import pytest
from conftest import VC_FILE, dump, repo

from mcda_studio.services import analysis_service as svc

from builders import tiny_project

CONFIG = {"method": "mavt", "scenario_id": None, "weight_profile_id": None, "parameters": {}}


def vc():
    return repo.load(VC_FILE)


def test_http_probe_equals_the_service_result_exactly(client):
    p = vc()
    body = {
        "project": dump(p),
        "node_id": "team",
        "weight": 0.5688552162065278,
        "configuration": CONFIG,
    }
    r = client.post("/api/sensitivity/probe", json=body)
    assert r.status_code == 200
    direct = svc.sensitivity_probe(p, "team", 0.5688552162065278, p.analysis)
    assert r.json() == dump(direct)


def test_the_stored_and_draft_endpoints_agree_and_leave_the_file_untouched(client):
    p = vc()
    assert client.post("/api/projects/import", json=dump(p)).status_code == 201
    original = client.get(f"/api/projects/{p.id}/file").content
    etag = client.get(f"/api/projects/{p.id}").headers.get("etag")

    stored = client.post(
        f"/api/projects/{p.id}/sensitivity/probe",
        json={"node_id": "market_size", "weight": 0.873, "configuration": CONFIG},
    )
    draft = client.post(
        "/api/sensitivity/probe",
        json={
            "project": dump(p),
            "node_id": "market_size",
            "weight": 0.873,
            "configuration": CONFIG,
        },
    )
    assert stored.status_code == draft.status_code == 200
    assert stored.json() == draft.json()
    # Nothing was written, and the revision did not move.
    assert client.get(f"/api/projects/{p.id}/file").content == original
    assert client.get(f"/api/projects/{p.id}").headers.get("etag") == etag


def test_many_probes_never_move_the_fingerprint_or_the_stored_bytes(client):
    """A cursor sweep is the realistic case: dozens of probes, zero persistence."""
    p = vc()
    assert client.post("/api/projects/import", json=dump(p)).status_code == 201
    original = client.get(f"/api/projects/{p.id}/file").content
    fingerprint = p.fingerprint()
    for i in range(25):
        r = client.post(
            f"/api/projects/{p.id}/sensitivity/probe",
            json={"node_id": "team", "weight": i / 24, "configuration": CONFIG},
        )
        assert r.status_code == 200
        assert r.json()["project_fingerprint"] == fingerprint
    assert client.get(f"/api/projects/{p.id}/file").content == original


@pytest.mark.parametrize("weight", [-0.0001, 1.0001, 2, -5])
def test_weights_outside_the_unit_interval_are_rejected_by_the_schema(client, weight):
    r = client.post(
        "/api/sensitivity/probe",
        json={"project": dump(tiny_project()), "node_id": "cost", "weight": weight},
    )
    assert r.status_code == 422


@pytest.mark.parametrize("weight", ["nan", "inf", "-inf"])
def test_nonfinite_weights_are_rejected(client, weight):
    r = client.post(
        "/api/sensitivity/probe",
        json={"project": dump(tiny_project()), "node_id": "cost", "weight": weight},
    )
    assert r.status_code == 422


def test_an_unknown_node_is_a_structured_error_not_a_crash(client):
    r = client.post(
        "/api/sensitivity/probe",
        json={"project": dump(tiny_project()), "node_id": "ghost", "weight": 0.5},
    )
    assert r.status_code == 422
    assert "ghost" in str(r.json())


def test_an_ineligible_only_child_is_refused_with_a_usable_reason(client):
    p = repo.load(VC_FILE.parents[1] / "infrastructure_procurement" / "project.json")
    r = client.post(
        "/api/sensitivity/probe",
        json={"project": dump(p), "node_id": "track_record", "weight": 0.5},
    )
    assert r.status_code == 422
    assert "no siblings" in str(r.json())


def test_an_unknown_profile_reference_is_refused_rather_than_silently_resolved(client):
    r = client.post(
        "/api/sensitivity/probe",
        json={
            "project": dump(tiny_project()),
            "node_id": "cost",
            "weight": 0.5,
            "configuration": {**CONFIG, "weight_profile_id": "ghost"},
        },
    )
    assert r.status_code == 422


def test_the_response_identifies_the_context_it_resolved(client):
    p = vc()
    r = client.post(
        "/api/sensitivity/probe",
        json={
            "project": dump(p),
            "node_id": "market_size",
            "weight": 0.4,
            "configuration": {**CONFIG, "scenario_id": "linear_market_size"},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["project_fingerprint"] == p.fingerprint()
    assert body["scenario_id"] == "linear_market_size"
    assert body["weight_profile_id"] == "default"
    assert body["configuration"]["scenario_id"] == "linear_market_size"
    assert body["node_path"] == ["market", "market_size"]
    assert body["weight"] == 0.4


def test_existing_sensitivity_endpoints_are_unchanged(client):
    """The probe is additive: the sweep contract must still match the service exactly."""
    p = vc()
    r = client.post(
        "/api/sensitivity",
        json={"project": dump(p), "node_id": "team", "configuration": CONFIG, "steps": 101},
    )
    assert r.status_code == 200
    assert r.json() == dump(svc.sensitivity(p, "team", p.analysis, 101))


def test_exact_crossover_reports_a_changed_rank_and_winner_set(client):
    project = vc()
    before = project.fingerprint()
    response = client.post(
        "/api/sensitivity/probe",
        json={"project": dump(project), "node_id": "team", "weight": 0.5688552162065278},
    )
    assert response.status_code == 200
    probe = response.json()
    assert probe["ranking"] == probe["baseline_ranking"]
    assert probe["ranking_differs_from_baseline"]
    assert probe["winner_differs_from_baseline"]
    assert [row["rank"] for row in probe["alternatives"]] == [1, 1, 3, 4]
    assert project.fingerprint() == before
