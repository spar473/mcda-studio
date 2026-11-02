import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { AnyAnalysisRecord, MethodInfo } from "../../src/api/types";
import { ResultsPanel } from "../../src/components/ResultsPanel";
import { FLOW_AXIS, flowX } from "../../src/components/results/FlowsView";
import { panelsFor } from "../../src/components/results/panels";
import { assertAnalysisRecord } from "../../src/state/useAnalysisRecord";
import { META } from "../fixtures";
import { project, prometheeContext, prometheeRecord } from "./fixture";

vi.mock("../../src/components/results/downloads", () => ({ saveDownload: vi.fn() }));
const methods: MethodInfo[] = META.methods;
async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(125); }); }
async function show(record: AnyAnalysisRecord = prometheeRecord) {
  vi.spyOn(api, "analysisRecord").mockResolvedValue(structuredClone(record));
  render(<ResultsPanel project={project} context={prometheeContext} validation={{ issues: [] }} methods={methods}/>);
  await settle();
}
beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

describe("PROMETHEE II results", () => {
  it("shows the flow views under the label and no MAVT value view", async () => {
    await show();
    expect(panelsFor("promethee2", methods.find((m) => m.name === "promethee2")).shown.map((p) => p.id))
      .toEqual(["flows", "partial_order", "explanation"]);
    const label = screen.getByLabelText("Flow label");
    expect(label).toHaveTextContent("Net outranking flows: these compare the alternatives with one another and are not preference values.");
    expect(screen.getByLabelText("Flow provenance")).toHaveTextContent("PROMETHEE II (outranking flows) · calculation promethee2.v1");
    expect(screen.queryByRole("table", { name: "Ranking" })).toBeNull();
    expect(screen.queryByText(/compensatory MAVT preference values/)).toBeNull();
    const rows = within(screen.getByRole("table", { name: "Outranking flows" })).getAllByRole("row");
    expect(rows.map((r) => r.textContent)).toEqual([
      "RankAlternativePositive flowNegative flowNet flow",
      "1Same a0.60000.1000+0.5000",
      "2C c0.30000.4000−0.1000",
      "3Same b0.35000.7500−0.4000",
    ]);
    const headers = within(screen.getByRole("table", { name: "Outranking flows" })).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers.some((h) => /value|score/i.test(h))).toBe(false);
    const options = within(screen.getByLabelText("CSV table")).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Outranking flows", "Single-criterion flows", "PROMETHEE I relations", "Explanation against MAVT"]);
    expect(screen.getByRole("navigation", { name: "Results views" })).toHaveTextContent("FlowsPROMETHEE IExplanation against MAVT");
  });
  it("draws net flows from zero on the fixed −1 to 1 axis, never the 0–1 value axis", async () => {
    await show();
    expect(FLOW_AXIS).toEqual({ min: -1, max: 1 });
    const chart = screen.getByTestId("flow-bars");
    expect(chart).toHaveAccessibleName(/fixed axis from −1 to 1/);
    expect(chart).toHaveTextContent("net flow (−1 to 1), not a preference value");
    expect([...chart.querySelectorAll("text[data-tick]")].map((t) => t.textContent)).toEqual(["−1", "−0.5", "0", "+0.5", "+1"]);
    const zero = flowX(0);
    expect(flowX(-1)).toBe(280); expect(flowX(1)).toBe(930); expect(zero).toBe(605);
    const bar = (id: string) => chart.querySelector(`g[data-alternative-id="${id}"] rect`);
    expect(Number(bar("a")?.getAttribute("x"))).toBe(zero);
    expect(Number(bar("a")?.getAttribute("width"))).toBeCloseTo(0.5 * 325);
    expect(Number(bar("b")?.getAttribute("x"))).toBeCloseTo(zero - 0.4 * 325);
    expect(Number(bar("b")?.getAttribute("width"))).toBeCloseTo(0.4 * 325);
  });
  it("lists each alternative's PROMETHEE I relations, incomparable first", async () => {
    await show();
    expect(screen.getByLabelText("Incomparable pairs")).toHaveTextContent("Incomparable: C and Same.");
    const table = screen.getByRole("table", { name: "PROMETHEE I relations" });
    const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Alternative", "Incomparable with", "Preferred to", "Indifferent to", "Below"]);
    const row = (id: string) => table.querySelector(`tr[data-alternative-id="${id}"]`);
    expect(row("a")).toHaveTextContent("Same—C, Same——");
    expect(row("c")).toHaveTextContent("CSame——Same");
    expect(row("b")).toHaveTextContent("SameC——Same");
  });
  it("explains every pair ordered differently, with zones, thresholds and reasons", async () => {
    await show();
    const pairs = within(screen.getByRole("list", { name: "Pairs ordered differently" })).getAllByRole("listitem")
      .filter((li) => li.hasAttribute("data-pair"));
    expect(pairs.map((li) => li.getAttribute("data-pair"))).toEqual(["b|a", "b|c"]);
    expect(pairs[0]).toHaveTextContent("Flow gap −0.9000 (net flow) = head-to-head −0.5000 + via the other alternatives −0.4000");
    const criteria = within(screen.getByRole("table", { name: "Criteria for Same and Same" })).getAllByRole("row");
    expect(criteria[1]).toHaveTextContent("Cost-4Samefull preference, capped · q = 1, p = 3−1.0000−0.6667−0.1000");
    expect(criteria[2]).toHaveTextContent("full preference, capped · usual function");
    expect(screen.getByRole("list", { name: "Reasons for Same and Same" })).toHaveTextContent("beyond p = 3, so PROMETHEE counts full preference and no more");
    expect(pairs[1]).toHaveTextContent("Criterion detail is given for the first 1 pairs; this pair lists its gaps only.");
    expect(screen.getByRole("table", { name: "Rank comparison" })).toHaveTextContent("Same11C32Same13");
  });
  it("says why the explanation is missing and refuses its table", async () => {
    const missing = structuredClone(prometheeRecord);
    missing.result.explanation = { available: false, unavailable_reason: "MAVT's model is not valid under this weight profile and scenario",
      unavailable_codes: ["MISSING_VALUE_FUNCTION"], detail_limit: 50, ranks: [], pairs: [] };
    await show(missing);
    expect(screen.getByLabelText("Explanation unavailable")).toHaveTextContent("MAVT's model is not valid under this weight profile and scenario (MISSING_VALUE_FUNCTION).");
    const option = within(screen.getByLabelText("CSV table")).getByRole("option", { name: "Explanation against MAVT" });
    expect(option).toBeDisabled();
  });
  it("refuses flows that do not match the project's alternatives", () => {
    const run = (r: AnyAnalysisRecord) => () => assertAnalysisRecord(r, project, "fp", prometheeContext.configuration, "first", null);
    expect(run(prometheeRecord)).not.toThrow();
    const dropped = structuredClone(prometheeRecord); dropped.result.flows.pop();
    expect(run(dropped)).toThrow(/Outranking flows/);
    const valued = structuredClone(prometheeRecord); const first = valued.result.ranking[0]; if (first) first.value = 0.75;
    expect(run(valued)).toThrow(/Outranking flows/);
    const pair = structuredClone(prometheeRecord); pair.result.partial_order.pop();
    expect(run(pair)).toThrow(/Outranking flows/);
  });
});
