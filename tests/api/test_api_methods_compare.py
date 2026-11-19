"""The method comparison through the HTTP API and the CLI: the routes, typed per-column errors,
the unknown-method refusal, the JSON and long CSV downloads, and the command."""

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

from builders import every_section

QUALIFICATION = EXAMPLES / "supplier_qualification" / "project.json"
CONTEXT = "Agreement between methods that share inputs is not independent validation."


def body(**extra: Any) -> dict[str, Any]:
    return {"project": dump(every_section(repo.load(QUALIFICATION))), **extra}


def test_the_comparison_route(client: TestClient) -> None:
    result = client.post("/api/methods/compare", json=body()).json()
    assert [c["method"] for c in result["columns"]] == [
        "mavt",
        "mavt_sorting",
        "smaa2",
        "promethee2",
        "ahp",
    ]
    assert all(c["status"] == "ok" for c in result["columns"])
    assert result["agreement"]["context"] == CONTEXT
    assert result["alternative_order"] == ["apex", "brightline", "cobalt", "delta", "evergreen"]
    bare = client.post("/api/methods/compare", json={"project": dump(repo.load(QUALIFICATION))})
    failed = {c["method"]: c["error"] for c in bare.json()["columns"] if c["status"] == "failed"}
    assert failed["promethee2"]["code"] == "VALIDATION_FAILED"
    assert failed["promethee2"]["issue_codes"] == ["PROMETHEE_NOT_STATED"]


def test_the_stored_route_and_a_subset(client: TestClient, tmp_path: Path) -> None:
    path = tmp_path / "q.json"
    path.write_text(to_json_text(every_section(repo.load(QUALIFICATION))))
    project_id = import_file(client, path)["project"]["id"]
    stored = client.post(
        f"/api/projects/{project_id}/methods/compare", json={"methods": ["ahp", "mavt"]}
    )
    assert [c["method"] for c in stored.json()["columns"]] == ["mavt", "ahp"]


def test_an_unregistered_method_is_a_422(client: TestClient) -> None:
    response = client.post("/api/methods/compare", json=body(methods=["mavt", "electre"]))
    assert response.status_code == 422 and errors(response)["code"] == "UNKNOWN_REFERENCE"


def export(client: TestClient, fmt: str, fingerprint: str | None = None) -> Any:
    request = body()
    comparison = client.post("/api/methods/compare", json=request).json()
    return client.post(
        "/api/methods/compare/export",
        json={
            **request,
            "format": fmt,
            "expected_project_fingerprint": fingerprint or comparison["project_fingerprint"],
        },
    )


def test_the_json_and_long_csv_downloads(client: TestClient) -> None:
    document = export(client, "json")
    assert document.status_code == 200 and document.headers["content-type"].startswith(
        "application/json"
    )
    assert 'filename="mcda-' in document.headers["content-disposition"]
    parsed = json.loads(document.content)
    assert all(c["record_digest"] for c in parsed["columns"])
    response = export(client, "csv")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 5 * 5  # one row per alternative and method
    assert {r["context"] for r in rows} == {CONTEXT}
    for method in ("mavt", "promethee2", "ahp"):
        names = {r["quantity_name"] for r in rows if r["method"] == method}
        assert len(names) == 1  # every row names its own method's quantity
    assert {r["quantity_name"] for r in rows} == {
        "overall value",
        "rank-1 acceptability",
        "net flow",
        "AHP priority",
    }
    stale = export(client, "csv", "0" * 64)
    assert stale.status_code == 412 and errors(stale)["code"] == "STALE_REVISION"


def test_a_failed_method_has_one_csv_row_with_its_error(client: TestClient) -> None:
    request = {"project": dump(repo.load(QUALIFICATION))}
    fingerprint = client.post("/api/methods/compare", json=request).json()["project_fingerprint"]
    response = client.post(
        "/api/methods/compare/export",
        json={**request, "format": "csv", "expected_project_fingerprint": fingerprint},
    )
    rows = list(csv.DictReader(io.StringIO(response.text)))
    failed = [r for r in rows if r["status"] == "failed"]
    assert sorted(r["method"] for r in failed) == ["ahp", "promethee2", "smaa2"]
    assert all(r["error_code"] == "VALIDATION_FAILED" and r["alternative_id"] == "" for r in failed)


def test_the_cli_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "console", Console(width=200))
    path = tmp_path / "q.json"
    path.write_bytes(QUALIFICATION.read_bytes())
    out = tmp_path / "comparison.json"
    result = CliRunner().invoke(cli_app, ["compare-methods", str(path), "-o", str(out)])
    assert result.exit_code == 0, result.output
    text = " ".join(result.output.split())
    assert (
        "PROMETHEE II (outranking flows) did not run: VALIDATION_FAILED (PROMETHEE_NOT_STATED)"
        in text
    )
    assert "every method that ran puts Apex Components first" in text and CONTEXT in text
    assert json.loads(out.read_text())["methods"][0] == "mavt"
    path.write_text(to_json_text(every_section(repo.load(QUALIFICATION))))
    result = CliRunner().invoke(
        cli_app, ["compare-methods", str(path), "--method", "mavt", "--method", "smaa2"]
    )
    text = " ".join(result.output.split())
    assert result.exit_code == 0 and "first: Apex Components - mavt" in text and "smaa2:" in text
