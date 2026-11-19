"""The new screening route reads a draft without writing the saved project."""

from conftest import EXAMPLES, dump, import_file, repo
from fastapi.testclient import TestClient

from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.services.screening_profiles_service import compare_profiles

STUDY = EXAMPLES / "nz_venture_screening"


def test_profile_route_is_read_only_and_rejects_an_unknown_profile(client: TestClient) -> None:
    project = repo.load(STUDY / "project.json")
    project_id = import_file(client, STUDY / "project.json")["project"]["id"]
    before = client.get(f"/api/projects/{project_id}")
    before_file = client.get(f"/api/projects/{project_id}/file").content
    cfg = AnalysisConfiguration(
        method="mavt_sorting", weight_profile_id="technical_ip", scenario_id="linear_market_size"
    )
    body = {
        "project": dump(project),
        "configuration": cfg.model_dump(mode="json"),
        "profile_ids": ["commercial_traction", "technical_ip"],
    }
    response = client.post("/api/screening-summary/profiles", json=body)
    assert response.status_code == 200, response.text
    assert response.json() == compare_profiles(project, cfg, body["profile_ids"]).model_dump(
        mode="json"
    )
    after = client.get(f"/api/projects/{project_id}")
    assert after.content == before.content and after.headers["etag"] == before.headers["etag"]
    assert client.get(f"/api/projects/{project_id}/file").content == before_file
    refused = client.post(
        "/api/screening-summary/profiles", json={**body, "profile_ids": ["technical_ip", "missing"]}
    )
    assert refused.status_code == 422
