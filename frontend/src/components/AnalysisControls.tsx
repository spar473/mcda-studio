import { useState } from "react";
import type { MethodInfo, Project } from "../api/types";
import type { AnalysisContext, AnalysisSelection } from "../state/analysisContext";
import { ConfirmDialog } from "./ui";

/** SMAA-2 run settings tried in this view; they travel in the request, never into the project. */
function RunSettings({ parameters, disabled, onChange }: {
  parameters: Record<string, unknown>; disabled: boolean; onChange: (patch: Record<string, unknown>) => void;
}) {
  const number = (key: string, fallback: number) => typeof parameters[key] === "number" ? parameters[key] : fallback;
  const commit = (key: string, text: string) => { const value = Number(text); if (Number.isInteger(value)) onChange({ [key]: value }); };
  return <fieldset className="run-settings" aria-label="SMAA-2 run settings">
    <label>Uncertain inputs <select aria-label="Uncertain inputs" disabled={disabled}
      value={typeof parameters.uncertainty === "string" ? parameters.uncertainty : "combined"}
      onChange={(e) => onChange({ uncertainty: e.target.value })}>
      <option value="combined">Measurements and weights</option>
      <option value="performance">Measurements only</option>
      <option value="preference">Weights only</option>
    </select></label>
    <label>Draws <input aria-label="Draws" disabled={disabled} inputMode="numeric" defaultValue={String(number("samples", 10000))}
      onBlur={(e) => commit("samples", e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") commit("samples", e.currentTarget.value); }}/></label>
    <label>Seed <input aria-label="Seed" disabled={disabled} inputMode="numeric" defaultValue={String(number("seed", 0))}
      onBlur={(e) => commit("seed", e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") commit("seed", e.currentTarget.value); }}/></label>
  </fieldset>;
}

export function AnalysisControls({ project, context, onSelect, disabled = false, methods, onUseMethodAsDefault }: {
  project: Project; context: AnalysisContext; disabled?: boolean; onSelect: (patch: Partial<AnalysisSelection>) => void;
  /** Registered methods (from /api/meta). Viewing one is transient; it never edits the project. */
  methods?: MethodInfo[];
  /** One undoable edit that makes the viewed method the saved default. */
  onUseMethodAsDefault?: () => void;
}) {
  const resolved = project.weight_profiles.find((p) => p.id === context.resolvedProfileId);
  const viewed = context.configuration.method;
  const saved = project.analysis.method;
  const [confirming, setConfirming] = useState<string[] | null>(null);
  const options = methods ?? [];
  const label = (name: string) => options.find((m) => m.name === name)?.label ?? name;
  function useAsDefault() {
    const parameters = Object.keys(project.analysis.parameters);
    if (parameters.length) setConfirming(parameters); else onUseMethodAsDefault?.();
  }
  return <section className="analysis-controls" aria-label="Analysis context">
    <label>Method <select aria-label="Method" disabled={disabled} value={viewed}
      onChange={(e) => onSelect({ method: e.target.value, parameters: null })}>
      {(options.some((m) => m.name === viewed) ? options : [...options, { name: viewed, label: viewed }])
        .map((m) => <option key={m.name} value={m.name}>{m.label}{m.name === saved ? " (saved default)" : ""}</option>)}
    </select></label>
    {viewed !== saved && onUseMethodAsDefault && <button type="button" disabled={disabled} onClick={useAsDefault}>
      Use viewed method as saved default</button>}
    {options.find((m) => m.name === viewed)?.capabilities.includes("acceptability") && <RunSettings
      parameters={context.configuration.parameters} disabled={disabled}
      onChange={(patch) => onSelect({ parameters: { ...context.configuration.parameters, ...patch } })}/>}
    <label>Scenario <select aria-label="Scenario" disabled={disabled} value={context.scenarioId ?? ""}
      onChange={(e) => onSelect({ scenarioId: e.target.value || null })}>
      <option value="">Base model</option>
      {project.scenarios.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
    </select></label>
    <label>Weight profile <select aria-label="Weight profile" disabled={disabled} value={context.profileId ?? ""}
      onChange={(e) => onSelect({ profileId: e.target.value || null })}>
      <option value="">Automatic (scenario, then first profile)</option>
      {project.weight_profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
    </select></label>
    {viewed !== saved && <span className="muted small" role="status">Viewing {label(viewed)} with its default parameters; the saved method is {label(saved)}.</span>}
    {viewed === "ahp" && <span className="muted small" aria-label="AHP reads no profile or scenario">AHP reads no weight profile or scenario:
      these two selections do not change its priorities.</span>}
    <details className="context-details"><summary>Details</summary>
      <span className="muted small">Resolved profile: {resolved?.name ?? "none"} · Revision {context.fingerprint.slice(0, 12)}</span>
    </details>
    <details><summary>Interpreting this model</summary>
      <p>Measurement scales describe information: categories have no order, ordinal levels have order without equal spacing,
        interval scales have an arbitrary zero, and ratio scales have a meaningful zero. Preference values express judgements on those measurements.</p>
      <p>Swing ratings compare worst-to-best improvements over stated ranges. Local weights are normalised within siblings;
        global leaf weights multiply the local weights down the tree. A weight is not abstract importance.</p>
      <p>Fixed anchors retain their stated range. Local anchors depend on the current alternative set: changing alternatives can change
        preference values and the meaning of the swing. Review swing judgements when that range changes.</p>
      <p>Additive MAVT is compensatory and assumes preferential independence. A poor criterion can be offset by another;
        an overall preference value is not a probability. These explanations follow the documented additive MAVT model, not observed DECERNS behaviour.</p>
      <p>Value-based sorting places each alternative in an ordered class by comparing its overall MAVT value with fixed boundaries. It inherits
        every MAVT assumption; with local anchors, adding an alternative can move others between classes, so fixed anchors are recommended.</p>
    </details>
    {confirming && <ConfirmDialog title="Use viewed method as saved default"
      message={<>Saved parameters belong to {label(saved)} and will be cleared: {confirming.join(", ")}. {label(viewed)} uses its own defaults. You can undo this.</>}
      confirmLabel="Use as saved default" onCancel={() => setConfirming(null)}
      onConfirm={() => { setConfirming(null); onUseMethodAsDefault?.(); }}/>}
  </section>;
}
