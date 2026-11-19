"""HTTP compilation, reopening and separate-copy binding; nothing in the library changes."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from conftest import errors

from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.evidence_workspace import EvidenceWorkspace
from mcda_studio.domain.project import Project
from mcda_studio.services import evidence_compilation_service as svc

ROOT = Path(__file__).parents[2]


def rejection(workspace: dict[str, Any], digest: str) -> dict[str, Any]:
    return {
        "workspace": workspace,
        "expected_review_digest": digest,
        "event": {
            "claim_id": "unreviewed_example",
            "review": {
                "status": "rejected",
                "reviewer": "Reviewer",
                "reviewed_at": datetime(2026, 11, 1, tzinfo=UTC).isoformat(),
            },
        },
    }


@pytest.mark.parametrize(
    "name,example", [("vc", "nz_deeptech_vc"), ("supplier", "supplier_qualification")]
)
def test_compile_export_import_copy_and_verify_binding(client, name, example):
    raw = json.loads((ROOT / f"examples/{example}/project.json").read_text())
    dossier = json.loads((ROOT / f"examples/evidence_demo/{name}.json").read_text())
    imported = client.post("/api/projects/import", json=raw)
    assert imported.status_code == 201 and imported.json()["copy_receipt"] is None
    project = imported.json()["project"]
    assert imported.json()["fingerprint"] == dossier["project_fingerprint"]
    saved = client.get(f"/api/projects/{project['id']}/file").content
    first = client.post("/api/evidence/inspect", json={"project": project, "document": dossier})
    body = rejection(first.json()["workspace"], first.json()["preview"]["review_digest"])
    reviewed = client.post("/api/evidence/review", json={"project": project, **body}).json()
    request = {
        "project": project,
        "workspace": reviewed["workspace"],
        "expected_review_digest": reviewed["preview"]["review_digest"],
        "expected_workspace_digest": reviewed["workspace"]["digest"],
    }
    compiled = client.post("/api/evidence/compile", json=request)
    assert compiled.status_code == 200, compiled.text
    bundle = compiled.json()
    p = Project.model_validate(project)
    expected = svc.compilation_bundle(
        p,
        EvidenceWorkspace.model_validate(reviewed["workspace"]),
        reviewed["preview"]["review_digest"],
        reviewed["workspace"]["digest"],
    )
    assert bundle == expected.model_dump(mode="json")
    assert bundle["workspace"]["original_dossier"] == EvidenceDossier.model_validate(
        dossier
    ).model_dump(mode="json")
    assert client.get(f"/api/projects/{project['id']}/file").content == saved
    # Reopening verifies by replay and reconstruction, then inspects the retained history.
    reopened = client.post(
        "/api/evidence/compilation/inspect", json={"project": project, "bundle": bundle}
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["compilation"] == bundle
    assert reopened.json()["inspection"] == reviewed
    # The compiled copy keeps the source ID, so importing it alongside needs a separate copy.
    conflict = client.post("/api/projects/import", json=bundle["project"])
    assert conflict.status_code == 409
    copy = client.post(
        "/api/projects/import", json=bundle["project"], params={"on_conflict": "new_id"}
    )
    assert copy.status_code == 201
    receipt = copy.json()["copy_receipt"]
    assert receipt["original_project_id"] == project["id"]
    assert receipt["original_fingerprint"] == bundle["compiled_fingerprint"]
    assert receipt["copy_project_id"] == copy.json()["project"]["id"] != project["id"]
    assert receipt["copy_fingerprint"] == copy.json()["fingerprint"]
    assert copy.headers["ETag"] == f'"{receipt["copy_fingerprint"]}"'
    copied = copy.json()["project"]
    bind = {"project": copied, "artifact": bundle}
    assert client.post("/api/provenance/binding", json=bind).json()["relationship"] == "different"
    binding = client.post("/api/provenance/binding", json={**bind, "copy_receipt": receipt})
    assert binding.status_code == 200, binding.text
    assert binding.json()["relationship"] == "verified_copy"
    assert binding.json()["current_fingerprint"] != binding.json()["compiled_fingerprint"]
    original = {"project": project, "artifact": bundle}
    assert client.post("/api/provenance/binding", json=original).json()["relationship"] == "source"
    historical = client.post(
        "/api/evidence/compilation/inspect", json={"project": copied, "bundle": bundle}
    )
    codes = [i["code"] for i in historical.json()["inspection"]["preview"]["issues"]]
    assert historical.json()["compilation"] == bundle and "EVIDENCE_STALE_PROJECT" in codes
    assert client.get(f"/api/projects/{project['id']}/file").content == saved


def test_stale_tampered_and_mismatched_requests_are_refused(client):
    raw = json.loads((ROOT / "examples/supplier_qualification/project.json").read_text())
    dossier = json.loads((ROOT / "examples/evidence_demo/supplier.json").read_text())
    first = client.post("/api/evidence/inspect", json={"project": raw, "document": dossier}).json()
    request = {
        "project": raw,
        "workspace": first["workspace"],
        "expected_review_digest": first["preview"]["review_digest"],
        "expected_workspace_digest": first["workspace"]["digest"],
    }
    twice = json.loads(json.dumps(dossier))
    twice["claims"][1]["review"] = twice["claims"][0]["review"]
    conflict = client.post("/api/evidence/inspect", json={"project": raw, "document": twice})
    conflicting = {
        **request,
        "workspace": conflict.json()["workspace"],
        "expected_review_digest": conflict.json()["preview"]["review_digest"],
        "expected_workspace_digest": conflict.json()["workspace"]["digest"],
    }
    refused = errors(client.post("/api/evidence/compile", json=conflicting))
    assert refused["code"] == "VALIDATION_FAILED"
    assert "EVIDENCE_MULTIPLE_ACCEPTED" in [d["code"] for d in refused["details"]]
    stale = {**request, "expected_review_digest": "wrong"}
    assert errors(client.post("/api/evidence/compile", json=stale))["code"] == "STALE_REVISION"
    edited = {**request, "project": {**raw, "title": "Edited"}}
    assert client.post("/api/evidence/compile", json=edited).status_code == 412
    history = {**request, "expected_workspace_digest": "0" * 64}
    assert client.post("/api/evidence/compile", json=history).status_code == 412
    bundle = client.post("/api/evidence/compile", json=request).json()
    bundle["project"]["title"] = "Tampered"
    tampered = client.post(
        "/api/evidence/compilation/inspect", json={"project": raw, "bundle": bundle}
    )
    assert errors(tampered)["code"] == "EDIT_REFUSED"
    assert "EVIDENCE_BUNDLE_CHANGED" in tampered.json()["error"]["message"]
    malformed = client.post(
        "/api/provenance/binding", json={"project": raw, "artifact": {"compilation_version": 1}}
    )
    assert malformed.status_code == 422
