"""Decision impact over HTTP and from the command line: the route returns the service's own result,
the existing Open Questions route and command are unchanged, looking changes nothing, and the
command rejects bad inputs."""

import json
from pathlib import Path

from conftest import EXAMPLES, dump, import_file, repo
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from mcda_studio.cli import app as cli_app
from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.services import decision_impact_service as impact
from mcda_studio.services import questions_service

STUDY = EXAMPLES / "nz_venture_screening"


def dossier() -> EvidenceDossier:
    return EvidenceDossier.model_validate_json((STUDY / "evidence.json").read_text())


def test_the_route_equals_the_service_and_leaves_open_questions_alone(client: TestClient) -> None:
    project = repo.load(STUDY / "project.json")
    cfg = {"method": "mavt", "weight_profile_id": "commercial_traction"}
    expected = impact.decision_impact(project, AnalysisConfiguration(**cfg), dossier())
    response = client.post(
        "/api/decision-impact",
        json={
            "project": dump(project),
            "configuration": cfg,
            "dossier": dossier().model_dump(mode="json"),
        },
    )
    assert response.status_code == 200, response.text
    assert response.json() == expected.model_dump(mode="json")
    assert response.json()["cells"][0]["tier"] == "leader_or_class"
    # the existing route answers exactly as the service always did, with no impact fields
    before = questions_service.open_questions(project, AnalysisConfiguration(method="mavt"))
    plain = client.post(
        "/api/open-questions", json={"project": dump(project), "configuration": {"method": "mavt"}}
    )
    assert plain.status_code == 200 and plain.json() == before.model_dump(mode="json")
    assert "cells" not in plain.json() and "tier" not in json.dumps(plain.json())


def test_a_missing_measurement_is_unavailable_with_its_reason_and_nothing_is_stored(
    client: TestClient,
) -> None:
    project = dump(repo.load(STUDY / "project.json"))
    project["performances"] = project["performances"][1:]
    stored_before = client.get("/api/projects").json()
    result = client.post("/api/decision-impact", json={"project": project}).json()
    assert (
        result["status"] == "unavailable"
        and "missing" in result["reason"]
        and result["cells"] == []
    )
    assert client.get("/api/projects").json() == stored_before


def test_a_stored_study_is_untouched_and_an_unknown_profile_is_an_error(client: TestClient) -> None:
    stored_id = import_file(client, STUDY / "project.json")["project"]["id"]
    before = client.get(f"/api/projects/{stored_id}").json()
    project = before["project"]
    ok = client.post("/api/decision-impact", json={"project": project})
    assert ok.status_code == 200 and ok.json()["status"] == "available"
    assert client.get(f"/api/projects/{stored_id}").json() == before
    bad = client.post(
        "/api/decision-impact",
        json={"project": project, "configuration": {"method": "mavt", "weight_profile_id": "nope"}},
    )
    assert bad.status_code == 200 and bad.json()["status"] == "unavailable"


def run(*args: str):
    return CliRunner().invoke(cli_app, ["decision-impact", *args])


def test_the_command_prints_the_services_json_and_open_questions_is_unchanged() -> None:
    project = STUDY / "project.json"
    result = run(
        str(project), "--evidence", str(STUDY / "evidence.json"), "--profile", "commercial_traction"
    )
    assert result.exit_code == 0, result.output
    expected = impact.decision_impact(
        repo.load(project),
        AnalysisConfiguration(method="mavt", weight_profile_id="commercial_traction"),
        dossier(),
    )
    assert json.loads(result.stdout) == expected.model_dump(mode="json")
    old = CliRunner().invoke(cli_app, ["open-questions", str(project)])
    assert (
        old.exit_code == 0 and "tier" not in old.stdout and "decision" not in json.loads(old.stdout)
    )


def test_the_command_rejects_bad_files_and_unknown_scenarios(tmp_path: Path) -> None:
    project = str(STUDY / "project.json")
    broken = tmp_path / "e.json"
    broken.write_text("{}")
    assert run(project, "--evidence", str(broken)).exit_code != 0
    assert run(project, "--proposals", str(broken)).exit_code != 0
    assert run(str(tmp_path / "missing.json")).exit_code != 0
    unknown = run(project, "--scenario", "missing")
    assert unknown.exit_code == 0 and json.loads(unknown.stdout)["status"] == "unavailable"
