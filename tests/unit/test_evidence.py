"""Evidence is reviewed explicitly and compilation never mutates the source project."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError
from typer.testing import CliRunner

from mcda_studio import cli
from mcda_studio.cli import app
from mcda_studio.domain.errors import StaleRevisionError, ValidationFailed
from mcda_studio.domain.evidence import Claim, EvidenceDossier, Origin, Review, Source
from mcda_studio.services import evidence_service as evidence
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text

ROOT = Path(__file__).parents[2]
repo = JsonProjectRepository()


def project():
    return repo.load(ROOT / "examples/supplier_qualification/project.json")


def claim(**changes):
    data = {
        "id": "cost_report",
        "alternative_id": "apex",
        "criterion_id": "unit_price",
        "value": 42.0,
        "unit": "NZD",
        "source": Source(
            name="Supplier quotation",
            reference="local:quote.pdf",
            location="p. 2",
            date=date(2026, 10, 1),
            description="Quoted price",
            classification="self_reported",
        ),
        "origin": Origin(kind="tool", proposed_by="Analyst", tool_id="extractor", tool_version="1"),
    }
    return Claim(**(data | changes))


def reviewed(status="accepted", **kwargs):
    return Review(
        status=status,
        reviewer="Reviewer",
        reviewed_at=datetime(2026, 10, 31, tzinfo=UTC),
        **kwargs,
    )


def dossier(p, *claims):
    return EvidenceDossier(project_fingerprint=p.fingerprint(), claims=list(claims))


def test_proposals_and_rejections_never_compile():
    p = project()
    d = dossier(p, claim(), claim(id="rejected", review=reviewed("rejected")))
    report = evidence.preview(p, d)
    assert report.changes == [] and report.issues == []
    assert to_json_text(evidence.compile_copy(p, d, report.review_digest)) == to_json_text(p)


def test_reviewed_diff_corrected_value_and_stale_guard():
    p = project()
    before = to_json_text(p)
    d = dossier(p, claim(review=reviewed("corrected", corrected_value=39.5)))
    report = evidence.preview(p, d)
    assert len(report.changes) == 1
    change = report.changes[0]
    assert change.before == p.performance_index()[("apex", "unit_price")]
    assert change.after == 39.5 and change.claim_id == "cost_report"
    result = evidence.compile_copy(p, d, report.review_digest)
    assert result.performance_index()[("apex", "unit_price")] == 39.5
    assert to_json_text(p) == before
    assert to_json_text(result) == to_json_text(evidence.compile_copy(p, d, report.review_digest))
    changed = d.model_copy(update={"claims": [claim(value=41, review=reviewed())]})
    with pytest.raises(StaleRevisionError):
        evidence.compile_copy(p, changed, report.review_digest)
    changed_project = p.model_copy(update={"title": "Changed"})
    assert "EVIDENCE_STALE_PROJECT" in [i.code for i in evidence.preview(changed_project, d).issues]


def test_conflicting_accepted_claims_and_bad_units_block_compilation():
    p = project()
    d = dossier(p, claim(review=reviewed()), claim(id="second", value=45, review=reviewed()))
    report = evidence.preview(p, d)
    assert [i.code for i in report.issues] == ["EVIDENCE_MULTIPLE_ACCEPTED"]
    assert report.changes == []
    with pytest.raises(ValidationFailed):
        evidence.compile_copy(p, d, report.review_digest)
    d = dossier(p, claim(unit="USD", review=reviewed()))
    assert [i.code for i in evidence.preview(p, d).issues] == ["EVIDENCE_UNIT_MISMATCH"]


def test_preview_identifies_missing_unreviewed_outdated_and_conflicting_evidence():
    p = project()
    p.performances = [
        m for m in p.performances if (m.alternative_id, m.criterion_id) != ("apex", "unit_price")
    ]
    d = dossier(p, claim(outdated=True), claim(id="other", value=44))
    report = evidence.preview(p, d)
    assert report.unreviewed_claims == ["cost_report", "other"]
    assert report.outdated_claims == ["cost_report"]
    assert [(c.alternative_id, c.criterion_id) for c in report.conflicting_cells] == [
        ("apex", "unit_price")
    ]
    assert ("apex", "unit_price") in [
        (c.alternative_id, c.criterion_id) for c in report.missing_measurements
    ]
    result = evidence.compile_copy(p, d, report.review_digest)
    assert ("apex", "unit_price") not in result.performance_index()


@pytest.mark.parametrize("example", ["vc", "supplier"])
def test_synthetic_evidence_examples_match_source_projects(example):
    project_name = "nz_deeptech_vc" if example == "vc" else "supplier_qualification"
    p = repo.load(ROOT / "examples" / project_name / "project.json")
    d = EvidenceDossier.model_validate_json(
        (ROOT / "examples" / "evidence_demo" / f"{example}.json").read_text()
    )
    report = evidence.preview(p, d)
    assert not report.issues and len(report.changes) == 1
    assert report.unreviewed_claims == ["unreviewed_example"]
    assert report.outdated_claims == ["unreviewed_example"] and len(report.conflicting_cells) == 1
    assert evidence.compile_copy(p, d, report.review_digest).fingerprint() != p.fingerprint()


def test_invalid_references_types_and_duplicate_existing_measurements_block():
    p = project()
    cases = [
        (claim(alternative_id="absent"), "EVIDENCE_UNKNOWN_ALTERNATIVE"),
        (claim(criterion_id="absent"), "EVIDENCE_UNKNOWN_CRITERION"),
        (claim(value="bad", review=reviewed()), "EVIDENCE_INVALID_VALUE"),
    ]
    for c, code in cases:
        assert code in [i.code for i in evidence.preview(p, dossier(p, c)).issues]
    p.performances.append(
        next(
            m
            for m in p.performances
            if (m.alternative_id, m.criterion_id) == ("apex", "unit_price")
        )
    )
    report = evidence.preview(p, dossier(p, claim(review=reviewed())))
    assert "EVIDENCE_DUPLICATE_MEASUREMENT" in [i.code for i in report.issues]


def test_origin_review_and_uncertainty_require_valid_metadata():
    with pytest.raises(ValidationError):
        Origin(kind="tool", proposed_by="X")
    with pytest.raises(ValidationError):
        Review(status="accepted", reviewer="X", reviewed_at=datetime(2026, 1, 1))
    with pytest.raises(ValidationError):
        reviewed("corrected")
    with pytest.raises(ValidationError):
        claim(uncertainty_lower=0, uncertainty_upper=41)


@given(st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False))
def test_compilation_is_order_independent_and_reproducible(value):
    p = project()
    a = claim(value=value, review=reviewed())
    b = claim(id="unreviewed", value=2)
    first, second = dossier(p, a, b), dossier(p, b, a)
    one = evidence.compile_copy(p, first, evidence.preview(p, first).review_digest)
    two = evidence.compile_copy(p, second, evidence.preview(p, second).review_digest)
    assert to_json_text(one) == to_json_text(two)
    assert one.performance_index()[("apex", "unit_price")] == value


def test_cli_preview_compile_and_refuse_overwrite(tmp_path):
    p = project()
    source, doc, output = (
        tmp_path / "source.json",
        tmp_path / "evidence.json",
        tmp_path / "copy.json",
    )
    repo.save(p, source)
    doc.write_text(dossier(p, claim(review=reviewed())).model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["evidence", "preview", str(source), str(doc)])
    assert result.exit_code == 0, result.output
    digest = json.loads(result.stdout)["review_digest"]
    command = [
        "evidence",
        "compile",
        str(source),
        str(doc),
        "-o",
        str(output),
        "--review-digest",
        digest,
    ]
    result = runner.invoke(app, command)
    assert result.exit_code == 0, result.output
    assert repo.load(output).performance_index()[("apex", "unit_price")] == 42
    assert repo.load(source).fingerprint() == p.fingerprint()
    prior = output.read_bytes()
    assert runner.invoke(app, command).exit_code != 0
    assert output.read_bytes() == prior


def test_failed_publication_leaves_no_output_or_temporary_file(tmp_path, monkeypatch):
    def fail_link(*_args):
        raise OSError("injected publication failure")

    monkeypatch.setattr(cli.os, "link", fail_link)
    with pytest.raises(OSError, match="injected"):
        cli._new_file(tmp_path / "new.json", "content")
    assert list(tmp_path.iterdir()) == []
