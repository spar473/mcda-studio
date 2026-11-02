import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { WeightPreview } from "../../src/api/types";
import { WeightsPanel } from "../../src/components/WeightsPanel";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import { node, projectWith } from "../fixtures";
const project=projectWith([node("cost"),node("quality",null,1)],{analysis:{method:"mavt",scenario_id:null,weight_profile_id:null,parameters:{}},
  weight_profiles:[{id:"first",name:"First",method:"swing",judgements:{cost:100,quality:20}},{id:"other",name:"Other",method:"swing",judgements:{cost:0}}]});
const context=resolveContext(project,"source",{...BASE_SELECTION,profileId:"first"});
const result:WeightPreview={project_fingerprint:"source",configuration:context.configuration,weight_profile_id:"first",scenario_id:null,weights_ready:true,
  local_weights:{cost:.137,quality:.863},global_weights:{cost:.137,quality:.863},path_shares:{cost:.137,quality:.863},sibling_rating_totals:{"<root>":120},weight_basis:"Authoritative engine interpretation",diagnostics:[],
  swing_ranges:{cost:{readiness:"ready",scale_type:"ratio",unit:"NZD",domain:{lower:20,upper:60,source:"fixed"},worst:[60],best:[20],diagnostics:[]},
  quality:{readiness:"incomplete",scale_type:"ratio",unit:null,domain:null,worst:[],best:[],diagnostics:[{code:"MISSING_MEASUREMENT",path:"performances[x,quality]",message:"Local reading missing",severity:"error"}]}}};
function setup(){const props={project,context,validation:{issues:[]},busy:false,apply:vi.fn(()=>Promise.resolve(true)),manage:vi.fn(()=>Promise.resolve(true)),onSelectProfile:vi.fn(),onSelectCriterion:vi.fn()};return {...render(<WeightsPanel {...props}/>),props};}
async function settle(){await act(async()=>{await vi.advanceTimersByTimeAsync(125);});}
beforeEach(()=>{vi.useFakeTimers();vi.spyOn(api,"previewWeights").mockResolvedValue(result);});
afterEach(()=>{vi.restoreAllMocks();vi.useRealTimers();});
describe("hierarchical swing weights use backend arithmetic and range semantics",()=>{
  it("renders supplied weights and swing endpoints without deriving ratios from raw ratings",async()=>{
    setup();await settle();expect(screen.getByLabelText("Engine weight interpretation")).toHaveTextContent("Authoritative engine interpretation");
    expect(screen.getByRole("meter",{name:"Local weight for COST"})).toHaveValue(.137);
    expect(screen.getByText(/Worst 60 → Best 20 NZD/)).toBeVisible();expect(screen.getByText(/Range incomplete/)).toBeVisible();
    expect(screen.getByRole("table",{name:"Swing ratings under top level"})).toHaveTextContent("0.1370");
    expect(screen.getByLabelText("Swing rating for COST")).toHaveValue("100");
  });
  it("changes raw ratings through a profile-scoped operation and accepts values above 100",async()=>{
    const view=setup();await settle();const input=screen.getByLabelText("Swing rating for COST");
    fireEvent.change(input,{target:{value:"240"}});fireEvent.blur(input);
    expect(view.props.apply).toHaveBeenCalledWith([{op:"set_judgement",node_id:"cost",profile_id:"first",rating:240}]);
    fireEvent.change(input,{target:{value:""}});fireEvent.blur(input);
    expect(view.props.apply).toHaveBeenLastCalledWith([{op:"clear_judgement",node_id:"cost",profile_id:"first"}]);
  });
  it("does not send nonfinite text and disables overlapping rating edits",async()=>{
    const view=setup();await settle();const input=screen.getByLabelText("Swing rating for COST");fireEvent.change(input,{target:{value:"Infinity"}});fireEvent.blur(input);
    expect(input).toHaveAttribute("aria-invalid","true");expect(view.props.apply).not.toHaveBeenCalled();
    view.rerender(<WeightsPanel {...view.props} busy={true}/>);expect(input).toBeDisabled();
  });
  it("invalid sibling sets show no plausible normalised bars",async()=>{
    vi.mocked(api.previewWeights).mockResolvedValue({...result,weights_ready:false,local_weights:{},global_weights:{},diagnostics:[{code:"ZERO_SUM_JUDGEMENTS",path:"weight_profiles[first].judgements",message:"All siblings zero",severity:"error"}]});
    setup();await settle();expect(screen.queryByRole("meter")).not.toBeInTheDocument();expect(screen.getByText("ZERO_SUM_JUDGEMENTS")).toBeVisible();expect(screen.getByText(/Worst 60 → Best 20 NZD/)).toBeVisible();
  });
  it("zero and missing ratings remain distinct on context switching and stale bars hide immediately",async()=>{
    const view=setup();await settle();const next=resolveContext(project,"source",{...BASE_SELECTION,profileId:"other"});
    vi.mocked(api.previewWeights).mockResolvedValue({...result,configuration:next.configuration,weight_profile_id:"other",weights_ready:false,local_weights:{},global_weights:{}});
    view.rerender(<WeightsPanel {...view.props} context={next}/>);expect(screen.queryByRole("meter")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Swing rating for COST")).toHaveValue("0");expect(screen.getByLabelText("Swing rating for QUALITY")).toHaveValue("");
    expect(screen.getByText("Zero rating")).toBeVisible();expect(screen.getByText("Missing rating")).toBeVisible();await settle();expect(screen.queryByRole("meter")).not.toBeInTheDocument();
  });
  it("path selection stays in the shared context rather than editing the project",async()=>{
    const view=setup();await settle();const table=screen.getByRole("table",{name:"Swing ratings under top level"});fireEvent.click(within(table).getByRole("button",{name:"COST"}));
    expect(view.props.onSelectCriterion).toHaveBeenCalledWith("cost");expect(view.props.apply).not.toHaveBeenCalled();
  });
  it("explains a selected global weight with engine shares rather than browser arithmetic",async()=>{
    // Deliberately inconsistent with naive multiplication: .6 x .5 would be .3000, but the engine
    // is the only authority, so the panel must print the supplied .4200 share verbatim.
    const nested=projectWith([node("team"),node("founder","team"),node("coverage","team",1),node("market",null,1)],
      {analysis:{method:"mavt",scenario_id:null,weight_profile_id:null,parameters:{}},
       weight_profiles:[{id:"first",name:"First",method:"swing",judgements:{team:100,market:50,founder:65,coverage:35}}]});
    const ctx=resolveContext(nested,"source",{...BASE_SELECTION,profileId:"first",criterionId:"founder"});
    vi.mocked(api.previewWeights).mockResolvedValue({...result,project_fingerprint:"source",configuration:ctx.configuration,
      local_weights:{team:.6,market:.4,founder:.5,coverage:.5},global_weights:{founder:.42,coverage:.18,market:.4},
      path_shares:{team:.6,market:.4,founder:.42,coverage:.18},swing_ranges:{}});
    const apply=vi.fn(()=>Promise.resolve(true));
    render(<WeightsPanel project={nested} context={ctx} validation={{issues:[]}} busy={false} apply={apply}
      manage={vi.fn(()=>Promise.resolve(true))} onSelectProfile={vi.fn()} onSelectCriterion={vi.fn()}/>);
    await settle();
    const steps=screen.getByRole("table",{name:"Derivation steps for FOUNDER"});
    expect(steps).toHaveTextContent("0.4200");expect(steps).not.toHaveTextContent("0.3000");
    // The objective's own share and the leaf's local share are both shown, and kept distinct.
    expect(within(steps).getByRole("row",{name:/TEAM/})).toHaveTextContent("0.6000");
    expect(within(steps).getByRole("row",{name:/FOUNDER/})).toHaveTextContent("65");
    expect(screen.getByLabelText("Weight derivation for FOUNDER")).toHaveTextContent("42.00% of the overall goal");
    expect(apply).not.toHaveBeenCalled();
  });
  it("names an objective's branch share without claiming it is a global weight",async()=>{
    const nested=projectWith([node("team"),node("founder","team"),node("coverage","team",1),node("market",null,1)],
      {analysis:{method:"mavt",scenario_id:null,weight_profile_id:null,parameters:{}},
       weight_profiles:[{id:"first",name:"First",method:"swing",judgements:{team:100,market:50,founder:65,coverage:35}}]});
    const ctx=resolveContext(nested,"source",{...BASE_SELECTION,profileId:"first",criterionId:"team"});
    vi.mocked(api.previewWeights).mockResolvedValue({...result,project_fingerprint:"source",configuration:ctx.configuration,
      local_weights:{team:.6,market:.4,founder:.5,coverage:.5},global_weights:{founder:.42,coverage:.18,market:.4},
      path_shares:{team:.6,market:.4,founder:.42,coverage:.18},swing_ranges:{}});
    render(<WeightsPanel project={nested} context={ctx} validation={{issues:[]}} busy={false} apply={vi.fn(()=>Promise.resolve(true))}
      manage={vi.fn(()=>Promise.resolve(true))} onSelectProfile={vi.fn()} onSelectCriterion={vi.fn()}/>);
    await settle();
    const box=screen.getByLabelText("Weight derivation for TEAM");
    expect(box).toHaveTextContent(/is an objective, not a leaf/);
    expect(box).toHaveTextContent(/0\.6000 of the overall goal/);
    expect(box).not.toHaveTextContent("global weight of");
  });
  it("offers no derived derivation while a sibling group is invalid",async()=>{
    const ctx=resolveContext(project,"source",{...BASE_SELECTION,profileId:"first",criterionId:"cost"});
    vi.mocked(api.previewWeights).mockResolvedValue({...result,configuration:ctx.configuration,weights_ready:false,
      local_weights:{},global_weights:{},path_shares:{}});
    render(<WeightsPanel project={project} context={ctx} validation={{issues:[]}} busy={false} apply={vi.fn(()=>Promise.resolve(true))}
      manage={vi.fn(()=>Promise.resolve(true))} onSelectProfile={vi.fn()} onSelectCriterion={vi.fn()}/>);
    await settle();
    expect(screen.queryByRole("table",{name:"Derivation steps for COST"})).not.toBeInTheDocument();
    expect(screen.getByLabelText("Weight derivation for COST")).toHaveTextContent(/unavailable until every sibling group is valid/);
  });
  it("reports an unresolved profile reference instead of claiming there is no profile",()=>{
    const dangling=resolveContext(project,"source",BASE_SELECTION);
    render(<WeightsPanel project={project} context={{...dangling,resolvedProfileId:"deleted_analyst"}} validation={{issues:[]}} busy={false}
      apply={vi.fn(()=>Promise.resolve(true))} manage={vi.fn(()=>Promise.resolve(true))} onSelectProfile={vi.fn()} onSelectCriterion={vi.fn()}/>);
    const alert=screen.getByRole("alert");
    expect(alert).toHaveTextContent("deleted_analyst");expect(alert).toHaveTextContent(/No other profile was substituted/);
    expect(screen.queryByText(/has no weight profile/)).not.toBeInTheDocument();
    expect(screen.queryByRole("table",{name:"Swing ratings under top level"})).not.toBeInTheDocument();
  });
});
