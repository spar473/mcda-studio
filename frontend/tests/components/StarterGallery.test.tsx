import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { StarterMaterialization, StarterTemplate } from "../../src/api/types";
import { StarterGallery } from "../../src/components/StarterGallery";
import * as downloads from "../../src/components/results/downloads";
import catalogJSON from "../fixtures/starter-catalog.json";
import freshJSON from "../fixtures/starter-fresh.json";
const catalog=catalogJSON as StarterTemplate[];
const fresh=freshJSON as StarterMaterialization;
afterEach(() => vi.restoreAllMocks());
const props=()=>({title:"My illustrative decision",description:"",decisionMaker:"",onOpen:vi.fn()});
function mocks() {
  vi.spyOn(api,"starterTemplates").mockResolvedValue(catalog);
  vi.spyOn(api,"instantiateStarter").mockResolvedValue(fresh);
  vi.spyOn(downloads,"saveDownload").mockImplementation(()=>undefined);
}
it("shows eight real starters and leaves optional unattached materials off",async()=>{
  mocks();render(<StarterGallery {...props()}/>);
  await screen.findByRole("button",{name:"Create my project — Venture screening"});
  await screen.findByRole("button",{name:"Create my project — Venture screening: evidence and model workflows (invented data)"});
  await screen.findByRole("button",{name:"Create my project — Clinic site selection"});
  await screen.findByRole("button",{name:"Create my project — Flood defence options"});
  await screen.findByRole("button",{name:"Create my project — Engineering trade study"});
  expect(screen.getAllByRole("article")).toHaveLength(8);
  expect(screen.getAllByRole("checkbox").every(item=>!(item as HTMLInputElement).checked)).toBe(true);
  expect(screen.queryByText(/coming soon|placeholder/i)).not.toBeInTheDocument();
});
it("creates an unreviewed draft with empty optional selection, can export lineage, and saves that exact project",async()=>{
  mocks();vi.spyOn(api,"listProjects").mockResolvedValue({projects:[],unreadable:[]});
  const imported=vi.spyOn(api,"importProject").mockResolvedValue({} as Awaited<ReturnType<typeof api.importProject>>);
  const p=props();render(<StarterGallery {...p}/>);
  const prepare=await screen.findByRole("button",{name:"Create my project — Venture screening: evidence and model workflows (invented data)"});
  await act(async()=>{fireEvent.click(prepare);await Promise.resolve();});
  expect(api.instantiateStarter).toHaveBeenCalledWith({template_id:"venture_screening",mode:"fresh",optional_artifact_ids:[],title:p.title,description:"",decision_maker:""});
  expect(screen.getByLabelText("Starter lineage")).toHaveTextContent("Fresh unreviewed project");
  // Opening no longer waits for a download (owner decision 5); downloading stays available.
  expect(screen.getByRole("button",{name:"Save and open prepared project"})).toBeEnabled();
  fireEvent.click(screen.getByRole("button",{name:"Download materials and lineage"}));
  expect(downloads.saveDownload).toHaveBeenCalledTimes(1);
  await act(async()=>{fireEvent.click(screen.getByRole("button",{name:"Save and open prepared project"}));await Promise.resolve();});
  expect(imported).toHaveBeenCalledWith(fresh.project);
  expect(p.onOpen).toHaveBeenCalledWith(fresh.project.id);
});
it("reopens and verifies portable materials with their exact reset receipt",async()=>{
  mocks();vi.spyOn(api,"verifyStarter").mockResolvedValue(fresh);
  render(<StarterGallery {...props()}/>);
  const file=new File([JSON.stringify(fresh)],"materials.json");Object.defineProperty(file,"text",{value:()=>Promise.resolve(JSON.stringify(fresh))});
  await act(async()=>{fireEvent.change(screen.getByLabelText("Reopen starter materials and lineage"),{target:{files:[file]}});await Promise.resolve();});
  expect(api.verifyStarter).toHaveBeenCalledWith(fresh);
  expect(screen.getByLabelText("Starter lineage")).toHaveTextContent(fresh.receipt.project_fingerprint);
});
it("opens a worked example in one action, with no download first",async()=>{
  mocks();vi.spyOn(api,"listProjects").mockResolvedValue({projects:[],unreadable:[]});
  const imported=vi.spyOn(api,"importProject").mockResolvedValue({} as Awaited<ReturnType<typeof api.importProject>>);
  const p=props();render(<StarterGallery {...p}/>);
  const open=await screen.findByRole("button",{name:"Open worked example — Venture screening"});
  await act(async()=>{fireEvent.click(open);await Promise.resolve();await Promise.resolve();await Promise.resolve();});
  expect(api.instantiateStarter).toHaveBeenCalledWith(expect.objectContaining({template_id:"venture_screening_study",mode:"worked_example"}));
  expect(imported).toHaveBeenCalledWith(fresh.project);
  expect(p.onOpen).toHaveBeenCalledWith(fresh.project.id);
  expect(downloads.saveDownload).not.toHaveBeenCalled();
});
