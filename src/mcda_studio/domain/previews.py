"""Read-only analytical outputs; none of these fields enter the persisted project schema."""

from typing import Literal

from pydantic import Field

from mcda_studio.domain.common import DomainModel, FiniteFloat, Id, Issue
from mcda_studio.domain.criteria import ValueFunctionSpec
from mcda_studio.domain.measurements import Domain, Measurement
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.results import ClassBand
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.domain.validation import ValidationReport


class ValueFunctionCandidate(DomainModel):
    """Omitted fields inherit; explicit null clears the candidate field, never the project."""

    scale: Scale | None = None
    value_function: ValueFunctionSpec | None = None


class PreviewProvenance(DomainModel):
    project_fingerprint: str
    configuration: AnalysisConfiguration
    weight_profile_id: Id | None
    scenario_id: Id | None


class ValueSample(DomainModel):
    measurement: FiniteFloat | str
    partial_value: FiniteFloat


class MeasurementMarker(DomainModel):
    alternative_id: Id
    raw_measurement: Measurement | None
    partial_value: FiniteFloat | None
    clamped: bool = False


class ValueFunctionPreview(PreviewProvenance):
    criterion_id: Id
    candidate: ValueFunctionCandidate | None
    candidate_fingerprint: str
    effective_scale: Scale | None
    effective_value_function: ValueFunctionSpec | None
    resolved_domain: Domain | None
    readiness: Literal["ready", "incomplete", "invalid"] = "incomplete"
    measurement_readiness: Literal["ready", "incomplete", "invalid"] = "incomplete"
    curve_ready: bool
    measurements_complete: bool
    samples: list[ValueSample] = Field(default_factory=list)
    markers: list[MeasurementMarker] = Field(default_factory=list)
    diagnostics: list[Issue] = Field(default_factory=list)


class SwingRangePreview(DomainModel):
    """Engine-resolved swing endpoints; independent of weight arithmetic/readiness."""

    readiness: Literal["ready", "incomplete", "invalid"]
    scale_type: ScaleType | None
    unit: str | None
    domain: Domain | None
    worst: list[Measurement] = Field(default_factory=list)
    best: list[Measurement] = Field(default_factory=list)
    diagnostics: list[Issue] = Field(default_factory=list)


class WeightPreview(PreviewProvenance):
    weights_ready: bool
    local_weights: dict[Id, FiniteFloat] = Field(default_factory=dict)
    global_weights: dict[Id, FiniteFloat] = Field(default_factory=dict)
    # Derived branch shares for every node, so the GUI can explain a global weight
    # without multiplying local weights itself. Leaf shares equal `global_weights`.
    path_shares: dict[Id, FiniteFloat] = Field(default_factory=dict)
    sibling_rating_totals: dict[str, FiniteFloat | None] = Field(default_factory=dict)
    weight_basis: str
    swing_ranges: dict[Id, SwingRangePreview] = Field(default_factory=dict)
    diagnostics: list[Issue] = Field(default_factory=list)


class AlternativeProbe(DomainModel):
    """One alternative's hypothetical outcome at the probed weight."""

    alternative_id: Id
    name: str
    value: FiniteFloat
    rank: int  # competition rank from the engine (1 = best, ties share a rank)
    baseline_value: FiniteFloat
    baseline_rank: int


class SensitivityProbe(PreviewProvenance):
    """Scores at one hypothetical local weight. Read-only: nothing here is ever persisted.

    The probed weight is a *what-if* preference setting, not a swing judgement and not a saved
    profile. It exists so the GUI can read exact values at an arbitrary point - a crossover, say -
    without interpolating between grid samples or ranking alternatives itself.
    """

    node_id: Id
    node_name: str
    node_path: list[Id]
    weight: FiniteFloat  # the requested local weight, echoed back
    base_weight: FiniteFloat  # the criterion's local weight in the unmodified model
    local_weights: dict[Id, FiniteFloat]  # hypothetical locals for the affected sibling group
    global_weights: dict[Id, FiniteFloat]  # hypothetical global leaf weights
    path_shares: dict[Id, FiniteFloat]  # hypothetical branch shares, engine-derived
    alternatives: list[AlternativeProbe]  # best first, ties in the project's own order
    ranking: list[Id]
    baseline_ranking: list[Id]
    ranking_differs_from_baseline: bool
    winner_differs_from_baseline: bool
    diagnostics: list[Issue] = Field(default_factory=list)


class SortingSensitivityProbe(SensitivityProbe):
    """The probe for value-based sorting: each alternative's class at the probed weight too."""

    method: Literal["mavt_sorting"] = "mavt_sorting"
    boundary_tolerance: float
    classes: list[ClassBand]  # best first
    class_by_alternative: dict[Id, Id]
    baseline_class_by_alternative: dict[Id, Id]


class AnalysisValidation(PreviewProvenance):
    validation: "ValidationReport"
