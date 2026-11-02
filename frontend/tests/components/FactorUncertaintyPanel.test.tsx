import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { CalculationInspection, FactorRunParameters, FactorRunRecord, FactorUncertaintyModel } from "../../src/api/types";
import { FactorUncertaintyPanel } from "../../src/components/FactorUncertaintyPanel";
import * as downloads from "../../src/components/results/downloads";
import { project, record } from "../results/fixture";

const origin = { kind: "human" as const, proposed_by: "Analyst", tool_id: null, tool_version: null };
const model: CalculationInspection["model"] = { schema_version: 1, project_fingerprint: "fp", units: {}, sources: [
  { id: "x", value: 0.5, unit: "1", origin, source: { name: "Note", reference: "local:note", location: "", date: "2026-11-01", description: "Synthetic", classification: "unknown" }, review: null },
], formulas: [] };
const inspection: CalculationInspection = { model, workspace: { workspace_version: 1, source_project: project, original_model: model, events: [], digest: "w" }, preview: { model, project_fingerprint: "fp", model_digest: "model", review_digest: "review", calculations: [], issues: [], limitations: [] }, relationship: "bound", bindings: ["fp"], factor_uses: [], checks: [], changes: [], applicable: false, workspace_exportable: true };
const parameters = { run: "smaa2_factors", evaluation: "sampled", draws: 1000, seed: 7, confidence: 0.95, configuration: project.analysis } satisfies FactorRunParameters;
const spec: FactorUncertaintyModel = { schema_version: 1, project_fingerprint: "fp", model_digest: "model", distributions: [], groups: [] };
const completed: FactorRunRecord = { artifact_kind: "factor_uncertainty_run", version: 1, source_project: project, model, uncertainty: spec, parameters, decision: null, digest: "digest", result: { run: "smaa2_factors", algorithm: "factor-mavt-smaa2.v1", sampler_algorithm: "factor-sampling.v1", rng: "PCG64", seed: 7, draw_count: 1000, evaluation: "sampled", confidence: 0.95, project_fingerprint: "fp", model_digest: "model", uncertainty_digest: "u", environment: {}, dependency_order: [], draw_columns: [], deterministic_inputs: { x: 0.5 }, reference: record.result, feasibility: { status: "no_requirements", result: null, issues: [] }, acceptability: [], trace: [], draws_digest: "rows", questions: [], warnings: [], limitations: [] } };

beforeEach(() => { vi.spyOn(api, "inspectFactorUncertainty").mockImplementation((_p, _m, uncertainty) => Promise.resolve({ uncertainty: uncertainty as FactorUncertaintyModel, uncertainty_digest: "u", issues: [], questions: [] })); vi.useFakeTimers(); vi.spyOn(api, "inspectCalculations").mockResolvedValue(inspection); });
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });
async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(150); }); }
async function start() {
  await settle();
  fireEvent.click(screen.getByRole("button", { name: "Start factor uncertainty sidecar" }));
  fireEvent.change(screen.getByLabelText("Distribution reviewer"), { target: { value: "Reviewer" } });
}
async function begin() {
  fireEvent.click(screen.getByLabelText("I accept these distributions and dependence assumptions"));
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Run factor uncertainty" })); await Promise.resolve(); });
}

it("requires an explicit distribution review and exposes Python's refusal without a usable result", async () => {
  const run = vi.spyOn(api, "runFactorUncertainty").mockRejectedValue(Error("UNCERTAINTY_DENOMINATOR: support includes zero"));
  const viewed = { ...project.analysis, weight_profile_id: "second", scenario_id: "viewed" };
  render(<FactorUncertaintyPanel project={project} fingerprint="fp" document={model} configuration={viewed} onDirty={vi.fn()}/>);
  await start();
  expect(screen.getByRole("button", { name: "Run factor uncertainty" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Source factor"), { target: { value: "x" } });
  fireEvent.change(screen.getByLabelText("Lower bound"), { target: { value: "0" } });
  fireEvent.change(screen.getByLabelText("Upper bound"), { target: { value: "1" } });
  fireEvent.click(screen.getByRole("button", { name: "Set pending distribution" }));
  expect(run).not.toHaveBeenCalled();
  await begin();
  expect(run.mock.calls[0]?.[3].configuration).toEqual(viewed);
  expect(project.analysis.scenario_id).toBeNull();
  expect(run.mock.calls[0]?.[2]).toMatchObject({ distributions: [{ factor_id: "x", review: { status: "accepted", reviewer: "Reviewer" } }] });
  expect(screen.getByRole("alert")).toHaveTextContent("support includes zero");
  expect(screen.queryByRole("region", { name: "Completed factor run" })).not.toBeInTheDocument();
});

it.each(["seed", "profile"] as const)("discards a late response after %s changes", async kind => {
  let finish!: (value: FactorRunRecord) => void;
  vi.spyOn(api, "runFactorUncertainty").mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const dirty = vi.fn();
  const view = render(<FactorUncertaintyPanel project={project} fingerprint="fp" document={model} onDirty={dirty}/>);
  await start(); await begin();
  if (kind === "seed") fireEvent.change(screen.getByLabelText("Seed"), { target: { value: "8" } });
  else view.rerender(<FactorUncertaintyPanel project={project} fingerprint="fp" document={model} configuration={{ ...project.analysis, weight_profile_id: "second" }} onDirty={dirty}/>);
  await act(async () => { finish(completed); await Promise.resolve(); });
  expect(screen.queryByRole("region", { name: "Completed factor run" })).not.toBeInTheDocument();
});

it.each(["project", "distribution"] as const)("rejects a response for another bound %s", async kind => {
  vi.spyOn(api, "runFactorUncertainty").mockResolvedValue({ ...completed, result: { ...completed.result, ...(kind === "project" ? { project_fingerprint: "other" } : { uncertainty_digest: "other" }) } });
  render(<FactorUncertaintyPanel project={project} fingerprint="fp" document={model} onDirty={vi.fn()}/>);
  await start(); await begin();
  expect(screen.getByRole("alert")).toHaveTextContent("does not match");
  expect(screen.queryByRole("button", { name: "Export factor run record" })).not.toBeInTheDocument();
});

it("retains an authored sidecar after a project edit but blocks running without rebinding it", async () => {
  const dirty = vi.fn();
  const view = render(<FactorUncertaintyPanel project={project} fingerprint="fp" document={model} onDirty={dirty}/>);
  await start();
  expect(dirty).toHaveBeenLastCalledWith(true);
  view.rerender(<FactorUncertaintyPanel project={project} fingerprint="other" document={model} onDirty={dirty}/>);
  await settle();
  expect(screen.getByRole("alert")).toHaveTextContent("another project or calculation revision");
  expect(screen.getByRole("button", { name: "Run factor uncertainty" })).toBeDisabled();
  expect(dirty).toHaveBeenLastCalledWith(true);
  const save = vi.spyOn(downloads, "saveDownload").mockImplementation(() => undefined);
  const exportDraft = screen.getByRole("button", { name: "Export factor uncertainty draft" });
  expect(exportDraft).toBeEnabled();
  fireEvent.click(exportDraft);
  expect(save).toHaveBeenCalledWith(expect.any(Blob), "factor-uncertainty-draft.json");
  expect(dirty).toHaveBeenLastCalledWith(false);
});
