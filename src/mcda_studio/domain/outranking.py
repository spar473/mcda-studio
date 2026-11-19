"""PROMETHEE II inputs: per leaf criterion, a direction, a weight, a preference function with its
thresholds and, on a labelled scale, a number for every label.

The section belongs to the ``promethee2`` method; no other method reads it, and it never reads
MAVT's value functions or swing weights. Types are checked here; the rules (thresholds, weights,
codings, one entry per leaf) are validation issues, so a draft can be saved incomplete. See
``docs/design/promethee-ii.md``.
"""

from typing import Annotated, Literal

from pydantic import Field

from mcda_studio.domain.common import DomainModel, FiniteFloat, Id


class UsualFunction(DomainModel):
    """Any positive difference is full preference."""

    kind: Literal["usual"] = "usual"


class UShapeFunction(DomainModel):
    """No preference up to the indifference threshold q, full preference beyond it."""

    kind: Literal["u_shape"] = "u_shape"
    q: FiniteFloat


class VShapeFunction(DomainModel):
    """Preference grows linearly from 0 to full at the preference threshold p."""

    kind: Literal["v_shape"] = "v_shape"
    p: FiniteFloat


class LinearPreferenceFunction(DomainModel):
    """No preference up to q, linear between q and p, full preference from p."""

    kind: Literal["linear"] = "linear"
    q: FiniteFloat
    p: FiniteFloat


AnyPreferenceFunction = UsualFunction | UShapeFunction | VShapeFunction | LinearPreferenceFunction
PreferenceFunction = Annotated[AnyPreferenceFunction, Field(discriminator="kind")]


class PrometheeCriterion(DomainModel):
    """PROMETHEE's inputs for one leaf; thresholds are in its units (its codes when labelled)."""

    criterion_id: Id
    direction: Literal["maximise", "minimise"]
    weight: FiniteFloat  # any non-negative number; normalised by the sum of all weights
    function: PreferenceFunction
    # Required on a labelled leaf, refused on a numeric one; omitted from files when absent.
    coding: dict[str, FiniteFloat] | None = Field(default=None, exclude_if=lambda v: v is None)


class PrometheeModel(DomainModel):
    criteria: list[PrometheeCriterion] = Field(default_factory=list)


def thresholds(function: AnyPreferenceFunction) -> tuple[float | None, float | None]:
    """The function's stated (q, p); a threshold the function does not have is None."""
    q = function.q if isinstance(function, UShapeFunction | LinearPreferenceFunction) else None
    p = function.p if isinstance(function, VShapeFunction | LinearPreferenceFunction) else None
    return q, p
