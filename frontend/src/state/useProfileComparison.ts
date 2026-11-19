import { useCallback } from "react";
import { api } from "../api/client";
import type { EvidenceDossier, Project } from "../api/types";
import { analysisKey, canonical, type AnalysisContext } from "./analysisContext";
import { useAnalysisRequest } from "./useAnalysisRequest";

/** Two independent engine summaries, keyed by the ordered pair and the exact loaded dossier. */
export function useProfileComparison(project: Project, context: AnalysisContext, profiles: readonly [string, string], dossier: EvidenceDossier | null) {
  const key = canonical({ analysis: analysisKey({ ...context, criterionId: null }, "screening-profiles"), profiles, dossier });
  const load = useCallback(async (signal: AbortSignal) => {
    const result = await api.screeningProfiles(project, context.configuration, [...profiles], signal, dossier ?? undefined);
    if (result.project_fingerprint !== context.fingerprint || canonical(result.configuration) !== canonical(context.configuration) ||
        result.scenario_id !== context.scenarioId || result.profiles.length !== 2 ||
        result.profiles.some((reading, index) => {
          const id = profiles[index], expected = { ...context.configuration, weight_profile_id: id };
          return reading.profile_id !== id || reading.summary.project_fingerprint !== context.fingerprint ||
            canonical(reading.summary.configuration) !== canonical(expected) || reading.summary.weight_profile_id !== id ||
            reading.summary.scenario_id !== context.scenarioId;
        })) throw Error("Profile comparison does not match the selected revision, profiles and scenario.");
    const left = result.profiles[0], right = result.profiles[1];
    if (!left || !right) throw Error("Profile comparison is missing a requested profile.");
    const ids = canonical(project.alternatives.map(alternative => alternative.id).sort());
    if (result.profiles.some(reading => reading.summary.status === "available" &&
        canonical(reading.summary.rows.map(row => row.alternative_id).sort()) !== ids) ||
        (left.summary.status === "available" && right.summary.status === "available"
          ? canonical(result.movements.map(movement => movement.alternative_id).sort()) !== ids
          : result.movements.length !== 0)) {
      throw Error("Profile comparison alternatives do not match the selected project.");
    }
    if (result.movements.some(movement => movement.from_profile_id !== profiles[0] || movement.to_profile_id !== profiles[1] ||
        !left.summary.rows.some(row => row.alternative_id === movement.alternative_id && row.rank === movement.from_rank) ||
        !right.summary.rows.some(row => row.alternative_id === movement.alternative_id && row.rank === movement.to_rank))) {
      throw Error("Profile comparison movements do not match their engine summaries.");
    }
    return result;
  }, [project, context, profiles, dossier]);
  return useAnalysisRequest(key, project.weight_profiles.length >= 2, load);
}
