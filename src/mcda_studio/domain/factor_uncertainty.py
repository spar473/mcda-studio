"""Stated uncertainty on fundamental source factors of a deterministic calculation model.

Separately versioned and bound to both the project and the deterministic model digest. A
distribution never names a formula: derived values are always recalculated from their factors.
Accepting a factor value and accepting its distribution are separate judgements. See
``docs/design/derived-uncertainty-verification-plan.md``.
"""

from typing import Annotated, Literal

from pydantic import Field

from mcda_studio.domain.common import DomainModel
from mcda_studio.domain.derived import Symbol
from mcda_studio.domain.evidence import Origin, Review
from mcda_studio.domain.uncertainty import (
    DiscreteDistribution,
    TriangularDistribution,
    UniformDistribution,
)

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
FactorDistributionKind = Annotated[
    UniformDistribution | TriangularDistribution | DiscreteDistribution,
    Field(discriminator="kind"),
]


class FactorDistribution(DomainModel):
    """One factor's marginal, in the factor's own unit; no conversion or inference."""

    factor_id: Symbol
    distribution: FactorDistributionKind
    origin: Origin
    review: Review | None = None


class QuantileGroup(DomainModel):
    """Factors that share one uniform draw through their own quantile functions.

    This states perfectly shared quantiles, not a correlation coefficient or covariance."""

    id: Symbol
    factor_ids: list[Symbol] = Field(min_length=2, max_length=64)
    rationale: str = Field(min_length=1, max_length=2000)
    origin: Origin
    review: Review | None = None


class FactorUncertaintyModel(DomainModel):
    schema_version: Literal[1] = 1
    project_fingerprint: Digest
    # The deterministic preview's model digest: any change to factors or formulas unbinds it.
    model_digest: Digest
    distributions: list[FactorDistribution] = Field(default_factory=list, max_length=256)
    groups: list[QuantileGroup] = Field(default_factory=list, max_length=64)
