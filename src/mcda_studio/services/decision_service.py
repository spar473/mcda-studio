"""Create and verify self-contained decision snapshots without replacing earlier records."""

import hashlib

from mcda_studio.domain.decision import DecisionDraft, DecisionRecord, EvidenceSnapshot
from mcda_studio.domain.errors import ModelEditError
from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.project import Project
from mcda_studio.services import evidence_service, results_service


def digest(record: DecisionRecord) -> str:
    body = record.model_dump(mode="json", exclude={"digest"})
    return hashlib.sha256(sealed_json(body).encode("utf-8")).hexdigest()


def sealed_json(body: object) -> str:
    """Canonical JSON of a record body; a supplied file with NaN/infinity is refused, not a 500.

    Records are sealed with strict JSON, so a genuine record can never contain them."""
    try:
        return results_service.canonical_json(body)
    except ValueError as exc:
        raise ModelEditError(
            "DECISION_RECORD_NONFINITE: decision record contains a nonfinite number"
        ) from exc


def create(
    project: Project,
    draft: DecisionDraft,
    previous: DecisionRecord | None = None,
    source_project: Project | None = None,
    dossier: EvidenceDossier | None = None,
) -> DecisionRecord:
    if draft.chosen_alternative_id not in project.alternative_ids():
        raise ModelEditError("DECISION_UNKNOWN_ALTERNATIVE: chosen alternative does not exist")
    if previous is not None:
        if previous.version != 1 or previous.digest != digest(previous):
            raise ModelEditError("DECISION_INVALID_PREDECESSOR: predecessor digest does not match")
        if previous.project.id != project.id:
            raise ModelEditError(
                "DECISION_DIFFERENT_PROJECT: predecessor belongs to another project"
            )
    if (source_project is None) != (dossier is None):
        raise ModelEditError(
            "DECISION_INCOMPLETE_EVIDENCE: provide both source project and dossier"
        )
    snapshot = None
    if source_project is not None and dossier is not None:
        preview = evidence_service.preview(source_project, dossier)
        compiled = evidence_service.compile_copy(source_project, dossier, preview.review_digest)
        if compiled.fingerprint() != project.fingerprint():
            raise ModelEditError(
                "DECISION_EVIDENCE_MISMATCH: dossier does not compile to this project"
            )
        snapshot = EvidenceSnapshot(
            source_project=source_project.model_copy(deep=True),
            dossier=dossier.model_copy(deep=True),
            review_digest=preview.review_digest,
            evidence_digest=preview.evidence_digest,
        )
    analyses = [results_service.analysis_record(project, cfg) for cfg in draft.configurations]
    record = DecisionRecord(
        digest="",
        previous_digest=previous.digest if previous else None,
        decision=draft.model_copy(deep=True),
        project=project.model_copy(deep=True),
        project_fingerprint=project.fingerprint(),
        analyses=analyses,
        evidence=snapshot,
    )
    record.digest = digest(record)
    return record
