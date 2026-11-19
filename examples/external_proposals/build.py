"""Build two wholly invented local intake/review demonstrations using one generic workflow."""

import json
from datetime import UTC, datetime
from pathlib import Path

from mcda_studio.domain.criteria import DirectRatingValueFunction, QualitativeValueFunction
from mcda_studio.domain.evidence import Claim, EvidenceDossier, Origin, Source
from mcda_studio.domain.external_proposals import (
    AlternativeTag,
    CategoricalProposal,
    ExternalProposal,
    LocalModelCard,
    NumericProposal,
    ProposalConfidence,
    ProposalIntake,
    ProposalReview,
    ProposalReviewDetails,
    ProposalSubject,
    SuggestedSourceClaim,
)
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.services import evidence_service
from mcda_studio.services import project_service as ps
from mcda_studio.services import proposal_import_service as imports
from mcda_studio.services import proposal_service as svc
from mcda_studio.storage.json_repository import to_json_text

ROOT = Path(__file__).resolve().parent
TIME = datetime(2026, 11, 1, tzinfo=UTC)


def build(name):
    screening = name == "screening"
    criterion = "sector" if screening else "supply_risk"
    labels = ["hardware", "software"] if screening else ["low", "medium", "high"]
    proposed, selected = ("software", "hardware") if screening else ("high", "medium")
    title = "Invented screening intake" if screening else "Invented supplier intake"
    p = ps.new_project(title).model_copy(update={"id": f"proposal_{name}"})
    p.description = (
        "Invented Option A/B data and sources. Illustrative review, not factual evidence."
    )
    for alt in ("a", "b"):
        p = ps.add_alternative(p, f"Option {alt.upper()}", alt_id=alt)
    p = ps.add_criterion(
        p,
        "Sector" if screening else "Supply risk",
        crit_id=criterion,
        scale=Scale(type=ScaleType.CATEGORICAL, labels=labels),
        value_function=QualitativeValueFunction(
            mapping={label: i / (len(labels) - 1) for i, label in enumerate(labels)}
        ),
    )
    p = ps.add_criterion(
        p,
        "Stage" if screening else "Readiness",
        crit_id="readiness",
        scale=Scale(type=ScaleType.ORDINAL, labels=["early", "ready"]),
        value_function=QualitativeValueFunction(mapping={"early": 0, "ready": 1}),
    )
    p = ps.add_criterion(
        p,
        "Reviewed numeric measure",
        crit_id="measure",
        scale=Scale(type=ScaleType.INTERVAL, lower=0, upper=1, unit="1"),
        value_function=DirectRatingValueFunction(min_rating=0, max_rating=1),
    )
    for alt in ("a", "b"):
        for crit, value in ((criterion, labels[0]), ("readiness", "ready"), ("measure", 0.5)):
            p = ps.set_performance(p, alt, crit, value)
    for crit, rating in ((criterion, 100), ("readiness", 70), ("measure", 40)):
        p = ps.set_judgement(p, crit, rating)
    sources = {
        f"brief_{a}": Source(
            name=f"Invented brief {a.upper()}",
            reference=f"local:invented-brief-{a}",
            location="table 1",
            date=TIME.date(),
            description="Every statement and value is invented for this demonstration.",
            classification="self_reported" if a == "a" else "independent",
        )
        for a in ("a", "b")
    }
    card = LocalModelCard(
        purpose="Propose labels and local measurements for review",
        limitations="Invented outputs; no accuracy, calibration or outcome claim.",
        model_version="1",
    )
    digest = evidence_service._digest(card.model_dump(mode="json"))

    def proposal(id, alt, leaf, payload, tool="external_a"):
        return ExternalProposal(
            id=id,
            subject=ProposalSubject(alternative_id=alt, criterion_id=leaf),
            payload=payload,
            tool_id=tool,
            tool_version="1",
            model_card_id="card",
            model_card_digest=digest,
            run_at=TIME,
            source_ids=[f"brief_{alt}"],
            confidence=ProposalConfidence(
                value=0.83,
                scale="unit_interval",
                meaning="Invented tool-reported confidence; metadata only",
            ),
        )

    items = [
        proposal("cell_a_first", "a", criterion, CategoricalProposal(value=proposed, unit=None)),
        proposal(
            "cell_a_second",
            "a",
            criterion,
            CategoricalProposal(value=selected, unit=None),
            "external_b",
        ),
        proposal("readiness_b", "b", "readiness", CategoricalProposal(value="early", unit=None)),
        proposal("numeric_b", "b", "measure", NumericProposal(value=0.91, unit="1")),
        proposal(
            "tag_a",
            "a",
            None,
            AlternativeTag(
                namespace="follow_up", label="check", text="Investigate the invented claim"
            ),
        ),
        proposal(
            "tag_b",
            "b",
            None,
            AlternativeTag(namespace="capacity", label="check", text="Reviewed annotation only"),
        ),
        proposal(
            "source_b",
            "b",
            None,
            SuggestedSourceClaim(
                source_id="brief_b",
                assertion="A pilot is reported" if screening else "A delivery window is reported",
                excerpt="Invented statement",
                location="table 1",
            ),
        ),
    ]
    human = EvidenceDossier(
        project_fingerprint=p.fingerprint(),
        claims=[
            Claim(
                id="human_a",
                alternative_id="a",
                criterion_id=criterion,
                value=selected,
                unit=None,
                source=sources["brief_a"],
                origin=Origin(kind="human", proposed_by="Illustrative reviewer"),
            )
        ],
    )
    intake = ProposalIntake(
        project_fingerprint=p.fingerprint(),
        sources=sources,
        model_cards={"card": card},
        proposals=sorted(items, key=lambda x: x.id),
        human_dossier=human,
    )
    workspace = svc.start(p, intake)
    events = []
    for id, status, correction in (
        ("cell_a_first", "corrected", CategoricalProposal(value=selected, unit=None)),
        ("readiness_b", "accepted", None),
        ("numeric_b", "rejected", None),
        ("tag_a", "rejected", None),
        ("tag_b", "accepted", None),
    ):
        original = next(x for x in items if x.id == id)
        event = ProposalReview(
            proposal_id=id,
            review=ProposalReviewDetails(
                status=status,
                reviewer="Illustrative reviewer",
                reviewed_at=TIME,
                note="Invented demonstration review",
                corrected_payload=correction,
                primary_source_id=original.source_ids[0] if status != "rejected" else None,
            ),
        )
        current = svc.inspect(p, workspace)
        workspace = svc.review(
            p, workspace, [event], current.review_digest, workspace.digest
        ).workspace
        events.append(event.model_dump(mode="json"))
    current = svc.inspect(p, workspace)
    bundle = svc.compile_bundle(p, workspace, current.review_digest, workspace.digest)
    csv, registries = imports.csv_files(intake)
    outputs = {
        f"{name}-project.json": to_json_text(p),
        f"{name}-intake.json": to_json_text(intake),
        f"{name}-proposals.csv": csv,
        f"{name}-registries.json": registries,
        f"{name}-reviews.json": json.dumps(events, indent=2) + "\n",
        f"{name}-workspace.json": to_json_text(workspace),
        f"{name}-compilation.json": to_json_text(bundle),
    }
    for filename, text in outputs.items():
        (ROOT / filename).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    for name in ("screening", "supplier"):
        build(name)
