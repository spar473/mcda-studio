"""Independent endpoint and control-point checks for one-measurement range screening."""

import math
from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from mcda_studio.domain.criteria import ControlPoint, PiecewiseLinearValueFunction
from mcda_studio.domain.errors import SensitivityError, ValidationFailed
from mcda_studio.domain.preferences import AnalysisConfiguration, Scenario
from mcda_studio.domain.scales import AnchorMode
from mcda_studio.methods.mavt.aggregation import evaluate_mavt
from mcda_studio.methods.mavt.measurement_range import assess_measurement_range

from builders import scored_project, tiny_project, with_classes


def test_decreasing_cost_can_change_rank_but_does_not_edit_project():
    p = tiny_project()
    before = p.model_dump_json()
    result = assess_measurement_range(p, p.analysis, "a", "cost", 20, 100)
    assert result.baseline_rank == 1 and result.rank_can_change
    assert result.minimum_score_at == 100 and result.maximum_score_at == 20
    assert p.model_dump_json() == before


def test_sorting_boundary_tolerance_is_observed():
    p = with_classes(scored_project({"a": 0.7, "b": 0.2}), [("Upper", 0.7), ("Lower", None)])
    close = assess_measurement_range(p, p.analysis, "a", "score", 0.7 - 0.5e-12, 0.7)
    assert close.baseline_class_id == "upper" and close.class_can_change is False
    crossing = assess_measurement_range(p, p.analysis, "a", "score", 0.7 - 2e-12, 0.7)
    assert crossing.class_can_change is True


def test_nonmonotone_piecewise_value_function_is_rejected():
    p = scored_project({"a": 0.5, "b": 0.8})
    p.criteria[0].value_function = PiecewiseLinearValueFunction(
        points=[
            ControlPoint(x=0, value=0),
            ControlPoint(x=0.5, value=1),
            ControlPoint(x=1, value=0),
        ]
    )
    # Normal validation refuses a non-monotone piecewise function.
    with pytest.raises(ValidationFailed, match="NON_MONOTONE_VALUE_FUNCTION"):
        assess_measurement_range(p, p.analysis, "a", "score", 0, 1)


def test_valid_piecewise_screen_matches_manual_values():
    p = scored_project({"a": 0.5, "b": 0.8})
    p.criteria[0].value_function = PiecewiseLinearValueFunction(
        points=[
            ControlPoint(x=0, value=0),
            ControlPoint(x=0.5, value=0.8),
            ControlPoint(x=1, value=1),
        ]
    )
    result = assess_measurement_range(p, p.analysis, "a", "score", 0, 1)
    # a: 0.8 at baseline, b: 0.92, a: 1.0 at the upper endpoint.
    assert result.baseline_rank == 2 and result.rank_can_change
    assert result.minimum_score_at == 0 and result.maximum_score_at == 1
    contact = result.boundary_contacts[0]
    # Second segment is U(x) = .8 + .4(x-.5); b has U=.92.
    expected = Fraction(0.5) + (Fraction(0.92) - Fraction(1e-12) - Fraction(0.8)) * Fraction(
        0.5
    ) / (1 - Fraction(0.8))
    assert Fraction(contact.exact_lower) == expected
    assert contact.lower == pytest.approx(0.8 - 2.5e-12, abs=2e-16)


def test_rank_tolerance_uses_the_engines_strict_comparison():
    p = scored_project({"a": 0.5, "b": 0.5})
    threshold = 0.5 - 1e-12
    within = assess_measurement_range(p, p.analysis, "a", "score", threshold, 0.5)
    assert within.rank_can_change is False
    beyond = assess_measurement_range(
        p, p.analysis, "a", "score", math.nextafter(threshold, 0), 0.5
    )
    assert beyond.rank_can_change is True


def test_local_anchor_and_range_outside_fixed_domain_are_explicitly_refused():
    p = tiny_project()
    p.criteria[0].scale.anchor_mode = AnchorMode.LOCAL
    with pytest.raises(SensitivityError, match="RANGE_LOCAL_ANCHORS"):
        assess_measurement_range(p, p.analysis, "a", "cost", 20, 60)
    p = tiny_project()
    with pytest.raises(SensitivityError, match="RANGE_OUTSIDE_DOMAIN"):
        assess_measurement_range(p, p.analysis, "a", "cost", 20, 101)
    with pytest.raises(SensitivityError, match="RANGE_EXCLUDES_BASELINE"):
        assess_measurement_range(p, p.analysis, "a", "cost", 21, 60)
    with pytest.raises(SensitivityError, match="RANGE_INVALID"):
        assess_measurement_range(p, p.analysis, "a", "cost", 0, float("inf"))


@given(st.integers(min_value=0, max_value=100), st.integers(min_value=0, max_value=100))
def test_one_criterion_rank_change_matches_independent_order_oracle(a, b):
    baseline, other = a / 100, b / 100
    p = scored_project({"a": baseline, "b": other})
    result = assess_measurement_range(p, p.analysis, "a", "score", 0, 1)

    def rank(x):
        return 1 + int(other > x + 1e-12)

    assert result.rank_can_change == (rank(0) != rank(baseline) or rank(1) != rank(baseline))


@given(st.integers(min_value=0, max_value=20), st.integers(min_value=20, max_value=100))
def test_decreasing_criterion_matches_hand_calculated_two_alternative_oracle(low, high):
    p = tiny_project()
    result = assess_measurement_range(p, p.analysis, "a", "cost", low, high)

    def rank(cost):
        a = (2 / 3) * ((100 - cost) / 100) + (1 / 3) * 0.6
        b = (2 / 3) * 0.4 + (1 / 3) * 0.9
        return 1 + int(b > a + 1e-12)

    assert result.rank_can_change == (rank(low) != rank(20) or rank(high) != rank(20))


def test_contacts_include_closed_class_boundary_and_flat_interval():
    # With U=x the class contact is exactly .7-tol; the higher class includes it.
    p = with_classes(scored_project({"a": 0.7, "b": 0.2}), [("Upper", 0.7), ("Lower", None)])
    result = assess_measurement_range(p, p.analysis, "a", "score", 0, 1)
    c = next(c for c in result.boundary_contacts if c.kind == "class")
    assert Fraction(c.exact_lower) == Fraction(0.7) - Fraction(1e-12)
    assert c.lower == c.upper
    # A plateau at b's value minus tol gives an interval contact, not a unique root.
    p = scored_project({"a": 0.25, "b": 0.5})
    p.criteria[0].value_function = PiecewiseLinearValueFunction(
        points=[
            ControlPoint(x=0, value=0),
            ControlPoint(x=0.25, value=0),
            ControlPoint(x=0.5, value=1e-12),
            ControlPoint(x=1, value=1),
        ]
    )
    # b's score is tol, so the contact threshold is exactly zero.
    result = assess_measurement_range(p, p.analysis, "a", "score", 0, 1)
    c = result.boundary_contacts[0]
    assert (c.lower, c.upper) == (0, 0.25)
    assert not result.rank_can_change  # touching the tolerance band need not change rank


def test_zero_weight_flat_contact_and_singleton_range():
    p = tiny_project()
    p.weight_profiles[0].judgements = {"cost": 0, "quality": 1}
    result = assess_measurement_range(p, p.analysis, "a", "cost", 0, 100)
    assert not result.rank_can_change and not result.boundary_contacts
    singleton = assess_measurement_range(p, p.analysis, "a", "cost", 20, 20)
    assert not singleton.rank_can_change


def test_scenario_override_and_every_witness_match_fresh_engine_evaluations():
    p = tiny_project()
    p.scenarios = [
        Scenario(
            id="reverse",
            name="Reverse",
            value_function_overrides={
                "cost": PiecewiseLinearValueFunction(
                    points=[
                        ControlPoint(x=0, value=0),
                        ControlPoint(x=40, value=0.3),
                        ControlPoint(x=100, value=1),
                    ]
                )
            },
        )
    ]
    cfg = AnalysisConfiguration(scenario_id="reverse")
    result = assess_measurement_range(p, cfg, "a", "cost", 0, 100)
    assert result.maximum_score_at == 100
    for witness in result.witnesses:
        fresh = p.model_copy(deep=True)
        cell = next(
            m for m in fresh.performances if m.alternative_id == "a" and m.criterion_id == "cost"
        )
        cell.value = witness.measurement
        evaluated = next(a for a in evaluate_mavt(fresh, cfg).ranking if a.alternative_id == "a")
        assert (witness.score, witness.rank) == (evaluated.value, evaluated.rank)
