"""Versioned deterministic calculation sidecar; source proposals require human review."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from mcda_studio.domain.common import DomainModel, FiniteFloat, Id
from mcda_studio.domain.evidence import Origin, Review, Source

Symbol = Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")]
UnitName = Annotated[str, StringConstraints(min_length=1, max_length=64)]
Exponent = Annotated[int, Field(strict=True, ge=-16, le=16)]
Dimension = dict[Id, Exponent]


class SourceFactor(DomainModel):
    id: Symbol
    value: FiniteFloat | None = None
    unit: UnitName
    source: Source
    origin: Origin
    review: Review | None = None


class DerivedFormula(DomainModel):
    id: Symbol
    expression: str = Field(min_length=1, max_length=2000)
    unit: UnitName
    origin: Origin
    review: Review | None = None
    # Both absent means an intermediate formula; both present means a measurement.
    alternative_id: Id | None = None
    criterion_id: Id | None = None


class DerivedModel(DomainModel):
    schema_version: Literal[1] = 1
    project_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    # Unit symbols have explicit dimensions. No implicit scaling or currency conversion.
    # "1" is reserved for dimensionless values and cannot be redefined.
    units: dict[UnitName, Dimension] = Field(default_factory=dict, max_length=128)
    sources: list[SourceFactor] = Field(default_factory=list, max_length=256)
    formulas: list[DerivedFormula] = Field(default_factory=list, max_length=128)
