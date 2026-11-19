import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { ScreeningSummary, ScreeningWhatIf } from "../../src/api/types";
import { useScreeningWhatIf } from "../../src/state/useScreeningWhatIf";
import { context, project, record } from "../results/fixture";

// Opaque protocol fixtures exercise identity and cancellation. Python's independent
// saved-profile oracles, rather than these fixtures, guarantee the trial numbers.
function reading(ratings: Record<string, number> = {}, fingerprint = "trial", ctx = context): ScreeningWhatIf {
  const trialRecord = structuredClone(record);
  trialRecord.result.project_fingerprint = fingerprint;
  trialRecord.result.configuration = ctx.configuration;
  trialRecord.result.weight_profile_id = ctx.resolvedProfileId;
  trialRecord.result.scenario_id = ctx.scenarioId;
  const summary: ScreeningSummary = {
    project_fingerprint: fingerprint, configuration: ctx.configuration, weight_profile_id: ctx.resolvedProfileId, scenario_id: ctx.scenarioId,
    status: "available", reason: "", issue_codes: [], label: "Screening preferences", fragility_definition: "One weight at a time",
    rows: trialRecord.result.ranking.map(row => ({ ...row, class_id: null, class_name: null, margin: null, nearest_boundary_class_id: null,
      requirements: null, drivers: [], fragility: null, open_questions: null })),
    columns: [], project_open_questions: null, excluded_criteria: [], limitations: [],
  };
  return { project_fingerprint: ctx.fingerprint, configuration: ctx.configuration, weight_profile_id: ctx.resolvedProfileId,
    scenario_id: ctx.scenarioId, status: "available", reason: "", ratings, controls: [], trial_project_fingerprint: fingerprint, summary, record: trialRecord };
}
const tick = async (duration = 155) => act(async () => { await vi.advanceTimersByTimeAsync(duration); });
beforeEach(() => { vi.useFakeTimers(); vi.spyOn(api, "screeningWhatIf").mockImplementation((_project, cfg, ratings) => Promise.resolve(reading(ratings, "trial", { ...context, configuration: cfg }))); });
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });
const useHarness = (props: { ratings: Record<string, number>; generation: number; enabled: boolean; ctx: typeof context }) =>
  useScreeningWhatIf(project, props.ctx, props.ratings, null, props.enabled, props.generation);
const initial = () => ({ ratings: {} as Record<string, number>, generation: 0, enabled: true, ctx: context });

it("debounces 150ms, sends original input and exact ratings, and never edits or saves", async () => {
  const edit = vi.spyOn(api, "edit"), save = vi.spyOn(api, "saveProject"), before = structuredClone(project);
  const { result, rerender } = renderHook(useHarness, { initialProps: initial() });
  await tick(149); expect(api.screeningWhatIf).not.toHaveBeenCalled(); await tick(1); expect(result.current.status).toBe("ready");
  rerender({ ...initial(), ratings: { cost: 137.12345678901235 } }); expect(result.current.status).toBe("loading"); await tick(149); expect(api.screeningWhatIf).toHaveBeenCalledTimes(1);
  await tick(1); expect(api.screeningWhatIf).toHaveBeenLastCalledWith(project, context.configuration, { cost: 137.12345678901235 }, expect.any(AbortSignal));
  expect(edit).not.toHaveBeenCalled(); expect(save).not.toHaveBeenCalled(); expect(project).toEqual(before);
});
it.each(["success", "error"])("a newer rating hides the old reading immediately and rejects its late %s", async outcome => {
  let resolveOld: (value: ScreeningWhatIf) => void = () => undefined, rejectOld: (error: Error) => void = () => undefined;
  vi.mocked(api.screeningWhatIf).mockImplementationOnce(() => new Promise((resolve, reject) => { resolveOld = resolve; rejectOld = reject; }));
  const { result, rerender } = renderHook(useHarness, { initialProps: initial() }); await tick();
  const ratings = { cost: 55.12345678901235 }; rerender({ ...initial(), ratings }); expect(result.current.status).toBe("loading"); await tick();
  expect(result.current).toMatchObject({ status: "ready", result: { ratings } });
  await act(async () => { if (outcome === "success") resolveOld(reading({}, "old")); else rejectOld(Error("Abandoned rating failed")); await Promise.resolve(); });
  expect(result.current).toMatchObject({ status: "ready", result: { ratings, trial_project_fingerprint: "trial" } });
});
it.each(["success", "error"])("Reset generation prevents a pending trial %s from reappearing", async outcome => {
  let resolveOld: (value: ScreeningWhatIf) => void = () => undefined, rejectOld: (error: Error) => void = () => undefined;
  const ratings: Record<string, number> = { cost: 77 };
  vi.mocked(api.screeningWhatIf).mockImplementationOnce(() => new Promise((resolve, reject) => { resolveOld = resolve; rejectOld = reject; }));
  const { result, rerender } = renderHook(useHarness, { initialProps: { ...initial(), ratings } }); await tick();
  rerender({ ...initial(), generation: 1 }); expect(result.current.status).toBe("loading"); await tick();
  await act(async () => { if (outcome === "success") resolveOld(reading(ratings, "reset-old")); else rejectOld(Error("Reset trial failed")); await Promise.resolve(); });
  expect(result.current).toMatchObject({ status: "ready", result: { ratings: {}, trial_project_fingerprint: "trial" } });
});
const contextCases = ["revision", "profile", "scenario"] as const;
function changedContext(kind: typeof contextCases[number]) {
  return kind === "revision" ? { ...context, fingerprint: "new-revision" }
    : kind === "profile" ? { ...context, profileId: "second", resolvedProfileId: "second", configuration: { ...context.configuration, weight_profile_id: "second" } }
      : { ...context, scenarioId: "alternate", configuration: { ...context.configuration, scenario_id: "alternate" } };
}
it.each(contextCases)("a ready reading hides immediately on a %s change even with the same generation", async kind => {
  const { result, rerender } = renderHook(useHarness, { initialProps: initial() }); await tick(); expect(result.current.status).toBe("ready");
  const ctx = changedContext(kind); vi.mocked(api.screeningWhatIf).mockResolvedValue(reading({}, "new-trial", ctx));
  rerender({ ...initial(), ctx }); expect(result.current.status).toBe("loading"); await tick();
  expect(result.current).toMatchObject({ status: "ready", result: { project_fingerprint: ctx.fingerprint, weight_profile_id: ctx.resolvedProfileId, scenario_id: ctx.scenarioId, trial_project_fingerprint: "new-trial" } });
});
it.each(contextCases.flatMap(kind => ["success", "error"].map(outcome => ({ kind, outcome }))))("a $kind change rejects the previous $outcome", async ({ kind, outcome }) => {
  let resolveOld: (value: ScreeningWhatIf) => void = () => undefined, rejectOld: (error: Error) => void = () => undefined;
  vi.mocked(api.screeningWhatIf).mockImplementationOnce(() => new Promise((resolve, reject) => { resolveOld = resolve; rejectOld = reject; }));
  const { result, rerender } = renderHook(useHarness, { initialProps: initial() }); await tick();
  const ctx = changedContext(kind); vi.mocked(api.screeningWhatIf).mockResolvedValue(reading({}, "new-trial", ctx)); rerender({ ...initial(), ctx }); await tick();
  await act(async () => { if (outcome === "success") resolveOld(reading({}, "old-source")); else rejectOld(Error("Old source failed")); await Promise.resolve(); });
  expect(result.current).toMatchObject({ status: "ready", result: { project_fingerprint: ctx.fingerprint, weight_profile_id: ctx.resolvedProfileId, scenario_id: ctx.scenarioId, trial_project_fingerprint: "new-trial" } });
});

it("rejects an incorrect echoed rating or nested trial fingerprint and never requests while closed", async () => {
  const wrong = reading({ cost: 3 }); vi.mocked(api.screeningWhatIf).mockResolvedValue(wrong);
  const { result, rerender } = renderHook(useHarness, { initialProps: initial() }); await tick(); expect(result.current.status).toBe("error");
  const nested = reading(); if (!nested.summary) throw Error("Fixture missing"); nested.summary.project_fingerprint = "another-trial";
  vi.mocked(api.screeningWhatIf).mockResolvedValue(nested); rerender({ ...initial(), generation: 1 }); await tick(); expect(result.current.status).toBe("error");
  vi.mocked(api.screeningWhatIf).mockClear(); rerender({ ...initial(), generation: 2, enabled: false }); await tick();
  expect(result.current.status).toBe("loading"); expect(api.screeningWhatIf).not.toHaveBeenCalled();
});

it("criterion inspection keeps the same reading and does not request another numerical evaluation", async () => {
  const { result, rerender } = renderHook(useHarness, { initialProps: initial() }); await tick();
  expect(result.current.status).toBe("ready");
  rerender({ ...initial(), ctx: { ...context, criterionId: "cost" } }); await tick();
  expect(result.current.status).toBe("ready"); expect(api.screeningWhatIf).toHaveBeenCalledTimes(1);
});
