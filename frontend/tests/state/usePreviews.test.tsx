import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { ValueFunctionCandidate, ValueFunctionPreview, WeightPreview } from "../../src/api/types";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import { previewContext, providedFieldsMatch, useValueFunctionPreview, useWeightPreview } from "../../src/state/usePreviews";
import { node, projectWith, ratioScale } from "../fixtures";

const project = projectWith([node("cost")], { analysis: { method: "mavt", scenario_id: null, weight_profile_id: null, parameters: {} },
  weight_profiles: [{ id: "first", name: "First", method: "swing", judgements: {} }, { id: "second", name: "Second", method: "swing", judgements: {} }],
  scenarios: [{ id: "s", name: "S", weight_profile_id: "second", value_function_overrides: {} }] });
const ctx = resolveContext(project, "snapshot", { ...BASE_SELECTION, criterionId: "cost" });
const provenance = { project_fingerprint: "snapshot", configuration: ctx.configuration, weight_profile_id: "first", scenario_id: null };
const weight: WeightPreview = { ...provenance, swing_ranges: {}, weights_ready: false, local_weights: {}, global_weights: {}, path_shares: {}, sibling_rating_totals: {},
  diagnostics: [{ severity: "error", code: "MISSING_JUDGEMENT", message: "missing", path: "" }], weight_basis: "swing" };
function curve(candidate: ValueFunctionCandidate | null = null): ValueFunctionPreview {
  return { ...provenance, criterion_id: "cost", candidate, candidate_fingerprint: "candidate",
    effective_scale: ratioScale, effective_value_function: null, resolved_domain: null, curve_ready: false,
    readiness: "incomplete", measurement_readiness: "incomplete", measurements_complete: false, samples: [], markers: [], diagnostics: [] } as ValueFunctionPreview;
}
function deferred<T>() { let resolve!: (v: T) => void; const promise = new Promise<T>((yes) => { resolve = yes; }); return { promise, resolve }; }
async function start() { await act(async () => { await vi.advanceTimersByTimeAsync(121); }); }
beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

describe("read-only engine preview requests", () => {
  it("requests the MAVT editors' previews for mavt while PROMETHEE II is viewed", async () => {
    const viewed = resolveContext(project, "snapshot", { ...BASE_SELECTION, method: "promethee2", scenarioId: "s" });
    const mavt = { ...viewed.configuration, method: "mavt", parameters: {} };
    expect(previewContext(viewed).configuration).toEqual(mavt);
    for (const method of ["mavt", "mavt_sorting", "smaa2"]) {
      const same = resolveContext(project, "snapshot", { ...BASE_SELECTION, method });
      expect(previewContext(same)).toBe(same);
    }
    const spy = vi.spyOn(api, "previewWeights").mockResolvedValue({ ...weight, configuration: mavt, scenario_id: "s", weight_profile_id: "second" });
    const { result } = renderHook(() => useWeightPreview(project, viewed)); await start();
    expect(spy).toHaveBeenCalledWith(project, mavt, expect.any(AbortSignal));
    expect(result.current).toMatchObject({ status: "ready", result: { scenario_id: "s" } });
  });
  it("previews missing weights without using or fabricating a full evaluation", async () => {
    const spy = vi.spyOn(api, "previewWeights").mockResolvedValue(weight);
    const evaluate = vi.spyOn(api, "evaluate"); const edit = vi.spyOn(api, "edit");
    const before = structuredClone(project);
    const { result } = renderHook(() => useWeightPreview(project, ctx)); await start();
    expect(result.current).toMatchObject({ status: "ready", result: { weights_ready: false, local_weights: {} } });
    expect(spy).toHaveBeenCalledWith(project, ctx.configuration, expect.any(AbortSignal));
    expect(evaluate).not.toHaveBeenCalled(); expect(edit).not.toHaveBeenCalled(); expect(project).toEqual(before);
  });
  it("rejects an old profile/scenario response with the same project fingerprint", async () => {
    const old = deferred<WeightPreview>(); const fresh = deferred<WeightPreview>();
    const spy = vi.spyOn(api, "previewWeights").mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise);
    const next = resolveContext(project, "snapshot", { ...BASE_SELECTION, scenarioId: "s", profileId: "second" });
    const { result, rerender } = renderHook(({ context }) => useWeightPreview(project, context), { initialProps: { context: ctx } });
    await start(); rerender({ context: next }); await start();
    await act(async () => { fresh.resolve({ ...weight, configuration: next.configuration, scenario_id: "s", weight_profile_id: "second" }); await Promise.resolve(); });
    await act(async () => { old.resolve(weight); await Promise.resolve(); });
    expect(spy.mock.calls[0]?.[2]?.aborted).toBe(true);
    expect(result.current).toMatchObject({ status: "ready", result: { scenario_id: "s", weight_profile_id: "second" } });
  });
  it("rejects a weight response resolved to another profile under automatic resolution", async () => {
    // The configuration, fingerprint and scenario all match: only the profile the engine actually
    // resolved differs. Automatic resolution is exactly where that can happen, so the resolved
    // profile has to be checked on its own and not inferred from the configuration.
    expect(ctx.configuration.weight_profile_id).toBeNull();
    expect(ctx.resolvedProfileId).toBe("first");
    vi.spyOn(api, "previewWeights").mockResolvedValue({ ...weight, weight_profile_id: "second" });
    const { result } = renderHook(() => useWeightPreview(project, ctx)); await start();
    expect(result.current.status).toBe("error");
    if (result.current.status === "error") expect(result.current.message).toContain("does not match");
  });
  it("pending candidates have independent identities and never edit the project", async () => {
    const a = deferred<ValueFunctionPreview>(); const b = deferred<ValueFunctionPreview>();
    const spy = vi.spyOn(api, "previewValueFunction").mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise);
    const edit = vi.spyOn(api, "edit"); const before = structuredClone(project);
    const first: ValueFunctionCandidate = { scale: { type: "ratio", anchor_mode: "fixed", upper: 10 } };
    const second: ValueFunctionCandidate = { scale: { type: "ratio", anchor_mode: "fixed", upper: 20 } };
    const { result, rerender } = renderHook(({ candidate }) => useValueFunctionPreview(project, ctx, candidate), { initialProps: { candidate: first } });
    await start(); rerender({ candidate: second }); await start();
    await act(async () => { b.resolve(curve({ scale: { ...ratioScale, upper: 20 }, value_function: null })); await Promise.resolve(); });
    await act(async () => { a.resolve(curve(first)); await Promise.resolve(); });
    expect(result.current.status).toBe("ready");
    expect(spy.mock.calls[0]?.[1]?.aborted).toBe(true); expect(edit).not.toHaveBeenCalled(); expect(project).toEqual(before);
  });
  it.each(["criterion", "candidate", "revision", "configuration"])("rejects mismatched %s preview provenance", async (field) => {
    const response = curve();
    if (field === "criterion") response.criterion_id = "other";
    if (field === "candidate") response.candidate = { scale: ratioScale, value_function: null };
    if (field === "revision") response.project_fingerprint = "old";
    if (field === "configuration") response.configuration = { ...ctx.configuration, parameters: { changed: true } };
    vi.spyOn(api, "previewValueFunction").mockResolvedValue(response);
    const { result } = renderHook(() => useValueFunctionPreview(project, ctx)); await start();
    expect(result.current.status).toBe("error");
  });
  it("does not start a value preview without a selected criterion", async () => {
    const spy = vi.spyOn(api, "previewValueFunction"); const none = { ...ctx, criterionId: null };
    renderHook(() => useValueFunctionPreview(project, none)); await start(); expect(spy).not.toHaveBeenCalled();
  });
  it("compares only provided defaults while detecting changed values and array order", () => {
    expect(providedFieldsMatch({ scale: { upper: 10 } }, { scale: ratioScale })).toBe(true);
    expect(providedFieldsMatch({ scale: { upper: 20 } }, { scale: ratioScale })).toBe(false);
    expect(providedFieldsMatch({ scale: null }, { scale: ratioScale })).toBe(false);
    expect(providedFieldsMatch([1,2], [2,1])).toBe(false);
    expect(providedFieldsMatch([1], [1,2])).toBe(false);
  });
});
