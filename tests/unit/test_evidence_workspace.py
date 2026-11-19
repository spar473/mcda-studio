"""Review copies preserve inputs/history and never confer validity on unsupported values."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mcda_studio.domain.errors import ModelEditError, StaleRevisionError, ValidationFailed
from mcda_studio.domain.evidence import EvidenceDossier, Review
from mcda_studio.domain.evidence_workspace import ClaimReview, EvidenceWorkspace
from mcda_studio.services import evidence_service, project_service, questions_service
from mcda_studio.services import evidence_workspace_service as svc
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text

ROOT = Path(__file__).parents[2]


def inputs():
    p = JsonProjectRepository().load(ROOT / "examples/supplier_qualification/project.json")
    d = EvidenceDossier.model_validate_json(
        (ROOT / "examples/evidence_demo/supplier.json").read_text()
    )
    return p, d


def event(claim_id="unreviewed_example", status="rejected", **kwargs):
    return ClaimReview(
        claim_id=claim_id,
        review=Review(
            status=status,
            reviewer="Local analyst",
            reviewed_at=datetime(2026, 11, 1, tzinfo=UTC),
            note="Checked source",
            **kwargs,
        ),
    )


def test_review_append_replay_reopen_and_cli_compatible_compilation(tmp_path):
    p, d = inputs()
    before, original = to_json_text(p), d.model_dump_json()
    initial = svc.inspect(p, d)
    proposed = svc.propose_review(p, initial.workspace, event(), initial.preview.review_digest)
    assert d.model_dump_json() == original and to_json_text(p) == before
    assert initial.workspace.reviews == []
    assert proposed.workspace.original_dossier == d
    assert proposed.dossier.claims[1].review.status == "rejected"
    assert proposed.preview.conflicting_cells == []
    path = tmp_path / "workspace.json"
    path.write_text(proposed.workspace.model_dump_json())
    reopened = svc.inspect(p, EvidenceWorkspace.model_validate_json(path.read_text()))
    assert reopened == proposed
    corrected = svc.propose_review(
        p,
        reopened.workspace,
        event("reviewed_example", "corrected", corrected_value=42),
        reopened.preview.review_digest,
    )
    assert [r.review.status for r in corrected.workspace.reviews] == ["rejected", "corrected"]
    assert corrected.workspace.original_dossier.claims[0].review.status == "accepted"
    exported = EvidenceDossier.model_validate_json(corrected.dossier.model_dump_json())
    compiled = evidence_service.compile_copy(p, exported, corrected.preview.review_digest)
    assert compiled.performance_index()[("apex", "unit_price")] == 42
    assert corrected.dossier.claims[0].value == 40  # original proposal survives corrections
    assert corrected.support[0].status == "supported"
    assert corrected.support[0].accepted_claim_ids == ["reviewed_example"]


@pytest.mark.parametrize("change", ["project", "dossier", "history"])
def test_stale_digest_or_tampered_history_cannot_review(change):
    p, d = inputs()
    initial = svc.inspect(p, d)
    if change == "project":
        p.title = "Different revision"
    elif change == "dossier":
        initial.workspace.original_dossier.claims[0].value = 41
    else:
        initial.workspace.reviews.append(event())
    with pytest.raises((StaleRevisionError, ModelEditError)):
        svc.propose_review(p, initial.workspace, event(), initial.preview.review_digest)


def test_stale_workspace_remains_exportable_and_readable_but_not_reviewable():
    p, d = inputs()
    initial = svc.inspect(p, d)
    p.title = "Changed project"
    stale = svc.inspect(p, initial.workspace)
    assert stale.workspace_exportable and stale.workspace == initial.workspace
    assert stale.dossier == d and not stale.support_available and stale.support == []
    assert "EVIDENCE_STALE_PROJECT" in [i.code for i in stale.preview.issues]
    with pytest.raises(StaleRevisionError):
        svc.propose_review(p, stale.workspace, event(), stale.preview.review_digest)
    raw_stale = svc.inspect(p, d)
    assert not raw_stale.workspace_exportable


@pytest.mark.parametrize("unit,value", [("USD", 45), ("NZD", "wrong"), ("NZD", -1)])
def test_acceptance_reuses_authoritative_units_and_numeric_validation(unit, value):
    p, d = inputs()
    d.claims[0].review = None
    d.claims[1].unit = unit
    d.claims[1].value = value
    current = svc.inspect(p, d)
    with pytest.raises(ValidationFailed):
        svc.propose_review(
            p, current.workspace, event(status="accepted"), current.preview.review_digest
        )
    # Rejection remains possible so an incomplete/invalid dossier can be repaired by review.
    rejected = svc.propose_review(p, current.workspace, event(), current.preview.review_digest)
    assert rejected.dossier.claims[1].review.status == "rejected"


def test_conflicting_acceptance_refused_reject_then_accept_is_explicit():
    p, d = inputs()
    current = svc.inspect(p, d)
    with pytest.raises(ValidationFailed, match="only one claim"):
        svc.propose_review(
            p, current.workspace, event(status="accepted"), current.preview.review_digest
        )
    first = svc.propose_review(
        p, current.workspace, event("reviewed_example"), current.preview.review_digest
    )
    second = svc.propose_review(
        p, first.workspace, event(status="accepted"), first.preview.review_digest
    )
    assert second.preview.changes[0].claim_id == "unreviewed_example"
    assert second.preview.changes[0].after == 45
    assert second.dossier.claims[1].outdated  # acceptance does not imply source freshness


def test_duplicate_unknown_claim_and_blank_reviewer_are_refused():
    p, d = inputs()
    current = svc.inspect(p, d)
    with pytest.raises(ModelEditError):
        svc.propose_review(p, current.workspace, event("absent"), current.preview.review_digest)
    bad = event()
    bad.review.reviewer = "   "
    with pytest.raises(ModelEditError):
        svc.propose_review(p, current.workspace, bad, current.preview.review_digest)
    d.claims.append(d.claims[1].model_copy(deep=True))
    duplicate = svc.inspect(p, d)
    with pytest.raises(ModelEditError):
        svc.propose_review(p, duplicate.workspace, event(), duplicate.preview.review_digest)


def test_incomplete_model_has_missing_unsupported_and_unverified_separately():
    p, d = inputs()
    p = project_service.clear_performance(p, "brightline", "unit_price")
    d.project_fingerprint = p.fingerprint()
    p.weight_profiles = []  # evidence inspection does not require a complete preference model
    d.project_fingerprint = p.fingerprint()
    current = svc.inspect(p, d)
    by_cell = {(s.alternative_id, s.criterion_id): s for s in current.support}
    assert by_cell[("apex", "unit_price")].status == "unverified"  # accepted 40 != entered 42
    assert by_cell[("brightline", "unit_price")].status == "missing"
    assert by_cell[("apex", "logistics_cost")].status == "unsupported"
    assert not current.preview.issues
    reviewed = svc.propose_review(p, current.workspace, event(), current.preview.review_digest)
    assert reviewed.workspace.reviews == [event()]


def test_support_questions_disappear_only_for_matching_accepted_values():
    p, d = inputs()
    d.claims[0].value = 42
    initial = svc.inspect(p, d)
    assert initial.support[0].status == "supported"
    questions, limits = questions_service.evidence_questions(p, d)
    assert limits == []
    assert not any(
        q.code == "MEASUREMENT_WITHOUT_ACCEPTED_SUPPORT"
        and (q.alternative_id, q.criterion_id) == ("apex", "unit_price")
        for q in questions
    )


def test_review_limit_is_a_domain_refusal():
    p, d = inputs()
    current = svc.inspect(p, d)
    current.workspace.reviews = [event()] * 2000
    current.workspace.digest = svc.workspace_digest(current.workspace)
    current = svc.inspect(p, current.workspace)
    with pytest.raises(ModelEditError, match="2000"):
        svc.propose_review(p, current.workspace, event(), current.preview.review_digest)
