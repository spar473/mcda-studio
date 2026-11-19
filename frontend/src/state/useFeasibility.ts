import { useCallback } from "react";
import { api } from "../api/client";
import type { Project } from "../api/types";
import { canonical } from "./analysisContext";
import { useAnalysisRequest } from "./useAnalysisRequest";

/** The feasibility check for one project revision. It depends on no method, profile or scenario,
 * so its identity is the revision alone; it runs only when the project states requirements. */
export function useFeasibility(project: Project, fingerprint: string) {
  const key = canonical({ kind: "feasibility", fingerprint });
  const load = useCallback(async (signal: AbortSignal) => {
    const result = await api.checkFeasibility(project, signal);
    if (result.project_fingerprint !== fingerprint) throw Error("Feasibility does not match the selected revision.");
    return result;
  }, [project, fingerprint]);
  return useAnalysisRequest(key, Boolean(project.requirements?.length), load);
}
