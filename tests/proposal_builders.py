"""Invented, domain-neutral proposal inputs shared by service/API/browser checks."""

from datetime import UTC, datetime

from mcda_studio.domain.external_proposals import ProposalIntake, ProposalReview
from mcda_studio.services import evidence_service, proposal_service

from builders import tiny_project

TIME = datetime(2026, 11, 1, tzinfo=UTC)


def inputs():
    project = tiny_project().model_copy(update={"id": "proposal_demo"})
    source = {
        "name": "Invented source",
        "reference": "local:invented-brief",
        "location": "table 1",
        "date": "2026-11-01",
        "description": "Invented test values",
        "classification": "unknown",
    }
    card = {
        "version": 1,
        "purpose": "Propose measurements",
        "limitations": "Invented, no factual evidence",
        "model_version": "1",
        "details": {},
    }
    from mcda_studio.domain.external_proposals import LocalModelCard

    digest = evidence_service._digest(LocalModelCard.model_validate(card).model_dump(mode="json"))
    proposal = {
        "proposal_version": 1,
        "id": "quote_a",
        "subject": {"alternative_id": "a", "criterion_id": "cost"},
        "payload": {"kind": "numeric_cell", "value": 30.0, "unit": None},
        "tool_id": "external_a",
        "tool_version": "1",
        "model_card_id": "card",
        "model_card_digest": digest,
        "run_at": TIME.isoformat(),
        "confidence": {
            "value": 0.83,
            "scale": "unit_interval",
            "meaning": "Tool-reported confidence only",
        },
        "source_ids": ["brief"],
        "replaces_proposal_id": None,
    }
    raw = {
        "schema_version": 1,
        "project_fingerprint": project.fingerprint(),
        "sources": {"brief": source},
        "model_cards": {"card": card},
        "proposals": [proposal],
        "human_dossier": None,
    }
    import json

    intake = ProposalIntake.model_validate_json(json.dumps(raw))
    return project, intake


def event(proposal_id="quote_a", status="accepted", payload=None, **changes):
    from mcda_studio.domain.external_proposals import ProposalReviewDetails

    review = ProposalReviewDetails(
        status=status,
        reviewer="Illustrative reviewer",
        reviewed_at=TIME,
        note="Checked locally",
        corrected_payload=payload,
        primary_source_id="brief",
        **changes,
    )
    return ProposalReview(proposal_id=proposal_id, review=review)


def apply(project, workspace, *events, bulk=False, comparison_target=None):
    current = proposal_service.inspect(project, workspace, comparison_target)
    return proposal_service.review(
        project,
        workspace,
        list(events),
        current.review_digest,
        workspace.digest,
        bulk,
        comparison_target,
    )


def compile_(project, workspace):
    current = proposal_service.inspect(project, workspace)
    return proposal_service.compile_bundle(
        project, workspace, current.review_digest, workspace.digest
    )
