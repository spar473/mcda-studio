import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { ValueFunctionPreview } from "../../src/api/types";
import { ValueFunctionEditor, type CandidateGuard } from "../../src/components/ValueFunctionEditor";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import { META, node, projectWith, ratioScale } from "../fixtures";
const criterion = node("cost",null,0,{scale:ratioScale,value_function:{kind:"piecewise_linear",out_of_domain:"error",points:[{x:0,value:0},{x:4,value:.3},{x:10,value:1}]}});
const project = projectWith([criterion],{analysis:{method:"mavt",parameters:{},scenario_id:null,weight_profile_id:null}});
const context = resolveContext(project,"source",{...BASE_SELECTION,criterionId:"cost"});
async function settle(){ await act(async()=>{await vi.advanceTimersByTimeAsync(125);}); }
function setup() {
  const apply=vi.fn(()=>Promise.resolve(true)), close=vi.fn(); let guard:CandidateGuard|null=null;
  const onGuard=(next:CandidateGuard|null)=>{guard=next;};
  const props={project,context,node:criterion,meta:META,apply,onClose:close,onGuard};
  const view=render(<ValueFunctionEditor {...props}/>); return {...view,props,apply,close,guard:()=>guard};
}
beforeEach(()=>{
  vi.useFakeTimers();
  vi.spyOn(api,"previewValueFunction").mockImplementation((request)=>Promise.resolve({
    project_fingerprint:context.fingerprint,configuration:request.configuration,weight_profile_id:null,scenario_id:null,
    criterion_id:"cost",candidate:request.candidate,candidate_fingerprint:"candidate",effective_scale:ratioScale,
    effective_value_function:criterion.value_function,resolved_domain:{lower:0,upper:10,source:"control_points"},
    curve_ready:true,readiness:"ready",measurement_readiness:"ready",measurements_complete:true,
    samples:[{measurement:0,partial_value:0},{measurement:4,partial_value:.3},{measurement:10,partial_value:1}],
    markers:[{alternative_id:"server",raw_measurement:2,partial_value:.137,clamped:false}],diagnostics:[]
  } as ValueFunctionPreview));
});
afterEach(()=>{vi.restoreAllMocks();vi.useRealTimers();});
describe("linked editor transaction and provenance",()=>{
  it("shows backend partial values, never edits before Apply, and commits a single batch",async()=>{
    const view=setup(); await settle(); const before=structuredClone(project);
    expect(screen.getByRole("table",{name:"Candidate alternative values"})).toHaveTextContent("0.137");
    fireEvent.change(screen.getByLabelText("Point 2 preference"),{target:{value:".4"}});
    expect(screen.queryByTestId("preference-curve")).not.toBeInTheDocument(); expect(view.apply).not.toHaveBeenCalled();
    expect(view.guard()?.dirty).toBe(true); await settle();
    expect(screen.getByRole("button",{name:"Apply candidate"})).toBeDisabled();
    fireEvent.click(screen.getByLabelText("Acknowledge candidate range change"));
    fireEvent.click(screen.getByRole("button",{name:"Apply candidate"}));await act(async()=>{await Promise.resolve();});
    expect(view.apply).toHaveBeenCalledTimes(1);expect(view.apply.mock.calls[0]).toEqual([[{op:"set_scale",criterion_id:"cost",scale:ratioScale},
      {op:"set_value_function",criterion_id:"cost",value_function:{kind:"piecewise_linear",out_of_domain:"error",points:[{x:0,value:0},{x:4,value:.4},{x:10,value:1}]}}]]);
    expect(view.close).toHaveBeenCalledTimes(1);expect(project).toEqual(before);
  });
  it("keeps invalid text visible and prevents save from applying its fallback",async()=>{
    const view=setup();await settle();fireEvent.change(screen.getByLabelText("Point 2 preference"),{target:{value:"-"}});await settle();
    fireEvent.change(screen.getByLabelText("Candidate endpoint convention"),{target:{value:"decreasing"}});
    expect(screen.getByLabelText("Point 2 preference")).toHaveValue("-");expect(screen.queryByTestId("preference-curve")).not.toBeInTheDocument();
    let ok=true;await act(async()=>{ok=await view.guard()?.commit() ?? false;});expect(ok).toBe(false);expect(view.apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button",{name:"Cancel candidate"}));expect(view.close).toHaveBeenCalled();
  });
  it("resets candidate acknowledgement when the judgement changes again",async()=>{
    setup();await settle();fireEvent.change(screen.getByLabelText("Point 2 measurement"),{target:{value:"5"}});await settle();
    fireEvent.click(screen.getByLabelText("Acknowledge candidate range change"));expect(screen.getByRole("button",{name:"Apply candidate"})).toBeEnabled();
    fireEvent.change(screen.getByLabelText("Point 2 measurement"),{target:{value:"6"}});await settle();
    expect(screen.getByLabelText("Acknowledge candidate range change")).not.toBeChecked();expect(screen.getByRole("button",{name:"Apply candidate"})).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Point 2 measurement"),{target:{value:"5"}});await settle();
    expect(screen.getByLabelText("Acknowledge candidate range change")).not.toBeChecked();
  });
  it("blocks context changes even with a valid response for the new context",async()=>{
    const view=setup();await settle();fireEvent.change(screen.getByLabelText("Point 2 measurement"),{target:{value:"5"}});await settle();
    view.rerender(<ValueFunctionEditor {...view.props} context={{...context,fingerprint:"changed"}}/>);
    expect(screen.getByText(/context changed while this editor/)).toBeVisible();expect(screen.queryByTestId("preference-curve")).not.toBeInTheDocument();
    expect(screen.getByRole("button",{name:"Apply candidate"})).toBeDisabled();
  });
  it("keyboard inputs are candidates and Escape cancels without mutation",async()=>{
    const view=setup();await settle();fireEvent.keyDown(screen.getByRole("slider",{name:"Control point 2"}),{key:"ArrowUp"});
    expect(screen.getByLabelText("Point 2 preference")).toHaveValue("0.31");expect(view.apply).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByRole("slider",{name:"Control point 2"}),{key:"Escape"});expect(view.close).toHaveBeenCalled();
  });
  it("does not apply an incomplete local preview",async()=>{
    vi.mocked(api.previewValueFunction).mockImplementation((request)=>Promise.resolve({project_fingerprint:"source",configuration:context.configuration,
      criterion_id:"cost",scenario_id:null,weight_profile_id:null,candidate:request.candidate,candidate_fingerprint:"x",effective_scale:ratioScale,
      effective_value_function:criterion.value_function,resolved_domain:null,curve_ready:false,readiness:"incomplete",measurement_readiness:"incomplete",
      measurements_complete:false,samples:[],markers:[],diagnostics:[]} as ValueFunctionPreview));
    setup();await settle();fireEvent.change(screen.getByLabelText("Point 2 preference"),{target:{value:".4"}});await settle();
    fireEvent.click(screen.getByLabelText("Acknowledge candidate range change"));expect(screen.getByRole("button",{name:"Apply candidate"})).toBeDisabled();
    expect(screen.getByText("Function incomplete")).toBeVisible();
  });
});
