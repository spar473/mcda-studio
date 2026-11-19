"""Value-based sorting inputs: ordered classes with numeric boundaries on the overall value scale.

The section belongs to the ``mavt_sorting`` method; MAVT never reads it. Types are checked here;
the rules (boundary order, range, audit cut-off) are validation issues, so a draft can be saved
incomplete. See ``docs/design/value-based-sorting.md``.
"""

from pydantic import Field, StrictInt

from mcda_studio.domain.common import DomainModel, FiniteFloat, Id


class SortingClass(DomainModel):
    """One ordered class. ``lower_boundary`` is the overall value needed to enter it.

    The lowest class has no boundary: it takes every remaining value.
    """

    id: Id
    name: str = Field(min_length=1)
    description: str = ""
    lower_boundary: FiniteFloat | None = None


class SortingAudit(DomainModel):
    """A seed-keyed sample of alternatives sorted below ``below_class_id``, for manual review."""

    below_class_id: Id
    sample_size: StrictInt
    seed: StrictInt


class SortingModel(DomainModel):
    classes: list[SortingClass] = Field(default_factory=list)  # best first
    audit: SortingAudit | None = None
