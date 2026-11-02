import { useEffect, useMemo, useRef, useState } from "react";
import type { CriterionNode, Meta, Operation, Project, ValueFunctionKind } from "../api/types";
import { allowedKinds, directionOf, VALUE_FUNCTION_LABEL } from "../model/defaults";
import { candidateFromDraft, initialValueDraft, insertControlPoint, setDraftNumber } from "../model/valueDraft";
import { analysisKey, canonical, type AnalysisContext } from "../state/analysisContext";
import { useValueFunctionPreview } from "../state/usePreviews";
import { ValueFunctionChart, plotExtent } from "./ValueFunctionChart";
import { Banner, Modal } from "./ui";

export interface CandidateGuard { dirty: boolean; commit: () => Promise<boolean> }
interface Props {
  targetScenarioId?: string | null;
  project: Project; context: AnalysisContext; node: CriterionNode; meta: Meta;
  apply: (ops: Operation[]) => Promise<boolean>; onClose: () => void;
  onGuard: (guard: CandidateGuard | null) => void;
}

export function ValueFunctionEditor({ project, context, node, meta, apply, onClose, onGuard, targetScenarioId = null }: Props) {
  const scenarioEdit = targetScenarioId !== null;
  const [origin] = useState(() => analysisKey(context, "editor-source"));
  const [initial] = useState(() => {
    const effective = project.scenarios.find((s) => s.id === context.scenarioId)?.value_function_overrides[node.id] ?? node.value_function;
    if (!node.scale || !effective) throw new Error("Choose a measurement scale and function before opening the editor.");
    return initialValueDraft(node.scale, effective);
  });
  const [draft, updateDraft] = useState(initial);
  const [selected, setSelected] = useState<number | null>(null);
  const [gesture, setGesture] = useState(false);
  const [applying, setApplying] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [reviewed, setReviewed] = useState<string | null>(null);
  const setDraft = (next: typeof initial) => { updateDraft(next); setReviewed(null); };
  const parsed = useMemo(() => candidateFromDraft(draft), [draft]);
  const candidate = parsed.candidate;
  const vf = candidate.value_function;
  const scale = candidate.scale;
  const candidateKey = canonical(candidate);
  const changed = candidateKey !== canonical({ scale: initial.scale, value_function: initial.valueFunction });
  const dirty = changed || parsed.errors.length > 0;
  const stale = origin !== analysisKey(context, "editor-source");
  const request = useValueFunctionPreview(project, context, candidate, parsed.errors.length === 0 && !stale);
  const preview = request.status === "ready" ? request.result : null;
  // Freeze the viewport for this editor session: dragging an endpoint must not move the coordinate system.
  const [extent, setExtent] = useState<ReturnType<typeof plotExtent>>(null);
  useEffect(() => {
    if (!extent && preview?.resolved_domain) setExtent(plotExtent(preview.resolved_domain.lower, preview.resolved_domain.upper));
  }, [extent, preview]);
  const currentReviewKey = canonical({ origin, candidate });
  const canApply = dirty && !stale && !gesture && !applying && (!context.scenarioId || scenarioEdit && targetScenarioId === context.scenarioId) && parsed.errors.length === 0 &&
    preview?.readiness === "ready" && (!changed || reviewed === currentReviewKey);
  const commit = async () => {
    if (!dirty) { onClose(); return true; }
    if (!canApply) { setMessage("Apply needs a current, valid backend preview and explicit range acknowledgement. Resolve the highlighted issues first."); return false; }
    setApplying(true);
    const ok = await apply(scenarioEdit ? [{ op: "set_scenario_override", scenario_id: targetScenarioId,
      criterion_id: node.id, value_function: vf }] : [{ op: "set_scale", criterion_id: node.id, scale },
      { op: "set_value_function", criterion_id: node.id, value_function: vf }]);
    setApplying(false);
    if (ok) onClose(); else setMessage("The candidate could not be applied. It is still available here for correction or cancellation.");
    return ok;
  };
  // Keep navigation/save pointed at the latest candidate, without persisting any UI state.
  const commitRef = useRef(commit); commitRef.current = commit;
  useEffect(() => { onGuard({ dirty, commit: () => commitRef.current() }); }, [dirty, onGuard]);
  useEffect(() => () => onGuard(null), [onGuard]);
  const raw = (key: string, value: number | null | undefined) => draft.text[key] ?? (value == null ? "" : String(value));
  const input = (key: string, label: string, value: number | null | undefined, readOnly = false) =>
    <input aria-label={label} inputMode="decimal" type="text" value={raw(key, value)} readOnly={readOnly}
      onChange={(e) => setDraft(setDraftNumber(draft, key, e.target.value))}/>;
  function switchKind(kind: ValueFunctionKind) {
    if (kind === vf.kind) return;
    if (parsed.errors.length) { setMessage("Correct incomplete numeric inputs before changing representation."); return; }
    let next = null;
    if (kind === "linear") next = { kind, direction: "increasing" as const, out_of_domain: "error" as const };
    if (kind === "piecewise_linear" && preview?.resolved_domain) {
      const first = preview.samples[0], last = preview.samples[preview.samples.length-1];
      if (typeof first?.measurement === "number" && typeof last?.measurement === "number") next = {
        kind, points: [{ x: first.measurement, value: first.partial_value }, { x: last.measurement, value: last.partial_value }], out_of_domain: "error" as const };
    }
    if (kind === "direct_rating" && preview?.resolved_domain) next = { kind, min_rating: preview.resolved_domain.lower,
      max_rating: preview.resolved_domain.upper, out_of_domain: "error" as const };
    if (!next) { setMessage("A resolved numeric domain is required before this kind switch. Complete local measurements or enter fixed anchors first."); return; }
    setDraft(initialValueDraft(scale, next)); setSelected(null); setMessage(null);
  }
  function removePoint(index: number) {
    if (parsed.errors.length) { setMessage("Correct incomplete numeric inputs before removing a point."); return; }
    if (vf.kind !== "piecewise_linear" || index === 0 || index === vf.points.length-1) return;
    setDraft({ ...draft, valueFunction: { ...vf, points: vf.points.filter((_, i) => i !== index) }, text: {} }); setSelected(null);
  }
  const direction = directionOf(vf, scale.labels);
  return <Modal title={`Edit value function · ${node.name}`} className="value-editor" onClose={onClose} footer={<>
    <span className="muted small" role="status">{dirty ? "Pending candidate · project unchanged" : "No candidate changes"}</span>
    <button type="button" onClick={onClose}>Cancel candidate</button>
    <button type="button" className="primary" disabled={!canApply} onClick={() => void commit()}>Apply candidate</button>
  </>}>
    <p className="muted small">Revision {context.fingerprint.slice(0,12)} · {context.scenarioId ? `Scenario ${context.scenarioId}` : "Base model"} · Criterion {node.id}</p>
    {context.scenarioId && !scenarioEdit && <Banner kind="warning">Scenario overrides can be inspected and previewed here. Open Scenarios → Edit override to commit scenario-only functions.</Banner>}
    {scenarioEdit && <Banner kind="info">Editing scenario {targetScenarioId}: {project.scenarios.find(s=>s.id===targetScenarioId)?.value_function_overrides[node.id] ? "explicit override" : "inherited from base; Apply creates an override"}. Shared units, scale bounds and anchor policy are read-only. Reset to Base removes the override in Scenarios.</Banner>}
    {stale && <Banner kind="error">The project or analysis context changed while this editor was open. Cancel and reopen to edit the current revision. This candidate cannot be applied.</Banner>}
    {message && <Banner kind="error" onDismiss={() => setMessage(null)}>{message}</Banner>}
    <div className="value-editor-grid">
      <div>
        <ValueFunctionChart draft={draft} onChange={setDraft} preview={preview} extent={extent} onGesture={setGesture}
          lockScale={scenarioEdit} selected={selected} onSelect={setSelected} onRemove={removePoint} alternativeNames={Object.fromEntries(project.alternatives.map((a) => [a.id, a.name]))}
          onInsert={(x, value) => { const next = insertControlPoint({ ...draft, newX: String(x), newValue: String(value) }); if(next)setDraft(next); }}/>
        <button type="button" disabled={!preview?.resolved_domain || gesture} onClick={() => {
          if (preview?.resolved_domain) setExtent(plotExtent(preview.resolved_domain.lower, preview.resolved_domain.upper));
        }}>Fit current domain to chart</button>
        <div className="preview-status" aria-live="polite">
          {parsed.errors.length > 0 ? <p role="alert">Invalid numeric input: {parsed.errors.join("; ")}</p> : request.status === "loading" ? <p>Previewing candidate…</p> :
            request.status === "error" ? <p role="alert">{request.message}</p> : <>
              <p><strong>Function {request.result.readiness}</strong> · Measurements {request.result.measurement_readiness}</p>
              {request.result.resolved_domain && <p>Effective domain: {request.result.resolved_domain.lower} – {request.result.resolved_domain.upper} {scale.unit ?? ""} · source: {request.result.resolved_domain.source}</p>}
              <ul className="issue-list inline" aria-label="Candidate diagnostics">{request.result.diagnostics.map((issue, i) =>
                <li key={i} className={issue.severity}><code>{issue.code}</code> {issue.message}<div className="muted small">{issue.path}</div></li>)}</ul>
            </>}
        </div>
      </div>
      <fieldset disabled={applying || stale} className="candidate-fields">
        <label>Representation<select aria-label="Candidate representation" value={vf.kind} onChange={(e) => switchKind(e.target.value as ValueFunctionKind)}>
          {allowedKinds(meta, scale.type).map((kind) => <option key={kind} value={kind}>{VALUE_FUNCTION_LABEL[kind]}</option>)}
        </select></label>
        <p className="muted small">Measurement scale: {scale.type}. {scale.type === "categorical" ? "Categories have no intrinsic order or spacing." : scale.type === "ordinal" ? "Label order is explicit; spacing is not a measurement." : "Numeric lower/upper bounds are separate from worst/best preference."}</p>
        <label>Measurement unit<input aria-label="Candidate unit" disabled={scenarioEdit} value={draft.scale.unit ?? ""} onChange={(e) => setDraft({ ...draft, scale: { ...draft.scale, unit: e.target.value || null } })}/></label>
        <p>Preference direction: {scale.type === "categorical" ? "Explicit category judgements (no intrinsic order)" : direction === "decreasing" ? "Lower measurements are preferred" : direction === "increasing" ? "Higher measurements are preferred" : "Explicit label judgements or invalid monotonicity"}</p>
        {vf.kind === "linear" && <>
          <label>Direction<select aria-label="Candidate direction" value={vf.direction} onChange={(e) => setDraft({ ...draft, valueFunction: { ...vf, direction: e.target.value as "increasing" | "decreasing" } })}>
            <option value="increasing">Increasing</option><option value="decreasing">Decreasing</option></select></label>
          <label>Anchors<select aria-label="Candidate anchors" disabled={scenarioEdit} value={scale.anchor_mode} onChange={(e) => setDraft({ ...draft, scale: { ...scale, anchor_mode: e.target.value as "fixed" | "local" } })}>
            <option value="fixed">Fixed, explicit scale bounds</option><option value="local">Local, all alternative measurements</option></select></label>
          {scale.anchor_mode === "fixed" ? <div className="row"><label>Numeric lower{input("lower", "Candidate lower", draft.scale.lower, scenarioEdit)}</label><label>Numeric upper{input("upper", "Candidate upper", draft.scale.upper, scenarioEdit)}</label></div> :
            <p className="note">Local anchors require every alternative measurement for this criterion. Adding/removing alternatives can change the preference range and requires reviewing swing judgements.</p>}
        </>}
        {vf.kind === "piecewise_linear" && <>
          <label>Endpoint preference convention<select aria-label="Candidate endpoint convention" value={vf.points[0]?.value === 1 ? "decreasing" : vf.points[0]?.value === 0 ? "increasing" : "invalid"}
            onChange={(e) => { if (parsed.errors.length) { setMessage("Correct incomplete numeric inputs before changing endpoint convention."); return; }
              const down = e.target.value === "decreasing"; setDraft({ ...draft, valueFunction: { ...vf,
              points: vf.points.map((point, i) => ({ ...point, value: i === 0 ? down ? 1 : 0 : i === vf.points.length-1 ? down ? 0 : 1 : point.value })) }, text: {} }); }}>
            <option value="increasing">Lower endpoint 0, upper endpoint 1</option><option value="decreasing">Lower endpoint 1, upper endpoint 0</option><option value="invalid" disabled>Invalid endpoint judgement</option></select></label>
          <table aria-label="Candidate control points"><thead><tr><th>Point</th><th>Measurement x</th><th>Preference input</th><th>Action</th></tr></thead><tbody>
            {draft.valueFunction.kind === "piecewise_linear" && draft.valueFunction.points.map((point, i, points) => <tr key={i} className={selected === i ? "selected-point" : ""}>
              <th><button type="button" onClick={() => setSelected(i)} aria-label={`Select point ${i+1}`}>{i+1}</button></th>
              <td>{input(`point.${i}.x`, `Point ${i+1} measurement`, point.x)}</td>
              <td>{input(`point.${i}.value`, `Point ${i+1} preference`, point.value, i===0 || i===points.length-1)}</td>
              <td>{i>0 && i<points.length-1 && <button type="button" onClick={() => removePoint(i)} aria-label={`Remove point ${i+1}`}>Remove</button>}</td>
            </tr>)}
          </tbody></table>
          <div className="row"><label>New measurement<input aria-label="New point measurement" value={draft.newX} onChange={(e) => setDraft({ ...draft, newX: e.target.value })}/></label>
            <label>New preference input<input aria-label="New point preference" value={draft.newValue} onChange={(e) => setDraft({ ...draft, newValue: e.target.value })}/></label></div>
          <button type="button" onClick={() => { const next = insertControlPoint(draft); if(next)setDraft(next);else setMessage("Enter both new-point coordinates as finite numbers."); }}>Add control point</button>
          <p className="muted small">Double-click the plot to add a judgement at that position. Select a handle and press Delete to remove an interior point. New points are inserted before the last endpoint; the backend validates ordering without silently sorting.</p>
        </>}
        {vf.kind === "direct_rating" && <div className="row"><label>Rating minimum{input("min_rating", "Candidate rating minimum", draft.valueFunction.kind === "direct_rating" ? draft.valueFunction.min_rating : null)}</label>
          <label>Rating maximum{input("max_rating", "Candidate rating maximum", draft.valueFunction.kind === "direct_rating" ? draft.valueFunction.max_rating : null)}</label></div>}
        {vf.kind === "qualitative" && <table aria-label="Candidate label judgements"><thead><tr><th>Label</th><th>Preference input</th></tr></thead><tbody>
          {draft.scale.labels.map((label) => <tr key={label}><th>{label}</th><td>{input(`label.${label}`, `Preference for ${label}`, draft.valueFunction.kind === "qualitative" ? draft.valueFunction.mapping[label] : null)}</td></tr>)}
        </tbody></table>}
        {vf.kind !== "qualitative" && <label>Measurements outside domain<select aria-label="Candidate outside domain" value={vf.out_of_domain} onChange={(e) => setDraft({ ...draft, valueFunction: { ...vf, out_of_domain: e.target.value as "error" | "clamp" } })}>
          <option value="error">Report an error</option><option value="clamp">Clamp to endpoint (explicit)</option></select></label>}
        {vf.kind !== "linear" && <p className="note">{vf.kind === "piecewise_linear" ? "Control-point endpoints" : vf.kind === "direct_rating" ? "Rating limits" : "Explicit labels"} determine this representation. Stored scale anchor mode remains {scale.anchor_mode}; a later linear function will use that choice.</p>}
      </fieldset>
    </div>
    {dirty && <Banner kind="warning"><strong>Review preference ranges and swing interpretation.</strong> Changing endpoints, direction, units or shape changes the meaning of a worst-to-best swing. Measurements affected by this candidate are listed below. Swing ratings are not adjusted automatically.
      <label className="review-check"><input type="checkbox" aria-label="Acknowledge candidate range change" checked={reviewed === currentReviewKey} onChange={(e) => setReviewed(e.target.checked ? currentReviewKey : null)}/> I understand this change and will review swing judgements after applying.</label></Banner>}
    <table aria-label="Candidate alternative values"><thead><tr><th>Alternative</th><th>Raw measurement</th><th>Backend partial value</th><th>Status</th></tr></thead><tbody>
      {preview?.markers.map((marker) => <tr key={marker.alternative_id}><th>{project.alternatives.find((a) => a.id === marker.alternative_id)?.name ?? marker.alternative_id}</th>
        <td>{marker.raw_measurement ?? "Missing"}</td><td>{marker.partial_value ?? "Unavailable"}</td><td>{marker.clamped ? "Clamped to endpoint" : marker.partial_value === null ? "Incomplete or invalid" : "In domain"}</td></tr>)}
    </tbody></table>
    <details className="math-help"><summary>Measurement scales, anchors and swing judgements</summary>
      <p>Preference values express explicit judgements on a 0–1 scale. Measurement units and scale type constrain meaningful comparisons; ordinal ranks and category names do not imply equal preference spacing. Piecewise segments are evaluated by the Python engine between your control points.</p>
      <p>Fixed anchors preserve an explicit comparison range. Local anchors are determined from the full alternative set and can change when its measurements or membership change. Weights represent the relative value of swings from each criterion’s worst level to its best over those particular ranges.</p>
      <p>Additive MAVT is compensatory: a gain on one criterion may offset a loss on another. Its use requires defensible preferential independence and appropriate swing judgements. A curve preview alone does not establish those assumptions or imply a complete model is ready to rank.</p>
    </details>
  </Modal>;
}
