import { useCallback } from "react";
import { api } from "../api/client";
import type { AnalysisConfiguration, MethodInfo, Project } from "../api/types";
import { canonical, type AnalysisContext } from "./analysisContext";
import { useAnalysisRequest } from "./useAnalysisRequest";
const MISSING = new Set(["NO_SORTING_MODEL", "PROMETHEE_NOT_STATED", "AHP_NOT_STATED"]);
export function useMethodAvailability(project: Project, context: AnalysisContext, methods: MethodInfo[]) {
  const configs = canonical(methods.map(m => context.configuration.method === m.name ? context.configuration : { ...context.configuration, method: m.name, parameters: {} }));
  const fingerprint = context.fingerprint;
  const load = useCallback(async (signal: AbortSignal) => {
    const configurations = JSON.parse(configs) as AnalysisConfiguration[];
    return Object.fromEntries(await Promise.all(configurations.map(async configuration => {
      const response = await api.validateAnalysis(project, configuration, signal);
      if (response.project_fingerprint !== fingerprint || canonical(response.configuration) !== canonical(configuration))
        throw Error("Method availability does not match this revision and configuration.");
      return [configuration.method, response.validation.issues.some(i => MISSING.has(i.code))] as const;
    })));
  }, [project, configs, fingerprint]);
  return useAnalysisRequest(canonical({ fingerprint, configs, kind: "method-availability" }), methods.length > 0, load);
}
