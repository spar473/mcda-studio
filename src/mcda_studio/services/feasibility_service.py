"""The feasibility check: each alternative's individual measurements against mandatory
requirements, outside any aggregation (``docs/design/feasibility-check.md``).

A missing or unusable measurement is unknown, never fail. Limits are compared exactly, because a
measurement is compared as entered with no arithmetic before it. No method reads requirements, and
no weight, profile, value function or scenario is read here.
"""

import csv
import json
from collections import Counter
from typing import Literal

from mcda_studio.domain.common import Issue, Severity
from mcda_studio.domain.errors import (
    AnalysisLimitError,
    ModelStructureError,
    StaleRevisionError,
    ValidationFailed,
)
from mcda_studio.domain.feasibility import (
    AlternativeFeasibility,
    FeasibilityResult,
    FeasibilityStatus,
    RequirementCheck,
    RequirementSummary,
)
from mcda_studio.domain.measurements import Measurement
from mcda_studio.domain.project import Project
from mcda_studio.domain.requirements import AnyRequirement, BoundRequirement
from mcda_studio.domain.scales import Scale
from mcda_studio.domain.validation import ValidationReport, validate_structure
from mcda_studio.services import results_service as results


def number(x: float) -> str:
    """A limit or measurement at full precision, without a trailing ``.0``."""
    text = repr(float(x))
    return text[:-2] if text.endswith(".0") else text


def check_requirements(project: Project) -> list[Issue]:
    """The rules for the requirements list, after the structural checks."""
    issues: list[Issue] = []

    def add(code: str, message: str, path: str, severity: Severity = Severity.ERROR) -> None:
        issues.append(Issue(severity=severity, code=code, message=message, path=path))

    if not project.requirements:
        add("NO_REQUIREMENTS", "the project states no requirements", "requirements")
        return issues
    try:
        tree = project.tree()
    except ModelStructureError:
        return issues  # the structural checks report the broken tree
    seen: set[str] = set()
    for r in project.requirements:
        where = f"requirements[{r.id}]"
        if r.id in seen:
            add("DUPLICATE_REQUIREMENT_ID", f"requirement id {r.id!r} is used twice", where)
            continue
        seen.add(r.id)
        if r.criterion_id not in tree or not tree.is_leaf(r.criterion_id):
            add(
                "UNKNOWN_REQUIREMENT_CRITERION",
                f"{r.criterion_id!r} is not a leaf criterion of this project",
                where,
            )
            continue
        scale = tree.node(r.criterion_id).scale
        if scale is None or (isinstance(r, BoundRequirement) != scale.is_numeric):
            add(
                "REQUIREMENT_SCALE_MISMATCH",
                "a bound needs a numeric leaf, and allowed labels a labelled one",
                where,
            )
            continue
        if isinstance(r, BoundRequirement):
            if r.unit != scale.unit:
                add(
                    "REQUIREMENT_UNIT_MISMATCH",
                    f"the bound is in {r.unit!r} but the leaf is measured in {scale.unit!r}; "
                    "nothing is converted",
                    f"{where}.unit",
                )
            if r.minimum is None and r.maximum is None:
                add("EMPTY_REQUIREMENT", "a bound needs a minimum, a maximum or both", where)
            elif (
                r.minimum is not None
                and r.maximum is not None
                and (
                    r.minimum > r.maximum
                    or (
                        r.minimum == r.maximum and not (r.minimum_inclusive and r.maximum_inclusive)
                    )
                )
            ):
                add("INVALID_BOUNDS", "no measurement can lie within these limits", where)
            continue
        if not r.allowed:
            add("EMPTY_REQUIREMENT", "a labels requirement needs at least one allowed label", where)
            continue
        unknown = [label for label in r.allowed if label not in scale.labels]
        if unknown:
            add(
                "UNKNOWN_REQUIRED_LABEL",
                f"allowed labels the scale does not have: {unknown}",
                f"{where}.allowed",
            )
        elif set(scale.labels) <= set(r.allowed):
            add(
                "REQUIREMENT_ALWAYS_PASSES",
                "every label of the scale is allowed, so this requirement never fails",
                where,
                Severity.WARNING,
            )
    return issues


def validate_requirements(project: Project) -> ValidationReport:
    structure = validate_structure(project).issues
    return ValidationReport(issues=[*structure, *check_requirements(project)])


def _check(r: AnyRequirement, scale: Scale, x: Measurement | None) -> RequirementCheck:
    def done(status: FeasibilityStatus, reason: str) -> RequirementCheck:
        return RequirementCheck(requirement_id=r.id, status=status, measurement=x, reason=reason)

    if x is None:
        return done("unknown", "no measurement")
    if isinstance(r, BoundRequirement):
        if isinstance(x, str):
            return done("unknown", f"{x!r} is a label, not a number")
        unit = f" {r.unit}" if r.unit else ""
        value = f"{number(x)}{unit}"
        if r.minimum is not None:
            if r.minimum_inclusive and not x >= r.minimum:
                return done("fail", f"{value} is below the minimum {number(r.minimum)}{unit}")
            if not r.minimum_inclusive and not x > r.minimum:
                return done(
                    "fail", f"{value} is not above the exclusive minimum {number(r.minimum)}{unit}"
                )
        if r.maximum is not None:
            if r.maximum_inclusive and not x <= r.maximum:
                return done("fail", f"{value} is above the maximum {number(r.maximum)}{unit}")
            if not r.maximum_inclusive and not x < r.maximum:
                return done(
                    "fail", f"{value} is not below the exclusive maximum {number(r.maximum)}{unit}"
                )
        return done("pass", f"{value} is within the limits")
    if not isinstance(x, str):
        return done("unknown", f"{number(x)} is a number, not a label")
    if x not in scale.labels:
        return done("unknown", f"{x!r} is not one of the scale's labels")
    if x in r.allowed:
        return done("pass", f"{x} is allowed")
    return done("fail", f"{x} is not one of the allowed labels {r.allowed}")


def overall(statuses: list[FeasibilityStatus]) -> FeasibilityStatus:
    """Any fail is fail; otherwise any unknown is unknown; otherwise pass."""
    if "fail" in statuses:
        return "fail"
    if "unknown" in statuses:
        return "unknown"
    return "pass"


def check_feasibility(project: Project) -> FeasibilityResult:
    report = validate_requirements(project)
    if not report.ok:
        raise ValidationFailed(report)
    assert project.requirements  # guaranteed by validation (NO_REQUIREMENTS)
    tree = project.tree()
    raw = project.performance_index()
    counts = Counter((p.alternative_id, p.criterion_id) for p in project.performances)
    alternatives = []
    for alt in project.alternatives:
        checks = []
        for r in project.requirements:
            scale = tree.node(r.criterion_id).scale
            assert scale is not None  # guaranteed by validation
            key = (alt.id, r.criterion_id)
            if counts[key] > 1:
                checks.append(
                    RequirementCheck(
                        requirement_id=r.id,
                        status="unknown",
                        measurement=None,
                        reason="multiple measurements for this alternative and criterion",
                    )
                )
            else:
                checks.append(_check(r, scale, raw.get(key)))
        alternatives.append(
            AlternativeFeasibility(
                alternative_id=alt.id,
                name=alt.name,
                status=overall([c.status for c in checks]),
                checks=checks,
                failed=[c.requirement_id for c in checks if c.status == "fail"],
                unknown=[c.requirement_id for c in checks if c.status == "unknown"],
            )
        )
    summary = []
    for k, r in enumerate(project.requirements):
        statuses = [a.checks[k].status for a in alternatives]
        summary.append(
            RequirementSummary(
                requirement_id=r.id,
                name=r.name,
                criterion_id=r.criterion_id,
                passed=statuses.count("pass"),
                failed=statuses.count("fail"),
                unknown=statuses.count("unknown"),
            )
        )
    return FeasibilityResult(
        project_id=project.id,
        project_fingerprint=project.fingerprint(),
        requirements=[r.model_copy(deep=True) for r in project.requirements],
        alternatives=alternatives,
        summary=summary,
        diagnostics=report.warnings,
    )


def export_feasibility(
    project: Project, expected_project_fingerprint: str, format_: Literal["json", "csv"]
) -> tuple[bytes, str, str, FeasibilityResult]:
    """The result as JSON, or a CSV with one row per alternative and requirement."""
    if project.fingerprint() != expected_project_fingerprint:
        raise StaleRevisionError("Export project does not match the displayed feasibility check.")
    result = check_feasibility(project)
    stem = f"mcda-{project.id}-{result.project_fingerprint[:12]}-feasibility"
    if format_ == "json":
        body = result.model_dump(mode="json")
        text = json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False)
        data = (text + "\n").encode("utf-8")
    else:
        buffer = results._BoundedBuffer()
        writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        writer.writerow(
            [
                "project_id",
                "project_fingerprint",
                "alternative_id",
                "alternative_name",
                "overall_status",
                "requirement_id",
                "requirement_name",
                "criterion_id",
                "requirement",
                "measurement",
                "status",
                "reason",
                "label",
            ]
        )
        by_id = {r.id: r for r in result.requirements}
        for a in result.alternatives:
            for c in a.checks:
                r = by_id[c.requirement_id]
                row: list[str | int | float | None] = [
                    project.id,
                    result.project_fingerprint,
                    a.alternative_id,
                    a.name,
                    a.status,
                    r.id,
                    r.name,
                    r.criterion_id,
                    results.canonical_json(r.model_dump(mode="json")),
                    c.measurement,
                    c.status,
                    c.reason,
                    result.label,
                ]
                writer.writerow(
                    [
                        ""
                        if v is None
                        else results.safe_csv_text(v)
                        if isinstance(v, str)
                        else str(v)
                        for v in row
                    ]
                )
        data = buffer.getvalue().encode("utf-8")
    if len(data) > results.MAX_EXPORT_BYTES:
        raise AnalysisLimitError("Feasibility export exceeds the 16 MiB download limit.")
    media = "application/json" if format_ == "json" else "text/csv"
    return data, media, f"{stem}.{format_}", result
