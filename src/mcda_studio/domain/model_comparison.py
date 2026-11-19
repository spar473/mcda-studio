"""Reviewed quantity checks and separate model-output comparisons; no domain dispatch."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mcda_studio.domain.common import Id
from mcda_studio.domain.derived import DerivedModel, Symbol, UnitName
from mcda_studio.domain.evidence import Origin, Review
from mcda_studio.domain.factor_uncertainty import FactorUncertaintyModel
from mcda_studio.domain.sidecar_common import SidecarModel

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Text = Annotated[str, Field(min_length=1, max_length=2000)]


class QuantityCheck(SidecarModel):
    id: Id
    quantity_kind: Literal["source", "formula"]
    quantity_id: Symbol
    unit: UnitName
    lower: Number | None = None
    upper: Number | None = None
    lower_inclusive: bool = True
    upper_inclusive: bool = True

    @model_validator(mode="after")
    def bounds(self) -> Self:
        if self.lower is None and self.upper is None:
            raise ValueError("a quantity check needs at least one finite bound")
        if (
            self.lower is not None
            and self.upper is not None
            and (
                self.lower > self.upper
                or (
                    self.lower == self.upper and not (self.lower_inclusive and self.upper_inclusive)
                )
            )
        ):
            raise ValueError("quantity check bounds are reversed or empty")
        return self


class ModelChecks(SidecarModel):
    schema_version: Literal[1] = 1
    project_fingerprint: Digest
    model_digest: Digest
    checks: list[QuantityCheck] = Field(default_factory=list, max_length=512)
    origin: Origin
    review: Review | None = None
    digest: str


class ModelScope(SidecarModel):
    population: Text | None = None
    geography: Text | None = None
    period: Text | None = None
    currency_basis: Text | None = None
    unit: UnitName | None = None


class SourceInterval(SidecarModel):
    factor_id: Symbol
    unit: UnitName
    lower: Number
    upper: Number
    origin: Origin
    review: Review | None = None

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.lower > self.upper:
            raise ValueError("source interval bounds are reversed")
        return self


class SourceRange(SidecarModel):
    kind: Literal["source_interval"] = "source_interval"
    intervals: list[SourceInterval] = Field(min_length=1, max_length=256)


class EnclosureRange(SidecarModel):
    kind: Literal["support_enclosure"] = "support_enclosure"


class ExactRange(SidecarModel):
    kind: Literal["exact_discrete_support"] = "exact_discrete_support"


class SampledRange(SidecarModel):
    kind: Literal["sampled_central95"] = "sampled_central95"
    draws: int = Field(default=1000, ge=1, le=100000)
    seed: int = Field(default=7, ge=0, lt=2**63)
    quantile_algorithm: Literal["linear.v1"] = "linear.v1"


RangeRequest = Annotated[
    SourceRange | EnclosureRange | ExactRange | SampledRange, Field(discriminator="kind")
]


class PopulationSegment(SidecarModel):
    formula_id: Symbol
    population_key: Id
    definition: Text


class SegmentAggregation(SidecarModel):
    segments: list[PopulationSegment] = Field(min_length=2, max_length=64)
    disjoint_populations: bool
    overlap_model_formula_id: Symbol | None = None
    overlap_quantity_ids: list[Symbol] = Field(default_factory=list, max_length=64)
    rationale: Text
    review: Review | None = None


class ModelOutputSpec(SidecarModel):
    id: Id
    label: Text
    model: DerivedModel
    formula_id: Symbol
    scope: ModelScope
    range: RangeRequest
    uncertainty: FactorUncertaintyModel | None = None
    checks: ModelChecks | None = None
    aggregation: SegmentAggregation | None = None


class ModelComparison(SidecarModel):
    schema_version: Literal[1] = 1
    project_fingerprint: Digest
    label: Text
    left: ModelOutputSpec
    right: ModelOutputSpec
    origin: Origin
    review: Review | None = None
    digest: str
