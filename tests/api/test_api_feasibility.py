"""The feasibility check through the HTTP API and the CLI: the routes, the edit operations and
schema versions, the JSON and CSV downloads, and the commands."""

import csv
import io
import json
from pathlib import Path
from typing import Any

import pytest
from conftest import EXAMPLES, dump, errors, import_file, repo
from fastapi.testclient import TestClient
from rich.console import Console
from typer.testing import CliRunner

from mcda_studio import cli
from mcda_studio.cli import app as cli_app
from mcda_studio.storage.json_repository import to_json_text

QUALIFICATION = EXAMPLES / "supplier_qualification" / "project.json"
LABEL = "feasibility: each requirement is tested on its own measurement; no score offsets a failure"
REQUIREMENTS: list[dict[str, Any]] = [
    {"kind": "bound", "id": "price_cap", "name": "Within budget", "criterion_id": "unit_price",
     "unit": "NZD", "maximum": 45},
    {"kind": "labels", "id": "certified", "name": "Certified", "criterion_id": "certification",
     "allowed": ["iso9001", "iso9001_14001"]},
]  # fmt: skip


def stated() -> dict[str, Any]:
    return {**dump(repo.load(QUALIFICATION)), "requirements": REQUIREMENTS, "schema_version": 6}


def flat(text: str) -> str:
    return " ".join(text.split())


def test_the_draft_and_stored_routes(client: TestClient, tmp_path: Path) -> None:
    result = client.post("/api/feasibility", json={"project": stated()}).json()
    assert result["label"] == LABEL
    overall = {a["alternative_id"]: a["status"] for a in result["alternatives"]}
    assert overall == {
        "apex": "pass",
        "brightline": "pass",
        "cobalt": "fail",
        "delta": "fail",
        "evergreen": "pass",
    }
    path = tmp_path / "q.json"
    path.write_text(json.dumps(stated()))
    project_id = import_file(client, path)["project"]["id"]
    stored = client.post(f"/api/projects/{project_id}/feasibility").json()
    assert stored["alternatives"] == result["alternatives"]


def test_errors_are_422_with_their_codes(client: TestClient) -> None:
    bare = client.post("/api/feasibility", json={"project": dump(repo.load(QUALIFICATION))})
    assert bare.status_code == 422 and errors(bare)["code"] == "VALIDATION_FAILED"
    assert [d["code"] for d in errors(bare)["details"]] == ["NO_REQUIREMENTS"]
    wrong = stated()
    wrong["requirements"] = [{**REQUIREMENTS[0], "unit": "USD"}]
    response = client.post("/api/feasibility", json={"project": wrong})
    assert [d["code"] for d in errors(response)["details"]] == ["REQUIREMENT_UNIT_MISMATCH"]
    # methods ignore requirements, even broken ones
    evaluated = client.post("/api/evaluate", json={"project": wrong})
    assert evaluated.status_code == 200


def test_a_ranking_is_unchanged_by_requirements(client: TestClient) -> None:
    def ranking(project: dict[str, Any]) -> list[Any]:
        body = client.post("/api/evaluate", json={"project": project}).json()
        return [(r["alternative_id"], r["rank"], r["value"]) for r in body["ranking"]]

    assert ranking(stated()) == ranking(dump(repo.load(QUALIFICATION)))


def test_duplicate_measurement_is_unknown_through_api(client: TestClient) -> None:
    project = stated()
    project["performances"].append(
        {"alternative_id": "apex", "criterion_id": "unit_price", "value": 100}
    )
    response = client.post("/api/feasibility", json={"project": project})
    assert response.status_code == 200
    apex = next(a for a in response.json()["alternatives"] if a["alternative_id"] == "apex")
    assert apex["status"] == "unknown"
    assert apex["checks"][0]["measurement"] is None
    assert "multiple measurements" in apex["checks"][0]["reason"]


def test_edit_operations_move_a_project_between_schema_versions(client: TestClient) -> None:
    start = dump(repo.load(QUALIFICATION))
    added = client.post(
        "/api/edit",
        json={
            "project": start,
            "operations": [{"op": "set_requirements", "requirements": REQUIREMENTS}],
        },
    ).json()["project"]
    assert added["schema_version"] == 6 and [r["id"] for r in added["requirements"]] == [
        "price_cap",
        "certified",
    ]
    cleared = client.post(
        "/api/edit", json={"project": added, "operations": [{"op": "clear_requirements"}]}
    ).json()["project"]
    assert cleared == start and cleared["schema_version"] == 2
    emptied = client.post(
        "/api/edit",
        json={"project": added, "operations": [{"op": "set_requirements", "requirements": []}]},
    ).json()["project"]
    assert emptied == start


def test_the_downloads(client: TestClient, tmp_path: Path) -> None:
    project = stated()
    fingerprint = client.post("/api/feasibility", json={"project": project}).json()[
        "project_fingerprint"
    ]
    document = client.post(
        "/api/feasibility/export",
        json={"project": project, "expected_project_fingerprint": fingerprint, "format": "json"},
    )
    assert document.status_code == 200 and document.json()["label"] == LABEL
    assert "-feasibility.json" in document.headers["content-disposition"]
    response = client.post(
        "/api/feasibility/export",
        json={"project": project, "expected_project_fingerprint": fingerprint, "format": "csv"},
    )
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert response.headers["content-type"].startswith("text/csv") and len(rows) == 10
    assert {r["label"] for r in rows} == {LABEL}
    stale = client.post(
        "/api/feasibility/export",
        json={"project": project, "expected_project_fingerprint": "0" * 64, "format": "csv"},
    )
    assert stale.status_code == 412 and errors(stale)["code"] == "STALE_REVISION"
    path = tmp_path / "q.json"
    path.write_text(json.dumps(project))
    project_id = import_file(client, path)["project"]["id"]
    stored = client.post(
        f"/api/projects/{project_id}/feasibility/export",
        json={"expected_project_fingerprint": fingerprint, "format": "json"},
    )
    assert (
        stored.status_code == 200
        and stored.json()["alternatives"] == document.json()["alternatives"]
    )


def test_the_cli_states_checks_prints_beside_and_clears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "console", Console(width=200))
    monkeypatch.setattr(cli, "err_console", Console(stderr=True, width=200))
    path = tmp_path / "q.json"
    path.write_text(to_json_text(repo.load(QUALIFICATION)))
    start = path.read_bytes()
    f = str(path)
    runner = CliRunner()

    def run(*args: str, code: int = 0) -> str:
        result = runner.invoke(cli_app, list(args))
        assert result.exit_code == code, result.output
        return flat(result.output)

    run("requirement", "bound", f, "price_cap", "unit_price", "--name", "Within budget",
        "--max", "45", "--unit", "NZD")  # fmt: skip
    run("requirement", "labels", f, "certified", "certification", "--name", "Certified",
        "--at-least", "iso9001")  # fmt: skip
    raw = json.loads(path.read_text())
    assert raw["schema_version"] == 6
    assert raw["requirements"][1]["allowed"] == ["iso9001", "iso9001_14001"]
    out = run("feasibility", f)
    assert LABEL in out
    assert "Delta Parts, Within budget: 51 NZD is above the maximum 45 NZD" in out
    out = run("evaluate", f)
    assert "feasibility:" in out and "fail (price_cap)" in out
    out = run("compare-methods", f)
    assert "feasibility:" in out
    run("requirement", "bound", f, "price_cap", "unit_price", "--name", "Within budget",
        "--max", "45", "--exclusive-max", "--unit", "USD")  # fmt: skip
    assert "REQUIREMENT_UNIT_MISMATCH" in run("feasibility", f, code=1)
    assert "feasibility not checked" in run("evaluate", f)
    assert "give --min, --max or both" in run(
        "requirement", "bound", f, "x", "unit_price", "--name", "X", code=1
    )
    assert "exactly one of --allow" in run(
        "requirement", "labels", f, "x", "region", "--name", "X", code=1
    )
    assert "need an ordinal leaf" in run(
        "requirement", "labels", f, "x", "region", "--name", "X", "--at-most", "regional", code=1
    )
    run("requirement", "labels", f, "home", "region", "--name", "Home", "--allow", "domestic")
    out_file = tmp_path / "f.json"
    run("feasibility", f, "-o", str(out_file), code=1)  # the USD bound still blocks it
    run("requirement", "remove", f, "price_cap")
    run("feasibility", f, "-o", str(out_file))
    assert [r["id"] for r in json.loads(out_file.read_text())["requirements"]] == [
        "certified",
        "home",
    ]
    run("requirement", "clear", f)
    assert path.read_bytes() == start
