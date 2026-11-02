"""Random incomplete-model checks against elementary independent oracles."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mcda_studio.domain.criteria import Direction
from mcda_studio.domain.previews import ValueFunctionCandidate
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.services import analysis_service as svc

from builders import tiny_project


@settings(max_examples=60, deadline=None)
@given(st.floats(-1e4, 1e4), st.floats(1e-3, 1e4), st.booleans())
def test_fixed_preview_matches_affine_oracle_without_measurements(lower, span, decreasing):
    p = tiny_project()
    p.performances = []
    p.weight_profiles = []
    vf = p.criteria[1].value_function.model_copy(
        update={"direction": Direction.DECREASING if decreasing else Direction.INCREASING}
    )
    before = p.model_dump_json()
    result = svc.preview_value_function(
        p,
        "quality",
        candidate=ValueFunctionCandidate(
            scale=Scale(type=ScaleType.INTERVAL, lower=lower, upper=lower + span), value_function=vf
        ),
        sample_count=13,
    )
    assert result.curve_ready and not result.measurements_complete
    for s in result.samples:
        expected = (s.measurement - lower) / ((lower + span) - lower)
        assert s.partial_value == pytest.approx(1 - expected if decreasing else expected, abs=1e-12)
    assert p.model_dump_json() == before


@settings(max_examples=60, deadline=None)
@given(st.floats(0.01, 1e5), st.floats(0.01, 1e5), st.floats(0.01, 100))
def test_weight_previews_are_normalised_scale_invariant_and_do_not_impute(a, b, factor):
    p = tiny_project()
    p.performances = []
    p.weight_profiles[0].judgements = {"cost": a, "quality": b}
    before = p.model_dump_json()
    result = svc.preview_weights(p)
    assert result.weights_ready and result.global_weights["cost"] == pytest.approx(
        a / (a + b), abs=1e-12
    )
    assert sum(result.global_weights.values()) == pytest.approx(1, abs=1e-12)
    assert p.model_dump_json() == before
    p.weight_profiles[0].judgements = {"cost": a * factor, "quality": b * factor}
    assert svc.preview_weights(p).global_weights == pytest.approx(result.global_weights, abs=1e-12)
    assert p.performances == []
