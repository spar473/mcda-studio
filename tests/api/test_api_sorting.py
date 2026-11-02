"""Value-based sorting through the HTTP API and the CLI: the result union, version-2 records and
exports, per-method CSV tables, sorting sensitivity, the edit operations and the schema rule."""

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
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import results_service as results
from mcda_studio.storage.json_repository import to_json_text

QUALIFICATION = EXAMPLES / "supplier_qualification" / "project.json"
SORTING = {"method": "mavt_sorting", "parameters": {}}


def flat(text: str) -> str:
    """CLI output with Rich's line wrapping undone, so a phrase matches at any terminal width."""
    return " ".join(text.split())


def body(path: Path = QUALIFICATION, **configuration: Any) -> dict[str, Any]:
    project = repo.load(path)
    cfg = {**project.analysis.model_dump(mode="json"), **configuration}
    return {"project": dump(project), "configuration": cfg}


def canonical_digest(record: dict[str, Any]) -> str:
    rest = {k: v for k, v in record.items() if k != "record_digest"}
    text = json.dumps(rest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---- the result union ----------------------------------------------------------------------------
def test_evaluate_returns_the_sorting_result_and_an_unchanged_mavt_body(client: TestClient) -> None:
    sorted_ = client.post("/api/evaluate", json=body()).json()
    assert sorted_["method"] == "mavt_sorting" and sorted_["schema_version"] == 2
    assert [c["class_id"] for c in sorted_["classes"]] == [
        "qualified",
        "conditional",
        "not_qualified",
    ]
    assert {"assignments", "audit_sample", "boundary_tolerance"} <= set(sorted_)
    mavt = client.post("/api/evaluate", json=body(SUPPLIER_FILE))
    expected = to_json_text(svc.evaluate_project(repo.load(SUPPLIER_FILE)))
    assert mavt.json() == json.loads(expected) and "classes" not in mavt.json()


def test_the_openapi_document_tags_the_result_union_and_lists_the_records(
    client: TestClient,
) -> None:
    spec = client.get("/openapi.json").json()
    evaluate = spec["paths"]["/api/evaluate"]["post"]["responses"]["200"]["content"]
    schema = evaluate["application/json"]["schema"]
    assert schema["discriminator"]["propertyName"] == "method"
    assert set(schema["discriminator"]["mapping"]) == {
        "mavt",
        "mavt_sorting",
        "smaa2",
        "promethee2",
        "ahp",
    }
    record = spec["paths"]["/api/analysis/record"]["post"]["responses"]["200"]["content"]
    refs = [r["$ref"].rsplit("/", 1)[1] for r in record["application/json"]["schema"]["oneOf"]]
    assert refs == [
        "AnalysisRecord",
        "SortingAnalysisRecord",
        "SmaaAnalysisRecord",
        "PrometheeAnalysisRecord",
        "AhpAnalysisRecord",
    ]


# ---- version-2 records and exports ---------------------------------------------------------------
def test_a_version_2_record_round_trips_through_the_json_export(client: TestClient) -> None:
    record = client.post("/api/analysis/record", json=body()).json()
    assert record["record_version"] == "2" and record["method"] == "mavt_sorting"
    assert record["method_label"] == "Value-based sorting (MAVT)"
    assert record["calculation_path"] == "mavt_sorting.math_fsum.v1"
    assert record["record_digest"] == canonical_digest(record)
    assert {"criteria", "path_shares", "contribution_totals", "dominance_relations"} <= set(record)
    exported = client.post(
        "/api/analysis/export",
        json={
            **body(),
            "format": "json",
            "expected_project_fingerprint": record["result"]["project_fingerprint"],
            "expected_record_digest": record["record_digest"],
        },
    )
    assert exported.status_code == 200
    document = exported.json()
    assert document["export_version"] == "2" and document["record"] == record
    reread = repo.from_dict(document["source_project"])
    again = results.analysis_record(reread, reread.analysis)
    assert again.record_digest == record["record_digest"]


def test_the_mavt_record_stays_version_1(client: TestClient) -> None:
    record = client.post("/api/analysis/record", json=body(QUALIFICATION, method="mavt"))
    assert record.status_code == 200 and record.json()["record_version"] == "1"
    assert "classes" not in record.json()["result"]


def export_csv(client: TestClient, table: str, request: dict[str, Any]) -> Any:
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


def test_sorting_csv_tables_carry_classes(client: TestClient) -> None:
    ranking = list(csv.DictReader(io.StringIO(export_csv(client, "ranking", body()).text)))
    assert [r["class_id"] for r in ranking] == [
        "qualified",
        "qualified",
        "conditional",
        "not_qualified",
        "not_qualified",
    ]
    assert {r["export_version"] for r in ranking} == {"2"}
    assert {r["calculation_path"] for r in ranking} == {"mavt_sorting.math_fsum.v1"}
    assert [r["in_audit_sample"] for r in ranking] == ["false", "false", "false", "false", "true"]
    classes = list(csv.DictReader(io.StringIO(export_csv(client, "classes", body()).text)))
    assert [(r["class_id"], r["member_count"], r["in_audit_pool"]) for r in classes] == [
        ("qualified", "2", "false"),
        ("conditional", "1", "false"),
        ("not_qualified", "2", "true"),
    ]
    assert classes[0]["member_ids"] == 'TEXT:["apex","delta"]'  # the CSV text policy
    for table in ("contributions", "partial_values", "dominance"):
        assert export_csv(client, table, body()).status_code == 200


def test_a_table_the_method_does_not_declare_is_refused(client: TestClient) -> None:
    refused = export_csv(client, "classes", body(SUPPLIER_FILE))
    assert refused.status_code == 422
    assert errors(refused)["code"] == "EXPORT_UNAVAILABLE"
    assert "does not export a 'classes' table" in errors(refused)["message"]


# ---- sensitivity ---------------------------------------------------------------------------------
def test_sorting_sensitivity_and_probe_add_classes_and_mavt_bodies_do_not(
    client: TestClient,
) -> None:
    sweep = client.post("/api/sensitivity", json={**body(), "node_id": "cost"}).json()
    assert sweep["method"] == "mavt_sorting" and len(sweep["class_changes"]) == 5
    assert {c["alternative_id"] for c in sweep["class_changes"]} == {
        "apex",
        "brightline",
        "cobalt",
        "delta",
        "evergreen",
    }
    probe = client.post(
        "/api/sensitivity/probe", json={**body(), "node_id": "cost", "weight": 0.3}
    ).json()
    assert set(probe["class_by_alternative"]) == set(probe["baseline_class_by_alternative"])
    plain = body(QUALIFICATION, method="mavt")
    mavt_sweep = client.post("/api/sensitivity", json={**plain, "node_id": "cost"}).json()
    mavt_probe = client.post(
        "/api/sensitivity/probe", json={**plain, "node_id": "cost", "weight": 0.3}
    ).json()
    assert not {"method", "classes", "class_changes"} & set(mavt_sweep)
    assert not {"method", "class_by_alternative"} & set(mavt_probe)
    for key in mavt_sweep:  # every MAVT field is the same under sorting
        if key not in {"diagnostics"}:
            assert sweep[key] == mavt_sweep[key], key


# ---- edit operations and the schema rule ---------------------------------------------------------
def test_editing_classes_moves_a_project_between_schema_versions(client: TestClient) -> None:
    start = dump(repo.load(SUPPLIER_FILE))
    classes = {
        "classes": [
            {"id": "go", "name": "Go", "lower_boundary": 0.6},
            {"id": "stop", "name": "Stop"},
        ]
    }
    added = client.post(
        "/api/edit",
        json={"project": start, "operations": [{"op": "set_sorting_model", "sorting": classes}]},
    ).json()["project"]
    assert added["schema_version"] == 2 and added["sorting"]["classes"][1]["lower_boundary"] is None
    cleared = client.post(
        "/api/edit", json={"project": added, "operations": [{"op": "clear_sorting_model"}]}
    ).json()["project"]
    assert cleared == start and "sorting" not in cleared


def test_the_saved_method_operation_clears_parameters_and_refuses_unknown_methods(
    client: TestClient,
) -> None:
    project = dump(repo.load(SUPPLIER_FILE))
    project["analysis"]["parameters"] = {"dominance_check": False}
    moved = client.post(
        "/api/edit",
        json={
            "project": project,
            "operations": [{"op": "set_analysis_method", "method": "mavt_sorting"}],
        },
    ).json()["project"]
    assert moved["analysis"] == {**project["analysis"], "method": "mavt_sorting", "parameters": {}}
    unknown = client.post(
        "/api/edit",
        json={"project": project, "operations": [{"op": "set_analysis_method", "method": "nope"}]},
    )
    assert unknown.status_code >= 400 and "unknown MCDA method" in unknown.text


def test_a_stored_sorting_project_saves_and_reloads_as_version_2(
    client: TestClient, store_dir: Path
) -> None:
    created = client.post("/api/projects/import", json=json.loads(QUALIFICATION.read_text()))
    assert created.status_code == 201
    pid = created.json()["project"]["id"]
    assert (store_dir / f"{pid}.json").read_bytes() == QUALIFICATION.read_bytes()
    stored = client.post(f"/api/projects/{pid}/evaluate", json={}).json()
    assert stored["method"] == "mavt_sorting"


# ---- CLI -----------------------------------------------------------------------------------------
def test_the_cli_sets_audits_views_and_clears_classes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Tables at a fixed width: a narrow terminal truncates cells, which no text matching undoes.
    monkeypatch.setattr(cli, "console", Console(width=160))
    monkeypatch.setattr(cli, "err_console", Console(stderr=True, width=160))
    runner = CliRunner()
    path = tmp_path / "s.json"
    path.write_bytes(SUPPLIER_FILE.read_bytes())
    f = str(path)

    def run(*args: str, code: int = 0) -> str:
        result = runner.invoke(cli_app, list(args))
        assert result.exit_code == code, result.output
        return flat(result.output)

    run(
        "classes",
        "set",
        f,
        "--class",
        "Qualified=0.70",
        "--class",
        "Conditional=0.60",
        "--class",
        "Not qualified",
    )
    run("classes", "audit", f, "--below", "conditional", "--size", "1", "--seed", "2026")
    assert json.loads(path.read_text())["schema_version"] == 2
    out = run("evaluate", f, "--method", "mavt_sorting")
    assert "Not qualified" in out and "audit sample below Conditional (1 of 2, seed 2026)" in out
    out = run("sensitivity", f, "--criterion", "cost", "--method", "mavt_sorting")
    assert "first change up" in out and "Conditional @" in out
    # lowering a weight past a change leads to the class below it, not the one above
    out = run("sensitivity", str(QUALIFICATION), "--criterion", "performance")
    assert "apex │ Qualified │ - │ Conditional @ 0.2039" in out
    assert "class" not in run("evaluate", f)  # the saved method is still MAVT
    run("method", f, "mavt_sorting")
    assert "valid" in run("validate", f)
    run("classes", "set", f, "--class", "A=0.5", "--class", "B=0.6", "--class", "C")
    out = run("validate", f, code=1)
    assert "BOUNDARIES_NOT_DECREASING" in out and "UNKNOWN_AUDIT_CLASS" in out
    run("classes", "audit", f, "--off")
    run("classes", "clear", f)
    run("method", f, "mavt")
    assert path.read_bytes() == SUPPLIER_FILE.read_bytes()
    assert "must be a number" in run("classes", "set", f, "--class", "Bad=x", code=1)
