"""Read-only inspection and explicit review proposals; no library or project writes."""

from collections import Counter
from typing import Literal

from mcda_studio.domain.common import DomainModel, Severity
from mcda_studio.domain.errors import ModelEditError, StaleRevisionError, ValidationFailed
from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.evidence_workspace import ClaimReview, EvidenceWorkspace
from mcda_studio.domain.measurements import Measurement
from mcda_studio.domain.project import Project
from mcda_studio.domain.validation import ValidationReport
from mcda_studio.services import evidence_service as evidence


class MeasurementSupport(DomainModel):
    alternative_id: str
    criterion_id: str
    measurement: Measurement | None
    status: Literal["supported", "unsupported", "unverified", "missing"]
    claim_ids: list[str]
    accepted_claim_ids: list[str]


class EvidenceInspection(DomainModel):
    workspace: EvidenceWorkspace
    dossier: EvidenceDossier
    preview: evidence.EvidencePreview
    support: list[MeasurementSupport]
    support_available: bool
    workspace_exportable: bool


def workspace_digest(workspace: EvidenceWorkspace) -> str:
    return evidence._digest(workspace.model_dump(mode="json", exclude={"digest"}))


def _replay(workspace: EvidenceWorkspace) -> EvidenceDossier:
    if workspace.digest != workspace_digest(workspace):
        raise ModelEditError("EVIDENCE_HISTORY_CHANGED: workspace digest does not match")
    if workspace.source_project.fingerprint() != workspace.original_dossier.project_fingerprint:
        raise ModelEditError("EVIDENCE_HISTORY_PROJECT: original dossier and project differ")
    dossier = workspace.original_dossier.model_copy(deep=True)
    counts = Counter(c.id for c in dossier.claims)
    for event in workspace.reviews:
        if counts[event.claim_id] != 1:
            raise ModelEditError("EVIDENCE_HISTORY_CLAIM: review needs one unique claim")
        next(c for c in dossier.claims if c.id == event.claim_id).review = event.review.model_copy(
            deep=True
        )
    return dossier


def inspect(project: Project, document: EvidenceDossier | EvidenceWorkspace) -> EvidenceInspection:
    if isinstance(document, EvidenceWorkspace):
        workspace = document.model_copy(deep=True)
        dossier = _replay(workspace)
    else:
        dossier = document.model_copy(deep=True)
        workspace = EvidenceWorkspace(
            source_project=project.model_copy(deep=True),
            original_dossier=dossier.model_copy(deep=True),
            digest="",
        )
        workspace.digest = workspace_digest(workspace)
    report = evidence.preview(project, dossier)
    available = not any(i.severity is Severity.ERROR for i in report.issues)
    support = []
    if available:
        raw = project.performance_index()
        accepted = {(c.alternative_id, c.criterion_id): c for c in report.changes}
        leaves = project.tree().leaves()
        for alt in project.alternatives:
            for leaf in leaves:
                cell = (alt.id, leaf)
                claims = [
                    c.id for c in dossier.claims if (c.alternative_id, c.criterion_id) == cell
                ]
                change = accepted.get(cell)
                matching = (
                    [change.claim_id]
                    if change is not None and cell in raw and change.after == raw[cell]
                    else []
                )
                status: Literal["supported", "unsupported", "unverified", "missing"] = (
                    "missing"
                    if cell not in raw
                    else "supported"
                    if matching
                    else "unverified"
                    if claims
                    else "unsupported"
                )
                support.append(
                    MeasurementSupport(
                        alternative_id=alt.id,
                        criterion_id=leaf,
                        measurement=raw.get(cell),
                        status=status,
                        claim_ids=claims,
                        accepted_claim_ids=matching,
                    )
                )
    return EvidenceInspection(
        workspace=workspace,
        dossier=dossier,
        preview=report,
        support=support,
        support_available=available,
        workspace_exportable=workspace.source_project.fingerprint() == dossier.project_fingerprint,
    )


def propose_review(
    project: Project,
    workspace: EvidenceWorkspace,
    event: ClaimReview,
    expected_review_digest: str,
) -> EvidenceInspection:
    """Return a candidate for explicit confirmation, preserving all input snapshots."""
    current = inspect(project, workspace)
    if current.preview.review_digest != expected_review_digest:
        raise StaleRevisionError("Evidence preview changed; inspect it again before reviewing.")
    if project.fingerprint() != current.dossier.project_fingerprint:
        raise StaleRevisionError("Dossier does not match this project revision.")
    matches = [c for c in current.dossier.claims if c.id == event.claim_id]
    if len(matches) != 1:
        raise ModelEditError("EVIDENCE_REVIEW_CLAIM: choose one unique claim")
    if not event.review.reviewer.strip():
        raise ModelEditError("EVIDENCE_REVIEWER: a named reviewer is required")
    if len(workspace.reviews) >= 2000:
        raise ModelEditError("EVIDENCE_HISTORY_LIMIT: workspace already has 2000 reviews")
    candidate = workspace.model_copy(deep=True)
    candidate.reviews.append(event.model_copy(deep=True))
    candidate.digest = workspace_digest(candidate)
    result = inspect(project, candidate)
    if event.review.status != "rejected":
        claim = matches[0]
        paths = {
            f"claims[{claim.id}]",
            f"performances[{claim.alternative_id},{claim.criterion_id}]",
        }
        errors = [
            i for i in result.preview.issues if i.severity is Severity.ERROR and i.path in paths
        ]
        if errors:
            raise ValidationFailed(ValidationReport(issues=errors))
    return result
