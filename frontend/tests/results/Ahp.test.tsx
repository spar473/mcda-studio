import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { AnyAnalysisRecord, MethodInfo } from "../../src/api/types";
import { ResultsPanel } from "../../src/components/ResultsPanel";
import { panelsFor } from "../../src/components/results/panels";
import { assertAnalysisRecord } from "../../src/state/useAnalysisRecord";
import { META } from "../fixtures";
import { ahpContext, ahpRecord, project } from "./fixture";

vi.mock("../../src/components/results/downloads", () => ({ saveDownload: vi.fn() }));
const methods: MethodInfo[] = META.methods;
async function show(record: AnyAnalysisRecord = ahpRecord) {
  vi.spyOn(api, "analysisRecord").mockResolvedValue(structuredClone(record));
  render(<ResultsPanel project={project} context={ahpContext} validation={{ issues: [] }} methods={methods}/>);
  await act(async () => { await vi.advanceTimersByTimeAsync(125); });
}
beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

describe("AHP results", () => {
  it("shows the priorities under the label and no MAVT value view", async () => {
    await show();
    expect(panelsFor("ahp", methods.find((m) => m.name === "ahp")).shown.map((p) => p.id)).toEqual(["priorities", "consistency"]);
    expect(screen.getByLabelText("AHP label")).toHaveTextContent(
      "AHP priorities under these pairwise judgements: shares of the goal that sum to one, not MAVT values or swing weights.");
    expect(screen.getByLabelText("AHP provenance")).toHaveTextContent("distributive synthesis · random index saaty-tran-2007");
    expect(screen.getByLabelText("AHP provenance")).toHaveTextContent("reads no weight profile or scenario");
    expect(screen.queryByRole("table", { name: "Ranking" })).toBeNull();
    const rows = within(screen.getByRole("table", { name: "AHP priorities" })).getAllByRole("row").map((r) => r.textContent);
    expect(rows).toEqual(["RankAlternativeAHP priority", "1Same a0.5000", "2C c0.3000", "3Same b0.2000"]);
    expect(screen.getByTestId("ahp-bars")).toHaveTextContent("AHP priority (shares sum to 1), not a preference value");
    expect(screen.getByRole("table", { name: "Criterion priorities" })).toHaveTextContent("Cost0.75000.7500");
    const options = within(screen.getByLabelText("CSV table")).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["AHP priorities", "Criterion priorities", "Local priorities by leaf", "Consistency"]);
  });
  it("lists every matrix's consistency, inconsistent first, with its triad", async () => {
    await show();
    const rows = within(screen.getByRole("table", { name: "AHP consistency" })).getAllByRole("row").slice(1);
    expect(rows.map((r) => r.getAttribute("data-matrix"))).toEqual(["alternatives:quality", "criteria:g", "alternatives:cost"]);
    expect(rows[0]).toHaveTextContent("Alternatives on Quality33.72800.36400.520.7000");
    expect(rows[0]).toHaveTextContent("above 0.10");
    expect(rows[0]).toHaveTextContent("C over Same: 9; Same over Same: 5; C over Same: 1/3, where consistency would need 45");
    expect(rows[1]).not.toHaveTextContent("above 0.10");
  });
  it("refuses priorities that do not match the project", () => {
    const run = (r: AnyAnalysisRecord) => () => assertAnalysisRecord(r, project, "fp", ahpContext.configuration, "first", null);
    expect(run(ahpRecord)).not.toThrow();
    const dropped = structuredClone(ahpRecord); dropped.result.alternatives.pop();
    expect(run(dropped)).toThrow(/AHP priorities/);
    const valued = structuredClone(ahpRecord); const first = valued.result.ranking[0]; if (first) first.value = 0.9;
    expect(run(valued)).toThrow(/AHP priorities/);
    const profiled = structuredClone(ahpRecord); profiled.result.weight_profile_id = "first";
    expect(run(profiled)).toThrow(/does not match/);
  });
});
