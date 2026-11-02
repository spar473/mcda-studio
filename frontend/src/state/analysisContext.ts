import type { AnalysisConfiguration, Project } from "../api/types";

/** Transient selection, deliberately outside Project and undo history. */
export interface AnalysisSelection {
  scenarioId: string | null;
  profileId: string | null;
  criterionId: string | null;
  /** A method viewed instead of the saved one; null (or absent) views the saved method. */
  method?: string | null;
  /** Run settings tried for the viewed method (for example SMAA-2's draws and seed); never saved. */
  parameters?: Record<string, unknown> | null;
}
export const BASE_SELECTION: AnalysisSelection = { scenarioId: null, profileId: null, criterionId: null, method: null, parameters: null };

export interface AnalysisContext extends AnalysisSelection {
  fingerprint: string;
  configuration: AnalysisConfiguration;
  resolvedProfileId: string | null;
}

export function reconcileSelection(project: Project, selection: AnalysisSelection): AnalysisSelection {
  return {
    scenarioId: project.scenarios.some((s) => s.id === selection.scenarioId) ? selection.scenarioId : null,
    profileId: project.weight_profiles.some((p) => p.id === selection.profileId) ? selection.profileId : null,
    criterionId: project.criteria.some((c) => c.id === selection.criterionId) ? selection.criterionId : null,
    // Kept as viewed even when it equals the saved method, so undoing a saved default never moves the view.
    method: selection.method ?? null,
    parameters: selection.parameters ?? null,
  };
}

/** Reference resolution only; all decision mathematics remains in Python. */
export function resolveContext(project: Project, fingerprint: string, selected: AnalysisSelection): AnalysisContext {
  const selection = reconcileSelection(project, selected);
  const scenario = project.scenarios.find((s) => s.id === selection.scenarioId);
  const method = selection.method ?? project.analysis.method;
  return {
    ...selection,
    fingerprint,
    resolvedProfileId: selection.profileId ?? scenario?.weight_profile_id ?? project.weight_profiles[0]?.id ?? null,
    configuration: {
      method,
      // Saved parameters belong to the saved method; any other viewed method uses its defaults.
      parameters: { ...(method === project.analysis.method ? structuredClone(project.analysis.parameters) : {}),
        ...structuredClone(selection.parameters ?? {}) },
      // Explicit null means base model, even when the saved default names a scenario.
      scenario_id: selection.scenarioId,
      weight_profile_id: selection.profileId,
    },
  };
}

/** Canonical identity includes nested parameters and pending candidates, never display rounding. */
export function canonical(value: unknown): string {
  if (value === undefined) return "null";
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  const object = value as Record<string, unknown>;
  return `{${Object.keys(object).sort().map((key) => `${JSON.stringify(key)}:${canonical(object[key])}`).join(",")}}`;
}

export function analysisKey(context: AnalysisContext, kind: string, parameters: unknown = null): string {
  return canonical({ fingerprint: context.fingerprint, configuration: context.configuration,
    criterion: context.criterionId, kind, parameters });
}
