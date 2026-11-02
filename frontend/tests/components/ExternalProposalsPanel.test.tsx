import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { ProposalCompilation, ProposalInspection } from "../../src/api/types";
import { ExternalProposalsPanel } from "../../src/components/ExternalProposalsPanel";
import * as downloads from "../../src/components/results/downloads";
import initialJSON from "../fixtures/proposals-initial.json";
import comparisonJSON from "../fixtures/proposals-comparison.json";
import reviewedJSON from "../fixtures/proposals-reviewed.json";
import compiledJSON from "../fixtures/proposals-compiled.json";

const initial = initialJSON as ProposalInspection;
const compared = comparisonJSON as ProposalInspection;
const reviewed = reviewedJSON as ProposalInspection;
const compiled = compiledJSON as ProposalCompilation;
const sourceProject = initial.workspace.source_project;
if (!sourceProject) throw Error("Bound UI fixture source missing");
const props = () => ({ project: sourceProject, fingerprint: initial.current_fingerprint, onDirty: vi.fn(), onWorkspace: vi.fn() });
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date("2026-11-01T00:00:00Z")); });
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });
async function tick() { await act(async () => { await vi.advanceTimersByTimeAsync(125); }); }
function mocks() {
  vi.spyOn(api, "importProposals").mockResolvedValue(initial);
  vi.spyOn(api, "inspectProposals").mockImplementation((_p, w, target) => Promise.resolve(w.digest === reviewed.workspace.digest ? reviewed : target ? compared : initial));
}
async function choose() {
  const file = new File(["{}"], "intake.json"); Object.defineProperty(file, "text", { value: () => Promise.resolve("{}") });
  await act(async () => { fireEvent.change(screen.getByLabelText("Import proposal file"), { target: { files: [file] } }); await Promise.resolve(); });
  await tick();
}
function open(p = props()) { const view = render(<ExternalProposalsPanel {...p}/>); fireEvent.click(screen.getByText("External proposals", { selector: "summary" })); return view; }
function selectBulk() {
  fireEvent.click(screen.getByLabelText("Select proposal readiness_b"));
  fireEvent.click(screen.getByLabelText("Select proposal tag_b"));
  fireEvent.change(screen.getByLabelText("Proposal reviewer"), { target: { value: "Illustrative reviewer" } });
  fireEvent.change(screen.getByLabelText("Proposal review decision"), { target: { value: "accepted" } });
  fireEvent.change(screen.getByLabelText("Proposal review note"), { target: { value: "Invented demonstration review" } });
  fireEvent.click(screen.getByRole("button", { name: "Use each selected proposal's sole cited source" }));
}
async function preview() {
  selectBulk(); vi.setSystemTime(new Date("2026-11-01T00:00:00Z"));
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Preview selected proposal reviews" })); await Promise.resolve(); });
}

it("starts with empty selection, no accept-all action and no default review decision", async () => {
  mocks(); open(); await choose();
  expect(screen.getByText(/0 explicitly selected/)).toBeInTheDocument();
  expect(screen.getAllByRole("checkbox").every(c => !((c as HTMLInputElement).checked))).toBe(true);
  expect(screen.queryByRole("button", { name: /accept all/i })).not.toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("Select proposal readiness_b"));
  expect(screen.getByLabelText("Proposal review decision")).toHaveValue("");
  expect(screen.getByRole("button", { name: "Preview selected proposal reviews" })).toBeDisabled();
  expect(screen.getByLabelText("External proposal review table")).toHaveTextContent("Confidence metadata only");
});

it("filters without selecting and shows originals, reviewed values and human sources side by side", async () => {
  mocks(); open(); await choose();
  fireEvent.change(screen.getByLabelText("Compare proposals with"), { target: { value: "tool:external_b" } }); await tick();
  fireEvent.change(screen.getByLabelText("Proposal agreement"), { target: { value: "disagreement" } });
  expect(screen.getByLabelText("External proposal review table")).toHaveTextContent("cell_a_first");
  expect(screen.queryByLabelText("Select proposal readiness_b")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Select proposal cell_a_first")).not.toBeChecked();
  fireEvent.click(screen.getByRole("button", { name: "Compare cell cell_a_first" }));
  const table = screen.getByRole("region", { name: "Proposal cell comparison" });
  expect(table).toHaveTextContent("external_a"); expect(table).toHaveTextContent("external_b"); expect(table).toHaveTextContent("human:human_a");
  expect(table).toHaveTextContent("software"); expect(table).toHaveTextContent("hardware");
  expect(table).toHaveTextContent("local:invented-brief-a");
});

it("lists every affected item and writes separate identical-metadata events only on confirmation", async () => {
  mocks(); const review = vi.spyOn(api, "reviewProposals").mockResolvedValue(reviewed);
  const p = props(); open(p); await choose(); await preview();
  const confirmation = screen.getByRole("region", { name: "Proposal review confirmation" });
  expect(within(confirmation).getAllByRole("listitem")).toHaveLength(2);
  expect(confirmation).toHaveTextContent("readiness_b"); expect(confirmation).toHaveTextContent("tag_b");
  const events = review.mock.calls[0]?.[2];
  expect(events?.map(e => e.proposal_id)).toEqual(["readiness_b", "tag_b"]);
  expect(new Set(events?.map(e => `${e.review.reviewer}|${e.review.reviewed_at}|${e.review.note}`)).size).toBe(1);
  expect(review.mock.calls[0]?.[4]).toBe(true);
  expect(p.onDirty).not.toHaveBeenCalledWith(true);
  fireEvent.click(screen.getByRole("button", { name: "Confirm listed proposal reviews" })); await tick();
  expect(p.onDirty).toHaveBeenLastCalledWith(true);
  expect(p.onWorkspace).toHaveBeenLastCalledWith(reviewed.workspace);
  expect(screen.getByLabelText("Import proposal file")).toBeDisabled();
  expect(screen.getByText("Proposal review history (2 events)")).toBeInTheDocument();
});

it("blocks bulk selection of unresolved items while retaining individual correction or rejection", async () => {
  mocks(); const blocked = { ...initial, rows: initial.rows.map(r => r.original.id === "numeric_b" ? { ...r, bulk_eligible: false, issues: [{ severity: "error" as const, code: "PROPOSAL_MODEL_CARD", message: "Missing card", path: "" }] } : r) };
  vi.spyOn(api, "inspectProposals").mockResolvedValue(blocked);
  open(); await choose();
  expect(screen.getByLabelText("Select proposal numeric_b")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Review proposal numeric_b" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Review proposal numeric_b" }));
  fireEvent.change(screen.getByLabelText("Proposal review decision"), { target: { value: "corrected" } });
  expect(screen.getByLabelText("Corrected proposal payload (JSON)")).toBeInTheDocument();
  expect(screen.getByText("Original: {\"kind\":\"numeric_cell\",\"value\":0.91,\"unit\":\"1\"}")).toBeInTheDocument();
});

it("drops a delayed review after the project changes", async () => {
  mocks(); let done!: (r: ProposalInspection) => void;
  vi.spyOn(api, "reviewProposals").mockImplementation(() => new Promise(resolve => { done = resolve; }));
  const p = props(); const view = open(p); await choose(); await preview();
  view.rerender(<ExternalProposalsPanel {...p} fingerprint="changed"/>);
  await act(async () => { done(reviewed); await Promise.resolve(); });
  expect(screen.queryByRole("button", { name: "Confirm listed proposal reviews" })).not.toBeInTheDocument();
  expect(p.onDirty).not.toHaveBeenCalledWith(true);
});

it("invalidates the confirmation when selection or review intent changes", async () => {
  mocks(); vi.spyOn(api, "reviewProposals").mockResolvedValue(reviewed);
  open(); await choose(); await preview();
  expect(screen.getByRole("button", { name: "Confirm listed proposal reviews" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Proposal review note"), { target: { value: "New reason" } });
  expect(screen.queryByRole("button", { name: "Confirm listed proposal reviews" })).not.toBeInTheDocument();
});

it("requires compilation acknowledgement, rejects a late copy and exports retained history", async () => {
  mocks(); vi.spyOn(api, "reviewProposals").mockResolvedValue(reviewed);
  let done!: (r: ProposalCompilation) => void;
  const compile = vi.spyOn(api, "compileProposals").mockImplementation(() => new Promise(resolve => { done = resolve; }));
  const save = vi.spyOn(downloads, "saveDownload").mockImplementation(() => undefined);
  const p = props(); open(p); await choose(); await preview();
  fireEvent.click(screen.getByRole("button", { name: "Confirm listed proposal reviews" })); await tick();
  expect(screen.getByRole("button", { name: "Compile reviewed proposal copy" })).toBeDisabled();
  fireEvent.click(screen.getByLabelText("I reviewed every proposal measurement change and retained annotation"));
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Compile reviewed proposal copy" })); await Promise.resolve(); });
  expect(compile).toHaveBeenCalledWith(p.project, reviewed.workspace, reviewed.review_digest, null);
  fireEvent.change(screen.getByLabelText("Registry recorder"), { target: { value: "New recorder" } });
  await act(async () => { done(compiled); await Promise.resolve(); });
  expect(screen.queryByRole("button", { name: "Export proposal compilation bundle" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Export proposal review workspace" }));
  expect(save.mock.calls[0]?.[1]).toBe("external-proposals-workspace.json");
  expect(p.onDirty).toHaveBeenLastCalledWith(false);
});

it("refuses mismatched review history and keeps the imported document intact", async () => {
  mocks(); vi.spyOn(api, "reviewProposals").mockResolvedValue({ ...reviewed, workspace: initial.workspace });
  const p = props(); open(p); await choose(); await preview();
  expect(screen.getByRole("alert")).toHaveTextContent("does not match the selected items");
  expect(screen.queryByRole("button", { name: "Confirm listed proposal reviews" })).not.toBeInTheDocument();
  expect(p.onDirty).not.toHaveBeenCalledWith(true);
});

it("discards an import response arriving after a project change before publishing its workspace", async () => {
  mocks(); let done!: (r: ProposalInspection) => void;
  vi.spyOn(api, "importProposals").mockImplementation(() => new Promise(resolve => { done = resolve; }));
  const p = props(); const view = open(p);
  const file = new File(["{}"], "intake.json"); Object.defineProperty(file, "text", { value: () => Promise.resolve("{}") });
  await act(async () => { fireEvent.change(screen.getByLabelText("Import proposal file"), { target: { files: [file] } }); await Promise.resolve(); });
  expect(api.importProposals).toHaveBeenCalledTimes(1);
  view.rerender(<ExternalProposalsPanel {...p} fingerprint="changed"/>);
  await act(async () => { done(initial); await Promise.resolve(); });
  expect(p.onWorkspace).not.toHaveBeenCalledWith(initial.workspace);
  expect(screen.queryByRole("button", { name: "Export proposal review workspace" })).not.toBeInTheDocument();
});
