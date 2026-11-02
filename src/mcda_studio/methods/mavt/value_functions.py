"""Pure value-function maths. No project state; every function is deterministic.

All functions return a value in [0, 1] and raise DomainError for an argument outside the domain
(beyond a 1e-9 relative tolerance for floating-point noise). Nothing extrapolates silently.
"""

import bisect
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from mcda_studio.domain.criteria import (
    Direction,
    DirectRatingValueFunction,
    LinearValueFunction,
    PiecewiseLinearValueFunction,
    QualitativeValueFunction,
    ValueFunctionSpec,
)
from mcda_studio.domain.errors import DomainError
from mcda_studio.domain.measurements import Domain, Measurement

_REL_TOL = 1e-9


def _check_in_domain(x: float, lower: float, upper: float) -> None:
    tol = _REL_TOL * (upper - lower)
    if x < lower - tol or x > upper + tol:
        raise DomainError(
            f"value {x!r} is outside the domain [{lower}, {upper}]; extrapolation is not performed"
        )


def _unit(v: float) -> float:
    return min(1.0, max(0.0, v))


def linear(x: float, lower: float, upper: float, *, increasing: bool = True) -> float:
    """v(x) = (x-L)/(U-L) if increasing else (U-x)/(U-L)."""
    if not upper > lower:
        raise DomainError(f"linear anchors must satisfy upper > lower (got {lower}, {upper})")
    _check_in_domain(x, lower, upper)
    return _unit((x - lower) / (upper - lower) if increasing else (upper - x) / (upper - lower))


def piecewise_linear(x: float, xs: Sequence[float], vs: Sequence[float]) -> float:
    """Interpolate between control points (xs strictly increasing)."""
    if len(xs) != len(vs) or len(xs) < 2:
        raise DomainError("a piecewise function needs >= 2 matching control points")
    if any(b <= a for a, b in zip(xs, xs[1:], strict=False)):
        raise DomainError("control-point x values must be strictly increasing")
    _check_in_domain(x, xs[0], xs[-1])
    x = min(max(x, xs[0]), xs[-1])
    i = bisect.bisect_right(xs, x) - 1
    if i >= len(xs) - 1:
        return float(vs[-1])
    x0, x1, v0, v1 = xs[i], xs[i + 1], vs[i], vs[i + 1]
    return _unit(v0 + (v1 - v0) * (x - x0) / (x1 - x0))


def qualitative(label: str, mapping: Mapping[str, float]) -> float:
    try:
        return float(mapping[label])
    except KeyError:
        raise DomainError(f"label {label!r} is not in the value-function mapping") from None


def direct_rating(x: float, min_rating: float, max_rating: float) -> float:
    return linear(x, min_rating, max_rating, increasing=True)


@dataclass(frozen=True)
class ValueEvaluator:
    """A value function bound to a concrete domain, ready to score measurements."""

    kind: str
    fn: Callable[[Measurement], float]
    domain: Domain | None
    clamp: bool

    def __call__(self, x: Measurement) -> tuple[float, bool]:
        """Return ``(partial_value, was_clamped)``."""
        clamped = False
        if self.clamp and self.domain is not None and not isinstance(x, str):
            if x < self.domain.lower:
                x, clamped = self.domain.lower, True
            elif x > self.domain.upper:
                x, clamped = self.domain.upper, True
        return self.fn(x), clamped


def build_evaluator(vf: ValueFunctionSpec, domain: Domain | None) -> ValueEvaluator:
    """Bind a value-function spec to its resolved domain."""
    if isinstance(vf, QualitativeValueFunction):
        mapping = dict(vf.mapping)
        return ValueEvaluator("qualitative", lambda x: qualitative(str(x), mapping), None, False)
    if domain is None:
        raise DomainError("cannot resolve the domain of a numeric value function")
    clamp = vf.out_of_domain == "clamp"
    if isinstance(vf, LinearValueFunction):
        lo, hi = domain.lower, domain.upper
        inc = vf.direction is Direction.INCREASING
        return ValueEvaluator(
            "linear", lambda x: linear(float(x), lo, hi, increasing=inc), domain, clamp
        )
    if isinstance(vf, PiecewiseLinearValueFunction):
        xs = [p.x for p in vf.points]
        vs = [p.value for p in vf.points]
        return ValueEvaluator(
            "piecewise_linear", lambda x: piecewise_linear(float(x), xs, vs), domain, clamp
        )
    if isinstance(vf, DirectRatingValueFunction):
        lo, hi = vf.min_rating, vf.max_rating
        return ValueEvaluator(
            "direct_rating", lambda x: direct_rating(float(x), lo, hi), domain, clamp
        )
    raise DomainError(f"unsupported value function {vf!r}")  # pragma: no cover
