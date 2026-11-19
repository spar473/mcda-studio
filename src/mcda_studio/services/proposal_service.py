"""Local external proposals: history replay, exact comparisons and existing evidence compilation."""

from collections import defaultdict
from typing import Literal

from pydantic import Field

from mcda_studio.domain.common import DomainModel, Issue, Severity
from mcda_studio.domain.errors import ModelEditError, StaleRevisionError, ValidationFailed
from mcda_studio.domain.evidence import Claim, EvidenceDossier, Origin, Review
from mcda_studio.domain.external_proposals import (
    AlternativeTag,
    CategoricalProposal,
    ExternalProposal,
    ExternalProposals,
    NumericProposal,
    ProposalIntake,
    ProposalPayload,
    ProposalRegistrySupply,
    ProposalReview,
    ProposalReviewDetails,
    SuggestedSourceClaim,
)
from mcda_studio.domain.project import Project
from mcda_studio.domain.scales import ScaleType
from mcda_studio.domain.validation import ValidationReport
from mcda_studio.services import evidence_compilation_service as compilations
from mcda_studio.services import evidence_service as evidence
from mcda_studio.services import evidence_workspace_service as workspaces
from mcda_studio.services.questions_service import Question

SimpleRelation = Literal["agreement", "disagreement", "incomparable"]
Relation = Literal["agreement", "disagreement", "incomparable", "mixed"]


class ProposalRow(DomainModel):
    original: ExternalProposal
    effective: ProposalPayload
    review: ProposalReviewDetails | None
    issues: list[Issue]
    bulk_eligible: bool
    original_relation: Relation | None = None
    original_relations: list[SimpleRelation] = Field(default_factory=list)
    effective_relations: list[SimpleRelation] = Field(default_factory=list)
    effective_relation: Relation | None = None


class ProposalColumn(DomainModel):
    id: str
    origin: Literal["tool", "human"]
    tool_id: str | None
    original_value: float | str | None
    effective_value: float | str | None
    original_unit: str | None
    effective_unit: str | None
    status: str
    sources: list[str]
    source_classifications: list[str]
    range_lower: float | None = None
    range_upper: float | None = None


class ProposalCell(DomainModel):
    alternative_id: str
    criterion_id: str
    columns: list[ProposalColumn]


class ReviewedAnnotation(DomainModel):
    proposal_id: str
    subject_alternative_id: str
    payload: AlternativeTag | SuggestedSourceClaim
    review: ProposalReviewDetails


class ProposalInspection(DomainModel):
    workspace: ExternalProposals
    current_fingerprint: str
    stale: bool
    rows: list[ProposalRow]
    comparisons: list[ProposalCell]
    comparison_target: str | None
    comparison_targets: list[str]
    preview: evidence.EvidencePreview
    dossier: EvidenceDossier
    annotations: list[ReviewedAnnotation]
    questions: list[Question]
    review_digest: str
    limitations: list[str]


class ProposalCompilation(DomainModel):
    artifact_kind: Literal["proposal_compilation"] = "proposal_compilation"
    version: Literal[1] = 1
    workspace: ExternalProposals
    evidence: compilations.EvidenceCompilation
    annotations: list[ReviewedAnnotation]
    digest: str


def workspace_digest(workspace: ExternalProposals) -> str:
    return evidence._digest(workspace.model_dump(mode="json", exclude={"digest"}))


def _error(code: str, message: str, proposal_id: str = "") -> Issue:
    return Issue(
        severity=Severity.ERROR,
        code=code,
        message=message,
        path=f"proposals[{proposal_id}]" if proposal_id else "",
    )


def _refuse(issues: list[Issue]) -> None:
    if issues:
        raise ValidationFailed(ValidationReport(issues=issues))


def measurement(payload: ProposalPayload) -> tuple[float | str, str | None] | None:
    if isinstance(payload, NumericProposal | CategoricalProposal):
        return payload.value, payload.unit
    if isinstance(payload, SuggestedSourceClaim) and payload.measurement is not None:
        return payload.measurement.value, payload.measurement.unit
    return None


def _issues(
    project: Project | None,
    intake: ProposalIntake,
    proposal: ExternalProposal,
    payload: ProposalPayload,
    review: ProposalReviewDetails | None = None,
) -> list[Issue]:
    issues = []

    def fail(code: str, message: str) -> None:
        issues.append(_error(code, message, proposal.id))

    if project is None:
        fail(
            "PROPOSAL_SOURCE_SNAPSHOT", "original project snapshot unavailable; inspect/export only"
        )
    elif proposal.subject.alternative_id not in project.alternative_ids():
        fail(
            "PROPOSAL_ALTERNATIVE",
            "unknown alternative; use a new linked proposal to change subject",
        )
    card = intake.model_cards.get(proposal.model_card_id)
    if card is None or evidence._digest(card.model_dump(mode="json")) != proposal.model_card_digest:
        fail("PROPOSAL_MODEL_CARD", "supply the exact locally referenced model card and digest")
    refs = list(proposal.source_ids)
    if isinstance(payload, SuggestedSourceClaim):
        refs.append(payload.source_id)
    if review:
        refs += review.supporting_source_ids
        if review.primary_source_id:
            refs.append(review.primary_source_id)
    if not refs or any(ref not in intake.sources for ref in refs):
        fail(
            "PROPOSAL_SOURCES", "every cited source must resolve locally; at least one is required"
        )
    cell = measurement(payload)
    criterion_id = proposal.subject.criterion_id
    if cell is not None and project is not None:
        tree = project.tree()
        if criterion_id is None or criterion_id not in tree or not tree.is_leaf(criterion_id):
            fail("PROPOSAL_CRITERION", "measurement subject must be a known leaf criterion")
        else:
            scale = tree.node(criterion_id).scale
            value, unit = cell
            if scale is None:
                fail("PROPOSAL_SCALE", "criterion needs a measurement scale")
            elif unit != scale.unit:
                fail("PROPOSAL_UNIT", "measurement unit must match the criterion exactly")
            elif scale.is_numeric:
                if isinstance(value, str) or (scale.type is ScaleType.RATIO and value < 0):
                    fail("PROPOSAL_VALUE", "numeric measurement is invalid for this scale")
            elif not isinstance(value, str) or value not in scale.labels:
                fail("PROPOSAL_LABEL", "review a label from the declared criterion vocabulary")
            if scale is not None and (
                (isinstance(payload, NumericProposal) and not scale.is_numeric)
                or (isinstance(payload, CategoricalProposal) and not scale.is_labelled)
            ):
                fail("PROPOSAL_KIND", "cell proposal kind does not match the measurement scale")
    elif criterion_id is not None and project is not None:
        tree = project.tree()
        if criterion_id not in tree or not tree.is_leaf(criterion_id):
            fail("PROPOSAL_CRITERION", "source assertion criterion must be a known leaf")
    return issues


def _effective(proposal: ExternalProposal, review: ProposalReviewDetails | None) -> ProposalPayload:
    return (
        review.corrected_payload
        if review and review.corrected_payload is not None
        else proposal.payload
    )


def _check_event(
    project: Project,
    intake: ProposalIntake,
    latest: dict[str, ProposalReviewDetails],
    event: ProposalReview,
) -> None:
    proposals = {p.id: p for p in intake.proposals}
    proposal = proposals.get(event.proposal_id)
    if proposal is None:
        raise ModelEditError("PROPOSAL_REVIEW_ID: choose an existing unique proposal")
    review = event.review
    if (
        review.corrected_payload is not None
        and review.corrected_payload.kind != proposal.payload.kind
    ):
        raise ModelEditError("PROPOSAL_CORRECTION_KIND: changing kind needs a new linked proposal")
    if review.status == "rejected":
        return
    payload = _effective(proposal, review)
    _refuse(_issues(project, intake, proposal, payload, review))
    if review.primary_source_id is None or review.primary_source_id not in intake.sources:
        _refuse(
            [
                _error(
                    "PROPOSAL_PRIMARY_SOURCE",
                    "explicitly select a resolved primary source",
                    proposal.id,
                )
            ]
        )
    if measurement(payload) is not None:
        for other_id, other_review in latest.items():
            other = proposals[other_id]
            if (
                other_id != proposal.id
                and other_review.status != "rejected"
                and other.subject == proposal.subject
                and measurement(_effective(other, other_review)) is not None
            ):
                _refuse(
                    [
                        _error(
                            "PROPOSAL_MULTIPLE_ACCEPTED",
                            "reject the earlier active cell claim first",
                            proposal.id,
                        )
                    ]
                )


def _merge_registry[T](registry: dict[str, T], additions: dict[str, T]) -> None:
    for key, value in additions.items():
        if key in registry and registry[key] != value:
            raise ModelEditError("PROPOSAL_REGISTRY_REPLACE: original entries cannot change")
        registry[key] = value
    if len(registry) > 2000:
        raise ModelEditError("PROPOSAL_REGISTRY_LIMIT: at most 2000 entries per registry")


def resolved_intake(workspace: ExternalProposals) -> ProposalIntake:
    result = workspace.intake.model_copy(deep=True)
    for supply in workspace.registry_supplies:
        _merge_registry(result.sources, supply.sources)
        _merge_registry(result.model_cards, supply.model_cards)
    return result


def supply_registries(
    project: Project,
    workspace: ExternalProposals,
    supply: ProposalRegistrySupply,
    expected_workspace_digest: str,
) -> ProposalInspection:
    _replay(workspace)
    if (
        workspace.source_project is None
        or project.fingerprint() != workspace.intake.project_fingerprint
        or expected_workspace_digest != workspace.digest
    ):
        raise StaleRevisionError("Registry context changed; no entries were rebound")
    if len(workspace.registry_supplies) >= 2000:
        raise ModelEditError("PROPOSAL_REGISTRY_LIMIT: at most 2000 registry additions")
    candidate = workspace.model_copy(deep=True)
    candidate.registry_supplies.append(supply.model_copy(deep=True))
    candidate.digest = workspace_digest(candidate)
    return inspect(project, candidate)


def _export_size(document: DomainModel) -> None:
    # The importer also uses this bound before constructing typed objects.
    from mcda_studio.services.proposal_import_service import _bounded

    _bounded(document.model_dump(mode="json"))
    if len(document.model_dump_json(indent=2).encode("utf-8")) + 1 > 8_000_000:
        raise ModelEditError("PROPOSAL_FILE_LIMIT: exported sidecar or bundle exceeds 8 MB")


def _replay(workspace: ExternalProposals) -> dict[str, ProposalReviewDetails]:
    _export_size(workspace)
    if workspace.digest != workspace_digest(workspace):
        raise ModelEditError("PROPOSAL_HISTORY_CHANGED: workspace digest does not match")
    if workspace.source_project is None:
        if workspace.reviews or workspace.registry_supplies:
            raise ModelEditError(
                "PROPOSAL_HISTORY_SOURCE: reviewed history requires its exact source"
            )
        return {}
    if workspace.source_project.fingerprint() != workspace.intake.project_fingerprint:
        raise ModelEditError("PROPOSAL_HISTORY_PROJECT: source snapshot does not match intake")
    latest: dict[str, ProposalReviewDetails] = {}
    intake = resolved_intake(workspace)
    for event in workspace.reviews:
        _check_event(workspace.source_project, intake, latest, event)
        latest[event.proposal_id] = event.review
    return latest


def start(project: Project, intake: ProposalIntake) -> ExternalProposals:
    result = ExternalProposals(
        source_project=(
            project.model_copy(deep=True)
            if project.fingerprint() == intake.project_fingerprint
            else None
        ),
        intake=intake.model_copy(deep=True),
        digest="",
    )
    result.digest = workspace_digest(result)
    _export_size(result)
    return result


def _adapt(
    workspace: ExternalProposals, latest: dict[str, ProposalReviewDetails]
) -> EvidenceDossier:
    claims = []
    intake = resolved_intake(workspace)
    for proposal in intake.proposals:
        review = latest.get(proposal.id)
        if review is None or review.status == "rejected":
            continue
        payload = _effective(proposal, review)
        cell = measurement(payload)
        if cell is None:
            continue
        value, unit = cell
        original_cell = measurement(proposal.payload)
        original_value = original_cell[0] if original_cell is not None else value
        assert review.primary_source_id is not None
        assert proposal.subject.criterion_id is not None
        claims.append(
            Claim(
                id=proposal.id,
                alternative_id=proposal.subject.alternative_id,
                criterion_id=proposal.subject.criterion_id,
                value=original_value,
                unit=unit,
                source=intake.sources[review.primary_source_id],
                origin=Origin(
                    kind="tool",
                    proposed_by="External proposal",
                    tool_id=proposal.tool_id,
                    tool_version=proposal.tool_version,
                ),
                review=Review(
                    status=review.status,
                    reviewer=review.reviewer,
                    reviewed_at=review.reviewed_at,
                    corrected_value=value if review.status == "corrected" else None,
                    note=review.note,
                ),
            )
        )
    return EvidenceDossier(project_fingerprint=workspace.intake.project_fingerprint, claims=claims)


def _annotations(
    workspace: ExternalProposals, latest: dict[str, ProposalReviewDetails]
) -> list[ReviewedAnnotation]:
    result = []
    for proposal in workspace.intake.proposals:
        review = latest.get(proposal.id)
        if review is None or review.status == "rejected":
            continue
        payload = _effective(proposal, review)
        if isinstance(payload, AlternativeTag | SuggestedSourceClaim):
            result.append(
                ReviewedAnnotation(
                    proposal_id=proposal.id,
                    subject_alternative_id=proposal.subject.alternative_id,
                    payload=payload,
                    review=review,
                )
            )
    return result


def _comparisons(
    workspace: ExternalProposals, latest: dict[str, ProposalReviewDetails]
) -> list[ProposalCell]:
    intake = resolved_intake(workspace)
    cells: dict[tuple[str, str], list[ProposalColumn]] = defaultdict(list)
    for proposal in intake.proposals:
        original = measurement(proposal.payload)
        effective = measurement(_effective(proposal, latest.get(proposal.id)))
        if (original is None and effective is None) or proposal.subject.criterion_id is None:
            continue
        refs = list(proposal.source_ids)
        review = latest.get(proposal.id)
        if isinstance(_effective(proposal, review), SuggestedSourceClaim):
            assertion = _effective(proposal, review)
            if isinstance(assertion, SuggestedSourceClaim):
                refs.append(assertion.source_id)
        if review is not None:
            if review.primary_source_id:
                refs.append(review.primary_source_id)
            refs.extend(review.supporting_source_ids)
        refs = list(dict.fromkeys(refs))
        cells[(proposal.subject.alternative_id, proposal.subject.criterion_id)].append(
            ProposalColumn(
                id=proposal.id,
                origin="tool",
                tool_id=proposal.tool_id,
                original_value=original[0] if original is not None else None,
                original_unit=original[1] if original is not None else None,
                effective_value=effective[0] if effective is not None else None,
                effective_unit=effective[1] if effective is not None else None,
                status=latest[proposal.id].status if proposal.id in latest else "pending",
                sources=[intake.sources[s].reference if s in intake.sources else s for s in refs],
                source_classifications=[
                    intake.sources[s].classification if s in intake.sources else "unresolved"
                    for s in refs
                ],
            )
        )
    human = intake.human_dossier
    if human is not None:
        if human.project_fingerprint != intake.project_fingerprint:
            raise ModelEditError(
                "PROPOSAL_HUMAN_PROJECT: comparison dossier belongs to another revision"
            )
        if len({c.id for c in human.claims}) != len(human.claims):
            raise ModelEditError("PROPOSAL_HUMAN_IDS: comparison claims need unique IDs")
        for claim in human.claims:
            if claim.origin.kind != "human":
                raise ModelEditError(
                    "PROPOSAL_HUMAN_ORIGIN: comparison dossier must contain human claims"
                )
            value = (
                claim.review.corrected_value
                if claim.review and claim.review.status == "corrected"
                else claim.value
            )
            assert value is not None
            cells[(claim.alternative_id, claim.criterion_id)].append(
                ProposalColumn(
                    id=f"human:{claim.id}",
                    origin="human",
                    tool_id=None,
                    original_value=claim.value,
                    effective_value=value,
                    original_unit=claim.unit,
                    effective_unit=claim.unit,
                    status=claim.review.status if claim.review else "pending",
                    sources=[claim.source.reference],
                    source_classifications=[claim.source.classification],
                    range_lower=claim.uncertainty_lower,
                    range_upper=claim.uncertainty_upper,
                )
            )
    return [
        ProposalCell(alternative_id=a, criterion_id=c, columns=columns)
        for (a, c), columns in sorted(cells.items())
    ]


def _relations(
    column: ProposalColumn, others: list[ProposalColumn], effective: bool
) -> list[SimpleRelation]:
    unit = column.effective_unit if effective else column.original_unit
    value = column.effective_value if effective else column.original_value
    relations: set[SimpleRelation] = set()
    for other in others:
        other_unit = other.effective_unit if effective else other.original_unit
        other_value = other.effective_value if effective else other.original_value
        relations.add(
            "incomparable"
            if value is None
            or other_value is None
            or unit != other_unit
            or isinstance(value, str) != isinstance(other_value, str)
            else "agreement"
            if value == other_value
            else "disagreement"
        )
    return sorted(relations)


def _summary(relations: list[SimpleRelation]) -> Relation | None:
    return "mixed" if len(relations) > 1 else relations[0] if relations else None


def inspect(
    project: Project, workspace: ExternalProposals, comparison_target: str | None = None
) -> ProposalInspection:
    latest = _replay(workspace)
    intake = resolved_intake(workspace)
    stale = (
        workspace.source_project is None
        or project.fingerprint() != workspace.intake.project_fingerprint
    )
    source = workspace.source_project
    dossier = _adapt(workspace, latest)
    preview = evidence.preview(source or project, dossier)
    comparisons = _comparisons(workspace, latest)
    columns = {col.id: (col, cell.columns) for cell in comparisons for col in cell.columns}
    targets = sorted({f"tool:{p.tool_id}" for p in workspace.intake.proposals})
    if workspace.intake.human_dossier is not None:
        targets.append("human")
    if comparison_target is not None and comparison_target not in targets:
        raise ModelEditError("PROPOSAL_COMPARISON_TARGET: choose a listed tool or human comparison")
    rows, questions = [], []
    for proposal in workspace.intake.proposals:
        review = latest.get(proposal.id)
        payload = _effective(proposal, review)
        issues = _issues(source, intake, proposal, payload, review)
        original_relations: list[SimpleRelation] = []
        effective_relations: list[SimpleRelation] = []
        if comparison_target is not None and proposal.id in columns:
            column, peers = columns[proposal.id]
            others = [
                p
                for p in peers
                if p.id != column.id
                and (
                    p.origin == "human"
                    if comparison_target == "human"
                    else p.origin == "tool" and f"tool:{p.tool_id}" == comparison_target
                )
            ]
            original_relations = _relations(column, others, False)
            effective_relations = _relations(column, others, True)
        rows.append(
            ProposalRow(
                original=proposal,
                effective=payload,
                review=review,
                issues=issues,
                bulk_eligible=not stale and not issues,
                original_relation=_summary(original_relations),
                effective_relation=_summary(effective_relations),
                original_relations=original_relations,
                effective_relations=effective_relations,
            )
        )
        if review is None or (issues and review.status != "rejected"):
            questions.append(
                Question(
                    group="evidence_quality",
                    code="PROPOSAL_PENDING",
                    question=f"Should proposal {proposal.id} be accepted, corrected or rejected?",
                    why="; ".join(i.message for i in issues)
                    or "Imported output awaits a human review.",
                    evidence="Inspect the local model card and cited sources; record a review.",
                    alternative_id=proposal.subject.alternative_id,
                    criterion_id=proposal.subject.criterion_id,
                )
            )
    for cell in comparisons:
        groups: dict[tuple[str | None, bool], set[float | str]] = defaultdict(set)
        for column in cell.columns:
            if column.original_value is not None:
                groups[(column.original_unit, isinstance(column.original_value, str))].add(
                    column.original_value
                )
        if any(len(values) > 1 for values in groups.values()):
            questions.append(
                Question(
                    group="evidence_quality",
                    code="PROPOSAL_DISAGREEMENT",
                    question="Which differing proposal is supported?",
                    why="Original comparable values differ; reviews do not erase this comparison.",
                    evidence="Compare originals, reviews and sources side by side; never average.",
                    alternative_id=cell.alternative_id,
                    criterion_id=cell.criterion_id,
                )
            )
        if len(groups) > 1 or any(c.original_value is None for c in cell.columns):
            questions.append(
                Question(
                    group="evidence_quality",
                    code="PROPOSAL_INCOMPARABLE",
                    question="Which explicit measurement and unit should this comparison use?",
                    why="Missing measurements or different units/types cannot be compared.",
                    evidence="Review the originals; supply an explicit compatible measurement.",
                    alternative_id=cell.alternative_id,
                    criterion_id=cell.criterion_id,
                )
            )
    if stale:
        questions.append(
            Question(
                group="evidence_quality",
                code="PROPOSAL_STALE_PROJECT",
                question="Which project revision does this intake describe?",
                why="The source snapshot is unavailable or differs from the open project.",
                evidence=(
                    "Inspect or export historically; new actions require the original revision."
                ),
            )
        )
    body = {
        "current": project.fingerprint(),
        "workspace": workspace.digest,
        "preview": preview.review_digest,
        "comparison_target": comparison_target,
    }
    return ProposalInspection(
        workspace=workspace.model_copy(deep=True),
        current_fingerprint=project.fingerprint(),
        stale=stale,
        rows=rows,
        comparisons=comparisons,
        comparison_target=comparison_target,
        comparison_targets=targets,
        preview=preview,
        dossier=dossier,
        annotations=_annotations(workspace, latest),
        questions=questions,
        review_digest=evidence._digest(body),
        limitations=[
            "Agreement is descriptive; shared sources remain disclosed.",
            "Confidence is metadata only; review identities and times are local assertions.",
            "Digests detect accidental changes, not deliberate rewriting or authenticity.",
        ],
    )


def review(
    project: Project,
    workspace: ExternalProposals,
    events: list[ProposalReview],
    expected_review_digest: str,
    expected_workspace_digest: str,
    bulk: bool = False,
    comparison_target: str | None = None,
) -> ProposalInspection:
    current = inspect(project, workspace, comparison_target)
    if current.stale:
        raise StaleRevisionError(
            "Proposal source differs from the open project; no automatic rebinding."
        )
    if (
        current.review_digest != expected_review_digest
        or workspace.digest != expected_workspace_digest
    ):
        raise StaleRevisionError("Proposal review context changed; inspect it again.")
    if (
        not events
        or len({e.proposal_id for e in events}) != len(events)
        or (len(events) > 1 and not bulk)
    ):
        raise ModelEditError(
            "PROPOSAL_SELECTION: select unique proposals; multiple items require bulk review"
        )
    if len(workspace.reviews) + len(events) > 2000:
        raise ModelEditError("PROPOSAL_HISTORY_LIMIT: at most 2000 review events")
    if bulk:
        common = {(e.review.reviewer, e.review.reviewed_at, e.review.note) for e in events}
        if len(common) != 1:
            raise ModelEditError(
                "PROPOSAL_BULK_METADATA: reviewer, time and note must be identical"
            )
        eligible = {r.original.id for r in current.rows if r.bulk_eligible}
        if any(e.proposal_id not in eligible for e in events):
            raise ModelEditError(
                "PROPOSAL_BULK_BLOCKED: exclude blocked items and unresolved sources/cards"
            )
    candidate = workspace.model_copy(deep=True)
    latest = _replay(candidate)
    intake = resolved_intake(candidate)
    for event in events:
        _check_event(project, intake, latest, event)
        candidate.reviews.append(event.model_copy(deep=True))
        latest[event.proposal_id] = event.review
    candidate.digest = workspace_digest(candidate)
    return inspect(project, candidate, comparison_target)


def compile_bundle(
    project: Project,
    workspace: ExternalProposals,
    expected_review_digest: str,
    expected_workspace_digest: str,
    comparison_target: str | None = None,
) -> ProposalCompilation:
    current = inspect(project, workspace, comparison_target)
    if (
        current.stale
        or current.review_digest != expected_review_digest
        or workspace.digest != expected_workspace_digest
    ):
        raise StaleRevisionError(
            "Proposal compilation acknowledgement changed; review the current preview."
        )
    dossier = _adapt(workspace, _replay(workspace))
    ordinary = workspaces.inspect(project, dossier)
    compiled = compilations.compilation_bundle(
        project, ordinary.workspace, ordinary.preview.review_digest, ordinary.workspace.digest
    )
    result = ProposalCompilation(
        workspace=workspace.model_copy(deep=True),
        evidence=compiled,
        annotations=current.annotations,
        digest="",
    )
    result.digest = evidence._digest(result.model_dump(mode="json", exclude={"digest"}))
    _export_size(result)
    return result


def verify(bundle: ProposalCompilation) -> ProposalCompilation:
    if bundle.digest != evidence._digest(bundle.model_dump(mode="json", exclude={"digest"})):
        raise ModelEditError("PROPOSAL_BUNDLE_CHANGED: compilation digest does not match")
    project, workspace = bundle.workspace.source_project, bundle.workspace
    if project is None:
        raise ModelEditError(
            "PROPOSAL_BUNDLE_SOURCE: compilation requires an exact source snapshot"
        )
    current = inspect(project, workspace)
    rebuilt = compile_bundle(project, workspace, current.review_digest, workspace.digest)
    if rebuilt != bundle:
        raise ModelEditError("PROPOSAL_BUNDLE_MISMATCH: retained compilation does not reproduce")
    return bundle
