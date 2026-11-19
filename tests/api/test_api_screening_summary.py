"""The screening summary over HTTP: the draft and stored routes return the service's own result,
a stale or unknown context is never substituted, and nothing is written."""

from pathlib import Path

from conftest import EXAMPLES, dump, import_file, repo
from fastapi.testclient import TestClient

from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.services import screening_summary_service as summary

STUDY = EXAMPLES / "nz_venture_screening"


def test_draft_and_stored_routes_equal_the_service(client: TestClient, tmp_path: Path) -> None:
    project = repo.load(STUDY / "project.json")
    configuration = {"method": "mavt_sorting", "weight_profile_id": "commercial_traction"}
    expected = summary.screening_summary(project, AnalysisConfiguration(**configuration))
    draft = client.post(
        "/api/screening-summary", json={"project": dump(project), "configuration": configuration}
    )
    assert draft.status_code == 200, draft.text
    assert draft.json() == expected.model_dump(mode="json")
    assert draft.json()["configuration"] == {**configuration, "scenario_id": None, "parameters": {}}
    assert draft.json()["weight_profile_id"] == "commercial_traction"
    stored_id = import_file(client, STUDY / "project.json")["project"]["id"]
    before = client.get(f"/api/projects/{stored_id}").json()
    stored = client.post(
        f"/api/projects/{stored_id}/screening-summary", json={"configuration": configuration}
    )
    assert stored.status_code == 200 and stored.json() == draft.json()
    assert client.get(f"/api/projects/{stored_id}").json() == before


def test_the_dossier_feeds_the_open_question_counts(client: TestClient) -> None:
    project = repo.load(STUDY / "project.json")
    dossier = EvidenceDossier.model_validate_json((STUDY / "evidence.json").read_text())
    body = {"project": dump(project), "dossier": dossier.model_dump(mode="json")}
    with_dossier = client.post("/api/screening-summary", json=body).json()
    without = client.post("/api/screening-summary", json={"project": dump(project)}).json()
    counts = lambda r: {row["alternative_id"]: row["open_questions"] for row in r["rows"]}  # noqa: E731
    assert counts(with_dossier)["upstock"] > counts(without)["upstock"]


def test_an_unknown_project_is_404_and_an_invalid_model_is_unavailable(client: TestClient) -> None:
    assert client.post("/api/projects/nope/screening-summary", json={}).status_code == 404
    project = dump(repo.load(STUDY / "project.json"))
    project["performances"] = project["performances"][1:]
    result = client.post("/api/screening-summary", json={"project": project}).json()
    assert result["status"] == "unavailable" and result["rows"] == []
    assert result["reason"] == "Ranking unavailable: 1 measurement(s) are missing."
