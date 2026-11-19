"""Versioned, local evidence dossier; claims are not themselves decision inputs."""

from datetime import date, datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from mcda_studio.domain.common import DomainModel, FiniteFloat, Id


class Source(DomainModel):
    name: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    location: str = ""
    date: date
    description: str = Field(min_length=1)
    classification: Literal["independent", "self_reported", "unknown"] = "unknown"


class Origin(DomainModel):
    kind: Literal["human", "tool"]
    proposed_by: str = Field(min_length=1)
    tool_id: str | None = None
    tool_version: str | None = None

    @model_validator(mode="after")
    def tool_identity(self) -> Self:
        if self.kind == "tool" and not self.tool_id:
            raise ValueError("tool proposals require a tool identifier")
        return self


class Review(DomainModel):
    status: Literal["accepted", "corrected", "rejected"]
    reviewer: str = Field(min_length=1)
    reviewed_at: datetime
    corrected_value: FiniteFloat | str | None = None
    note: str = ""

    @model_validator(mode="after")
    def review_details(self) -> Self:
        if self.reviewed_at.utcoffset() is None:
            raise ValueError("review time must include a timezone")
        if (self.status == "corrected") != (self.corrected_value is not None):
            raise ValueError("only corrected reviews require a corrected value")
        return self


class Claim(DomainModel):
    id: Id
    alternative_id: Id
    criterion_id: Id
    value: FiniteFloat | str
    unit: str | None
    source: Source
    origin: Origin
    review: Review | None = None
    uncertainty_lower: FiniteFloat | None = None
    uncertainty_upper: FiniteFloat | None = None
    outdated: bool = False

    @model_validator(mode="after")
    def uncertainty(self) -> Self:
        lo, hi = self.uncertainty_lower, self.uncertainty_upper
        if (lo is None) != (hi is None):
            raise ValueError("uncertainty needs both bounds")
        if (
            lo is not None
            and hi is not None
            and (isinstance(self.value, str) or lo > hi or not lo <= self.value <= hi)
        ):
            raise ValueError("uncertainty bounds must contain the numeric claim")
        return self


class EvidenceDossier(DomainModel):
    schema_version: Literal[1] = 1
    project_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    claims: list[Claim] = Field(default_factory=list)
