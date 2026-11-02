import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { SortingSensitivityProbe, SortingSensitivityResult } from "../../src/api/types";
import { SensitivityChart } from "../../src/components/SensitivityChart";
import { SensitivityPanel } from "../../src/components/SensitivityPanel";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import { node, projectWith } from "../fixtures";

const project = projectWith([node("team"), node("market", null, 1)], {
  analysis: { method: "mavt_sorting", scenario_id: null, weight_profile_id: null, parameters: {} },
  alternatives: [{ id: "a", name: "Alpha", metadata: {} }, { id: "b", name: "Beta", metadata: {} }],
  weight_profiles: [{ id: "first", name: "First", method: "swing", judgements: { team: 100, market: 50 } }],
});
const context = resolveContext(project, "rev1", BASE_SELECTION);
const classes = [
  { class_id: "go", name: "Go", rank: 1, lower_boundary: 0.55, upper_boundary: null },
  { class_id: "stop", name: "Stop", rank: 2, lower_boundary: null, upper_boundary: 0.55 },
];
const sweep: SortingSensitivityResult = {
  method: "mavt_sorting", boundary_tolerance: 1e-12, classes,
  node_id: "team", node_name: "TEAM", base_weight: 0.4,
  baseline_ranking: ["a", "b"], baseline_values: { a: 0.6, b: 0.5 },
  grid: [0, 0.4, 1], values: { a: [0.3, 0.6, 0.95], b: [0.9, 0.5, 0.1] },
  rankings: [["b", "a"], ["a", "b"], ["a", "b"]], crossovers: [], rank_change_points: [],
  first_winner_change_up: null, first_winner_change_down: null,
  ranking_stable_range: [0, 1], winner_stable_range: [0, 1], diagnostics: [],
  class_changes: [
    { alternative_id: "a", base_class_id: "go", class_stable_range: [0.3333, 1],
      change_points: [{ weight: 0.3333, boundary_class_id: "go", class_before: "stop", class_after: "go" }],
      first_change_down: { weight: 0.3333, boundary_class_id: "go", class_before: "stop", class_after: "go" }, first_change_up: null },
    { alternative_id: "b", base_class_id: "stop", class_stable_range: [0.2, 1],
      change_points: [{ weight: 0.2, boundary_class_id: "go", class_before: "go", class_after: "stop" }],
      first_change_down: { weight: 0.2, boundary_class_id: "go", class_before: "go", class_after: "stop" }, first_change_up: null },
  ],
};
function probeAt(weight: number): SortingSensitivityProbe {
  return {
    method: "mavt_sorting", boundary_tolerance: 1e-12, classes,
    class_by_alternative: { a: weight < 0.3333 ? "stop" : "go", b: weight < 0.2 ? "go" : "stop" },
    baseline_class_by_alternative: { a: "go", b: "stop" },
    project_fingerprint: "rev1", configuration: context.configuration, weight_profile_id: "first", scenario_id: null,
    node_id: "team", node_name: "TEAM", node_path: ["team"], weight, base_weight: 0.4,
    local_weights: { team: weight, market: 1 - weight }, global_weights: { team: weight, market: 1 - weight },
    path_shares: { team: weight, market: 1 - weight },
    alternatives: [
      { alternative_id: "a", name: "Alpha", value: 0.6, rank: 1, baseline_value: 0.6, baseline_rank: 1 },
      { alternative_id: "b", name: "Beta", value: 0.5, rank: 2, baseline_value: 0.5, baseline_rank: 2 },
    ],
    ranking: ["a", "b"], baseline_ranking: ["a", "b"], ranking_differs_from_baseline: false, winner_differs_from_baseline: false, diagnostics: [],
  };
}
async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(130); }); }
beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

describe("sorting sensitivity", () => {
  it("draws class bands and first class changes from the engine's boundaries and roots", () => {
    const names = new Map([["a", "Alpha"], ["b", "Beta"]]);
    render(<SensitivityChart result={sweep} names={names} visible={["a", "b"]} cursor={0.4} onCursor={() => undefined}/>);
    expect(screen.getByTestId("class-band-go")).toBeInTheDocument();
    expect(screen.getByTestId("class-band-stop")).toBeInTheDocument();
    const markers = [screen.getByTestId("class-change-a"), screen.getByTestId("class-change-b")];
    expect(markers.map((m) => m.getAttribute("cx"))).toEqual([(62 + 0.3333 * 520).toFixed(4).replace(/0+$/, ""), String(62 + 0.2 * 520)]);
    expect(markers[0]?.getAttribute("cy")).toBe(markers[1]?.getAttribute("cy")); // both sit on the Go boundary
  });
  it("lists first class changes, probes their exact weight and shows classes at the probed weight", async () => {
    vi.spyOn(api, "sensitivity").mockResolvedValue(structuredClone(sweep));
    const probe = vi.spyOn(api, "sensitivityProbe").mockImplementation((_p, _n, weight) => Promise.resolve(probeAt(weight)));
    render(<SensitivityPanel project={project} context={context} validation={{ issues: [] }} onSelectCriterion={() => undefined}/>);
    fireEvent.change(screen.getByLabelText("Criterion to vary"), { target: { value: "team" } });
    await settle(); await settle();
    const table = screen.getByRole("table", { name: "Class changes" });
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("AlphaGo0.3333 → Stopnone in this direction");
    fireEvent.click(within(table).getByRole("button", { name: "0.2000" }));
    await settle();
    expect(probe).toHaveBeenLastCalledWith(expect.anything(), "team", 0.2, context.configuration, expect.anything());
    const values = screen.getByRole("table", { name: "Sensitivity values" });
    // the last two columns: class at the probed weight, then at the baseline
    expect(within(values).getAllByRole("row")[1]?.textContent).toMatch(/StopGo$/);
    expect(within(values).getAllByRole("row")[2]?.textContent).toMatch(/StopStop$/);
  });
});
