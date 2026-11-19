import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAnalysisRequest } from "../../src/state/useAnalysisRequest";

type Load = (signal: AbortSignal) => Promise<string>;
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
async function start() { await act(async () => { await vi.advanceTimersByTimeAsync(121); }); }
function hook(key: string, load: Load) {
  return renderHook(({ k, l }) => useAnalysisRequest(k, true, l), { initialProps: { k: key, l: load } });
}
function retryOf(request: ReturnType<typeof useAnalysisRequest<string>>) {
  if (request.status !== "error") throw Error(`expected an error, got ${request.status}`);
  return request.retry;
}
beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

describe("retrying a failed analysis request", () => {
  it("re-sends the same request with a fresh signal and shows loading meanwhile", async () => {
    const load = vi.fn<Load>().mockRejectedValueOnce(new Error("Network down")).mockResolvedValueOnce("fresh");
    const { result } = hook("A", load);
    await start(); expect(result.current).toMatchObject({ status: "error", message: "Network down" });
    act(() => { retryOf(result.current)(); });
    expect(result.current).toEqual({ status: "loading" });
    await start(); expect(result.current).toEqual({ status: "ready", result: "fresh" });
    expect(load).toHaveBeenCalledTimes(2);
    const [first, second] = load.mock.calls.map(([signal]) => signal);
    expect(second).not.toBe(first); expect(second?.aborted).toBe(false);
  });
  it("repeated clicks issue one request", async () => {
    const load = vi.fn<Load>().mockRejectedValueOnce(new Error("down")).mockResolvedValue("ok");
    const { result } = hook("A", load); await start();
    const retry = retryOf(result.current);
    act(() => { retry(); retry(); retry(); });
    await start(); expect(result.current).toEqual({ status: "ready", result: "ok" }); expect(load).toHaveBeenCalledTimes(2);
  });
  it("after the project changes, Retry requests the current context and never the obsolete one", async () => {
    const loadA = vi.fn<Load>().mockRejectedValue(new Error("A failed"));
    const loadB = vi.fn<Load>().mockRejectedValueOnce(new Error("B failed")).mockResolvedValueOnce("B");
    const { result, rerender } = hook("A", loadA); await start();
    rerender({ k: "B", l: loadB }); expect(result.current).toEqual({ status: "loading" });
    await start(); expect(result.current).toMatchObject({ status: "error", message: "B failed" });
    act(() => { retryOf(result.current)(); });
    await start(); expect(result.current).toEqual({ status: "ready", result: "B" });
    expect(loadA).toHaveBeenCalledTimes(1); expect(loadB).toHaveBeenCalledTimes(2);
  });
  it("a Retry captured before the context changed does nothing", async () => {
    const loadA = vi.fn<Load>().mockRejectedValue(new Error("A failed"));
    const loadB = vi.fn<Load>().mockResolvedValue("B");
    const { result, rerender } = hook("A", loadA); await start();
    const stale = retryOf(result.current);
    rerender({ k: "B", l: loadB }); await start(); expect(result.current).toEqual({ status: "ready", result: "B" });
    act(() => { stale(); }); await start();
    expect(result.current).toEqual({ status: "ready", result: "B" });
    expect(loadA).toHaveBeenCalledTimes(1); expect(loadB).toHaveBeenCalledTimes(1);
  });
  it("a late answer to a retried request cannot appear under a newer context", async () => {
    const failed = deferred<string>(), retried = deferred<string>(), next = deferred<string>();
    const loadA = vi.fn<Load>().mockReturnValueOnce(failed.promise).mockReturnValueOnce(retried.promise);
    const loadB = vi.fn<Load>().mockReturnValueOnce(next.promise);
    const { result, rerender } = hook("A", loadA); await start();
    await act(async () => { failed.reject(new Error("timeout")); await Promise.resolve(); });
    act(() => { retryOf(result.current)(); }); await start();
    rerender({ k: "B", l: loadB }); await start();
    expect(loadA.mock.calls[1]?.[0].aborted).toBe(true);
    await act(async () => { retried.resolve("late A"); await Promise.resolve(); });
    expect(result.current).toEqual({ status: "loading" });
    await act(async () => { next.resolve("B"); await Promise.resolve(); });
    expect(result.current).toEqual({ status: "ready", result: "B" });
  });
});
