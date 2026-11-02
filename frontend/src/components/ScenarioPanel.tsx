import { useState } from "react";
import type { Operation, Project, ScenarioComparison } from "../api/types";
import { isLeaf, pathNames } from "../model/tree";
import type { AnalysisContext } from "../state/analysisContext";
import { useScenarioComparison } from "../state/useScenarioAnalysis";
import { Banner, Modal } from "./ui";
import { ScenarioComparisonChart } from "./results/ResultsCharts";

type Mode="create"|"duplicate"|"rename"|"delete"|"default";
interface Props {
  project:Project;context:AnalysisContext;busy:boolean;
  manage:(op:Operation)=>Promise<boolean>;onSelect:(scenarioId:string|null)=>void;
  onEdit:(criterionId:string)=>void;
}
/** Presentation joins use stable IDs, never display names or positions in ranked arrays. */
export function comparisonRows(project:Project,result:ScenarioComparison){
  const outcome=result.scenarios[0];
  return project.alternatives.map(a=>({id:a.id,name:a.name,base:result.baseline.values[a.id],
    value:outcome?.values[a.id],baseRank:result.baseline.rank_by_alternative[a.id],
    rank:outcome?.rank_by_alternative[a.id],delta:outcome?.delta_from_baseline[a.id]}));
}
export function ScenarioPanel({project,context,busy,manage,onSelect,onEdit}:Props){
  const scenario=project.scenarios.find(s=>s.id===context.scenarioId);
  const [dialog,setDialog]=useState<{mode:Mode;id:string|null;revision:string}|null>(null);
  const [name,setName]=useState("");const [replacement,setReplacement]=useState("");
  const [pending,setPending]=useState(false);const [error,setError]=useState<string|null>(null);
  const request=useScenarioComparison(project,context);
  const result=request.status==="ready"?request.result:null;
  const outcome=result?.scenarios[0];
  const profileName=(id:string|null)=>project.weight_profiles.find(p=>p.id===id)?.name ?? id ?? "None";
  const referenced=dialog?.id!==null && project.analysis.scenario_id===dialog?.id;
  function open(mode:Mode){setDialog({mode,id:scenario?.id??null,revision:context.fingerprint});
    setName(mode==="duplicate"?`${scenario?.name??"Scenario"} (copy)`:mode==="rename"?scenario?.name??"":"");setReplacement("");setError(null);}
  const names=dialog && ["create","duplicate","rename"].includes(dialog.mode);
  const disabled=busy||pending||!!dialog&&dialog.revision!==context.fingerprint||!!names&&!name.trim()||dialog?.mode==="delete"&&referenced&&!replacement;
  async function submit(){
    if(!dialog||disabled)return;
    let op:Operation;
    switch(dialog.mode){
      case "create":op={op:"create_scenario",name:name.trim()};break;
      case "duplicate":if(!dialog.id)return;op={op:"duplicate_scenario",scenario_id:dialog.id,name:name.trim()};break;
      case "rename":if(!dialog.id)return;op={op:"rename_scenario",scenario_id:dialog.id,name:name.trim()};break;
      case "delete":if(!dialog.id)return;op={op:"remove_scenario",scenario_id:dialog.id,repair_default:referenced,
        replacement_scenario_id:replacement==="__base__"||!replacement?null:replacement};break;
      case "default":op={op:"set_default_scenario",scenario_id:dialog.id};break;
    }
    setPending(true);const ok=await manage(op);setPending(false);
    if(ok)setDialog(null);else setError("Scenario change was refused. The project was retained; inspect the application message or cancel and reopen.");
  }
  const labels:Record<Mode,string>={create:"Create scenario",duplicate:"Duplicate scenario",rename:"Rename scenario",delete:"Delete scenario",default:"Change saved scenario default"};
  return <section className="panel" aria-label="Scenarios">
    <h2>Scenarios</h2>
    <p>A scenario stores named function overrides and a preference-profile reference. Measurements, units and measurement-scale anchor policies remain shared with the base model. Viewing and comparison are read-only.</p>
    <div className="scenario-toolbar">
      <label>Scenario to manage<select aria-label="Scenario to manage" value={context.scenarioId??""} disabled={busy} onChange={e=>onSelect(e.target.value||null)}>
        <option value="">Base model</option>{project.scenarios.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
      </select></label>
      <button type="button" disabled={busy} onClick={()=>open("create")}>Create scenario</button>
      <button type="button" disabled={busy||!scenario} onClick={()=>open("duplicate")}>Duplicate scenario</button>
      <button type="button" disabled={busy||!scenario} onClick={()=>open("rename")}>Rename scenario</button>
      <button type="button" disabled={busy||!scenario} onClick={()=>open("delete")}>Delete scenario</button>
      <button type="button" disabled={busy||project.analysis.scenario_id===context.scenarioId} onClick={()=>open("default")}>Use viewed scenario as saved default</button>
    </div>
    <p className="muted small">Saved scenario default: {project.scenarios.find(s=>s.id===project.analysis.scenario_id)?.name??"Base model"}. Ordinary selection does not change it.</p>
    {scenario ? <>
      <p>Viewing <strong>{scenario.name}</strong> · stable ID <code>{scenario.id}</code> · resolved profile <strong>{profileName(context.resolvedProfileId)}</strong></p>
      <label>Scenario profile<select aria-label="Scenario profile" value={scenario.weight_profile_id??""} disabled={busy}
        onChange={e=>void manage({op:"set_scenario_profile",scenario_id:scenario.id,profile_id:e.target.value||null})}>
        <option value="">First project profile (no scenario reference)</option>{project.weight_profiles.filter(p=>p.method==="swing").map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
      </select></label>
      {context.profileId && <Banner kind="info">The explicitly viewed weight profile overrides this scenario’s stored profile reference for analysis and comparison. Select Automatic above to use the scenario reference.</Banner>}
      <h3>Functions relative to base</h3>
      <table className="grid scenario-overrides" aria-label="Scenario function overrides"><thead><tr><th>Criterion path</th><th>Source</th><th>Function</th><th>Actions</th></tr></thead><tbody>
        {project.criteria.filter(n=>isLeaf(project.criteria,n.id)).map(n=>{
          const override=scenario.value_function_overrides[n.id];return <tr key={n.id}>
            <th>{pathNames(project.criteria,n.id).join(" › ")}</th><td>{override?"Explicit override":"Inherited from base"}</td><td>{(override??n.value_function)?.kind??"Missing definition"}</td>
            <td><button type="button" disabled={busy||!n.scale||!(override??n.value_function)} onClick={()=>onEdit(n.id)}>Edit override for {n.name}</button>
              <button type="button" disabled={busy||!override} aria-label={`Reset ${n.name} to base`} onClick={()=>void manage({op:"clear_scenario_override",scenario_id:scenario.id,criterion_id:n.id})}>Reset to Base</button></td></tr>;
        })}</tbody></table>
      <h3>Comparison with Base model</h3>
      {request.status==="loading"&&<p role="status">Comparing scenario with base…</p>}
      {request.status==="error"&&<><Banner kind="error">{request.message} No base result is substituted for this scenario.</Banner>
        <button type="button" onClick={request.retry}>Retry comparison</button></>}
      {result&&outcome&&<>
        <ScenarioComparisonChart comparison={result} alternatives={project.alternatives} projectId={project.id}/>
        <p aria-label="Comparison profiles">Base profile: {profileName(result.baseline.weight_profile_id)} · Scenario profile: {profileName(outcome.weight_profile_id)}.
          {result.baseline.weight_profile_id!==outcome.weight_profile_id?" Preference profiles differ; changes may reflect weights as well as functions.":" Both outcomes use the same preference profile."}</p>
        <p>Applied function overrides: {Object.keys(outcome.applied_overrides).map(id=>project.criteria.find(n=>n.id===id)?.name??id).join(", ")||"None (all inherited)"}.</p>
        <p role="status">{outcome.winner_differs_from_baseline?"Winner set changed":"Winner set unchanged"} · {outcome.ranking_differs_from_baseline?"Competition ranking changed":"Competition ranking unchanged"}. Tied alternatives share a competition rank.</p>
        <div className="comparison-scroll" role="region" aria-label="Scrollable comparison" tabIndex={0}><table className="grid" aria-label="Scenario comparison"><thead><tr><th>Alternative</th><th>ID</th><th>Base value</th><th>Scenario value</th><th>Base rank</th><th>Scenario rank</th><th>Value change</th></tr></thead><tbody>
          {comparisonRows(project,result).map(row=><tr key={row.id}><th>{row.name}</th><td><code>{row.id}</code></td><td>{row.base?.toFixed(6)}</td><td>{row.value?.toFixed(6)}</td><td>{row.baseRank}</td><td>{row.rank}</td><td>{row.delta?.toFixed(6)}</td></tr>)}
        </tbody></table></div>
        <p className="muted small">Scores are compensatory MAVT preference values, not probabilities or financial returns. Base explicitly clears the scenario while retaining any explicitly viewed profile. Other saved configurations may still have problems.</p>
        <ul className="issue-list inline" aria-label="Comparison diagnostics">{[...result.baseline.diagnostics,...outcome.diagnostics].map((issue,i)=><li key={i} className={issue.severity}><code>{issue.code}</code> {issue.message} <span>{issue.path}</span></li>)}</ul>
      </>}
    </>:<p>Select or create a scenario to manage its overrides and compare it with the base.</p>}
    {dialog&&<Modal title={labels[dialog.mode]} onClose={()=>{if(!pending)setDialog(null);}} footer={<>
      <button type="button" disabled={pending} onClick={()=>setDialog(null)}>Cancel</button><button type="button" className={dialog.mode==="delete"?"danger":"primary"} disabled={disabled} onClick={()=>void submit()}>Confirm scenario change</button>
    </>}>
      {dialog.revision!==context.fingerprint&&<Banner kind="error">The project changed. Cancel and reopen this dialog.</Banner>}
      {error&&<Banner kind="error">{error}</Banner>}
      {names&&<label>Scenario name<input aria-label="Scenario name" value={name} disabled={pending} onChange={e=>setName(e.target.value)}/></label>}
      {dialog.mode==="create"&&<p>The new scenario inherits base functions and uses the first profile unless a profile is explicitly chosen for analysis or stored on the scenario.</p>}
      {dialog.mode==="duplicate"&&<p>Copy the selected scenario into an independent ID and override collection.</p>}
      {dialog.mode==="delete"&&<><p>Delete this scenario and its overrides only. The base remains intact. If it is being viewed, the view moves to Base or the explicitly chosen replacement.</p>
        {referenced&&<label>Repair saved default<select aria-label="Scenario default replacement" value={replacement} onChange={e=>setReplacement(e.target.value)}>
          <option value="">Choose explicitly…</option><option value="__base__">Base model</option>{project.scenarios.filter(s=>s.id!==dialog.id).map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
        </select></label>}</>}
      {dialog.mode==="default"&&<p>Explicitly change the saved scenario default to {scenario?.name??"Base model"}. The saved profile override, method and parameters remain intact. Save to persist this change.</p>}
    </Modal>}
  </section>;
}
