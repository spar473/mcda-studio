import type { Capability, MethodInfo } from "../../api/types";

/** One Results view and the method capability it needs (see the method seam design note). */
export interface ResultPanel { id: string; label: string; capability: Capability }

const MAVT_PANELS: ResultPanel[] = [
  { id: "overall", label: "Overall values", capability: "value_scores" },
  { id: "contributions", label: "Contributions", capability: "contributions" },
  { id: "partial", label: "Partial values", capability: "contributions" },
  { id: "dominance", label: "Dominance", capability: "contributions" },
  { id: "comparison", label: "Scenario comparison", capability: "scenario_comparison" },
  { id: "inspection", label: "Linked inspection", capability: "contributions" },
];

/** Panels by method, in display order. A method missing here has no Results panels yet. */
export const RESULT_PANELS: Record<string, readonly ResultPanel[]> = {
  mavt: MAVT_PANELS,
  mavt_sorting: [{ id: "classes", label: "Classes", capability: "classes" }, ...MAVT_PANELS],
  smaa2: [{ id: "acceptability", label: "Acceptability", capability: "acceptability" }],
  promethee2: [
    { id: "flows", label: "Flows", capability: "flows" },
    { id: "partial_order", label: "PROMETHEE I", capability: "flows" },
    { id: "explanation", label: "Explanation against MAVT", capability: "flows" },
  ],
  ahp: [
    { id: "priorities", label: "AHP priorities", capability: "consistency" },
    { id: "consistency", label: "Consistency", capability: "consistency" },
  ],
};

const ALL_PANELS = [...new Map(Object.values(RESULT_PANELS).flat().map((p) => [p.id, p])).values()];

/** The panels a method shows (registered for it and backed by a declared capability), and the
 * views other methods offer that it does not, for the one-line explanation. */
export function panelsFor(method: string, info: MethodInfo | undefined): { shown: ResultPanel[]; missing: ResultPanel[] } {
  const capabilities = new Set(info?.capabilities ?? []);
  const shown = (RESULT_PANELS[method] ?? []).filter((p) => info === undefined || capabilities.has(p.capability));
  const ids = new Set(shown.map((p) => p.id));
  return { shown, missing: ALL_PANELS.filter((p) => !ids.has(p.id)) };
}
