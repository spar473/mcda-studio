"""AHP through the HTTP API and the CLI: the result union, version-2 records and exports, its CSV
tables, the read-only matrix preview, refusals of routes it does not support, edit operations and
schema version 5."""

import csv
import hashlib
import io
import itertools
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
from mcda_studio.domain.pairwise import (
    AhpModel,
    AlternativeJudgements,
    CriteriaJudgements,
    PairwiseJudgement,
)
from mcda_studio.domain.project import Project
from mcda_studio.methods.ahp import matrix
from mcda_studio.services import project_service as ps
from mcda_studio.services import results_service as results
from mcda_studio.storage.json_repository import to_json_text

from builders import tiny_project

LABEL = (
    "AHP priorities under these pairwise judgements: shares of the goal that sum to one, not MAVT "
    "values or swing weights"
)
AHP = {"method": "ahp", "weight_profile_id": None, "scenario_id": None, "parameters": {}}
ALTERNATIVES = ["apex", "brightline", "cobalt", "delta", "evergreen"]
LEAVES = [
    "unit_price",
    "logistics_cost",
    "defect_rate",
    "certification",
    "on_time",
    "lead_time",
    "financial_stability",
    "region",
]


def j(row: str, column: str, value: float) -> PairwiseJudgement:
    return PairwiseJudgement(row=row, column=column, value=value)


def judged(path: Path = SUPPLIER_FILE) -> Project:
    """The supplier example with every matrix judged; the unit-price matrix is inconsistent."""
    criteria = [
        CriteriaJudgements(
            parent_id=None,
            judgements=[
                j("cost", "performance", 2),
                j("cost", "risk", 4),
                j("performance", "risk", 2),
            ],
        ),
        *(
            CriteriaJudgements(parent_id=g, judgements=[j(a, b, v)])
            for g, a, b, v in [
                ("cost", "unit_price", "logistics_cost", 3),
                ("performance", "quality", "delivery", 1),
                ("quality", "defect_rate", "certification", 2),
                ("delivery", "on_time", "lead_time", 2),
                ("risk", "financial_stability", "region", 3),
            ]
        ),
    ]
    alternatives = []
    for k, leaf in enumerate(LEAVES):
        weights = [(1, 2, 3, 6, 2)[(i + k) % 5] for i in range(5)]  # consistent: exact ratios
        js = []
        for (i, a), (m, b) in itertools.combinations(enumerate(ALTERNATIVES), 2):
            if leaf == "unit_price":
                v = 1 + ((i * 3 + m * 5 + k) % 5)
                js.append(j(a, b, float(v)) if (i + m + k) % 2 else j(b, a, float(v)))
            else:
                hi, lo = (a, b) if weights[i] >= weights[m] else (b, a)
                js.append(j(hi, lo, max(weights[i], weights[m]) / min(weights[i], weights[m])))
        alternatives.append(AlternativeJudgements(criterion_id=leaf, judgements=js))
    return ps.set_ahp_model(repo.load(path), AhpModel(criteria=criteria, alternatives=alternatives))


def body(project: Project | None = None, **configuration: Any) -> dict[str, Any]:
    return {"project": dump(project or judged()), "configuration": {**AHP, **configuration}}


def flat(text: str) -> str:
    """CLI output with Rich's line wrapping undone, so a phrase matches at any terminal width."""
    return " ".join(text.split())


def test_evaluate_returns_priorities_under_the_label(client: TestClient) -> None:
    result = client.post("/api/evaluate", json=body()).json()
    assert result["method"] == "ahp" and result["schema_version"] == 5
    assert result["label"] == LABEL and result["synthesis"] == "distributive"
    assert result["weight_profile_id"] is None and result["scenario_id"] is None
    assert [(r["alternative_id"], r["value"]) for r in result["ranking"]] == [
        (a["alternative_id"], a["priority"]) for a in result["alternatives"]
    ]
    assert abs(sum(a["priority"] for a in result["alternatives"]) - 1) <= 1e-12
    assert len(result["matrices"]) == 6 + 8
    flagged = [m["group_id"] for m in result["matrices"] if m["inconsistent"]]
    assert flagged == ["unit_price"]
    assert [d["code"] for d in result["diagnostics"]] == ["AHP_INCONSISTENT"]
    ideal = client.post("/api/evaluate", json=body(parameters={"synthesis": "ideal"})).json()
    assert ideal["synthesis"] == "ideal" and all(a["ideal_score"] for a in ideal["alternatives"])


def test_a_version_2_record_round_trips_through_the_json_export(client: TestClient) -> None:
    record = client.post("/api/analysis/record", json=body()).json()
    assert record["record_version"] == "2" and record["method"] == "ahp"
    assert record["calculation_path"] == "ahp.eigen_power.v1"
    assert record["method_label"] == "AHP (pairwise priorities)"
    assert record["scenario_name"] == "" and record["resolved_profile_name"] == ""
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
    again = results.analysis_record(reread, reread.analysis.model_copy(update=AHP))
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


def test_the_four_tables_carry_the_label_and_no_value_column(client: TestClient) -> None:
    counts = {
        "priorities": 5,
        "criterion_priorities": 3 + 2 * 5,
        "local_priorities": 5 * 8,
        "consistency": 14,
    }
    for table, count in counts.items():
        response = csv_table(client, table, body())
        assert response.status_code == 200, response.text
        rows = list(csv.DictReader(io.StringIO(response.text)))
        assert len(rows) == count and {r["label"] for r in rows} == {LABEL}
        assert {r["method"] for r in rows} == {"ahp"} and {r["export_version"] for r in rows} == {
            "2"
        }
        columns = response.text.splitlines()[0].replace('"', "").split(",")
        assert not {"value", "overall_value", "score"} & set(columns)
    consistency = list(csv.DictReader(io.StringIO(csv_table(client, "consistency", body()).text)))
    unit_price = next(r for r in consistency if r["group_id"] == "unit_price")
    assert (
        unit_price["inconsistent"] == "true"
        and unit_price["random_index_table"] == "saaty-tran-2007"
    )
    assert unit_price["triad_items"].startswith("TEXT:[")  # the CSV text policy prefixes it
    assert len(json.loads(unit_price["triad_items"].removeprefix("TEXT:"))) == 3


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
def test_routes_ahp_does_not_support_are_refused_with_422(
    client: TestClient, route: str, extra: dict[str, Any]
) -> None:
    response = client.post(route, json={**body(), **extra})
    assert response.status_code == 422 and errors(response)["code"] == "METHOD_NOT_SUPPORTED"


def test_the_matrix_preview(client: TestClient) -> None:
    items = ["a", "b", "c"]
    partial = client.post("/api/ahp/preview", json={"items": items, "judgements": []}).json()
    assert partial["ready"] is False and partial["analysis"] is None
    assert [i["code"] for i in partial["issues"]] == ["AHP_JUDGEMENT_MISSING"]
    complete = client.post(
        "/api/ahp/preview",
        json={
            "items": items,
            "judgements": [
                {"row": "a", "column": "b", "value": 9},
                {"row": "c", "column": "a", "value": 3},
                {"row": "b", "column": "c", "value": 5},
            ],
        },
    ).json()
    assert complete["ready"] and complete["random_index_table"] == "saaty-tran-2007"
    analysis = complete["analysis"]
    assert analysis["inconsistent"] and analysis["most_inconsistent_triad"]["items"] == items
    sixteen = [f"x{k}" for k in range(16)]
    many = client.post("/api/ahp/preview", json={"items": sixteen, "judgements": []}).json()
    assert "AHP_TOO_MANY_ITEMS" in [i["code"] for i in many["issues"]]
    huge = client.post(
        "/api/ahp/preview", json={"items": [f"x{k}" for k in range(101)], "judgements": []}
    )
    assert huge.status_code == 422


def test_non_convergence_is_a_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(matrix, "MAX_ITERATIONS", 1)
    response = client.post("/api/evaluate", json=body())
    assert response.status_code == 422 and errors(response)["code"] == "AHP_NO_CONVERGENCE"


def test_edit_operations_move_a_project_between_schema_versions(client: TestClient) -> None:
    start = dump(repo.load(SUPPLIER_FILE))
    section = dump(judged())["ahp"]
    added = client.post(
        "/api/edit",
        json={"project": start, "operations": [{"op": "set_ahp_model", "ahp": section}]},
    ).json()["project"]
    assert added["schema_version"] == 5 and added["ahp"] == section
    cleared = client.post(
        "/api/edit", json={"project": added, "operations": [{"op": "clear_ahp_model"}]}
    ).json()["project"]
    assert cleared == start and cleared["schema_version"] == 1


def test_the_cli_judges_checks_runs_and_clears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "console", Console(width=160))
    monkeypatch.setattr(cli, "err_console", Console(stderr=True, width=160))
    path = tmp_path / "tiny.json"
    path.write_text(to_json_text(tiny_project()))
    start = path.read_bytes()
    f = str(path)
    runner = CliRunner()

    def run(*args: str, code: int = 0) -> str:
        result = runner.invoke(cli_app, list(args))
        assert result.exit_code == code, result.output
        return flat(result.output)

    run("ahp", "judge", f, "--top", "quality", "cost", "2")
    run("ahp", "judge", f, "--leaf", "cost", "a", "b", "3")
    assert "pairs not judged" in run("ahp", "check", f, code=1)
    run("ahp", "judge", f, "--leaf", "quality", "b", "a", "5")
    assert json.loads(path.read_text())["schema_version"] == 5
    out = run("ahp", "check", f)
    assert "criteria under top level" in out and "alternatives under cost" in out
    out = run("evaluate", f, "--method", "ahp")
    assert LABEL in out and "distributive synthesis; random index saaty-tran-2007" in out
    assert "AHP priority" in out
    out = run("evaluate", f, "--method", "ahp", "--synthesis", "ideal")
    assert "ideal synthesis" in out and "ideal score" in out
    assert "swap ROW and COLUMN and give 2 instead" in run(
        "ahp", "judge", f, "--leaf", "cost", "a", "b", "0.5", code=1
    )
    assert "exactly one of --top, --group PARENT or --leaf LEAF" in run(
        "ahp", "judge", f, "a", "b", "3", code=1
    )
    run("ahp", "judge", f, "--leaf", "cost", "b", "a", "4")  # replaces the pair, either way round
    model = json.loads(path.read_text())["ahp"]
    assert model["alternatives"][0]["judgements"] == [{"row": "b", "column": "a", "value": 4.0}]
    run("ahp", "remove", f, "--leaf", "quality", "a", "b")
    assert "AHP_JUDGEMENT_MISSING" in run("evaluate", f, "--method", "ahp", code=1)
    run("ahp", "clear", f)
    assert path.read_bytes() == start
