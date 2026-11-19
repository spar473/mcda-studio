import type { Project, ValueFunction } from "../api/types";
import { canonical, resolveContext, type AnalysisSelection } from "./analysisContext";

/** Stored domain endpoints/anchor labels only, never an evaluated value function.
 * Local min/max stay in Python; the identity conservatively tracks their observations. */
function rangeInputs(vf: ValueFunction | null | undefined, scale: Project["criteria"][number]["scale"]) {
  if (!vf) return { domain: null, anchors: null };
  if (vf.kind === "linear") return {
    domain: scale?.anchor_mode === "local" ? null : { lower: scale?.lower ?? null, upper: scale?.upper ?? null },
    anchors: vf.direction === "decreasing" ? [1, 0] : [0, 1],
  };
  if (vf.kind === "piecewise_linear") {
    const first = vf.points[0], last = vf.points[vf.points.length - 1];
    return { domain: { lower: first?.x ?? null, upper: last?.x ?? null },
      anchors: [first?.value ?? null, last?.value ?? null] };
  }
  if (vf.kind === "direct_rating") return {
    domain: { lower: vf.min_rating, upper: vf.max_rating }, anchors: [0, 1],
  };
  return { domain: null, anchors: Object.entries(vf.mapping)
    .filter(([, value]) => value === 0 || value === 1).sort(([a], [b]) => a.localeCompare(b)) };
}

/** Range identity excludes viewed profile, its judgements, scenario ID and curve interiors. */
export function swingReviewIdentity(project: Project, selected: AnalysisSelection): string {
  const context = resolveContext(project, "", selected);
  const scenario = project.scenarios.find((s) => s.id === context.scenarioId);
  return canonical({ criteria: project.criteria.map((node) => {
    const vf = scenario?.value_function_overrides[node.id] ?? node.value_function;
    const local = vf?.kind === "linear" && node.scale?.anchor_mode === "local";
    return { id: node.id, parent: node.parent_id,
      scale: node.scale ? { type: node.scale.type, unit: node.scale.unit,
        labels: node.scale.labels, anchor_mode: node.scale.anchor_mode } : null,
      range: rangeInputs(vf, node.scale),
      observed: local ? [...project.alternatives].sort((a, b) => a.id.localeCompare(b.id)).map((a) => ({
        id: a.id, values: project.performances.filter((p) => p.alternative_id === a.id && p.criterion_id === node.id).map((p) => p.value),
      })) : null,
    };
  }).sort((a, b) => a.id.localeCompare(b.id)) });
}
