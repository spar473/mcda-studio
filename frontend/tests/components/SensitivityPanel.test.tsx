import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { SensitivityProbe, SensitivityResult } from "../../src/api/types";
import { SensitivityPanel } from "../../src/components/SensitivityPanel";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import { node, projectWith } from "../fixtures";

const project = projectWith([node("team"), node("founder", "team"), node("coverage", "team", 1), node("market", null, 1)], {
  analysis: { method: "mavt", scenario_id: null, weight_profile_id: null, parameters: {} },
  alternatives: [{ id: "a", name: "Alpha", metadata: {} }, { id: "b", name: "Beta", metadata: {} }],
  weight_profiles: [{ id: "first", name: "First", method: "swing", judgements: { team: 100, market: 50, founder: 65, coverage: 35 } }],
});
const context = resolveContext(project, "rev1", BASE_SELECTION);

const sweep: SensitivityResult = {
  node_id: "team", node_name: "TEAM", base_weight: 0.4,
  baseline_ranking: ["a", "b"], baseline_values: { a: 0.6, b: 0.5 },
  grid: [0, 0.25, 0.4, 0.5, 0.75, 1], values: { a: [0.3, 0.5, 0.6, 0.65, 0.8, 0.95], b: [0.9, 0.7, 0.5, 0.45, 0.3, 0.1] },
  rankings: [["b", "a"], ["b", "a"], ["a", "b"], ["a", "b"], ["a", "b"], ["a", "b"]],
  crossovers: [{ alternative_a: "a", alternative_b: "b", weight: 0.375, leader_before: "b", leader_after: "a" }],
  rank_change_points: [0.375], first_winner_change_up: null,
  first_winner_change_down: { weight: 0.375, from_winner: "a", to_winner: "b" },
  ranking_stable_range: [0.375, 1], winner_stable_range: [0.375, 1], diagnostics: [],
};
const provenance = { project_fingerprint: "rev1", configuration: context.configuration, weight_profile_id: "first", scenario_id: null };
function probeAt(weight: number, over: Partial<SensitivityProbe> = {}): SensitivityProbe {
  return {
    ...provenance, node_id: "team", node_name: "TEAM", node_path: ["team"], weight, base_weight: 0.4,
    local_weights: { team: weight, market: 1 - weight }, global_weights: { founder: 0.6 * weight, coverage: 0.4 * weight, market: 1 - weight },
    path_shares: { team: weight, market: 1 - weight },
    alternatives: [
      { alternative_id: "a", name: "Alpha", value: 0.6, rank: 1, baseline_value: 0.6, baseline_rank: 1 },
      { alternative_id: "b", name: "Beta", value: 0.5, rank: 2, baseline_value: 0.5, baseline_rank: 2 },
    ],
    ranking: ["a", "b"], baseline_ranking: ["a", "b"],
    ranking_differs_from_baseline: false, winner_differs_from_baseline: false, diagnostics: [], ...over,
  };
}

function setup(ctx = context) {
  const onSelectCriterion = vi.fn();
  const view = render(<SensitivityPanel project={project} context={ctx} validation={{ issues: [] }} onSelectCriterion={onSelectCriterion} />);
  return { ...view, onSelectCriterion };
}
async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(130); }); }
/** The sweep lands first; only then does the cursor exist, so the probe is a second request. */
async function chooseTeam() {
  fireEvent.change(screen.getByLabelText("Criterion to vary"), { target: { value: "team" } });
  await settle();
  await settle();
}

const sweepSpy = () => vi.mocked(api.sensitivity);
const probeSpy = () => vi.mocked(api.sensitivityProbe);
beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(api, "sensitivity").mockResolvedValue(sweep);
  vi.spyOn(api, "sensitivityProbe").mockImplementation((_p, _n, w) => Promise.resolve(probeAt(w)));
});
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

describe("sensitivity exploration is read-only and engine-backed", () => {
  it("Retry re-requests a failed sweep, then a failed probe, without edits or saves", async () => {
    sweepSpy().mockRejectedValueOnce(new Error("Sweep unavailable"));
    probeSpy().mockRejectedValueOnce(new Error("Probe unavailable"));
    const edit = vi.spyOn(api, "edit"), save = vi.spyOn(api, "saveProject"); const before = structuredClone(project);
    setup(); await chooseTeam();
    expect(screen.getByRole("alert")).toHaveTextContent("Sweep unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry sensitivity" }));
    await settle(); await settle();
    expect(screen.getByRole("alert")).toHaveTextContent("Probe unavailable");
    expect(screen.getByRole("list", { name: "Exact crossovers" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry probe" }));
    await settle();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(sweepSpy()).toHaveBeenCalledTimes(2); expect(probeSpy()).toHaveBeenCalledTimes(2);
    expect(probeSpy().mock.calls[1]?.slice(0, 3)).toEqual(probeSpy().mock.calls[0]?.slice(0, 3));
    expect(edit).not.toHaveBeenCalled(); expect(save).not.toHaveBeenCalled(); expect(project).toEqual(before);
  });
  it("never sends an edit or a save, however much the cursor moves", async () => {
    const edit = vi.spyOn(api, "edit"), save = vi.spyOn(api, "saveProject");
    const before = structuredClone(project);
    setup(); await chooseTeam();
    for (const w of ["0.1", "0.9", "0.375"]) {
      const input = screen.getByLabelText("Hypothetical local weight");
      fireEvent.change(input, { target: { value: w } });
      fireEvent.blur(input);
      await settle();
    }
    expect(edit).not.toHaveBeenCalled();
    expect(save).not.toHaveBeenCalled();
    expect(project).toEqual(before);   // the model itself is untouched
  });

  it("asks the engine for an arbitrary weight instead of interpolating the grid", async () => {
    setup(); await chooseTeam();
    probeSpy().mockClear();
    // 0.375 is the exact crossover and is NOT one of the grid points.
    expect(sweep.grid).not.toContain(0.375);
    fireEvent.click(screen.getByRole("button", { name: "0.3750" }));
    await settle();
    expect(probeSpy()).toHaveBeenCalledWith(project, "team", 0.375, context.configuration, expect.any(AbortSignal));
  });

  it("shows engine competition ranks, so a tie does not become a unique winner", async () => {
    probeSpy().mockImplementation((_p, _n, w) => Promise.resolve(probeAt(w, {
      alternatives: [
        { alternative_id: "a", name: "Alpha", value: 0.55, rank: 1, baseline_value: 0.6, baseline_rank: 1 },
        { alternative_id: "b", name: "Beta", value: 0.55, rank: 1, baseline_value: 0.5, baseline_rank: 2 },
      ],
      diagnostics: [{ severity: "info", code: "TIED_ALTERNATIVES", message: "tied", path: "" }],
    })));
    setup(); await chooseTeam();
    const rows = within(screen.getByRole("table", { name: "Sensitivity values" })).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell")[0]?.textContent)).toEqual(["1", "1"]);
    expect(screen.getByText("TIED_ALTERNATIVES")).toBeVisible();
  });

  it("reports a rank change below the winner without calling it a winner change", async () => {
    probeSpy().mockImplementation((_p, _n, w) => Promise.resolve(probeAt(w, {
      ranking_differs_from_baseline: true, winner_differs_from_baseline: false,
    })));
    setup(); await chooseTeam();
    expect(screen.getByText(/Competition ranks change below the top; the rank-one winner set is unchanged/)).toBeVisible();
    expect(screen.queryByText(/rank-one winner set differs/)).not.toBeInTheDocument();
  });

  it("refuses to plot a criterion the engine cannot vary, and says why", () => {
    const onlyChild = projectWith([node("solo"), node("kid", "solo")], {
      analysis: { method: "mavt", scenario_id: null, weight_profile_id: null, parameters: {} },
      weight_profiles: [{ id: "first", name: "First", method: "swing", judgements: {} }],
    });
    render(<SensitivityPanel project={onlyChild} context={resolveContext(onlyChild, "r", BASE_SELECTION)}
      validation={{ issues: [] }} onSelectCriterion={vi.fn()} />);
    expect(screen.getByText(/No criterion in this model can be varied/)).toBeVisible();
    expect(sweepSpy()).not.toHaveBeenCalled();
  });

  it("does not calculate while the model has validation errors", async () => {
    render(<SensitivityPanel project={project} context={context} onSelectCriterion={vi.fn()}
      validation={{ issues: [{ severity: "error", code: "X", message: "bad", path: "" }] }} />);
    await chooseTeam();
    expect(sweepSpy()).not.toHaveBeenCalled();
    expect(screen.getByText(/1 validation error/)).toBeVisible();
  });

  it("hiding an alternative is a view change that never renormalises the model", async () => {
    setup(); await chooseTeam();
    probeSpy().mockClear(); sweepSpy().mockClear();
    fireEvent.click(screen.getByRole("checkbox", { name: /Beta/ }));
    await settle();
    expect(screen.queryByTestId("series-b")).not.toBeInTheDocument();
    expect(screen.getByText(/1 alternative\(s\) hidden/)).toBeVisible();
    // Hidden rows stay in the numbers, and nothing was recalculated.
    expect(within(screen.getByRole("table", { name: "Sensitivity values" })).getByText("Beta")).toBeVisible();
    expect(probeSpy()).not.toHaveBeenCalled();
    expect(sweepSpy()).not.toHaveBeenCalled();
  });

  it("rejects a probe that came back for another profile", async () => {
    probeSpy().mockResolvedValue(probeAt(0.4, { weight_profile_id: "someone_else" }));
    setup(); await chooseTeam();
    expect(screen.getByRole("alert")).toHaveTextContent(/does not match/);
    expect(screen.queryByRole("table", { name: "Sensitivity values" })).not.toBeInTheDocument();
  });

  it("rejects a probe that answered an older cursor position", async () => {
    probeSpy().mockImplementation(() => Promise.resolve(probeAt(0.4)));  // always answers 0.4
    setup(); await chooseTeam();
    const input = screen.getByLabelText("Hypothetical local weight");
    fireEvent.change(input, { target: { value: "0.9" } });
    fireEvent.blur(input);
    await settle();
    expect(screen.getByRole("alert")).toHaveTextContent(/does not match/);
  });

  it("rejects a sweep that came back for another criterion", async () => {
    sweepSpy().mockResolvedValue({ ...sweep, node_id: "market" });
    setup(); await chooseTeam();
    expect(screen.getByRole("alert")).toHaveTextContent(/does not match the selected criterion/);
    expect(screen.queryByTestId("sensitivity-chart")).not.toBeInTheDocument();
  });

  it("hides a previous criterion's chart immediately when the context changes", async () => {
    const view = setup(); await chooseTeam();
    expect(screen.getByTestId("sensitivity-chart")).toBeVisible();
    view.rerender(<SensitivityPanel project={project} context={{ ...context, fingerprint: "rev2" }}
      validation={{ issues: [] }} onSelectCriterion={vi.fn()} />);
    expect(screen.queryByTestId("sensitivity-chart")).not.toBeInTheDocument();
  });

  it("labels the resolved context and the axes without needing hover", async () => {
    setup(); await chooseTeam();
    expect(screen.getByLabelText("Sensitivity context")).toHaveTextContent(/Profile “First”/);
    expect(screen.getByLabelText("Sensitivity context")).toHaveTextContent(/base model/);
    const chart = screen.getByTestId("sensitivity-chart");
    expect(chart).toHaveTextContent(/Local weight of TEAM/);
    expect(chart).toHaveTextContent("Overall MAVT value");
    expect(screen.getByLabelText("Stability intervals")).toHaveTextContent("0.375");
  });


  it("never probes a weight outside [0, 1]", async () => {
    setup(); await chooseTeam();
    probeSpy().mockClear();
    for (const bad of ["1.5", "-0.2", "7"]) {
      const input = screen.getByLabelText("Hypothetical local weight");
      fireEvent.change(input, { target: { value: bad } });
      fireEvent.blur(input);
      await settle();
    }
    expect(probeSpy()).not.toHaveBeenCalled();
  });
});


it("describes a newly tied winner set using backend flags, even when ID order stays the same", async () => {
  probeSpy().mockImplementation((_p, _n, w) => Promise.resolve(probeAt(w, {
    ranking_differs_from_baseline: true, winner_differs_from_baseline: true,
    alternatives: [
      { alternative_id: "a", name: "Alpha", value: .55, rank: 1, baseline_value: .6, baseline_rank: 1 },
      { alternative_id: "b", name: "Beta", value: .55, rank: 1, baseline_value: .5, baseline_rank: 2 },
    ],
  })));
  setup(); await chooseTeam();
  expect(screen.getByText(/rank-one winner set differs from the baseline \(including ties\)/)).toBeVisible();
  expect(screen.queryByText(/The ranking is unchanged/)).not.toBeInTheDocument();
});
