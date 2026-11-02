"""Pre-B2 readiness matrix: only actual criterion dependencies may block a curve."""

import pytest

from mcda_studio.domain.criteria import (
    ControlPoint,
    LinearValueFunction,
    PiecewiseLinearValueFunction,
)
from mcda_studio.domain.preferences import AnalysisConfiguration, Scenario
from mcda_studio.domain.previews import ValueFunctionCandidate
from mcda_studio.domain.scales import AnchorMode, Scale, ScaleType
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps

from builders import tiny_project


@pytest.mark.parametrize("local", [False, True])
@pytest.mark.parametrize(
    "condition,measurement_state",
    [
        ("complete", "ready"),
        ("missing", "incomplete"),
        ("wrong_type", "invalid"),
        ("out_of_domain", "invalid"),
        ("duplicate", "invalid"),
        ("none", "incomplete"),
    ],
)
def test_measurement_readiness_matrix(local, condition, measurement_state):
    p = tiny_project()
    if local:
        p = ps.set_scale(p, "cost", Scale(type=ScaleType.RATIO, anchor_mode=AnchorMode.LOCAL))
    if condition == "missing":
        p = ps.clear_performance(p, "a", "cost")
    if condition == "wrong_type":
        p = ps.set_performance(p, "a", "cost", "bad")
    if condition == "out_of_domain":
        p = ps.set_performance(p, "a", "cost", -5)
    if condition == "duplicate":
        p.performances.append(p.performances[0].model_copy())
    if condition == "none":
        p.alternatives = []
        p.performances = []
    before = p.model_dump_json(), p.fingerprint()
    r = svc.preview_value_function(p, "cost")
    assert r.measurement_readiness == measurement_state
    expected = measurement_state if local else "ready"
    assert r.readiness == expected and r.curve_ready == (expected == "ready")
    if local and expected != "ready":
        assert r.resolved_domain is None and r.samples == []
        assert all(m.partial_value is None for m in r.markers)
    assert (p.model_dump_json(), p.fingerprint()) == before


@pytest.mark.parametrize(
    "candidate,expected",
    [
        (ValueFunctionCandidate(scale=None), "incomplete"),
        (ValueFunctionCandidate(value_function=None), "incomplete"),
        (ValueFunctionCandidate(scale=Scale(type=ScaleType.RATIO)), "incomplete"),
        (ValueFunctionCandidate(scale=Scale(type=ScaleType.RATIO, lower=10, upper=0)), "invalid"),
        (
            ValueFunctionCandidate(value_function=PiecewiseLinearValueFunction(points=[])),
            "incomplete",
        ),
        (
            ValueFunctionCandidate(
                value_function=PiecewiseLinearValueFunction(
                    points=[ControlPoint(x=0, value=0), ControlPoint(x=0, value=1)]
                )
            ),
            "invalid",
        ),
    ],
)
def test_definition_readiness_matrix(candidate, expected):
    r = svc.preview_value_function(tiny_project(), "cost", candidate=candidate)
    assert r.readiness == expected and not r.curve_ready


@pytest.mark.parametrize("weights", ["absent", "invalid", "unknown", "duplicate"])
def test_unrelated_weight_problems_do_not_block_the_selected_function(weights):
    p = ps.clear_performance(tiny_project(), "a", "quality")
    cfg = AnalysisConfiguration()
    if weights == "absent":
        p.weight_profiles = []
    if weights == "invalid":
        p.weight_profiles[0].judgements = {}
    if weights == "unknown":
        cfg.weight_profile_id = "missing"
    if weights == "duplicate":
        p.weight_profiles.append(p.weight_profiles[0].model_copy(deep=True))
    r = svc.preview_value_function(p, "cost", cfg)
    assert r.readiness == "ready" and r.measurement_readiness == "ready"
    assert [m.partial_value for m in r.markers] == pytest.approx([0.8, 0.4])


def test_selected_scenario_function_does_not_need_its_unresolved_weight_profile():
    p = ps.add_scenario(
        tiny_project(),
        Scenario(
            id="s",
            name="S",
            weight_profile_id="missing",
            value_function_overrides={"cost": LinearValueFunction()},
        ),
    )
    r = svc.preview_value_function(p, "cost", AnalysisConfiguration(scenario_id="s"))
    assert r.readiness == "ready" and r.weight_profile_id is None
    assert [m.partial_value for m in r.markers] == pytest.approx([0.2, 0.6])


def test_api_exposes_both_readiness_axes_and_never_fills_local_gaps():
    # Service evidence is serialised through the same response model used by HTTP.
    p = ps.clear_performance(tiny_project(), "a", "cost")
    fixed = svc.preview_value_function(p, "cost").model_dump(mode="json")
    assert fixed["readiness"] == "ready" and fixed["measurement_readiness"] == "incomplete"
    p = ps.set_scale(p, "cost", Scale(type=ScaleType.RATIO, anchor_mode=AnchorMode.LOCAL))
    local = svc.preview_value_function(p, "cost").model_dump(mode="json")
    assert local["readiness"] == "incomplete" and local["resolved_domain"] is None


@pytest.mark.parametrize(
    "case,expected",
    [
        ("qualitative", "ready"),
        ("labels_missing", "incomplete"),
        ("mapping_missing", "invalid"),
        ("ordinal_reversed", "invalid"),
        ("direct", "ready"),
        ("direct_reversed", "invalid"),
    ],
)
def test_labelled_and_direct_readiness_matrix(case, expected):
    from mcda_studio.domain.criteria import DirectRatingValueFunction, QualitativeValueFunction

    p = tiny_project()
    p.performances = []
    p.weight_profiles = []
    if case.startswith("direct"):
        candidate = ValueFunctionCandidate(
            scale=Scale(type=ScaleType.INTERVAL),
            value_function=DirectRatingValueFunction(
                min_rating=10 if case == "direct_reversed" else 0, max_rating=10
            ),
        )
    else:
        labels = [] if case == "labels_missing" else ["low", "high"]
        mapping = (
            {}
            if case == "labels_missing"
            else {"low": 0}
            if case == "mapping_missing"
            else {"low": 1, "high": 0}
            if case == "ordinal_reversed"
            else {"low": 0, "high": 1}
        )
        candidate = ValueFunctionCandidate(
            scale=Scale(type=ScaleType.ORDINAL, labels=labels),
            value_function=QualitativeValueFunction(mapping=mapping),
        )
    result = svc.preview_value_function(p, "quality", candidate=candidate)
    assert result.readiness == expected
    assert result.curve_ready == (expected == "ready")
