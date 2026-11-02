"""Bounded read-only previews using the existing MAVT validators, domains and evaluators."""

import hashlib
import json
import math
from collections import Counter
from typing import Literal

from mcda_studio.domain.common import Issue, Severity
from mcda_studio.domain.criteria import LinearValueFunction, PiecewiseLinearValueFunction
from mcda_studio.domain.errors import ModelStructureError, UnknownReferenceError, WeightError
from mcda_studio.domain.measurements import effective_domain
from mcda_studio.domain.preferences import AnalysisConfiguration, check_judgements
from mcda_studio.domain.previews import (
    MeasurementMarker,
    SwingRangePreview,
    ValueFunctionCandidate,
    ValueFunctionPreview,
    ValueSample,
    WeightPreview,
)
from mcda_studio.domain.project import Project
from mcda_studio.domain.scales import AnchorMode
from mcda_studio.domain.validation import validate_leaf_model
from mcda_studio.methods.base import get_method
from mcda_studio.methods.mavt.value_functions import build_evaluator
from mcda_studio.methods.mavt.weighting import (
    WEIGHT_BASIS,
    compute_weights,
    path_shares,
)


def _issue(code: str, message: str, path: str = "", *, warning: bool = False) -> Issue:
    return Issue(
        severity=Severity.WARNING if warning else Severity.ERROR,
        code=code,
        message=message,
        path=path,
    )


def _configuration(
    project: Project, configuration: AnalysisConfiguration | None, *, resolve_weights: bool = True
) -> AnalysisConfiguration:
    cfg = (configuration or project.analysis).model_copy(deep=True)
    get_method(cfg.method)  # unknown -> UnknownReferenceError; capabilities are checked by callers
    for kind, ids in (
        ("profile", [p.id for p in project.weight_profiles]),
        ("scenario", [s.id for s in project.scenarios]),
    ):
        if (resolve_weights or kind == "scenario" and cfg.scenario_id is not None) and len(
            set(ids)
        ) != len(ids):
            raise ModelStructureError(
                f"duplicate {kind} ids prevent unambiguous preview resolution"
            )
    project.resolve_scenario(cfg)
    if resolve_weights:
        project.resolve_profile(cfg)
    return cfg


def _range_notes(project: Project, cfg: AnalysisConfiguration) -> list[Issue]:
    scenario = project.resolve_scenario(cfg)
    notes = []
    for node in project.criteria:
        vf = (
            scenario.value_function_overrides.get(node.id, node.value_function)
            if scenario
            else node.value_function
        )
        if (
            isinstance(vf, LinearValueFunction)
            and node.scale
            and node.scale.anchor_mode is AnchorMode.LOCAL
        ):
            notes.append(
                _issue(
                    "SWING_RANGE_REVIEW",
                    "Local anchors depend on the alternative set. If alternatives or measurements "
                    "change, review swing judgements over the resulting worst-to-best range.",
                    f"criteria[{node.id}]",
                    warning=True,
                )
            )
    return notes


def preview_weights(
    project: Project, configuration: AnalysisConfiguration | None = None
) -> WeightPreview:
    cfg = _configuration(project, configuration)
    tree = project.tree()
    profile = project.resolve_profile(cfg)
    result = WeightPreview(
        project_fingerprint=project.fingerprint(),
        configuration=cfg,
        weight_profile_id=profile.id if profile else None,
        scenario_id=cfg.scenario_id,
        weights_ready=False,
        weight_basis=WEIGHT_BASIS,
        diagnostics=_range_notes(project, cfg),
        swing_ranges=_swing_ranges(project, cfg),
    )
    if not tree.all_ids():
        result.diagnostics.append(_issue("NO_CRITERIA", "the project has no criteria"))
    if profile is None:
        result.diagnostics.append(_issue("NO_WEIGHT_PROFILE", "the project has no weight profile"))
        return result
    if profile.method != "swing":
        result.diagnostics.append(
            _issue(
                "UNSUPPORTED_WEIGHT_METHOD",
                "only swing weighting is supported",
                f"weight_profiles[{profile.id}]",
            )
        )
    try:
        result.diagnostics.extend(
            check_judgements(tree, profile.judgements, f"weight_profiles[{profile.id}]")
        )
        for parent in [None, *[n for n in tree.all_ids() if not tree.is_leaf(n)]]:
            kids = tree.child_ids(parent)
            if kids:
                ratings = [profile.judgements.get(k) for k in kids]
                # A missing only-child rating is not invented as a judgment or a group total.
                result.sibling_rating_totals["<root>" if parent is None else parent] = (
                    math.fsum(float(r) for r in ratings if r is not None)
                    if all(r is not None for r in ratings)
                    else None
                )
        if not any(i.severity is Severity.ERROR for i in result.diagnostics):
            weights = compute_weights(tree, profile.judgements)
            result.local_weights = weights.local
            result.global_weights = weights.global_
            result.path_shares = path_shares(tree, weights.local)
            result.weights_ready = True
    except (OverflowError, WeightError) as exc:
        result.diagnostics.append(_issue("INVALID_WEIGHTS", str(exc)))
    return result


def preview_value_function(
    project: Project,
    criterion_id: str,
    configuration: AnalysisConfiguration | None = None,
    candidate: ValueFunctionCandidate | None = None,
    sample_count: int = 101,
) -> ValueFunctionPreview:
    if not 2 <= sample_count <= 501:
        raise ValueError("sample_count must be between 2 and 501")
    cfg = _configuration(project, configuration, resolve_weights=False)
    tree = project.tree()
    node = tree.node(criterion_id).model_copy(deep=True)
    scenario = project.resolve_scenario(cfg)
    # Weight preferences do not participate in criterion-value evaluation.
    profile = None
    profile_issue = None
    try:
        if len({p.id for p in project.weight_profiles}) != len(project.weight_profiles):
            raise UnknownReferenceError("weight-profile references are ambiguous")
        profile = project.resolve_profile(cfg)
    except UnknownReferenceError as exc:
        profile_issue = _issue(
            "PREVIEW_PROFILE_UNRESOLVED", str(exc), "configuration", warning=True
        )
    if scenario:
        override = scenario.value_function_overrides.get(criterion_id)
        if override is not None:
            node.value_function = override.model_copy(deep=True)
    if candidate is not None:
        for name in candidate.model_fields_set:
            if name == "scale":
                node.scale = candidate.scale.model_copy(deep=True) if candidate.scale else None
            elif name == "value_function":
                node.value_function = (
                    candidate.value_function.model_copy(deep=True)
                    if candidate.value_function
                    else None
                )
    vf, scale = node.value_function, node.scale
    payload = {
        "criterion_id": criterion_id,
        "scale": scale.model_dump(mode="json") if scale else None,
        "value_function": vf.model_dump(mode="json") if vf else None,
    }
    result = ValueFunctionPreview(
        project_fingerprint=project.fingerprint(),
        configuration=cfg,
        criterion_id=criterion_id,
        weight_profile_id=profile.id if profile else None,
        scenario_id=cfg.scenario_id,
        candidate=candidate.model_copy(deep=True) if candidate else None,
        candidate_fingerprint=hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        effective_scale=scale,
        effective_value_function=vf,
        resolved_domain=None,
        curve_ready=False,
        measurements_complete=False,
    )
    if profile_issue is not None:
        result.diagnostics.append(profile_issue)
    if not tree.is_leaf(criterion_id):
        result.diagnostics.append(
            _issue(
                "MEASUREMENT_ON_NON_LEAF",
                "only a leaf has a value function",
                f"criteria[{criterion_id}]",
            )
        )
        result.readiness = "invalid"
        result.measurement_readiness = "invalid"
        return result
    alt_ids = project.alternative_ids()
    selected = [p for p in project.performances if p.criterion_id == criterion_id]
    integrity = []
    for alt, count in Counter(alt_ids).items():
        if count > 1:
            integrity.append(_issue("DUPLICATE_ALTERNATIVE_ID", f"duplicate alternative {alt!r}"))
    for alt, count in Counter(p.alternative_id for p in selected).items():
        path = f"performances[{alt},{criterion_id}]"
        if count > 1:
            integrity.append(
                _issue("DUPLICATE_MEASUREMENT", "measurement given more than once", path)
            )
        if alt not in alt_ids:
            integrity.append(_issue("UNKNOWN_ALTERNATIVE", f"unknown alternative {alt!r}", path))
    perf = project.performance_index()
    definition = validate_leaf_model(node, vf, [], {})
    measured = validate_leaf_model(node, vf, alt_ids, perf)
    # Structured issue identity, never filtering full-project messages to guess relevant errors.
    for issue in [*definition.issues, *measured.issues, *integrity]:
        if issue not in result.diagnostics:
            result.diagnostics.append(issue)
    complete = bool(alt_ids) and measured.ok and not integrity
    result.measurements_complete = complete
    local = (
        isinstance(vf, LinearValueFunction)
        and scale is not None
        and scale.anchor_mode is AnchorMode.LOCAL
    )
    if local:
        result.diagnostics.append(
            _issue(
                "SWING_RANGE_REVIEW",
                "Changing alternatives or measurements may change local anchors; "
                "review swing judgements over the new range.",
                f"criteria[{criterion_id}]",
                warning=True,
            )
        )
        if not alt_ids:
            result.diagnostics.append(
                _issue(
                    "NO_ALTERNATIVES",
                    "local anchors require measurements from the complete alternative set",
                )
            )
    can_resolve = definition.ok and (not local or complete)
    if can_resolve and scale is not None and vf is not None:
        observed = [float(perf[(a, criterion_id)]) for a in alt_ids] if local else []
        result.resolved_domain = effective_domain(scale, vf, observed)
        if scale.is_numeric and result.resolved_domain is None:
            can_resolve = False
        if can_resolve:
            domain = result.resolved_domain
            evaluator = build_evaluator(vf, domain)
            if domain is None:  # qualitative: labels have no interpolated numeric spacing
                result.samples = [
                    ValueSample(measurement=label, partial_value=evaluator(label)[0])
                    for label in scale.labels
                ]
            else:
                span = domain.upper - domain.lower
                xs = {domain.lower, domain.upper}
                if isinstance(vf, PiecewiseLinearValueFunction):
                    xs.update(p.x for p in vf.points)
                if not math.isfinite(span) or len(xs) > sample_count:
                    result.diagnostics.append(
                        _issue(
                            "PREVIEW_SAMPLE_LIMIT",
                            "finite domain and a sampling budget covering all control points "
                            "are required",
                        )
                    )
                    can_resolve = False
                else:
                    remaining = sample_count - len(xs)
                    xs.update(
                        domain.lower + span * (i / (remaining + 1)) for i in range(1, remaining + 1)
                    )
                    result.samples = [
                        ValueSample(measurement=x, partial_value=evaluator(x)[0])
                        for x in sorted(xs)
                    ]
            result.curve_ready = can_resolve
            if can_resolve:
                for alternative in project.alternatives:
                    raw = perf.get((alternative.id, criterion_id))
                    path = f"performances[{alternative.id},{criterion_id}]"
                    invalid = any(
                        i.severity is Severity.ERROR and (not i.path or i.path == path)
                        for i in [*measured.issues, *integrity]
                    )
                    value, clamped = (
                        evaluator(raw) if raw is not None and not invalid else (None, False)
                    )
                    result.markers.append(
                        MeasurementMarker(
                            alternative_id=alternative.id,
                            raw_measurement=raw,
                            partial_value=value,
                            clamped=clamped,
                        )
                    )
    if not result.markers:
        result.markers = [
            MeasurementMarker(
                alternative_id=a.id,
                raw_measurement=perf.get((a.id, criterion_id)),
                partial_value=None,
            )
            for a in project.alternatives
        ]
    incomplete_codes = {
        "MISSING_SCALE",
        "MISSING_VALUE_FUNCTION",
        "MISSING_ANCHORS",
        "MISSING_MEASUREMENT",
        "NO_ALTERNATIVES",
        "TOO_FEW_CONTROL_POINTS",
        "TOO_FEW_LABELS",
    }

    def state(issues: list[Issue]) -> Literal["incomplete", "invalid"]:
        errors = [i for i in issues if i.severity is Severity.ERROR]
        return "invalid" if any(i.code not in incomplete_codes for i in errors) else "incomplete"

    required = [*definition.issues, *measured.issues, *integrity] if local else definition.issues
    result.readiness = (
        "ready"
        if result.curve_ready
        else state(
            [*required, *[i for i in result.diagnostics if i.code == "PREVIEW_SAMPLE_LIMIT"]]
        )
    )
    result.measurement_readiness = "ready" if complete else state([*measured.issues, *integrity])
    return result


def _swing_ranges(project: Project, cfg: AnalysisConfiguration) -> dict[str, SwingRangePreview]:
    """Reuse scoped value previews; unresolved ranges never invalidate weight arithmetic."""
    ranges: dict[str, SwingRangePreview] = {}
    tree = project.tree()
    scenario = project.resolve_scenario(cfg)
    for leaf in tree.leaves():
        vf = tree.node(leaf).value_function
        if scenario:
            vf = scenario.value_function_overrides.get(leaf, vf)
        budget = (
            min(501, max(2, len(vf.points))) if isinstance(vf, PiecewiseLinearValueFunction) else 2
        )
        preview = preview_value_function(project, leaf, cfg, sample_count=budget)
        scale = preview.effective_scale
        samples = preview.samples
        # Numeric endpoints define the full comparison swing, including decreasing functions.
        endpoints = [samples[0], samples[-1]] if preview.resolved_domain and samples else samples
        ranges[leaf] = SwingRangePreview(
            readiness=preview.readiness,
            scale_type=scale.type if scale else None,
            unit=scale.unit if scale else None,
            domain=preview.resolved_domain,
            worst=[s.measurement for s in endpoints if s.partial_value == 0],
            best=[s.measurement for s in endpoints if s.partial_value == 1],
            diagnostics=preview.diagnostics,
        )
    return ranges
