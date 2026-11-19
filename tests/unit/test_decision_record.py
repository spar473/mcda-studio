"""Decision records keep the exact project and completed analysis used for a decision."""

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mcda_studio.cli import app
from mcda_studio.domain.decision import DecisionDraft, DecisionRecord
from mcda_studio.domain.errors import McdaError
from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.services import decision_service, evidence_service
from mcda_studio.storage.json_repository import JsonProjectRepository

ROOT = Path(__file__).parents[2]
repo = JsonProjectRepository()


def project():
    return repo.load(ROOT / "examples/supplier_qualification/project.json")


def draft():
    return DecisionDraft(
        owner="Analyst",
        date=date(2026, 10, 31),
        chosen_alternative_id="apex",
        rationale="Quality and delivery",
        configurations=[AnalysisConfiguration(method="mavt")],
        unresolved_assumptions=["Delivery estimate"],
        review_triggers=["Annual review"],
    )


def test_snapshot_is_reproducible_and_revision_does_not_change_it():
    p = project()
    first = decision_service.create(p, draft())
    body = first.model_dump(mode="json", exclude={"digest"})
    canonical = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    assert first.digest == hashlib.sha256(canonical.encode()).hexdigest()
    restored = DecisionRecord.model_validate_json(first.model_dump_json())
    assert decision_service.digest(restored) == first.digest
    assert restored.project_fingerprint == p.fingerprint()
    assert restored.analyses[0].record_digest
    original = first.model_dump_json()
    p.title = "Updated"
    second = decision_service.create(p, draft(), first)
    assert second.previous_digest == first.digest and second.digest != first.digest
    assert first.model_dump_json() == original and first.project.title != second.project.title


def test_refuses_unknown_choice_and_tampered_predecessor():
    p = project()
    with pytest.raises(McdaError, match="DECISION_UNKNOWN_ALTERNATIVE"):
        decision_service.create(p, draft().model_copy(update={"chosen_alternative_id": "missing"}))
    first = decision_service.create(p, draft())
    first.decision.rationale = "tampered"
    with pytest.raises(McdaError, match="DECISION_INVALID_PREDECESSOR"):
        decision_service.create(p, draft(), first)


def test_evidence_snapshot_must_reproduce_the_project():
    source = project()
    dossier = EvidenceDossier.model_validate_json(
        (ROOT / "examples/evidence_demo/supplier.json").read_text()
    )
    preview = evidence_service.preview(source, dossier)
    compiled = evidence_service.compile_copy(source, dossier, preview.review_digest)
    record = decision_service.create(compiled, draft(), source_project=source, dossier=dossier)
    assert record.evidence is not None
    assert record.evidence.review_digest == preview.review_digest
    assert record.evidence.dossier == dossier
    with pytest.raises(McdaError, match="DECISION_EVIDENCE_MISMATCH"):
        decision_service.create(source, draft(), source_project=source, dossier=dossier)
    with pytest.raises(McdaError, match="DECISION_INCOMPLETE_EVIDENCE"):
        decision_service.create(source, draft(), dossier=dossier)


def test_cli_creates_new_record_and_never_overwrites(tmp_path):
    p = project()
    project_path, draft_path, record_path = (
        tmp_path / "project.json",
        tmp_path / "draft.json",
        tmp_path / "record.json",
    )
    repo.save(p, project_path)
    draft_path.write_text(draft().model_dump_json(), encoding="utf-8")
    command = ["decision", "record", str(project_path), str(draft_path), "-o", str(record_path)]
    runner = CliRunner()
    run = runner.invoke(app, command)
    assert run.exit_code == 0, run.output
    record = DecisionRecord.model_validate_json(record_path.read_text())
    assert record.digest == decision_service.digest(record)
    prior = record_path.read_bytes()
    assert runner.invoke(app, command).exit_code != 0
    assert record_path.read_bytes() == prior
