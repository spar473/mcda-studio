import { useCallback, useMemo } from "react";
import { api } from "../api/client";
import type { AnalysisConfiguration, Project, ValueFunctionCandidate } from "../api/types";
import { analysisKey, canonical, type AnalysisContext } from "./analysisContext";
import { useAnalysisRequest } from "./useAnalysisRequest";

/** Compare caller-provided fields without recreating the server's schema defaults. */
export function providedFieldsMatch(expected: unknown, actual: unknown): boolean {
  if (expected === null || typeof expected !== "object") return canonical(expected) === canonical(actual);
  if (Array.isArray(expected)) return Array.isArray(actual) && expected.length === actual.length &&
    expected.every((value: unknown, i) => providedFieldsMatch(value, actual[i]));
  if (actual === null || typeof actual !== "object") return false;
  const received = actual as Record<string, unknown>;
  return Object.entries(expected).every(([field, value]: [string, unknown]) => providedFieldsMatch(value, received[field]));
}

/** Methods built on the MAVT model; their previews use the viewed configuration. */
const VALUE_MODEL_METHODS = new Set(["mavt", "mavt_sorting", "smaa2"]);

/** The MAVT editors edit the MAVT model whatever method is viewed. While a method that does not read
 * it (PROMETHEE II) is viewed, their previews are requested for `mavt` with the same profile and
 * scenario; the preview routes still refuse that method itself. */
export function previewContext(context: AnalysisContext): AnalysisContext {
  if (VALUE_MODEL_METHODS.has(context.configuration.method)) return context;
  return { ...context, method: "mavt", parameters: null, configuration: { ...context.configuration, method: "mavt", parameters: {} } };
}

function verify(result: { project_fingerprint: string; configuration: AnalysisConfiguration;
  weight_profile_id: string | null; scenario_id: string | null }, context: AnalysisContext, requireProfile = true): void {
  if (result.project_fingerprint !== context.fingerprint || result.scenario_id !== context.scenarioId ||
      requireProfile && result.weight_profile_id !== context.resolvedProfileId || canonical(result.configuration) !== canonical(context.configuration)) {
    throw new Error("Preview response does not match the selected revision and configuration.");
  }
}

export function useWeightPreview(project: Project, viewed: AnalysisContext) {
  const context = useMemo(() => previewContext(viewed), [viewed]);
  const key = analysisKey(context, "weights-preview");
  const load = useCallback(async (signal: AbortSignal) => {
    const result = await api.previewWeights(project, context.configuration, signal);
    verify(result, context); return result;
  }, [project, context]);
  return useAnalysisRequest(key, true, load);
}

/** Weights for structural views (canvas, presentation). The key leaves out the selected criterion,
 * so selecting or collapsing nodes never re-requests them; edits and context changes do. */
export function useStructureWeights(project: Project, viewed: AnalysisContext, enabled: boolean) {
  const context = useMemo(() => previewContext(viewed), [viewed]);
  const key = analysisKey({ ...context, criterionId: null }, "weights-preview");
  const structural = useMemo(() => ({ ...context, criterionId: null }), [key]); // eslint-disable-line react-hooks/exhaustive-deps
  const load = useCallback(async (signal: AbortSignal) => {
    const result = await api.previewWeights(project, structural.configuration, signal);
    verify(result, structural); return result;
  }, [project, structural]);
  return useAnalysisRequest(key, enabled, load);
}

/** A candidate is a transient read-only request, never an editor operation or a saved Project. */
export function useValueFunctionPreview(project: Project, viewed: AnalysisContext, candidate?: ValueFunctionCandidate, enabled = true) {
  const context = useMemo(() => previewContext(viewed), [viewed]);
  const key = analysisKey(context, "value-function-preview", candidate ?? null);
  const load = useCallback(async (signal: AbortSignal) => {
    if (!context.criterionId) throw new Error("Select a criterion first.");
    const result = await api.previewValueFunction({ project, criterion_id: context.criterionId,
      configuration: context.configuration, candidate, sample_count: 501 }, signal);
    verify(result, context, false);
    if (result.criterion_id !== context.criterionId || (candidate ? !providedFieldsMatch(candidate, result.candidate) : result.candidate !== null)) {
      throw new Error("Preview response does not match the selected criterion and pending candidate.");
    }
    return result;
  }, [project, context, candidate]);
  return useAnalysisRequest(key, enabled && context.criterionId !== null, load);
}
