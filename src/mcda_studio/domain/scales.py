"""Measurement scales: categorical, ordinal, interval and ratio.

A scale records *what kind of measurement* an attribute is. It does not say how the
measurement becomes a preference score - that is the value function's job, and which
value functions are admissible for which scale type is enforced in ``criteria.py``.
"""

from enum import StrEnum

from pydantic import Field

from mcda_studio.domain.common import DomainModel, FiniteFloat


class ScaleType(StrEnum):
    CATEGORICAL = "categorical"  # unordered labels
    ORDINAL = "ordinal"  # ordered labels (low -> high); spacing is NOT assumed equal
    INTERVAL = "interval"  # numeric, arbitrary zero
    RATIO = "ratio"  # numeric, true zero (values must be >= 0)


class AnchorMode(StrEnum):
    """Where the 0-and-1 anchors of a *linear* value function come from.

    FIXED: ``lower``/``upper`` are stated by the user and never depend on the alternatives.
    LOCAL: anchors are the min/max over the alternatives currently in the project. This is an
           explicit, recorded choice because adding an alternative can then change every
           existing alternative's score.
    """

    FIXED = "fixed"
    LOCAL = "local"


class Scale(DomainModel):
    type: ScaleType
    unit: str | None = None
    lower: FiniteFloat | None = None
    upper: FiniteFloat | None = None
    anchor_mode: AnchorMode = AnchorMode.FIXED
    labels: list[str] = Field(default_factory=list)

    @property
    def is_numeric(self) -> bool:
        return self.type in (ScaleType.INTERVAL, ScaleType.RATIO)

    @property
    def is_labelled(self) -> bool:
        return self.type in (ScaleType.CATEGORICAL, ScaleType.ORDINAL)
