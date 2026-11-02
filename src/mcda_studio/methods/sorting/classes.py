"""Value-based sorting: ordered classes from fixed boundaries on the overall MAVT value.

The rule (specification §7): with classes C_1 (best) .. C_q and lower boundaries b_1 > .. > b_{q-1},

    class(a) = C_h  where  h = 1 + #{k < q : U(a) < b_k - tol},

so a value within ``tol`` of a boundary, on either side, goes to the higher class. ``tol`` is the
ranking tie tolerance. Evaluation, sensitivity and the probe all read ``class_index``.
"""

import hashlib
import re

from mcda_studio.domain.common import Issue, Severity
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import (
    AuditSample,
    ClassAssignment,
    ClassBand,
    ClassSummary,
    MavtResult,
    MavtSortingResult,
    ValueModelResult,
)
from mcda_studio.domain.sorting import SortingAudit, SortingModel
from mcda_studio.methods.mavt.aggregation import TIE_TOL

BOUNDARY_ASSUMPTION = (
    "Classes are fixed boundaries on the overall value: an alternative belongs to the best class "
    "whose lower boundary it reaches, and a value within 1e-12 of a boundary goes to the higher "
    "class. Class membership inherits every MAVT assumption, including compensation."
)


def lower_boundaries(model: SortingModel) -> list[float]:
    """b_1 .. b_{q-1}; validation guarantees every class but the lowest has one."""
    out: list[float] = []
    for c in model.classes[:-1]:
        assert c.lower_boundary is not None
        out.append(c.lower_boundary)
    return out


def class_index(value: float, boundaries: list[float]) -> int:
    """0-based class index (0 = best) for an overall value."""
    return sum(1 for b in boundaries if value < b - TIE_TOL)


def class_bands(model: SortingModel) -> list[ClassBand]:
    classes = model.classes
    return [
        ClassBand(
            class_id=c.id,
            name=c.name,
            rank=i + 1,
            lower_boundary=c.lower_boundary if i < len(classes) - 1 else None,
            upper_boundary=classes[i - 1].lower_boundary if i > 0 else None,
        )
        for i, c in enumerate(classes)
    ]


def _assignment(alt: str, value: float, model: SortingModel) -> ClassAssignment:
    boundaries = lower_boundaries(model)
    index = class_index(value, boundaries)
    nearest: tuple[float, int] | None = None
    for k, b in enumerate(boundaries):  # the higher boundary wins an exact tie
        distance = abs(value - b)
        if nearest is None or distance < nearest[0]:
            nearest = (distance, k)
    return ClassAssignment(
        alternative_id=alt,
        class_id=model.classes[index].id,
        class_rank=index + 1,
        on_boundary=nearest is not None and nearest[0] <= TIE_TOL,
        nearest_boundary_class_id=model.classes[nearest[1]].id if nearest else None,
        distance_to_nearest_boundary=nearest[0] if nearest else None,
    )


def _audit_key(seed: int, alternative_id: str) -> tuple[str, str]:
    return hashlib.sha256(f"{seed}:{alternative_id}".encode()).hexdigest(), alternative_id


def audit_sample(
    audit: SortingAudit, model: SortingModel, assignments: list[ClassAssignment]
) -> AuditSample:
    """A seed-keyed pseudo-random sample of the alternatives sorted below the cut-off class."""
    cutoff = next(i for i, c in enumerate(model.classes) if c.id == audit.below_class_id)
    pool = [a.alternative_id for a in assignments if a.class_rank > cutoff + 1]
    chosen = sorted(pool, key=lambda alt: _audit_key(audit.seed, alt))[: audit.sample_size]
    return AuditSample(
        below_class_id=audit.below_class_id,
        seed=audit.seed,
        requested_size=audit.sample_size,
        pool_size=len(pool),
        alternative_ids=chosen,
    )


def build_sorting_result(base: MavtResult, model: SortingModel) -> MavtSortingResult:
    """Sort a completed MAVT result into classes; every MAVT field is carried over unchanged."""
    names = {a.alternative_id: a.name for a in base.ranking}
    assignments = [_assignment(a.alternative_id, a.value, model) for a in base.ranking]
    diagnostics = list(base.diagnostics)
    for a in assignments:
        if a.on_boundary:
            cls = next(c for c in model.classes if c.id == a.nearest_boundary_class_id)
            diagnostics.append(
                Issue(
                    severity=Severity.INFO,
                    code="ON_CLASS_BOUNDARY",
                    message=f"{names[a.alternative_id]} is on the lower boundary of {cls.name} "
                    f"({cls.lower_boundary}) within the 1e-12 tolerance and is assigned to "
                    f"{model.classes[a.class_rank - 1].name}",
                    path=f"sorting.classes[{cls.id}].lower_boundary",
                )
            )
    sample = audit_sample(model.audit, model, assignments) if model.audit else None
    if sample is not None and sample.pool_size == 0:
        diagnostics.append(
            Issue(
                severity=Severity.INFO,
                code="AUDIT_POOL_EMPTY",
                message="no alternative is sorted below the audit cut-off, so nothing is sampled",
                path="sorting.audit",
            )
        )
    elif sample is not None and sample.pool_size < sample.requested_size:
        diagnostics.append(
            Issue(
                severity=Severity.INFO,
                code="AUDIT_SAMPLE_IS_WHOLE_POOL",
                message=f"only {sample.pool_size} alternative(s) are below the audit cut-off; "
                "the sample is all of them",
                path="sorting.audit",
            )
        )
    shared = {name: getattr(base, name) for name in ValueModelResult.model_fields}
    shared.pop("method")
    return MavtSortingResult(
        **shared
        | {"diagnostics": diagnostics, "assumptions": [*base.assumptions, BOUNDARY_ASSUMPTION]},
        boundary_tolerance=TIE_TOL,
        classes=[
            ClassSummary(
                **band.model_dump(),
                alternative_ids=[
                    a.alternative_id for a in assignments if a.class_id == band.class_id
                ],
            )
            for band in class_bands(model)
        ],
        assignments=assignments,
        audit_sample=sample,
    )


_LEAF_IN_PATH = re.compile(r"\[([^\]]+)\]$")


def check_sorting(project: Project, value_model_issues: list[Issue]) -> list[Issue]:
    """The sorting section's rules, plus the anchor warning drawn from the value-model report."""
    issues: list[Issue] = []

    def add(severity: Severity, code: str, message: str, path: str) -> None:
        issues.append(Issue(severity=severity, code=code, message=message, path=path))

    model = project.sorting
    if model is None:
        add(
            Severity.ERROR,
            "NO_SORTING_MODEL",
            "value-based sorting needs classes; the project has none",
            "sorting",
        )
        return issues
    classes = model.classes
    if not classes:
        add(Severity.ERROR, "NO_CLASSES", "the sorting section has no classes", "sorting.classes")
    seen: set[str] = set()
    for c in classes:
        if c.id in seen:
            add(
                Severity.ERROR,
                "DUPLICATE_CLASS_ID",
                f"class id {c.id!r} is used more than once",
                f"sorting.classes[{c.id}]",
            )
        seen.add(c.id)
    names: set[str] = set()
    for c in classes:
        folded = c.name.strip().casefold()
        if folded in names:
            add(
                Severity.WARNING,
                "DUPLICATE_CLASS_NAME",
                f"several classes are named {c.name!r}",
                f"sorting.classes[{c.id}].name",
            )
        names.add(folded)
    for i, c in enumerate(classes):
        where = f"sorting.classes[{c.id}].lower_boundary"
        lowest = i == len(classes) - 1
        if lowest and c.lower_boundary is not None:
            add(
                Severity.ERROR,
                "UNEXPECTED_CLASS_BOUNDARY",
                f"{c.name!r} is the lowest class and takes every remaining value, so it has no "
                "lower boundary",
                where,
            )
        elif not lowest and c.lower_boundary is None:
            add(
                Severity.ERROR,
                "MISSING_CLASS_BOUNDARY",
                f"{c.name!r} needs a lower boundary: the overall value needed to enter it",
                where,
            )
        if c.lower_boundary is not None and not 0.0 <= c.lower_boundary <= 1.0:
            add(
                Severity.ERROR,
                "BOUNDARY_OUT_OF_RANGE",
                f"boundary {c.lower_boundary!r} of {c.name!r} is outside [0, 1], where every "
                "overall value lies",
                where,
            )
    for upper, lower in zip(classes, classes[1:], strict=False):
        if upper.lower_boundary is None or lower.lower_boundary is None:
            continue
        if not upper.lower_boundary - lower.lower_boundary > 2 * TIE_TOL:
            add(
                Severity.ERROR,
                "BOUNDARIES_NOT_DECREASING",
                f"the boundary of {lower.name!r} ({lower.lower_boundary}) must be more than "
                f"2e-12 below that of {upper.name!r} ({upper.lower_boundary}); boundaries are "
                "never reordered automatically",
                f"sorting.classes[{lower.id}].lower_boundary",
            )
    if model.audit is not None:
        audit = model.audit
        ids = [c.id for c in classes]
        if audit.below_class_id not in ids:
            add(
                Severity.ERROR,
                "UNKNOWN_AUDIT_CLASS",
                f"the audit cut-off names unknown class {audit.below_class_id!r}",
                "sorting.audit.below_class_id",
            )
        elif audit.below_class_id == ids[-1]:
            add(
                Severity.ERROR,
                "AUDIT_BELOW_LOWEST_CLASS",
                "the audit cut-off is the lowest class, so no alternative can fall below it",
                "sorting.audit.below_class_id",
            )
        if audit.sample_size < 1:
            add(
                Severity.ERROR,
                "INVALID_AUDIT_SAMPLE_SIZE",
                f"the audit sample size must be at least 1, not {audit.sample_size}",
                "sorting.audit.sample_size",
            )
    anchored = sorted(
        {
            m.group(1)
            for i in value_model_issues
            if i.code == "LOCAL_ANCHORS" and (m := _LEAF_IN_PATH.search(i.path))
        }
    )
    if anchored:
        add(
            Severity.WARNING,
            "SORTING_LOCAL_ANCHORS",
            f"local anchors on {', '.join(anchored)}: adding or removing an alternative can move "
            "others between classes; fixed anchors are recommended for sorting",
            "sorting",
        )
    return issues
