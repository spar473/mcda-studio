from datetime import UTC, datetime
from pathlib import Path

import pytest

from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.services import evidence_workspace_service as svc
from mcda_studio.storage.json_repository import JsonProjectRepository

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize(
    "name,example", [("vc", "nz_deeptech_vc"), ("supplier", "supplier_qualification")]
)
def test_inspect_review_export_reopen_is_stateless_and_matches_service(client, name, example):
    p = JsonProjectRepository().load(ROOT / f"examples/{example}/project.json")
    d = EvidenceDossier.model_validate_json(
        (ROOT / f"examples/evidence_demo/{name}.json").read_text()
    )
    document = p.model_dump(mode="json")
    imported = client.post("/api/projects/import", json=document)
    assert imported.status_code == 201
    before = client.get(f"/api/projects/{p.id}").json()
    response = client.post(
        "/api/evidence/inspect", json={"project": document, "document": d.model_dump(mode="json")}
    )
    assert response.status_code == 200
    initial = response.json()
    assert initial == svc.inspect(p, d).model_dump(mode="json")
    body = {
        "project": document,
        "workspace": initial["workspace"],
        "expected_review_digest": initial["preview"]["review_digest"],
        "event": {
            "claim_id": "unreviewed_example",
            "review": {
                "status": "rejected",
                "reviewer": "Reviewer",
                "reviewed_at": datetime(2026, 11, 1, tzinfo=UTC).isoformat(),
            },
        },
    }
    reviewed = client.post("/api/evidence/review", json=body)
    assert reviewed.status_code == 200
    result = reviewed.json()
    assert result["dossier"]["claims"][1]["review"]["status"] == "rejected"
    assert len(result["workspace"]["reviews"]) == 1
    reopened = client.post(
        "/api/evidence/inspect", json={"project": document, "document": result["workspace"]}
    )
    assert reopened.json() == result
    assert client.get(f"/api/projects/{p.id}").json() == before
    body["expected_review_digest"] = "wrong"
    assert client.post("/api/evidence/review", json=body).status_code == 412
    body["workspace"]["digest"] = "changed"
    assert client.post("/api/evidence/review", json=body).status_code == 409


def test_malformed_evidence_never_calls_review(client):
    p = JsonProjectRepository().load(ROOT / "examples/supplier_qualification/project.json")
    assert (
        client.post(
            "/api/evidence/inspect",
            json={"project": p.model_dump(mode="json"), "document": {"claims": []}},
        ).status_code
        == 422
    )
