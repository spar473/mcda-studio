import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api, ApiError } from "../../src/api/client";
import type { EvidenceInspection } from "../../src/api/types";
import { EvidenceWorkspacePanel } from "../../src/components/EvidenceWorkspacePanel";
import { project } from "../results/fixture";

beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

const dossier: EvidenceInspection["dossier"] = { schema_version: 1, project_fingerprint: "fp", claims: [{
  id: "quote", alternative_id: "a", criterion_id: "cost", value: 42, unit: "NZD",
  source: { name: "Quotation", reference: "local:quote", location: "p2", date: "2026-10-31", description: "Price per item", classification: "self_reported" },
  origin: { kind: "tool", proposed_by: "Analyst", tool_id: "extractor", tool_version: "1" },
  review: null, uncertainty_lower: null, uncertainty_upper: null, outdated: true,
}] };
const result: EvidenceInspection = { dossier, workspace: { workspace_version: 1, source_project: project, original_dossier: dossier, reviews: [], digest: "workspace" },
  preview: { project_fingerprint: "fp", evidence_digest: "dossier", review_digest: "preview", changes: [], issues: [], missing_measurements: [], unreviewed_claims: ["quote"], outdated_claims: ["quote"], conflicting_cells: [] },
  support_available: true, workspace_exportable: true, support: [{ alternative_id: "a", criterion_id: "cost", measurement: 42, status: "unverified", claim_ids: ["quote"], accepted_claim_ids: [] }] };
const props = () => ({ project, fingerprint: "fp", active: true, onDossier: vi.fn(), onDirty: vi.fn(), onMeasurement: vi.fn() });
async function tick() { await act(async () => { await vi.advanceTimersByTimeAsync(125); }); }
async function choose(text = "{}") {
  const file = new File([text], "dossier.json");
  Object.defineProperty(file, "text", { value: () => Promise.resolve(text) });
  await act(async () => { fireEvent.change(screen.getByLabelText("Evidence dossier or review workspace"), { target: { files: [file] } }); await Promise.resolve(); });
  await tick();
}
async function review() {
  fireEvent.click(screen.getByRole("button", { name: "Review quote" }));
  fireEvent.change(screen.getByLabelText("Reviewer"), { target: { value: "Reviewer" } });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Preview review" })); await Promise.resolve(); });
}

it("stays read-only until a file is selected and explains provenance, support and affected measurements", async () => {
  const inspect = vi.spyOn(api, "inspectEvidence").mockResolvedValue(result);
  const spy = vi.spyOn(api, "reviewEvidence");
  const p = props();
  render(<EvidenceWorkspacePanel {...p}/>);
  await tick(); expect(inspect).not.toHaveBeenCalled();
  await choose();
  expect(screen.getByLabelText("Evidence claims")).toHaveTextContent("unreviewed · outdated");
  expect(screen.getByLabelText("Evidence claims")).toHaveTextContent("extractor 1");
  expect(screen.getByText(/Independence does not establish correctness/)).toBeInTheDocument();
  expect(screen.getByLabelText("Measurement support")).toHaveTextContent("unverified");
  fireEvent.click(screen.getByRole("button", { name: "Inspect affected measurement" }));
  expect(p.onMeasurement).toHaveBeenCalledWith("a", "cost");
  expect(spy).not.toHaveBeenCalled();
});

it("previews a backend review and requires explicit confirmation before changing the workspace", async () => {
  vi.spyOn(api, "inspectEvidence").mockResolvedValue(result);
  const candidate = { ...result, workspace: { ...result.workspace, digest: "candidate" } };
  const spy = vi.spyOn(api, "reviewEvidence").mockResolvedValue(candidate);
  const p = props(); render(<EvidenceWorkspacePanel {...p}/>);
  await choose(); await review();
  expect(spy.mock.calls[0]?.slice(0, 2)).toEqual([project, result.workspace]);
  expect(spy.mock.calls[0]?.[2].claim_id).toBe("quote");
  expect(spy.mock.calls[0]?.[2].review).toMatchObject({ reviewer: "Reviewer", status: "accepted" });
  expect(spy.mock.calls[0]?.[3]).toBe("preview");
  expect(p.onDirty).not.toHaveBeenCalledWith(true);
  expect(screen.getByRole("button", { name: "Confirm review in workspace" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Confirm review in workspace" }));
  await tick();
  expect(p.onDirty).toHaveBeenLastCalledWith(true);
  expect(screen.getByLabelText("Evidence dossier or review workspace")).toBeDisabled();
  expect(api.inspectEvidence).toHaveBeenLastCalledWith(project, candidate.workspace, expect.any(AbortSignal));
});

it("invalidates a preview when the review intent changes", async () => {
  vi.spyOn(api, "inspectEvidence").mockResolvedValue(result);
  vi.spyOn(api, "reviewEvidence").mockResolvedValue(result);
  render(<EvidenceWorkspacePanel {...props()}/>);
  await choose(); await review();
  fireEvent.change(screen.getByLabelText("Review note"), { target: { value: "Changed rationale" } });
  expect(screen.queryByRole("button", { name: "Confirm review in workspace" })).not.toBeInTheDocument();
});

it("explains backend acceptance refusals and leaves the current dossier intact", async () => {
  vi.spyOn(api, "inspectEvidence").mockResolvedValue(result);
  vi.spyOn(api, "reviewEvidence").mockRejectedValue(new ApiError(422, "VALIDATION_FAILED", "Project has one validation error", [
    { code: "EVIDENCE_MULTIPLE_ACCEPTED", path: "performances[a,cost]", message: "only one claim may be accepted for a cell" },
  ]));
  const p = props(); render(<EvidenceWorkspacePanel {...p}/>);
  await choose(); await review();
  expect(screen.getByRole("alert")).toHaveTextContent("only one claim may be accepted for a cell");
  expect(screen.queryByRole("button", { name: "Confirm review in workspace" })).not.toBeInTheDocument();
  expect(p.onDirty).not.toHaveBeenCalledWith(true);
});

it("ignores a review response arriving after a project revision changes", async () => {
  vi.spyOn(api, "inspectEvidence").mockResolvedValue(result);
  let resolve!: (value: EvidenceInspection) => void;
  vi.spyOn(api, "reviewEvidence").mockImplementation(() => new Promise(done => { resolve = done; }));
  const p = props(); const view = render(<EvidenceWorkspacePanel {...p}/>);
  await choose(); await review();
  view.rerender(<EvidenceWorkspacePanel {...p} fingerprint="changed"/>);
  await act(async () => { resolve(result); await Promise.resolve(); });
  expect(screen.queryByRole("button", { name: "Confirm review in workspace" })).not.toBeInTheDocument();
  expect(p.onDirty).not.toHaveBeenCalledWith(true);
});

it("shows stale dossier errors and blocks review while preserving workspace export", async () => {
  vi.spyOn(api, "inspectEvidence").mockResolvedValue({ ...result, support_available: false, support: [], preview: { ...result.preview, issues: [{ severity: "error", code: "EVIDENCE_STALE_PROJECT", message: "Dossier changed", path: "" }] } });
  render(<EvidenceWorkspacePanel {...props()}/>);
  await choose();
  expect(screen.getByRole("alert")).toHaveTextContent("EVIDENCE_STALE_PROJECT");
  expect(screen.getByRole("button", { name: "Review quote" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Export review workspace" })).toBeEnabled();
  expect(screen.queryByLabelText("Measurement support")).not.toBeInTheDocument();
});

it("rejects mismatched inspections and malformed local JSON", async () => {
  vi.spyOn(api, "inspectEvidence").mockResolvedValue({ ...result, preview: { ...result.preview, project_fingerprint: "wrong" } });
  render(<EvidenceWorkspacePanel {...props()}/>);
  await choose();
  expect(screen.getByRole("alert")).toHaveTextContent("does not match");
  await choose("not json");
  expect(screen.getByRole("alert")).toHaveTextContent("Could not read evidence JSON");
});
