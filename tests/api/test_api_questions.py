"""Open Questions are generated on the server for the submitted context."""

import json

from conftest import EXAMPLES, dump, repo
from fastapi.testclient import TestClient


def test_questions_route_keeps_context_and_missing_measurements(client: TestClient) -> None:
    p = dump(repo.load(EXAMPLES / "supplier_qualification" / "project.json"))
    p["performances"] = [
        m
        for m in p["performances"]
        if (m["alternative_id"], m["criterion_id"]) != ("apex", "unit_price")
    ]
    cfg = {"method": "mavt", "weight_profile_id": None, "scenario_id": None, "parameters": {}}
    response = client.post("/api/open-questions", json={"project": p, "configuration": cfg})
    assert response.status_code == 200
    body = response.json()
    assert body["configuration"] == cfg
    assert any(
        q["code"] == "MISSING_MEASUREMENT" and q["alternative_id"] == "apex"
        for q in body["questions"]
    )
    assert any("could not run" in note for note in body["limitations"])


def test_questions_route_reports_claims_without_accepting_them(client: TestClient) -> None:
    p = dump(repo.load(EXAMPLES / "nz_deeptech_vc" / "project.json"))
    dossier = json.loads((EXAMPLES / "evidence_demo" / "vc.json").read_text())
    response = client.post("/api/open-questions", json={"project": p, "dossier": dossier})
    assert response.status_code == 200
    body = response.json()
    assert {q["code"] for q in body["questions"] if q["group"] == "evidence_quality"} == {
        "UNREVIEWED_CLAIM",
        "OUTDATED_CLAIM",
        "CONFLICTING_CLAIMS",
        "MEASUREMENT_WITHOUT_ACCEPTED_SUPPORT",
    }
    assert "Evidence dossier review and provenance gaps" in body["coverage"]


def test_reviewed_range_exposes_contacts_and_engine_witnesses(client: TestClient) -> None:
    p = dump(repo.load(EXAMPLES / "supplier_qualification" / "project.json"))
    dossier = json.loads((EXAMPLES / "evidence_demo" / "supplier.json").read_text())
    dossier["claims"][0].update(value=42, uncertainty_lower=20, uncertainty_upper=60)
    response = client.post("/api/open-questions", json={"project": p, "dossier": dossier})
    assert response.status_code == 200
    result = next(
        q["measurement_range"]
        for q in response.json()["questions"]
        if q["code"] == "MEASUREMENT_RANGE_CHANGE"
    )
    assert result["rank_can_change"] and result["class_can_change"]
    assert {c["kind"] for c in result["boundary_contacts"]} == {"rank", "class"}
    assert {w["rank"] for w in result["witnesses"]} != {result["baseline_rank"]}
