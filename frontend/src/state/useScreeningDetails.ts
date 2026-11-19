import { useCallback } from "react";
import { api } from "../api/client";
import type { EvidenceDossier, Project } from "../api/types";
import { analysisKey, canonical, type AnalysisContext } from "./analysisContext";
import { useAnalysisRequest } from "./useAnalysisRequest";

/** The screening summary for one revision, profile and scenario (and the dossier, when one is
 * loaded). Python computes every number; a response for another context is never shown. */
export function useScreeningDetails(project: Project, context: AnalysisContext, dossier?: EvidenceDossier | null, alternativeId: string | null = null) {
  const key = canonical({ analysis: analysisKey({ ...context, criterionId: null }, "screening-details"), alternativeId, dossier: dossier ?? null });
  const load = useCallback(async (signal: AbortSignal) => {
    const result = await api.screeningDetails(project, context.configuration, alternativeId, signal, dossier ?? undefined);
    if (result.project_fingerprint !== context.fingerprint || canonical(result.configuration) !== canonical(context.configuration) ||
        (result.status === "available" && (result.weight_profile_id !== context.resolvedProfileId || result.scenario_id !== context.scenarioId || (alternativeId !== null && result.alternative?.row.alternative_id !== alternativeId)))) {
      throw new Error("Screening summary does not match the selected revision and configuration.");
    }
    return result;
  }, [project, context, dossier, alternativeId]);
  return useAnalysisRequest(key, project.alternatives.length > 0, load);
}
