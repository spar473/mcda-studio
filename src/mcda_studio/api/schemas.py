"""Request/response envelopes. Anything describing the model itself is a domain model."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field

from mcda_studio.api.operations import Operation
from mcda_studio.domain.analysis_record import AnalysisPresentation, ExportTable
from mcda_studio.domain.calculation_workspace import CalculationWorkspace, ProposedEvent
from mcda_studio.domain.common import DomainModel, Id
from mcda_studio.domain.criteria import Direction
from mcda_studio.domain.decision import DecisionDetails, DecisionRecord
from mcda_studio.domain.derived import DerivedModel
from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.evidence_workspace import ClaimReview, EvidenceWorkspace
from mcda_studio.domain.external_proposals import ExternalProposals
from mcda_studio.domain.factor_uncertainty import FactorUncertaintyModel
from mcda_studio.domain.model_comparison import ModelComparison
from mcda_studio.domain.pairwise import PairwiseJudgement
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.previews import ValueFunctionCandidate
from mcda_studio.domain.project import Project
from mcda_studio.domain.provenance import ProjectCopyReceipt
from mcda_studio.domain.scales import AnchorMode, ScaleType
from mcda_studio.domain.validation import ValidationReport
from mcda_studio.methods.base import Capability
from mcda_studio.services.decision_record_service import (
    MAX_ARTIFACTS,
    DecisionRecordV2,
    SupportingArtifact,
)
from mcda_studio.services.derived_service import DerivedCompilation
from mcda_studio.services.evidence_compilation_service import EvidenceCompilation
from mcda_studio.services.factor_analysis_service import FactorRunParameters


class Health(DomainModel):
    status: Literal["ok"] = "ok"
    version: str
    schema_version: int
    methods: list[str]
    store: str
    build: dict[str, str | bool | None]


class ScaleTypeInfo(DomainModel):
    type: ScaleType
    numeric: bool
    labelled: bool
    #: value-function kinds the engine accepts on this scale type, in display order
    allowed_value_functions: list[str]


class MethodInfo(DomainModel):
    """A registered decision method and what it can do (see the method seam design note)."""

    name: str
    label: str
    capabilities: list[Capability]
    export_tables: list[ExportTable]  # the CSV tables its analysis record can fill


class Meta(DomainModel):
    """The engine's own vocabulary, so a client never has to hard-code its rules."""

    scale_types: list[ScaleTypeInfo]
    value_function_kinds: list[str]
    anchor_modes: list[AnchorMode]
    directions: list[Direction]
    out_of_domain_policies: list[str]
    methods: list[MethodInfo]


class ValidationSummary(DomainModel):
    ok: bool
    errors: int
    warnings: int


class ProjectSummary(DomainModel):
    id: Id
    title: str
    description: str
    decision_maker: str
    alternatives: int
    criteria: int  # every node of the tree
    leaves: int
    scenarios: int
    updated_at: datetime
    fingerprint: str
    validation: ValidationSummary


class UnreadableFile(DomainModel):
    file: str
    error: str


class ProjectList(DomainModel):
    projects: list[ProjectSummary]
    unreadable: list[UnreadableFile]


class ProjectDocument(DomainModel):
    """A project plus the revision token a client must send back (``If-Match``) when saving."""

    project: Project
    fingerprint: str
    updated_at: datetime | None  # None for a draft that is not stored
    validation: ValidationReport


class ImportedProjectDocument(ProjectDocument):
    """A stored import. ``copy_receipt`` records the ID change made to avoid a conflict, so a
    compilation artifact for the original file can still be verified against this copy."""

    copy_receipt: ProjectCopyReceipt | None = None


class CreateProjectRequest(DomainModel):
    title: str = Field(min_length=1)
    description: str = ""
    decision_maker: str = ""
    method: str = "mavt"
    template: str = "blank"


class DuplicateRequest(DomainModel):
    title: str | None = Field(default=None, min_length=1)


class TemplateInfo(DomainModel):
    name: str


class ExampleInfo(DomainModel):
    name: str
    project_id: Id
    title: str
    description: str
    alternatives: int
    criteria: int


OnConflict = Literal["error", "new_id"]


class DraftRequest(DomainModel):
    project: Project


class EditRequest(DomainModel):
    project: Project
    operations: Annotated[list[Operation], Field(min_length=1, max_length=500)]


class AnalysisOptions(DomainModel):
    configuration: AnalysisConfiguration | None = None


class EvaluateDraftRequest(AnalysisOptions):
    project: Project


class OpenQuestionsRequest(EvaluateDraftRequest):
    proposals: ExternalProposals | None = None
    model_comparison: ModelComparison | None = None
    dossier: EvidenceDossier | None = None
    factor_record: dict[str, Any] | None = None

    proxy: dict[str, Any] | None = None


class DerivedPreviewRequest(DomainModel):
    project: Project
    model: DerivedModel | DerivedCompilation


class DerivedCompileRequest(DomainModel):
    project: Project
    model: DerivedModel
    expected_review_digest: str


class CalculationInspectRequest(DomainModel):
    project: Project
    document: DerivedModel | CalculationWorkspace


class CalculationProposeRequest(DomainModel):
    project: Project
    workspace: CalculationWorkspace
    event: ProposedEvent
    expected_review_digest: str


class CalculationApplyRequest(DomainModel):
    project: Project
    workspace: CalculationWorkspace
    expected_review_digest: str
    recorded_by: str = Field(min_length=1, max_length=200)
    recorded_at: datetime


class EvidenceInspectRequest(DomainModel):
    project: Project
    document: EvidenceDossier | EvidenceWorkspace


class EvidenceReviewRequest(DomainModel):
    project: Project
    workspace: EvidenceWorkspace
    event: ClaimReview
    expected_review_digest: str


class EvidenceCompileRequest(DomainModel):
    project: Project
    workspace: EvidenceWorkspace
    expected_review_digest: str
    expected_workspace_digest: str


class EvidenceCompilationInspectRequest(DomainModel):
    project: Project
    bundle: EvidenceCompilation


AnyDecisionRecord = Annotated[DecisionRecord | DecisionRecordV2, Field(discriminator="version")]


class DecisionPreviewRequest(DomainModel):
    """``predecessor`` is a version-1 or version-2 record, validated by the endpoint. Records
    embed complete analysis records, which are response models only in this contract."""

    project: Project
    details: DecisionDetails
    artifacts: list[SupportingArtifact] = Field(default_factory=list, max_length=MAX_ARTIFACTS)
    predecessor: dict[str, Any] | None = None


class DecisionInspectRequest(DomainModel):
    project: Project
    record: dict[str, Any]
    predecessor: dict[str, Any] | None = None


class ArtifactBindingRequest(DomainModel):
    project: Project
    artifact: EvidenceCompilation | DerivedCompilation
    copy_receipt: ProjectCopyReceipt | None = None


class MethodComparisonOptions(AnalysisOptions):
    """The selected profile and scenario, and optionally which methods to compare (all by
    default)."""

    methods: list[str] | None = Field(default=None, max_length=20)


class MethodComparisonRequest(MethodComparisonOptions):
    project: Project


class MethodComparisonExportOptions(MethodComparisonOptions):
    expected_project_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    format: Literal["json", "csv"] = "json"


class MethodComparisonExportRequest(MethodComparisonExportOptions):
    project: Project


class FeasibilityRequest(DomainModel):
    project: Project


class FeasibilityExportOptions(DomainModel):
    expected_project_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    format: Literal["json", "csv"] = "json"


class FeasibilityExportRequest(FeasibilityExportOptions):
    project: Project


class AhpPreviewRequest(DomainModel):
    """One drafted AHP matrix: its items in order and the judgements stated so far."""

    items: list[Id] = Field(max_length=100)
    judgements: list[PairwiseJudgement] = Field(max_length=5000)


class SensitivityOptions(AnalysisOptions):
    node_id: Id
    steps: int = Field(default=101, ge=2, le=1001)


class SensitivityDraftRequest(SensitivityOptions):
    project: Project


class SensitivityProbeOptions(AnalysisOptions):
    node_id: Id
    # A hypothetical local weight. Bounds are enforced here and again in the engine, so a bad
    # value is a 422 rather than an undefined redistribution.
    weight: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)


class SensitivityProbeRequest(SensitivityProbeOptions):
    project: Project


class CompareOptions(AnalysisOptions):
    scenario_ids: list[Id] | None = None


class CompareDraftRequest(CompareOptions):
    project: Project


class ValueFunctionPreviewRequest(EvaluateDraftRequest):
    criterion_id: Id
    candidate: ValueFunctionCandidate | None = None
    sample_count: int = Field(default=101, ge=2, le=501)


class AnalysisExportOptions(AnalysisOptions):
    expected_project_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_record_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    format: Literal["json", "csv"] = "json"
    table: ExportTable = "ranking"
    presentation: AnalysisPresentation = Field(default_factory=AnalysisPresentation)


class AnalysisExportRequest(AnalysisExportOptions):
    project: Project


class TrashEntry(DomainModel):
    entry: str
    project_id: str | None
    title: str | None
    deleted_at: datetime | None
    readable: bool
    conflict: bool
    error: str | None


class RestoreRequest(DomainModel):
    as_copy: bool = False


class FactorInspectRequest(DomainModel):
    project: Project
    model: DerivedModel
    uncertainty: FactorUncertaintyModel


class FactorRunRequest(FactorInspectRequest):
    parameters: FactorRunParameters = Field(default_factory=FactorRunParameters)
    decision: DecisionDetails | None = None


class FactorVerifyRequest(DomainModel):
    record: dict[str, Any]
    replay: bool = False
