import { renderHook } from "@testing-library/react";
import { expect, it } from "vitest";
import { useTrialDownloadGuard } from "../../src/components/WeightTrialGate";

it("rejects an in-flight download throughout a trial and permanently after Reset or a source change", () => {
  const { result, rerender } = renderHook(gate => useTrialDownloadGuard(gate), { initialProps: { active: false, generation: 0 } });
  const ticket = result.current.ticket(), permits = result.current.permits;
  expect(permits(ticket)).toBe(true); rerender({ active: true, generation: 0 });
  expect(result.current.disabled).toBe(true); expect(result.current.ticket()).toBeNull(); expect(permits(ticket)).toBe(false);
  rerender({ active: false, generation: 1 }); expect(result.current.disabled).toBe(false); expect(permits(ticket)).toBe(false);
  const restored = result.current.ticket(); expect(permits(restored)).toBe(true);
  rerender({ active: false, generation: 2 }); expect(permits(restored)).toBe(false); expect(permits(result.current.ticket())).toBe(true);
});
it("an unmounted export owner can never finish a download after leaving its tab", () => {
  const { result, unmount } = renderHook(() => useTrialDownloadGuard());
  const ticket = result.current.ticket(), permits = result.current.permits;
  expect(permits(ticket)).toBe(true); unmount(); expect(permits(ticket)).toBe(false);
});
