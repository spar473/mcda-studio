"""PROMETHEE II's own rules for its section (design note §6). MAVT's checks do not apply."""

from pydantic import BaseModel, ConfigDict

from mcda_studio.domain.common import Issue, Severity
from mcda_studio.domain.errors import ModelStructureError
from mcda_studio.domain.outranking import (
    AnyPreferenceFunction,
    LinearPreferenceFunction,
    PrometheeCriterion,
    UShapeFunction,
    VShapeFunction,
    thresholds,
)
from mcda_studio.domain.project import Project
from mcda_studio.domain.scales import ScaleType

#: Differences and thresholds are compared as equal within this share of the larger magnitude.
THRESHOLD_REL = 1e-12


class PrometheeParameters(BaseModel):
    # PROMETHEE II has no parameters; unknown keys are reported as UNKNOWN_PARAMETER and ignored.
    model_config = ConfigDict(extra="ignore", frozen=True)


def threshold_tolerance(x_a: float, x_b: float) -> float:
    return THRESHOLD_REL * max(1.0, abs(x_a), abs(x_b))


def function_problem(function: AnyPreferenceFunction) -> str | None:
    if isinstance(function, UShapeFunction) and function.q < 0:
        return "the U-shape function needs q >= 0"
    if isinstance(function, VShapeFunction) and function.p <= 0:
        return "the V-shape function needs p > 0"
    if isinstance(function, LinearPreferenceFunction) and not 0 <= function.q < function.p:
        return "the linear function needs 0 <= q < p"
    return None


def coded_measurements(project: Project, entry: PrometheeCriterion) -> list[float] | None:
    """The leaf's measurements as numbers (codes on a labelled leaf); None if any is unusable."""
    node = project.tree().node(entry.criterion_id)
    if node.scale is None:
        return None
    raw = project.performance_index()
    out: list[float] = []
    for alt in project.alternative_ids():
        value = raw.get((alt, entry.criterion_id))
        if node.scale.is_numeric:
            if value is None or isinstance(value, str):
                return None
            out.append(float(value))
        else:
            if not isinstance(value, str) or entry.coding is None or value not in entry.coding:
                return None
            out.append(entry.coding[value])
    return out


def check_promethee(project: Project) -> list[Issue]:
    """The rules for the section, after the method-independent measurement checks."""
    issues: list[Issue] = []

    def add(code: str, message: str, path: str, severity: Severity = Severity.ERROR) -> None:
        issues.append(Issue(severity=severity, code=code, message=message, path=path))

    model = project.promethee
    if model is None:
        add(
            "PROMETHEE_NOT_STATED",
            "PROMETHEE II needs its own inputs (direction, weight and preference function per "
            "leaf); the project states none",
            "promethee",
        )
        return issues
    if len(project.alternatives) < 2:
        add(
            "PROMETHEE_TOO_FEW_ALTERNATIVES",
            "PROMETHEE II compares alternatives with one another: it needs at least two",
            "alternatives",
        )
    try:
        tree = project.tree()
    except ModelStructureError:
        return issues  # the measurement checks report the broken tree
    leaves = tree.leaves()
    stated: dict[str, PrometheeCriterion] = {}
    for entry in model.criteria:
        where = f"promethee.criteria[{entry.criterion_id}]"
        if entry.criterion_id not in tree or not tree.is_leaf(entry.criterion_id):
            add(
                "UNKNOWN_PROMETHEE_CRITERION",
                f"{entry.criterion_id!r} is not a leaf criterion of this project",
                where,
            )
            continue
        if entry.criterion_id in stated:
            add("DUPLICATE_PROMETHEE_CRITERION", "this leaf has more than one entry", where)
            continue
        stated[entry.criterion_id] = entry
        if problem := function_problem(entry.function):
            add("INVALID_PREFERENCE_FUNCTION", problem, f"{where}.function")
        if entry.weight < 0:
            add("INVALID_PROMETHEE_WEIGHT", "a weight must not be negative", f"{where}.weight")
        scale = tree.node(entry.criterion_id).scale
        if scale is None:
            continue  # the measurement checks report the missing scale
        if scale.is_numeric:
            if entry.coding is not None:
                add(
                    "UNEXPECTED_CODING",
                    "a numeric leaf is compared on its measurements; it takes no coding",
                    f"{where}.coding",
                )
            continue
        coding = entry.coding or {}
        missing = [label for label in scale.labels if label not in coding]
        if missing:
            add(
                "CODING_MISSING",
                f"a labelled leaf needs a number for each of its labels; missing {missing}",
                f"{where}.coding",
            )
        unknown = sorted(set(coding) - set(scale.labels))
        if unknown:
            add(
                "UNKNOWN_CODED_LABEL",
                f"codes are given for labels the scale does not have: {unknown}",
                f"{where}.coding",
            )
        if scale.type is ScaleType.ORDINAL and not missing:
            codes = [coding[label] for label in scale.labels]
            if any(b <= a for a, b in zip(codes, codes[1:], strict=False)):
                add(
                    "ORDINAL_CODING_UNORDERED",
                    "the codes do not increase with the scale's label order (low to high)",
                    f"{where}.coding",
                    Severity.WARNING,
                )
    for leaf in leaves:
        if leaf not in stated:
            add(
                "PROMETHEE_CRITERION_MISSING",
                f"leaf {leaf!r} has no direction, weight and preference function",
                f"promethee.criteria[{leaf}]",
            )
    weights = [e.weight for e in stated.values()]
    if weights and all(w == 0 for w in weights):
        add(
            "ZERO_PROMETHEE_WEIGHTS",
            "every weight is zero, so the weights cannot be normalised",
            "promethee.criteria",
        )
        return issues
    for leaf, entry in stated.items():
        where = f"promethee.criteria[{leaf}]"
        if entry.weight == 0:
            add(
                "PROMETHEE_CRITERION_INERT",
                "weight 0: this criterion never contributes to the net flows",
                where,
                Severity.WARNING,
            )
            continue
        values = coded_measurements(project, entry)
        if values is None or function_problem(entry.function):
            continue
        q = thresholds(entry.function)[0] or 0.0
        spread = max(values) - min(values)
        if spread <= q + threshold_tolerance(max(values), min(values)):
            observed = f"{spread:.6g}"
            add(
                "PROMETHEE_CRITERION_INERT",
                f"the largest difference observed ({observed}) is at or below q = {q:.6g}: "
                "this criterion never contributes"
                if q
                else "every alternative measures the same: this criterion never contributes",
                where,
                Severity.WARNING,
            )
    return issues
