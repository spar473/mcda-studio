"""Analyst-stated uncertainty for SMAA-2: distributions for measurements, weight uncertainty for
sibling groups, and the stated dependence between them.

The section belongs to the ``smaa2`` method; no other method reads it. Types are checked here; the
rules (supports inside the value-function domain, probabilities summing to one, known cells and
groups, supported dependence) are validation issues, so a draft can be saved incomplete. A missing
measurement stays missing: a distribution never fills it. See ``docs/design/smaa-2.md``.
"""

from typing import Annotated, Literal

from pydantic import Field

from mcda_studio.domain.common import DomainModel, FiniteFloat, Id


class UniformDistribution(DomainModel):
    kind: Literal["uniform"] = "uniform"
    lower: FiniteFloat
    upper: FiniteFloat


class TriangularDistribution(DomainModel):
    kind: Literal["triangular"] = "triangular"
    lower: FiniteFloat
    mode: FiniteFloat
    upper: FiniteFloat


class DiscreteDistribution(DomainModel):
    """Listed numeric values with their probabilities."""

    kind: Literal["discrete"] = "discrete"
    values: list[FiniteFloat]
    probabilities: list[FiniteFloat]


class CategoricalDistribution(DomainModel):
    """Listed labels of a labelled scale with their probabilities."""

    kind: Literal["categorical"] = "categorical"
    labels: list[str]
    probabilities: list[FiniteFloat]


Distribution = Annotated[
    UniformDistribution | TriangularDistribution | DiscreteDistribution | CategoricalDistribution,
    Field(discriminator="kind"),
]


class CellUncertainty(DomainModel):
    """One measurement's distribution, used instead of its entered value in SMAA runs."""

    alternative_id: Id
    criterion_id: Id
    distribution: Distribution


class GroupUncertainty(DomainModel):
    """Weight uncertainty in one sibling group; a group without an entry keeps its ratings.

    ``unknown``: local weights uniform on the group's simplex, Dirichlet(1, ..., 1).
    ``rating_intervals``: each child's raw swing rating uniform on its stated [lower, upper], then
    normalised within the group.
    """

    parent_id: Id | None  # None is the top-level group
    kind: Literal["unknown", "rating_intervals"]
    intervals: dict[Id, tuple[FiniteFloat, FiniteFloat]] = Field(default_factory=dict)


class CellRef(DomainModel):
    alternative_id: Id
    criterion_id: Id


class SharedDraw(DomainModel):
    """Cells from one source: they use one common uniform draw through their own quantiles."""

    id: Id
    cells: list[CellRef]


class SmaaModel(DomainModel):
    # Only "independent" is supported; anything else is refused by validation, not assumed.
    dependence: str = "independent"
    cells: list[CellUncertainty] = Field(default_factory=list)
    groups: list[GroupUncertainty] = Field(default_factory=list)
    shared_draws: list[SharedDraw] = Field(default_factory=list)
