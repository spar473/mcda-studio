import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { ProxyInputs, ProxyInspection, ProxyComparisonBundle } from "../../src/api/types";
import { ProxyCriterionPanel } from "../../src/components/ProxyCriterionPanel";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import inputsJSON from "../fixtures/proxy-inputs.json";
import inspectionJSON from "../fixtures/proxy-inspection.json";
import pairJSON from "../fixtures/proxy-pair.json";
import feasibleInputsJSON from "../fixtures/proxy-feasibility-inputs.json";
import feasiblePairJSON from "../fixtures/proxy-feasibility-pair.json";

const inputs = inputsJSON as ProxyInputs;
const inspection = inspectionJSON as ProxyInspection;
const bundle = pairJSON as ProxyComparisonBundle;
const props = () => ({ project: inputs.project, context: resolveContext(inputs.project, inspection.state.project_fingerprint, BASE_SELECTION), onDirty: vi.fn(), onInputs: vi.fn() });
afterEach(() => vi.restoreAllMocks());
async function open(candidate = inputs) {
  const file = new File([JSON.stringify(candidate)], "proxy-inputs.json");
  Object.defineProperty(file, "text", { value: () => Promise.resolve(JSON.stringify(candidate)) });
  await act(async () => { fireEvent.change(screen.getByLabelText("Open proxy inputs"), { target: { files: [file] } }); await Promise.resolve(); });
  await screen.findByRole("button", { name: "Inspect both proxy copies" });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Inspect both proxy copies" })); await Promise.resolve(); });
}
function mock() { vi.spyOn(api,"inspectProxy").mockResolvedValue(inspection); vi.spyOn(api,"inspectProposals").mockRejectedValue(Error("No proposal sidecar opened")); }
function reviewer() {
  fireEvent.change(screen.getByLabelText("Proxy reviewer"), { target: { value: "Local reviewer" } });
  fireEvent.change(screen.getByLabelText("Proxy review reason"), { target: { value: "Reviewed the card and weight consequences" } });
}
function acknowledge() {
  fireEvent.click(screen.getByLabelText("I acknowledge card")); fireEvent.click(screen.getByLabelText("I acknowledge overlap")); fireEvent.click(screen.getByLabelText("I acknowledge weight changes"));
}
it("starts without activation or nonzero proxy swing ratings", () => {
  const p=props(); render(<ProxyCriterionPanel {...p}/>);
  expect(screen.queryByRole("checkbox", { name: "Enable separate proxy preview" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Prepare an optional proxy declaration" }));
  const state=JSON.parse(screen.getByLabelText<HTMLTextAreaElement>("Proxy declaration JSON").value) as { enabled:boolean; swing_ratings: Record<string,number|null> };
  expect(state.enabled).toBe(false); expect(Object.values(state.swing_ratings)).toEqual([null,null]);
  expect(p.onDirty).toHaveBeenLastCalledWith(true);
});
it("requires every acknowledgement then shows both results with separate axes", async () => {
  mock(); const run=vi.spyOn(api,"runProxy").mockResolvedValue(bundle); render(<ProxyCriterionPanel {...props()}/>); await open(); reviewer();
  const button=screen.getByRole("button",{name:"Run with and without disclosed proxy"});
  expect(button).toBeDisabled(); acknowledge(); expect(button).toBeEnabled();
  await act(async()=>{ fireEvent.click(button); await Promise.resolve(); });
  expect(run).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("region",{name:"Complete proxy pair"})).toBeInTheDocument();
  expect(screen.getAllByRole("meter")).toHaveLength(4);
  fireEvent.change(screen.getByLabelText("Proxy review reason"),{target:{value:"Changed rationale"}});
  expect(screen.queryByRole("region",{name:"Complete proxy pair"})).not.toBeInTheDocument();
  expect(button).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Proxy review reason"),{target:{value:"Reviewed the card and weight consequences"}});
  expect(screen.queryByRole("region",{name:"Complete proxy pair"})).not.toBeInTheDocument();
});
it("ignores a late pair after the configuration changes", async () => {
  mock(); let finish!: (value: ProxyComparisonBundle) => void;
  vi.spyOn(api,"runProxy").mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
  const p=props(); const view=render(<ProxyCriterionPanel {...p}/>); await open(); reviewer(); acknowledge();
  fireEvent.click(screen.getByRole("button",{name:"Run with and without disclosed proxy"}));
  view.rerender(<ProxyCriterionPanel {...p} context={{...p.context, configuration:{...p.context.configuration,weight_profile_id:"quality_led"}}}/>);
  await act(async()=>{finish(bundle);await Promise.resolve();});
  expect(screen.queryByRole("region",{name:"Complete proxy pair"})).not.toBeInTheDocument();
  view.rerender(<ProxyCriterionPanel {...p}/>);
  expect(screen.queryByRole("region",{name:"Complete proxy pair"})).not.toBeInTheDocument();
});
it("does not turn an unacknowledged unknown fact into permission to run", async () => {
  mock(); vi.mocked(api.inspectProxy).mockResolvedValue({...inspection,unknown_facts:["calibration_evidence"]});
  render(<ProxyCriterionPanel {...props()}/>); await open(); reviewer(); acknowledge();
  expect(screen.getByRole("button",{name:"Run with and without disclosed proxy"})).toBeDisabled();
  fireEvent.click(screen.getByLabelText("I acknowledge unknown facts"));
  expect(screen.getByRole("button",{name:"Run with and without disclosed proxy"})).toBeEnabled();
});
it("blocks a run while edited declarations have not been recorded and reviewed", async () => {
  mock(); render(<ProxyCriterionPanel {...props()}/>); await open(); reviewer(); acknowledge();
  expect(screen.getByRole("button",{name:"Run with and without disclosed proxy"})).toBeEnabled();
  fireEvent.change(screen.getByLabelText("Proxy declaration JSON"),{target:{value:JSON.stringify({...inspection.state,score_meaning:"A newly declared meaning"})}});
  acknowledge();
  expect(screen.getByRole("button",{name:"Run with and without disclosed proxy"})).toBeDisabled();
  expect(screen.getByText(/Declaration edits are pending/)).toBeInTheDocument();
});

it("shows a failed requirement beside the proxy-favoured rank, with both halves visible", async () => {
  const source=feasibleInputsJSON as ProxyInputs, result=feasiblePairJSON as ProxyComparisonBundle;
  mock(); vi.mocked(api.inspectProxy).mockResolvedValue(result.inspection);
  vi.spyOn(api,"runProxy").mockResolvedValue(result);
  render(<ProxyCriterionPanel project={source.project} context={resolveContext(source.project,result.inspection.state.project_fingerprint,BASE_SELECTION)} onDirty={vi.fn()}/>);
  await open(source); reviewer(); acknowledge();
  await act(async()=>{fireEvent.click(screen.getByRole("button",{name:"Run with and without disclosed proxy"}));await Promise.resolve();});
  for (const title of ["Without disclosed proxy ranking","With disclosed proxy ranking"]) {
    const table=screen.getByRole("table",{name:title});
    expect(within(table).getByText("fails (Minimum quality)")).toBeVisible();
    expect(within(table).getByText("passes",{exact:true})).toBeVisible();
  }
  const withTable=screen.getByRole("table",{name:"With disclosed proxy ranking"});
  expect(within(withTable).getAllByRole("row")[2]).toHaveTextContent("Option B1");
});
