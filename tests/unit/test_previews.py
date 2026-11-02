"""Independent preview oracles and incomplete-model/non-mutation acceptance."""

import math
from pathlib import Path

import pytest

from mcda_studio.domain.criteria import (
    ControlPoint,
    Direction,
    DirectRatingValueFunction,
    LinearValueFunction,
    PiecewiseLinearValueFunction,
    QualitativeValueFunction,
)
from mcda_studio.domain.errors import ModelStructureError, UnknownReferenceError
from mcda_studio.domain.preferences import AnalysisConfiguration, Scenario, WeightProfile
from mcda_studio.domain.previews import ValueFunctionCandidate
from mcda_studio.domain.scales import AnchorMode, Scale, ScaleType
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository

from builders import tiny_project


def codes(result):
    return {i.code for i in result.diagnostics}


def local_project():
    p = tiny_project()
    return ps.set_scale(p, "cost", Scale(type=ScaleType.RATIO, anchor_mode=AnchorMode.LOCAL))


@pytest.mark.parametrize("direction", list(Direction))
def test_linear_samples_follow_an_independent_formula(direction):
    p = ps.set_value_function(tiny_project(), "cost", LinearValueFunction(direction=direction))
    result = svc.preview_value_function(p, "cost", sample_count=17)
    assert result.curve_ready and result.measurements_complete
    assert len(result.samples) == 17
    for sample in result.samples:
        expected = sample.measurement / 100
        if direction is Direction.DECREASING:
            expected = 1 - expected
        assert sample.partial_value == pytest.approx(expected, abs=1e-15)
    assert [m.partial_value for m in result.markers] == pytest.approx(
        [0.2, 0.6] if direction is Direction.INCREASING else [0.8, 0.4]
    )


@pytest.mark.parametrize("values", [[0, 0.25, 0.25, 1], [1, 0.75, 0.75, 0]])
def test_piecewise_includes_knots_plateaus_and_matches_an_independent_oracle(values):
    p = tiny_project()
    xs = [0, 10, 65, 100]
    vf = PiecewiseLinearValueFunction(
        points=[ControlPoint(x=x, value=v) for x, v in zip(xs, values, strict=True)]
    )
    preview = svc.preview_value_function(
        p, "cost", candidate=ValueFunctionCandidate(value_function=vf), sample_count=29
    )
    assert preview.curve_ready
    assert len(preview.samples) <= 29
    assert set(xs) <= {s.measurement for s in preview.samples}
    for point in preview.samples:
        x = point.measurement
        i = next(i for i in range(3) if xs[i] <= x <= xs[i + 1])
        expected = values[i] + (values[i + 1] - values[i]) * (x - xs[i]) / (xs[i + 1] - xs[i])
        assert point.partial_value == pytest.approx(expected)
    assert preview.resolved_domain.source == "control_points"


def test_fixed_curve_before_weights_unrelated_criteria_or_measurements_are_complete():
    p = ps.add_criterion(tiny_project(), "Unfinished", crit_id="unfinished")
    p.performances = []
    p.weight_profiles = []
    before = p.model_dump_json(), p.fingerprint()
    result = svc.preview_value_function(p, "cost")
    assert result.curve_ready and not result.measurements_complete
    assert len(result.samples) == 101
    assert [m.raw_measurement for m in result.markers] == [None, None]
    assert all(m.partial_value is None for m in result.markers)
    assert result.weight_profile_id is None
    assert codes(result) == {"MISSING_MEASUREMENT"}
    assert (p.model_dump_json(), p.fingerprint()) == before


def test_fixed_curve_without_alternatives_is_valid_but_measurements_are_incomplete():
    p = tiny_project()
    p.alternatives = []
    p.performances = []
    result = svc.preview_value_function(p, "cost")
    assert result.curve_ready and not result.measurements_complete and not result.markers


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda p: ps.clear_performance(p, "a", "cost"), "MISSING_MEASUREMENT"),
        (lambda p: ps.set_performance(p, "a", "cost", "wrong"), "INVALID_MEASUREMENT_TYPE"),
        (lambda p: ps.set_performance(p, "a", "cost", -1), "NEGATIVE_RATIO_VALUE"),
        (lambda p: ps.set_performance(p, "a", "cost", 60), "DEGENERATE_LOCAL_ANCHORS"),
    ],
)
def test_local_anchors_refuse_incomplete_invalid_or_degenerate_measurement_sets(mutate, code):
    result = svc.preview_value_function(mutate(local_project()), "cost")
    assert not result.curve_ready and not result.measurements_complete
    assert result.resolved_domain is None and not result.samples
    assert all(m.partial_value is None for m in result.markers)
    assert {code, "LOCAL_ANCHORS", "SWING_RANGE_REVIEW"} <= codes(result)


def test_no_alternatives_do_not_invent_a_local_domain():
    p = local_project()
    p.alternatives = []
    p.performances = []
    result = svc.preview_value_function(p, "cost")
    assert not result.curve_ready and result.resolved_domain is None
    assert "NO_ALTERNATIVES" in codes(result)


def test_alternative_changes_recompute_local_domains_and_existing_partial_values():
    p = local_project()
    before = svc.preview_value_function(p, "cost")
    assert [m.partial_value for m in before.markers] == [1, 0]
    added = ps.add_alternative(p, "C", alt_id="c")
    missing = svc.preview_value_function(added, "cost")
    assert not missing.curve_ready and missing.project_fingerprint != before.project_fingerprint
    added = ps.set_performance(added, "c", "cost", 100)
    after = svc.preview_value_function(added, "cost")
    assert after.resolved_domain.upper == 100
    assert after.markers[1].partial_value == pytest.approx((100 - 60) / (100 - 20))
    removed = svc.preview_value_function(ps.remove_alternative(added, "a"), "cost")
    assert removed.resolved_domain.lower == 60
    assert removed.markers[0].partial_value == 1
    assert {"LOCAL_ANCHORS", "SWING_RANGE_REVIEW"} <= codes(after)
    assert p.performance_index()[("a", "cost")] == 20


@pytest.mark.parametrize("policy", ["error", "clamp"])
def test_out_of_domain_markers_follow_policy_while_the_fixed_curve_remains_inspectable(policy):
    p = ps.set_performance(tiny_project(), "a", "cost", 120)
    p = ps.set_value_function(
        p, "cost", LinearValueFunction(direction=Direction.DECREASING, out_of_domain=policy)
    )
    result = svc.preview_value_function(p, "cost")
    assert result.curve_ready
    marker = result.markers[0]
    assert marker.raw_measurement == 120
    if policy == "error":
        assert marker.partial_value is None and not marker.clamped
        assert not result.measurements_complete and "OUT_OF_DOMAIN" in codes(result)
    else:
        assert marker.partial_value == 0 and marker.clamped and result.measurements_complete
        assert "CLAMPED_MEASUREMENT" in codes(result)


@pytest.mark.parametrize(
    "scale_type,labels,values",
    [
        (ScaleType.ORDINAL, ["low", "mid", "high"], [0, 0.1, 1]),
        (ScaleType.CATEGORICAL, ["red", "blue", "green"], [1, 0, 0.4]),
    ],
)
def test_labelled_preview_keeps_explicit_judgements_without_invented_spacing(
    scale_type, labels, values
):
    p = tiny_project()
    p.performances = []
    candidate = ValueFunctionCandidate(
        scale=Scale(type=scale_type, labels=labels),
        value_function=QualitativeValueFunction(mapping=dict(zip(labels, values, strict=True))),
    )
    result = svc.preview_value_function(p, "quality", candidate=candidate)
    assert result.curve_ready and result.resolved_domain is None
    assert [s.measurement for s in result.samples] == labels
    assert [s.partial_value for s in result.samples] == values
    assert not result.measurements_complete


def test_direct_rating_uses_its_rating_range_not_scale_bounds():
    result = svc.preview_value_function(
        tiny_project(),
        "quality",
        candidate=ValueFunctionCandidate(
            value_function=DirectRatingValueFunction(min_rating=2, max_rating=10)
        ),
        sample_count=9,
    )
    assert result.curve_ready and result.resolved_domain.source == "rating_range"
    for s in result.samples:
        assert s.partial_value == pytest.approx((s.measurement - 2) / 8)


@pytest.mark.parametrize(
    "candidate,code",
    [
        (ValueFunctionCandidate(value_function=None), "MISSING_VALUE_FUNCTION"),
        (ValueFunctionCandidate(scale=None), "MISSING_SCALE"),
        (
            ValueFunctionCandidate(value_function=DirectRatingValueFunction()),
            "INCOMPATIBLE_VALUE_FUNCTION",
        ),
        (
            ValueFunctionCandidate(
                value_function=PiecewiseLinearValueFunction(
                    points=[ControlPoint(x=1, value=0), ControlPoint(x=1, value=1)]
                )
            ),
            "CONTROL_POINTS_NOT_ORDERED",
        ),
        (
            ValueFunctionCandidate(
                value_function=PiecewiseLinearValueFunction(
                    points=[ControlPoint(x=0, value=0.1), ControlPoint(x=100, value=1)]
                )
            ),
            "ENDPOINT_CONVENTION",
        ),
        (
            ValueFunctionCandidate(
                value_function=PiecewiseLinearValueFunction(
                    points=[
                        ControlPoint(x=0, value=0),
                        ControlPoint(x=10, value=1),
                        ControlPoint(x=100, value=0.5),
                    ]
                )
            ),
            "NON_MONOTONE_VALUE_FUNCTION",
        ),
    ],
)
def test_candidate_validation_uses_the_same_leaf_rules_as_full_evaluation(candidate, code):
    p = tiny_project()
    before = p.model_dump_json()
    result = svc.preview_value_function(p, "cost", candidate=candidate)
    assert not result.curve_ready and not result.samples and code in codes(result)
    assert p.model_dump_json() == before


def test_candidate_and_scenario_outputs_are_deeply_isolated():
    p = ps.add_scenario(
        tiny_project(),
        Scenario(
            id="changed", name="Changed", value_function_overrides={"cost": LinearValueFunction()}
        ),
    )
    cfg = AnalysisConfiguration(scenario_id="changed")
    original = p.model_dump_json(), p.fingerprint()
    scenario = svc.preview_value_function(p, "cost", cfg)
    assert scenario.samples[0].partial_value == 0
    scenario.effective_value_function.direction = Direction.DECREASING
    candidate = ValueFunctionCandidate(scale=Scale(type=ScaleType.RATIO, lower=0, upper=200))
    changed = svc.preview_value_function(p, "cost", cfg, candidate)
    assert changed.candidate_fingerprint != scenario.candidate_fingerprint
    assert changed.project_fingerprint == original[1]
    changed.candidate.scale.upper = 999
    changed.effective_scale.upper = 999
    changed.configuration.parameters["new"] = True
    assert candidate.scale.upper == 200 and cfg.parameters == {}
    assert (p.model_dump_json(), p.fingerprint()) == original


def test_preview_does_not_hide_duplicate_or_unknown_measurements():
    p = tiny_project()
    p.performances.append(p.performances[0].model_copy())
    result = svc.preview_value_function(p, "cost")
    assert result.curve_ready and not result.measurements_complete
    assert "DUPLICATE_MEASUREMENT" in codes(result)
    assert result.markers[0].partial_value is None
    p.performances[-1].alternative_id = "unknown"
    assert "UNKNOWN_ALTERNATIVE" in codes(svc.preview_value_function(p, "cost"))


def test_large_offset_small_span_keeps_engine_tolerance_and_local_warning():
    p = tiny_project()
    p = ps.set_scale(p, "quality", Scale(type=ScaleType.INTERVAL, lower=1e9, upper=1e9 + 1))
    p = ps.set_performance(p, "a", "quality", 1e9 + 0.25)
    p = ps.set_performance(p, "b", "quality", 1e9 + 0.75)
    result = svc.preview_value_function(p, "quality")
    assert [m.partial_value for m in result.markers] == [0.25, 0.75]
    p = ps.set_performance(p, "a", "quality", 1e9 - 1e-5)
    assert "OUT_OF_DOMAIN" in codes(svc.preview_value_function(p, "quality"))
    p = ps.set_scale(p, "quality", Scale(type=ScaleType.INTERVAL, anchor_mode=AnchorMode.LOCAL))
    assert "NEAR_DEGENERATE_LOCAL_ANCHORS" in codes(svc.preview_value_function(p, "quality"))


def test_control_point_sample_budget_is_bounded_without_discarding_knots():
    vf = PiecewiseLinearValueFunction(points=[ControlPoint(x=x, value=x / 10) for x in range(11)])
    result = svc.preview_value_function(
        tiny_project(), "cost", candidate=ValueFunctionCandidate(value_function=vf), sample_count=2
    )
    assert not result.curve_ready and not result.samples and "PREVIEW_SAMPLE_LIMIT" in codes(result)
    for count in [1, 502]:
        with pytest.raises(ValueError):
            svc.preview_value_function(tiny_project(), "cost", sample_count=count)


def test_weights_do_not_require_any_measurements_or_leaf_models():
    p = tiny_project()
    p.performances = []
    p.alternatives = []
    for node in p.criteria:
        node.scale = None
        node.value_function = None
    before = p.model_dump_json(), p.fingerprint()
    result = svc.preview_weights(p)
    assert result.weights_ready
    assert result.local_weights == {"cost": 100 / 150, "quality": 50 / 150}
    assert result.global_weights == result.local_weights
    assert result.sibling_rating_totals == {"<root>": 150}
    assert (p.model_dump_json(), p.fingerprint()) == before


@pytest.mark.parametrize(
    "judgements,code",
    [
        ({"cost": 100}, "MISSING_JUDGEMENT"),
        ({"cost": -1, "quality": 1}, "INVALID_JUDGEMENT"),
        ({"cost": 0, "quality": 0}, "ZERO_SUM_JUDGEMENTS"),
        ({"cost": 1, "quality": 1, "ghost": 1}, "UNKNOWN_JUDGEMENT_NODE"),
    ],
)
def test_invalid_weights_never_emit_a_partially_normalised_set(judgements, code):
    p = tiny_project()
    p.weight_profiles[0].judgements = judgements
    result = svc.preview_weights(p)
    assert not result.weights_ready and not result.local_weights and not result.global_weights
    assert code in codes(result)


def test_only_child_has_unit_weight_without_a_fabricated_rating():
    p = ps.remove_criterion(tiny_project(), "quality")
    p.weight_profiles[0].judgements = {}
    result = svc.preview_weights(p)
    assert result.weights_ready and result.global_weights == {"cost": 1}
    assert result.sibling_rating_totals["<root>"] is None
    assert p.weight_profiles[0].judgements == {}


def test_profiles_scenarios_and_tree_weights_match_an_independent_product():
    p = tiny_project()
    p = ps.add_criterion(p, "Group", crit_id="group")
    p = ps.add_criterion(p, "Inner 1", parent_id="group", crit_id="i1")
    p = ps.add_criterion(p, "Inner 2", parent_id="group", crit_id="i2")
    p.weight_profiles[0].judgements = {"cost": 50, "quality": 30, "group": 20, "i1": 1, "i2": 3}
    p = ps.add_weight_profile(
        p,
        WeightProfile(
            id="other",
            name="Other",
            judgements={"cost": 1, "quality": 1, "group": 2, "i1": 1, "i2": 1},
        ),
    )
    p = ps.add_scenario(p, Scenario(id="s", name="S", weight_profile_id="other"))
    base = svc.preview_weights(p)
    assert base.global_weights == pytest.approx(
        {"cost": 0.5, "quality": 0.3, "i1": 0.2 * 0.25, "i2": 0.2 * 0.75}
    )
    assert math.fsum(base.global_weights.values()) == pytest.approx(1)
    automatic = svc.preview_weights(p, AnalysisConfiguration(scenario_id="s"))
    assert automatic.weight_profile_id == "other" and automatic.global_weights["i1"] == 0.25
    explicit = svc.preview_weights(
        p, AnalysisConfiguration(scenario_id="s", weight_profile_id="default")
    )
    assert explicit.global_weights == base.global_weights
    assert explicit.project_fingerprint == base.project_fingerprint


def test_missing_profile_empty_tree_and_unknown_references_are_explicit():
    p = tiny_project()
    p.weight_profiles = []
    assert "NO_WEIGHT_PROFILE" in codes(svc.preview_weights(p))
    assert svc.preview_value_function(p, "cost").curve_ready
    assert "NO_CRITERIA" in codes(svc.preview_weights(ps.new_project("Blank")))
    for cfg in [
        AnalysisConfiguration(scenario_id="missing"),
        AnalysisConfiguration(weight_profile_id="missing"),
        AnalysisConfiguration(method="electre"),
    ]:
        with pytest.raises(UnknownReferenceError):
            svc.preview_weights(p, cfg)
    with pytest.raises(UnknownReferenceError):
        svc.preview_value_function(p, "missing")
    p = ps.add_criterion(p, "Child", parent_id="cost", crit_id="child", discard_leaf_data=True)
    assert "MEASUREMENT_ON_NON_LEAF" in codes(svc.preview_value_function(p, "cost"))
    p.criteria[-1].parent_id = "child"
    with pytest.raises(ModelStructureError):
        svc.preview_weights(p)


def test_vc_preview_values_and_weights_equal_the_unchanged_full_evaluation():
    p = JsonProjectRepository().load(
        Path(__file__).parents[2] / "examples/nz_deeptech_vc/project.json"
    )
    for cfg in [AnalysisConfiguration(), AnalysisConfiguration(scenario_id="linear_market_size")]:
        full = svc.evaluate_project(p, cfg)
        weights = svc.preview_weights(p, cfg)
        assert (
            weights.local_weights == full.local_weights
            and weights.global_weights == full.global_weights
        )
        for leaf in full.leaf_order:
            preview = svc.preview_value_function(p, leaf, cfg)
            assert preview.curve_ready and preview.measurements_complete
            for marker in preview.markers:
                detail = next(
                    a for a in full.alternatives if a.alternative_id == marker.alternative_id
                )
                assert marker.partial_value == detail.partial_values[leaf]


def test_finite_large_domain_sampling_avoids_intermediate_overflow():
    p = tiny_project()
    p.performances = []
    result = svc.preview_value_function(
        p,
        "cost",
        candidate=ValueFunctionCandidate(scale=Scale(type=ScaleType.RATIO, lower=0, upper=1e308)),
        sample_count=101,
    )
    assert result.curve_ready and len(result.samples) == 101
    assert all(math.isfinite(s.measurement) and 0 <= s.partial_value <= 1 for s in result.samples)


def test_overflowing_rating_total_is_explicit_and_emits_no_weights():
    p = tiny_project()
    p.weight_profiles[0].judgements = {"cost": 1e308, "quality": 1e308}
    result = svc.preview_weights(p)
    assert not result.weights_ready and result.global_weights == {}
    assert "INVALID_WEIGHTS" in codes(result)
