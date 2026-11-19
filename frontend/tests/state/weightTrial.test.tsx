import { act, renderHook } from "@testing-library/react";
import { expect, it } from "vitest";
import { useWeightTrial, type TrialControl } from "../../src/state/useWeightTrial";
const controls: TrialControl[] = [
  { criterion_id: "team", name: "Team", raw_rating: 137.12345678901235, local_weight: .6, global_share: .6, slider_min: 0, slider_max: 137.12345678901235, step: "any" },
  { criterion_id: "market", name: "Market", raw_rating: 90, local_weight: .4, global_share: .4, slider_min: 0, slider_max: 100, step: "any" },
];
it("keeps exact uncapped ratings, accepts only stated controls, and Reset clears only the trial", () => {
  const source = structuredClone(controls), { result } = renderHook(() => useWeightTrial("source"));
  act(() => result.current.setOpen(true)); act(() => result.current.acceptBaseline(controls));
  act(() => result.current.change("team", 250.9876543210987));
  expect(result.current.ratings).toEqual({ team: 250.9876543210987 }); expect(result.current.active).toBe(true);
  for (const value of [-1, NaN, Infinity]) act(() => result.current.change("team", value));
  act(() => result.current.change("mandate", 30)); expect(result.current.ratings).toEqual({ team: 250.9876543210987 });
  act(() => result.current.reset()); expect(result.current.active).toBe(false); expect(result.current.ratings).toEqual({});
  expect(result.current.baseline).toEqual(source); expect(controls).toEqual(source); expect(result.current.open).toBe(true);
});
it("Reset and close invalidate every callback captured under the previous generation", () => {
  const { result } = renderHook(() => useWeightTrial("source"));
  act(() => result.current.acceptBaseline(controls)); const old = result.current;
  act(() => result.current.reset()); act(() => old.change("team", 1)); act(() => old.acceptBaseline([])); act(() => old.setOpen(true));
  expect(result.current.ratings).toEqual({}); expect(result.current.baseline).toEqual(controls); expect(result.current.open).toBe(false);
  act(() => result.current.setOpen(true)); act(() => result.current.change("team", 3)); const editing = result.current;
  act(() => result.current.setOpen(false)); act(() => editing.change("market", 2));
  expect(result.current.active).toBe(false); expect(result.current.open).toBe(false); expect(result.current.generation).toBeGreaterThan(editing.generation);
});
it("a source change clears all trial data, keeps only panel openness, and returning cannot resurrect old callbacks", () => {
  const { result, rerender } = renderHook(({ source }) => useWeightTrial(source), { initialProps: { source: "one" } });
  act(() => result.current.setOpen(true)); act(() => result.current.acceptBaseline(controls)); act(() => result.current.change("team", 0));
  const old = result.current; rerender({ source: "two" });
  expect(result.current).toMatchObject({ open: true, active: false, baseline: null, ratings: {} });
  act(() => old.acceptBaseline(controls)); act(() => old.change("market", 5)); expect(result.current.baseline).toBeNull();
  rerender({ source: "one" }); act(() => old.acceptBaseline(controls)); act(() => old.change("team", 1));
  expect(result.current).toMatchObject({ active: false, baseline: null, ratings: {} }); expect(result.current.generation).toBeGreaterThan(old.generation);
});
