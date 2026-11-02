import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { AnalysisValidation, ScenarioComparison } from "../../src/api/types";
import { ScenarioPanel, comparisonRows } from "../../src/components/ScenarioPanel";
import { ScopedAnalysis } from "../../src/state/useScenarioAnalysis";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import { node, projectWith, ratioScale } from "../fixtures";
const project=projectWith([node("cost",null,0,{scale:ratioScale,value_function:{kind:"linear",direction:"increasing",out_of_domain:"error"}})],{
 analysis:{method:"mavt",scenario_id:null,weight_profile_id:null,parameters:{}},alternatives:[{id:"b",name:"Same",metadata:{}},{id:"a",name:"Same",metadata:{}}],
 weight_profiles:[{id:"first",name:"First",method:"swing",judgements:{cost:100}}],scenarios:[{id:"s",name:"Experiment",weight_profile_id:null,value_function_overrides:{cost:{kind:"linear",direction:"decreasing",out_of_domain:"error"}}}]});
const ctx=resolveContext(project,"fp",{...BASE_SELECTION,scenarioId:"s"});
const outcome={scenario_id:null,scenario_name:"baseline",configuration:{...ctx.configuration,scenario_id:null},weight_profile_id:"first",
 applied_overrides:{},resolved_domains:{},diagnostics:[],ranking:["b","a"],values:{a:.2,b:.8},rank_by_alternative:{a:2,b:1},delta_from_baseline:{a:0,b:0},ranking_differs_from_baseline:false,winner_differs_from_baseline:false};
const comparison:ScenarioComparison={project_fingerprint:"fp",configuration:ctx.configuration,scenario_ids:["s"],baseline:outcome,
 scenarios:[{...outcome,scenario_id:"s",scenario_name:"Experiment",configuration:ctx.configuration,ranking:["a","b"],values:{a:.6,b:.4},rank_by_alternative:{a:1,b:2},delta_from_baseline:{a:.123,b:-.4},ranking_differs_from_baseline:true,winner_differs_from_baseline:true}]};
const validation:AnalysisValidation={project_fingerprint:"fp",configuration:ctx.configuration,scenario_id:"s",weight_profile_id:"first",validation:{issues:[]}};
async function settle(){await act(async()=>{await vi.advanceTimersByTimeAsync(125);});}
function setup(){const props={project,context:ctx,busy:false,manage:vi.fn(()=>Promise.resolve(true)),onSelect:vi.fn(),onEdit:vi.fn()};return {...render(<ScenarioPanel {...props}/>),props};}
beforeEach(()=>{vi.useFakeTimers();vi.spyOn(api,"compareScenarios").mockResolvedValue(comparison);vi.spyOn(api,"validateAnalysis").mockResolvedValue(validation);});
afterEach(()=>{vi.restoreAllMocks();vi.useRealTimers();});
describe("scenario management and authoritative comparison",()=>{
 it("joins by IDs despite reversed rankings and duplicate names, and uses server deltas/ranks",async()=>{
   setup();await settle();const rows=within(screen.getByRole("table",{name:"Scenario comparison"})).getAllByRole("row");
   expect(rows[1]).toHaveTextContent("b");expect(rows[1]).toHaveTextContent("-0.400000");
   expect(rows[2]).toHaveTextContent("a");expect(rows[2]).toHaveTextContent("0.123000");
   expect(comparisonRows(project,comparison).map(r=>r.id)).toEqual(["b","a"]);
   expect(comparisonRows(project,comparison).map(r=>r.value)).toEqual([.4,.6]);
   expect(within(rows[1] as HTMLElement).getAllByRole("cell")[2]).toHaveTextContent("0.400000");
   expect(screen.getByText(/Winner set changed/)).toBeVisible();
 });
 it("transient selection never calls an edit",()=>{
   const view=setup();fireEvent.change(screen.getByLabelText("Scenario to manage"),{target:{value:""}});
   expect(view.props.onSelect).toHaveBeenCalledWith(null);expect(view.props.manage).not.toHaveBeenCalled();expect(project.analysis.scenario_id).toBeNull();
 });
 it.each(["create","duplicate","rename"])("%s is an explicit single scenario operation",async(mode)=>{
   const view=setup();fireEvent.click(screen.getByRole("button",{name:`${mode[0]?.toUpperCase()}${mode.slice(1)} scenario`}));
   fireEvent.change(screen.getByLabelText("Scenario name"),{target:{value:"  Named  "}});
   await act(async()=>{fireEvent.click(screen.getByRole("button",{name:"Confirm scenario change"}));await Promise.resolve();});
   expect(view.props.manage).toHaveBeenCalledWith(mode==="create"?{op:"create_scenario",name:"Named"}:{op:mode==="duplicate"?"duplicate_scenario":"rename_scenario",scenario_id:"s",name:"Named"});
 });
 it("reset removes the override instead of copying a base function",()=>{
   const view=setup();fireEvent.click(screen.getByLabelText("Reset COST to base"));
   expect(view.props.manage).toHaveBeenCalledWith({op:"clear_scenario_override",scenario_id:"s",criterion_id:"cost"});
   fireEvent.click(screen.getByRole("button",{name:"Edit override for COST"}));expect(view.props.onEdit).toHaveBeenCalledWith("cost");
 });
 it("saved-default deletion requires explicitly choosing Base or a replacement",async()=>{
   const view=setup();view.rerender(<ScenarioPanel {...view.props} project={{...project,analysis:{...project.analysis,scenario_id:"s"}}}/>);
   fireEvent.click(screen.getByRole("button",{name:"Delete scenario"}));expect(screen.getByRole("button",{name:"Confirm scenario change"})).toBeDisabled();
   expect(screen.getByLabelText("Scenario default replacement")).toHaveValue("");
   fireEvent.change(screen.getByLabelText("Scenario default replacement"),{target:{value:"__base__"}});
   await act(async()=>{fireEvent.click(screen.getByRole("button",{name:"Confirm scenario change"}));await Promise.resolve();});
   expect(view.props.manage).toHaveBeenCalledWith({op:"remove_scenario",scenario_id:"s",repair_default:true,replacement_scenario_id:null});
 });
 it("scenario profiles use an explicit reference or the original first-profile fallback",()=>{
   const view=setup();fireEvent.change(screen.getByLabelText("Scenario profile"),{target:{value:"first"}});
   expect(view.props.manage).toHaveBeenCalledWith({op:"set_scenario_profile",scenario_id:"s",profile_id:"first"});
   fireEvent.change(screen.getByLabelText("Scenario profile"),{target:{value:""}});expect(view.props.manage).toHaveBeenLastCalledWith({op:"set_scenario_profile",scenario_id:"s",profile_id:null});
 });
 it.each(["revision","profile","scenario","alternatives"])("rejects a comparison with mismatched %s",async(field)=>{
   const response=structuredClone(comparison);
   if(field==="revision")response.project_fingerprint="wrong";
   if(field==="profile"&&response.scenarios[0])response.scenarios[0].weight_profile_id="wrong";
   if(field==="scenario")response.scenario_ids=["wrong"];
   if(field==="alternatives"&&response.scenarios[0])delete response.scenarios[0].values.a;
   vi.mocked(api.compareScenarios).mockResolvedValue(response);setup();await settle();
   expect(screen.getByRole("alert")).toHaveTextContent(/does not match|do not match/);expect(screen.queryByRole("table",{name:"Scenario comparison"})).not.toBeInTheDocument();
 });
 it("rejects an obsolete comparison even if transport ignores cancellation",async()=>{
   let release:(v:ScenarioComparison)=>void=()=>undefined;const old=new Promise<ScenarioComparison>(resolve=>{release=resolve;});
   vi.mocked(api.compareScenarios).mockReturnValueOnce(old).mockResolvedValueOnce({...comparison,project_fingerprint:"fresh"});
   const view=setup();await settle();view.rerender(<ScenarioPanel {...view.props} context={{...ctx,fingerprint:"fresh"}}/>);await settle();
   await act(async()=>{release(comparison);await Promise.resolve();});expect(screen.getByRole("table",{name:"Scenario comparison"})).toBeVisible();
   expect(vi.mocked(api.compareScenarios).mock.calls[0]?.[3]?.aborted).toBe(true);
 });
 it("criterion selection retains the mounted workspace while model validation stays scoped",async()=>{
   const child=vi.fn();function Workspace(){child();return <input aria-label="Workspace cursor" defaultValue="0.4"/>;}
   const view=render(<ScopedAnalysis project={project} context={ctx}>{()=> <Workspace/>}</ScopedAnalysis>);await settle();
   fireEvent.change(screen.getByLabelText("Workspace cursor"),{target:{value:"0.7"}});
   view.rerender(<ScopedAnalysis project={project} context={{...ctx,criterionId:"cost"}}>{()=> <Workspace/>}</ScopedAnalysis>);
   expect(screen.getByLabelText("Workspace cursor")).toHaveValue("0.7");await settle();expect(screen.getByLabelText("Workspace cursor")).toHaveValue("0.7");
 });
 it("scoped validation checks provenance and allows an effective ready model",async()=>{
   const view=render(<ScopedAnalysis project={project} context={ctx}>{report=><p>{report.issues.length===0?"Selected analysis ready":"Selected analysis blocked"}</p>}</ScopedAnalysis>);await settle();
   expect(screen.getByText("Selected analysis ready")).toBeVisible();
   vi.mocked(api.validateAnalysis).mockResolvedValue({...validation,weight_profile_id:"wrong"});view.rerender(<ScopedAnalysis project={project} context={{...ctx,fingerprint:"changed"}}>{()=> <p>Should be hidden</p>}</ScopedAnalysis>);await settle();
   expect(screen.getByRole("alert")).toHaveTextContent("does not match");expect(screen.getByText("Should be hidden")).not.toBeVisible();
 });
 it("Retry re-requests a failed comparison and never substitutes the base result",async()=>{
   vi.mocked(api.compareScenarios).mockRejectedValueOnce(new Error("Comparison unavailable"));
   const view=setup();await settle();
   expect(screen.getByRole("alert")).toHaveTextContent("Comparison unavailable");expect(screen.queryByRole("table",{name:"Scenario comparison"})).toBeNull();
   fireEvent.click(screen.getByRole("button",{name:"Retry comparison"}));await settle();
   expect(screen.getByRole("table",{name:"Scenario comparison"})).toBeVisible();expect(api.compareScenarios).toHaveBeenCalledTimes(2);
   expect(vi.mocked(api.compareScenarios).mock.calls[1]?.slice(0,3)).toEqual(vi.mocked(api.compareScenarios).mock.calls[0]?.slice(0,3));
   expect(view.props.manage).not.toHaveBeenCalled();expect(view.props.onEdit).not.toHaveBeenCalled();
 });
 it("Retry re-checks a failed scoped validation before showing the workspace",async()=>{
   vi.mocked(api.validateAnalysis).mockRejectedValueOnce(new Error("Check unavailable"));
   render(<ScopedAnalysis project={project} context={ctx}>{report=><p>{report.issues.length===0?"Selected analysis ready":"Selected analysis blocked"}</p>}</ScopedAnalysis>);await settle();
   expect(screen.getByRole("alert")).toHaveTextContent("Check unavailable");expect(screen.getByText("Selected analysis blocked")).not.toBeVisible();
   fireEvent.click(screen.getByRole("button",{name:"Retry analysis check"}));await settle();
   expect(screen.getByText("Selected analysis ready")).toBeVisible();expect(api.validateAnalysis).toHaveBeenCalledTimes(2);
 });
});
