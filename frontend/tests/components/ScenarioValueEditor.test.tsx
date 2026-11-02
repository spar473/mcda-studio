import {act,fireEvent,render,screen} from "@testing-library/react";
import {beforeEach,afterEach,expect,it,vi} from "vitest";
import {api} from "../../src/api/client";
import type {ValueFunctionPreview} from "../../src/api/types";
import {ValueFunctionEditor} from "../../src/components/ValueFunctionEditor";
import {BASE_SELECTION,resolveContext} from "../../src/state/analysisContext";
import {META,node,projectWith,ratioScale} from "../fixtures";
const criterion=node("cost",null,0,{scale:ratioScale,value_function:{kind:"piecewise_linear",points:[{x:0,value:0},{x:4,value:.3},{x:10,value:1}],out_of_domain:"error"}});
const project=projectWith([criterion],{analysis:{method:"mavt",scenario_id:null,weight_profile_id:null,parameters:{}},scenarios:[{id:"s",name:"S",weight_profile_id:null,value_function_overrides:{}}]});
const context=resolveContext(project,"source",{...BASE_SELECTION,scenarioId:"s",criterionId:"cost"});
async function settle(){await act(async()=>{await vi.advanceTimersByTimeAsync(125);});}
beforeEach(()=>{vi.useFakeTimers();vi.spyOn(api,"previewValueFunction").mockImplementation(request=>Promise.resolve({project_fingerprint:"source",configuration:context.configuration,
 scenario_id:"s",weight_profile_id:null,criterion_id:"cost",candidate:request.candidate,candidate_fingerprint:"candidate",effective_scale:ratioScale,effective_value_function:request.candidate?.value_function,
 resolved_domain:{lower:0,upper:10,source:"fixed"},curve_ready:true,readiness:"ready",measurement_readiness:"ready",measurements_complete:true,samples:[{measurement:0,partial_value:0},{measurement:10,partial_value:1}],markers:[],diagnostics:[]} as ValueFunctionPreview));});
afterEach(()=>{vi.restoreAllMocks();vi.useRealTimers();});
it("commits a scenario function only and locks shared base scale/units/anchors",async()=>{
 const before=structuredClone(project),apply=vi.fn(()=>Promise.resolve(true));
 render(<ValueFunctionEditor project={project} context={context} node={criterion} meta={META} apply={apply} onClose={vi.fn()} onGuard={vi.fn()} targetScenarioId="s"/>);await settle();
 expect(screen.getByLabelText("Candidate unit")).toBeDisabled();
 fireEvent.change(screen.getByLabelText("Candidate representation"),{target:{value:"linear"}});await settle();
 expect(screen.getByLabelText("Candidate anchors")).toBeDisabled();expect(screen.getByLabelText("Candidate lower")).toHaveAttribute("readonly");expect(screen.queryByRole("slider")).not.toBeInTheDocument();
 fireEvent.click(screen.getByLabelText("Acknowledge candidate range change"));await act(async()=>{fireEvent.click(screen.getByRole("button",{name:"Apply candidate"}));await Promise.resolve();});
 expect(apply).toHaveBeenCalledWith([{op:"set_scenario_override",scenario_id:"s",criterion_id:"cost",value_function:{kind:"linear",direction:"increasing",out_of_domain:"error"}}]);expect(project).toEqual(before);
});
