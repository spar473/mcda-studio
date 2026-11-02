import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { CalculationApplication, CalculationInspection, DerivedCompilation, DerivedPreview } from "../../src/api/types";
import { parseDimension } from "../../src/components/CalculationWorkspaceView";
import { DerivedMeasurementsPanel } from "../../src/components/DerivedMeasurementsPanel";
import { project } from "../results/fixture";

beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

const source = { name: "Note", reference: "local:note", location: "", date: "2026-11-01", description: "Synthetic", classification: "unknown" as const };
const review = { status: "accepted" as const, reviewer: "Reviewer", reviewed_at: "2026-11-01T00:00:00Z", corrected_value: null, note: "" };
const model: DerivedPreview["model"] = { schema_version: 1, project_fingerprint: "fp", units: { NZD: { NZD: 1 } }, sources: [
  { id: "price", value: 10, unit: "NZD", source, origin: { kind: "human", proposed_by: "Author", tool_id: null, tool_version: null }, review },
  { id: "years", value: 10, unit: "1", source, origin: { kind: "tool", proposed_by: "Operator", tool_id: "extractor", tool_version: "0.1" }, review: null },
], formulas: [{ id: "cost", expression: "price * years", unit: "NZD", origin: { kind: "human", proposed_by: "Author", tool_id: null, tool_version: null }, review, alternative_id: "a", criterion_id: "cost" }] };
const preview: DerivedPreview = { project_fingerprint: "fp", model_digest: "model", review_digest: "review", model,
  calculations: [{ id: "cost", expression: "price * years", value: 100, unit: "NZD", dimension: { NZD: 1 }, dependencies: ["price", "years"], source_ids: ["price", "years"], alternative_id: "a", criterion_id: "cost", before: 80 }],
  issues: [], limitations: ["Deterministic only."] };
const workspace: CalculationInspection["workspace"] = { workspace_version: 1, source_project: project, original_model: model, events: [], digest: "w0" };
const inspection: CalculationInspection = { workspace, model, preview, relationship: "bound", bindings: ["fp"],
  factor_uses: [{ factor_id: "price", formula_ids: ["cost"], alternative_ids: ["a", "b"], shared: true }, { factor_id: "years", formula_ids: ["cost"], alternative_ids: ["a"], shared: false }],
  checks: [{ formula_id: "cost", references: ["price", "years"], status: "calculates", value: 100, dimension: { NZD: 1 }, issue: null, explanation: "Calculates 100 NZD; its dimensions (NZD) match the declared unit." }],
  changes: [{ formula_id: "cost", alternative_id: "a", criterion_id: "cost", before: 80, after: 100, changed: true }], applicable: true, workspace_exportable: true };
const bundle: DerivedCompilation = { compilation_version: 1, source_project: project, project, preview, compiled_fingerprint: "applied", digest: "bundle" };

async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(125); }); }

async function chooseFile(text = "{}") {
  const file = new File([text], "model.json", { type: "application/json" });
  Object.defineProperty(file, "text", { value: () => Promise.resolve(text) });
  await act(async () => { fireEvent.change(screen.getByLabelText("Calculation model"), { target: { files: [file] } }); await Promise.resolve(); });
  await settle();
}

function name(value = "Analyst") { fireEvent.change(screen.getByLabelText("Your name (recorded with each change)"), { target: { value } }); }

it("makes no calculation request until a file is chosen, then explains sources and sharing", async () => {
  const spy = vi.spyOn(api, "inspectCalculations").mockResolvedValue(inspection);
  render(<DerivedMeasurementsPanel project={project} fingerprint="fp"/>);
  await settle();
  expect(spy).not.toHaveBeenCalled();
  await chooseFile();
  expect(spy).toHaveBeenCalledWith(project, {}, expect.any(AbortSignal));
  expect(screen.getByLabelText("Calculated measurements", { exact: true })).toHaveTextContent("Source factors: price, years");
  expect(screen.getByLabelText("Calculation source inputs")).toHaveTextContent("Shared across alternatives: one value, one review.");
  expect(screen.getByLabelText("Calculation source inputs")).toHaveTextContent("Proposed by Operator (tool proposal), tool extractor 0.1");
  expect(screen.getByLabelText("Check for cost")).toHaveTextContent("Check: Calculates 100 NZD");
  expect(within(screen.getByLabelText("Measurement changes")).getByText("Would change")).toBeInTheDocument();
  expect(screen.getByText("Deterministic only.")).toBeInTheDocument();
});

it("starts a blank model bound to the open revision", async () => {
  const spy = vi.spyOn(api, "inspectCalculations").mockResolvedValue({ ...inspection, model: { ...model, units: {}, sources: [], formulas: [] } });
  render(<DerivedMeasurementsPanel project={project} fingerprint="fp"/>);
  fireEvent.click(screen.getByRole("button", { name: "Start a new calculation model" }));
  await settle();
  expect(spy).toHaveBeenCalledWith(project, { schema_version: 1, project_fingerprint: "fp", units: {}, sources: [], formulas: [] }, expect.any(AbortSignal));
});

it("hides a calculation from another project revision", async () => {
  vi.spyOn(api, "inspectCalculations").mockResolvedValue({ ...inspection, preview: { ...preview, project_fingerprint: "old" } });
  render(<DerivedMeasurementsPanel project={project} fingerprint="fp"/>);
  await chooseFile();
  expect(screen.getByRole("alert")).toHaveTextContent("does not match");
  expect(screen.queryByText("price * years")).not.toBeInTheDocument();
});

it("records a revision as a pending proposal, guards it until export and can discard it", async () => {
  vi.spyOn(api, "inspectCalculations").mockResolvedValue(inspection);
  const pending = { ...inspection, workspace: { ...workspace, digest: "w1" }, applicable: false };
  const propose = vi.spyOn(api, "proposeCalculation").mockResolvedValue(pending);
  const onDirty = vi.fn();
  render(<DerivedMeasurementsPanel project={project} fingerprint="fp" onDirty={onDirty}/>);
  await chooseFile();
  expect(screen.getByRole("button", { name: "Revise price" })).toBeDisabled();
  name();
  fireEvent.click(screen.getByRole("button", { name: "Revise price" }));
  const form = screen.getByRole("form", { name: "Revise factor price" });
  fireEvent.change(within(form).getByLabelText("Value"), { target: { value: "12.5" } });
  await act(async () => { fireEvent.click(within(form).getByRole("button", { name: "Record factor definition" })); await Promise.resolve(); });
  const event = propose.mock.calls[0]?.[2];
  expect(event).toMatchObject({ kind: "source", factor: { id: "price", value: 12.5, review: null, origin: { kind: "human", proposed_by: "Analyst" } } });
  expect(propose.mock.calls[0]?.[3]).toBe("review");
  expect(onDirty).toHaveBeenLastCalledWith(true);
  expect(screen.getByText(/Calculation changes have not been exported/)).toBeInTheDocument();
  expect(screen.getByLabelText("Calculation model")).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Discard calculation changes since export" }));
  expect(onDirty).toHaveBeenLastCalledWith(false);
});

it("records tool proposals with their identity and factor corrections as numbers", async () => {
  vi.spyOn(api, "inspectCalculations").mockResolvedValue(inspection);
  const propose = vi.spyOn(api, "proposeCalculation").mockResolvedValue(inspection);
  render(<DerivedMeasurementsPanel project={project} fingerprint="fp"/>);
  await chooseFile(); name();
  fireEvent.click(screen.getByRole("button", { name: "Add source factor" }));
  const form = screen.getByRole("form", { name: "New source factor" });
  for (const [label, value] of [["Factor ID (used in formulas)", "share"], ["Value", "0.2"], ["Source name", "Report"], ["Source reference", "doc:1"], ["Source description", "Market share"]] as const)
    fireEvent.change(within(form).getByLabelText(label), { target: { value } });
  fireEvent.change(within(form).getByLabelText("Proposed by"), { target: { value: "tool" } });
  fireEvent.change(within(form).getByLabelText("Tool ID"), { target: { value: "extractor" } });
  await act(async () => { fireEvent.click(within(form).getByRole("button", { name: "Record factor definition" })); await Promise.resolve(); });
  expect(propose.mock.calls[0]?.[2]).toMatchObject({ factor: { id: "share", value: 0.2, origin: { kind: "tool", proposed_by: "Analyst", tool_id: "extractor" } } });
  await settle();
  fireEvent.click(screen.getByRole("button", { name: "Review years" }));
  const reviewForm = screen.getByRole("form", { name: "Review factor years" });
  fireEvent.change(within(reviewForm).getByLabelText("Review decision"), { target: { value: "corrected" } });
  fireEvent.change(within(reviewForm).getByLabelText("Corrected value"), { target: { value: "8" } });
  await act(async () => { fireEvent.click(within(reviewForm).getByRole("button", { name: "Record review" })); await Promise.resolve(); });
  expect(propose.mock.calls[1]?.[2]).toMatchObject({ kind: "review", entry: "source", id: "years", review: { status: "corrected", corrected_value: 8, reviewer: "Analyst" } });
});

it("shows a refused acceptance with Python's explanation and records nothing", async () => {
  vi.spyOn(api, "inspectCalculations").mockResolvedValue(inspection);
  const onDirty = vi.fn();
  vi.spyOn(api, "proposeCalculation").mockRejectedValue(new Error("CALCULATION_ACCEPT_INVALID: formula 'cost' does not calculate. The expression gives customer."));
  render(<DerivedMeasurementsPanel project={project} fingerprint="fp" onDirty={onDirty}/>);
  await chooseFile(); name();
  fireEvent.click(screen.getByRole("button", { name: "Review cost" }));
  expect(within(screen.getByRole("form", { name: "Review formula cost" })).queryByRole("option", { name: "Accept a corrected value" })).not.toBeInTheDocument();
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Record review" })); await Promise.resolve(); });
  expect(screen.getByRole("alert")).toHaveTextContent("The expression gives customer");
  expect(onDirty).not.toHaveBeenCalledWith(true);
});

it("discards a late proposal after the project revision changes", async () => {
  vi.spyOn(api, "inspectCalculations").mockResolvedValue(inspection);
  let done!: (value: CalculationInspection) => void;
  vi.spyOn(api, "proposeCalculation").mockImplementation(() => new Promise(resolve => { done = resolve; }));
  const onDirty = vi.fn();
  const view = render(<DerivedMeasurementsPanel project={project} fingerprint="fp" onDirty={onDirty}/>);
  await chooseFile(); name();
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Remove years" })); await Promise.resolve(); });
  view.rerender(<DerivedMeasurementsPanel project={project} fingerprint="new" onDirty={onDirty}/>);
  await act(async () => { done(inspection); await Promise.resolve(); });
  expect(onDirty).not.toHaveBeenCalledWith(true);
});

const application: CalculationApplication = { inspection: { ...inspection, workspace: { ...workspace, digest: "w2" }, applicable: false },
  assignments: [{ alternative_id: "a", criterion_id: "cost", value: 100 }], project_fingerprint: "applied", bundle };

it("applies only after acknowledgement, through one editor edit, and records only a matching result", async () => {
  const inspect = vi.spyOn(api, "inspectCalculations").mockResolvedValue(inspection);
  const apply = vi.spyOn(api, "applyCalculation").mockResolvedValue(application);
  const onApply = vi.fn().mockResolvedValue("applied");
  const onDirty = vi.fn();
  const view = render(<DerivedMeasurementsPanel project={project} fingerprint="fp" onApply={onApply} onDirty={onDirty}/>);
  await chooseFile(); name();
  expect(screen.getByRole("button", { name: "Apply to this project" })).toBeDisabled();
  fireEvent.click(screen.getByLabelText("I reviewed every measurement change to apply"));
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Apply to this project" })); await Promise.resolve(); await Promise.resolve(); });
  expect(apply).toHaveBeenCalledWith(project, workspace, "review", "Analyst", expect.any(String));
  expect(onApply).toHaveBeenCalledWith(application.assignments);
  expect(onDirty).toHaveBeenLastCalledWith(true);
  inspect.mockResolvedValue({ ...application.inspection, preview: { ...preview, project_fingerprint: "applied" } });
  view.rerender(<DerivedMeasurementsPanel project={project} fingerprint="applied" onApply={onApply} onDirty={onDirty}/>);
  await settle();
  expect(inspect).toHaveBeenLastCalledWith(project, application.inspection.workspace, expect.any(AbortSignal));
  expect(screen.getByRole("button", { name: "Export calculation bundle for this application" })).toBeInTheDocument();
  // Exporting the workspace clears the unexported-history guard.
  fireEvent.click(screen.getByRole("button", { name: "Export calculation workspace" }));
  expect(onDirty).toHaveBeenLastCalledWith(false);
});

it("refuses to record an application whose project edit differs or failed", async () => {
  vi.spyOn(api, "inspectCalculations").mockResolvedValue(inspection);
  vi.spyOn(api, "applyCalculation").mockResolvedValue(application);
  for (const [result, text] of [["other", "does not match the reviewed application"], [null, "was not applied"]] as const) {
    const onDirty = vi.fn();
    const view = render(<DerivedMeasurementsPanel project={project} fingerprint="fp" onApply={vi.fn().mockResolvedValue(result)} onDirty={onDirty}/>);
    await chooseFile(); name();
    fireEvent.click(screen.getByLabelText("I reviewed every measurement change to apply"));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Apply to this project" })); await Promise.resolve(); await Promise.resolve(); });
    expect(screen.getByRole("alert")).toHaveTextContent(text);
    expect(onDirty).not.toHaveBeenCalledWith(true);
    view.unmount();
  }
});

it("blocks editing an earlier revision and offers an explicit rebind", async () => {
  vi.spyOn(api, "inspectCalculations").mockResolvedValue({ ...inspection, relationship: "earlier", checks: [], applicable: false });
  const propose = vi.spyOn(api, "proposeCalculation").mockResolvedValue(inspection);
  render(<DerivedMeasurementsPanel project={project} fingerprint="fp" onApply={vi.fn()}/>);
  await chooseFile(); name();
  expect(screen.getByRole("alert")).toHaveTextContent("earlier revision");
  expect(screen.getByRole("button", { name: "Revise price" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: "Apply to this project" })).not.toBeInTheDocument();
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Rebind workspace to the open project" })); await Promise.resolve(); });
  expect(propose.mock.calls[0]?.[2]).toMatchObject({ kind: "rebind", project, recorded_by: "Analyst" });
});

it("requires target review before compiling a separate copy, using the exact backend digest", async () => {
  vi.spyOn(api, "inspectCalculations").mockResolvedValue(inspection);
  const compile = vi.spyOn(api, "compileDerived").mockResolvedValue(bundle);
  render(<DerivedMeasurementsPanel project={project} fingerprint="fp"/>);
  await chooseFile();
  expect(screen.getByText(/Current measurement: 80 → calculated estimate: 100/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Compile reviewed copy" })).toBeDisabled();
  fireEvent.click(screen.getByLabelText("I reviewed all target changes for the separate copy"));
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Compile reviewed copy" })); await Promise.resolve(); });
  expect(compile).toHaveBeenCalledWith(project, model, "review");
  expect(screen.getByRole("button", { name: "Export calculation bundle" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Recalculate preview" }));
  await settle();
  expect(screen.queryByRole("button", { name: "Export calculation bundle" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Compile reviewed copy" })).toBeDisabled();
});

it("never exports a compilation for another review digest", async () => {
  vi.spyOn(api, "inspectCalculations").mockResolvedValue(inspection);
  vi.spyOn(api, "compileDerived").mockResolvedValue({ ...bundle, preview: { ...preview, review_digest: "wrong" } });
  render(<DerivedMeasurementsPanel project={project} fingerprint="fp"/>);
  await chooseFile();
  fireEvent.click(screen.getByLabelText("I reviewed all target changes for the separate copy"));
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Compile reviewed copy" })); await Promise.resolve(); });
  expect(screen.getByRole("alert")).toHaveTextContent("does not match the reviewed preview");
  expect(screen.queryByRole("button", { name: "Export compiled project copy" })).not.toBeInTheDocument();
});

it("does not offer applying or compiling an invalid calculation", async () => {
  vi.spyOn(api, "inspectCalculations").mockResolvedValue({ ...inspection, applicable: false,
    preview: { ...preview, issues: [{ severity: "error", code: "DERIVED_UNREVIEWED_SOURCE", message: "Accept the factor first", path: "" }] } });
  render(<DerivedMeasurementsPanel project={project} fingerprint="fp" onApply={vi.fn()}/>);
  await chooseFile();
  expect(screen.getAllByRole("alert")[0]).toHaveTextContent("DERIVED_UNREVIEWED_SOURCE");
  expect(screen.queryByRole("button", { name: "Compile reviewed copy" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Apply to this project" })).not.toBeInTheDocument();
});

it("relates a reopened calculation bundle to the current project through Python only", async () => {
  vi.spyOn(api, "previewDerived").mockResolvedValue(preview);
  const bind = vi.spyOn(api, "bindArtifact").mockResolvedValue({ artifact_kind: "calculation_bundle", artifact_digest: "bundle", source_fingerprint: "source",
    compiled_fingerprint: "compiled", current_fingerprint: "fp", relationship: "different", copy_receipt: null });
  render(<DerivedMeasurementsPanel project={project} fingerprint="fp"/>);
  await chooseFile(JSON.stringify(bundle));
  expect(bind).toHaveBeenCalledWith(project, bundle, null, expect.any(AbortSignal));
  expect(screen.getByLabelText("Calculation bundle provenance")).toHaveTextContent("historical inspection only");
});

it("parses unit dimensions for Python to validate", () => {
  expect(parseDimension("NZD customer^-1 year^-1")).toEqual({ NZD: 1, customer: -1, year: -1 });
  expect(parseDimension("m × m")).toEqual({ m: 2 });
  expect(parseDimension("NZD^x")).toBeNull();
});
