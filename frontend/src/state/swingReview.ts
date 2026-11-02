import type { Project } from "../api/types";
import { canonical, resolveContext, type AnalysisSelection } from "./analysisContext";

/** Identity of raw preference/range inputs only; no domain or preference maths in the browser. */
export function swingReviewIdentity(project: Project, selected: AnalysisSelection): string {
  const context = resolveContext(project, "", selected);
  const scenario = project.scenarios.find((s) => s.id === context.scenarioId);
  const profile = project.weight_profiles.find((p) => p.id === context.resolvedProfileId);
  // The method and its parameters never change swing ranges, so viewing another method needs no review.
  const { scenario_id, weight_profile_id } = context.configuration;
  return canonical({ configuration: { scenario_id, weight_profile_id }, resolvedProfile: context.resolvedProfileId,
    judgements: profile?.judgements ?? null,
    criteria: project.criteria.map((node) => {
      const vf = scenario?.value_function_overrides[node.id] ?? node.value_function;
      const local = vf?.kind === "linear" && node.scale?.anchor_mode === "local";
      return { id: node.id, parent: node.parent_id, scale: node.scale, valueFunction: vf,
        observed: local ? [...project.alternatives].sort((a,b) => a.id.localeCompare(b.id)).map((a) => ({
          id: a.id, values: project.performances.filter((p) => p.alternative_id === a.id && p.criterion_id === node.id).map((p) => p.value),
        })) : null };
    }).sort((a,b) => a.id.localeCompare(b.id)),
  });
}
