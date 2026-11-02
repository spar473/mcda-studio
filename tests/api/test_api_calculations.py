"""Calculation workspace endpoints are stateless, match the service and feed /api/edit exactly."""

import json
from datetime import UTC, datetime
from pathlib import Path

from conftest import errors

from mcda_studio.domain.calculation_workspace import CalculationWorkspace, ReviewEntry
from mcda_studio.domain.derived import DerivedModel
from mcda_studio.domain.evidence import Review
from mcda_studio.domain.project import Project
from mcda_studio.services import calculation_workspace_service as cw

EXAMPLE = Path(__file__).parents[2] / "examples/derived_measurements"
WHEN = datetime(2026, 11, 1, 9, tzinfo=UTC)


def test_inspect_propose_apply_and_edit_reproduce_the_service(client):
    raw = json.loads((EXAMPLE / "supplier-project.json").read_text())
    model = json.loads((EXAMPLE / "supplier-model.json").read_text())
    stored = client.post("/api/projects/import", json=raw).json()
    saved = client.get(f"/api/projects/{raw['id']}/file").content
    project = stored["project"]
    opened = client.post("/api/calculations/inspect", json={"project": project, "document": model})
    assert opened.status_code == 200, opened.text
    p = Project.model_validate(project)
    expected = cw.inspect(p, DerivedModel.model_validate(model))
    assert opened.json() == expected.model_dump(mode="json")
    event = ReviewEntry(
        entry="source",
        id="price_a",
        review=Review(status="corrected", reviewer="A", reviewed_at=WHEN, corrected_value=47.0),
    )
    body = {
        "project": project,
        "workspace": opened.json()["workspace"],
        "event": event.model_dump(mode="json"),
        "expected_review_digest": opened.json()["preview"]["review_digest"],
    }
    proposed = client.post("/api/calculations/propose", json=body)
    assert proposed.status_code == 200, proposed.text
    assert proposed.json() == cw.propose(
        p, expected.workspace, event, expected.preview.review_digest
    ).model_dump(mode="json")
    candidate = proposed.json()
    applied = client.post(
        "/api/calculations/apply",
        json={
            "project": project,
            "workspace": candidate["workspace"],
            "expected_review_digest": candidate["preview"]["review_digest"],
            "recorded_by": "Analyst",
            "recorded_at": WHEN.isoformat(),
        },
    )
    assert applied.status_code == 200, applied.text
    result = applied.json()
    operations = [{"op": "set_performance", **a} for a in result["assignments"]]
    edited = client.post("/api/edit", json={"project": project, "operations": operations})
    assert edited.status_code == 200
    assert edited.json()["fingerprint"] == result["project_fingerprint"]
    assert edited.json()["project"] == result["bundle"]["project"]
    reopened = cw.inspect(
        Project.model_validate(edited.json()["project"]),
        CalculationWorkspace.model_validate(result["inspection"]["workspace"]),
    )
    assert reopened.relationship == "bound"
    binding = client.post(
        "/api/provenance/binding",
        json={"project": edited.json()["project"], "artifact": result["bundle"]},
    )
    assert binding.json()["relationship"] == "compiled"
    # Nothing was written: the stored project file is byte-identical.
    assert client.get(f"/api/projects/{raw['id']}/file").content == saved


def test_stale_refused_and_malformed_requests_are_structured(client):
    raw = json.loads((EXAMPLE / "venture-project.json").read_text())
    model = json.loads((EXAMPLE / "venture-model.json").read_text())
    opened = client.post(
        "/api/calculations/inspect", json={"project": raw, "document": model}
    ).json()
    event = {
        "kind": "review",
        "entry": "formula",
        "id": "market_a",
        "review": {
            "status": "corrected",
            "reviewer": "A",
            "reviewed_at": WHEN.isoformat(),
            "corrected_value": 1,
        },
    }
    body = {
        "project": raw,
        "workspace": opened["workspace"],
        "event": event,
        "expected_review_digest": opened["preview"]["review_digest"],
    }
    refused = errors(client.post("/api/calculations/propose", json=body))
    assert (
        refused["code"] == "EDIT_REFUSED" and "CALCULATION_FORMULA_CORRECTION" in refused["message"]
    )
    stale = client.post("/api/calculations/propose", json={**body, "expected_review_digest": "x"})
    assert errors(stale)["code"] == "STALE_REVISION"
    apply_kind = {**body, "event": {"kind": "apply", "review_digest": "0" * 64}}
    assert client.post("/api/calculations/propose", json=apply_kind).status_code == 422
    tampered = {**opened["workspace"], "digest": "0" * 64}
    changed = client.post("/api/calculations/inspect", json={"project": raw, "document": tampered})
    assert "CALCULATION_HISTORY_CHANGED" in errors(changed)["message"]
    naive = {
        **body,
        "event": {**event, "review": {**event["review"], "reviewed_at": "2026-11-01T09:00"}},
    }
    assert client.post("/api/calculations/propose", json=naive).status_code == 422
    nothing = client.post(
        "/api/calculations/apply",
        json={
            "project": raw,
            "workspace": opened["workspace"],
            "expected_review_digest": opened["preview"]["review_digest"],
            "recorded_by": "",
            "recorded_at": WHEN.isoformat(),
        },
    )
    assert nothing.status_code == 422
