import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

export type AnalysisRequest<T> =
  | { status: "loading" }
  | { status: "ready"; result: T }
  | { status: "error"; message: string; retry: () => void };

/** Key-gated results plus cancellation: an obsolete success OR failure can never become current.
 * After a failure, `retry` re-issues the same key; it never touches the project or its history. */
export function useAnalysisRequest<T>(key: string, enabled: boolean,
  load: (signal: AbortSignal) => Promise<T>): AnalysisRequest<T> {
  const [done, setDone] = useState<{ key: string; result: T } | { key: string; message: string } | null>(null);
  const [retries, setRetries] = useState({ key, count: 0 });
  const attempt = retries.key === key ? retries.count : 0;
  useEffect(() => {
    if (!enabled) return;
    let current = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void load(controller.signal).then((result) => {
        if (current) setDone({ key, result });
      }).catch((error: unknown) => {
        if (current) setDone({ key, message: error instanceof Error ? error.message : String(error) });
      });
    }, 120);
    return () => { current = false; controller.abort(); window.clearTimeout(timer); };
  }, [key, enabled, load, attempt]);
  const liveKey = useRef(key);
  useLayoutEffect(() => { liveKey.current = key; }, [key]);
  // Only the failure currently shown can be retried: a retry captured under an older key does nothing.
  const retry = useCallback(() => {
    if (liveKey.current !== key) return;
    setDone(null);
    setRetries((r) => ({ key, count: (r.key === key ? r.count : 0) + 1 }));
  }, [key]);
  // Hide even a previously ready result immediately on revision/configuration change.
  if (!enabled || done?.key !== key) return { status: "loading" };
  return "result" in done ? { status: "ready", result: done.result } : { status: "error", message: done.message, retry };
}
