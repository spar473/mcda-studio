import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { FeasibilityResult, MethodComparison, ScreeningSummary } from "../../src/api/types";
import { ComparePanel } from "../../src/components/ComparePanel";
import { FeasibilityView } from "../../src/components/results/FeasibilityView";
import { WeightTrialGate } from "../../src/components/WeightTrialGate";
import { saveDownload } from "../../src/components/results/downloads";
import { context, project } from "../results/fixture";
vi.mock("../../src/components/results/downloads", () => ({ saveDownload: vi.fn() }));
const feasibility: FeasibilityResult = { label: "feasibility: each requirement is tested on its own measurement; no score offsets a failure", project_id: project.id, project_fingerprint: "fp", requirements: [], diagnostics: [], alternatives: [], summary: [] };
const comparison: MethodComparison = { project_id: project.id, project_fingerprint: "fp", configuration: context.configuration, methods: [], alternative_order: project.alternatives.map(item => item.id),
  alternative_names: Object.fromEntries(project.alternatives.map(item => [item.id, item.name])), columns: [], agreement: { leaders_agree: null, leader_groups: [], classes: [], reasons: [], context: "Agreement between methods that share inputs is not independent validation." } };
const summary: ScreeningSummary = { project_fingerprint: "fp", configuration: context.configuration, weight_profile_id: context.resolvedProfileId, scenario_id: null,
  status: "unavailable", reason: "Unavailable fixture", issue_codes: [], label: "", fragility_definition: "", rows: [], columns: [], project_open_questions: null, excluded_criteria: [], limitations: [] };
const tick = async () => act(async () => { await vi.advanceTimersByTimeAsync(200); });
beforeEach(() => { vi.useFakeTimers(); vi.spyOn(api, "compareMethods").mockResolvedValue(comparison); vi.spyOn(api, "screeningSummary").mockResolvedValue(summary); });
afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks(); vi.useRealTimers(); });

it.each(["comparison", "feasibility"] as const)("blocks %s downloads and drops an old completion after Reset, while retaining the original request", async kind => {
  let finish: (file: { blob: Blob; filename: string }) => void = () => undefined;
  const exporter = kind === "comparison" ? vi.spyOn(api, "exportComparison") : vi.spyOn(api, "exportFeasibility");
  exporter.mockImplementationOnce(() => new Promise<{ blob: Blob; filename: string }>(resolve => { finish = resolve; }));
  const element = (active: boolean, generation: number) => <WeightTrialGate value={{ active, generation, reset: vi.fn() }}>
    {kind === "comparison" ? <ComparePanel project={project} context={context}/> : <FeasibilityView result={feasibility} project={project}/>}
  </WeightTrialGate>;
  const view = render(element(false, 0)); await tick();
  const name = `Download ${kind} CSV`; fireEvent.click(screen.getByRole("button", { name }));
  const before = structuredClone(project); view.rerender(element(true, 0)); expect(screen.getByRole("button", { name })).toBeDisabled();
  view.rerender(element(false, 1)); await act(async () => { finish({ blob: new Blob(["obsolete"]), filename: "obsolete.csv" }); await Promise.resolve(); });
  expect(saveDownload).not.toHaveBeenCalled();
  exporter.mockResolvedValue({ blob: new Blob(["saved"]), filename: "saved.csv" }); fireEvent.click(screen.getByRole("button", { name })); await tick();
  expect(saveDownload).toHaveBeenCalledOnce(); expect(saveDownload).toHaveBeenCalledWith(expect.any(Blob), "saved.csv");
  const expected = { project, expected_project_fingerprint: "fp", format: "csv", ...(kind === "comparison" ? { configuration: context.configuration } : {}) };
  expect(exporter).toHaveBeenLastCalledWith(expected, expect.any(AbortSignal)); expect(project).toEqual(before);
});
