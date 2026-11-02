"""Completed analysis envelopes; none of these fields are persisted in the project file.

Version 1 records and exports hold MAVT data only, byte for byte as before the method track.
Every other method has a version-2 record: a common envelope plus its own result and context.
"""

from typing import Annotated, Any, Literal

from pydantic import Discriminator, Field, Tag

from mcda_studio.domain.common import DomainModel, Id, Issue
from mcda_studio.domain.criteria import ValueFunctionSpec
from mcda_studio.domain.measurements import Domain
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import (
    AhpResult,
    MavtResult,
    MavtSortingResult,
    PrometheeResult,
    ScenarioComparison,
    SmaaResult,
)
from mcda_studio.domain.scales import Scale

DominanceRelation = Literal[
    "same_alternative", "dominates", "dominated_by", "equal", "incomparable", "not_checked"
]
ExportTable = Literal[
    "ranking",
    "contributions",
    "partial_values",
    "comparison",
    "dominance",
    "classes",
    "rank_acceptability",
    "class_acceptability",
    "inputs_to_check",
    "flows",
    "criterion_flows",
    "partial_order",
    "explanation",
    "priorities",
    "criterion_priorities",
    "local_priorities",
    "consistency",
]


class CriterionContext(DomainModel):
    criterion_id: Id
    name: str
    description: str
    path_ids: list[Id]
    path_names: list[str]
    scale: Scale
    value_function: ValueFunctionSpec
    function_source: Literal["base", "scenario_override"]
    resolved_domain: Domain | None


class AnalysisRecord(DomainModel):
    record_version: Literal["1"] = "1"
    record_digest: str
    project_title: str
    scenario_name: str
    resolved_profile_name: str
    calculation_path: Literal["mavt.math_fsum.v1"] = "mavt.math_fsum.v1"
    comparison_calculation_path: Literal["mavt.math_fsum.v1"] = "mavt.math_fsum.v1"
    numerical_tolerance: float
    csv_text_policy: Literal["text-prefix-controls-v1"] = "text-prefix-controls-v1"
    alternative_order: list[Id]
    criteria: list[CriterionContext]
    path_shares: dict[Id, float]
    contribution_totals: dict[Id, float]
    dominance_enabled: bool
    dominance_relations: dict[Id, dict[Id, DominanceRelation]]
    result: MavtResult
    comparison: ScenarioComparison | None
    comparison_diagnostics: list[Issue] = Field(default_factory=list)


class RecordEnvelopeV2(DomainModel):
    """The part every version-2 record shares; each method adds its result and context."""

    record_version: Literal["2"] = "2"
    record_digest: str
    method: str
    method_label: str
    calculation_path: str
    numerical_tolerance: float
    csv_text_policy: Literal["text-prefix-controls-v1"] = "text-prefix-controls-v1"
    project_title: str
    scenario_name: str
    resolved_profile_name: str
    alternative_order: list[Id]
    configuration: AnalysisConfiguration


class SortingAnalysisRecord(RecordEnvelopeV2):
    """Value-based sorting: the sorted result and the value-model context its MAVT panels read."""

    method: Literal["mavt_sorting"] = "mavt_sorting"
    calculation_path: Literal["mavt_sorting.math_fsum.v1"] = "mavt_sorting.math_fsum.v1"
    comparison_calculation_path: Literal["mavt.math_fsum.v1"] = "mavt.math_fsum.v1"
    criteria: list[CriterionContext]
    path_shares: dict[Id, float]
    contribution_totals: dict[Id, float]
    dominance_enabled: bool
    dominance_relations: dict[Id, dict[Id, DominanceRelation]]
    result: MavtSortingResult
    comparison: ScenarioComparison | None
    comparison_diagnostics: list[Issue] = Field(default_factory=list)


class SmaaAnalysisRecord(RecordEnvelopeV2):
    """SMAA-2: the acceptabilities with their full provenance; no value-model context."""

    method: Literal["smaa2"] = "smaa2"
    calculation_path: Literal["smaa2.pcg64.v1"] = "smaa2.pcg64.v1"
    result: SmaaResult


class PrometheeAnalysisRecord(RecordEnvelopeV2):
    """PROMETHEE II: the flows, the partial order and the explanation; no value-model context."""

    method: Literal["promethee2"] = "promethee2"
    calculation_path: Literal["promethee2.v1"] = "promethee2.v1"
    result: PrometheeResult


class AhpAnalysisRecord(RecordEnvelopeV2):
    """AHP: the priorities and every matrix's consistency; no value-model context."""

    method: Literal["ahp"] = "ahp"
    calculation_path: Literal["ahp.eigen_power.v1"] = "ahp.eigen_power.v1"
    result: AhpResult


#: Version-2 records, by method.
VersionTwoRecord = Annotated[
    SortingAnalysisRecord | SmaaAnalysisRecord | PrometheeAnalysisRecord | AhpAnalysisRecord,
    Field(discriminator="method"),
]


def _record_kind(value: Any) -> str:
    """Version 1 is MAVT; a version-2 record is told apart by its method."""
    if isinstance(value, dict):
        version, method = value.get("record_version"), value.get("method")
    else:
        version, method = getattr(value, "record_version", None), getattr(value, "method", None)
    return "1" if version == "1" else str(method)


#: Any completed record: version 1 (MAVT) or a method's version-2 record.
AnyAnalysisRecord = Annotated[
    Annotated[AnalysisRecord, Tag("1")]
    | Annotated[SortingAnalysisRecord, Tag("mavt_sorting")]
    | Annotated[SmaaAnalysisRecord, Tag("smaa2")]
    | Annotated[PrometheeAnalysisRecord, Tag("promethee2")]
    | Annotated[AhpAnalysisRecord, Tag("ahp")],
    Discriminator(_record_kind),
]


class AnalysisPresentation(DomainModel):
    sort: Literal["rank", "project"] = "rank"
    hidden_alternative_ids: list[Id] = Field(default_factory=list, max_length=100)
    hidden_criterion_ids: list[Id] = Field(default_factory=list, max_length=100)
    precision: Literal["4", "full"] = "4"


class AnalysisExportDocument(DomainModel):
    export_version: Literal["1"] = "1"
    data_scope: Literal["complete_model; visibility_is_presentation_only"] = (
        "complete_model; visibility_is_presentation_only"
    )
    record: AnalysisRecord
    source_project: Project
    presentation: AnalysisPresentation


class AnalysisExportDocumentV2(DomainModel):
    """A version-2 record with its source project; a version-1 export is MAVT by definition."""

    export_version: Literal["2"] = "2"
    data_scope: Literal["complete_model; visibility_is_presentation_only"] = (
        "complete_model; visibility_is_presentation_only"
    )
    record: VersionTwoRecord
    source_project: Project
    presentation: AnalysisPresentation


AnyAnalysisExportDocument = Annotated[
    AnalysisExportDocument | AnalysisExportDocumentV2, Field(discriminator="export_version")
]
