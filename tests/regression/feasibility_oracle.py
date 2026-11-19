"""Independent plain-Python oracle for the feasibility check. It never imports mcda_studio.

It reads a project file as plain JSON and recomputes from the design note alone: the validation
codes of the requirements list, each requirement's pass, fail or unknown with the class of its
reason, and each alternative's overall status. Comparisons are exact; there is no tolerance.
"""

from typing import Any

Project = dict[str, Any]
NUMERIC = ("interval", "ratio")


def _leaves(project: Project) -> dict[str, dict[str, Any]]:
    parents = {c.get("parent_id") for c in project["criteria"]}
    return {c["id"]: c for c in project["criteria"] if c["id"] not in parents}


def issues(project: Project) -> list[tuple[str, str]]:
    """(code, severity) for every rule the requirements list breaks, in list order."""
    requirements = project.get("requirements") or []
    if not requirements:
        return [("NO_REQUIREMENTS", "error")]
    leaves = _leaves(project)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for r in requirements:
        if r["id"] in seen:
            out.append(("DUPLICATE_REQUIREMENT_ID", "error"))
            continue
        seen.add(r["id"])
        leaf = leaves.get(r["criterion_id"])
        if leaf is None:
            out.append(("UNKNOWN_REQUIREMENT_CRITERION", "error"))
            continue
        scale = leaf["scale"]
        if (r["kind"] == "bound") != (scale["type"] in NUMERIC):
            out.append(("REQUIREMENT_SCALE_MISMATCH", "error"))
            continue
        if r["kind"] == "bound":
            if r.get("unit") != scale.get("unit"):
                out.append(("REQUIREMENT_UNIT_MISMATCH", "error"))
            lo, hi = r.get("minimum"), r.get("maximum")
            if lo is None and hi is None:
                out.append(("EMPTY_REQUIREMENT", "error"))
            elif lo is not None and hi is not None:
                closed = r.get("minimum_inclusive", True) and r.get("maximum_inclusive", True)
                if lo > hi or (lo == hi and not closed):
                    out.append(("INVALID_BOUNDS", "error"))
            continue
        allowed = r["allowed"]
        if not allowed:
            out.append(("EMPTY_REQUIREMENT", "error"))
        elif any(label not in scale["labels"] for label in allowed):
            out.append(("UNKNOWN_REQUIRED_LABEL", "error"))
        elif all(label in allowed for label in scale["labels"]):
            out.append(("REQUIREMENT_ALWAYS_PASSES", "warning"))
    return out


def check(requirement: dict[str, Any], scale: dict[str, Any], x: Any) -> tuple[str, str]:
    """(status, reason class) for one measurement; ``x`` is None when there is none."""
    if x is None:
        return "unknown", "missing"
    is_label = isinstance(x, str)
    if requirement["kind"] == "bound":
        if is_label:
            return "unknown", "label_on_numeric"
        lo, hi = requirement.get("minimum"), requirement.get("maximum")
        if lo is not None:
            if requirement.get("minimum_inclusive", True):
                if x < lo:
                    return "fail", "below_minimum"
            elif x <= lo:
                return "fail", "not_above_minimum"
        if hi is not None:
            if requirement.get("maximum_inclusive", True):
                if x > hi:
                    return "fail", "above_maximum"
            elif x >= hi:
                return "fail", "not_below_maximum"
        return "pass", "within"
    if not is_label:
        return "unknown", "number_on_labels"
    if x not in scale["labels"]:
        return "unknown", "unknown_label"
    return ("pass", "allowed") if x in requirement["allowed"] else ("fail", "not_allowed")


def evaluate(project: Project) -> dict[str, Any]:
    """{alternative id: {"status": ..., "checks": [(status, reason class), ...]}}."""
    leaves = _leaves(project)
    cells = {(p["alternative_id"], p["criterion_id"]): p["value"] for p in project["performances"]}
    out: dict[str, Any] = {}
    for alt in project["alternatives"]:
        checks = [
            check(r, leaves[r["criterion_id"]]["scale"], cells.get((alt["id"], r["criterion_id"])))
            for r in project["requirements"]
        ]
        statuses = [s for s, _ in checks]
        status = "fail" if "fail" in statuses else "unknown" if "unknown" in statuses else "pass"
        out[alt["id"]] = {"status": status, "checks": checks}
    return out
