"""The new screening route reads a draft without writing the saved project."""

import json

from conftest import EXAMPLES, dump, import_file, repo
from fastapi.testclient import TestClient

from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.services.screening_what_if_service import what_if_weights

STUDY = EXAMPLES / "nz_venture_screening"


def test_trial_route_cannot_write_source_or_return_a_temporary_project(client: TestClient) -> None:
    project = repo.load(STUDY / "project.json")
    project_id = import_file(client, STUDY / "project.json")["project"]["id"]
    before = client.get(f"/api/projects/{project_id}")
    file = client.get(f"/api/projects/{project_id}/file").content
    cfg = AnalysisConfiguration(
        method="mavt_sorting",
        weight_profile_id="commercial_traction",
        scenario_id="linear_market_size",
    )
    body = {
        "project": dump(project),
        "configuration": cfg.model_dump(mode="json"),
        "ratings": {"team": 170.125},
    }
    response = client.post("/api/screening-summary/what-if", json=body)
    assert response.status_code == 200, response.text
    assert response.json() == what_if_weights(project, cfg, body["ratings"]).model_dump(mode="json")
    assert set(response.json()) == {
        "project_fingerprint",
        "configuration",
        "weight_profile_id",
        "scenario_id",
        "status",
        "reason",
        "ratings",
        "controls",
        "trial_project_fingerprint",
        "summary",
        "record",
    }
    after = client.get(f"/api/projects/{project_id}")
    assert after.content == before.content and after.headers["etag"] == before.headers["etag"]
    assert client.get(f"/api/projects/{project_id}/file").content == file
    for ratings in ({"team": True}, {"team": "12"}, {"team": -1}):
        refused = client.post("/api/screening-summary/what-if", json={**body, "ratings": ratings})
        assert refused.status_code == 422, refused.text
    for value in (float("nan"), float("inf"), -float("inf")):
        refused = client.post(
            "/api/screening-summary/what-if",
            content=json.dumps({**body, "ratings": {"team": value}}),
            headers={"Content-Type": "application/json"},
        )
        assert refused.status_code == 422, refused.text
