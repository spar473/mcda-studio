import { useCallback } from "react";
import { api } from "../api/client";
import type { AnySensitivityProbe, AnySensitivityResult, Project, SensitivityProbe, SensitivityResult } from "../api/types";
import { analysisKey, canonical, type AnalysisContext } from "./analysisContext";
import { useAnalysisRequest } from "./useAnalysisRequest";

/**
 * Sensitivity is read-only exploration. Neither hook sends an edit, so no cursor movement can
 * reach the project; both are keyed on the full context so a response for one profile, scenario,
 * revision or criterion can never be shown under another.
 */

export const SENSITIVITY_STEPS = 101;

/**
 * The sweep. `SensitivityResult` predates the preview provenance envelope and carries no
 * fingerprint, configuration or resolved profile, so there is nothing in the body to re-check
 * beyond the node it reports. Identity therefore rests entirely on the request key, which
 * includes the revision, the whole configuration and the selected criterion — the same gate that
 * `useAnalysisRequest` applies to every other analysis request. The probe below *does* carry
 * provenance and is verified field by field.
 */
export function useSensitivity(project: Project, context: AnalysisContext, nodeId: string | null, enabled = true) {
  const key = analysisKey(context, "sensitivity", nodeId);
  const load = useCallback(async (signal: AbortSignal) => {
    if (!nodeId) throw new Error("Select a criterion first.");
    const result = await api.sensitivity(project, nodeId, context.configuration, SENSITIVITY_STEPS, signal);
    if (result.node_id !== nodeId) {
      throw new Error("Sensitivity response does not match the selected criterion.");
    }
    return result;
  }, [project, context, nodeId]);
  // Explicit: inference would collapse the union to its base, as a sorting body extends the MAVT one.
  return useAnalysisRequest<AnySensitivityResult>(key, enabled && nodeId !== null, load);
}

/**
 * One hypothetical weight. The response is checked against the live context before it is shown:
 * revision, complete configuration, resolved scenario, resolved *profile* and the echoed node and
 * weight. The resolved profile is checked separately from the configuration because under
 * automatic resolution the configuration can match while the engine resolves a different profile.
 */
export function useSensitivityProbe(
  project: Project, context: AnalysisContext, nodeId: string | null, weight: number | null, enabled = true,
) {
  const key = analysisKey(context, "sensitivity-probe", { nodeId, weight });
  const load = useCallback(async (signal: AbortSignal) => {
    if (!nodeId || weight === null) throw new Error("Select a criterion and a weight first.");
    const result = await api.sensitivityProbe(project, nodeId, weight, context.configuration, signal);
    if (result.project_fingerprint !== context.fingerprint ||
        result.scenario_id !== context.scenarioId ||
        result.weight_profile_id !== context.resolvedProfileId ||
        canonical(result.configuration) !== canonical(context.configuration) ||
        result.node_id !== nodeId || result.weight !== weight) {
      throw new Error("Probe response does not match the selected revision, configuration and weight.");
    }
    return result;
  }, [project, context, nodeId, weight]);
  return useAnalysisRequest<AnySensitivityProbe>(key, enabled && nodeId !== null && weight !== null, load);
}

export type SensitivityRequest = ReturnType<typeof useSensitivity>;
export type ProbeRequest = ReturnType<typeof useSensitivityProbe>;
export type { SensitivityProbe, SensitivityResult };
