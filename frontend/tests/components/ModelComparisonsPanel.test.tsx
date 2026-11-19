import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { ModelComparisonCompilation, ModelComparisonInspection } from "../../src/api/types";
import { ModelComparisonsPanel } from "../../src/components/ModelComparisonsPanel";
import * as downloads from "../../src/components/results/downloads";
import inspectionJSON from "../fixtures/model-inspection.json";
import bundleJSON from "../fixtures/model-bundle.json";

const inspection = inspectionJSON as ModelComparisonInspection;
const bundle = bundleJSON as ModelComparisonCompilation;
const project = bundle.source_project;
const props = () => ({ project, fingerprint: inspection.current_fingerprint, onDirty: vi.fn(), onComparison: vi.fn() });
afterEach(() => vi.restoreAllMocks());
async function choose() {
  const file = new File([JSON.stringify(inspection.comparison)], "models.json");
  Object.defineProperty(file, "text", { value: () => Promise.resolve(JSON.stringify(inspection.comparison)) });
  await act(async () => { fireEvent.change(screen.getByLabelText("Model comparison or historical bundle"), { target: { files: [file] } }); await Promise.resolve(); });
  await screen.findByText("Which assumptions explain these model estimates?");
}
function mocks() { vi.spyOn(api, "inspectModels").mockResolvedValue(inspection); }
function fill() {
  fireEvent.change(screen.getByLabelText("Model reviewer"), { target: { value: "Illustrative reviewer" } });
  fireEvent.change(screen.getByLabelText("Model review rationale"), { target: { value: "Reviewed target scope" } });
  fireEvent.change(screen.getByLabelText("Selected model output"), { target: { value: "right" } });
  fireEvent.change(screen.getByLabelText("Target alternative"), { target: { value: "a" } });
  fireEvent.change(screen.getByLabelText("Target criterion"), { target: { value: "annual" } });
  fireEvent.click(screen.getByLabelText(/I reviewed this exact population/));
  fireEvent.click(screen.getByLabelText(/I reviewed both declarations/));
}
it("retains overlapping ranges and starts without an output or target selection", async () => {
  mocks(); render(<ModelComparisonsPanel {...props()}/>); await choose();
  expect(screen.getByLabelText("Selected model output")).toHaveValue("");
  expect(screen.getByLabelText("Target alternative")).toHaveValue("");
  expect(screen.getByText("support_enclosure")).toBeInTheDocument();
  expect(screen.getByText("source_interval")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Compile selected output into a separate copy" })).toBeDisabled();
  expect(screen.getByLabelText("Model questions")).toHaveTextContent("Which assumptions explain these model estimates?");
});
it("requires both acknowledgements and compiles the exact selected cell then invalidates a changed target", async () => {
  mocks(); const compile=vi.spyOn(api,"compileModels").mockResolvedValue(bundle);
  vi.spyOn(downloads,"saveDownload").mockImplementation(() => undefined);
  render(<ModelComparisonsPanel {...props()}/>); await choose();
  fill();
  expect(screen.getByLabelText("Model selection measurement diff")).toHaveTextContent("600000 → selected output: 1000000");
  fireEvent.click(screen.getByLabelText(/I reviewed both declarations/));
  expect(screen.getByRole("button", { name: "Compile selected output into a separate copy" })).toBeDisabled();
  fireEvent.click(screen.getByLabelText(/I reviewed both declarations/));
  await act(async () => { fireEvent.click(screen.getByRole("button",{name:"Compile selected output into a separate copy"})); await Promise.resolve(); });
  expect(compile).toHaveBeenCalledWith(project, inspection.comparison, expect.objectContaining({side:"right",alternative_id:"a",criterion_id:"annual",target_scope:inspection.comparison.right.scope}), inspection.review_digest);
  expect(screen.getByLabelText("Model selection result")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Target alternative"), { target: { value: "b" } });
  expect(screen.queryByLabelText("Model selection result")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Compile selected output into a separate copy" })).toBeDisabled();
});
it("does not publish a late review into a changed project context", async () => {
  mocks(); let finish!: (value: ModelComparisonInspection) => void;
  vi.spyOn(api,"reviewModels").mockImplementation(() => new Promise(resolve => { finish=resolve; }));
  const p=props(); const view=render(<ModelComparisonsPanel {...p}/>); await choose(); fill();
  fireEvent.click(screen.getByRole("button",{name:"Accept comparison declarations"}));
  const changed={...inspection,current_fingerprint:"changed_revision",stale:true};
  vi.mocked(api.inspectModels).mockResolvedValue(changed);
  view.rerender(<ModelComparisonsPanel {...p} fingerprint="changed_revision"/>);
  await act(async () => { finish({...inspection,comparison:{...inspection.comparison,label:"Late review must stay historical"}}); await Promise.resolve(); });
  expect(screen.queryByText("Late review must stay historical")).not.toBeInTheDocument();
  expect(p.onDirty).not.toHaveBeenCalledWith(true);
});
