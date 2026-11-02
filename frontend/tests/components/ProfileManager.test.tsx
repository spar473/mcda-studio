import { fireEvent, render, screen, act } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProfileManager } from "../../src/components/ProfileManager";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import { projectWith } from "../fixtures";
const project=projectWith([],{analysis:{method:"mavt",scenario_id:null,weight_profile_id:null,parameters:{nested:{p:true}}},weight_profiles:[
  {id:"first",name:"First",method:"swing",judgements:{a:100}},{id:"second",name:"Second",method:"swing",judgements:{a:200}}]});
const context=resolveContext(project,"original",{...BASE_SELECTION,profileId:"first"});
function setup(){const manage=vi.fn(()=>Promise.resolve(true)),onSelect=vi.fn();const props={project,context,busy:false,manage,onSelect};return {...render(<ProfileManager {...props}/>),props,manage,onSelect};}
async function confirm(){await act(async()=>{fireEvent.click(screen.getByRole("button",{name:"Confirm profile change"}));await Promise.resolve();});}
describe("preference-profile commands are explicit and isolated",()=>{
  it("switching is view state and does not change the saved default or project",()=>{
    const before=structuredClone(project);const view=setup();fireEvent.change(screen.getByLabelText("Profile to edit"),{target:{value:"second"}});
    expect(view.onSelect).toHaveBeenCalledWith("second");expect(view.manage).not.toHaveBeenCalled();expect(project).toEqual(before);
  });
  it("creates a deliberately blank profile through a single service operation",async()=>{
    const view=setup();fireEvent.click(screen.getByRole("button",{name:"Create profile"}));expect(screen.getByRole("button",{name:"Confirm profile change"})).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Profile name"),{target:{value:"  Analyst  "}});await confirm();
    expect(view.manage).toHaveBeenCalledWith({op:"create_weight_profile",name:"Analyst"});
  });
  it.each(["duplicate","rename"])("%s targets the stable selected profile ID",async(mode)=>{
    const view=setup();fireEvent.click(screen.getByRole("button",{name:mode==="duplicate"?"Duplicate profile":"Rename profile"}));
    fireEvent.change(screen.getByLabelText("Profile name"),{target:{value:"New name"}});await confirm();
    expect(view.manage).toHaveBeenCalledWith({op:mode==="duplicate"?"duplicate_weight_profile":"rename_weight_profile",profile_id:"first",name:"New name"});
  });
  it("deletion has no preselected replacement and is one atomic reference-update operation",async()=>{
    const view=setup();fireEvent.click(screen.getByRole("button",{name:"Delete profile"}));
    const button=screen.getByRole("button",{name:"Delete and replace references"});expect(button).toBeDisabled();
    expect(screen.getByLabelText("Replacement profile")).toHaveValue("");expect(screen.getByLabelText("Replacement profile")).not.toHaveTextContent("First");
    fireEvent.change(screen.getByLabelText("Replacement profile"),{target:{value:"second"}});
    await act(async()=>{fireEvent.click(button);await Promise.resolve();});
    expect(view.manage).toHaveBeenCalledTimes(1);expect(view.manage).toHaveBeenCalledWith({op:"remove_weight_profile",profile_id:"first",replacement_profile_id:"second"});
  });
  it("changing a saved default requires its own confirmation",async()=>{
    const view=setup();fireEvent.click(screen.getByRole("button",{name:"Use viewed profile as saved default"}));expect(view.manage).not.toHaveBeenCalled();await confirm();
    expect(view.manage).toHaveBeenCalledWith({op:"set_default_weight_profile",profile_id:"first"});expect(project.analysis.weight_profile_id).toBeNull();
  });
  it("cancel, pending state and changed source revisions prevent commands",()=>{
    const view=setup();fireEvent.click(screen.getByRole("button",{name:"Rename profile"}));fireEvent.click(screen.getByRole("button",{name:"Cancel"}));expect(view.manage).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button",{name:"Rename profile"}));view.rerender(<ProfileManager {...view.props} context={{...context,fingerprint:"new"}}/>);
    expect(screen.getByText(/revision changed/)).toBeVisible();expect(screen.getByRole("button",{name:"Confirm profile change"})).toBeDisabled();
  });
  it("the last profile cannot be deleted and no-profile models can create one",()=>{
    const view=setup();view.rerender(<ProfileManager {...view.props} project={{...project,weight_profiles:project.weight_profiles.slice(0,1)}}/>);
    expect(screen.getByRole("button",{name:"Delete profile"})).toBeDisabled();
    view.rerender(<ProfileManager {...view.props} project={{...project,weight_profiles:[]}} context={{...context,resolvedProfileId:null}}/>);
    expect(screen.getByRole("button",{name:"Create profile"})).toBeEnabled();expect(screen.getByRole("button",{name:"Duplicate profile"})).toBeDisabled();
  });
});
