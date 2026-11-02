"""AHP over the project's criteria tree: local priorities per sibling group, global priorities down
the tree, alternatives' priorities per leaf, and their synthesis (design note §2 and §3).

Every number comes from the section's pairwise judgements; measurements, value functions, swing
weights, profiles and scenarios are never read.
"""

import math
from typing import Literal

from mcda_studio.domain.common import Issue, Severity
from mcda_studio.domain.errors import ValidationFailed
from mcda_studio.domain.pairwise import PairwiseJudgement
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import (
    AhpAlternativePriority,
    AhpMatrixAnalysis,
    AhpMatrixPreview,
    AhpMatrixResult,
    AhpResult,
    AhpTriad,
    RankedAlternative,
)
from mcda_studio.methods.ahp.matrix import (
    CR_THRESHOLD,
    MAX_ITERATIONS,
    RANDOM_INDEX,
    TOLERANCE,
    MatrixAnalysis,
    analyse,
    matrix_issues,
)
from mcda_studio.methods.ahp.validation import ahp_parameters, criteria_groups, group_label
from mcda_studio.methods.base import validate_analysis
from mcda_studio.methods.mavt.aggregation import TIE_TOL, ordered_indices, rank_values

AHP_ASSUMPTIONS = [
    "Priorities are the principal eigenvectors of the stated pairwise matrices: the judgements "
    "read as ratios. They are shares of the goal that sum to one, not MAVT values or swing "
    "weights.",
    "A consistency ratio above 0.10 is a warning about the judgements, not an error; a consistent "
    "matrix is not thereby a valid one.",
    "Criteria priorities are multiplied down the criteria tree, and the alternatives' priorities "
    "on each leaf are combined with the leaves' global priorities.",
    "Under distributive synthesis, adding or removing an alternative, even a copy of one, can "
    "change the order of two others; ideal synthesis divides each leaf's priorities by its best.",
    "AHP reads no measurements, value functions, swing weights, profiles or scenarios.",
]


def _analysis(a: MatrixAnalysis) -> AhpMatrixAnalysis:
    triad = a.triad
    return AhpMatrixAnalysis(
        items=a.items,
        priorities=dict(zip(a.items, a.priorities, strict=True)),
        lambda_max=a.lambda_max,
        consistency_index=a.consistency_index,
        random_index=a.random_index,
        consistency_ratio=a.consistency_ratio,
        inconsistent=a.inconsistent,
        most_inconsistent_triad=None
        if triad is None
        else AhpTriad(
            items=triad.items,
            judgements=triad.judgements,
            index=triad.index,
            consistent_value=triad.consistent_value,
        ),
        iterations=a.iterations,
    )


def preview_matrix(items: list[str], judgements: list[PairwiseJudgement]) -> AhpMatrixPreview:
    """A read-only analysis of one drafted matrix: its issues until it is complete, then its
    priorities and consistency."""
    issues = matrix_issues(items, judgements, "matrix")
    if not items:
        issues.insert(
            0,
            Issue(
                severity=Severity.ERROR,
                code="AHP_TOO_FEW_ITEMS",
                message="a matrix needs at least one item",
                path="matrix",
            ),
        )
    if len(set(items)) != len(items):
        issues.insert(
            0,
            Issue(
                severity=Severity.ERROR,
                code="DUPLICATE_AHP_ITEM",
                message="an item is listed more than once",
                path="matrix",
            ),
        )
    ready = not issues
    return AhpMatrixPreview(
        consistency_threshold=CR_THRESHOLD,
        ready=ready,
        issues=issues,
        analysis=_analysis(analyse(items, judgements)) if ready else None,
    )


def run_ahp(project: Project, configuration: AnalysisConfiguration) -> AhpResult:
    report = validate_analysis(project, configuration)
    if not report.ok:
        raise ValidationFailed(report)
    params = ahp_parameters(configuration)
    model = project.ahp
    assert model is not None  # guaranteed by validation (AHP_NOT_STATED)
    tree = project.tree()
    names = {a.id: a.name for a in project.alternatives}
    diagnostics: list[Issue] = list(report.warnings)
    matrices: list[AhpMatrixResult] = []

    def add_matrix(
        kind: Literal["criteria", "alternatives"],
        group: str | None,
        items: list[str],
        judgements: list[PairwiseJudgement],
    ) -> MatrixAnalysis:
        analysis = analyse(items, judgements)
        matrices.append(
            AhpMatrixResult(
                kind=kind,
                group_id=group,
                judgements=[j.model_copy() for j in judgements],
                **_analysis(analysis).model_dump(),
            )
        )
        if analysis.inconsistent:
            where = (
                f"ahp.criteria[{group_label(group)}]"
                if kind == "criteria"
                else f"ahp.alternatives[{group}]"
            )
            triad = analysis.triad
            hint = f"; most inconsistent triad: {', '.join(triad.items)}" if triad else ""
            diagnostics.append(
                Issue(
                    severity=Severity.WARNING,
                    code="AHP_INCONSISTENT",
                    message=f"consistency ratio {analysis.consistency_ratio:.3f} is above "
                    f"{CR_THRESHOLD:.2f}{hint}",
                    path=where,
                )
            )
        return analysis

    stated = {e.parent_id: e.judgements for e in model.criteria}
    judged = set(criteria_groups(tree))
    local: dict[str, float] = {}
    for parent in [None, *(i for i in tree.all_ids() if not tree.is_leaf(i))]:
        children = tree.child_ids(parent)
        if parent in judged:
            analysis = add_matrix("criteria", parent, children, stated[parent])
            local.update(zip(children, analysis.priorities, strict=True))
        elif len(children) == 1:
            local[children[0]] = 1.0
    leaves = tree.leaves()
    global_ = {leaf: math.prod(local[node] for node in tree.path(leaf)) for leaf in leaves}

    alt_ids = project.alternative_ids()
    on_leaf = {e.criterion_id: e.judgements for e in model.alternatives}
    local_alt: dict[str, list[float]] = {}
    for leaf in leaves:
        local_alt[leaf] = add_matrix("alternatives", leaf, alt_ids, on_leaf[leaf]).priorities

    ideal = params.synthesis == "ideal"
    parts: list[dict[str, float]] = []
    for a in range(len(alt_ids)):
        row = {}
        for leaf in leaves:
            p = local_alt[leaf]
            score = p[a] / max(p) if ideal else p[a]
            row[leaf] = global_[leaf] * score
        parts.append(row)
    scores = [math.fsum(row.values()) for row in parts]
    total = math.fsum(scores)
    priorities = [s / total for s in scores] if ideal else scores
    ranks = rank_values(priorities, TIE_TOL)
    order = ordered_indices(priorities)
    tied = sorted({r for r in ranks if ranks.count(r) > 1})
    for r in tied:
        members = [names[alt_ids[i]] for i, x in enumerate(ranks) if x == r]
        diagnostics.append(
            Issue(
                severity=Severity.INFO,
                code="TIED_ALTERNATIVES",
                message=f"alternatives tied on AHP priority at rank {r}: {', '.join(members)}",
            )
        )
    return AhpResult(
        schema_version=project.required_schema_version(),
        project_id=project.id,
        project_fingerprint=project.fingerprint(),
        configuration=configuration,
        weight_profile_id=None,
        scenario_id=None,
        ranking=[
            RankedAlternative(
                alternative_id=alt_ids[i],
                name=names[alt_ids[i]],
                value=priorities[i],
                rank=ranks[i],
            )
            for i in order
        ],
        diagnostics=diagnostics,
        assumptions=list(AHP_ASSUMPTIONS),
        synthesis=params.synthesis,
        random_indices=list(RANDOM_INDEX),
        consistency_threshold=CR_THRESHOLD,
        tolerance=TOLERANCE,
        max_iterations=MAX_ITERATIONS,
        leaf_order=leaves,
        local_priorities=local,
        global_priorities=global_,
        matrices=matrices,
        alternatives=[
            AhpAlternativePriority(
                alternative_id=alt_ids[i],
                name=names[alt_ids[i]],
                rank=ranks[i],
                priority=priorities[i],
                ideal_score=scores[i] if ideal else None,
                local_priorities={leaf: local_alt[leaf][i] for leaf in leaves},
                weighted_parts=parts[i],
            )
            for i in order
        ],
    )
