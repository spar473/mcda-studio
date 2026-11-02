// Friendly aliases over the generated schema. The Python models are the source of truth;
// `schema.ts` is generated from docs/api/openapi.json (npm run gen:types).
import type { components } from "./schema";

type S = components["schemas"];

export type Project = S["Project-Output"];
export type Alternative = S["Alternative-Output"];
export type CriterionNode = S["CriterionNode-Output"];
export type Scale = S["Scale-Output"];
export type ScaleType = S["ScaleType"];
export type AnchorMode = S["AnchorMode"];
export type Direction = S["Direction"];
export type ControlPoint = S["ControlPoint"];
export type Performance = S["Performance"];
export type WeightProfile = S["WeightProfile-Output"];
export type Scenario = S["Scenario-Output"];
export type ValueFunction = NonNullable<CriterionNode["value_function"]>;
export type ValueFunctionKind = ValueFunction["kind"];
export type LinearVF = S["LinearValueFunction-Output"];
export type PiecewiseVF = S["PiecewiseLinearValueFunction-Output"];
export type QualitativeVF = S["QualitativeValueFunction-Output"];
export type DirectRatingVF = S["DirectRatingValueFunction-Output"];
export type Measurement = number | string;

export type Operation = S["EditRequest"]["operations"][number];
export type Issue = S["Issue-Output"];
export type ValidationReport = S["ValidationReport"];
export type ProjectDocument = S["ProjectDocument"];
export type ImportedProjectDocument = S["ImportedProjectDocument"];
export type ProjectSummary = S["ProjectSummary"];
export type ProjectList = S["ProjectList"];
export type CreateProjectRequest = S["CreateProjectRequest"];
export type Meta = S["Meta"];
export type ExampleInfo = S["ExampleInfo"];
export type TemplateInfo = S["TemplateInfo"];
export type AnalysisConfiguration = S["AnalysisConfiguration-Output"];
export type MavtResult = S["MavtResult"];
export type MavtSortingResult = S["MavtSortingResult"];
export type SmaaResult = S["SmaaResult"];
export type PrometheeResult = S["PrometheeResult"];
export type AhpResult = S["AhpResult"];
/** Every result the API can return, tagged by `method`. */
export type AnyResult = MavtResult | MavtSortingResult | SmaaResult | PrometheeResult | AhpResult;
export type AcceptabilityEstimate = S["AcceptabilityEstimate"];
export type AlternativeAcceptability = S["AlternativeAcceptability"];
export type InputToCheck = S["InputToCheck"];
export type SmaaModel = S["SmaaModel-Output"];
export type CellUncertainty = S["CellUncertainty-Output"];
export type GroupUncertainty = S["GroupUncertainty-Output"];
export type SharedDraw = S["SharedDraw"];
export type Distribution = CellUncertainty["distribution"];
export type PrometheeModel = S["PrometheeModel-Output"];
export type PrometheeCriterion = S["PrometheeCriterion-Output"];
export type PreferenceFunction = PrometheeCriterion["function"];
export type AlternativeFlows = S["AlternativeFlows"];
export type PartialOrderPair = S["PartialOrderPair"];
export type OutrankingExplanation = S["OutrankingExplanation"];
export type PairExplanation = S["PairExplanation"];
export type CriterionExplanation = S["CriterionExplanation"];
export type AhpModel = S["AhpModel-Output"];
export type PairwiseJudgement = S["PairwiseJudgement"];
export type AhpMatrixResult = S["AhpMatrixResult"];
export type AhpMatrixAnalysis = S["AhpMatrixAnalysis"];
export type AhpMatrixPreview = S["AhpMatrixPreview"];
export type AhpTriad = S["AhpTriad"];
export type MethodComparison = S["MethodComparison"];
export type Requirement = NonNullable<Project["requirements"]>[number];
export type BoundRequirement = Extract<Requirement, { kind: "bound" }>;
export type LabelsRequirement = Extract<Requirement, { kind: "labels" }>;
export type FeasibilityResult = S["FeasibilityResult"];
export type QuestionsResult = S["QuestionsResult"];
export type FactorRunParameters = S["FactorRunParameters-Input"];
export type FactorRunRecord = S["FactorRunRecord"];
export type FactorUncertaintyModel = S["FactorUncertaintyModel-Output"];
export type FactorInspection = S["FactorInspection"];
export type DerivedPreview = S["DerivedPreview-Output"];
export type DerivedCompilation = S["DerivedCompilation-Output"];
export type CalculationInspection = S["CalculationInspection"];
export type CalculationWorkspace = CalculationInspection["workspace"];
export type CalculationApplication = S["CalculationApplication"];
export type CalculationEvent = S["DefineUnit-Input"] | S["DefineSource-Input"] | S["DefineFormula-Input"]
  | S["ReviewEntry-Input"] | S["RemoveEntry-Input"] | S["Rebind-Input"];
export type CalculationAssignment = S["Assignment"];
export type SourceFactorInput = S["SourceFactor-Input"];
export type DerivedFormulaInput = S["DerivedFormula-Input"];
export type EvidenceInspection = S["EvidenceInspection"];
export type EvidenceWorkspace = EvidenceInspection["workspace"];
export type EvidenceDossier = EvidenceInspection["dossier"];
export type ClaimReview = S["ClaimReview-Input"];
export type EvidenceCompilation = S["EvidenceCompilation-Output"];
export type EvidenceCompilationInspection = S["EvidenceCompilationInspection"];
export type ProjectCopyReceipt = S["ProjectCopyReceipt-Output"];
export type ArtifactBinding = S["ArtifactBinding"];
export type DecisionDetails = S["DecisionDetails-Input"];
export type DecisionRecordV2 = S["DecisionRecordV2"];
export type DecisionRecordV1 = S["DecisionRecord"];
export type DecisionRecordInspection = S["DecisionRecordInspection"];
export type AlternativeFeasibility = S["AlternativeFeasibility"];
export type ComparisonColumn = S["ComparisonColumn"];
export type ComparisonCell = S["ComparisonCell"];
export type MethodComparisonExportRequest = S["MethodComparisonExportRequest"];
export type MethodInfo = S["MethodInfo"];
export type Capability = MethodInfo["capabilities"][number];
export type SortingModel = S["SortingModel-Output"];
export type SortingClass = S["SortingClass-Output"];
export type SortingAudit = S["SortingAudit"];
export type ClassBand = S["ClassBand"];
export type ClassSummary = S["ClassSummary"];
export type ClassAssignment = S["ClassAssignment"];
export type AuditSample = S["AuditSample"];
export type ClassChange = S["ClassChange"];
export type AlternativeClassChanges = S["AlternativeClassChanges"];
export type Health = S["Health"];
export type OnConflict = "error" | "new_id";

export type WeightPreview = S["WeightPreview"];
export type ValueFunctionPreview = S["ValueFunctionPreview"];
export type ValueFunctionCandidate = S["ValueFunctionCandidate-Input"];
export type ValueFunctionPreviewRequest = S["ValueFunctionPreviewRequest"];

export type SwingRangePreview = S["SwingRangePreview"];

export type SensitivityResult = S["SensitivityResult"];
export type SensitivityProbe = S["SensitivityProbe"];
export type SortingSensitivityResult = S["SortingSensitivityResult"];
export type SortingSensitivityProbe = S["SortingSensitivityProbe"];
/* A sorting body is the MAVT body plus a method tag and classes. The MAVT bodies carry no tag; the
 * `never` keeps TypeScript from treating a sorting body as an MAVT one (union subtype reduction),
 * so `result.method === "mavt_sorting"` narrows reliably. */
export type AnySensitivityResult = (SensitivityResult & { method?: never }) | SortingSensitivityResult;
export type AnySensitivityProbe = (SensitivityProbe & { method?: never }) | SortingSensitivityProbe;
export type AlternativeProbe = S["AlternativeProbe"];
export type Crossover = S["Crossover"];
export type WinnerChange = S["WinnerChange"];


export type AnalysisValidation = S["AnalysisValidation"];
export type ScenarioComparison = S["ScenarioComparison"];

export type AnalysisRecord = S["AnalysisRecord"];
export type SortingAnalysisRecord = S["SortingAnalysisRecord"];
export type SmaaAnalysisRecord = S["SmaaAnalysisRecord"];
export type PrometheeAnalysisRecord = S["PrometheeAnalysisRecord"];
export type AhpAnalysisRecord = S["AhpAnalysisRecord"];
/** Version 1 is MAVT; version 2 carries every other method's record. */
export type AnyAnalysisRecord = AnalysisRecord | SortingAnalysisRecord | SmaaAnalysisRecord | PrometheeAnalysisRecord | AhpAnalysisRecord;
/** A record of a method built on MAVT values: MAVT itself or value-based sorting. */
export type ValueRecord = AnalysisRecord | SortingAnalysisRecord;
export const isSmaaRecord = (record: AnyAnalysisRecord): record is SmaaAnalysisRecord =>
  record.record_version === "2" && record.method === "smaa2";
export const isPrometheeRecord = (record: AnyAnalysisRecord): record is PrometheeAnalysisRecord =>
  record.record_version === "2" && record.method === "promethee2";
export const isAhpRecord = (record: AnyAnalysisRecord): record is AhpAnalysisRecord =>
  record.record_version === "2" && record.method === "ahp";
export type CriterionContext = S["CriterionContext"];
export type AnalysisPresentation = S["AnalysisPresentation-Output"];
export type AnalysisExportRequest = S["AnalysisExportRequest"];
export type AnalysisExportDocument = S["AnalysisExportDocument"];
export type AnalysisExportDocumentV2 = S["AnalysisExportDocumentV2"];
export type ExportTable = NonNullable<AnalysisExportRequest["table"]>;

export type TrashEntry = S["TrashEntry"];

export type ExternalProposals = S["ExternalProposals-Output"];
export type ProposalIntake = S["ProposalIntake-Output"];
export type ProposalInspection = S["ProposalInspection"];
export type ProposalReview = S["ProposalReview-Output"];
export type ProposalPayload = S["ExternalProposal-Output"]["payload"];
export type ProposalCompilation = S["ProposalCompilation-Output"];
export type ProposalRegistrySupply = S["ProposalRegistrySupply-Output"];

export type StarterTemplate = S["StarterTemplate-Output"];
export type StarterRequest = S["StarterInstantiationRequest-Input"];
export type StarterMaterialization = S["StarterMaterialization-Output"];
export type ModelComparison = S["ModelComparison-Output"];
export type ModelComparisonInspection = S["ModelComparisonInspection"];
export type ModelComparisonCompilation = S["ModelComparisonCompilation"];
export type ModelTargetSelection = S["ModelTargetSelection-Input"];
export type ModelOutputRun = S["ModelOutputRun-Output"];
export type ModelOutputSpec = S["ModelOutputSpec-Output"];
export type ModelChecks = S["ModelChecks-Output"];
export type CheckedFactorRun = S["CheckedFactorRun"];

export type ProxyPlanState = S["ProxyPlanState-Output"];
export type ProxyCriterionPlan = S["ProxyCriterionPlan-Output"];
export type ProxyOperation = S["ProxyOperation-Input"];
export type ProxyInputs = S["ProxyInputs-Output"];
export type ProxyInspection = S["ProxyInspection"];
export type ProxyPairRequest = S["ProxyPairRequest-Input"];
export type ProxyComparisonBundle = S["ProxyComparisonBundle"];
