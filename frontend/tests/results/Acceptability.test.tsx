import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { AnyAnalysisRecord, MethodInfo, Project } from "../../src/api/types";
import { AnalysisControls } from "../../src/components/AnalysisControls";
import { ResultsPanel } from "../../src/components/ResultsPanel";
import { panelsFor } from "../../src/components/results/panels";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import { assertAnalysisRecord } from "../../src/state/useAnalysisRecord";
import { META } from "../fixtures";
import { project, smaaContext, smaaRecord } from "./fixture";

vi.mock("../../src/components/results/downloads", () => ({ saveDownload: vi.fn() }));
const methods: MethodInfo[] = META.methods;
async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(125); }); }
beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

describe("SMAA-2 results", () => {
  it("shows only the Acceptability view, under its label", async () => {
    vi.spyOn(api, "analysisRecord").mockResolvedValue(structuredClone(smaaRecord));
    render(<ResultsPanel project={project} context={smaaContext} validation={{ issues: [] }} methods={methods}/>);
    await settle();
    expect(panelsFor("smaa2", methods.find((m) => m.name === "smaa2")).shown.map((p) => p.id)).toEqual(["acceptability"]);
    expect(screen.getByLabelText("Acceptability label")).toHaveTextContent("Sampled acceptability under these assumptions.");
    expect(screen.getByLabelText("Acceptability label")).toHaveTextContent("not a probability of success");
    expect(screen.getByLabelText("Acceptability provenance")).toHaveTextContent("1000 draws, seed 4, 95.0 % Clopper–Pearson intervals");
    expect(screen.queryByRole("table", { name: "Ranking" })).toBeNull(); // no MAVT score views
    const rows = within(screen.getByRole("table", { name: "Rank acceptability" })).getAllByRole("row");
    expect(rows[2]).toHaveTextContent("Same a62.0 % (59.0 %–65.0 %)38.0 % (35.0 %–41.0 %)0.0 % (0.0 %–3.0 %)60.0 % (57.0 %–63.0 %)2.0 %");
    expect(screen.getByRole("table", { name: "Class acceptability" })).toHaveTextContent("GoStop");
    expect(screen.getByRole("list", { name: "Inputs to check" })).toHaveTextContent("local weight of Cost under G: 80.0 % in the upper half");
    expect(screen.getByText(/Heuristic: association in these draws/)).toBeInTheDocument();
    expect(screen.getByTestId("acceptability-bars").querySelectorAll("rect[data-rank]")).toHaveLength(5);
    const tables = within(screen.getByLabelText("CSV table")).getAllByRole("option").map((o) => o.textContent);
    expect(tables).toEqual(["Rank acceptability", "Class acceptability", "Inputs to check"]);
  });
  it("refuses acceptabilities that do not match the project's alternatives", () => {
    const run = (r: AnyAnalysisRecord) => () => assertAnalysisRecord(r, project, "fp", smaaContext.configuration, "first", null);
    expect(run(smaaRecord)).not.toThrow();
    const dropped = structuredClone(smaaRecord); dropped.result.acceptability.pop();
    expect(run(dropped)).toThrow(/Acceptabilities/);
    const short = structuredClone(smaaRecord); short.result.acceptability[0]?.ranks.pop();
    expect(run(short)).toThrow(/Acceptabilities/);
  });
});

describe("SMAA-2 run settings", () => {
  function controls(selection = BASE_SELECTION) {
    const p: Project = structuredClone(project);
    const onSelect = vi.fn();
    render(<AnalysisControls project={p} context={resolveContext(p, "fp", selection)} onSelect={onSelect} methods={methods}/>);
    return onSelect;
  }
  it("appear only for a method with acceptability, and change the view, not the project", () => {
    controls();
    expect(screen.queryByLabelText("SMAA-2 run settings")).toBeNull();
  });
  it("send the tried settings as view parameters", () => {
    const onSelect = controls({ ...BASE_SELECTION, method: "smaa2" });
    fireEvent.change(screen.getByLabelText("Uncertain inputs"), { target: { value: "performance" } });
    expect(onSelect).toHaveBeenLastCalledWith({ parameters: { uncertainty: "performance" } });
    const seed = screen.getByLabelText("Seed");
    fireEvent.change(seed, { target: { value: "17" } }); fireEvent.blur(seed);
    expect(onSelect).toHaveBeenLastCalledWith({ parameters: { seed: 17 } });
  });
  it("merge over the viewed method's parameters in the request", () => {
    const context = resolveContext(project, "fp", { ...BASE_SELECTION, method: "smaa2", parameters: { samples: 5000 } });
    expect(context.configuration).toMatchObject({ method: "smaa2", parameters: { samples: 5000 } });
    expect(resolveContext(project, "fp", { ...BASE_SELECTION, method: "smaa2" }).configuration.parameters).toEqual({});
  });
});
