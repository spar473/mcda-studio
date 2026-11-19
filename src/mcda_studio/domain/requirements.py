"""Mandatory requirements on individual leaf measurements, for the feasibility check.

The section is method-independent: no method reads it, and it reads no method's inputs, weights,
profiles, value functions or scenarios. Types are checked here; the rules (known leaves, matching
scale kind and unit, ordered limits, known labels) are validation issues, so a draft can be saved
incomplete. See ``docs/design/feasibility-check.md``.
"""

from typing import Annotated, Literal

from pydantic import Field

from mcda_studio.domain.common import DomainModel, FiniteFloat, Id


class BoundRequirement(DomainModel):
    """A numeric leaf's measurement must lie within the stated limits, in the leaf's unit."""

    kind: Literal["bound"] = "bound"
    id: Id
    name: str = Field(min_length=1)
    criterion_id: Id
    unit: str | None  # must equal the leaf's unit exactly; nothing is converted
    minimum: FiniteFloat | None = None
    minimum_inclusive: bool = True
    maximum: FiniteFloat | None = None
    maximum_inclusive: bool = True
    rationale: str = ""


class LabelsRequirement(DomainModel):
    """A labelled leaf's measurement must be one of the allowed labels."""

    kind: Literal["labels"] = "labels"
    id: Id
    name: str = Field(min_length=1)
    criterion_id: Id
    allowed: list[str]
    rationale: str = ""


Requirement = Annotated[BoundRequirement | LabelsRequirement, Field(discriminator="kind")]
AnyRequirement = BoundRequirement | LabelsRequirement
