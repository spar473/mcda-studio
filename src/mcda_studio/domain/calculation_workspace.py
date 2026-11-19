"""Portable authoring history around unchanged version-1 calculation models."""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mcda_studio.domain.common import DomainModel
from mcda_studio.domain.derived import (
    DerivedFormula,
    DerivedModel,
    Dimension,
    SourceFactor,
    Symbol,
    UnitName,
)
from mcda_studio.domain.evidence import Review
from mcda_studio.domain.project import Project

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Person = Annotated[str, Field(min_length=1, max_length=200)]


class _Recorded(DomainModel):
    recorded_at: datetime

    @model_validator(mode="after")
    def aware(self) -> Self:
        if self.recorded_at.utcoffset() is None:
            raise ValueError("recorded time must include a timezone")
        return self


class DefineUnit(_Recorded):
    kind: Literal["unit"] = "unit"
    unit: UnitName
    dimension: Dimension
    recorded_by: Person


class DefineSource(_Recorded):
    kind: Literal["source"] = "source"
    # A definition is a proposal; its acceptance is a separate review event.
    factor: SourceFactor


class DefineFormula(_Recorded):
    kind: Literal["formula"] = "formula"
    formula: DerivedFormula


class ReviewEntry(DomainModel):
    kind: Literal["review"] = "review"
    entry: Literal["source", "formula"]
    id: Symbol
    review: Review


class RemoveEntry(_Recorded):
    kind: Literal["remove"] = "remove"
    entry: Literal["source", "formula"]
    id: Symbol
    recorded_by: Person


class Rebind(_Recorded):
    kind: Literal["rebind"] = "rebind"
    # The whole revision is retained, so replay never depends on a project kept elsewhere.
    project: Project
    recorded_by: Person
    note: str = Field(default="", max_length=2000)


class ApplyCalculation(_Recorded):
    kind: Literal["apply"] = "apply"
    review_digest: Digest
    recorded_by: Person
    # The applied project's fingerprint; replay recompiles and must reproduce it exactly.
    project_fingerprint: Digest


ProposedEvent = Annotated[
    DefineUnit | DefineSource | DefineFormula | ReviewEntry | RemoveEntry | Rebind,
    Field(discriminator="kind"),
]
CalculationEvent = Annotated[
    DefineUnit
    | DefineSource
    | DefineFormula
    | ReviewEntry
    | RemoveEntry
    | Rebind
    | ApplyCalculation,
    Field(discriminator="kind"),
]


class CalculationWorkspace(DomainModel):
    workspace_version: Literal[1] = 1
    source_project: Project
    original_model: DerivedModel
    # Append-only. Reopening replays these events rather than trusting a cached current model.
    events: list[CalculationEvent] = Field(default_factory=list, max_length=2000)
    digest: str
