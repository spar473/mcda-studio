"""Decision impact for qualitative and ordinal cells (``docs/design/decision-impact.md``).

For each scored labelled cell, every other label of its scale is tried **one cell at a time with
everything else fixed**, using the existing MAVT and class functions: the value evaluator the
engine built, ``overall_values`` (the same ``fsum``), ``rank_values`` (competition ranks, 1e-12
tolerance) and ``class_index``. Nothing is re-implemented. Only the changed alternative's row can
move, so only its overall value is recomputed.

The result is read-only and opt-in: it adds no stored format and leaves Open Questions and every
existing output unchanged. It is not robustness over combinations of cells.
"""

import math
from typing import Literal

from mcda_studio.domain.common import DomainModel, Id
from mcda_studio.domain.criteria import QualitativeValueFunction
from mcda_studio.domain.errors import AnalysisLimitError, McdaError, ValidationFailed
from mcda_studio.domain.evidence import Claim, EvidenceDossier
from mcda_studio.domain.external_proposals import ExternalProposals
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.methods.mavt.aggregation import overall_values, prepare_mavt, rank_values
from mcda_studio.methods.mavt.value_functions import build_evaluator
from mcda_studio.methods.sorting.classes import check_sorting, class_index, lower_boundaries
from mcda_studio.services import evidence_service, proposal_service

#: At most this many label trials per request: 100 alternatives × 100 leaves would be far more.
MAX_TRIALS = 20_000
LABEL = (
    "One cell at a time, everything else fixed. This is not robustness over combinations of "
    "cells, and it predicts nothing: it shows which uncertain ratings could change the screening "
    "result, so the next diligence question is the one that matters."
)
LIMITATIONS = [
    "Each cell is varied alone; two ratings moving together can do what neither does alone.",
    "Only qualitative and ordinal cells whose leaf carries positive weight are analysed; numeric "
    "cells are covered by the measurement-range questions.",
    "Reasons come from the dossier and proposals supplied; a cell with no open reason is still "
    "analysed.",
]
#: A dossier marks a rating that rests on judgement by starting its source description with this.
JUDGEMENT_PREFIX = "Judgement"

Change = Literal["target_rank", "other_rank", "leader", "target_class"]
Reason = Literal[
    "judgement_only",
    "disputed",
    "outdated",
    "missing",
    "proposal_pending",
    "proposal_rejected",
    "tool_human_disagreement",
]
Tier = Literal["leader_or_class", "rank", "none"]


class LabelEffect(DomainModel):
    """What one alternative label does to the screening result."""

    label: str
    levels: int  # signed steps along the scale's label order; positive is later in the list
    value: float  # the alternative's new overall value
    target_rank: int
    target_class_id: Id | None = None
    leaders: list[Id]
    changes: list[Change]


class CellImpact(DomainModel):
    alternative_id: Id
    alternative_name: str
    criterion_id: Id
    criterion_name: str
    current_label: str
    ordered: bool  # an ordinal scale; on a categorical scale label order is only the listed order
    global_weight: float
    effects: list[LabelEffect]  # every other label, in the scale's order
    target_rank_labels: list[str]
    any_rank_labels: list[str]
    target_class_labels: list[str]
    leader_labels: list[str]
    smallest_changes: list[str]  # nearest labels (by steps) that change anything, both sides
    can_change_decision: bool  # some other label changes the leader or the target's class
    tier: Tier
    reasons: list[Reason]  # empty means "no open reason"


class DecisionImpact(DomainModel):
    project_fingerprint: str
    configuration: AnalysisConfiguration
    weight_profile_id: Id | None = None
    scenario_id: Id | None = None
    status: Literal["available", "unavailable"]
    reason: str = ""
    label: str = LABEL
    baseline_leaders: list[Id] = []
    baseline_classes: dict[Id, Id] = {}
    analysed_cells: int = 0
    cells: list[CellImpact] = []
    limitations: list[str] = LIMITATIONS


def _active(claim: Claim) -> bool:
    return claim.review is not None and claim.review.status != "rejected"


def _dossier_reasons(
    project: Project, dossier: EvidenceDossier | None
) -> dict[tuple[str, str], set[Reason]]:
    """Reasons from the evidence dossier, only when it is valid for this project revision."""
    if dossier is None:
        return {}
    review = evidence_service.preview(project, dossier)
    if any(issue.severity.value == "error" for issue in review.issues):
        return {}
    cells: dict[tuple[str, str], list[Claim]] = {}
    for claim in dossier.claims:
        cells.setdefault((claim.alternative_id, claim.criterion_id), []).append(claim)
    out: dict[tuple[str, str], set[Reason]] = {}
    conflicting = {(c.alternative_id, c.criterion_id) for c in review.conflicting_cells}
    pending = {cell for cell, claims in cells.items() if any(c.review is None for c in claims)}
    for alt in project.alternatives:
        for leaf in project.tree().leaves():
            cell = (alt.id, leaf)
            reasons: set[Reason] = set()
            # A valid dossier has at most one accepted or corrected claim per cell.
            active = next((c for c in cells.get(cell, []) if _active(c)), None)
            if active is None:
                reasons.add("missing")
            else:
                if active.source.description.startswith(JUDGEMENT_PREFIX):
                    reasons.add("judgement_only")
                if active.outdated:
                    reasons.add("outdated")
            if cell in conflicting or cell in pending:
                reasons.add("disputed")
            out[cell] = reasons
    return out


def _proposal_reasons(
    project: Project, proposals: ExternalProposals | None
) -> dict[tuple[str, str], set[Reason]]:
    if proposals is None:
        return {}
    inspected = proposal_service.inspect(project, proposals)
    out: dict[tuple[str, str], set[Reason]] = {}
    for row in inspected.rows:
        criterion = row.original.subject.criterion_id
        if criterion is None:
            continue
        cell = (row.original.subject.alternative_id, criterion)
        if row.review is None:
            out.setdefault(cell, set()).add("proposal_pending")
        elif row.review.status == "rejected":
            out.setdefault(cell, set()).add("proposal_rejected")
    for question in inspected.questions:
        if question.code == "PROPOSAL_DISAGREEMENT" and question.criterion_id is not None:
            cell = (question.alternative_id or "", question.criterion_id)
            out.setdefault(cell, set()).add("tool_human_disagreement")
    return out


def _unavailable(
    project: Project, configuration: AnalysisConfiguration, reason: str
) -> DecisionImpact:
    return DecisionImpact(
        project_fingerprint=project.fingerprint(),
        configuration=configuration,
        weight_profile_id=configuration.weight_profile_id,
        scenario_id=configuration.scenario_id,
        status="unavailable",
        reason=reason,
    )


def decision_impact(
    project: Project,
    configuration: AnalysisConfiguration | None = None,
    dossier: EvidenceDossier | None = None,
    proposals: ExternalProposals | None = None,
) -> DecisionImpact:
    """One-cell-at-a-time checks of every scored labelled cell. Read-only."""
    requested = (configuration or project.analysis).model_copy(deep=True)
    mavt = requested.model_copy(update={"method": "mavt", "parameters": {}})
    try:
        prep = prepare_mavt(project, mavt)
    except ValidationFailed as exc:
        codes = [e.code for e in exc.report.errors]
        missing = codes.count("MISSING_MEASUREMENT")
        reason = (
            f"Decision impact unavailable: {missing} measurement(s) are missing."
            if missing
            else f"Decision impact unavailable: the model has {len(codes)} validation error(s)."
        )
        return _unavailable(project, requested, reason)
    except McdaError as exc:
        return _unavailable(project, requested, f"Decision impact unavailable: {exc}")

    weights = prep.global_vector()
    base_values = overall_values(prep.partial, weights)
    base_ranks = rank_values(base_values)
    boundaries: list[float] | None = None
    class_ids: list[str] = []
    if project.sorting is not None:
        issues = check_sorting(project, [])
        if not any(issue.severity.value == "error" for issue in issues):
            boundaries = lower_boundaries(project.sorting)
            class_ids = [c.id for c in project.sorting.classes]

    def class_of(value: float) -> str | None:
        return class_ids[class_index(value, boundaries)] if boundaries is not None else None

    base_class = [class_of(v) for v in base_values]
    leaders = {i for i, rank in enumerate(base_ranks) if rank == 1}
    names = {a.id: a.name for a in project.alternatives}

    # Cells: positive-weight leaves with a qualitative value function and an entered label.
    candidates = []
    trials = 0
    for j, leaf in enumerate(prep.leaf_ids):
        node = prep.tree.node(leaf)
        vf = (
            prep.scenario.value_function_overrides.get(leaf, node.value_function)
            if prep.scenario
            else node.value_function
        )
        if (
            weights[j] <= 0
            or node.scale is None
            or node.scale.is_numeric
            or not isinstance(vf, QualitativeValueFunction)
        ):
            continue
        for i, alt in enumerate(prep.alt_ids):
            if isinstance(prep.raw.get((alt, leaf)), str):
                candidates.append((i, j, leaf, node, vf))
                trials += max(0, len(node.scale.labels) - 1)
    if trials > MAX_TRIALS:
        raise AnalysisLimitError(
            f"Decision impact would try {trials} labels; the limit is {MAX_TRIALS}."
        )

    reasons: dict[tuple[str, str], set[Reason]] = {}
    for source in (_dossier_reasons(project, dossier), _proposal_reasons(project, proposals)):
        for cell, found in source.items():
            reasons.setdefault(cell, set()).update(found)
    reason_order: list[Reason] = [
        "judgement_only",
        "disputed",
        "outdated",
        "missing",
        "proposal_pending",
        "proposal_rejected",
        "tool_human_disagreement",
    ]

    impacts: list[tuple[int, CellImpact]] = []
    for order, (i, j, leaf, node, vf) in enumerate(candidates):
        assert node.scale is not None
        alt = prep.alt_ids[i]
        current = str(prep.raw[(alt, leaf)])
        labels = list(node.scale.labels)
        position = labels.index(current)
        evaluator = build_evaluator(vf, prep.domains[leaf])
        effects: list[LabelEffect] = []
        for k, label in enumerate(labels):
            if label == current:
                continue
            row = prep.partial[i].copy()
            row[j] = evaluator(label)[0]
            values = list(base_values)
            values[i] = overall_values(row[None, :], weights)[0]
            ranks = rank_values(values)
            now_leaders = {x for x, rank in enumerate(ranks) if rank == 1}
            new_class = class_of(values[i])
            changes: list[Change] = []
            if ranks[i] != base_ranks[i]:
                changes.append("target_rank")
            if any(ranks[x] != base_ranks[x] for x in range(len(values)) if x != i):
                changes.append("other_rank")
            if now_leaders != leaders:
                changes.append("leader")
            if new_class != base_class[i]:
                changes.append("target_class")
            effects.append(
                LabelEffect(
                    label=label,
                    levels=k - position,
                    value=values[i],
                    target_rank=ranks[i],
                    target_class_id=new_class,
                    leaders=[prep.alt_ids[x] for x in sorted(now_leaders)],
                    changes=changes,
                )
            )
        by_change = {
            change: [e.label for e in effects if change in e.changes]
            for change in ("target_rank", "other_rank", "leader", "target_class")
        }
        moving = [e for e in effects if e.changes]
        nearest = min((abs(e.levels) for e in moving), default=None)
        smallest = [e.label for e in moving if abs(e.levels) == nearest] if moving else []
        decisive = bool(by_change["leader"] or by_change["target_class"])
        any_rank = bool(by_change["target_rank"] or by_change["other_rank"])
        tier: Tier = "leader_or_class" if decisive else ("rank" if any_rank else "none")
        found = reasons.get((alt, leaf), set())
        impacts.append(
            (
                order,
                CellImpact(
                    alternative_id=alt,
                    alternative_name=names[alt],
                    criterion_id=leaf,
                    criterion_name=node.name,
                    current_label=current,
                    ordered=node.scale.type.value == "ordinal",
                    global_weight=float(weights[j]),
                    effects=effects,
                    target_rank_labels=by_change["target_rank"],
                    any_rank_labels=sorted(
                        {*by_change["target_rank"], *by_change["other_rank"]}, key=labels.index
                    ),
                    target_class_labels=by_change["target_class"],
                    leader_labels=by_change["leader"],
                    smallest_changes=smallest,
                    can_change_decision=decisive,
                    tier=tier,
                    reasons=[r for r in reason_order if r in found],
                ),
            )
        )
    rank_of_tier = {"leader_or_class": 0, "rank": 1, "none": 2}
    impacts.sort(key=lambda pair: (rank_of_tier[pair[1].tier], pair[0]))
    assert all(math.isfinite(e.value) for _, c in impacts for e in c.effects)
    return DecisionImpact(
        project_fingerprint=project.fingerprint(),
        configuration=requested,
        weight_profile_id=prep.profile.id,
        scenario_id=prep.scenario.id if prep.scenario else None,
        status="available",
        baseline_leaders=[prep.alt_ids[x] for x in sorted(leaders)],
        baseline_classes={prep.alt_ids[x]: c for x, c in enumerate(base_class) if c is not None},
        analysed_cells=len(impacts),
        cells=[c for _, c in impacts],
    )
