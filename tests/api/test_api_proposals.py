"""HTTP and CLI proposal parity; local source and saved project bytes stay unchanged."""

import json

from typer.testing import CliRunner

from mcda_studio.cli import app
from mcda_studio.services import proposal_import_service as imports
from mcda_studio.services import proposal_service as svc
from mcda_studio.storage.json_repository import to_json_text
from proposal_builders import apply, compile_, event, inputs


def test_http_import_review_compile_verify_and_open_questions_without_library_changes(client):
    p, intake = inputs()
    project = p.model_dump(mode="json")
    assert client.post("/api/projects/import", json=project).status_code == 201
    before = client.get(f"/api/projects/{p.id}/file").content
    imported = client.post(
        "/api/proposals/import", json={"project": project, "text": intake.model_dump_json()}
    )
    assert imported.status_code == 200, imported.text
    inspection = imported.json()
    workspace = svc.start(p, intake)
    assert inspection == svc.inspect(p, workspace).model_dump(mode="json")
    body = {
        "project": project,
        "workspace": inspection["workspace"],
        "expected_review_digest": inspection["review_digest"],
        "expected_workspace_digest": workspace.digest,
        "events": [event().model_dump(mode="json")],
    }
    response = client.post("/api/proposals/review", json=body)
    assert response.status_code == 200, response.text
    reviewed = response.json()
    assert reviewed == apply(p, workspace, event()).model_dump(mode="json")
    request = {
        "project": project,
        "workspace": reviewed["workspace"],
        "expected_review_digest": reviewed["review_digest"],
        "expected_workspace_digest": reviewed["workspace"]["digest"],
    }
    compiled = client.post("/api/proposals/compile", json=request)
    assert compiled.status_code == 200, compiled.text
    assert compiled.json() == compile_(p, apply(p, workspace, event()).workspace).model_dump(
        mode="json"
    )
    assert client.post("/api/proposals/verify", json=compiled.json()).json() == compiled.json()
    questions = client.post(
        "/api/open-questions", json={"project": project, "proposals": inspection["workspace"]}
    )
    assert questions.status_code == 200, questions.text
    assert "PROPOSAL_PENDING" in [q["code"] for q in questions.json()["questions"]]
    assert client.get(f"/api/projects/{p.id}/file").content == before


def test_http_csv_parity_stale_ack_and_invalid_numeric_types(client):
    p, intake = inputs()
    csv, registries = imports.csv_files(intake)
    payload = {
        "project": p.model_dump(mode="json"),
        "text": csv,
        "format": "csv",
        "registries_text": registries,
    }
    response = client.post("/api/proposals/import", json=payload)
    assert response.status_code == 200, response.text
    current = response.json()
    bad = {**payload, "format": "json", "text": intake.model_dump_json(), "registries_text": None}
    assert client.post("/api/proposals/import", json=bad).json() == current
    events = [event().model_dump(mode="json")]
    request = {
        "project": payload["project"],
        "workspace": current["workspace"],
        "events": events,
        "expected_review_digest": "wrong",
        "expected_workspace_digest": current["workspace"]["digest"],
    }
    assert client.post("/api/proposals/review", json=request).status_code == 412
    raw = intake.model_dump(mode="json")
    raw["proposals"][0]["payload"]["value"] = True
    rejected = client.post("/api/proposals/import", json={**bad, "text": json.dumps(raw)})
    assert rejected.status_code == 409 and "PROPOSAL_IMPORT" in rejected.text
    tampered = compile_(p, apply(p, svc.start(p, intake), event()).workspace).model_dump(
        mode="json"
    )
    tampered["evidence"]["project"]["title"] = "Changed"
    assert client.post("/api/proposals/verify", json=tampered).status_code == 409


def test_transport_limit_is_enforced_without_trusting_content_length(client):
    response = client.post(
        "/api/proposals/import",
        content=iter([b" " * 12_000_001] * 2),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PROPOSAL_BODY_LIMIT"


def test_cli_import_review_confirmation_compile_verify_and_exclusive_output(tmp_path):
    p, intake = inputs()
    project, source, workspace_file, events_file, reviewed_file, bundle_file = [
        tmp_path / name
        for name in (
            "project.json",
            "intake.json",
            "workspace.json",
            "events.json",
            "reviewed.json",
            "bundle.json",
        )
    ]
    project.write_text(to_json_text(p))
    source.write_text(intake.model_dump_json())
    events_file.write_text(json.dumps([event().model_dump(mode="json")]))
    runner = CliRunner()
    result = runner.invoke(
        app, ["proposals", "import", str(project), str(source), "--output", str(workspace_file)]
    )
    assert result.exit_code == 0, result.output
    command = [
        "proposals",
        "review",
        str(project),
        str(workspace_file),
        str(events_file),
        "--output",
        str(reviewed_file),
    ]
    preview = runner.invoke(app, command)
    assert preview.exit_code == 0, preview.output
    confirmation = json.loads(preview.output)
    assert confirmation["affected"][0]["proposal_id"] == "quote_a"
    assert not reviewed_file.exists()
    result = runner.invoke(
        app, [*command, "--confirm-selection", confirmation["confirmation_digest"]]
    )
    assert result.exit_code == 0, result.output
    from mcda_studio.domain.external_proposals import ExternalProposals

    reviewed = ExternalProposals.model_validate_json(reviewed_file.read_text())
    current = svc.inspect(p, reviewed)
    command = [
        "proposals",
        "compile",
        str(project),
        str(reviewed_file),
        "--review-digest",
        current.review_digest,
        "--workspace-digest",
        reviewed.digest,
        "--output",
        str(bundle_file),
    ]
    result = runner.invoke(app, command)
    assert result.exit_code == 0, result.output
    assert json.loads(bundle_file.read_text()) == compile_(p, reviewed).model_dump(mode="json")
    assert runner.invoke(app, ["proposals", "verify", str(bundle_file)]).exit_code == 0
    before = bundle_file.read_bytes()
    assert runner.invoke(app, command).exit_code != 0 and bundle_file.read_bytes() == before
    assert project.read_text() == to_json_text(p)
