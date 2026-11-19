import { createContext, useCallback, useContext, useLayoutEffect, useRef } from "react";

/** UI blocking only. No temporary project or numerical reading crosses this context. */
export const WeightTrialGate = createContext<{ active: boolean; generation: number; reset: () => void }>({ active: false, generation: 0, reset: () => undefined });
export const useWeightTrialGate = () => useContext(WeightTrialGate);
export const RESET_TRIAL = "Reset what-if to use this";
export const RESET_DOWNLOAD = "Reset what-if to download the saved model";

/** Existing export bodies stay unchanged. A trial blocks downloads and Reset/source
 * changes permanently invalidate an earlier in-flight request, even after re-enabling. */
export function useTrialDownloadGuard(override?: { active: boolean; generation: number }) {
  const gate = useWeightTrialGate();
  const { active, generation } = override ?? gate;
  const live = useRef({ active, generation, alive: true });
  useLayoutEffect(() => {
    live.current = { active, generation, alive: true };
    return () => { live.current.alive = false; };
  }, [active, generation]);
  const ticket = useCallback(() => !live.current.alive || live.current.active ? null : live.current.generation, []);
  const permits = useCallback((token: number | null) => token !== null && live.current.alive && !live.current.active && live.current.generation === token, []);
  return { disabled: active, ticket, permits };
}
