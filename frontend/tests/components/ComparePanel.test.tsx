import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { ComparisonColumn, MethodComparison } from "../../src/api/types";
import { ComparePanel } from "../../src/components/ComparePanel";
import { saveDownload } from "../../src/components/results/downloads";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import { project } from "../results/fixture";

vi.mock("../../src/components/results/downloads", () => ({ saveDownload: vi.fn() }));
const context = resolveContext(project, "fp", BASE_SELECTION);
const cfg = (method: string) => ({ method, parameters: {}, scenario_id: null, weight_profile_id: null });
const cell = (id: string, rank: number, quantity: number, extra: Partial<MethodComparison["columns"][number]["cells"][number]> = {}) =>
  ({ alternative_id: id, rank, quantity, interval: null, class_id: null, class_share: null, notes: [], ...extra });
function ok(method: string, label: string, quantity: [string, string], leaders: string[], cells: ReturnType<typeof cell>[], own: string | null = null): ComparisonColumn {
  return { method, method_label: label, status: "ok", configuration: cfg(method), inputs: [`inputs of ${method}`], calculation_path: `${method}.v1`,
    record_digest: "a".repeat(64), label: own, quantity_name: quantity[0], quantity_range: quantity[1], leaders, cells, error: null };
}
const comparison: MethodComparison = {
  project_id: "p1", project_fingerprint: "fp", configuration: cfg("mavt"), methods: ["mavt", "smaa2", "promethee2", "ahp"],
  alternative_order: ["c", "a", "b"], alternative_names: { c: "Gamma", a: "Alpha", b: "Beta" },
  columns: [
    ok("mavt", "MAVT (additive value)", ["overall value", "0 to 1"], ["a"], [cell("c", 3, 0.2), cell("a", 1, 0.7), cell("b", 2, 0.6)]),
    ok("smaa2", "SMAA-2 (sampled acceptability)", ["rank-1 acceptability", "share of draws, 0 to 1"], ["b"],
      [cell("c", 3, 0.1, { interval: [0.08, 0.12] }), cell("a", 2, 0.4, { interval: [0.38, 0.42] }), cell("b", 1, 0.5, { interval: [0.48, 0.52], notes: ["tied for first in 1.0% of draws"] })],
      "sampled acceptability under these assumptions"),
    ok("promethee2", "PROMETHEE II (outranking flows)", ["net flow", "-1 to 1"], ["a"],
      [cell("c", 3, -0.6), cell("a", 1, 0.4), cell("b", 2, 0.2, { notes: ["incomparable with Alpha under PROMETHEE I"] })], "net outranking flows: these compare the alternatives with one another and are not preference values"),
    { method: "ahp", method_label: "AHP (pairwise priorities)", status: "failed", configuration: cfg("ahp"), inputs: ["pairwise judgements (ahp)"],
      calculation_path: null, record_digest: null, label: null, quantity_name: "AHP priority", quantity_range: "share of the goal, 0 to 1",
      leaders: [], cells: [], error: { status: 422, code: "VALIDATION_FAILED", message: "invalid", issue_codes: ["AHP_NOT_STATED"] } },
  ],
  agreement: { leaders_agree: false, leader_groups: [{ leaders: ["a"], methods: ["mavt", "promethee2"] }, { leaders: ["b"], methods: ["smaa2"] }],
    classes: [], reasons: [{ method: "smaa2", leaders: ["b"], mavt_leaders: ["a"], reasons: ["Beta takes rank 1 in 50.0% of draws (48.0% to 52.0%)"] }],
    context: "Agreement between methods that share inputs is not independent validation." },
};
async function setup(result: MethodComparison = comparison) {
  const spy = vi.spyOn(api, "compareMethods").mockResolvedValue(structuredClone(result));
  const onOpenTab = vi.fn();
  render(<ComparePanel project={project} context={context} onOpenTab={onOpenTab}/>);
  await act(async () => { await vi.advanceTimersByTimeAsync(125); });
  return { spy, onOpenTab };
}
beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

describe("the Compare tab", () => {
  it("shows one column per method, naming its method, inputs, parameters and own label", async () => {
    const { spy } = await setup();
    expect(spy).toHaveBeenCalledWith(project, context.configuration, expect.any(AbortSignal));
    const table = screen.getByRole("table", { name: "Methods side by side" });
    const headers = within(table).getAllByRole("columnheader").slice(1);
    expect(headers.map((h) => h.getAttribute("data-method"))).toEqual(["mavt", "smaa2", "promethee2", "ahp"]);
    expect(headers[0]).toHaveTextContent("MAVT (additive value)overall value (0 to 1) · rankReads: inputs of mavtParameters: defaults");
    expect(headers[1]).toHaveTextContent("sampled acceptability under these assumptions");
    expect(headers[2]).toHaveTextContent("net flow (-1 to 1)");
    expect(screen.getByLabelText("Comparison context")).toHaveTextContent("Agreement between methods that share inputs is not independent validation.");
    expect(screen.queryByText(/consensus score/i)).toBeInTheDocument(); // only in the explanation that there is none
  });
  it("shows each method's own numbers, a failed method's typed error, and opens the tab that fixes it", async () => {
    const { onOpenTab } = await setup();
    const beta = screen.getByRole("table", { name: "Methods side by side" }).querySelector('tr[data-alternative-id="b"]');
    expect(beta).toHaveTextContent("2 · 0.6000");
    expect(beta).toHaveTextContent("1 · 50.0 % (48.0 %–52.0 %)");
    expect(beta).toHaveTextContent("2 · +0.2000incomparable with Alpha under PROMETHEE I");
    const first = screen.getByRole("table", { name: "Methods side by side" }).querySelector('tr[data-alternative-id="c"] td[data-method="ahp"]');
    expect(first).toHaveTextContent("Did not run: VALIDATION_FAILED (AHP_NOT_STATED)");
    fireEvent.click(screen.getByRole("button", { name: "Open pairwise" }));
    expect(onOpenTab).toHaveBeenCalledWith("pairwise");
  });
  it("draws each quantity on its own axis, never a shared one", async () => {
    await setup();
    const flow = screen.getByLabelText("PROMETHEE II (outranking flows) net flow for Gamma");
    expect([flow.getAttribute("min"), flow.getAttribute("max")]).toEqual(["-1", "1"]);
    const value = screen.getByLabelText("MAVT (additive value) overall value for Gamma");
    expect([value.getAttribute("min"), value.getAttribute("max")]).toEqual(["0", "1"]);
  });
  it("states where the methods differ, with each method's reason", async () => {
    await setup();
    expect(screen.getByRole("list", { name: "First place by method" })).toHaveTextContent(
      "Alpha: MAVT (additive value), PROMETHEE II (outranking flows)Beta: SMAA-2 (sampled acceptability)");
    expect(screen.getByLabelText("Why smaa2 differs")).toHaveTextContent(
      "SMAA-2 (sampled acceptability) puts Beta first where MAVT puts Alpha:Beta takes rank 1 in 50.0% of draws (48.0% to 52.0%)");
  });
  it("orders rows by one column's own rank and downloads the comparison", async () => {
    await setup();
    fireEvent.change(screen.getByLabelText("Order rows by"), { target: { value: "smaa2" } });
    const rows = within(screen.getByRole("table", { name: "Methods side by side" })).getAllByRole("row").slice(1);
    expect(rows.map((r) => r.getAttribute("data-alternative-id"))).toEqual(["b", "a", "c"]);
    const exportSpy = vi.spyOn(api, "exportComparison").mockResolvedValue({ blob: new Blob(["x"]), filename: "c.csv" });
    fireEvent.click(screen.getByRole("button", { name: "Download comparison CSV" }));
    await act(async () => { await Promise.resolve(); });
    expect(exportSpy.mock.calls[0]?.[0]).toMatchObject({ expected_project_fingerprint: "fp", format: "csv" });
    expect(saveDownload).toHaveBeenCalled();
  });
  it("says when every method that ran agrees, and when fewer than two ran", async () => {
    const agreed = structuredClone(comparison);
    agreed.agreement = { ...agreed.agreement, leaders_agree: true, leader_groups: [{ leaders: ["a"], methods: ["mavt", "promethee2"] }], reasons: [] };
    await setup(agreed);
    expect(screen.getByLabelText("Agreement")).toHaveTextContent("Every method that ran puts Alpha first.");
  });
});
