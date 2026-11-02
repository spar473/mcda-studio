import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { MavtResult, ValidationReport } from "../../src/api/types";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import { useEvaluation } from "../../src/state/useEvaluation";
import { projectWith } from "../fixtures";

const project = projectWith([], { analysis: { method: "mavt", scenario_id: "saved", weight_profile_id: null, parameters: {} } });
const context = (fingerprint: string) => resolveContext(project, fingerprint, BASE_SELECTION);
function response(fp: string): MavtResult {
  return { method: "mavt", schema_version: 1, project_id: "p1", project_fingerprint: fp,
    configuration: context(fp).configuration, weight_profile_id: null, scenario_id: null,
    ranking: [], diagnostics: [], assumptions: [], leaf_order: [], local_weights: {}, global_weights: {},
    resolved_domains: {}, weight_basis: "swing", alternatives: [], dominance: [] };
}
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
const valid: ValidationReport = { issues: [] };
async function start() { await act(async () => { await vi.advanceTimersByTimeAsync(121); }); }
beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

describe("revision/configuration-safe evaluation", () => {
  it("sends explicit base configuration and an AbortSignal", async () => {
    const spy = vi.spyOn(api, "evaluate").mockResolvedValue(response("one"));
    const ctx = context("one"); const { result } = renderHook(() => useEvaluation(project, valid, ctx));
    await start(); expect(result.current.status).toBe("ready");
    expect(spy).toHaveBeenCalledWith(project, expect.objectContaining({ scenario_id: null }), expect.any(AbortSignal));
  });
  it("rejects a delayed old success even when the transport ignores abort", async () => {
    const old = deferred<MavtResult>(); const fresh = deferred<MavtResult>();
    const spy = vi.spyOn(api, "evaluate").mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise);
    const { result, rerender } = renderHook(({ ctx }) => useEvaluation(project, valid, ctx), { initialProps: { ctx: context("old") } });
    await start(); rerender({ ctx: context("new") }); await start();
    expect(spy.mock.calls[0]?.[2]?.aborted).toBe(true);
    await act(async () => { fresh.resolve(response("new")); await Promise.resolve(); });
    await act(async () => { old.resolve(response("old")); await Promise.resolve(); });
    expect(result.current).toMatchObject({ status: "ready", result: { project_fingerprint: "new" } });
  });
  it("hides a completed old result immediately on a new revision", async () => {
    vi.spyOn(api, "evaluate").mockResolvedValue(response("old"));
    const { result, rerender } = renderHook(({ ctx }) => useEvaluation(project, valid, ctx), { initialProps: { ctx: context("old") } });
    await start(); expect(result.current.status).toBe("ready");
    rerender({ ctx: context("new") }); expect(result.current).toEqual({ status: "loading" });
  });
  it("rejects stale errors and A-B-A request races", async () => {
    const a1 = deferred<MavtResult>(); const b = deferred<MavtResult>(); const a2 = deferred<MavtResult>();
    vi.spyOn(api, "evaluate").mockReturnValueOnce(a1.promise).mockReturnValueOnce(b.promise).mockReturnValueOnce(a2.promise);
    const { result, rerender } = renderHook(({ ctx }) => useEvaluation(project, valid, ctx), { initialProps: { ctx: context("A") } });
    await start(); rerender({ ctx: context("B") }); await start(); rerender({ ctx: context("A") }); await start();
    await act(async () => { a1.resolve(response("A")); b.reject(new Error("old failure")); await Promise.resolve(); });
    expect(result.current.status).toBe("loading");
    await act(async () => { a2.resolve(response("A")); await Promise.resolve(); }); expect(result.current.status).toBe("ready");
  });
  it.each(["project_fingerprint", "scenario_id", "weight_profile_id"] as const)("rejects mismatched %s provenance", async (field) => {
    vi.spyOn(api, "evaluate").mockResolvedValue({ ...response("one"), [field]: "wrong" });
    const ctx = context("one"); const { result } = renderHook(() => useEvaluation(project, valid, ctx));
    await start(); expect(result.current.status).toBe("error");
    if (result.current.status === "error") expect(result.current.message).toContain("does not match");
  });
  it("invalidates results on nested parameter changes, and blocks incomplete models", async () => {
    const spy = vi.spyOn(api, "evaluate").mockResolvedValue(response("one"));
    const { result, rerender } = renderHook(({ ctx, report }) => useEvaluation(project, report, ctx),
      { initialProps: { ctx: context("one"), report: valid } });
    await start(); expect(result.current.status).toBe("ready");
    const ctx = context("one"); ctx.configuration.parameters = { nested: { changed: 1 } };
    rerender({ ctx, report: valid }); expect(result.current.status).toBe("loading");
    rerender({ ctx, report: { issues: [{ severity: "error", code: "MISSING", path: "", message: "missing" }] } });
    await start(); expect(result.current).toMatchObject({ status: "blocked" }); expect(spy).toHaveBeenCalledTimes(1);
  });
});
