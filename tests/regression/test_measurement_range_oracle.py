"""Numerical and rational verification of the fixed-anchor range calculation."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from measurement_range_oracle import contact, rank

from mcda_studio.domain.criteria import ControlPoint, PiecewiseLinearValueFunction
from mcda_studio.methods.mavt.measurement_range import assess_measurement_range

from builders import scored_project


@settings(max_examples=100)
@given(st.integers(1, 99), st.integers(1, 99), st.booleans())
def test_piecewise_contacts_and_states_against_independent_numeric_oracle(middle, other, reverse):
    xs = [0.0, 0.5, 1.0]
    values = [0.0, middle / 100, 1.0]
    if reverse:
        values = [1 - v for v in values]
    b = other / 100
    p = scored_project({"a": 0.5, "b": b})
    p.criteria[0].value_function = PiecewiseLinearValueFunction(
        points=[ControlPoint(x=x, value=v) for x, v in zip(xs, values, strict=True)]
    )
    result = assess_measurement_range(p, p.analysis, "a", "score", 0, 1)
    expected = contact(b, xs, values)
    assert expected is not None
    assert len(result.boundary_contacts) == 1
    assert result.boundary_contacts[0].lower == pytest.approx(expected, rel=0, abs=1e-14)
    assert result.baseline_rank == rank(0.5, b, xs, values)
    assert result.rank_can_change == any(rank(x, b, xs, values) != result.baseline_rank for x in xs)
    for witness in result.witnesses:
        assert witness.rank == rank(witness.measurement, b, xs, values)
