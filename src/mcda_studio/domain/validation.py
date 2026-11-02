"""Model-completeness validation.

``validate_project`` never raises for a *semantic* problem; it returns a report so that an editor
can show every problem at once and so that incomplete (e.g. blank) projects can be saved.
Evaluation refuses to run while the report contains errors.
"""

import contextlib
import math
from collections import Counter
from collections.abc import Sequence

from mcda_studio.domain.common import DomainModel, Issue, Severity
from mcda_studio.domain.criteria import (
    ALLOWED_VALUE_FUNCTIONS,
    CriterionNode,
    CriterionTree,
    DirectRatingValueFunction,
    LinearValueFunction,
    PiecewiseLinearValueFunction,
    QualitativeValueFunction,
    ValueFunctionSpec,
)
from mcda_studio.domain.errors import ModelStructureError, UnknownReferenceError
from mcda_studio.domain.measurements import Measurement, effective_domain
from mcda_studio.domain.preferences import AnalysisConfiguration, check_judgements
from mcda_studio.domain.project import Project
from mcda_studio.domain.scales import AnchorMode, Scale, ScaleType

_REL_TOL = 1e-9
#: spread/magnitude below which local anchors are numerically meaningless (see NEAR_DEGENERATE)
_NEAR_DEGENERATE_REL = 1e-9


class ValidationReport(DomainModel):
    issues: list[Issue]

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors


class _Collector:
    def __init__(self) -> None:
        self.issues: list[Issue] = []

    def add(self, severity: Severity, code: str, message: str, path: str = "") -> None:
        self.issues.append(Issue(severity=severity, code=code, message=message, path=path))

    def error(self, code: str, message: str, path: str = "") -> None:
        self.add(Severity.ERROR, code, message, path)

    def warn(self, code: str, message: str, path: str = "") -> None:
        self.add(Severity.WARNING, code, message, path)


def _duplicates(values: Sequence[str]) -> list[str]:
    return [v for v, n in Counter(values).items() if n > 1]


def validate_project(
    project: Project, configuration: AnalysisConfiguration | None = None
) -> ValidationReport:
    cfg = configuration or project.analysis
    c = _Collector()

    for dup in _duplicates([a.id for a in project.alternatives]):
        c.error("DUPLICATE_ALTERNATIVE_ID", f"alternative id {dup!r} is used more than once")
    for dup in _duplicates([p.id for p in project.weight_profiles]):
        c.error("DUPLICATE_PROFILE_ID", f"weight profile id {dup!r} is used more than once")
    for dup in _duplicates([s.id for s in project.scenarios]):
        c.error("DUPLICATE_SCENARIO_ID", f"scenario id {dup!r} is used more than once")
    names = _duplicates([a.name.strip().casefold() for a in project.alternatives])
    for dup in names:
        c.warn("DUPLICATE_ALTERNATIVE_NAME", f"several alternatives are named {dup!r}")

    if not project.alternatives:
        c.error("NO_ALTERNATIVES", "the project has no alternatives")
    elif len(project.alternatives) == 1:
        c.warn("SINGLE_ALTERNATIVE", "only one alternative: a ranking is trivial")
    if not project.criteria:
        c.error("NO_CRITERIA", "the project has no criteria")

    try:
        tree = project.tree()
    except ModelStructureError as exc:
        c.error("INVALID_TREE", str(exc))
        return ValidationReport(issues=c.issues)

    alt_ids = [a.id for a in project.alternatives]
    leaves = tree.leaves()
    leaf_set = set(leaves)
    _check_performance_table(c, project, tree)
    perf = project.performance_index()
    _check_parent_data(c, tree)

    # ---- leaf models: base project, then every scenario's overrides -----------------------
    for leaf in leaves:
        node = tree.node(leaf)
        _check_leaf(c, f"criteria[{leaf}]", node, node.value_function, alt_ids, perf, report=True)
    for scenario in project.scenarios:
        for leaf, vf in scenario.value_function_overrides.items():
            where = f"scenarios[{scenario.id}].value_function_overrides[{leaf}]"
            if leaf not in leaf_set:
                c.error("UNKNOWN_OVERRIDE_TARGET", f"{leaf!r} is not a leaf criterion", where)
                continue
            _check_leaf(c, where, tree.node(leaf), vf, alt_ids, perf, report=False)

    # ---- weights, scenarios, configuration ------------------------------------------------
    if not project.weight_profiles:
        c.error("NO_WEIGHT_PROFILE", "the project has no weight profile")
    for prof in project.weight_profiles:
        if prof.method != "swing":
            c.error(
                "UNSUPPORTED_WEIGHT_METHOD",
                f"weight method {prof.method!r} is not supported (only 'swing')",
                f"weight_profiles[{prof.id}]",
            )
        c.issues.extend(check_judgements(tree, prof.judgements, f"weight_profiles[{prof.id}]"))
    profile_ids = {p.id for p in project.weight_profiles}
    for scenario in project.scenarios:
        if scenario.weight_profile_id and scenario.weight_profile_id not in profile_ids:
            c.error(
                "UNKNOWN_PROFILE",
                f"unknown weight profile {scenario.weight_profile_id!r}",
                f"scenarios[{scenario.id}]",
            )
    if cfg.weight_profile_id and cfg.weight_profile_id not in profile_ids:
        c.error(
            "UNKNOWN_PROFILE", f"unknown weight profile {cfg.weight_profile_id!r}", "configuration"
        )
    if cfg.scenario_id and cfg.scenario_id not in {s.id for s in project.scenarios}:
        c.error("UNKNOWN_SCENARIO", f"unknown scenario {cfg.scenario_id!r}", "configuration")
    else:
        with contextlib.suppress(UnknownReferenceError):
            project.resolve_profile(cfg)  # unknown ids were already reported above
    return ValidationReport(issues=c.issues)


def _check_performance_table(c: _Collector, project: Project, tree: CriterionTree) -> None:
    """Every entry names a known alternative and leaf, once."""
    alt_set = set(project.alternative_ids())
    leaf_set = set(tree.leaves())
    seen: set[tuple[str, str]] = set()
    for p in project.performances:
        where = f"performances[{p.alternative_id},{p.criterion_id}]"
        if p.alternative_id not in alt_set:
            c.error("UNKNOWN_ALTERNATIVE", f"unknown alternative {p.alternative_id!r}", where)
        if p.criterion_id not in tree:
            c.error("UNKNOWN_CRITERION", f"unknown criterion {p.criterion_id!r}", where)
        elif p.criterion_id not in leaf_set:
            c.error(
                "MEASUREMENT_ON_NON_LEAF",
                f"{p.criterion_id!r} is not a leaf criterion; it cannot be measured",
                where,
            )
        key = (p.alternative_id, p.criterion_id)
        if key in seen:
            c.error("DUPLICATE_MEASUREMENT", "measurement given more than once", where)
        seen.add(key)


def _check_parent_data(c: _Collector, tree: CriterionTree) -> None:
    """Non-leaf nodes must not carry leaf data."""
    for node_id in tree.all_ids():
        node = tree.node(node_id)
        if not tree.is_leaf(node_id) and (node.scale or node.value_function):
            c.error(
                "LEAF_DATA_ON_PARENT",
                "a criterion with children must not have its own scale or value function",
                f"criteria[{node_id}]",
            )


def _check_measurements(
    c: _Collector,
    node: CriterionNode,
    scale: Scale,
    alt_ids: Sequence[str],
    perf: dict[tuple[str, str], Measurement],
) -> tuple[list[float], bool]:
    """Presence and type of one leaf's measurements: the numbers, and whether all are usable."""
    numeric: list[float] = []
    all_present = True
    for alt in alt_ids:
        where = f"performances[{alt},{node.id}]"
        value = perf.get((alt, node.id))
        if value is None:
            c.error("MISSING_MEASUREMENT", f"no measurement for {alt!r} on {node.id!r}", where)
            all_present = False
            continue
        if scale.is_numeric:
            if isinstance(value, str):
                c.error(
                    "INVALID_MEASUREMENT_TYPE",
                    f"expected a number on a {scale.type.value} scale, got {value!r}",
                    where,
                )
                all_present = False
            else:
                if scale.type is ScaleType.RATIO and value < 0:
                    c.error(
                        "NEGATIVE_RATIO_VALUE", f"ratio-scale value {value} must be >= 0", where
                    )
                numeric.append(float(value))
        else:
            if not isinstance(value, str) or value not in scale.labels:
                c.error(
                    "INVALID_LABEL",
                    f"{value!r} is not one of the scale labels {scale.labels}",
                    where,
                )
                all_present = False
    return numeric, all_present


def _check_structure(c: _Collector, project: Project) -> CriterionTree | None:
    """Alternatives, criteria and the tree; ``None`` when the tree cannot be built."""
    for dup in _duplicates([a.id for a in project.alternatives]):
        c.error("DUPLICATE_ALTERNATIVE_ID", f"alternative id {dup!r} is used more than once")
    for dup in _duplicates([a.name.strip().casefold() for a in project.alternatives]):
        c.warn("DUPLICATE_ALTERNATIVE_NAME", f"several alternatives are named {dup!r}")
    if not project.alternatives:
        c.error("NO_ALTERNATIVES", "the project has no alternatives")
    if not project.criteria:
        c.error("NO_CRITERIA", "the project has no criteria")
    try:
        return project.tree()
    except ModelStructureError as exc:
        c.error("INVALID_TREE", str(exc))
        return None


def validate_structure(project: Project) -> ValidationReport:
    """The method-independent checks for a method that reads neither measurements nor MAVT's
    value model: alternatives, criteria and the tree."""
    c = _Collector()
    _check_structure(c, project)
    return ValidationReport(issues=c.issues)


def validate_measurements(project: Project) -> ValidationReport:
    """The method-independent checks for a method that reads raw measurements rather than MAVT's
    value model: alternatives, the tree, the performance table, and each leaf's scale and
    measurements. Value functions, weight profiles and scenarios are not checked."""
    c = _Collector()
    tree = _check_structure(c, project)
    if tree is None:
        return ValidationReport(issues=c.issues)
    _check_performance_table(c, project, tree)
    _check_parent_data(c, tree)
    perf = project.performance_index()
    alt_ids = project.alternative_ids()
    for leaf in tree.leaves():
        node = tree.node(leaf)
        path = f"criteria[{leaf}]"
        if node.scale is None:
            c.error("MISSING_SCALE", "leaf criterion has no measurement scale", path)
            continue
        _check_scale(c, path, node.scale)
        _check_measurements(c, node, node.scale, alt_ids, perf)
    return ValidationReport(issues=c.issues)


def _check_leaf(
    c: _Collector,
    path: str,
    node: CriterionNode,
    vf: ValueFunctionSpec | None,
    alt_ids: Sequence[str],
    perf: dict[tuple[str, str], Measurement],
    *,
    report: bool,
) -> None:
    """Check one leaf's scale, value function (``vf``) and measurements.

    ``report`` is False when re-checking a scenario override, to avoid repeating scale errors.
    """
    scale = node.scale
    if scale is None:
        if report:
            c.error("MISSING_SCALE", "leaf criterion has no measurement scale", path)
        return
    if vf is None:
        c.error("MISSING_VALUE_FUNCTION", "leaf criterion has no value function", path)
        return
    if report:
        _check_scale(c, path, scale)
    if vf.kind not in ALLOWED_VALUE_FUNCTIONS[scale.type]:
        c.error(
            "INCOMPATIBLE_VALUE_FUNCTION",
            f"a {vf.kind!r} value function is not meaningful on a {scale.type.value} scale",
            path,
        )
        return

    numeric, all_present = _check_measurements(c, node, scale, alt_ids, perf)

    # value-function specifics
    if isinstance(vf, LinearValueFunction):
        if scale.anchor_mode is AnchorMode.FIXED:
            if scale.lower is None or scale.upper is None:
                c.error(
                    "MISSING_ANCHORS",
                    "a linear value function on a fixed-anchor scale needs both lower and upper",
                    path,
                )
        else:
            # Always warn, including for a scenario override: ``report`` only suppresses repeated
            # *scale* errors; an override that introduces local anchors changes the model's
            # dependence on the alternative set and the path says where it comes from.
            c.warn(
                "LOCAL_ANCHORS",
                "anchors are derived from the alternatives: adding or "
                "removing an alternative can change every score on this criterion",
                path,
            )
            if all_present and numeric and min(numeric) == max(numeric):
                c.error(
                    "DEGENERATE_LOCAL_ANCHORS",
                    "identical minimum and maximum over the alternatives: "
                    "the linear function is undefined",
                    path,
                )
            elif all_present and numeric:
                lo, hi = min(numeric), max(numeric)
                if hi - lo <= _NEAR_DEGENERATE_REL * max(abs(lo), abs(hi)):
                    c.warn(
                        "NEAR_DEGENERATE_LOCAL_ANCHORS",
                        "the alternatives differ only at floating-point noise level relative to "
                        "their magnitude; a local linear function would stretch that noise over "
                        "the whole 0-1 range",
                        path,
                    )
    elif isinstance(vf, PiecewiseLinearValueFunction):
        _check_piecewise(c, path, vf)
    elif isinstance(vf, QualitativeValueFunction):
        _check_qualitative(c, path, scale, vf)
    elif isinstance(vf, DirectRatingValueFunction) and not vf.min_rating < vf.max_rating:
        c.error("REVERSED_BOUNDS", "min_rating must be less than max_rating", path)

    # domain: no silent extrapolation
    if scale.is_numeric and numeric and not isinstance(vf, QualitativeValueFunction):
        domain = effective_domain(scale, vf, numeric)
        policy = getattr(vf, "out_of_domain", "error")
        if domain is not None and domain.lower < domain.upper:
            tol = _REL_TOL * (domain.upper - domain.lower)
            for alt in alt_ids:
                value = perf.get((alt, node.id))
                if isinstance(value, str) or value is None:
                    continue
                if value < domain.lower - tol or value > domain.upper + tol:
                    where = f"performances[{alt},{node.id}]"
                    msg = (
                        f"{value} is outside the value-function domain "
                        f"[{domain.lower}, {domain.upper}]"
                    )
                    if policy == "clamp":
                        c.warn("CLAMPED_MEASUREMENT", msg + "; it will be clamped", where)
                    else:
                        c.error("OUT_OF_DOMAIN", msg + "; extrapolation is not performed", where)


def validate_leaf_model(
    node: CriterionNode,
    value_function: ValueFunctionSpec | None,
    alternative_ids: Sequence[str],
    performances: dict[tuple[str, str], Measurement],
    *,
    path: str | None = None,
) -> ValidationReport:
    """The same leaf rules as full validation, scoped for read-only previews.

    Empty alternatives validate a fixed definition without demanding measurements. Callers of
    local-anchor previews must additionally require the complete relevant measurement set.
    """
    collector = _Collector()
    _check_leaf(
        collector,
        path or f"criteria[{node.id}]",
        node,
        value_function,
        alternative_ids,
        performances,
        report=True,
    )
    return ValidationReport(issues=collector.issues)


def _check_scale(c: _Collector, path: str, scale: Scale) -> None:
    if scale.is_numeric:
        if scale.labels:
            c.warn("UNUSED_LABELS", "labels are ignored on a numeric scale", path)
        if scale.lower is not None and scale.upper is not None and not scale.lower < scale.upper:
            c.error(
                "REVERSED_BOUNDS",
                f"lower ({scale.lower}) must be strictly less than upper ({scale.upper})",
                path,
            )
        if scale.type is ScaleType.RATIO and scale.lower is not None and scale.lower < 0:
            c.error(
                "NEGATIVE_RATIO_BOUND", "a ratio scale cannot have a negative lower bound", path
            )
    else:
        if len(scale.labels) < 2:
            c.error("TOO_FEW_LABELS", "a categorical/ordinal scale needs at least two labels", path)
        for dup in _duplicates(scale.labels):
            c.error("DUPLICATE_LABEL", f"label {dup!r} appears more than once", path)


def _check_piecewise(c: _Collector, path: str, vf: PiecewiseLinearValueFunction) -> None:
    pts = vf.points
    if len(pts) < 2:
        c.error("TOO_FEW_CONTROL_POINTS", "a piecewise function needs at least two points", path)
        return
    xs = [p.x for p in pts]
    vs = [p.value for p in pts]
    if any(b <= a for a, b in zip(xs, xs[1:], strict=False)):
        c.error(
            "CONTROL_POINTS_NOT_ORDERED", "control-point x values must be strictly increasing", path
        )
        return
    if any(v < 0 or v > 1 for v in vs):
        c.error("CONTROL_VALUE_RANGE", "control-point values must lie in [0, 1]", path)
        return
    non_dec = all(b >= a for a, b in zip(vs, vs[1:], strict=False))
    non_inc = all(b <= a for a, b in zip(vs, vs[1:], strict=False))
    if not (non_dec or non_inc) or vs[0] == vs[-1]:
        c.error(
            "NON_MONOTONE_VALUE_FUNCTION",
            "values must be monotone (non-decreasing or non-increasing) and not constant",
            path,
        )
        return
    lo, hi = (vs[0], vs[-1]) if non_dec else (vs[-1], vs[0])
    if lo != 0.0 or hi != 1.0:
        c.error(
            "ENDPOINT_CONVENTION",
            "the worst end must have value 0 and the best end value 1 "
            "(normalisation to [0, 1] over the swing range)",
            path,
        )


def _check_qualitative(
    c: _Collector, path: str, scale: Scale, vf: QualitativeValueFunction
) -> None:
    if set(vf.mapping) != set(scale.labels):
        missing = sorted(set(scale.labels) - set(vf.mapping))
        extra = sorted(set(vf.mapping) - set(scale.labels))
        c.error(
            "MAPPING_LABEL_MISMATCH",
            f"mapping must cover exactly the scale labels (missing {missing}, extra {extra})",
            path,
        )
        return
    if not scale.labels:
        return  # _check_scale reports the incomplete labelled scale; never min([]).
    vals = [vf.mapping[label] for label in scale.labels]
    if any(not math.isfinite(v) or v < 0 or v > 1 for v in vals):
        c.error("MAPPING_VALUE_RANGE", "mapped preference values must lie in [0, 1]", path)
        return
    if min(vals) != 0.0 or max(vals) != 1.0:
        c.error(
            "ENDPOINT_CONVENTION", "the worst label must map to 0 and the best label to 1", path
        )
    if scale.type is ScaleType.ORDINAL and any(b < a for a, b in zip(vals, vals[1:], strict=False)):
        c.error(
            "ORDINAL_ORDER_VIOLATED",
            "ordinal labels are ordered low -> high, so mapped values must not decrease",
            path,
        )


def require_valid(
    project: Project, configuration: AnalysisConfiguration | None = None
) -> ValidationReport:
    """Return the report if it has no errors; otherwise raise ValidationFailed."""
    from mcda_studio.domain.errors import ValidationFailed

    report = validate_project(project, configuration)
    if not report.ok:
        raise ValidationFailed(report)
    return report


__all__ = [
    "CriterionTree",
    "ValidationReport",
    "check_configuration_ids",
    "require_valid",
    "validate_measurements",
    "validate_project",
    "validate_structure",
    "validate_value_model",
]


def check_configuration_ids(project: Project) -> list[Issue]:
    """Method-independent: a configuration can only name a profile or scenario unambiguously."""
    c = _Collector()
    for kind, values in [
        ("PROFILE", [p.id for p in project.weight_profiles]),
        ("SCENARIO", [s.id for s in project.scenarios]),
    ]:
        for duplicate in _duplicates(values):
            c.error(f"DUPLICATE_{kind}_ID", f"ambiguous {kind.lower()} id {duplicate!r}")
    return c.issues


def validate_value_model(
    project: Project, configuration: AnalysisConfiguration
) -> ValidationReport:
    """Validate only the effective value model (MAVT and the methods built on its values).

    The project-wide report remains unchanged for the editor. A detached validation view selects
    the effective functions/profile; it is never saved and never changes the source fingerprint.
    The method dispatch, and the method-independent checks before it, are in
    ``mcda_studio.methods.base.validate_analysis``.
    """
    c = _Collector()
    try:
        scenario = project.resolve_scenario(configuration)
    except UnknownReferenceError as exc:
        c.error("UNKNOWN_SCENARIO", str(exc), "configuration")
        return ValidationReport(issues=c.issues)
    try:
        profile = project.resolve_profile(configuration)
    except UnknownReferenceError as exc:
        c.error("UNKNOWN_PROFILE", str(exc), "configuration")
        return ValidationReport(issues=c.issues)
    try:
        tree = project.tree()
    except ModelStructureError as exc:
        c.error("INVALID_TREE", str(exc))
        return ValidationReport(issues=c.issues)
    view = project.model_copy(deep=True)
    overrides = scenario.value_function_overrides if scenario else {}
    for target, vf in overrides.items():
        if target not in tree or not tree.is_leaf(target):
            c.error(
                "UNKNOWN_OVERRIDE_TARGET",
                f"{target!r} is not a leaf criterion",
                f"scenarios[{configuration.scenario_id}].value_function_overrides[{target}]",
            )
        else:
            next(n for n in view.criteria if n.id == target).value_function = vf.model_copy(
                deep=True
            )
    view.scenarios = []
    view.weight_profiles = [profile.model_copy(deep=True)] if profile else []
    view.analysis = configuration.model_copy(update={"scenario_id": None})
    report = validate_project(view, view.analysis)
    for issue in report.issues:
        # Translate addresses, not messages; effective override diagnostics belong to that scenario.
        for target in overrides:
            prefix = f"criteria[{target}]"
            if issue.path == prefix or issue.path.startswith(prefix + "."):
                issue = issue.model_copy(
                    update={
                        "path": issue.path.replace(
                            prefix,
                            f"scenarios[{configuration.scenario_id}].value_function_overrides[{target}]",
                            1,
                        )
                    }
                )
                break
        c.issues.append(issue)
    return ValidationReport(issues=c.issues)
