"""Reference cases (``docs/design/reference-cases.md``).

For an alternative in the open project, find the most similar reference cases: past alternatives
rated on the same labelled criteria as of a dated snapshot. Similarity is one minus the mean label
gap over the compared criteria both sides rated; it is computed with exact fractions. The compared
criteria are the labelled leaves with positive global weight in the active profile, from the
engine's own weight code.

Read-only and opt-in: nothing here changes a score, rank, class or stored project byte, and the
result predicts nothing. Outcomes appear only when they are asked for.
"""

from collections.abc import Sequence
from fractions import Fraction
from typing import Literal

from mcda_studio.domain.common import DomainModel, Id, Issue, Severity
from mcda_studio.domain.criteria import CriterionTree
from mcda_studio.domain.errors import McdaError, ModelStructureError, UnknownReferenceError
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.reference_cases import (
    ContextRow,
    IsoDate,
    ReferenceCase,
    ReferenceCases,
    ReferenceCasesInvalid,
    ReferenceClaim,
    ReferenceOutcome,
)
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.domain.validation import ValidationReport
from mcda_studio.methods.mavt.weighting import compute_weights

K_DEFAULT = 3
K_MIN = 1
K_MAX = 20
MIN_SHARED_DEFAULT = "1/2"

LABEL = (
    "Similarity is measured only on the rated criteria, as each reference case stood at its "
    "snapshot date. It says nothing about how this alternative will turn out. Outcomes are context "
    "chosen by the author of the reference set. A small reference set is not representative, and "
    "public sources under-report cases that closed."
)
LIMITATIONS = [
    "Numeric criteria are not compared in version 1 of the reference set.",
    "Every compared criterion counts equally unless profile weighting is chosen.",
    "The snapshot guard checks the dates of the sources a rating cites, not whether a claim was "
    "knowable at the snapshot.",
    "The author of the reference set knew the outcomes when rating the cases.",
]

Weighting = Literal["equal", "profile"]
Group = Literal["same", "one_step", "further", "not_compared"]
MissingSide = Literal["alternative", "reference_case", "both"]


class ReferenceCasesValidation(DomainModel):
    """The outcome of checking a reference set against a project."""

    reference_set_id: Id
    valid: bool
    issues: list[Issue]
    case_count: int
    rating_count: int


class LeafComparison(DomainModel):
    criterion_id: Id
    criterion_name: str
    ordered: bool  # an ordinal scale; steps are counted only on ordered scales
    alternative_label: str | None = None
    case_label: str | None = None
    steps: int | None = None  # label positions apart on an ordered scale; None otherwise
    gap: str | None = None  # the exact per-criterion gap as "p/q"; None when not compared
    missing: MissingSide | None = None
    case_note: str = ""


class CaseMatch(DomainModel):
    case_id: Id
    name: str
    snapshot_date: IsoDate
    context: list[ContextRow]
    similarity: float
    similarity_exact: str  # "p/q"
    shared_count: int
    compared_count: int
    same: list[LeafComparison]
    one_step: list[LeafComparison]
    further: list[LeafComparison]
    not_compared: list[LeafComparison]
    outcome: ReferenceOutcome | None = None


class NotComparableCase(DomainModel):
    case_id: Id
    name: str
    snapshot_date: IsoDate
    shared_count: int
    compared_count: int
    shared_fraction: str  # "p/q"


class AlternativeReferenceCases(DomainModel):
    alternative_id: Id
    alternative_name: str
    cases: list[CaseMatch]
    remaining_count: int  # comparable cases ranked below the top k
    not_comparable: list[NotComparableCase]
    excluded_case_ids: list[Id] = []  # left out because they share the alternative's id


class ReferenceCasesResult(DomainModel):
    project_fingerprint: str
    reference_set_id: Id
    reference_set_title: str
    configuration: AnalysisConfiguration
    weight_profile_id: Id | None = None
    status: Literal["available", "unavailable"]
    reason: str = ""
    k: int
    weighting: Weighting
    min_shared_fraction: str
    include_outcomes: bool
    exclude_same_id: bool = False
    compared_criteria: list[Id] = []
    alternatives: list[AlternativeReferenceCases] = []
    label: str = LABEL
    limitations: list[str] = LIMITATIONS


# ---- validation ------------------------------------------------------------------------------


def _issue(code: str, message: str, path: str) -> Issue:
    return Issue(severity=Severity.ERROR, code=code, message=message, path=path)


def validate(project: Project, reference_set: ReferenceCases) -> ReferenceCasesValidation:
    """Check the reference set against the project and apply the snapshot guard. Read-only."""
    issues: list[Issue] = []
    tree = project.tree()
    known = set(tree.all_ids())
    if reference_set.criteria_from != project.id:
        issues.append(
            _issue(
                "REFERENCE_PROJECT_MISMATCH",
                f"the reference set uses the criteria of project {reference_set.criteria_from!r}, "
                f"not {project.id!r}",
                "criteria_from",
            )
        )
    seen_cases: set[str] = set()
    for c, case in enumerate(reference_set.cases):
        at = f"cases[{c}]"
        if case.id in seen_cases:
            issues.append(
                _issue("REFERENCE_DUPLICATE_CASE", f"case id {case.id!r} is repeated", f"{at}.id")
            )
        seen_cases.add(case.id)
        claims: dict[str, ReferenceClaim] = {}
        for j, claim in enumerate(case.claims):
            if claim.id in claims:
                issues.append(
                    _issue(
                        "REFERENCE_DUPLICATE_CLAIM",
                        f"claim id {claim.id!r} is repeated in this case",
                        f"{at}.claims[{j}].id",
                    )
                )
            claims.setdefault(claim.id, claim)  # a repeated id is reported; the first one stands
            if claim.source not in reference_set.sources:
                issues.append(
                    _issue(
                        "REFERENCE_UNKNOWN_SOURCE",
                        f"source {claim.source!r} is not in the reference set's sources",
                        f"{at}.claims[{j}].source",
                    )
                )
        rated: set[str] = set()
        for r, rating in enumerate(case.ratings):
            where = f"{at}.ratings[{r}]"
            leaf = rating.criterion_id
            if leaf not in known:
                issues.append(
                    _issue(
                        "REFERENCE_UNKNOWN_CRITERION",
                        f"criterion {leaf!r} is not in the project",
                        f"{where}.criterion_id",
                    )
                )
            elif not tree.is_leaf(leaf):
                issues.append(
                    _issue(
                        "REFERENCE_UNKNOWN_CRITERION",
                        f"criterion {leaf!r} is not a leaf criterion; only leaves are rated",
                        f"{where}.criterion_id",
                    )
                )
            else:
                scale = tree.node(leaf).scale
                if scale is None or not scale.is_labelled:
                    issues.append(
                        _issue(
                            "REFERENCE_NUMERIC_CRITERION",
                            f"criterion {leaf!r} is numeric; version 1 of the reference set "
                            "rates only labelled (ordinal or categorical) criteria",
                            f"{where}.criterion_id",
                        )
                    )
                elif rating.label not in scale.labels:
                    issues.append(
                        _issue(
                            "REFERENCE_UNKNOWN_LABEL",
                            f"{rating.label!r} is not a label of criterion {leaf!r}",
                            f"{where}.label",
                        )
                    )
            if leaf in rated:
                issues.append(
                    _issue(
                        "REFERENCE_DUPLICATE_RATING",
                        f"criterion {leaf!r} is rated more than once in this case",
                        f"{where}.criterion_id",
                    )
                )
            rated.add(leaf)
            for k, claim_id in enumerate(rating.claim_ids):
                path = f"{where}.claim_ids[{k}]"
                cited = claims.get(claim_id)
                if cited is None:
                    issues.append(
                        _issue(
                            "REFERENCE_UNKNOWN_CLAIM",
                            f"claim {claim_id!r} is not among this case's claims",
                            path,
                        )
                    )
                    continue
                source = reference_set.sources.get(cited.source)
                if source is None:
                    continue  # reported once, at the claim
                # The snapshot guard: a rating may rest only on what was published by the snapshot.
                if source.date is None:
                    issues.append(
                        _issue(
                            "REFERENCE_UNDATED_SOURCE",
                            f"claim {claim_id!r} rests on undated source {cited.source!r}; a "
                            "rating needs a source dated on or before the snapshot",
                            path,
                        )
                    )
                elif source.date > case.snapshot_date:
                    issues.append(
                        _issue(
                            "REFERENCE_SOURCE_AFTER_SNAPSHOT",
                            f"claim {claim_id!r} rests on source {cited.source!r} dated "
                            f"{source.date.isoformat()}, after the snapshot "
                            f"{case.snapshot_date.isoformat()}",
                            path,
                        )
                    )
        if case.outcome.as_of < case.snapshot_date:
            issues.append(
                _issue(
                    "REFERENCE_OUTCOME_BEFORE_SNAPSHOT",
                    f"the outcome is dated {case.outcome.as_of.isoformat()}, before the snapshot "
                    f"{case.snapshot_date.isoformat()}",
                    f"{at}.outcome.as_of",
                )
            )
        for k, claim_id in enumerate(case.outcome.claim_ids):
            if claim_id not in claims:
                issues.append(
                    _issue(
                        "REFERENCE_UNKNOWN_CLAIM",
                        f"claim {claim_id!r} is not among this case's claims",
                        f"{at}.outcome.claim_ids[{k}]",
                    )
                )
    return ReferenceCasesValidation(
        reference_set_id=reference_set.id,
        valid=not issues,
        issues=issues,
        case_count=len(reference_set.cases),
        rating_count=sum(len(case.ratings) for case in reference_set.cases),
    )


def check(project: Project, reference_set: ReferenceCases) -> None:
    """Raise ``ReferenceCasesInvalid`` with every issue when the reference set does not fit."""
    report = validate(project, reference_set)
    if not report.valid:
        raise ReferenceCasesInvalid(ValidationReport(issues=report.issues))


# ---- the computation -------------------------------------------------------------------------


def parse_fraction(text: str) -> Fraction:
    """An exact fraction from "p/q" or a decimal string, in (0, 1]."""
    try:
        value = Fraction(text.strip())
    except (ValueError, ZeroDivisionError) as exc:
        raise McdaError(f"min_shared_fraction {text!r} is not a fraction such as 1/2") from exc
    if not 0 < value <= 1:
        raise McdaError("min_shared_fraction must be greater than 0 and at most 1")
    return value


def fraction_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def label_gap(scale: Scale, a: str, b: str) -> tuple[Fraction, int | None]:
    """The gap between two labels of one scale, with the steps apart on an ordered scale.

    Ordinal: ``|i - j| / (n - 1)`` with label positions ``i``, ``j`` and ``n`` labels (a one-label
    scale has no gap). Categorical: 0 when the labels are equal, else 1.
    """
    labels = scale.labels
    i, j = labels.index(a), labels.index(b)
    if scale.type is ScaleType.ORDINAL:
        steps = abs(i - j)
        n = len(labels)
        return (Fraction(steps, n - 1) if n > 1 else Fraction(0)), steps
    return (Fraction(0) if a == b else Fraction(1)), None


def compared_criteria(tree: CriterionTree, global_weights: dict[str, float]) -> list[str]:
    """Labelled leaves whose global weight in the active profile is positive, in tree order."""
    out = []
    for leaf in tree.leaves():
        scale = tree.node(leaf).scale
        if scale is not None and scale.is_labelled and global_weights[leaf] > 0:
            out.append(leaf)
    return out


def _labels_of(case: ReferenceCase) -> dict[str, tuple[str, str]]:
    return {r.criterion_id: (r.label, r.note) for r in case.ratings}


def _compare(
    tree: CriterionTree,
    leaves: Sequence[str],
    weights: dict[str, Fraction],
    alternative: dict[str, str],
    case: ReferenceCase,
    weighting: Weighting,
) -> tuple[Fraction | None, int, list[LeafComparison]]:
    """Distance over the shared leaves (None when nothing is shared), the shared count and rows."""
    rated = _labels_of(case)
    rows: list[LeafComparison] = []
    gaps: list[Fraction] = []
    shared_weights: list[Fraction] = []
    for leaf in leaves:
        node = tree.node(leaf)
        assert node.scale is not None
        mine = alternative.get(leaf)
        theirs, note = rated.get(leaf, (None, ""))
        ordered = node.scale.type is ScaleType.ORDINAL
        if mine is None or theirs is None:
            missing: MissingSide = (
                "both"
                if mine is None and theirs is None
                else "alternative"
                if mine is None
                else "reference_case"
            )
            rows.append(
                LeafComparison(
                    criterion_id=leaf,
                    criterion_name=node.name,
                    ordered=ordered,
                    alternative_label=mine,
                    case_label=theirs,
                    missing=missing,
                    case_note=note,
                )
            )
            continue  # missing is not compared: never a gap of 0 or 1
        gap, steps = label_gap(node.scale, mine, theirs)
        gaps.append(gap)
        shared_weights.append(weights[leaf])
        rows.append(
            LeafComparison(
                criterion_id=leaf,
                criterion_name=node.name,
                ordered=ordered,
                alternative_label=mine,
                case_label=theirs,
                steps=steps,
                gap=fraction_text(gap),
                case_note=note,
            )
        )
    if not gaps:
        return None, 0, rows
    if weighting == "equal":
        distance = sum(gaps, Fraction(0)) / len(gaps)
    else:
        total = sum(shared_weights, Fraction(0))
        distance = sum((w * g for w, g in zip(shared_weights, gaps, strict=True)), Fraction(0))
        distance /= total
    return distance, len(gaps), rows


def _group(row: LeafComparison) -> Group:
    if row.gap is None:
        return "not_compared"
    if row.alternative_label == row.case_label:
        return "same"
    if row.ordered and row.steps == 1:
        return "one_step"
    return "further"


def reference_cases(
    project: Project,
    reference_set: ReferenceCases,
    configuration: AnalysisConfiguration | None = None,
    alternative_id: str | None = None,
    k: int = K_DEFAULT,
    weighting: Weighting = "equal",
    min_shared_fraction: str = MIN_SHARED_DEFAULT,
    include_outcomes: bool = False,
    exclude_same_id: bool = False,
) -> ReferenceCasesResult:
    """The most similar reference cases for one alternative, or for every alternative.

    With ``exclude_same_id`` a case whose id equals the alternative's id is left out of that
    alternative's comparison (leave-one-out) and named in ``excluded_case_ids``."""
    if type(k) is not int or not K_MIN <= k <= K_MAX:
        raise McdaError(f"k must be a whole number from {K_MIN} to {K_MAX}")
    if weighting not in ("equal", "profile"):
        raise McdaError("weighting must be 'equal' or 'profile'")
    threshold = parse_fraction(min_shared_fraction)
    check(project, reference_set)
    if alternative_id is not None and alternative_id not in project.alternative_ids():
        raise UnknownReferenceError(f"unknown alternative id {alternative_id!r}")
    requested = (configuration or project.analysis).model_copy(deep=True)
    base = ReferenceCasesResult(
        project_fingerprint=project.fingerprint(),
        reference_set_id=reference_set.id,
        reference_set_title=reference_set.title,
        configuration=requested,
        status="unavailable",
        k=k,
        weighting=weighting,
        min_shared_fraction=fraction_text(threshold),
        include_outcomes=include_outcomes,
        exclude_same_id=exclude_same_id,
    )
    tree = project.tree()
    try:
        profile = project.resolve_profile(requested)
        if profile is None:
            base.reason = "Reference cases unavailable: the project has no weight profile."
            return base
        weight_set = compute_weights(tree, profile.judgements)
    except McdaError as exc:
        base.reason = f"Reference cases unavailable: {exc}"
        return base
    base.weight_profile_id = profile.id
    leaves = compared_criteria(tree, weight_set.global_)
    base.compared_criteria = leaves
    if not leaves:
        base.reason = (
            "Reference cases unavailable: no labelled criterion carries positive weight in this "
            "profile."
        )
        return base
    weights = {leaf: Fraction(weight_set.global_[leaf]) for leaf in leaves}
    raw = project.performance_index()
    alternatives = [
        a for a in project.alternatives if alternative_id is None or a.id == alternative_id
    ]
    out: list[AlternativeReferenceCases] = []
    for alt in alternatives:
        mine: dict[str, str] = {}
        for leaf in leaves:
            value = raw.get((alt.id, leaf))
            if value is None:
                continue
            scale = tree.node(leaf).scale
            assert scale is not None
            if not isinstance(value, str) or value not in scale.labels:
                raise ModelStructureError(
                    f"alternative {alt.id!r} has {value!r} on {leaf!r}, which is not a label of "
                    "its scale"
                )
            mine[leaf] = value
        ranked: list[tuple[Fraction, int, str, CaseMatch]] = []
        not_comparable: list[NotComparableCase] = []
        excluded: list[str] = []
        for case in reference_set.cases:
            if exclude_same_id and case.id == alt.id:
                excluded.append(case.id)
                continue
            distance, shared, rows = _compare(tree, leaves, weights, mine, case, weighting)
            fraction = Fraction(shared, len(leaves))
            if distance is None or fraction < threshold:
                not_comparable.append(
                    NotComparableCase(
                        case_id=case.id,
                        name=case.name,
                        snapshot_date=case.snapshot_date,
                        shared_count=shared,
                        compared_count=len(leaves),
                        shared_fraction=fraction_text(fraction),
                    )
                )
                continue
            similarity = 1 - distance
            groups: dict[Group, list[LeafComparison]] = {
                "same": [],
                "one_step": [],
                "further": [],
                "not_compared": [],
            }
            for row in rows:
                groups[_group(row)].append(row)
            match = CaseMatch(
                case_id=case.id,
                name=case.name,
                snapshot_date=case.snapshot_date,
                context=case.context,
                similarity=float(similarity),
                similarity_exact=fraction_text(similarity),
                shared_count=shared,
                compared_count=len(leaves),
                same=groups["same"],
                one_step=groups["one_step"],
                further=groups["further"],
                not_compared=groups["not_compared"],
                outcome=case.outcome if include_outcomes else None,
            )
            ranked.append((similarity, shared, case.id, match))
        # Similarity descending, then shared count descending, then case id: exact fractions.
        ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
        out.append(
            AlternativeReferenceCases(
                alternative_id=alt.id,
                alternative_name=alt.name,
                cases=[item[3] for item in ranked[:k]],
                remaining_count=max(0, len(ranked) - k),
                not_comparable=not_comparable,
                excluded_case_ids=excluded,
            )
        )
    base.status = "available"
    base.alternatives = out
    return base
