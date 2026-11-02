import { useCallback, useMemo } from "react";
import { api } from "../api/client";
import type { AnalysisConfiguration, Issue, Project } from "../api/types";
import { analysisKey, canonical, type AnalysisContext } from "./analysisContext";
import { useAnalysisRequest } from "./useAnalysisRequest";

/**
 * The engine's issues for one method's own section (for example `sorting` or `smaa`), checked
 * under that method whatever method is viewed, so its editor can show them. Read-only.
 */
export function useMethodIssues(project: Project, context: AnalysisContext, method: string,
  keep: (issue: Issue) => boolean) {
  const serialized = canonical(context.configuration.method === method ? context.configuration
    : { ...context.configuration, method, parameters: {} });
  const configuration = useMemo(() => JSON.parse(serialized) as AnalysisConfiguration, [serialized]);
  const key = analysisKey({ ...context, configuration, criterionId: null }, `${method}-section-validation`);
  const { fingerprint } = context;
  const load = useCallback(async (signal: AbortSignal) => {
    const response = await api.validateAnalysis(project, configuration, signal);
    if (response.project_fingerprint !== fingerprint || canonical(response.configuration) !== serialized)
      throw Error("Validation response does not match the selected analysis context.");
    return response.validation.issues.filter(keep);
  }, [project, configuration, fingerprint, serialized, keep]);
  return useAnalysisRequest(key, true, load);
}
