import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { DecisionRecordInspection, DecisionRecordV2 } from "../../src/api/types";
import { DecisionRecordPanel } from "../../src/components/DecisionRecordPanel";
import * as downloads from "../../src/components/results/downloads";
import { project } from "../results/fixture";

beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

const record = {
  version: 2, digest: "d".repeat(64), previous_digest: null, predecessor: null, project, project_fingerprint: "fp",
  decision: { owner: "Owner", date: "2026-11-01", outcome: "selected", selected_alternative_id: "a", alternatives_considered: ["c", "a", "b"],
    rationale: "Because", configurations: [{ method: "mavt", weight_profile_id: null, scenario_id: null, parameters: {} }], unresolved_assumptions: ["Assumed"], review_triggers: [] },
  analyses: [{ configuration: { method: "mavt", weight_profile_id: null, scenario_id: null, parameters: {} }, status: "unavailable", record: null, reason: "[SMAA_MISSING] no inputs", issues: [] }],
  feasibility: { status: "no_requirements", result: null, issues: [] }, supporting_artifacts: [],
  anchors: [{ artifact_digest: "e".repeat(64), artifact_kind: "evidence_compilation", relationship: "verified_copy", anchored_to: "record_project", anchor_artifact_digest: null }],
  measurement_trace: [{ alternative_id: "a", criterion_id: "cost", value: 7, origin: "evidence", artifact_digest: "e".repeat(64), reference_id: "quote", inputs: [], original_value: 8 },
    { alternative_id: "b", criterion_id: "cost", value: 6, origin: "entered", artifact_digest: null, reference_id: null, inputs: [], original_value: null }],
  notices: [{ severity: "warning", code: "DECISION_ANALYSIS_UNAVAILABLE", message: "[SMAA_MISSING] no inputs", path: "analyses[0]" }],
} as unknown as DecisionRecordV2;
const props = () => ({ project, fingerprint: "fp", active: true, methods: [{ name: "mavt", label: "MAVT", capabilities: [], export_tables: [] }], onDirty: vi.fn() });
async function tick() { await act(async () => { await vi.advanceTimersByTimeAsync(125); }); }
function file(name: string, value: unknown) {
  const text = JSON.stringify(value);
  const f = new File([text], name);
  Object.defineProperty(f, "text", { value: () => Promise.resolve(text) });
  return f;
}
async function choose(label: string, ...files: File[]) {
  await act(async () => { fireEvent.change(screen.getByLabelText(label), { target: { files } }); await Promise.resolve(); await Promise.resolve(); });
}
function fill() {
  fireEvent.change(screen.getByLabelText("Decision owner"), { target: { value: "Owner" } });
  fireEvent.change(screen.getByLabelText("Selected alternative"), { target: { value: "a" } });
  fireEvent.change(screen.getByLabelText("Rationale"), { target: { value: "Because" } });
}
async function preview() {
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Preview decision record" })); await Promise.resolve(); });
}

it("requires the stated decision before Python builds a record, then exports it explicitly", async () => {
  const spy = vi.spyOn(api, "previewDecision").mockResolvedValue(record);
  const save = vi.spyOn(downloads, "saveDownload").mockImplementation(() => undefined);
  const p = props(); render(<DecisionRecordPanel {...p}/>);
  expect(screen.getByRole("button", { name: "Preview decision record" })).toBeDisabled();
  fill();
  fireEvent.change(screen.getByLabelText("Unresolved assumptions (one per line)"), { target: { value: "Assumed\n\n second " } });
  await preview();
  const [, details, artifacts, predecessor] = spy.mock.calls[0] ?? [];
  expect(details).toMatchObject({ owner: "Owner", outcome: "selected", selected_alternative_id: "a", alternatives_considered: ["c", "a", "b"],
    unresolved_assumptions: ["Assumed", "second"], configurations: [{ method: "mavt", parameters: project.analysis.parameters }] });
  expect(artifacts).toEqual([]); expect(predecessor).toBeNull();
  const view = screen.getByLabelText("Previewed record");
  expect(view).toHaveTextContent("Selected: Same");
  expect(view).toHaveTextContent("unavailable — [SMAA_MISSING] no inputs");
  expect(screen.getByLabelText("Previewed record measurement provenance")).toHaveTextContent("claim quote");
  expect(screen.getByLabelText("Previewed record measurement provenance")).toHaveTextContent("8");
  expect(p.onDirty).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByRole("button", { name: "Export decision record" }));
  expect(save.mock.calls[0]?.[1]).toBe(`decision-record-${"d".repeat(12)}.json`);
  expect(p.onDirty).toHaveBeenLastCalledWith(false);
});

it("clears the selection when its alternative is no longer considered", () => {
  render(<DecisionRecordPanel {...props()}/>);
  fill();
  const [first] = screen.getAllByRole("checkbox", { name: "Same" }); // alternative "a", the selection
  if (!first) throw Error("checkbox missing");
  fireEvent.click(first);
  expect(screen.getByLabelText("Selected alternative")).toHaveValue("");
  expect(screen.getByRole("button", { name: "Preview decision record" })).toBeDisabled();
});

it("keeps the draft but renders no controls while another tab is open", () => {
  const p = props(); const view = render(<DecisionRecordPanel {...p}/>);
  fireEvent.change(screen.getByLabelText("Decision owner"), { target: { value: "Kept owner" } });
  expect(screen.getByLabelText("Analysis 1 scenario")).toBeInTheDocument();
  view.rerender(<DecisionRecordPanel {...p} active={false}/>);
  expect(screen.queryByLabelText("Analysis 1 scenario")).not.toBeInTheDocument();
  view.rerender(<DecisionRecordPanel {...p}/>);
  expect(screen.getByLabelText("Decision owner")).toHaveValue("Kept owner");
});

it("drops a preview once the decision details change", async () => {
  vi.spyOn(api, "previewDecision").mockResolvedValue(record);
  const p = props(); render(<DecisionRecordPanel {...p}/>);
  fill(); await preview();
  expect(screen.getByLabelText("Previewed record")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Rationale"), { target: { value: "A different reason" } });
  expect(screen.queryByLabelText("Previewed record")).not.toBeInTheDocument();
  expect(p.onDirty).toHaveBeenLastCalledWith(false);
});

it("ignores a delayed preview after the project revision changes", async () => {
  let done!: (value: DecisionRecordV2) => void;
  vi.spyOn(api, "previewDecision").mockImplementation(() => new Promise(resolve => { done = resolve; }));
  const p = props(); const view = render(<DecisionRecordPanel {...p}/>);
  fill(); await preview();
  view.rerender(<DecisionRecordPanel {...p} fingerprint="changed"/>);
  await act(async () => { done(record); await Promise.resolve(); });
  expect(screen.queryByLabelText("Previewed record")).not.toBeInTheDocument();
});

it("refuses a record built for another project revision", async () => {
  vi.spyOn(api, "previewDecision").mockResolvedValue({ ...record, project_fingerprint: "other" });
  render(<DecisionRecordPanel {...props()}/>);
  fill(); await preview();
  expect(screen.getByRole("alert")).toHaveTextContent("does not match the current project");
  expect(screen.queryByLabelText("Previewed record")).not.toBeInTheDocument();
});

it("pairs bundles with their receipts by exact fingerprint and blocks unrelated files", async () => {
  const spy = vi.spyOn(api, "previewDecision").mockResolvedValue(record);
  render(<DecisionRecordPanel {...props()}/>);
  fill();
  const bundle = { compilation_version: 1, compiled_fingerprint: "compiled", digest: "b" };
  const receipt = { receipt_version: 1, original_fingerprint: "compiled", digest: "r" };
  const stray = { receipt_version: 1, original_fingerprint: "elsewhere", digest: "s" };
  await choose("Supporting bundles and copy receipts", file("bundle.json", bundle), file("receipt.json", receipt), file("stray.json", stray));
  expect(screen.getByLabelText("Supporting files")).toHaveTextContent("stray.json: copy receipt matching no selected bundle");
  expect(screen.getByRole("button", { name: "Preview decision record" })).toBeDisabled();
  await choose("Supporting bundles and copy receipts", file("bundle.json", bundle), file("receipt.json", receipt));
  expect(screen.getByLabelText("Supporting files")).toHaveTextContent("bundle.json: bundle with copy receipt");
  await preview();
  expect(spy.mock.calls[0]?.[2]).toEqual([{ artifact: bundle, copy_receipt: receipt }]);
});

it("opens a record historically and revises it as a new linked record", async () => {
  const inspection: DecisionRecordInspection = { record, current_project_matches: false, predecessor_verified: null };
  const open = vi.spyOn(api, "inspectDecision").mockResolvedValue(inspection);
  const spy = vi.spyOn(api, "previewDecision").mockResolvedValue({ ...record, previous_digest: record.digest });
  render(<DecisionRecordPanel {...props()}/>);
  await choose("Decision record file", file("record.json", record));
  await tick();
  expect(open).toHaveBeenCalledWith(project, record, null, expect.any(AbortSignal));
  expect(screen.getByLabelText("Opened decision record")).toHaveTextContent("shown historically");
  fireEvent.click(screen.getByRole("button", { name: "Revise this record" }));
  expect(screen.getByLabelText("Rationale")).toHaveValue("Because");
  expect(screen.getByText(/Revising record.json/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Unresolved assumptions (one per line)"), { target: { value: "Changed" } });
  await preview();
  expect(spy.mock.calls[0]?.[3]).toEqual(record);
  expect(screen.getByLabelText("Previewed record")).toBeInTheDocument();
});
