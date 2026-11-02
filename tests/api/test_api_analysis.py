"""Validation and evaluation through HTTP must equal the engine called directly, to the last bit.

The API adds no arithmetic, so the strongest test is equality of the *parsed JSON response* with
the in-process result (floats round-trip exactly through JSON), and equality with the CLI's
output file for the same project.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import SUPPLIER_FILE, VC_FILE, dump, errors, import_file, repo
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from mcda_studio.cli import app as cli_app
from mcda_studio.domain.criteria import LinearValueFunction
from mcda_studio.domain.results import MavtResult, ScenarioComparison, SensitivityResult
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.domain.validation import ValidationReport
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps

VC = repo.load(VC_FILE)
SUPPLIER = repo.load(SUPPLIER_FILE)
PRINTED_BASE = {  # reference report, rounded to the printed three decimals
    "forever_harvest": 0.723,
    "outlier_space": 0.660,
    "kura_dynamics": 0.599,
    "hyades": 0.573,
}


# ---- validation -------------------------------------------------------------------------------
@pytest.mark.parametrize("project", [VC, SUPPLIER], ids=["vc", "supplier"])
def test_validation_endpoints_equal_the_service(client: TestClient, project: Any) -> None:
    direct = svc.validate(project)
    draft = client.post("/api/validate", json={"project": dump(project)})
    assert draft.status_code == 200
    assert ValidationReport.model_validate(draft.json()) == direct
    import_file(client, SUPPLIER_FILE if project is SUPPLIER else VC_FILE)
    stored = client.get(f"/api/projects/{project.id}/validation")
    assert ValidationReport.model_validate(stored.json()) == direct


def test_validation_reports_problems_with_paths_one_layer_at_a_time(client: TestClient) -> None:
    """A leaf without a scale reports only that (no cascade of consequences); fixing it reveals
    the next gap, so the editor can lead the user through completing a criterion."""

    def codes(project: Any) -> set[tuple[str, str]]:
        body = client.post("/api/validate", json={"project": dump(project)}).json()
        return {(i["code"], i["path"]) for i in body["issues"] if i["severity"] == "error"}

    p = ps.add_criterion(
        ps.add_alternative(ps.new_project("Half done"), "A"), "Cost", crit_id="cost"
    )
    assert codes(p) == {("MISSING_SCALE", "criteria[cost]")}
    p = ps.set_scale(p, "cost", Scale(type=ScaleType.RATIO, lower=0, upper=10))
    assert codes(p) == {("MISSING_VALUE_FUNCTION", "criteria[cost]")}
    p = ps.set_value_function(p, "cost", LinearValueFunction())
    assert codes(p) == {("MISSING_MEASUREMENT", "performances[a,cost]")}
    p = ps.set_performance(p, p.alternatives[0].id, "cost", 3.0)
    assert codes(p) == set()


# ---- evaluation: identical to the engine ---------------------------------------------------------
def test_evaluate_stored_project_is_bit_identical_to_the_engine(client: TestClient) -> None:
    import_file(client, VC_FILE)
    resp = client.post(f"/api/projects/{VC.id}/evaluate", json={})
    assert resp.status_code == 200
    via_http = MavtResult.model_validate(resp.json())
    assert via_http == svc.evaluate_project(VC)  # exact float equality, every field
    assert via_http.project_fingerprint == VC.fingerprint()


def test_evaluate_draft_equals_evaluate_stored(client: TestClient) -> None:
    import_file(client, VC_FILE)
    stored = client.post(f"/api/projects/{VC.id}/evaluate", json={}).json()
    draft = client.post("/api/evaluate", json={"project": dump(VC)}).json()
    assert draft == stored


def test_vc_reference_scores_through_the_api(client: TestClient) -> None:
    resp = client.post("/api/evaluate", json={"project": dump(VC)})
    result = MavtResult.model_validate(resp.json())
    scores = {r.alternative_id: r.value for r in result.ranking}
    for alt, printed in PRINTED_BASE.items():
        assert round(scores[alt], 3) == printed, alt
    assert [r.alternative_id for r in result.ranking] == [
        "forever_harvest",
        "outlier_space",
        "kura_dynamics",
        "hyades",
    ]
    assert sum(result.global_weights.values()) == pytest.approx(1.0, abs=1e-12)


def test_scenario_selection_through_the_api(client: TestClient) -> None:
    resp = client.post(
        "/api/evaluate",
        json={"project": dump(VC), "configuration": {"scenario_id": "linear_market_size"}},
    )
    assert resp.status_code == 200
    result = MavtResult.model_validate(resp.json())
    assert result.scenario_id == "linear_market_size"
    values = {r.alternative_id: r.value for r in result.ranking}
    assert round(values["outlier_space"], 3) == 0.652
    assert round(values["hyades"], 3) == 0.573
    assert round(values["kura_dynamics"], 3) == 0.556
    assert [r.alternative_id for r in result.ranking][2] == "hyades"  # Hyades overtakes Kura
    direct = svc.evaluate_project(
        VC, VC.analysis.model_copy(update={"scenario_id": "linear_market_size"})
    )
    assert result == direct


def test_api_result_equals_the_cli_result_file(client: TestClient, tmp_path: Path) -> None:
    out = tmp_path / "cli_result.json"
    run = CliRunner().invoke(cli_app, ["evaluate", str(SUPPLIER_FILE), "-o", str(out)])
    assert run.exit_code == 0, run.output
    cli_result = MavtResult.model_validate_json(out.read_text(encoding="utf-8"))
    api = client.post("/api/evaluate", json={"project": dump(SUPPLIER)})
    assert MavtResult.model_validate(api.json()) == cli_result


def test_evaluation_is_deterministic_across_repeated_calls(client: TestClient) -> None:
    bodies = {client.post("/api/evaluate", json={"project": dump(SUPPLIER)}).text for _ in range(5)}
    assert len(bodies) == 1


def test_evaluating_an_invalid_project_is_refused_with_every_error(client: TestClient) -> None:
    p = ps.add_alternative(ps.add_alternative(ps.new_project("Broken"), "A"), "B")
    p = ps.add_criterion(p, "Cost", crit_id="cost")
    p = ps.add_criterion(p, "Quality", crit_id="quality")
    p = ps.set_scale(p, "quality", Scale(type=ScaleType.RATIO, lower=0, upper=10))
    resp = client.post("/api/evaluate", json={"project": dump(p)})
    assert resp.status_code == 422
    err = errors(resp)
    assert err["code"] == "VALIDATION_FAILED"
    found = {(d["code"], d["path"]) for d in err["details"]}
    assert ("MISSING_SCALE", "criteria[cost]") in found
    assert ("MISSING_VALUE_FUNCTION", "criteria[quality]") in found
    assert all(d["severity"] == "error" for d in err["details"])


def test_an_unknown_scenario_or_profile_is_reported_as_a_validation_failure(
    client: TestClient,
) -> None:
    for cfg, code in (
        ({"scenario_id": "nope"}, "UNKNOWN_SCENARIO"),
        ({"weight_profile_id": "nope"}, "UNKNOWN_PROFILE"),
    ):
        resp = client.post("/api/evaluate", json={"project": dump(SUPPLIER), "configuration": cfg})
        assert resp.status_code == 422
        assert code in {d["code"] for d in errors(resp)["details"]}


def test_an_unknown_method_is_refused(client: TestClient) -> None:
    resp = client.post(
        "/api/evaluate", json={"project": dump(SUPPLIER), "configuration": {"method": "topsis"}}
    )
    assert resp.status_code == 422
    assert errors(resp)["code"] == "UNKNOWN_REFERENCE"


def test_evaluating_a_missing_stored_project_is_404(client: TestClient) -> None:
    assert client.post("/api/projects/missing/evaluate", json={}).status_code == 404


# ---- sensitivity -------------------------------------------------------------------------------
@pytest.mark.parametrize("node", ["team", "market", "market_size"])
def test_sensitivity_equals_the_engine_and_reproduces_the_report_crossovers(
    client: TestClient, node: str
) -> None:
    resp = client.post("/api/sensitivity", json={"project": dump(VC), "node_id": node})
    assert resp.status_code == 200
    via_http = SensitivityResult.model_validate(resp.json())
    assert via_http == svc.sensitivity(VC, node)
    change = via_http.first_winner_change_up
    assert change is not None
    printed = {"team": 0.569, "market": 0.674, "market_size": 0.873}[node]
    assert round(change.weight, 3) == printed


def test_sensitivity_on_a_stored_project_and_step_bounds(client: TestClient) -> None:
    import_file(client, VC_FILE)
    ok = client.post(f"/api/projects/{VC.id}/sensitivity", json={"node_id": "market", "steps": 11})
    assert ok.status_code == 200 and len(ok.json()["grid"]) >= 11
    for steps in (1, 1002):
        bad = client.post(
            f"/api/projects/{VC.id}/sensitivity", json={"node_id": "market", "steps": steps}
        )
        assert bad.status_code == 422 and errors(bad)["code"] == "INVALID_REQUEST"


def test_sensitivity_that_is_mathematically_undefined_is_a_clear_422(client: TestClient) -> None:
    p = ps.new_project("Single")
    for name in ("A", "B"):
        p = ps.add_alternative(p, name)
    p = ps.add_criterion(
        p,
        "Only",
        crit_id="only",
        scale=Scale(type=ScaleType.INTERVAL, lower=0, upper=1),
        value_function=LinearValueFunction(),
    )
    for alt, v in (("a", 0.2), ("b", 0.8)):
        p = ps.set_performance(p, alt, "only", v)
    resp = client.post("/api/sensitivity", json={"project": dump(p), "node_id": "only"})
    assert resp.status_code == 422
    assert errors(resp)["code"] == "SENSITIVITY_UNDEFINED"
    unknown = client.post("/api/sensitivity", json={"project": dump(SUPPLIER), "node_id": "ghost"})
    assert unknown.status_code == 422 and errors(unknown)["code"] == "SENSITIVITY_UNDEFINED"


# ---- scenarios -----------------------------------------------------------------------------------
def test_scenario_comparison_equals_the_engine(client: TestClient) -> None:
    resp = client.post("/api/scenarios/compare", json={"project": dump(VC)})
    assert resp.status_code == 200
    via_http = ScenarioComparison.model_validate(resp.json())
    assert via_http == svc.compare_scenarios(VC)
    outcome = via_http.scenarios[0]
    assert outcome.scenario_id == "linear_market_size"
    assert outcome.ranking_differs_from_baseline and not outcome.winner_differs_from_baseline
    bad = client.post(
        "/api/scenarios/compare", json={"project": dump(VC), "scenario_ids": ["nope"]}
    )
    assert bad.status_code == 422 and errors(bad)["code"] == "SENSITIVITY_UNDEFINED"


def test_numbers_survive_json_exactly(client: TestClient) -> None:
    """The response text, re-parsed, has the very same floats as the in-process result."""
    resp = client.post("/api/evaluate", json={"project": dump(VC)})
    parsed = json.loads(resp.text)
    direct = svc.evaluate_project(VC).model_dump(mode="json")
    assert parsed == direct
