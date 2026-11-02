import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api, ApiError } from "../../src/api/client";
import type { ArtifactBinding, EvidenceCompilation, EvidenceInspection } from "../../src/api/types";
import { EvidenceWorkspacePanel } from "../../src/components/EvidenceWorkspacePanel";
import * as downloads from "../../src/components/results/downloads";
import { project } from "../results/fixture";

beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

const review = { status: "accepted" as const, reviewer: "Analyst", reviewed_at: "2026-11-01T00:00:00Z", corrected_value: null, note: "" };
const dossier: EvidenceInspection["dossier"] = { schema_version: 1, project_fingerprint: "fp", claims: [{
  id: "quote", alternative_id: "a", criterion_id: "cost", value: 7, unit: "kg",
  source: { name: "Quotation", reference: "local:quote", location: "", date: "2026-10-31", description: "Weight", classification: "self_reported" },
  origin: { kind: "human", proposed_by: "Analyst", tool_id: null, tool_version: null },
  review, uncertainty_lower: null, uncertainty_upper: null, outdated: false,
}] };
const workspace: EvidenceInspection["workspace"] = { workspace_version: 1, source_project: project, original_dossier: dossier, reviews: [], digest: "history" };
const inspection: EvidenceInspection = { dossier, workspace, support_available: true, workspace_exportable: true, support: [],
  preview: { project_fingerprint: "fp", evidence_digest: "dossier", review_digest: "preview", changes: [{ alternative_id: "a", criterion_id: "cost", claim_id: "quote", before: 8, after: 7 }],
    issues: [], missing_measurements: [{ alternative_id: "b", criterion_id: "quality" }], unreviewed_claims: [], outdated_claims: [], conflicting_cells: [] } };
const compiled = { ...project, performances: [] };
const bundle: EvidenceCompilation = { compilation_version: 1, workspace, preview: inspection.preview, project: compiled, compiled_fingerprint: "compiled", digest: "bundle" };
const props = () => ({ project, fingerprint: "fp", active: true, onDossier: vi.fn(), onDirty: vi.fn(), onMeasurement: vi.fn() });
async function tick() { await act(async () => { await vi.advanceTimersByTimeAsync(125); }); }
async function choose(label: string, text = "{}") {
  const file = new File([text], "file.json");
  Object.defineProperty(file, "text", { value: () => Promise.resolve(text) });
  await act(async () => { fireEvent.change(screen.getByLabelText(label), { target: { files: [file] } }); await Promise.resolve(); });
  await tick();
}
async function compile() {
  fireEvent.click(screen.getByLabelText("I reviewed every measurement change for the separate copy"));
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Compile reviewed copy" })); await Promise.resolve(); });
}

it("shows each target change and compiles only after explicit acknowledgement", async () => {
  vi.spyOn(api, "inspectEvidence").mockResolvedValue(inspection);
  const spy = vi.spyOn(api, "compileEvidence").mockResolvedValue(bundle);
  const save = vi.spyOn(downloads, "saveDownload").mockImplementation(() => undefined);
  const p = props(); render(<EvidenceWorkspacePanel {...p}/>);
  await choose("Evidence dossier or review workspace");
  const table = screen.getByRole("table", { name: "Measurement changes for compilation" });
  expect(table).toHaveTextContent("Same"); expect(table).toHaveTextContent("Cost"); expect(table).toHaveTextContent("kg");
  expect(table).toHaveTextContent("87quote · accepted by Analyst · Quotation");
  expect(screen.getByText(/1 missing measurements/)).toHaveTextContent("missing measurements stay missing, not zero");
  expect(screen.getByRole("button", { name: "Compile reviewed copy" })).toBeDisabled();
  expect(spy).not.toHaveBeenCalled();
  await compile();
  expect(spy).toHaveBeenCalledWith(project, workspace, "preview", "history");
  fireEvent.click(screen.getByRole("button", { name: "Export compiled project copy" }));
  expect(save.mock.calls[0]?.[1]).toBe("evidence-compiled-project.json");
  expect(p.onDirty).not.toHaveBeenCalledWith(true);
  fireEvent.click(screen.getByRole("button", { name: "Export evidence compilation bundle" }));
  expect(save.mock.calls[1]?.[1]).toBe("evidence-compilation.json");
  expect(JSON.parse(await (save.mock.calls[1]?.[0] as Blob).text())).toEqual(bundle);
});

it("drops a compilation whose digests or project differ from the acknowledged preview", async () => {
  vi.spyOn(api, "inspectEvidence").mockResolvedValue(inspection);
  vi.spyOn(api, "compileEvidence").mockResolvedValue({ ...bundle, workspace: { ...workspace, digest: "other history" } });
  render(<EvidenceWorkspacePanel {...props()}/>);
  await choose("Evidence dossier or review workspace");
  await compile();
  expect(screen.getByRole("alert")).toHaveTextContent("does not match the acknowledged preview");
  expect(screen.queryByRole("button", { name: "Export evidence compilation bundle" })).not.toBeInTheDocument();
});

it("ignores a delayed compilation after the project revision changes", async () => {
  vi.spyOn(api, "inspectEvidence").mockResolvedValue(inspection);
  let done!: (value: EvidenceCompilation) => void;
  vi.spyOn(api, "compileEvidence").mockImplementation(() => new Promise(resolve => { done = resolve; }));
  const p = props(); const view = render(<EvidenceWorkspacePanel {...p}/>);
  await choose("Evidence dossier or review workspace");
  await compile();
  view.rerender(<EvidenceWorkspacePanel {...p} fingerprint="changed"/>);
  await act(async () => { done(bundle); await Promise.resolve(); });
  expect(screen.queryByRole("button", { name: "Export evidence compilation bundle" })).not.toBeInTheDocument();
});

it("ignores a delayed compilation after review intent changes while the panel stays open", async () => {
  vi.spyOn(api, "inspectEvidence").mockResolvedValue(inspection);
  let done!: (value: EvidenceCompilation) => void;
  vi.spyOn(api, "compileEvidence").mockImplementation(() => new Promise(resolve => { done = resolve; }));
  render(<EvidenceWorkspacePanel {...props()}/>);
  await choose("Evidence dossier or review workspace");
  await compile();
  fireEvent.click(screen.getByRole("button", { name: "Review quote" }));
  expect(screen.getByRole("table", { name: "Measurement changes for compilation" })).toBeInTheDocument();
  await act(async () => { done(bundle); await Promise.resolve(); });
  expect(screen.queryByRole("button", { name: "Export evidence compilation bundle" })).not.toBeInTheDocument();
});

it("invalidates acknowledgement and compiled copies when review intent changes", async () => {
  vi.spyOn(api, "inspectEvidence").mockResolvedValue(inspection);
  vi.spyOn(api, "compileEvidence").mockResolvedValue(bundle);
  render(<EvidenceWorkspacePanel {...props()}/>);
  await choose("Evidence dossier or review workspace");
  await compile();
  expect(screen.getByRole("button", { name: "Export evidence compilation bundle" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Review quote" }));
  expect(screen.queryByRole("button", { name: "Export evidence compilation bundle" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("I reviewed every measurement change for the separate copy")).not.toBeChecked();
  expect(screen.getByRole("button", { name: "Compile reviewed copy" })).toBeDisabled();
});

it("blocks compilation for validation errors or a stale dossier and explains backend refusals", async () => {
  const inspect = vi.spyOn(api, "inspectEvidence").mockResolvedValue({ ...inspection, preview: { ...inspection.preview,
    issues: [{ severity: "error", code: "EVIDENCE_UNIT_MISMATCH", message: "claim unit must match", path: "claims[quote]" }] } });
  render(<EvidenceWorkspacePanel {...props()}/>);
  await choose("Evidence dossier or review workspace");
  expect(screen.getByText("Compilation is blocked until the errors listed above are resolved.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Compile reviewed copy" })).not.toBeInTheDocument();
  inspect.mockResolvedValue({ ...inspection, preview: { ...inspection.preview,
    issues: [{ severity: "error", code: "EVIDENCE_STALE_PROJECT", message: "stale", path: "" }] } });
  await choose("Evidence dossier or review workspace", "{\"changed\":1}");
  expect(screen.getByText(/Compilation is unavailable/)).toBeInTheDocument();
  expect(screen.queryByRole("table", { name: "Measurement changes for compilation" })).not.toBeInTheDocument();
  inspect.mockResolvedValue(inspection);
  vi.spyOn(api, "compileEvidence").mockRejectedValue(new ApiError(412, "STALE_REVISION", "Review history changed; review the compilation again."));
  await choose("Evidence dossier or review workspace", "{\"again\":1}");
  await compile();
  expect(screen.getByRole("alert")).toHaveTextContent("Review history changed");
});

const verifiedCopy: ArtifactBinding = { artifact_kind: "evidence_compilation", artifact_digest: "bundle", source_fingerprint: "fp", compiled_fingerprint: "compiled", current_fingerprint: "fp",
  relationship: "verified_copy", copy_receipt: { receipt_version: 1, transformation: "new_project_id", original_project_id: "p1", original_fingerprint: "compiled", copy_project_id: "copy", copy_fingerprint: "fp", digest: "receipt" } };

it("reopens a bundle historically and relates it to the current project only through Python", async () => {
  const inspect = vi.spyOn(api, "inspectEvidence");
  const open = vi.spyOn(api, "inspectEvidenceCompilation").mockResolvedValue({ compilation: bundle, inspection });
  const bind = vi.spyOn(api, "bindArtifact").mockResolvedValue({ ...verifiedCopy, relationship: "different", copy_receipt: null });
  render(<EvidenceWorkspacePanel {...props()}/>);
  const text = JSON.stringify(bundle);
  await choose("Evidence dossier or review workspace", text);
  expect(inspect).not.toHaveBeenCalled();
  expect(open).toHaveBeenCalledWith(project, bundle, expect.any(AbortSignal));
  expect(screen.getByRole("table", { name: "Recorded measurement changes" })).toHaveTextContent("quote");
  expect(screen.getByRole("table", { name: "Recorded measurement changes" })).toHaveTextContent("Original measurement");
  await tick();
  expect(bind).toHaveBeenLastCalledWith(project, bundle, null, expect.any(AbortSignal));
  expect(screen.getByLabelText("Evidence compilation provenance")).toHaveTextContent("historical inspection only");
  bind.mockResolvedValue(verifiedCopy);
  await choose("Copy receipt (optional)", JSON.stringify(verifiedCopy.copy_receipt));
  expect(bind).toHaveBeenLastCalledWith(project, bundle, verifiedCopy.copy_receipt, expect.any(AbortSignal));
  expect(screen.getByLabelText("Evidence compilation provenance")).toHaveTextContent("Import replaced project ID p1 with copy");
  expect(screen.getByLabelText("Evidence compilation provenance")).toHaveTextContent("fingerprints remain different");
});

it("shows a receipt refusal instead of a relationship", async () => {
  vi.spyOn(api, "inspectEvidenceCompilation").mockResolvedValue({ compilation: bundle, inspection });
  vi.spyOn(api, "bindArtifact").mockRejectedValue(new ApiError(409, "EDIT_REFUSED", "PROVENANCE_RECEIPT_PROJECT: copy receipt does not describe this project revision"));
  render(<EvidenceWorkspacePanel {...props()}/>);
  await choose("Evidence dossier or review workspace", JSON.stringify(bundle));
  await tick();
  expect(screen.getByLabelText("Evidence compilation provenance")).toHaveTextContent("PROVENANCE_RECEIPT_PROJECT");
  expect(screen.getByLabelText("Evidence compilation provenance")).not.toHaveTextContent("verified separate copy");
});

it("ignores a binding computed for an earlier project revision", async () => {
  vi.spyOn(api, "inspectEvidenceCompilation").mockResolvedValue({ compilation: bundle, inspection });
  vi.spyOn(api, "bindArtifact").mockResolvedValue({ ...verifiedCopy, current_fingerprint: "older" });
  render(<EvidenceWorkspacePanel {...props()}/>);
  await choose("Evidence dossier or review workspace", JSON.stringify(bundle));
  await tick();
  expect(screen.getByLabelText("Evidence compilation provenance")).toHaveTextContent("does not match this project revision");
});
