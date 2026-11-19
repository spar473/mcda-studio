"""Scenario round trips preserve base state and engine results under random raw preferences."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mcda_studio.domain.criteria import Direction, LinearValueFunction
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps

from builders import tiny_project


@settings(max_examples=60, deadline=None)
@given(st.integers(1, 10000), st.integers(1, 10000), st.sampled_from(list(Direction)))
def test_sparse_scenario_roundtrip_and_comparison_match_an_independent_affine_oracle(
    a, b, direction
):
    p = tiny_project()
    p.id = "property-case"
    p = ps.set_judgement(p, "cost", a)
    p = ps.set_judgement(p, "quality", b)
    before = p.fingerprint()
    base = svc.evaluate_project(p)
    q = ps.create_scenario(p, "S", "s")
    q = ps.set_scenario_override(q, "s", "cost", LinearValueFunction(direction=direction))
    q = ps.duplicate_scenario(q, "s", "Copy", "copy")
    comparison = svc.compare_scenarios(q, ["s", "copy"], AnalysisConfiguration())
    expected = {}
    for alt, cost, quality in [("a", 0.2, 0.6), ("b", 0.6, 0.9)]:
        partial = cost if direction is Direction.INCREASING else 1 - cost
        expected[alt] = partial * a / (a + b) + quality * b / (a + b)
    for outcome in comparison.scenarios:
        assert outcome.values == pytest.approx(expected, abs=1e-12)
        assert outcome.delta_from_baseline == pytest.approx(
            {k: expected[k] - comparison.baseline.values[k] for k in expected}, abs=1e-12
        )
    q = ps.clear_scenario_override(q, "copy", "cost")
    assert (
        svc.evaluate_project(q, AnalysisConfiguration(scenario_id="copy")).ranking == base.ranking
    )
    q = ps.remove_scenario(ps.remove_scenario(q, "copy"), "s")
    assert q.fingerprint() == before and p.fingerprint() == before
