import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { AnalysisRecord, ScreeningSummary, ScreeningWhatIf } from "../../src/api/types";
import { ResultsPanel } from "../../src/components/ResultsPanel";
import { saveDownload } from "../../src/components/results/downloads";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import { project as source, record as fixture } from "../results/fixture";
vi.mock("../../src/components/results/downloads", () => ({ saveDownload: vi.fn() }));
// Opaque UI protocol readings; the Python saved-profile tests own the numerical guarantee.
const project = { ...structuredClone(source), criteria: source.criteria.filter(node => node.id !== "g").map(node => ({ ...node, parent_id: null })) };
const context = resolveContext(project, "fp", BASE_SELECTION);
function reading(trial: boolean): ScreeningWhatIf {
  const record: AnalysisRecord = structuredClone(fixture), fp = trial ? "trial-fp" : "fp";
  record.result.project_fingerprint = fp; record.record_digest = (trial ? "d" : "a").repeat(64);
  if (trial) {
    record.result.local_weights = { cost: 0, quality: 1 }; record.result.global_weights = { cost: 0, quality: 1 };
    record.result.ranking = [{ alternative_id: "b", name: "Same", rank: 1, value: .8 }, { alternative_id: "a", name: "Same", rank: 2, value: .6 }, { alternative_id: "c", name: source.alternatives[0]?.name ?? "C", rank: 3, value: .2 }];
    for (const alternative of record.result.alternatives) {
      const row = record.result.ranking.find(item => item.alternative_id === alternative.alternative_id); if (!row) throw Error("Reading missing");
      alternative.rank = row.rank; alternative.overall_value = row.value; record.contribution_totals[row.alternative_id] = row.value;
      alternative.weighted_contributions = { cost: 0, quality: row.value };
    }
  }
  const summary: ScreeningSummary = { project_fingerprint: fp, configuration: context.configuration, weight_profile_id: "first", scenario_id: null, status: "available", reason: "", issue_codes: [],
    label: "Screening preferences", fragility_definition: "One weight at a time", rows: record.result.ranking.map(row => ({ ...row, class_id: null, class_name: null, margin: null, nearest_boundary_class_id: null,
      requirements: null, drivers: [], fragility: null, open_questions: 5 })), columns: [{ column: "open_questions", available: true, reason: "" }], project_open_questions: 1, excluded_criteria: [], limitations: [] };
  return { project_fingerprint: "fp", configuration: context.configuration, weight_profile_id: "first", scenario_id: null, status: "available", reason: "", ratings: trial ? { cost: 0 } : {},
    controls: [{ criterion_id: "cost", name: "Cost", raw_rating: trial ? 0 : 100, local_weight: trial ? 0 : .5, global_share: trial ? 0 : .5, slider_min: 0, slider_max: 100, step: "any" },
      { criterion_id: "quality", name: "Quality", raw_rating: 100, local_weight: trial ? 1 : .5, global_share: trial ? 1 : .5, slider_min: 0, slider_max: 100, step: "any" }],
    trial_project_fingerprint: fp, summary, record };
}
const tick = async () => act(async () => { await vi.advanceTimersByTimeAsync(200); });
async function activate() {
  fireEvent.click(screen.getByText("What-if weights", { exact: true })); await tick();
  fireEvent.change(screen.getByRole("slider", { name: "What-if Cost" }), { target: { value: "0" } }); await tick();
}
beforeEach(() => {
  vi.useFakeTimers(); vi.spyOn(api, "analysisRecord").mockResolvedValue(structuredClone(fixture));
  vi.spyOn(api, "screeningSummary").mockResolvedValue(reading(false).summary as ScreeningSummary);
  vi.spyOn(api, "screeningWhatIf").mockImplementation((_project, _configuration, ratings) => Promise.resolve(reading(Object.keys(ratings).length > 0)));
});
afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks(); vi.useRealTimers(); });

it("reranks only the summary and ranking chart, hides counts and blocks exports, then Reset restores saved readings without edits", async () => {
  const edit = vi.spyOn(api, "edit"), save = vi.spyOn(api, "saveProject"), before = structuredClone(project);
  render(<ResultsPanel project={project} context={context} validation={{ issues: [] }}/>); await tick();
  const saved = screen.getByRole("table", { name: "Ranking" }).textContent;
  const contributionValues = () => [...screen.getByRole("group", { name: "Weighted leaf contributions" }).querySelectorAll("rect[data-contribution]")].map(node => node.getAttribute("data-contribution"));
  const contributions = contributionValues();
  await activate();
  const summary = screen.getByRole("table", { name: "Screening summary" });
  expect(within(summary).getAllByRole("row").slice(1).map(row => row.querySelectorAll("td")[1]?.textContent)).toEqual(["0.8000", "0.6000", "0.2000"]);
  expect(within(summary).queryByRole("columnheader", { name: "Open questions" })).toBeNull(); expect(screen.getByText("Open-question counts reflect the saved weights", { exact: true })).toBeVisible();
  const chart = screen.getByRole("group", { name: "Overall MAVT values" });
  expect([...chart.querySelectorAll("g[data-alternative-id]")].map(node => node.getAttribute("data-alternative-id"))).toEqual(["b", "a", "c"]);
  expect(screen.getByRole("table", { name: "Ranking" }).textContent).toBe(saved);
  expect(contributionValues()).toEqual(contributions);
  for (const name of ["Download analysis JSON", "Download CSV", "Download ranking SVG", "Download contributions SVG"]) expect(screen.getByRole("button", { name })).toBeDisabled();
  expect(screen.queryByRole("checkbox", { name: "Compare profiles" })).toBeNull(); expect(screen.getByText("Compare profiles: Reset what-if to use this", { exact: true })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Reset" })); await tick();
  expect(screen.getByRole("columnheader", { name: "Open questions" })).toBeVisible(); expect(screen.getByRole("button", { name: "Download ranking SVG" })).toBeEnabled();
  expect(api.analysisRecord).toHaveBeenCalledTimes(1); expect(edit).not.toHaveBeenCalled(); expect(save).not.toHaveBeenCalled(); expect(project).toEqual(before);
});
it("permanently suppresses a saved export started before a trial even when it resolves after Reset, then uses the original export body", async () => {
  let finish: (file: { blob: Blob; filename: string }) => void = () => undefined;
  const exported = vi.spyOn(api, "exportAnalysis").mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  render(<ResultsPanel project={project} context={context} validation={{ issues: [] }}/>); await tick();
  fireEvent.click(screen.getByRole("button", { name: "Download analysis JSON" })); await activate();
  fireEvent.click(screen.getByRole("button", { name: "Reset" })); await tick();
  await act(async () => { finish({ blob: new Blob(["obsolete"]), filename: "obsolete.json" }); await Promise.resolve(); });
  expect(saveDownload).not.toHaveBeenCalled();
  exported.mockResolvedValue({ blob: new Blob(["saved"]), filename: "saved.json" });
  fireEvent.click(screen.getByRole("button", { name: "Download analysis JSON" })); await tick();
  expect(saveDownload).toHaveBeenCalledOnce(); expect(saveDownload).toHaveBeenCalledWith(expect.any(Blob), "saved.json");
  expect(exported).toHaveBeenLastCalledWith({ project, configuration: context.configuration, expected_project_fingerprint: "fp", expected_record_digest: fixture.record_digest,
    format: "json", table: "ranking", presentation: { sort: "rank", precision: "4", hidden_alternative_ids: [], hidden_criterion_ids: [] } }, expect.any(AbortSignal));
});
