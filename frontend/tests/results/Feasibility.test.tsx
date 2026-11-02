import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { FeasibilityResult, MethodComparison, Project } from "../../src/api/types";
import { ComparePanel } from "../../src/components/ComparePanel";
import { ResultsPanel } from "../../src/components/ResultsPanel";
import { saveDownload } from "../../src/components/results/downloads";
import { FeasibilityView, StatusBadge } from "../../src/components/results/FeasibilityView";
import { resolveContext, BASE_SELECTION } from "../../src/state/analysisContext";
import { project as base, record } from "./fixture";

vi.mock("../../src/components/results/downloads", () => ({ saveDownload: vi.fn() }));
const LABEL = "feasibility: each requirement is tested on its own measurement; no score offsets a failure";
const project: Project = { ...base, requirements: [
  { kind: "bound", id: "cap", name: "Cost cap", criterion_id: "cost", unit: "kg", minimum: null, minimum_inclusive: true, maximum: 5, maximum_inclusive: true, rationale: "" },
  { kind: "bound", id: "floor", name: "Quality floor", criterion_id: "quality", unit: "%", minimum: 3, minimum_inclusive: true, maximum: null, maximum_inclusive: true, rationale: "" },
] };
const context = resolveContext(project, "fp", BASE_SELECTION);
const check = (id: string, status: "pass" | "fail" | "unknown", reason: string, measurement: number | null = 1) =>
  ({ requirement_id: id, status, measurement, reason });
const feasibility: FeasibilityResult = {
  label: LABEL, project_id: "p1", project_fingerprint: "fp", requirements: project.requirements ?? [], diagnostics: [],
  alternatives: [
    { alternative_id: "c", name: "Gamma", status: "fail", failed: ["floor"], unknown: [],
      checks: [check("cap", "pass", "2 kg is within the limits"), check("floor", "fail", "2 % is below the minimum 3 %")] },
    { alternative_id: "a", name: "Alpha", status: "unknown", failed: [], unknown: ["cap"],
      checks: [check("cap", "unknown", "no measurement", null), check("floor", "pass", "6 % is within the limits")] },
    { alternative_id: "b", name: "Beta", status: "pass", failed: [], unknown: [],
      checks: [check("cap", "pass", "4 kg is within the limits"), check("floor", "pass", "8 % is within the limits")] },
  ],
  summary: [{ requirement_id: "cap", name: "Cost cap", criterion_id: "cost", passed: 2, failed: 0, unknown: 1 },
    { requirement_id: "floor", name: "Quality floor", criterion_id: "quality", passed: 2, failed: 1, unknown: 0 }],
};
async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(125); }); }
beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks(); vi.useRealTimers(); });

describe("feasibility beside the rankings", () => {
  it("lists every alternative in project order, a failure as fails and unknown as unknown, never pass", () => {
    render(<FeasibilityView result={feasibility}/>);
    expect(screen.getByLabelText("Feasibility label")).toHaveTextContent(
      "Feasibility: each requirement is tested on its own measurement; no score offsets a failure. It does not change any ranking.");
    const rows = within(screen.getByRole("table", { name: "Feasibility by alternative" })).getAllByRole("row").slice(1);
    expect(rows.map((r) => r.getAttribute("data-alternative-id"))).toEqual(["c", "a", "b"]);
    expect(rows[0]?.querySelector("td")).toHaveTextContent("fails");
    expect(rows[1]?.querySelector("td")).toHaveTextContent("unknown");
    expect(rows[1]).toHaveTextContent("no measurement");
    expect(rows[1]?.querySelector("td")).not.toHaveTextContent("pass");
    expect(screen.getByText(/Cost cap: 2 pass, 0 fail, 1 unknown/)).toBeInTheDocument();
    render(<StatusBadge result={feasibility} alternativeId="a"/>);
    expect(document.querySelector('span[data-feasibility="unknown"]')).toHaveTextContent("unknown (Cost cap)");
  });
  it("downloads its own JSON and CSV for the shown revision", async () => {
    const spy = vi.spyOn(api, "exportFeasibility").mockResolvedValue({ blob: new Blob(["x"]), filename: "f.csv" });
    render(<FeasibilityView result={feasibility} project={project}/>);
    fireEvent.click(screen.getByRole("button", { name: "Download feasibility CSV" }));
    await settle();
    expect(spy).toHaveBeenCalledWith({ project, expected_project_fingerprint: "fp", format: "csv" }, expect.any(AbortSignal));
    expect(saveDownload).toHaveBeenCalledWith(expect.any(Blob), "f.csv");
  });
  it("shows feasibility below a complete, unchanged ranking in Results", async () => {
    vi.spyOn(api, "analysisRecord").mockResolvedValue(structuredClone({ ...record, result: { ...record.result } }));
    const spy = vi.spyOn(api, "checkFeasibility").mockResolvedValue(structuredClone(feasibility));
    render(<ResultsPanel project={project} context={context} validation={{ issues: [] }}/>);
    await settle();
    expect(spy).toHaveBeenCalledWith(project, expect.any(AbortSignal));
    const ranking = within(screen.getByRole("table", { name: "Ranking" })).getAllByRole("row").slice(1);
    expect(ranking).toHaveLength(3);
    const beside = screen.getByRole("region", { name: "Feasibility beside the ranking" });
    expect(within(beside).getByRole("table", { name: "Feasibility by alternative" })).toHaveTextContent("fails");
  });
  it("adds no feasibility section when the project states no requirements", async () => {
    vi.spyOn(api, "analysisRecord").mockResolvedValue(structuredClone(record));
    const spy = vi.spyOn(api, "checkFeasibility");
    render(<ResultsPanel project={base} context={resolveContext(base, "fp", BASE_SELECTION)} validation={{ issues: [] }}/>);
    await settle();
    expect(spy).not.toHaveBeenCalled();
    expect(screen.queryByRole("region", { name: "Feasibility beside the ranking" })).toBeNull();
  });
  it("puts each alternative's status in its own column of the comparison, hiding no row", async () => {
    const cfg = { method: "mavt", parameters: {}, scenario_id: null, weight_profile_id: null };
    const comparison: MethodComparison = {
      project_id: "p1", project_fingerprint: "fp", configuration: cfg, methods: ["mavt"], alternative_order: ["c", "a", "b"],
      alternative_names: { c: "Gamma", a: "Alpha", b: "Beta" },
      columns: [{ method: "mavt", method_label: "MAVT (additive value)", status: "ok", configuration: cfg, inputs: ["x"], calculation_path: "mavt.v1",
        record_digest: "a".repeat(64), label: null, quantity_name: "overall value", quantity_range: "0 to 1", leaders: ["c"], error: null,
        cells: ["c", "a", "b"].map((id, k) => ({ alternative_id: id, rank: k + 1, quantity: 0.9 - k / 10, interval: null, class_id: null, class_share: null, notes: [] })) }],
      agreement: { leaders_agree: null, leader_groups: [], classes: [], reasons: [], context: "Agreement between methods that share inputs is not independent validation." },
    };
    vi.spyOn(api, "compareMethods").mockResolvedValue(comparison);
    vi.spyOn(api, "checkFeasibility").mockRejectedValueOnce(new Error("Requirements need attention"))
      .mockResolvedValue(structuredClone(feasibility));
    render(<ComparePanel project={project} context={context}/>);
    expect(screen.getByText("Checking requirements…")).toBeInTheDocument();
    await settle();
    expect(screen.getByRole("alert")).toHaveTextContent("Feasibility could not be checked: Requirements need attention");
    expect(screen.getByRole("table", { name: "Methods side by side" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry feasibility" }));
    await settle();
    const table = screen.getByRole("table", { name: "Methods side by side" });
    expect(within(table).getAllByRole("columnheader")[1]).toHaveTextContent("Feasibility");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((r) => r.getAttribute("data-alternative-id"))).toEqual(["c", "a", "b"]);
    expect(rows[0]).toHaveTextContent("fails (Quality floor)");
    expect(rows[0]).toHaveTextContent("1 · 0.9000");
    expect(rows[1]).toHaveTextContent("unknown (Cost cap)");
    expect(rows[2]).toHaveTextContent("passes");
  });
});
