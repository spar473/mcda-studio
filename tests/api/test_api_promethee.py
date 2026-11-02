"""PROMETHEE II through the HTTP API and the CLI: the result union, version-2 records and exports,
its CSV tables, refusals of routes it does not support, edit operations and schema version 4."""

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pytest
from conftest import SUPPLIER_FILE, dump, errors, repo
from fastapi.testclient import TestClient
from rich.console import Console
from typer.testing import CliRunner

from mcda_studio import cli
from mcda_studio.cli import app as cli_app
from mcda_studio.domain.outranking import (
    LinearPreferenceFunction,
    PrometheeCriterion,
    PrometheeModel,
    UShapeFunction,
    UsualFunction,
    VShapeFunction,
)
from mcda_studio.domain.project import Project
from mcda_studio.services import project_service as ps
from mcda_studio.services import results_service as results

LABEL = (
    "net outranking flows: these compare the alternatives with one another and are not "
    "preference values"
)
PROMETHEE = {
    "method": "promethee2",
    "weight_profile_id": None,
    "scenario_id": None,
    "parameters": {},
}
LEVELS = {"none": 0.0, "iso9001": 1.0, "iso9001_14001": 2.0}
REGIONS = {"overseas": 0.0, "regional": 1.0, "domestic": 2.0}


def stated(path: Path = SUPPLIER_FILE) -> Project:
    """The supplier example with PROMETHEE inputs on every leaf; on-time delivery under the usual
    function weighs enough that two pairs are ordered differently from MAVT."""

    def c(criterion: str, direction: str, weight: float, function: Any, coding: Any = None) -> Any:
        return PrometheeCriterion(
            criterion_id=criterion,
            direction=direction,  # type: ignore[arg-type]
            weight=weight,
            function=function,
            coding=coding,
        )

    model = PrometheeModel(
        criteria=[
            c("unit_price", "minimise", 1.0, LinearPreferenceFunction(q=2.0, p=4.0)),
            c("logistics_cost", "minimise", 1.0, VShapeFunction(p=3.0)),
            c("defect_rate", "minimise", 2.0, UShapeFunction(q=0.5)),
            c("certification", "maximise", 1.0, UsualFunction(), LEVELS),
            c("on_time", "maximise", 4.0, UsualFunction()),
            c("lead_time", "minimise", 1.0, LinearPreferenceFunction(q=2.0, p=10.0)),
            c("financial_stability", "maximise", 1.0, UsualFunction()),
            c("region", "maximise", 1.0, UsualFunction(), REGIONS),
        ]
    )
    return ps.set_promethee_model(repo.load(path), model)


def body(project: Project | None = None, **configuration: Any) -> dict[str, Any]:
    return {"project": dump(project or stated()), "configuration": {**PROMETHEE, **configuration}}


def flat(text: str) -> str:
    """CLI output with Rich's line wrapping undone, so a phrase matches at any terminal width."""
    return " ".join(text.split())


def test_evaluate_returns_flows_under_the_label(client: TestClient) -> None:
    result = client.post("/api/evaluate", json=body()).json()
    assert result["method"] == "promethee2" and result["schema_version"] == 4
    assert result["label"] == LABEL
    flows = result["flows"]
    assert [f["rank"] for f in flows] == [1, 2, 3, 4, 5]
    assert abs(sum(f["net_flow"] for f in flows)) <= 5e-12
    assert [(r["alternative_id"], r["value"]) for r in result["ranking"]] == [
        (f["alternative_id"], f["net_flow"]) for f in flows
    ]
    explanation = result["explanation"]
    assert explanation["available"] and len(explanation["pairs"]) == 2
    assert all(pair["reasons"] for pair in explanation["pairs"])


def test_a_version_2_record_round_trips_through_the_json_export(client: TestClient) -> None:
    record = client.post("/api/analysis/record", json=body()).json()
    assert record["record_version"] == "2" and record["method"] == "promethee2"
    assert record["calculation_path"] == "promethee2.v1"
    assert record["method_label"] == "PROMETHEE II (outranking flows)"
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
    again = results.analysis_record(reread, reread.analysis.model_copy(update=PROMETHEE))
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


def rows(client: TestClient, table: str, request: dict[str, Any] | None = None) -> list[Any]:
    response = csv_table(client, table, request or body())
    assert response.status_code == 200, response.text
    return list(csv.DictReader(io.StringIO(response.text)))


def test_the_four_tables_carry_the_label_and_no_value_column(client: TestClient) -> None:
    flows = rows(client, "flows")
    assert len(flows) == 5 and {r["label"] for r in flows} == {LABEL}
    assert {r["method"] for r in flows} == {"promethee2"} and {
        r["export_version"] for r in flows
    } == {"2"}
    for table, count in (("criterion_flows", 5 * 8), ("partial_order", 10)):
        listed = rows(client, table)
        assert len(listed) == count and {r["label"] for r in listed} == {LABEL}
    explanation = rows(client, "explanation")
    assert len(explanation) == 2 * 8 and {r["label"] for r in explanation} == {LABEL}
    for table in ("flows", "criterion_flows", "partial_order", "explanation"):
        header = csv_table(client, table, body()).text.splitlines()[0]
        columns = [c.strip('"') for c in header.split(",")]
        assert "value" not in columns and "overall_value" not in columns and "score" not in columns


def test_the_explanation_table_is_refused_when_mavt_is_unavailable(client: TestClient) -> None:
    broken = stated()
    broken = ps.set_value_function(broken, "unit_price", None)  # type: ignore[arg-type]
    response = csv_table(client, "explanation", body(broken))
    assert response.status_code == 422 and errors(response)["code"] == "EXPORT_UNAVAILABLE"
    assert "no explanation against MAVT" in response.text
    assert csv_table(client, "flows", body(broken)).status_code == 200
    mavt_table = csv_table(client, "ranking", body())
    assert mavt_table.status_code == 422 and "does not export a 'ranking' table" in mavt_table.text


@pytest.mark.parametrize(
    ("route", "extra"),
    [
        ("/api/sensitivity", {"node_id": "cost"}),
        ("/api/sensitivity/probe", {"node_id": "cost", "weight": 0.3}),
        ("/api/scenarios/compare", {}),
        ("/api/weights/preview", {}),
        ("/api/value-functions/preview", {"criterion_id": "unit_price"}),
    ],
)
def test_routes_promethee_does_not_support_are_refused_with_422(
    client: TestClient, route: str, extra: dict[str, Any]
) -> None:
    response = client.post(route, json={**body(), **extra})
    assert response.status_code == 422 and errors(response)["code"] == "METHOD_NOT_SUPPORTED"


def test_mavt_previews_of_the_same_project_are_served(client: TestClient) -> None:
    mavt = {"method": "mavt"}
    assert client.post("/api/weights/preview", json=body(**mavt)).status_code == 200
    preview = client.post(
        "/api/value-functions/preview", json={**body(**mavt), "criterion_id": "unit_price"}
    )
    assert preview.status_code == 200


def test_analysis_validation_reports_the_section_rules(client: TestClient) -> None:
    project = ps.clear_promethee_model(stated())
    report = client.post("/api/analysis/validate", json=body(project)).json()
    assert [i["code"] for i in report["validation"]["issues"]] == ["PROMETHEE_NOT_STATED"]
    failed = client.post("/api/evaluate", json=body(project))
    assert failed.status_code == 422 and errors(failed)["code"] == "VALIDATION_FAILED"


def test_edit_operations_move_a_project_between_schema_versions(client: TestClient) -> None:
    start = dump(repo.load(SUPPLIER_FILE))
    section = dump(stated())["promethee"]
    added = client.post(
        "/api/edit",
        json={
            "project": start,
            "operations": [{"op": "set_promethee_model", "promethee": section}],
        },
    ).json()["project"]
    assert added["schema_version"] == 4 and added["promethee"] == section
    assert "coding" not in added["promethee"]["criteria"][0]
    cleared = client.post(
        "/api/edit", json={"project": added, "operations": [{"op": "clear_promethee_model"}]}
    ).json()["project"]
    assert cleared == start and cleared["schema_version"] == 1


def test_the_cli_states_runs_explains_and_clears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "console", Console(width=160))
    monkeypatch.setattr(cli, "err_console", Console(stderr=True, width=160))
    path = tmp_path / "s.json"
    path.write_bytes(SUPPLIER_FILE.read_bytes())
    f = str(path)
    runner = CliRunner()

    def run(*args: str, code: int = 0) -> str:
        result = runner.invoke(cli_app, list(args))
        assert result.exit_code == code, result.output
        return flat(result.output)

    criterion = ("promethee", "criterion", f)
    run(*criterion, "unit_price", "--minimise", "--weight", "1", "--linear", "2", "4")
    run(*criterion, "logistics_cost", "--minimise", "--weight", "1", "--v-shape", "3")
    run(*criterion, "defect_rate", "--minimise", "--weight", "2", "--u-shape", "0.5")
    run(
        *criterion,
        "certification",
        "--maximise",
        "--weight",
        "1",
        "--code",
        "none=0",
        "--code",
        "iso9001=1",
        "--code",
        "iso9001_14001=2",
    )
    run(*criterion, "on_time", "--maximise", "--weight", "4")
    run(*criterion, "lead_time", "--minimise", "--weight", "1", "--linear", "2", "10")
    run(*criterion, "financial_stability", "--maximise", "--weight", "1", "--usual")
    run(
        *criterion,
        "region",
        "--maximise",
        "--weight",
        "1",
        "--code",
        "overseas=0",
        "--code",
        "regional=1",
        "--code",
        "domestic=2",
    )
    assert json.loads(path.read_text())["schema_version"] == 4
    assert repo.load(path).promethee == stated().promethee
    out = run("evaluate", f, "--method", "promethee2")
    assert LABEL in out and "net flow" in out and "PROMETHEE I incomparable pairs:" in out
    assert "MAVT rank" in out and "head-to-head" in out and "via others" in out
    assert "the usual function counts any difference as full preference" in out
    assert "give exactly one of --maximise or --minimise" in run(
        *criterion, "unit_price", "--weight", "1", code=1
    )
    assert "give at most one of" in run(
        *criterion, "unit_price", "--maximise", "--weight", "1", "--usual", "--v-shape", "2", code=1
    )
    assert "LABEL=NUMBER" in run(
        *criterion, "region", "--maximise", "--weight", "1", "--code", "domestic", code=1
    )
    run("promethee", "remove", f, "region")
    out = run("evaluate", f, "--method", "promethee2", code=1)
    assert "PROMETHEE_CRITERION_MISSING" in out
    run("promethee", "clear", f)
    assert path.read_bytes() == SUPPLIER_FILE.read_bytes()
