import type { ProxyPlanState, ProxyCriterionPlan, ProxyOperation, ProxyInputs, ProxyInspection, ProxyPairRequest, ProxyComparisonBundle } from "./types";
import type { StarterTemplate, StarterRequest, StarterMaterialization, ModelComparison, ModelComparisonInspection, ModelTargetSelection, ModelComparisonCompilation, ModelOutputSpec, ModelOutputRun, CheckedFactorRun } from "./types";
import type { ExternalProposals, ProposalInspection, ProposalReview, ProposalCompilation, ProposalRegistrySupply } from "./types";
import type { DecisionDetails as FactorDecision, FactorInspection, FactorRunParameters, FactorRunRecord } from "./types";
import type {
  AhpMatrixPreview, PairwiseJudgement, MethodComparison, MethodComparisonExportRequest, FeasibilityResult, QuestionsResult, DerivedPreview,
  EvidenceInspection, EvidenceWorkspace, ClaimReview, DerivedCompilation,
  CalculationInspection, CalculationWorkspace, CalculationApplication, CalculationEvent,
  EvidenceCompilation, EvidenceCompilationInspection, ArtifactBinding, ProjectCopyReceipt, ImportedProjectDocument,
  DecisionDetails, DecisionRecordV2, DecisionRecordInspection,
  AnalysisValidation, ScenarioComparison, AnyAnalysisRecord, AnalysisExportRequest, AnyResult,
  AnySensitivityProbe, AnySensitivityResult,
  AnalysisConfiguration,
  CreateProjectRequest,
  ExampleInfo,
  Health,
  Meta,
  OnConflict,
  Operation,
  Project,
  ProjectDocument,
  ProjectList,
  TemplateInfo,
  TrashEntry,
  WeightPreview,
  ValueFunctionPreview,
  ValueFunctionPreviewRequest,
} from "./types";

export interface ErrorDetail {
  path?: string;
  message?: string;
  code?: string;
  severity?: string;
}

/** The server's standard error body, as an exception. `status` 0 means "never reached it". */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ErrorDetail[];

  constructor(status: number, code: string, message: string, details: ErrorDetail[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

interface ErrorBody {
  error?: { code?: string; message?: string; details?: ErrorDetail[] };
}

async function parseError(response: Response): Promise<ApiError> {
  let body: ErrorBody | undefined;
  try {
    body = (await response.json()) as ErrorBody;
  } catch {
    body = undefined;
  }
  const e = body?.error;
  if (e?.code) {
    return new ApiError(response.status, e.code, e.message ?? e.code, e.details ?? []);
  }
  return new ApiError(
    response.status,
    `HTTP_${String(response.status)}`,
    `The server answered ${String(response.status)} ${response.statusText}`.trim(),
  );
}

async function request<T>(
  method: string,
  url: string,
  options: { body?: unknown; headers?: Record<string, string>; signal?: AbortSignal } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
  const init: RequestInit = { method, headers, signal: options.signal };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new ApiError(
      0,
      "NETWORK",
      "Cannot reach the MCDA Studio server. Is `mcda serve` still running?",
    );
  }
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const enc = encodeURIComponent;

export const api = {
  startProxy: (state: ProxyPlanState) => request<ProxyCriterionPlan>("POST", "/api/proxy/start", { body: state }),
  reviseProxy: (plan: ProxyCriterionPlan, operation: ProxyOperation) => request<ProxyCriterionPlan>("POST", "/api/proxy/revise", { body: { plan, operation, expected_digest: plan.digest } }),
  inspectProxy: (inputs: ProxyInputs) => request<ProxyInspection>("POST", "/api/proxy/preview-pair", { body: inputs }),
  runProxy: (inputs: ProxyPairRequest) => request<ProxyComparisonBundle>("POST", "/api/proxy/run-pair", { body: inputs }),
  verifyProxy: (document: unknown) => request<ProxyComparisonBundle>("POST", "/api/proxy/verify", { body: { document } }),

  starterTemplates: () => request<StarterTemplate[]>("GET", "/api/starter-templates"),
  instantiateStarter: (body: StarterRequest) => request<StarterMaterialization>("POST", "/api/starter-templates/instantiate", { body }),
  verifyStarter: (body: unknown) => request<StarterMaterialization>("POST", "/api/starter-templates/verify", { body }),
  archiveStarter: async (body: StarterMaterialization) => {
    const response = await fetch("/api/starter-templates/archive", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!response.ok) throw await parseError(response);
    return response.blob();
  },
  draftModelComparison: (project: Project, comparison: unknown) => request<ModelComparison>("POST", "/api/model-comparisons/draft", { body: { project, comparison } }),
  reviewModelInput: (project: Project, comparison: ModelComparison, side: "left" | "right", kind: string, id: string, review: unknown, expectedReviewDigest: string) => request<ModelComparisonInspection>("POST", "/api/model-comparisons/review-input", { body: { project, comparison, side, kind, id, review, expected_review_digest: expectedReviewDigest } }),
  inspectModels: (project: Project, comparison: unknown, signal?: AbortSignal) => request<ModelComparisonInspection>("POST", "/api/model-comparisons/inspect", { body: { project, comparison }, signal }),
  reviewModels: (project: Project, comparison: ModelComparison, review: unknown, expectedReviewDigest: string) => request<ModelComparisonInspection>("POST", "/api/model-comparisons/review", { body: { project, comparison, review, expected_review_digest: expectedReviewDigest } }),
  compileModels: (project: Project, comparison: ModelComparison, selection: ModelTargetSelection, expectedReviewDigest: string) => request<ModelComparisonCompilation>("POST", "/api/model-comparisons/compile", { body: { project, comparison, selection, expected_review_digest: expectedReviewDigest } }),
  verifyModels: (document: unknown) => request<ModelComparisonCompilation>("POST", "/api/model-comparisons/verify", { body: { document } }),
  runModelOutput: (project: Project, specification: ModelOutputSpec) => request<ModelOutputRun>("POST", "/api/model-outputs/run", { body: { project, specification } }),
  runCheckedFactors: (body: unknown) => request<CheckedFactorRun>("POST", "/api/checked-factor-runs/run", { body }),
  verifyCheckedFactors: (document: unknown) => request<CheckedFactorRun>("POST", "/api/checked-factor-runs/verify", { body: { document } }),

  importProposals: (project: Project, text: string, format: "json" | "csv", registriesText: string | null = null) =>
    request<ProposalInspection>("POST", "/api/proposals/import", { body: { project, text, format, registries_text: registriesText } }),
  inspectProposals: (project: Project, workspace: ExternalProposals, comparisonTarget: string | null = null, signal?: AbortSignal) =>
    request<ProposalInspection>("POST", "/api/proposals/inspect", { body: { project, workspace, comparison_target: comparisonTarget }, signal }),
  reviewProposals: (project: Project, workspace: ExternalProposals, events: ProposalReview[], reviewDigest: string, bulk: boolean, comparisonTarget: string | null) =>
    request<ProposalInspection>("POST", "/api/proposals/review", { body: { project, workspace, events, expected_review_digest: reviewDigest, expected_workspace_digest: workspace.digest, bulk, comparison_target: comparisonTarget } }),
  compileProposals: (project: Project, workspace: ExternalProposals, reviewDigest: string, comparisonTarget: string | null) =>
    request<ProposalCompilation>("POST", "/api/proposals/compile", { body: { project, workspace, expected_review_digest: reviewDigest, expected_workspace_digest: workspace.digest, comparison_target: comparisonTarget } }),
  verifyProposals: (bundle: unknown) => request<ProposalCompilation>("POST", "/api/proposals/verify", { body: bundle }),
  supplyProposalRegistries: (project: Project, workspace: ExternalProposals, supply: ProposalRegistrySupply) =>
    request<ProposalInspection>("POST", "/api/proposals/registries", { body: { project, workspace, supply, expected_workspace_digest: workspace.digest } }),

  inspectEvidence: (project: Project, document: unknown, signal?: AbortSignal) =>
    request<EvidenceInspection>("POST", "/api/evidence/inspect", { body: { project, document }, signal }),
  reviewEvidence: (project: Project, workspace: EvidenceWorkspace, event: ClaimReview, expectedReviewDigest: string, signal?: AbortSignal) =>
    request<EvidenceInspection>("POST", "/api/evidence/review", { body: { project, workspace, event, expected_review_digest: expectedReviewDigest }, signal }),
  compileEvidence: (project: Project, workspace: EvidenceWorkspace, expectedReviewDigest: string, expectedWorkspaceDigest: string, signal?: AbortSignal) =>
    request<EvidenceCompilation>("POST", "/api/evidence/compile", { body: { project, workspace, expected_review_digest: expectedReviewDigest, expected_workspace_digest: expectedWorkspaceDigest }, signal }),
  inspectEvidenceCompilation: (project: Project, bundle: unknown, signal?: AbortSignal) =>
    request<EvidenceCompilationInspection>("POST", "/api/evidence/compilation/inspect", { body: { project, bundle }, signal }),
  bindArtifact: (project: Project, artifact: unknown, copyReceipt: ProjectCopyReceipt | null, signal?: AbortSignal) =>
    request<ArtifactBinding>("POST", "/api/provenance/binding", { body: { project, artifact, copy_receipt: copyReceipt }, signal }),
  previewDecision: (project: Project, details: DecisionDetails, artifacts: { artifact: unknown; copy_receipt: unknown }[], predecessor: unknown, signal?: AbortSignal) =>
    request<DecisionRecordV2>("POST", "/api/decisions/preview", { body: { project, details, artifacts, predecessor }, signal }),
  inspectDecision: (project: Project, record: unknown, predecessor: unknown, signal?: AbortSignal) =>
    request<DecisionRecordInspection>("POST", "/api/decisions/inspect", { body: { project, record, predecessor }, signal }),
  inspectFactorUncertainty: (project: Project, model: DerivedPreview["model"], uncertainty: unknown) =>
    request<FactorInspection>("POST", "/api/factor-uncertainty/inspect", { body: { project, model, uncertainty } }),
  runFactorUncertainty: (project: Project, model: DerivedPreview["model"], uncertainty: unknown, parameters: FactorRunParameters, decision: FactorDecision | null) =>
    request<FactorRunRecord>("POST", "/api/factor-uncertainty/run", { body: { project, model, uncertainty, parameters, decision } }),
  verifyFactorRun: (record: unknown) =>
    request<FactorRunRecord>("POST", "/api/factor-uncertainty/verify", { body: { record } }),
  inspectCalculations: (project: Project, document: unknown, signal?: AbortSignal) =>
    request<CalculationInspection>("POST", "/api/calculations/inspect", { body: { project, document }, signal }),
  proposeCalculation: (project: Project, workspace: CalculationWorkspace, event: CalculationEvent, expectedReviewDigest: string, signal?: AbortSignal) =>
    request<CalculationInspection>("POST", "/api/calculations/propose", { body: { project, workspace, event, expected_review_digest: expectedReviewDigest }, signal }),
  applyCalculation: (project: Project, workspace: CalculationWorkspace, expectedReviewDigest: string, recordedBy: string, recordedAt: string, signal?: AbortSignal) =>
    request<CalculationApplication>("POST", "/api/calculations/apply", { body: { project, workspace, expected_review_digest: expectedReviewDigest, recorded_by: recordedBy, recorded_at: recordedAt }, signal }),
  previewDerived: (project: Project, model: unknown, signal?: AbortSignal) =>
    request<DerivedPreview>("POST", "/api/derived/preview", { body: { project, model }, signal }),
  compileDerived: (project: Project, model: DerivedPreview["model"], expectedReviewDigest: string, signal?: AbortSignal) =>
    request<DerivedCompilation>("POST", "/api/derived/compile", { body: { project, model, expected_review_digest: expectedReviewDigest }, signal }),
  openQuestions: (project: Project, configuration: AnalysisConfiguration, signal?: AbortSignal, dossier?: unknown, factorRecord?: unknown, proposals?: unknown, modelComparison?: unknown, proxy?: unknown) =>
    request<QuestionsResult>("POST", "/api/open-questions", { body: { project, configuration, dossier, factor_record: factorRecord, proposals, model_comparison: modelComparison, proxy }, signal }),
  health: () => request<Health>("GET", "/api/health"),
  meta: () => request<Meta>("GET", "/api/meta"),
  templates: () => request<TemplateInfo[]>("GET", "/api/templates"),
  examples: () => request<ExampleInfo[]>("GET", "/api/examples"),
  listProjects: () => request<ProjectList>("GET", "/api/projects"),
  listTrash: () => request<TrashEntry[]>("GET", "/api/trash"),
  restoreProject: (entry: string, asCopy = false) =>
    request<ProjectDocument>("POST", `/api/trash/${enc(entry)}/restore`, { body: { as_copy: asCopy } }),
  createProject: (body: CreateProjectRequest) =>
    request<ProjectDocument>("POST", "/api/projects", { body }),
  importProject: (raw: unknown, onConflict: OnConflict = "error") =>
    request<ImportedProjectDocument>("POST", `/api/projects/import?on_conflict=${onConflict}`, {
      body: raw,
    }),
  importExample: (name: string, onConflict: OnConflict = "error") =>
    request<ProjectDocument>("POST", `/api/examples/${enc(name)}/import?on_conflict=${onConflict}`),
  getProject: (id: string) => request<ProjectDocument>("GET", `/api/projects/${enc(id)}`),
  saveProject: (project: Project, ifMatch: string) =>
    request<ProjectDocument>("PUT", `/api/projects/${enc(project.id)}`, {
      body: project,
      headers: { "If-Match": `"${ifMatch}"` },
    }),
  deleteProject: (id: string) => request<undefined>("DELETE", `/api/projects/${enc(id)}`),
  duplicateProject: (id: string, title?: string) =>
    request<ProjectDocument>("POST", `/api/projects/${enc(id)}/duplicate`, {
      body: title ? { title } : {},
    }),
  edit: (project: Project, operations: Operation[]) =>
    request<ProjectDocument>("POST", "/api/edit", { body: { project, operations } }),
  evaluate: (project: Project, configuration?: AnalysisConfiguration, signal?: AbortSignal) =>
    request<AnyResult>("POST", "/api/evaluate", { body: { project, configuration }, signal }),
  previewWeights: (project: Project, configuration: AnalysisConfiguration, signal?: AbortSignal) =>
    request<WeightPreview>("POST", "/api/weights/preview", { body: { project, configuration }, signal }),
  previewValueFunction: (body: ValueFunctionPreviewRequest, signal?: AbortSignal) =>
    request<ValueFunctionPreview>("POST", "/api/value-functions/preview", { body, signal }),
  sensitivity: (project: Project, node_id: string, configuration: AnalysisConfiguration, steps: number, signal?: AbortSignal) =>
    request<AnySensitivityResult>("POST", "/api/sensitivity", { body: { project, node_id, configuration, steps }, signal }),
  // Read-only: a probe is a what-if lookup, never an edit. It must not be sent through api.edit.
  sensitivityProbe: (project: Project, node_id: string, weight: number, configuration: AnalysisConfiguration, signal?: AbortSignal) =>
    request<AnySensitivityProbe>("POST", "/api/sensitivity/probe", { body: { project, node_id, weight, configuration }, signal }),
  // Read-only: one drafted AHP matrix's priorities and consistency, computed in Python.
  previewAhpMatrix: (items: string[], judgements: PairwiseJudgement[], signal?: AbortSignal) =>
    request<AhpMatrixPreview>("POST", "/api/ahp/preview", { body: { items, judgements }, signal }),
  validateAnalysis: (project: Project, configuration: AnalysisConfiguration, signal?: AbortSignal) =>
    request<AnalysisValidation>("POST", "/api/analysis/validate", { body: { project, configuration }, signal }),
  compareScenarios: (project: Project, scenario_ids: string[], configuration: AnalysisConfiguration, signal?: AbortSignal) =>
    request<ScenarioComparison>("POST", "/api/scenarios/compare", { body: { project, scenario_ids, configuration }, signal }),
  analysisRecord: (project: Project, configuration: AnalysisConfiguration, signal?: AbortSignal) =>
    request<AnyAnalysisRecord>("POST", "/api/analysis/record", { body: { project, configuration }, signal }),
  exportAnalysis: async (body: AnalysisExportRequest, signal?: AbortSignal) => {
    const response = await fetch("/api/analysis/export", { method: "POST", signal,
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!response.ok) throw await parseError(response);
    if (response.headers.get("X-Analysis-Record-Digest") !== body.expected_record_digest ||
        response.headers.get("X-Project-Fingerprint") !== body.expected_project_fingerprint)
      throw new ApiError(0, "EXPORT_CONTEXT", "Download does not match the completed analysis record.");
    const media = response.headers.get("Content-Type") ?? "";
    if (!media.startsWith(body.format === "csv" ? "text/csv" : "application/json"))
      throw new ApiError(0, "EXPORT_FORMAT", "The server returned an unexpected download format.");
    const filename = /filename="([^"/\\]+)"/.exec(response.headers.get("Content-Disposition") ?? "")?.[1];
    if (!filename) throw new ApiError(0, "EXPORT_FILENAME", "The server did not identify the download file.");
    return { blob: await response.blob(), filename };
  },
  // Read-only: every method's own reading of the project, side by side.
  compareMethods: (project: Project, configuration: AnalysisConfiguration, signal?: AbortSignal) =>
    request<MethodComparison>("POST", "/api/methods/compare", { body: { project, configuration }, signal }),
  exportComparison: async (body: MethodComparisonExportRequest, signal?: AbortSignal) => {
    const response = await fetch("/api/methods/compare/export", { method: "POST", signal,
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!response.ok) throw await parseError(response);
    if (response.headers.get("X-Project-Fingerprint") !== body.expected_project_fingerprint)
      throw new ApiError(0, "EXPORT_CONTEXT", "Download does not match the displayed comparison.");
    const media = response.headers.get("Content-Type") ?? "";
    if (!media.startsWith(body.format === "csv" ? "text/csv" : "application/json"))
      throw new ApiError(0, "EXPORT_FORMAT", "The server returned an unexpected download format.");
    const filename = /filename="([^"/\\]+)"/.exec(response.headers.get("Content-Disposition") ?? "")?.[1];
    if (!filename) throw new ApiError(0, "EXPORT_FILENAME", "The server did not identify the download file.");
    return { blob: await response.blob(), filename };
  },
  // Read-only: pass, fail or unknown per alternative and requirement, outside every method.
  checkFeasibility: (project: Project, signal?: AbortSignal) =>
    request<FeasibilityResult>("POST", "/api/feasibility", { body: { project }, signal }),
  exportFeasibility: async (body: { project: Project; expected_project_fingerprint: string; format: "json" | "csv" }, signal?: AbortSignal) => {
    const response = await fetch("/api/feasibility/export", { method: "POST", signal,
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!response.ok) throw await parseError(response);
    if (response.headers.get("X-Project-Fingerprint") !== body.expected_project_fingerprint)
      throw new ApiError(0, "EXPORT_CONTEXT", "Download does not match the displayed feasibility check.");
    const filename = /filename="([^"/\\]+)"/.exec(response.headers.get("Content-Disposition") ?? "")?.[1];
    if (!filename) throw new ApiError(0, "EXPORT_FILENAME", "The server did not identify the download file.");
    return { blob: await response.blob(), filename };
  },
  downloadUrl: (id: string) => `/api/projects/${enc(id)}/file`,
};
