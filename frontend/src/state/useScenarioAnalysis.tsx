import { useCallback, type ReactNode } from "react";
import { api } from "../api/client";
import type { Project, ValidationReport } from "../api/types";
import { analysisKey, canonical, type AnalysisContext } from "./analysisContext";
import { useAnalysisRequest } from "./useAnalysisRequest";

export function ScopedAnalysis({ project, context, children }: {
  project: Project; context: AnalysisContext; children: (validation: ValidationReport) => ReactNode;
}) {
  const key=analysisKey({...context,criterionId:null},"effective-validation",context.resolvedProfileId);
  const load=useCallback(async(signal:AbortSignal)=>{
    const response=await api.validateAnalysis(project,context.configuration,signal);
    if(response.project_fingerprint!==context.fingerprint || response.scenario_id!==context.scenarioId ||
      response.weight_profile_id!==context.resolvedProfileId || canonical(response.configuration)!==canonical(context.configuration))
      throw Error("Validation response does not match the selected analysis context.");
    return response;
  },[project,context]);
  const request=useAnalysisRequest(key,true,load);
  const ready=request.status==="ready";
  // Keep workspace controls mounted across model-context changes, while hiding obsolete output
  // immediately and disabling its analysis requests until the new validation is authoritative.
  const report:ValidationReport=ready?request.result.validation:{issues:[{
    severity:"error",code:"ANALYSIS_PENDING",path:"analysis",message:"Selected analysis has not been validated."}]};
  return <>{request.status==="loading"&&<p role="status">Checking selected analysis…</p>}
    {request.status==="error"&&<><p role="alert">{request.message}</p>
      <button type="button" onClick={request.retry}>Retry analysis check</button></>}
    <div hidden={!ready}>{children(report)}</div></>;
}

export function useScenarioComparison(project:Project,context:AnalysisContext){
  const key=analysisKey(context,"scenario-comparison",{resolved:context.resolvedProfileId,scenarioIds:[context.scenarioId]});
  const load=useCallback(async(signal:AbortSignal)=>{
    if(!context.scenarioId)throw Error("Select a scenario to compare.");
    const response=await api.compareScenarios(project,[context.scenarioId],context.configuration,signal);
    const scenario=response.scenarios[0];
    const baseConfiguration={...context.configuration,scenario_id:null};
    const baseProfile=context.profileId ?? project.weight_profiles[0]?.id ?? null;
    if(response.project_fingerprint!==context.fingerprint || canonical(response.configuration)!==canonical(context.configuration) ||
      canonical(response.scenario_ids)!==canonical([context.scenarioId]) || response.scenarios.length!==1 ||
      !scenario || scenario.scenario_id!==context.scenarioId || scenario.weight_profile_id!==context.resolvedProfileId ||
      canonical(scenario.configuration)!==canonical(context.configuration) || response.baseline.scenario_id!==null ||
      response.baseline.weight_profile_id!==baseProfile || canonical(response.baseline.configuration)!==canonical(baseConfiguration))
      throw Error("Comparison response does not match the selected revision, scenarios and profiles.");
    const ids=project.alternatives.map(a=>a.id).sort();
    for(const outcome of [response.baseline,scenario]) if(canonical(Object.keys(outcome.values).sort())!==canonical(ids) ||
      canonical(Object.keys(outcome.rank_by_alternative).sort())!==canonical(ids) || canonical(Object.keys(outcome.delta_from_baseline).sort())!==canonical(ids))
      throw Error("Comparison alternatives do not match the project.");
    return response;
  },[project,context]);
  return useAnalysisRequest(key,context.scenarioId!==null,load);
}
