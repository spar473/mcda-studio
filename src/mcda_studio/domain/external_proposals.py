"""Typed local proposal intake and append-only review sidecars; no analytical weights."""

from datetime import date, datetime
from typing import Annotated, Any, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from mcda_studio.domain.common import DomainModel, Id
from mcda_studio.domain.evidence import EvidenceDossier, Source
from mcda_studio.domain.project import Project

Text = Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class ProposalModel(DomainModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        strict=True,
        json_schema_serialization_defaults_required=True,
    )

    @model_validator(mode="before")
    @classmethod
    def strict_metadata(cls, value: Any) -> Any:
        if isinstance(value, dict):
            for key in ("run_at", "reviewed_at", "recorded_at"):
                if key in value and not (
                    isinstance(value[key], datetime)
                    or isinstance(value[key], str)
                    and "T" in value[key]
                ):
                    raise ValueError("timestamps must be explicit ISO date-times with timezones")
            sources = value.get("sources")
            if isinstance(sources, dict):
                for source in sources.values():
                    if isinstance(source, dict) and "date" in source:
                        supplied_date = source["date"]
                        if type(supplied_date) is not date and not (
                            isinstance(supplied_date, str)
                            and len(supplied_date) == 10
                            and supplied_date[4] == "-"
                            and supplied_date[7] == "-"
                        ):
                            raise ValueError("source date must be an explicit ISO calendar date")
            for key in ("schema_version", "proposal_version", "workspace_version", "version"):
                if key in value and type(value[key]) is not int:
                    raise ValueError("version numbers must be integers")
        return value


class ConfidenceBounds(ProposalModel):
    name: Text
    lower: Number
    upper: Number

    @model_validator(mode="after")
    def bounds(self) -> Self:
        if self.lower > self.upper:
            raise ValueError("confidence scale bounds are reversed")
        return self


class ProposalConfidence(ProposalModel):
    value: Number
    scale: Literal["unit_interval"] | ConfidenceBounds
    meaning: Text

    @model_validator(mode="after")
    def in_scale(self) -> Self:
        lo, hi = (
            (0.0, 1.0) if self.scale == "unit_interval" else (self.scale.lower, self.scale.upper)
        )
        if not lo <= self.value <= hi:
            raise ValueError("confidence is outside its declared scale")
        return self


class LocalModelCard(ProposalModel):
    version: Literal[1] = 1
    purpose: Text
    limitations: Text
    model_version: Text
    # Local explanatory fields; the separate proxy plan imposes its stronger activation contract.
    details: dict[Id, Text] = Field(default_factory=dict, max_length=64)


class ProposalSubject(ProposalModel):
    alternative_id: Id
    criterion_id: Id | None = None


class NumericProposal(ProposalModel):
    kind: Literal["numeric_cell"] = "numeric_cell"
    value: Number
    unit: str | None = Field(max_length=64)


class CategoricalProposal(ProposalModel):
    kind: Literal["categorical_cell"] = "categorical_cell"
    value: Text
    unit: str | None = Field(max_length=64)


class AlternativeTag(ProposalModel):
    kind: Literal["alternative_tag"] = "alternative_tag"
    namespace: Id
    label: Text
    text: Text


class ProposedMeasurement(ProposalModel):
    value: Number | Text
    unit: str | None = Field(max_length=64)


class SuggestedSourceClaim(ProposalModel):
    kind: Literal["source_claim"] = "source_claim"
    source_id: Id
    assertion: Text
    excerpt: Text
    location: Text
    measurement: ProposedMeasurement | None = None


ProposalPayload = Annotated[
    NumericProposal | CategoricalProposal | AlternativeTag | SuggestedSourceClaim,
    Field(discriminator="kind"),
]


class ExternalProposal(ProposalModel):
    proposal_version: Literal[1] = 1
    id: Id
    subject: ProposalSubject
    payload: ProposalPayload
    tool_id: Text
    tool_version: Text
    model_card_id: Id
    model_card_digest: Digest
    run_at: datetime = Field(strict=False)
    confidence: ProposalConfidence | None = None
    source_ids: list[Id] = Field(default_factory=list, max_length=64)
    replaces_proposal_id: Id | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        if self.run_at.utcoffset() is None:
            raise ValueError("tool run timestamp needs a timezone")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("duplicate source reference")
        if (
            self.payload.kind in {"numeric_cell", "categorical_cell"}
            and not self.subject.criterion_id
        ):
            raise ValueError("cell proposals require a criterion subject")
        if self.payload.kind == "alternative_tag" and self.subject.criterion_id is not None:
            raise ValueError("alternative tags cannot target a criterion")
        if (
            isinstance(self.payload, SuggestedSourceClaim)
            and self.payload.measurement is not None
            and self.subject.criterion_id is None
        ):
            raise ValueError("a source claim measurement needs a criterion")
        return self


class ProposalIntake(ProposalModel):
    schema_version: Literal[1] = 1
    project_fingerprint: Digest
    sources: dict[Id, Source] = Field(default_factory=dict, max_length=2000)
    model_cards: dict[Id, LocalModelCard] = Field(default_factory=dict, max_length=2000)
    proposals: list[ExternalProposal] = Field(default_factory=list, max_length=2000)
    human_dossier: EvidenceDossier | None = None

    @model_validator(mode="after")
    def identifiers(self) -> Self:
        ids = [p.id for p in self.proposals]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate proposal IDs")
        return self


class ProposalReviewDetails(ProposalModel):
    status: Literal["accepted", "corrected", "rejected"]
    reviewer: Text
    reviewed_at: datetime = Field(strict=False)
    note: str = Field(default="", max_length=2000)
    corrected_payload: ProposalPayload | None = None
    primary_source_id: Id | None = None
    supporting_source_ids: list[Id] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def details(self) -> Self:
        if not self.reviewer.strip():
            raise ValueError("a named reviewer is required")
        if self.reviewed_at.utcoffset() is None:
            raise ValueError("review timestamp needs a timezone")
        if (self.status == "corrected") != (self.corrected_payload is not None):
            raise ValueError("only a corrected review requires a replacement payload")
        if len(set(self.supporting_source_ids)) != len(self.supporting_source_ids):
            raise ValueError("duplicate supporting source reference")
        return self


class ProposalReview(ProposalModel):
    proposal_id: Id
    review: ProposalReviewDetails


class ProposalRegistrySupply(ProposalModel):
    sources: dict[Id, Source] = Field(default_factory=dict, max_length=2000)
    model_cards: dict[Id, LocalModelCard] = Field(default_factory=dict, max_length=2000)
    recorded_by: Text
    recorded_at: datetime = Field(strict=False)
    note: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def recorded(self) -> Self:
        if not self.recorded_by.strip() or self.recorded_at.utcoffset() is None:
            raise ValueError(
                "registry additions need a named local recorder and timezone-aware time"
            )
        if not self.sources and not self.model_cards:
            raise ValueError("supply at least one local registry entry")
        return self


class ExternalProposals(ProposalModel):
    """Original intake plus its exact source and separate, replayable review events."""

    workspace_version: Literal[1] = 1
    source_project: Project | None
    intake: ProposalIntake
    reviews: list[ProposalReview] = Field(default_factory=list, max_length=2000)
    registry_supplies: list[ProposalRegistrySupply] = Field(default_factory=list, max_length=2000)
    digest: str
