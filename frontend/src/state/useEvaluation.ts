import { useCallback } from "react";
import { api } from "../api/client";
import type { Project, ValidationReport } from "../api/types";
import { errorsOf } from "../model/issues";
import { analysisKey, canonical, type AnalysisContext } from "./analysisContext";
import { useAnalysisRequest } from "./useAnalysisRequest";

export function useEvaluation(project: Project, validation: ValidationReport, context: AnalysisContext) {
  const key = analysisKey(context, "evaluate");
  const load = useCallback(async (signal: AbortSignal) => {
    const result = await api.evaluate(project, context.configuration, signal);
    if (result.project_fingerprint !== context.fingerprint ||
        result.scenario_id !== context.scenarioId || result.weight_profile_id !== context.resolvedProfileId ||
        canonical(result.configuration) !== canonical(context.configuration)) {
      throw new Error("Analysis response does not match the selected revision and configuration.");
    }
    return result;
  }, [project, context]);
  const errors = errorsOf(validation).length;
  const request = useAnalysisRequest(key, errors === 0, load);
  return errors > 0 ? { status: "blocked" as const, errors } : request;
}
