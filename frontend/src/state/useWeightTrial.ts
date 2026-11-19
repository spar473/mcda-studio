import { useCallback, useState } from "react";
import type { ScreeningWhatIf } from "../api/types";

export type TrialControl = ScreeningWhatIf["controls"][number];
interface TrialState {
  sourceKey: string; generation: number; open: boolean;
  ratings: Record<string, number>; baseline: TrialControl[] | null;
}
const initial = (sourceKey: string, generation: number, open = false): TrialState => ({ sourceKey, generation, open, ratings: {}, baseline: null });

/** This owner lives beside editor tab state. No project, profile or dossier is copied here. */
export function useWeightTrial(sourceKey: string) {
  const [state, setState] = useState(() => initial(sourceKey, 0));
  if (state.sourceKey !== sourceKey) setState(initial(sourceKey, state.generation + 1, state.open));
  const current = state.sourceKey === sourceKey ? state : initial(sourceKey, state.generation + 1, state.open);
  const generation = current.generation;
  const valid = useCallback((value: TrialState) => value.sourceKey === sourceKey && value.generation === generation, [sourceKey, generation]);
  const setOpen = useCallback((open: boolean) => setState(previous => !valid(previous) ? previous : open ? { ...previous, open }
    : { ...previous, open: false, ratings: {}, generation: previous.generation + 1 }), [valid]);
  const reset = useCallback(() => setState(previous => valid(previous)
    ? { ...previous, ratings: {}, generation: previous.generation + 1 } : previous), [valid]);
  const change = useCallback((criterionId: string, rating: number) => setState(previous => {
    if (!valid(previous) || !Number.isFinite(rating) || rating < 0 || !previous.baseline?.some(control => control.criterion_id === criterionId)) return previous;
    return { ...previous, ratings: { ...previous.ratings, [criterionId]: rating } };
  }), [valid]);
  const acceptBaseline = useCallback((controls: TrialControl[]) => setState(previous => {
    if (!valid(previous) || previous.baseline !== null || Object.keys(previous.ratings).length) return previous;
    return { ...previous, baseline: controls };
  }), [valid]);
  return { ...current, active: Object.keys(current.ratings).length > 0, setOpen, reset, change, acceptBaseline };
}
export type WeightTrial = ReturnType<typeof useWeightTrial>;
