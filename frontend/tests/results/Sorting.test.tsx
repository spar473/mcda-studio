import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { AnyAnalysisRecord, MethodInfo } from "../../src/api/types";
import { ResultsPanel } from "../../src/components/ResultsPanel";
import { panelsFor, RESULT_PANELS } from "../../src/components/results/panels";
import { assertAnalysisRecord } from "../../src/state/useAnalysisRecord";
import { META } from "../fixtures";
import { context, project, record, sortingContext, sortingRecord } from "./fixture";

vi.mock("../../src/components/results/downloads", () => ({ saveDownload: vi.fn() }));
const methods: MethodInfo[] = META.methods;
const mavt = methods.find((m) => m.name === "mavt"), sorting = methods.find((m) => m.name === "mavt_sorting");
async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(125); }); }
function show(rec: AnyAnalysisRecord, ctx = sortingContext) {
  vi.spyOn(api, "analysisRecord").mockResolvedValue(structuredClone(rec));
  return render(<ResultsPanel project={project} context={ctx} validation={{ issues: [] }} methods={methods}/>);
}
beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

describe("the Results panel registry", () => {
  it("shows MAVT's six views and names Classes as not offered", () => {
    const { shown, missing } = panelsFor("mavt", mavt);
    expect(shown.map((p) => p.id)).toEqual(["overall", "contributions", "partial", "dominance", "comparison", "inspection"]);
    expect(missing.map((p) => p.label)).toEqual(["Classes", "Acceptability", "Flows", "PROMETHEE I", "Explanation against MAVT",
      "AHP priorities", "Consistency"]);
  });
  it("puts Classes first for sorting and keeps every MAVT view", () => {
    expect(panelsFor("mavt_sorting", sorting).shown.map((p) => p.id)).toEqual(["classes", ...(RESULT_PANELS.mavt ?? []).map((p) => p.id)]);
  });
  it("hides a registered panel whose capability the method does not declare", () => {
    const narrow: MethodInfo = { name: "mavt_sorting", label: "Narrow", capabilities: ["classes", "value_scores"], export_tables: ["ranking"] };
    expect(panelsFor("mavt_sorting", narrow).shown.map((p) => p.id)).toEqual(["classes", "overall"]);
  });
  it("offers nothing for a method without registered panels", () => {
    expect(panelsFor("unknown", undefined).shown).toEqual([]);
  });
});

describe("sorting results", () => {
  it("renders classes, assignments, the audit sample and class bands from the engine record", async () => {
    show(sortingRecord); await settle();
    const classes = screen.getByRole("table", { name: "Results classes" });
    expect(within(classes).getAllByRole("row").slice(1).map((r) => r.textContent)).toEqual([
      "1Go go0.5000 or moreSame, Same",
      expect.stringContaining("Stop stopbelow 0.5000"),
    ]);
    expect(screen.getByRole("table", { name: "Class assignments" })).toHaveTextContent("0.3000 from Go");
    expect(screen.getByLabelText("Audit sample")).toHaveTextContent("Audit sample below Go: 1 of 1");
    const bands = screen.getByTestId("class-bands");
    expect([...bands.querySelectorAll("rect")].map((r) => [r.getAttribute("x"), r.getAttribute("width")])).toEqual([["605", "325"], ["280", "325"]]);
    expect(screen.getByRole("navigation", { name: "Results views" })).toHaveTextContent(/^Classes/);
    expect(screen.getByLabelText("Views not offered")).toHaveTextContent("Value-based sorting (MAVT) does not offer: Acceptability, Flows, PROMETHEE I, Explanation against MAVT, AHP priorities, Consistency.");
    const tables = within(screen.getByLabelText("CSV table")).getAllByRole("option").map((o) => o.textContent);
    expect(tables).toEqual(["Overall ranking", "Classes", "Weighted contributions", "Partial values and measurements", "Dominance matrix", "Base versus scenario"]);
  });
  it("keeps MAVT's tables and names Classes as a view MAVT does not offer", async () => {
    show(record, context); await settle();
    expect(screen.queryByRole("table", { name: "Results classes" })).toBeNull();
    expect(screen.queryByTestId("class-bands")).toBeNull();
    expect(screen.getByLabelText("Views not offered")).toHaveTextContent("MAVT (additive value) does not offer: Classes, Acceptability, Flows, PROMETHEE I, Explanation against MAVT, AHP priorities, Consistency.");
    const tables = within(screen.getByLabelText("CSV table")).getAllByRole("option").map((o) => o.textContent);
    expect(tables).not.toContain("Classes");
  });
});

describe("record checks by method", () => {
  it("accepts a version-2 record for sorting and refuses mismatched versions", () => {
    expect(() => assertAnalysisRecord(sortingRecord, project, "fp", sortingContext.configuration, "first", null)).not.toThrow();
    expect(() => assertAnalysisRecord(record, project, "fp", sortingContext.configuration, "first", null)).toThrow(/does not match/);
    const asMavt = { ...sortingRecord, result: { ...sortingRecord.result, configuration: context.configuration } };
    expect(() => assertAnalysisRecord(asMavt, project, "fp", context.configuration, "first", null)).toThrow(/does not match/);
  });
  it("refuses a record whose version alone is wrong for the method", () => {
    // Every other field agrees with the context, so only the version check can refuse these.
    const v2AsMavt = { ...sortingRecord, result: { ...sortingRecord.result, method: "mavt", configuration: context.configuration } } as unknown as AnyAnalysisRecord;
    expect(() => assertAnalysisRecord(v2AsMavt, project, "fp", context.configuration, "first", null)).toThrow(/does not match/);
    const v1AsSorting = { ...record, result: { ...record.result, method: "mavt_sorting", configuration: sortingContext.configuration } } as unknown as AnyAnalysisRecord;
    expect(() => assertAnalysisRecord(v1AsSorting, project, "fp", sortingContext.configuration, "first", null)).toThrow(/does not match/);
  });
  it("refuses an alternative assigned twice or to an unlisted class", () => {
    const twice = structuredClone(sortingRecord);
    twice.result.assignments[2] = { ...twice.result.assignments[1]! }; // eslint-disable-line @typescript-eslint/no-non-null-assertion
    expect(() => assertAnalysisRecord(twice, project, "fp", sortingContext.configuration, "first", null)).toThrow(/Class assignments/);
    const stray = structuredClone(sortingRecord);
    stray.result.assignments[0] = { ...stray.result.assignments[0]!, class_id: "elsewhere" }; // eslint-disable-line @typescript-eslint/no-non-null-assertion
    expect(() => assertAnalysisRecord(stray, project, "fp", sortingContext.configuration, "first", null)).toThrow(/Class assignments/);
  });
});
