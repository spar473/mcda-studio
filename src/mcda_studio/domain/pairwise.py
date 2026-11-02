"""AHP inputs: pairwise judgements for each sibling group of criteria and, per leaf, for the
alternatives.

The section belongs to the ``ahp`` method; no other method reads it, and it never reads swing
weights, value functions or measurements. Each pair is stored once, as the matrix entry that is at
least 1: ``row`` is the favoured item (either item when they are judged equal) and the reciprocal
is derived, never stored. Types are checked here; the rules (known items, one judgement per pair,
values from 1 to 9, complete matrices) are validation issues, so a draft can be saved incomplete.
See ``docs/design/ahp.md``.
"""

from pydantic import Field

from mcda_studio.domain.common import DomainModel, FiniteFloat, Id


class PairwiseJudgement(DomainModel):
    """``row`` is ``value`` times as important, or preferred, as ``column`` (1 <= value <= 9)."""

    row: Id
    column: Id
    value: FiniteFloat


class CriteriaJudgements(DomainModel):
    """The children of one criterion (``None``: the top level) judged against each other."""

    parent_id: Id | None
    judgements: list[PairwiseJudgement] = Field(default_factory=list)


class AlternativeJudgements(DomainModel):
    """The alternatives judged against each other on one leaf criterion."""

    criterion_id: Id
    judgements: list[PairwiseJudgement] = Field(default_factory=list)


class AhpModel(DomainModel):
    criteria: list[CriteriaJudgements] = Field(default_factory=list)
    alternatives: list[AlternativeJudgements] = Field(default_factory=list)
