import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Project } from "../../src/api/types";
import { AnalysisControls } from "../../src/components/AnalysisControls";
import { BASE_SELECTION, resolveContext, type AnalysisSelection } from "../../src/state/analysisContext";
import { META, node, projectWith } from "../fixtures";

function setup(selection: AnalysisSelection = BASE_SELECTION, parameters: Record<string, unknown> = {}) {
  const project: Project = projectWith([node("cost")], {
    analysis: { method: "mavt", scenario_id: null, weight_profile_id: null, parameters },
  });
  const onSelect = vi.fn(), onUse = vi.fn();
  render(<AnalysisControls project={project} context={resolveContext(project, "fp", selection)} onSelect={onSelect}
    methods={META.methods} onUseMethodAsDefault={onUse}/>);
  return { onSelect, onUse };
}

describe("method selection", () => {
  it("lists every registered method by label and marks the saved default", () => {
    setup();
    const options = within(screen.getByLabelText("Method")).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["AHP (pairwise priorities)", "MAVT (additive value) · saved", "Value-based sorting (MAVT)",
      "PROMETHEE II (outranking flows)", "SMAA-2 (sampled acceptability)"]);
    expect(screen.queryByRole("button", { name: "Use viewed method as saved default" })).toBeNull();
  });
  it("choosing a method is a view: it selects, and never writes the saved default", () => {
    const { onSelect, onUse } = setup();
    fireEvent.change(screen.getByLabelText("Method"), { target: { value: "mavt_sorting" } });
    expect(onSelect).toHaveBeenCalledWith({ method: "mavt_sorting", parameters: null }); // run settings do not follow
    expect(onUse).not.toHaveBeenCalled();
  });
  it("uses the viewed method as the saved default on request, at once when there are no parameters", () => {
    const { onUse } = setup({ ...BASE_SELECTION, method: "mavt_sorting" });
    expect(screen.getByRole("status")).toHaveTextContent("Viewing Value-based sorting (MAVT) with its default parameters");
    fireEvent.click(screen.getByRole("button", { name: "Use viewed method as saved default" }));
    expect(onUse).toHaveBeenCalledTimes(1);
  });
  it("lists the saved parameters it will clear and waits for confirmation", () => {
    const { onUse } = setup({ ...BASE_SELECTION, method: "mavt_sorting" }, { dominance_check: false });
    fireEvent.click(screen.getByRole("button", { name: "Use viewed method as saved default" }));
    expect(onUse).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toHaveTextContent("will be cleared: dominance_check");
    fireEvent.click(screen.getByRole("button", { name: "Use as saved default" }));
    expect(onUse).toHaveBeenCalledTimes(1);
  });
});

it("disables only API-confirmed missing setup and offers the editor without changing the method", async () => {
  vi.useFakeTimers();
  const { api } = await import("../../src/api/client");
  const { act } = await import("@testing-library/react");
  const project = projectWith([node("cost")]);
  const context = resolveContext(project, "fp", BASE_SELECTION), select = vi.fn(), open = vi.fn();
  vi.spyOn(api, "validateAnalysis").mockImplementation((_p, configuration) => Promise.resolve({ project_fingerprint: "fp", configuration,
    scenario_id: null, weight_profile_id: null, validation: { issues: configuration.method === "ahp"
      ? [{ severity: "error", code: "AHP_NOT_STATED", message: "Pairwise not stated", path: "ahp" }]
      : configuration.method === "smaa2" ? [{ severity: "error", code: "MISSING_MEASUREMENT", message: "Missing", path: "performances" }] : [] } }));
  const before = structuredClone(project);
  try {
    render(<AnalysisControls project={project} context={context} methods={META.methods} onSelect={select} onOpenTab={open}/>);
    await act(async () => { await vi.advanceTimersByTimeAsync(125); });
    expect(screen.getByRole("option", { name: "AHP (pairwise priorities): not set up for this study" })).toBeDisabled();
    expect(screen.getByRole("option", { name: /SMAA-2/ })).not.toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Set up AHP" })); expect(open).toHaveBeenCalledWith("pairwise");
    expect(select).not.toHaveBeenCalled(); expect(project).toEqual(before);
  } finally { vi.restoreAllMocks(); vi.useRealTimers(); }
});
