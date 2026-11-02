"""Performance table entries and the value-function domain they must respect."""

from collections.abc import Iterable
from typing import Literal

from mcda_studio.domain.common import DomainModel, FiniteFloat, Id
from mcda_studio.domain.criteria import (
    DirectRatingValueFunction,
    LinearValueFunction,
    PiecewiseLinearValueFunction,
    ValueFunctionSpec,
)
from mcda_studio.domain.scales import AnchorMode, Scale

Measurement = float | str


class Performance(DomainModel):
    """One cell of the performance table: how an alternative performs on a leaf criterion."""

    alternative_id: Id
    criterion_id: Id
    value: FiniteFloat | str


class Domain(DomainModel):
    """The numeric interval over which a value function is defined, and where it came from."""

    lower: float
    upper: float
    source: Literal["fixed", "local", "control_points", "rating_range"]


def effective_domain(
    scale: Scale, vf: ValueFunctionSpec, observed: Iterable[float]
) -> Domain | None:
    """Domain of ``vf`` on ``scale``; ``None`` if it cannot be determined (or is not numeric).

    For LOCAL linear anchors the domain is the min/max of ``observed`` (the alternatives'
    measurements) - this is exactly the dependence on the alternative set that is recorded.
    """
    if isinstance(vf, LinearValueFunction):
        if scale.anchor_mode is AnchorMode.LOCAL:
            values = list(observed)
            if not values:
                return None
            return Domain(lower=min(values), upper=max(values), source="local")
        if scale.lower is None or scale.upper is None:
            return None
        return Domain(lower=scale.lower, upper=scale.upper, source="fixed")
    if isinstance(vf, PiecewiseLinearValueFunction):
        if len(vf.points) < 2:
            return None
        return Domain(lower=vf.points[0].x, upper=vf.points[-1].x, source="control_points")
    if isinstance(vf, DirectRatingValueFunction):
        return Domain(lower=vf.min_rating, upper=vf.max_rating, source="rating_range")
    return None
