"""SMAA-2 through the HTTP API and the CLI: the result union, version-2 records and exports, its
CSV tables, refusals of routes it does not support, edit operations and schema version 3."""

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pytest
from conftest import EXAMPLES, SUPPLIER_FILE, dump, errors, repo
from fastapi.testclient import TestClient
from rich.console import Console
from typer.testing import CliRunner

from mcda_studio import cli
from mcda_studio.cli import app as cli_app
from mcda_studio.domain.project import Project
from mcda_studio.domain.uncertainty import (
    CellUncertainty,
    GroupUncertainty,
    SmaaModel,
    UniformDistribution,
)
from mcda_studio.services import project_service as ps
from mcda_studio.services import results_service as results

QUALIFICATION = EXAMPLES / "supplier_qualification" / "project.json"
SMAA = {
    "method": "smaa2",
    "weight_profile_id": None,
    "scenario_id": None,
    "parameters": {"samples": 2000, "seed": 1},
}


def flat(text: str) -> str:
    """CLI output with Rich's line wrapping undone, so a phrase matches at any terminal width."""
    return " ".join(text.split())


def uncertain(path: Path = QUALIFICATION) -> Project:
    model = SmaaModel(
        cells=[
            CellUncertainty(
                alternative_id="apex",
                criterion_id="unit_price",
                distribution=UniformDistribution(lower=38.0, upper=46.0),
            )
        ],
        groups=[GroupUncertainty(parent_id=None, kind="unknown")],
    )
    return ps.set_smaa_model(repo.load(path), model)


def body(project: Project | None = None, **configuration: Any) -> dict[str, Any]:
    return {"project": dump(project or uncertain()), "configuration": {**SMAA, **configuration}}


def test_evaluate_returns_acceptabilities_with_the_label(client: TestClient) -> None:
    result = client.post("/api/evaluate", json=body()).json()
    assert result["method"] == "smaa2" and result["schema_version"] == 3
    assert result["label"] == "sampled acceptability under these assumptions"
    assert result["samples"] == 2000 and result["seed"] == 1
    assert [a["alternative_id"] for a in result["acceptability"]] == [
        "apex",
        "brightline",
        "cobalt",
        "delta",
        "evergreen",
    ]
    assert [c["class_id"] for c in result["classes"]] == [
        "qualified",
        "conditional",
        "not_qualified",
    ]


def test_a_version_2_record_round_trips_through_the_json_export(client: TestClient) -> None:
    record = client.post("/api/analysis/record", json=body()).json()
    assert record["record_version"] == "2" and record["method"] == "smaa2"
    assert record["calculation_path"] == "smaa2.pcg64.v1"
    assert "criteria" not in record and "dominance_relations" not in record  # no MAVT context
    rest = {k: v for k, v in record.items() if k != "record_digest"}
    text = json.dumps(rest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert record["record_digest"] == hashlib.sha256(text.encode()).hexdigest()
    options = {
        "expected_project_fingerprint": record["result"]["project_fingerprint"],
        "expected_record_digest": record["record_digest"],
    }
    document = client.post(
        "/api/analysis/export", json={**body(), **options, "format": "json"}
    ).json()
    assert document["export_version"] == "2" and document["record"] == record
    reread = repo.from_dict(document["source_project"])
    again = results.analysis_record(reread, reread.analysis.model_copy(update=SMAA))
    assert again.record_digest == record["record_digest"]


def csv_table(client: TestClient, table: str, request: dict[str, Any]) -> Any:
    record = client.post("/api/analysis/record", json=request).json()
    return client.post(
        "/api/analysis/export",
        json={
            **request,
            "format": "csv",
            "table": table,
            "expected_project_fingerprint": record["result"]["project_fingerprint"],
            "expected_record_digest": record["record_digest"],
        },
    )


def test_the_three_smaa_tables(client: TestClient) -> None:
    rows = list(csv.DictReader(io.StringIO(csv_table(client, "rank_acceptability", body()).text)))
    assert len(rows) == 5 * (5 + 2)  # every rank, then sole and tied first, per alternative
    assert {r["export_version"] for r in rows} == {"2"} and {r["method"] for r in rows} == {"smaa2"}
    apex = [r for r in rows if r["alternative_id"] == "apex" and r["event"] == "rank"]
    assert sum(int(r["count"]) for r in apex) == 2000
    classes = list(
        csv.DictReader(io.StringIO(csv_table(client, "class_acceptability", body()).text))
    )
    assert len(classes) == 5 * 3
    inputs = list(csv.DictReader(io.StringIO(csv_table(client, "inputs_to_check", body()).text)))
    assert inputs and inputs[0]["label"].startswith("heuristic")


def test_tables_the_run_cannot_fill_are_refused(client: TestClient) -> None:
    no_classes = csv_table(client, "class_acceptability", body(uncertain(SUPPLIER_FILE)))
    assert no_classes.status_code == 422 and errors(no_classes)["code"] == "EXPORT_UNAVAILABLE"
    mavt_table = csv_table(client, "ranking", body())
    assert mavt_table.status_code == 422 and "does not export a 'ranking' table" in mavt_table.text


@pytest.mark.parametrize(
    ("route", "extra"),
    [
        ("/api/sensitivity", {"node_id": "cost"}),
        ("/api/sensitivity/probe", {"node_id": "cost", "weight": 0.3}),
        ("/api/scenarios/compare", {}),
    ],
)
def test_routes_smaa_does_not_support_are_refused_with_422(
    client: TestClient, route: str, extra: dict[str, Any]
) -> None:
    response = client.post(route, json={**body(), **extra})
    assert response.status_code == 422 and errors(response)["code"] == "METHOD_NOT_SUPPORTED"


def test_previews_stay_available(client: TestClient) -> None:
    assert client.post("/api/weights/preview", json=body()).status_code == 200
    preview = client.post(
        "/api/value-functions/preview", json={**body(), "criterion_id": "unit_price"}
    )
    assert preview.status_code == 200


def test_edit_operations_move_a_project_between_schema_versions(client: TestClient) -> None:
    start = dump(repo.load(QUALIFICATION))
    section = dump(uncertain())["smaa"]
    added = client.post(
        "/api/edit",
        json={"project": start, "operations": [{"op": "set_smaa_model", "smaa": section}]},
    ).json()["project"]
    assert added["schema_version"] == 3 and added["smaa"] == section
    cleared = client.post(
        "/api/edit", json={"project": added, "operations": [{"op": "clear_smaa_model"}]}
    ).json()["project"]
    assert cleared == start and cleared["schema_version"] == 2  # the classes still need version 2


def test_the_cli_states_runs_and_clears_uncertainty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "console", Console(width=160))
    monkeypatch.setattr(cli, "err_console", Console(stderr=True, width=160))
    path = tmp_path / "q.json"
    path.write_bytes(QUALIFICATION.read_bytes())
    f = str(path)
    runner = CliRunner()

    def run(*args: str, code: int = 0) -> str:
        result = runner.invoke(cli_app, list(args))
        assert result.exit_code == code, result.output
        return flat(result.output)

    run("uncertainty", "cell", f, "apex", "unit_price", "--uniform", "38", "46")
    run(
        "uncertainty",
        "cell",
        f,
        "delta",
        "certification",
        "--categorical",
        "iso9001=0.2,iso9001_14001=0.8",
    )
    run(
        "uncertainty",
        "group",
        f,
        "--interval",
        "cost=80:120",
        "--interval",
        "performance=70:110",
        "--interval",
        "risk=40:60",
    )
    run("uncertainty", "cell", f, "brightline", "on_time", "--discrete", "91=0.6,99=0.4")
    run("uncertainty", "cell", f, "evergreen", "on_time", "--uniform", "85", "92")
    run(
        "uncertainty",
        "share",
        f,
        "carrier",
        "--cell",
        "brightline:on_time",
        "--cell",
        "evergreen:on_time",
    )
    assert json.loads(path.read_text())["schema_version"] == 3
    out = run("evaluate", f, "--method", "smaa2", "--samples", "2000", "--seed", "7")
    assert "sampled acceptability under these assumptions (combined run; 2000 draws, seed 7" in out
    assert "inputs to check (heuristic" in out and "Qualified" in out
    out = run(
        "evaluate", f, "--method", "smaa2", "--uncertainty", "preference", "--samples", "1000"
    )
    assert "(preference run; 1000 draws" in out
    assert "must be a number" not in run("uncertainty", "cell", f, "apex", "unit_price", "--remove")
    assert "OUTCOME=PROBABILITY" in run(
        "uncertainty", "cell", f, "apex", "unit_price", "--discrete", "40", code=1
    )
    run("uncertainty", "group", f, "--fixed")
    run("uncertainty", "clear", f)
    assert path.read_bytes() == QUALIFICATION.read_bytes()
