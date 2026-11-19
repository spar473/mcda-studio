"""Version-2 decision records: exact analyses, feasibility and traceable supporting artifacts.

Records are created in memory and exported by the caller; nothing replaces an earlier record. A
revision is a new record naming its predecessor's digest. Version-1 records remain readable.
"""

import hashlib
from collections.abc import Sequence
from typing import Literal

from pydantic import Field

from mcda_studio.domain.analysis_record import AnyAnalysisRecord
from mcda_studio.domain.common import DomainModel, Issue, Severity
from mcda_studio.domain.decision import DecisionDetails, DecisionRecord
from mcda_studio.domain.errors import McdaError, ModelEditError, ValidationFailed
from mcda_studio.domain.feasibility import FeasibilityResult
from mcda_studio.domain.measurements import Measurement
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.provenance import ProjectCopyReceipt
from mcda_studio.domain.validation import ValidationReport
from mcda_studio.services import decision_service, feasibility_service, results_service
from mcda_studio.services import derived_service as derived
from mcda_studio.services import evidence_compilation_service as evidence_compilation
from mcda_studio.services import provenance_service as provenance

MAX_ARTIFACTS = 8


class AnalysisSnapshot(DomainModel):
    """One requested configuration; an unavailable analysis is recorded, never dropped."""

    configuration: AnalysisConfiguration
    status: Literal["completed", "unavailable"]
    record: AnyAnalysisRecord | None
    reason: str
    issues: list[Issue]


class FeasibilitySnapshot(DomainModel):
    status: Literal["checked", "no_requirements", "unavailable"]
    result: FeasibilityResult | None
    issues: list[Issue]


class SupportingArtifact(DomainModel):
    artifact: evidence_compilation.EvidenceCompilation | derived.DerivedCompilation
    copy_receipt: ProjectCopyReceipt | None = None


class ArtifactAnchor(DomainModel):
    """Where an artifact's compiled project sits: the record's project, or the original project
    of another artifact in the record (a calculation compiled on top of compiled evidence)."""

    artifact_digest: str
    artifact_kind: Literal["evidence_compilation", "calculation_bundle"]
    relationship: Literal["compiled", "verified_copy"]
    anchored_to: Literal["record_project", "artifact_source"]
    anchor_artifact_digest: str | None


class MeasurementTrace(DomainModel):
    """Which retained artifact set each entered measurement, and what it replaced."""

    alternative_id: str
    criterion_id: str
    value: Measurement
    origin: Literal["evidence", "calculation", "entered"]
    artifact_digest: str | None
    reference_id: str | None  # claim or calculation id
    inputs: list[str]  # fundamental calculation sources; empty otherwise
    original_value: Measurement | None  # before the artifact replaced it; None if it was missing


class PredecessorSummary(DomainModel):
    version: int
    digest: str
    owner: str
    date: str
    outcome: Literal["selected", "deferred"]
    selected_alternative_id: str | None
    rationale: str
    project_fingerprint: str


class DecisionRecordV2(DomainModel):
    version: Literal[2] = 2
    digest: str
    previous_digest: str | None
    predecessor: PredecessorSummary | None
    decision: DecisionDetails
    project: Project
    project_fingerprint: str
    analyses: list[AnalysisSnapshot]
    feasibility: FeasibilitySnapshot
    supporting_artifacts: list[SupportingArtifact] = Field(max_length=MAX_ARTIFACTS)
    anchors: list[ArtifactAnchor]
    measurement_trace: list[MeasurementTrace]
    notices: list[Issue]


AnyDecisionRecord = DecisionRecord | DecisionRecordV2


def digest(record: DecisionRecordV2) -> str:
    body = record.model_dump(mode="json", exclude={"digest"})
    return hashlib.sha256(decision_service.sealed_json(body).encode("utf-8")).hexdigest()


def _analysis_digest_ok(record: AnyAnalysisRecord) -> bool:
    body = record.model_dump(mode="json", exclude={"record_digest"})
    expected = hashlib.sha256(decision_service.sealed_json(body).encode("utf-8")).hexdigest()
    return record.record_digest == expected


def _error(code: str, message: str, path: str) -> Issue:
    return Issue(severity=Severity.ERROR, code=code, message=message, path=path)


def _refuse(issues: list[Issue]) -> None:
    if issues:
        raise ValidationFailed(ValidationReport(issues=issues))


def _reference_issues(project: Project, details: DecisionDetails) -> list[Issue]:
    """Every alternative the decision names must exist in the recorded project. Shared by
    creation and verification, so a re-signed record cannot name an unknown alternative."""
    ids = set(project.alternative_ids())
    issues = [
        _error(
            "DECISION_UNKNOWN_ALTERNATIVE",
            f"considered alternative {a!r} is not in the project",
            f"decision.alternatives_considered[{k}]",
        )
        for k, a in enumerate(details.alternatives_considered)
        if a not in ids
    ]
    chosen = details.selected_alternative_id
    if chosen is not None and chosen not in ids:
        issues.append(
            _error(
                "DECISION_UNKNOWN_SELECTION",
                f"selected alternative {chosen!r} is not in the project",
                "decision.selected_alternative_id",
            )
        )
    return issues


def _analysis_issues(record: DecisionRecordV2) -> list[Issue]:
    """Each snapshot answers exactly its declared configuration: a completed one carries a
    sealed record of that method and configuration for this project; an unavailable one carries
    only its reason."""
    declared = record.decision.configurations
    if len(record.analyses) != len(declared):
        return [_error("DECISION_ANALYSIS_COUNT", "one snapshot per configuration", "analyses")]
    issues = []
    for k, (snapshot, configuration) in enumerate(zip(record.analyses, declared, strict=True)):
        path = f"analyses[{k}]"
        if snapshot.configuration != configuration:
            issues.append(
                _error("DECISION_ANALYSIS_CONFIGURATION", "snapshot differs from request", path)
            )
        sealed = snapshot.record
        if snapshot.status == "completed" and sealed is None:
            issues.append(
                _error("DECISION_ANALYSIS_RECORD_MISSING", "completed without a record", path)
            )
        if snapshot.status == "completed" and (snapshot.reason or snapshot.issues):
            issues.append(_error("DECISION_ANALYSIS_STATUS", "completed with a reason", path))
        if snapshot.status == "unavailable" and (sealed is not None or not snapshot.reason):
            issues.append(
                _error("DECISION_ANALYSIS_STATUS", "unavailable needs a reason, no record", path)
            )
        if sealed is None:
            continue
        envelope = getattr(sealed, "configuration", sealed.result.configuration)
        if (
            sealed.result.method != configuration.method
            or sealed.result.configuration != configuration
            or envelope != configuration
        ):
            issues.append(
                _error(
                    "DECISION_ANALYSIS_SUBSTITUTED",
                    "sealed analysis belongs to another method or configuration",
                    path,
                )
            )
        if not _analysis_digest_ok(sealed):
            issues.append(_error("DECISION_ANALYSIS_DIGEST", "sealed digest does not match", path))
        if sealed.result.project_fingerprint != record.project_fingerprint:
            issues.append(
                _error("DECISION_ANALYSIS_PROJECT", "sealed analysis is for another project", path)
            )
    return issues


def _issues(exc: McdaError) -> list[Issue]:
    return list(exc.report.issues) if isinstance(exc, ValidationFailed) else []


def _analysis(project: Project, configuration: AnalysisConfiguration) -> AnalysisSnapshot:
    try:
        record = results_service.analysis_record(project, configuration)
    except McdaError as exc:
        return AnalysisSnapshot(
            configuration=configuration.model_copy(deep=True),
            status="unavailable",
            record=None,
            reason="; ".join(f"[{i.code}] {i.message}" for i in _issues(exc)[:3])
            or f"{type(exc).__name__}: {str(exc).splitlines()[0]}",
            issues=_issues(exc),
        )
    return AnalysisSnapshot(
        configuration=configuration.model_copy(deep=True),
        status="completed",
        record=record,
        reason="",
        issues=[],
    )


def _feasibility(project: Project) -> FeasibilitySnapshot:
    if not project.requirements:
        return FeasibilitySnapshot(status="no_requirements", result=None, issues=[])
    try:
        result = feasibility_service.check_feasibility(project)
    except McdaError as exc:
        return FeasibilitySnapshot(status="unavailable", result=None, issues=_issues(exc))
    return FeasibilitySnapshot(status="checked", result=result, issues=[])


def _source(artifact: SupportingArtifact) -> Project:
    a = artifact.artifact
    if isinstance(a, evidence_compilation.EvidenceCompilation):
        return a.workspace.source_project
    return a.source_project


def _anchor(project: Project, artifacts: Sequence[SupportingArtifact]) -> list[ArtifactAnchor]:
    """Anchor every artifact by exact fingerprints, downstream first; refuse anything unrelated."""
    digests = [a.artifact.digest for a in artifacts]
    if len(set(digests)) != len(digests):
        raise ModelEditError("DECISION_DUPLICATE_ARTIFACT: each artifact may be cited once")
    # fingerprint -> (project at that point, artifact whose original project it is)
    frontier: dict[str, tuple[Project, str | None]] = {project.fingerprint(): (project, None)}
    used: set[str] = set()
    anchors: list[ArtifactAnchor] = []
    pending = list(artifacts)
    while pending:
        progress = []
        for item in pending:
            receipt = item.copy_receipt
            target = receipt.copy_fingerprint if receipt else item.artifact.compiled_fingerprint
            if target not in frontier:
                continue
            if target in used:
                raise ModelEditError(
                    "DECISION_AMBIGUOUS_ARTIFACT: two artifacts claim the same compiled project"
                )
            anchor_project, anchor_digest = frontier[target]
            binding = provenance.bind(anchor_project, item.artifact, receipt)
            if binding.relationship not in ("compiled", "verified_copy"):
                continue
            used.add(target)
            anchors.append(
                ArtifactAnchor(
                    artifact_digest=item.artifact.digest,
                    artifact_kind=binding.artifact_kind,
                    relationship=binding.relationship,
                    anchored_to="record_project" if anchor_digest is None else "artifact_source",
                    anchor_artifact_digest=anchor_digest,
                )
            )
            source = _source(item)
            frontier.setdefault(source.fingerprint(), (source, item.artifact.digest))
            progress.append(item)
        if not progress and any(item.copy_receipt for item in pending):
            raise ModelEditError(
                "DECISION_RECEIPT_UNMATCHED: a copy receipt describes neither this project nor "
                "the original project of a cited artifact (was the copy edited after import?)"
            )
        if not progress:
            raise ModelEditError(
                "DECISION_ARTIFACT_UNRELATED: an artifact compiles neither this project nor the "
                "original project of another cited artifact (supply its copy receipt if imported)"
            )
        pending = [item for item in pending if item not in progress]
    return anchors


def _trace(
    project: Project, artifacts: Sequence[SupportingArtifact], anchors: list[ArtifactAnchor]
) -> list[MeasurementTrace]:
    by_digest = {a.artifact.digest: a for a in artifacts}
    # Walk downstream to upstream: the first artifact that changed a cell set its value.
    chain: list[SupportingArtifact] = []
    current: str | None = None
    for _ in anchors:
        # Only record-anchored artifacts have no anchor digest, so this starts at the record.
        step = next((a for a in anchors if a.anchor_artifact_digest == current), None)
        if step is None:
            break
        chain.append(by_digest[step.artifact_digest])
        current = step.artifact_digest
    trace = []
    for p in project.performances:
        cell = (p.alternative_id, p.criterion_id)
        entry = MeasurementTrace(
            alternative_id=p.alternative_id,
            criterion_id=p.criterion_id,
            value=p.value,
            origin="entered",
            artifact_digest=None,
            reference_id=None,
            inputs=[],
            original_value=None,
        )
        for item in chain:
            a = item.artifact
            if isinstance(a, evidence_compilation.EvidenceCompilation):
                change = next(
                    (c for c in a.preview.changes if (c.alternative_id, c.criterion_id) == cell),
                    None,
                )
                if change is not None:
                    entry.origin, entry.reference_id = "evidence", change.claim_id
                    entry.artifact_digest, entry.original_value = a.digest, change.before
                    break
            else:
                calculation = next(
                    (
                        c
                        for c in a.preview.calculations
                        if (c.alternative_id, c.criterion_id) == cell
                    ),
                    None,
                )
                if calculation is not None:
                    entry.origin, entry.reference_id = "calculation", calculation.id
                    entry.artifact_digest, entry.original_value = a.digest, calculation.before
                    entry.inputs = list(calculation.source_ids)
                    break
        trace.append(entry)
    return trace


def _notices(
    project: Project,
    details: DecisionDetails,
    analyses: list[AnalysisSnapshot],
    feasibility: FeasibilitySnapshot,
    trace: list[MeasurementTrace],
    predecessor: PredecessorSummary | None,
) -> list[Issue]:
    notices = []

    def add(severity: Severity, code: str, message: str, path: str = "") -> None:
        notices.append(Issue(severity=severity, code=code, message=message, path=path))

    for k, a in enumerate(analyses):
        if a.status == "unavailable":
            add(Severity.WARNING, "DECISION_ANALYSIS_UNAVAILABLE", a.reason, f"analyses[{k}]")
    if len(details.alternatives_considered) != len(project.alternatives):
        add(
            Severity.INFO,
            "DECISION_ANALYSIS_UNIVERSE",
            f"Analyses use all {len(project.alternatives)} project alternatives; "
            f"{len(details.alternatives_considered)} are recorded as considered.",
        )
    chosen = details.selected_alternative_id
    status = (
        next((a for a in feasibility.result.alternatives if a.alternative_id == chosen), None)
        if feasibility.result is not None
        else None
    )
    if status is not None:
        if status.failed:
            add(
                Severity.WARNING,
                "DECISION_SELECTED_FAILS_REQUIREMENT",
                f"The selected alternative fails mandatory requirement(s): "
                f"{', '.join(status.failed)}.",
            )
        if status.unknown:
            add(
                Severity.WARNING,
                "DECISION_SELECTED_UNRESOLVED_REQUIREMENT",
                f"Requirement(s) unresolved for the selected alternative: "
                f"{', '.join(status.unknown)}.",
            )
    entered = sum(t.origin == "entered" for t in trace)
    if entered:
        add(
            Severity.INFO,
            "DECISION_MEASUREMENTS_WITHOUT_ARTIFACT",
            f"{entered} measurement(s) were entered directly; no cited artifact sets them.",
        )
    if predecessor is not None and predecessor.project_fingerprint != project.fingerprint():
        add(
            Severity.INFO,
            "DECISION_PROJECT_CHANGED",
            "The project differs from the one recorded by the predecessor.",
        )
    return notices


def _summary(previous: DecisionRecord | DecisionRecordV2) -> PredecessorSummary:
    if isinstance(previous, DecisionRecordV2):
        if previous.digest != digest(previous):
            raise ModelEditError("DECISION_INVALID_PREDECESSOR: predecessor digest does not match")
        verify(previous)
        d = previous.decision
        return PredecessorSummary(
            version=2,
            digest=previous.digest,
            owner=d.owner,
            date=d.date.isoformat(),
            outcome=d.outcome,
            selected_alternative_id=d.selected_alternative_id,
            rationale=d.rationale,
            project_fingerprint=previous.project_fingerprint,
        )
    if previous.digest != decision_service.digest(previous):
        raise ModelEditError("DECISION_INVALID_PREDECESSOR: predecessor digest does not match")
    _refuse(_v1_reference_issues(previous))
    v1 = previous.decision
    return PredecessorSummary(
        version=1,
        digest=previous.digest,
        owner=v1.owner,
        date=v1.date.isoformat(),
        outcome="selected",
        selected_alternative_id=v1.chosen_alternative_id,
        rationale=v1.rationale,
        project_fingerprint=previous.project_fingerprint,
    )


def _v1_reference_issues(record: DecisionRecord) -> list[Issue]:
    if record.decision.chosen_alternative_id in record.project.alternative_ids():
        return []
    return [
        _error(
            "DECISION_UNKNOWN_SELECTION",
            "chosen alternative is not in the recorded project",
            "decision.chosen_alternative_id",
        )
    ]


def create(
    project: Project,
    details: DecisionDetails,
    artifacts: Sequence[SupportingArtifact] = (),
    previous: DecisionRecord | DecisionRecordV2 | None = None,
) -> DecisionRecordV2:
    """Snapshot the exact project, requested analyses and cited artifacts; nothing is written."""
    _refuse(_reference_issues(project, details))
    if len(artifacts) > MAX_ARTIFACTS:
        raise ModelEditError(f"DECISION_ARTIFACT_LIMIT: cite at most {MAX_ARTIFACTS} artifacts")
    predecessor = _summary(previous) if previous is not None else None
    if previous is not None and previous.project.id != project.id:
        raise ModelEditError("DECISION_DIFFERENT_PROJECT: predecessor belongs to another project")
    cited = [a.model_copy(deep=True) for a in artifacts]
    anchors = _anchor(project, cited)
    trace = _trace(project, cited, anchors)
    analyses = [_analysis(project, c) for c in details.configurations]
    feasibility = _feasibility(project)
    record = DecisionRecordV2(
        digest="",
        previous_digest=predecessor.digest if predecessor else None,
        predecessor=predecessor,
        decision=details.model_copy(deep=True),
        project=project.model_copy(deep=True),
        project_fingerprint=project.fingerprint(),
        analyses=analyses,
        feasibility=feasibility,
        supporting_artifacts=cited,
        anchors=anchors,
        measurement_trace=trace,
        notices=_notices(project, details, analyses, feasibility, trace, predecessor),
    )
    record.digest = digest(record)
    return record


def verify(record: DecisionRecordV2) -> DecisionRecordV2:
    """Check the digest and re-derive everything deterministic from the retained inputs.

    Analyses are checked by their own sealed digests rather than rerun: SMAA-2 repeatability is
    promised only in the environment each result records."""
    if record.digest != digest(record):
        raise ModelEditError("DECISION_RECORD_CHANGED: decision record digest does not match")
    project = record.project
    if record.project_fingerprint != project.fingerprint():
        raise ModelEditError("DECISION_RECORD_MISMATCH: project fingerprint does not match")
    _refuse(_reference_issues(project, record.decision) + _analysis_issues(record))
    anchors = _anchor(project, record.supporting_artifacts)
    trace = _trace(project, record.supporting_artifacts, anchors)
    feasibility = _feasibility(project)
    expected = (
        anchors,
        trace,
        feasibility,
        _notices(project, record.decision, record.analyses, feasibility, trace, record.predecessor),
    )
    if expected != (record.anchors, record.measurement_trace, record.feasibility, record.notices):
        raise ModelEditError("DECISION_RECORD_MISMATCH: decision record does not reproduce")
    if (record.predecessor is None) != (record.previous_digest is None) or (
        record.predecessor is not None and record.predecessor.digest != record.previous_digest
    ):
        raise ModelEditError("DECISION_RECORD_MISMATCH: predecessor link is inconsistent")
    return record


class DecisionRecordInspection(DomainModel):
    """A verified record, read historically against whatever project is open now."""

    record: DecisionRecordV2 | DecisionRecord
    current_project_matches: bool
    predecessor_verified: Literal[True] | None  # None when no predecessor file was supplied


def inspect(
    project: Project,
    record: DecisionRecordV2 | DecisionRecord,
    predecessor: DecisionRecordV2 | DecisionRecord | None = None,
) -> DecisionRecordInspection:
    if isinstance(record, DecisionRecordV2):
        verify(record)
    elif record.digest != decision_service.digest(record):
        raise ModelEditError("DECISION_RECORD_CHANGED: decision record digest does not match")
    else:
        _refuse(_v1_reference_issues(record))
    checked = None
    if predecessor is not None:
        summary = _summary(predecessor)
        # Without the predecessor file a re-signed summary cannot be told apart; with it, any
        # difference is refused rather than reported.
        if record.previous_digest != summary.digest or (
            isinstance(record, DecisionRecordV2) and record.predecessor != summary
        ):
            raise ModelEditError("DECISION_PREDECESSOR_MISMATCH: not this record's predecessor")
        checked = True
    return DecisionRecordInspection(
        record=record.model_copy(deep=True),
        current_project_matches=record.project_fingerprint == project.fingerprint(),
        predecessor_verified=checked,
    )
