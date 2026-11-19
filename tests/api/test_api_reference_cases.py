"""Reference cases over HTTP and from the command line: the routes return the service's own
results, an invalid reference set is refused with every path, a stored project's bytes and ETag
are unchanged by looking, and the commands print the service's JSON."""

import json
from pathlib import Path
from typing import Any

from conftest import dump, errors, import_file
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import reference_case_builders as b
from mcda_studio.cli import app as cli_app
from mcda_studio.services import reference_case_service as svc
from mcda_studio.storage.json_repository import JsonProjectRepository

HAND = {"o4": "D", "o5": "v5", "cat": "red"}
FULL = {"o4": "A", "o5": "v1", "cat": "green", "o4b": "B", "o5b": "v4"}


def raw_set() -> dict[str, Any]:
    return b.reference_set(b.case("hand", HAND), b.case("full", FULL))


def test_the_route_equals_the_service_and_outcomes_need_asking(client: TestClient) -> None:
    project = b.project()
    expected = svc.reference_cases(project, b.load(raw_set()), alternative_id="x")
    body = {"project": dump(project), "reference_cases": raw_set(), "alternative_id": "x"}
    response = client.post("/api/reference-cases", json=body)
    assert response.status_code == 200, response.text
    assert response.json() == expected.model_dump(mode="json")
    assert all(c["outcome"] is None for c in response.json()["alternatives"][0]["cases"])
    shown = client.post("/api/reference-cases", json={**body, "include_outcomes": True}).json()
    assert shown["alternatives"][0]["cases"][0]["outcome"]["label"] == "An outcome"
    weighted = client.post("/api/reference-cases", json={**body, "weighting": "profile", "k": 1})
    assert weighted.status_code == 200 and len(weighted.json()["alternatives"][0]["cases"]) == 1


def test_an_invalid_set_is_refused_with_paths_and_validate_reports_them(
    client: TestClient,
) -> None:
    raw = raw_set()
    raw["cases"][1]["ratings"][0]["label"] = "Z"
    raw["cases"][0]["claims"][0]["source"] = "undated"
    body = {"project": dump(b.project()), "reference_cases": raw}
    refused = client.post("/api/reference-cases", json=body)
    assert refused.status_code == 422
    err = errors(refused)
    assert err["code"] == "VALIDATION_FAILED"
    paths = {d["path"] for d in err["details"]}
    assert "cases[1].ratings[0].label" in paths
    assert "cases[0].ratings[0].claim_ids[0]" in paths
    checked = client.post("/api/reference-cases/validate", json=body)
    assert checked.status_code == 200
    report = checked.json()
    assert report["valid"] is False
    assert {i["code"] for i in report["issues"]} == {
        "REFERENCE_UNKNOWN_LABEL",
        "REFERENCE_UNDATED_SOURCE",
    }
    fine = client.post(
        "/api/reference-cases/validate",
        json={"project": dump(b.project()), "reference_cases": raw_set()},
    )
    assert fine.json()["valid"] is True and fine.json()["rating_count"] == 8


def test_bad_options_and_formats_are_refused(client: TestClient) -> None:
    body = {"project": dump(b.project()), "reference_cases": raw_set()}
    for extra in ({"k": 0}, {"k": 21}, {"weighting": "both"}, {"reference_cases": {"version": 2}}):
        assert client.post("/api/reference-cases", json={**body, **extra}).status_code == 422
    unknown = client.post("/api/reference-cases", json={**body, "alternative_id": "nobody"})
    assert unknown.status_code == 422 and errors(unknown)["code"] == "UNKNOWN_REFERENCE"
    fraction = client.post("/api/reference-cases", json={**body, "min_shared_fraction": "2"})
    assert fraction.status_code == 400


def test_looking_leaves_a_stored_project_and_its_etag_unchanged(
    client: TestClient, tmp_path: Path
) -> None:
    path = tmp_path / "fixture.json"
    JsonProjectRepository().save(b.project(), path)
    stored_id = import_file(client, path)["project"]["id"]
    before = client.get(f"/api/projects/{stored_id}")
    project = before.json()["project"]
    for extra in ({}, {"include_outcomes": True}, {"alternative_id": "y"}):
        answer = client.post(
            "/api/reference-cases",
            json={"project": project, "reference_cases": raw_set(), **extra},
        )
        assert answer.status_code == 200, answer.text
    client.post(
        "/api/reference-cases/validate", json={"project": project, "reference_cases": raw_set()}
    )
    after = client.get(f"/api/projects/{stored_id}")
    assert after.json() == before.json()
    assert after.headers["ETag"] == before.headers["ETag"]


def run(*args: str) -> Any:
    return CliRunner().invoke(cli_app, ["reference-cases", *args])


def test_the_commands_print_the_services_json(tmp_path: Path) -> None:
    project_path = tmp_path / "p.json"
    JsonProjectRepository().save(b.project(), project_path)
    set_path = tmp_path / "r.json"
    set_path.write_text(json.dumps(raw_set()), encoding="utf-8")
    before = project_path.read_bytes()
    result = run(str(project_path), "--reference-cases", str(set_path), "--alternative", "x")
    assert result.exit_code == 0, result.output
    expected = svc.reference_cases(b.project(), b.load(raw_set()), alternative_id="x")
    assert json.loads(result.stdout) == json.loads(expected.model_dump_json())
    same = run("run", str(project_path), "--reference-cases", str(set_path), "--alternative", "x")
    assert json.loads(same.stdout) == json.loads(result.stdout)
    outcomes = run(
        str(project_path),
        "--reference-cases",
        str(set_path),
        "--include-outcomes",
        "--weighting",
        "profile",
        "--k",
        "1",
        "--profile",
        "four",
    )
    assert outcomes.exit_code == 0, outcomes.output
    data = json.loads(outcomes.stdout)
    assert data["weight_profile_id"] == "four" and data["weighting"] == "profile"
    assert data["alternatives"][0]["cases"][0]["outcome"]["as_of"]
    valid = run("validate", str(set_path), "--project", str(project_path))
    assert valid.exit_code == 0 and json.loads(valid.stdout)["valid"] is True
    assert project_path.read_bytes() == before


def test_the_commands_reject_bad_inputs(tmp_path: Path) -> None:
    project_path = tmp_path / "p.json"
    JsonProjectRepository().save(b.project(), project_path)
    broken = tmp_path / "broken.json"
    broken.write_text("{}", encoding="utf-8")
    assert run(str(project_path), "--reference-cases", str(broken)).exit_code != 0
    bad = raw_set()
    bad["cases"][0]["ratings"][0]["label"] = "Z"
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    refused = run(str(project_path), "--reference-cases", str(bad_path))
    assert refused.exit_code == 1 and "REFERENCE_UNKNOWN_LABEL" in refused.output
    checked = run("validate", str(bad_path), "--project", str(project_path))
    assert checked.exit_code == 1 and json.loads(checked.stdout)["valid"] is False
    good = tmp_path / "good.json"
    good.write_text(json.dumps(raw_set()), encoding="utf-8")
    assert run(str(project_path), "--reference-cases", str(good), "--k", "0").exit_code == 1
    assert run(str(project_path), "--reference-cases", str(good), "--weighting", "x").exit_code == 1
    assert run(str(tmp_path / "missing.json"), "--reference-cases", str(good)).exit_code != 0


def test_exclude_same_id_over_http_and_from_the_command_line(
    client: TestClient, tmp_path: Path
) -> None:
    raw = b.reference_set(b.case("x", FULL), b.case("hand", HAND))
    project = b.project()
    expected = svc.reference_cases(
        project, b.load(raw), alternative_id="x", exclude_same_id=True
    ).model_dump(mode="json")
    assert expected["alternatives"][0]["excluded_case_ids"] == ["x"]
    body = {"project": dump(project), "reference_cases": raw, "alternative_id": "x"}
    kept = client.post("/api/reference-cases", json=body).json()
    assert kept["exclude_same_id"] is False
    assert "x" in [c["case_id"] for c in kept["alternatives"][0]["cases"]]
    left = client.post("/api/reference-cases", json={**body, "exclude_same_id": True})
    assert left.status_code == 200 and left.json() == expected
    project_path = tmp_path / "p.json"
    JsonProjectRepository().save(project, project_path)
    set_path = tmp_path / "r.json"
    set_path.write_text(json.dumps(raw), encoding="utf-8")
    printed = run(
        str(project_path),
        "--reference-cases",
        str(set_path),
        "--alternative",
        "x",
        "--exclude-same-id",
    )
    assert printed.exit_code == 0, printed.output
    assert json.loads(printed.stdout) == expected
