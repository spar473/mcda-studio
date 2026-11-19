import { useCallback, useMemo } from "react";
import { api } from "../api/client";
import { isAhpRecord, isPrometheeRecord, isSmaaRecord, type AnalysisConfiguration, type EvidenceDossier, type Project } from "../api/types";
import { analysisKey, canonical, type AnalysisContext } from "./analysisContext";
import { useAnalysisRequest } from "./useAnalysisRequest";
import { assertAnalysisRecord } from "./useAnalysisRecord";

/** Original project only; the dossier participates in cancellation, never in the trial request. */
export function useScreeningWhatIf(project: Project, context: AnalysisContext, ratings: Record<string, number>, dossier: EvidenceDossier | null, enabled: boolean, generation: number) {
  const key = canonical({ analysis: analysisKey({ ...context, criterionId: null }, "screening-what-if"), ratings, dossier, enabled, generation });
  const serialized = canonical(context.configuration);
  const configuration = useMemo(() => JSON.parse(serialized) as AnalysisConfiguration, [serialized]);
  const serializedRatings = canonical(ratings);
  // Equal ratings keep the same identity, so a criterion-only selection never re-evaluates.
  const exactRatings = useMemo(() => JSON.parse(serializedRatings) as Record<string, number>, [serializedRatings]);
  const { fingerprint, resolvedProfileId, scenarioId } = context;
  const load = useCallback(async (signal: AbortSignal) => {
    const result = await api.screeningWhatIf(project, configuration, exactRatings, signal);
    if (result.project_fingerprint !== fingerprint || canonical(result.configuration) !== serialized ||
        canonical(result.ratings) !== serializedRatings) throw Error("What-if preview does not match the source revision and requested ratings.");
    if (result.status === "available") {
      const { record, summary, trial_project_fingerprint: trial } = result;
      if (!record || !summary || !trial || isAhpRecord(record) || isPrometheeRecord(record) || isSmaaRecord(record) ||
          result.weight_profile_id !== resolvedProfileId || result.scenario_id !== scenarioId ||
          record.result.project_fingerprint !== trial || summary.project_fingerprint !== trial ||
          record.result.project_id !== project.id || ("configuration" in record && canonical(record.configuration) !== serialized) ||
          canonical(record.result.configuration) !== serialized || canonical(summary.configuration) !== serialized ||
          record.result.weight_profile_id !== resolvedProfileId || summary.weight_profile_id !== resolvedProfileId ||
          record.result.scenario_id !== scenarioId || summary.scenario_id !== scenarioId || summary.status !== "available") {
        throw Error("What-if engine records do not match the temporary reading and selected context.");
      }
      assertAnalysisRecord(record, project, trial, configuration, resolvedProfileId, scenarioId);
    } else if (result.record || result.summary || result.trial_project_fingerprint) {
      throw Error("An unavailable what-if preview cannot contain a ranking.");
    }
    return result;
  }, [project, configuration, serialized, fingerprint, resolvedProfileId, scenarioId, exactRatings, serializedRatings]);
  return useAnalysisRequest(key, enabled, load, 150);
}
