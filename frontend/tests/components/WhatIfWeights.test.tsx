import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import summaryJSON from "../fixtures/screening-summary.json";
import projectJSON from "../fixtures/screening-study-project.json";
import { ScreeningSummaryView } from "../../src/components/results/ScreeningSummaryView";
import type { Project, ScreeningSummary, ScreeningWhatIf } from "../../src/api/types";
import { WhatIfWeights } from "../../src/components/WhatIfWeights";
import type { WeightTrial } from "../../src/state/useWeightTrial";
const controls: ScreeningWhatIf["controls"] = [
  { criterion_id: "team", name: "Team", raw_rating: 250.12345678901235, local_weight: .6000000000000001, global_share: .6000000000000001, slider_min: 0, slider_max: 250.12345678901235, step: "any" },
  { criterion_id: "market", name: "Market", raw_rating: 90, local_weight: .3999999999999999, global_share: .3999999999999999, slider_min: 0, slider_max: 100, step: "any" },
];
const preview: ScreeningWhatIf = { project_fingerprint: "source", configuration: { method: "mavt", weight_profile_id: null, scenario_id: null, parameters: {} },
  status: "available", reason: "", ratings: {}, controls, weight_profile_id: "first", scenario_id: null, trial_project_fingerprint: "trial", summary: null, record: null };
function trial(): WeightTrial {
  return { sourceKey: "source", generation: 0, open: true, active: false, ratings: {}, baseline: controls,
    setOpen: vi.fn(), reset: vi.fn(), change: vi.fn(), acceptBaseline: vi.fn() };
}
it("renders exactly the backend controls and engine weights, with exact uncapped fractional input and no save action", () => {
  const state = trial(); render(<WhatIfWeights trial={state} request={{ status: "ready", result: preview }} supported/>);
  expect(screen.getAllByRole("slider").map(slider => slider.getAttribute("aria-label"))).toEqual(["What-if Team", "What-if Market"]);
  const slider = screen.getByRole("slider", { name: "What-if Team" });
  expect(slider).toHaveAttribute("step", "any"); expect(slider).toHaveAttribute("max", "250.12345678901235"); expect(slider).toHaveValue("250.12345678901235");
  expect(slider).toHaveAttribute("aria-valuetext", "250.1235 raw rating"); expect(screen.getByText("Engine normalised weight: 60.0 %", { exact: true })).toBeVisible();
  fireEvent.change(slider, { target: { value: "137.12345678901235" } }); expect(state.change).toHaveBeenLastCalledWith("team", 137.12345678901235);
  fireEvent.click(screen.getByText("Enter an exact raw rating for Team", { exact: true }));
  const exact = screen.getByLabelText("Exact raw rating for Team"); expect(exact).toHaveValue("250.12345678901235");
  fireEvent.change(exact, { target: { value: "301.9876543210987" } }); fireEvent.blur(exact);
  expect(state.change).toHaveBeenLastCalledWith("team", 301.9876543210987);
  expect(screen.queryByRole("button", { name: /save.*profile/i })).toBeNull();
});
it("shows an active trial and Reset; pending or unavailable output never retains old engine weights", () => {
  const state = { ...trial(), active: true, ratings: { team: 300.9876543210987 } };
  const view = render(<WhatIfWeights trial={state} request={{ status: "loading" }} supported/>);
  expect(screen.getByText("What-if, not saved", { exact: false })).toBeVisible();
  expect(screen.getAllByText("Engine normalised weight: Calculating…", { exact: true })).toHaveLength(2);
  const slider = screen.getByRole("slider", { name: "What-if Team" }); expect(slider).toHaveAttribute("max", "300.9876543210987"); expect(slider).toHaveValue("300.9876543210987");
  const unavailable = { ...preview, status: "unavailable" as const, reason: "All sibling ratings are zero.", trial_project_fingerprint: null, controls: controls.map(control => ({ ...control, local_weight: null, global_share: null })) };
  view.rerender(<WhatIfWeights trial={state} request={{ status: "ready", result: unavailable }} supported/>);
  expect(screen.getAllByText("Engine normalised weight: Unavailable", { exact: true })).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: "Reset" })); expect(state.reset).toHaveBeenCalledOnce();
});
it("explains other methods with an explicit read-only MAVT view action", () => {
  const explore = vi.fn(); render(<WhatIfWeights trial={trial()} request={{ status: "loading" }} supported={false} onExplore={explore}/>);
  expect(screen.queryByRole("slider")).toBeNull(); fireEvent.click(screen.getByRole("button", { name: "Explore MAVT weights" })); expect(explore).toHaveBeenCalledOnce();
});

it("hides only the open-question column and its disclosures while retaining every other engine row", () => {
  const summary = structuredClone(summaryJSON) as unknown as ScreeningSummary;
  const source = projectJSON as unknown as Project, before = structuredClone(summary);
  render(<ScreeningSummaryView summary={summary} project={source} hideOpenQuestions/>);
  expect(screen.getAllByRole("columnheader").map(node => node.textContent)).toEqual([
    "Rank", "Alternative", "Overall value", "Class (margin)", "Requirements", "Largest contributions", "Closest change",
  ]);
  expect(screen.getAllByRole("rowheader").map(node => node.textContent)).toEqual(summary.rows.map(row => row.name));
  fireEvent.click(screen.getByRole("button", { name: "About: Preference values under this profile; not probabilities or predictions." }));
  expect(screen.getByRole("note").textContent).not.toContain(`${String(summary.project_open_questions)} open question(s)`);
  expect(summary).toEqual(before);
});
