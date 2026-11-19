"""The screening summary: one read-only row per alternative (``docs/design/screening-summary.md``).

Every number comes from an existing engine run under the selected profile and scenario: MAVT
values, ranks and weighted contributions; sorting classes and boundary distances; the feasibility
check; Open Questions; and exact one-way crossovers and class changes for fragility. Nothing here
edits the project or adds a stored format, and a model MAVT cannot evaluate gives an unavailable
summary with its reason, never a row of zeros.
"""

import math
from typing import Literal

from mcda_studio.domain.common import DomainModel, Id
from mcda_studio.domain.errors import AnalysisLimitError, McdaError, ValidationFailed
from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.feasibility import FeasibilityStatus
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import MavtResult, MavtSortingResult
from mcda_studio.methods.mavt import sensitivity as one_way
from mcda_studio.methods.mavt.aggregation import TIE_TOL, prepare_mavt
from mcda_studio.methods.sorting import sensitivity as class_sensitivity
from mcda_studio.services import analysis_service, feasibility_service, questions_service
from mcda_studio.services.sensitivity_eligibility import eligible_nodes, node_global_weight

#: Fragility is computed for at most this many criterion nodes, the Open Questions bound.
MAX_FRAGILITY_NODES = 50

LABEL = (
    "Overall value is a preference value under this profile and scenario, not a probability or a "
    "prediction."
)
FRAGILITY_DEFINITION = (
    "Closest change: the smallest one-way change in a single criterion's weight, measured as a "
    "share of the total weight, at which this alternative's competition rank or class changes. The "
    "other weights in that criterion's group move proportionally; criteria weighted zero are not "
    "varied."
)
LIMITATIONS = [
    "One weight changes at a time with the rest of its group in proportion; this is not robustness "
    "over every combination of weights.",
    "Largest contributions and closest changes are MAVT's reading under the selected profile and "
    "scenario, whatever method is being viewed.",
    "Open-question counts use the same inputs as the Open Questions tab, including the evidence "
    "dossier when one is supplied.",
]

Column = Literal["classes", "requirements", "fragility", "open_questions"]


class Driver(DomainModel):
    """One weighted leaf contribution, w_j * v_j(a), in value points of the 0-1 scale."""

    criterion_id: Id
    name: str
    contribution: float


class Fragility(DomainModel):
    """The closest one-way change for one alternative.

    ``status`` is ``change`` (a rank or class change was found), ``tied`` (already tied with
    another alternative, so any separating change alters its rank) or ``none`` (no eligible
    criterion changes its rank or class anywhere in [0, 1]).
    """

    status: Literal["change", "tied", "none"]
    kind: Literal["rank", "class"] | None = None
    criterion_id: Id | None = None
    criterion_name: str | None = None
    direction: Literal["raise", "lower"] | None = None
    base_local_weight: float | None = None
    local_weight: float | None = None
    weight_change: float | None = None  # in global weight, a share of the total weight
    other_alternative_id: Id | None = None  # rank: the alternative it swaps with
    class_after_id: Id | None = None  # class: the class it moves to
    tied_with: list[Id] = []


class RequirementStatus(DomainModel):
    status: FeasibilityStatus
    failed: list[Id]
    unknown: list[Id]


class SummaryRow(DomainModel):
    alternative_id: Id
    name: str
    rank: int
    value: float
    class_id: Id | None = None
    class_name: str | None = None
    margin: float | None = None  # distance to the nearest class boundary
    nearest_boundary_class_id: Id | None = None
    requirements: RequirementStatus | None = None
    drivers: list[Driver] = []
    fragility: Fragility | None = None
    open_questions: int | None = None


class ColumnNote(DomainModel):
    column: Column
    available: bool
    reason: str = ""


class ScreeningSummary(DomainModel):
    project_fingerprint: str
    configuration: AnalysisConfiguration  # as requested
    weight_profile_id: Id | None  # resolved
    scenario_id: Id | None  # resolved
    status: Literal["available", "unavailable"]
    reason: str = ""
    issue_codes: list[str] = []
    label: str = LABEL
    fragility_definition: str = FRAGILITY_DEFINITION
    rows: list[SummaryRow] = []
    columns: list[ColumnNote] = []
    project_open_questions: int | None = None
    excluded_criteria: list[Id] = []  # weighted zero, so never varied for fragility
    limitations: list[str] = LIMITATIONS


def _unavailable(
    project: Project, configuration: AnalysisConfiguration, exc: McdaError
) -> ScreeningSummary:
    if isinstance(exc, ValidationFailed):
        errors = list(getattr(exc.report, "errors", []))
        codes = [e.code for e in errors]
        missing = codes.count("MISSING_MEASUREMENT")
        reason = (
            f"Ranking unavailable: {missing} measurement(s) are missing."
            if missing
            else f"Ranking unavailable: the model has {len(errors)} validation error(s)."
        )
    else:
        codes, reason = [], f"Ranking unavailable: {exc}"
    return ScreeningSummary(
        project_fingerprint=project.fingerprint(),
        configuration=configuration,
        weight_profile_id=configuration.weight_profile_id,
        scenario_id=configuration.scenario_id,
        status="unavailable",
        reason=reason,
        issue_codes=codes,
    )


def _fragility(
    project: Project,
    mavt: AnalysisConfiguration,
    sorting: AnalysisConfiguration | None,
    values: dict[str, float],
) -> tuple[dict[str, Fragility], list[str]]:
    prep = prepare_mavt(project, mavt)
    tree, local = prep.tree, prep.local
    varied, excluded = eligible_nodes(tree, local)
    best: dict[str, Fragility] = {}

    def offer(alt: str, candidate: Fragility) -> None:
        # Changes within TIE_TOL are equal (lowering one of two siblings is raising the other, so
        # one change can arrive twice, differing only in its last bits): the first offered, in
        # tree order, is kept, so rounding noise never chooses between them.
        current = best.get(alt)
        assert candidate.weight_change is not None
        if (
            current is None
            or current.weight_change is None
            or (candidate.weight_change < current.weight_change - TIE_TOL)
        ):
            best[alt] = candidate

    for node_id in varied:
        base = local[node_id]
        parent = tree.node(node_id).parent_id
        scale = node_global_weight(tree, local, parent) if parent is not None else 1.0
        name = tree.node(node_id).name
        result = one_way.weight_sensitivity(project, mavt, node_id, steps=2)
        for c in result.crossovers:
            for alt, other in (
                (c.alternative_a, c.alternative_b),
                (c.alternative_b, c.alternative_a),
            ):
                offer(alt, Fragility(
                    status="change", kind="rank", criterion_id=node_id, criterion_name=name,
                    direction="raise" if c.weight > base else "lower", base_local_weight=base,
                    local_weight=c.weight, weight_change=abs(c.weight - base) * scale,
                    other_alternative_id=other,
                ))  # fmt: skip
        if sorting is not None:
            classes = class_sensitivity.sorting_sensitivity(project, sorting, result)
            for changes in classes.class_changes:
                for point, direction in ((changes.first_change_up, "raise"),
                                         (changes.first_change_down, "lower")):  # fmt: skip
                    if point is None:
                        continue
                    after = point.class_after if direction == "raise" else point.class_before
                    offer(changes.alternative_id, Fragility(
                        status="change", kind="class", criterion_id=node_id, criterion_name=name,
                        direction=direction, base_local_weight=base, local_weight=point.weight,
                        weight_change=abs(point.weight - base) * scale, class_after_id=after,
                    ))  # fmt: skip
    out: dict[str, Fragility] = {}
    for alt, value in values.items():
        tied = [b for b, other in values.items() if b != alt and abs(other - value) <= TIE_TOL]
        if tied:
            out[alt] = Fragility(status="tied", tied_with=tied)
        else:
            out[alt] = best.get(alt, Fragility(status="none"))
    return out, excluded


def screening_summary(
    project: Project,
    configuration: AnalysisConfiguration | None = None,
    dossier: EvidenceDossier | None = None,
) -> ScreeningSummary:
    """The summary for one project revision, profile and scenario. Read-only."""
    requested = (configuration or project.analysis).model_copy(deep=True)
    mavt = requested.model_copy(update={"method": "mavt", "parameters": {}})
    try:
        result = analysis_service.evaluate_project(project, mavt)
    except (ValidationFailed, AnalysisLimitError) as exc:
        return _unavailable(project, requested, exc)
    assert isinstance(result, MavtResult)
    names = {a.id: a.name for a in project.alternatives}
    leaf_names = {n.id: n.name for n in project.criteria}
    order = {leaf: i for i, leaf in enumerate(result.leaf_order)}
    contributions = {a.alternative_id: a.weighted_contributions for a in result.alternatives}
    values = {r.alternative_id: r.value for r in result.ranking}
    columns: list[ColumnNote] = []

    assignments: dict[str, tuple[str, str, float | None, str | None]] = {}
    sorting_cfg: AnalysisConfiguration | None = None
    if project.sorting is None or not project.sorting.classes:
        columns.append(
            ColumnNote(column="classes", available=False, reason="No classes are set up.")
        )
    else:
        sorting_cfg = mavt.model_copy(update={"method": "mavt_sorting"})
        try:
            sorted_result = analysis_service.evaluate_project(project, sorting_cfg)
            assert isinstance(sorted_result, MavtSortingResult)
            class_names = {c.class_id: c.name for c in sorted_result.classes}
            for a in sorted_result.assignments:
                assignments[a.alternative_id] = (
                    a.class_id,
                    class_names[a.class_id],
                    a.distance_to_nearest_boundary,
                    a.nearest_boundary_class_id,
                )
            columns.append(ColumnNote(column="classes", available=True))
        except ValidationFailed as exc:
            sorting_cfg = None
            codes = ", ".join(e.code for e in exc.report.errors)
            columns.append(ColumnNote(
                column="classes", available=False, reason=f"The classes have errors: {codes}."
            ))  # fmt: skip

    requirements: dict[str, RequirementStatus] = {}
    if not project.requirements:
        columns.append(
            ColumnNote(column="requirements", available=False, reason="No requirements are stated.")
        )
    else:
        try:
            checked = feasibility_service.check_feasibility(project)
            for f in checked.alternatives:
                requirements[f.alternative_id] = RequirementStatus(
                    status=f.status, failed=list(f.failed), unknown=list(f.unknown)
                )
            columns.append(ColumnNote(column="requirements", available=True))
        except ValidationFailed as exc:
            codes = ", ".join(e.code for e in exc.report.errors)
            columns.append(ColumnNote(
                column="requirements", available=False,
                reason=f"The requirements have errors: {codes}.",
            ))  # fmt: skip

    fragility: dict[str, Fragility] = {}
    excluded: list[str] = []
    if len(project.criteria) > MAX_FRAGILITY_NODES:
        columns.append(ColumnNote(
            column="fragility", available=False,
            reason=f"Not computed: more than {MAX_FRAGILITY_NODES} criterion nodes.",
        ))  # fmt: skip
    else:
        fragility, excluded = _fragility(project, mavt, sorting_cfg, values)
        columns.append(ColumnNote(column="fragility", available=True))

    counts: dict[str, int] | None = None
    project_level: int | None = None
    try:
        questions = questions_service.open_questions(project, requested, dossier).questions
        counts = {a: 0 for a in values}
        project_level = 0
        for q in questions:
            if q.alternative_id in counts:
                counts[q.alternative_id] += 1
            else:
                project_level += 1
        columns.append(ColumnNote(column="open_questions", available=True))
    except McdaError as exc:
        columns.append(ColumnNote(
            column="open_questions", available=False, reason=f"Open Questions unavailable: {exc}"
        ))  # fmt: skip

    rows: list[SummaryRow] = []
    for ranked in result.ranking:
        alt = ranked.alternative_id
        positive = [(c, leaf) for leaf, c in contributions[alt].items() if c > 0.0]
        positive.sort(key=lambda item: (-item[0], order[item[1]]))
        drivers = [
            Driver(criterion_id=leaf, name=leaf_names[leaf], contribution=c)
            for c, leaf in positive[:2]
        ]
        assigned = assignments.get(alt)
        rows.append(SummaryRow(
            alternative_id=alt, name=names[alt], rank=ranked.rank, value=ranked.value,
            class_id=assigned[0] if assigned else None,
            class_name=assigned[1] if assigned else None,
            margin=assigned[2] if assigned else None,
            nearest_boundary_class_id=assigned[3] if assigned else None,
            requirements=requirements.get(alt), drivers=drivers, fragility=fragility.get(alt),
            open_questions=counts[alt] if counts is not None else None,
        ))  # fmt: skip
    assert all(math.isfinite(r.value) for r in rows)
    return ScreeningSummary(
        project_fingerprint=result.project_fingerprint,
        configuration=requested,
        weight_profile_id=result.weight_profile_id,
        scenario_id=result.scenario_id,
        status="available",
        rows=rows,
        columns=columns,
        project_open_questions=project_level,
        excluded_criteria=excluded,
    )
