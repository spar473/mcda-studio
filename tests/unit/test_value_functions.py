import numpy as np
import pytest

from mcda_studio.domain.criteria import (
    ControlPoint,
    Direction,
    LinearValueFunction,
    PiecewiseLinearValueFunction,
    QualitativeValueFunction,
)
from mcda_studio.domain.errors import DomainError
from mcda_studio.domain.measurements import Domain
from mcda_studio.methods.mavt.value_functions import (
    build_evaluator,
    direct_rating,
    linear,
    piecewise_linear,
    qualitative,
)

# Control points quoted for the reference study's "Market Size" criterion (US$bn -> partial value).
MARKET_X = [1.380, 2.552, 5.077, 10.037, 26.450]
MARKET_V = [0.000, 0.252, 0.500, 0.748, 1.000]


class TestLinear:
    def test_increasing(self) -> None:
        assert linear(2.0, 2.0, 6.0) == 0.0
        assert linear(6.0, 2.0, 6.0) == 1.0
        assert linear(3.0, 2.0, 6.0) == pytest.approx(0.25)

    def test_decreasing(self) -> None:
        assert linear(2.0, 2.0, 6.0, increasing=False) == 1.0
        assert linear(6.0, 2.0, 6.0, increasing=False) == 0.0
        assert linear(3.0, 2.0, 6.0, increasing=False) == pytest.approx(0.75)

    @pytest.mark.parametrize("x", [1.9, 6.1, -50.0, 1e9])
    def test_outside_domain_is_an_error_not_extrapolation(self, x: float) -> None:
        with pytest.raises(DomainError, match="extrapolation"):
            linear(x, 2.0, 6.0)

    def test_floating_point_noise_at_the_boundary_is_tolerated(self) -> None:
        assert linear(6.0 + 1e-12, 2.0, 6.0) == 1.0

    @pytest.mark.parametrize("lo,hi", [(5.0, 5.0), (6.0, 2.0)])
    def test_reversed_or_equal_anchors_rejected(self, lo: float, hi: float) -> None:
        with pytest.raises(DomainError):
            linear(3.0, lo, hi)


class TestPiecewise:
    def test_passes_through_every_control_point(self) -> None:
        for x, v in zip(MARKET_X, MARKET_V, strict=True):
            assert piecewise_linear(x, MARKET_X, MARKET_V) == pytest.approx(v, abs=1e-15)

    def test_interpolation_matches_independent_implementation(self) -> None:
        for x in [1.7129, 1.38, 2.0, 3.3, 7.5, 12.0, 26.45, 20.0]:
            expected = float(np.interp(x, MARKET_X, MARKET_V))
            assert piecewise_linear(x, MARKET_X, MARKET_V) == pytest.approx(expected, abs=1e-12)

    def test_unrounded_measurement_1_7129(self) -> None:
        # first segment: 0.252 * (1.7129 - 1.380) / (2.552 - 1.380)  (derived, see docs)
        assert piecewise_linear(1.7129, MARKET_X, MARKET_V) == pytest.approx(0.07158, abs=5e-5)

    def test_outside_control_range_rejected(self) -> None:
        with pytest.raises(DomainError):
            piecewise_linear(1.0, MARKET_X, MARKET_V)
        with pytest.raises(DomainError):
            piecewise_linear(30.0, MARKET_X, MARKET_V)

    def test_unordered_points_rejected(self) -> None:
        with pytest.raises(DomainError):
            piecewise_linear(2.0, [1.0, 3.0, 2.0], [0.0, 0.5, 1.0])

    def test_decreasing_function(self) -> None:
        assert piecewise_linear(5.0, [0.0, 10.0], [1.0, 0.0]) == pytest.approx(0.5)


class TestQualitativeAndRating:
    def test_mapping(self) -> None:
        assert qualitative("fair", {"poor": 0.0, "fair": 0.3, "good": 1.0}) == 0.3

    def test_unknown_label(self) -> None:
        with pytest.raises(DomainError, match="not in the value-function mapping"):
            qualitative("great", {"poor": 0.0, "good": 1.0})

    def test_direct_rating(self) -> None:
        assert direct_rating(75.0, 0.0, 100.0) == pytest.approx(0.75)


class TestEvaluator:
    def test_linear_decreasing_bound_to_domain(self) -> None:
        ev = build_evaluator(
            LinearValueFunction(direction=Direction.DECREASING),
            Domain(lower=0.0, upper=10.0, source="fixed"),
        )
        assert ev(2.0) == (pytest.approx(0.8), False)

    def test_clamp_policy_reports_clamping(self) -> None:
        vf = LinearValueFunction(out_of_domain="clamp")
        ev = build_evaluator(vf, Domain(lower=0.0, upper=10.0, source="fixed"))
        assert ev(12.0) == (1.0, True)
        assert ev(-3.0) == (0.0, True)
        assert ev(5.0) == (0.5, False)

    def test_error_policy_raises(self) -> None:
        ev = build_evaluator(LinearValueFunction(), Domain(lower=0.0, upper=10.0, source="fixed"))
        with pytest.raises(DomainError):
            ev(12.0)

    def test_piecewise_and_qualitative(self) -> None:
        pw = PiecewiseLinearValueFunction(
            points=[ControlPoint(x=0, value=0), ControlPoint(x=4, value=1)]
        )
        assert (
            build_evaluator(pw, Domain(lower=0, upper=4, source="control_points"))(1.0)[0] == 0.25
        )
        q = QualitativeValueFunction(mapping={"x": 0.0, "y": 1.0})
        assert build_evaluator(q, None)("y") == (1.0, False)

    def test_numeric_function_without_domain_is_an_error(self) -> None:
        with pytest.raises(DomainError):
            build_evaluator(LinearValueFunction(), None)


def test_domain_tolerance_is_relative_to_the_span_not_to_the_magnitude_of_the_anchors() -> None:
    """Anchors near 1e6 with a span of 1e-3: a value 1e-3 above the upper anchor overshoots the
    whole span and must be rejected. A tolerance scaled by the anchor magnitude (1e-9 * 1e6 =
    1e-3) would silently accept it."""
    lower, upper = 1_000_000.0, 1_000_000.001
    with pytest.raises(DomainError):
        linear(upper + 1e-3, lower, upper)
    with pytest.raises(DomainError):
        piecewise_linear(upper + 1e-3, [lower, upper], [0.0, 1.0])
    # a span-relative band still absorbs genuine floating-point noise on an ordinary scale
    assert linear(10.0 + 0.5e-9 * 10.0, 0.0, 10.0) == 1.0
