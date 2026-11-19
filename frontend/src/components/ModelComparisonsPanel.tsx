import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { AnalysisConfiguration, CheckedFactorRun, ModelComparison, ModelComparisonCompilation, ModelComparisonInspection, ModelOutputSpec, ModelTargetSelection, Project } from "../api/types";
import { canonical } from "../state/analysisContext";
import { useAnalysisRequest } from "../state/useAnalysisRequest";
import { download } from "./CalculationWorkspaceView";

type InputKind = "source" | "formula" | "distribution" | "group" | "checks" | "interval" | "aggregation";
function entries(spec: ModelOutputSpec): { kind: InputKind; id: string; value: unknown }[] {
  return [
    ...spec.model.sources.map(value => ({ kind: "source" as const, id: value.id, value })),
    ...spec.model.formulas.map(value => ({ kind: "formula" as const, id: value.id, value })),
    ...(spec.uncertainty?.distributions ?? []).map(value => ({ kind: "distribution" as const, id: value.factor_id, value })),
    ...(spec.uncertainty?.groups ?? []).map(value => ({ kind: "group" as const, id: value.id, value })),
    ...(spec.checks ? [{ kind: "checks" as const, id: "checks", value: spec.checks }] : []),
    ...(spec.range.kind === "source_interval" ? spec.range.intervals.map(value => ({ kind: "interval" as const, id: value.factor_id, value })) : []),
    ...(spec.aggregation ? [{ kind: "aggregation" as const, id: "aggregation", value: spec.aggregation }] : []),
  ];
}

export function ModelComparisonsPanel({ project, fingerprint, configuration, onDirty, onComparison }: {
  project: Project; fingerprint: string; configuration?: AnalysisConfiguration;
  onDirty: (dirty: boolean) => void; onComparison?: (value: ModelComparison | null) => void;
}) {
  const [document, setDocument] = useState<unknown>(null);
  const [original, setOriginal] = useState<unknown>(null);
  const [pending, setPending] = useState({ comparison: false, bundle: false, checked: false });
  const dirty = pending.comparison || pending.bundle || pending.checked;
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reviewer, setReviewer] = useState(""); const [note, setNote] = useState("");
  const [input, setInput] = useState(""); const [inputStatus, setInputStatus] = useState<"accepted" | "rejected" | "corrected">("accepted"); const [correction, setCorrection] = useState("");
  const [side, setSide] = useState<"" | "left" | "right">(""); const [alternative, setAlternative] = useState(""); const [criterion, setCriterion] = useState("");
  const [ack, setAck] = useState(""); const [scopeAck, setScopeAck] = useState("");
  const [bundle, setBundle] = useState<{ key: string; value: ModelComparisonCompilation } | null>(null);
  const [checked, setChecked] = useState<{ key: string; value: CheckedFactorRun } | null>(null);
  const [runKind, setRunKind] = useState<"mavt" | "mavt_sorting" | "smaa2_factors">("smaa2_factors");
  const [draws, setDraws] = useState("1000"); const [seed, setSeed] = useState("7");
  const [editor, setEditor] = useState("");
  const sequence = useRef(0);
  const key = canonical({ fingerprint, document, configuration });
  const liveKey = useRef(key); useLayoutEffect(() => { liveKey.current = key; }, [key]);
  useEffect(() => { onDirty(dirty); }, [onDirty, dirty]);
  const load = useCallback(async (signal: AbortSignal) => {
    const result = await api.inspectModels(project, document, signal);
    if (result.current_fingerprint !== fingerprint) throw Error("Model response belongs to another project revision.");
    return result;
  }, [project, document, fingerprint]);
  const request = useAnalysisRequest(key, document !== null, load);
  const current = request.status === "ready" ? request.result : null;
  useEffect(() => { onComparison?.(current?.comparison ?? null); }, [current, onComparison]);
  const selected = current && side ? current.comparison[side] : null;
  const selectionKey = canonical({ key, side, alternative, criterion, reviewer, note });
  const checkedKey = canonical({ key, side, runKind, draws, seed });
  const actionKey = canonical({ key, reviewer, note, input, inputStatus, correction, side, alternative, criterion, ack, scopeAck, runKind, draws, seed });
  const liveAction = useRef(actionKey); useLayoutEffect(() => { liveAction.current = actionKey; }, [actionKey]);
  const review = () => ({ status: "accepted", reviewer, reviewed_at: new Date().toISOString(), note, corrected_value: null });
  async function mutate(action: () => Promise<ModelComparisonInspection>) {
    const captured = actionKey; setBusy(true); setError(null);
    try { const result = await action(); if (captured === liveAction.current) { setDocument(result.comparison); setPending(previous => ({ ...previous, comparison: true })); } }
    catch (error) { if (captured === liveAction.current) setError(String(error)); }
    finally { setBusy(false); }
  }
  const ready = current && !current.stale && !busy && reviewer.trim() !== "" && note.trim() !== "";
  return <section className="panel model-comparisons" aria-label="Model comparisons">
    <h3>Model comparisons</h3>
    <p>Keep two explicit models side by side. Ranges retain their declared meaning; overlapping ranges leave the model disagreement open. Only one reviewed output may supply a criterion cell.</p>
    <label>Model comparison or historical bundle<input type="file" accept=".json" disabled={dirty || busy} onChange={event => {
      const file = event.target.files?.[0]; const token = ++sequence.current;
      setDocument(null); setOriginal(null); setError(null); setBundle(null); setChecked(null);
      if (!file) return;
      if (file.size > 8_000_000) { setError("Model file exceeds the 8 MB limit."); return; }
      void file.text().then(async text => {
        const value: unknown = JSON.parse(text);
        if (typeof value === "object" && value !== null && "artifact_kind" in value && value.artifact_kind === "model_comparison_compilation") {
          const verified = await api.verifyModels(value);
          if (token === sequence.current) { setDocument(verified.inspection.comparison); setOriginal(value); }
        } else if (token === sequence.current) { setDocument(value); setOriginal(value); }
      }).catch((error: unknown) => { if (token === sequence.current) setError(String(error)); });
    }}/></label>
    {dirty && <p role="status">Model review or run changes are not exported. Export the current files before saving or leaving.</p>}
    {error && <p role="alert">{error}</p>}
    {request.status === "loading" && <p role="status">Checking both models…</p>}
    {request.status === "error" && <><p role="alert">{request.message}</p><button type="button" onClick={request.retry}>Retry model comparison</button></>}
    {current && <>
      {current.stale && <p role="alert">Stale project binding. These declarations are historical; create and review new inputs for this revision.</p>}
      <p>{current.comparable ? "Known matching scope; two distinct model declarations remain." : "Incomparable until scope and unavailable outputs are reviewed."}</p>
      <div className="starter-grid">{(["left", "right"] as const).map(which => <ModelView key={which} spec={current.comparison[which]} snapshot={current[which]}/>)}</div>
      <ul aria-label="Model questions">{current.questions.map((question, index) => <li key={`${question.code}-${index}`}><strong>{question.question}</strong><p>{question.why}</p><p>{question.evidence}</p></li>)}</ul>
      <label>Model reviewer<input value={reviewer} disabled={busy} onChange={event => setReviewer(event.target.value)}/></label>
      <label>Model review rationale<textarea value={note} disabled={busy} onChange={event => setNote(event.target.value)}/></label>
      <p>Review deterministic sources/formulas first. Each change clears this model's distribution, group and quantity-check reviews; review those separately afterwards.</p>
      <label>Displayed input to review<select value={input} disabled={busy} onChange={event => setInput(event.target.value)}><option value="">Choose one input</option>{(["left", "right"] as const).flatMap(which => entries(current.comparison[which]).map(entry => <option key={`${which}:${entry.kind}:${entry.id}`} value={`${which}:${entry.kind}:${entry.id}`}>{which}: {entry.kind} {entry.id}</option>))}</select></label>
      {input && <details open><summary>Exact selected declaration</summary><pre>{JSON.stringify(entries(current.comparison[input.split(":")[0] as "left" | "right"]).find(entry => `${entry.kind}:${entry.id}` === input.split(":").slice(1).join(":"))?.value, null, 2)}</pre></details>}
      <label>Input review action<select value={inputStatus} disabled={busy} onChange={event => setInputStatus(event.target.value as typeof inputStatus)}><option value="accepted">Accept</option><option value="rejected">Reject</option><option value="corrected">Correct source value</option></select></label>
      {inputStatus === "corrected" && <label>Corrected source value<input value={correction} disabled={busy} onChange={event => setCorrection(event.target.value)}/></label>}
      <button type="button" disabled={!ready || !input || (inputStatus === "corrected" && (input.split(":")[1] !== "source" || correction.trim() === ""))} onClick={() => {
        const [which, kind, id] = input.split(":") as ["left" | "right", InputKind, string];
        void mutate(() => api.reviewModelInput(project, current.comparison, which, kind, id, { ...review(), status: inputStatus, corrected_value: inputStatus === "corrected" ? Number(correction) : null }, current.review_digest));
      }}>Record one input review</button>{" "}
      <button type="button" disabled={!ready} onClick={() => void mutate(() => api.reviewModels(project, current.comparison, review(), current.review_digest))}>Accept comparison declarations</button>
      <h4>Select one measurement supplier</h4>
      <label>Selected model output<select value={side} disabled={busy} onChange={event => { setSide(event.target.value as typeof side); setScopeAck(""); }}><option value="">Choose one output</option><option value="left">Left — {current.comparison.left.label}</option><option value="right">Right — {current.comparison.right.label}</option></select></label>
      <label>Target alternative<select value={alternative} disabled={busy} onChange={event => setAlternative(event.target.value)}><option value="">Choose one alternative</option>{project.alternatives.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label>Target criterion<select value={criterion} disabled={busy} onChange={event => setCriterion(event.target.value)}><option value="">Choose one criterion</option>{project.criteria.filter(node => !project.criteria.some(child => child.parent_id === node.id)).map(node => <option key={node.id} value={node.id}>{node.name} ({node.scale?.unit ?? "no unit"})</option>)}</select></label>
      {selected && <><dl>{Object.entries(selected.scope).map(([field, value]) => <div key={field}><dt>{field.replaceAll("_", " ")}</dt><dd>{value ?? "unknown"}</dd></div>)}</dl><label><input type="checkbox" checked={scopeAck === canonical({ key, side, alternative, criterion })} disabled={busy} onChange={event => setScopeAck(event.target.checked ? canonical({ key, side, alternative, criterion }) : "")}/>I reviewed this exact population, geography, period, currency basis and unit for the target cell.</label></>}
      <label><input type="checkbox" checked={ack === key} disabled={busy} onChange={event => setAck(event.target.checked ? key : "")}/>I reviewed both declarations and the separate-copy selection diff. The other model and disagreement remain retained.</label>
      <p>Selection: {side || "none"} → {alternative || "no alternative"} / {criterion || "no criterion"}. The original project remains the source snapshot.</p>
      {side && alternative && criterion && <p aria-label="Model selection measurement diff">Current measurement: {project.performances.find(item => item.alternative_id === alternative && item.criterion_id === criterion)?.value ?? "missing"} → selected output: {current[side].run?.value ?? "unavailable"} {current[side].run?.unit}. Only this target cell is supplied by the selected output.</p>}
      <button type="button" disabled={!ready || !selected || !alternative || !criterion || current.comparison.review?.status !== "accepted" || ack !== key || scopeAck !== canonical({ key, side, alternative, criterion })} onClick={() => {
        if (!selected || !side) return;
        const captured = actionKey;
        const selection: ModelTargetSelection = { side, alternative_id: alternative, criterion_id: criterion, target_scope: selected.scope, review: { ...review(), status: "accepted" } };
        setBusy(true); setError(null);
        void api.compileModels(project, current.comparison, selection, current.review_digest).then(value => { if (captured === liveAction.current) { setBundle({ key: selectionKey, value }); setPending(previous => ({ ...previous, bundle: true })); } }).catch((error: unknown) => { if (captured === liveAction.current) setError(String(error)); }).finally(() => setBusy(false));
      }}>Compile selected output into a separate copy</button>
      {bundle?.key === selectionKey && <section aria-label="Model selection result"><p>Compiled only {bundle.value.selection.side}; all model declarations, ranges and questions remain in the bundle.</p><button type="button" onClick={() => { download(bundle.value, "model-comparison-bundle.json"); setPending(previous => ({ ...previous, comparison: false, bundle: false })); }}>Download model comparison bundle</button>{" "}<button type="button" onClick={() => download(bundle.value.calculation.project, "selected-model-project.json")}>Download compiled project copy</button></section>}
      <h4>Checked fundamental-factor run</h4>
      <p>Use the explicitly selected model's measurement targets, shared fundamental draws and reviewed quantity checks. A violated draw aborts; no draws are discarded.</p>
      {selected && (!selected.checks || !selected.uncertainty) && <p>This output needs separately declared factor uncertainty and reviewed quantity checks before a checked run is available. Source bounds alone are not distributions.</p>}
      <label>Checked method<select value={runKind} disabled={busy} onChange={event => setRunKind(event.target.value as typeof runKind)}><option value="mavt">MAVT</option><option value="mavt_sorting">Value-based sorting</option><option value="smaa2_factors">Fixed-weight factor-based SMAA-2</option></select></label>
      <label>Checked draws<input type="number" min="1" value={draws} disabled={busy} onChange={event => setDraws(event.target.value)}/></label><label>Checked seed<input type="number" min="0" value={seed} disabled={busy} onChange={event => setSeed(event.target.value)}/></label>
      <button type="button" disabled={!selected?.checks || !selected.uncertainty || current.stale || busy} onClick={() => {
        if (!selected) return;
        const captured = actionKey; setBusy(true); setError(null);
        void api.runCheckedFactors({ project, model: selected.model, uncertainty: selected.uncertainty, checks: selected.checks, parameters: { run: runKind, draws: Number(draws), seed: Number(seed), configuration: configuration ?? project.analysis } }).then(value => { if (captured === liveAction.current) { setChecked({ key: checkedKey, value }); setPending(previous => ({ ...previous, checked: true })); } }).catch((error: unknown) => { if (captured === liveAction.current) setError(String(error)); }).finally(() => setBusy(false));
      }}>Run selected model with quantity checks</button>
      {checked?.key === checkedKey && <><p>Completed {checked.value.record.result.draw_count} checked draws. Checks digest: <code className="digest">{checked.value.checks_digest}</code></p><details><summary>Checked results and shared-factor traces</summary><pre>{JSON.stringify(checked.value.record.result, null, 2)}</pre></details><button type="button" onClick={() => { download(checked.value, "checked-factor-run.json"); setPending(previous => ({ ...previous, checked: false })); }}>Download checked factor run</button></>}
      <details><summary>Edit new comparison declarations</summary><p>Start from the exact JSON below. Editing creates a new unreviewed comparison; model, uncertainty and check bindings still must match. Original files remain readable and downloadable.</p><button type="button" onClick={() => setEditor(JSON.stringify(current.comparison, null, 2))}>Copy displayed declarations into editor</button><label>New comparison JSON<textarea rows={14} value={editor} onChange={event => setEditor(event.target.value)}/></label><button type="button" disabled={busy || current.stale || !editor} onClick={() => {
        const captured = key; setBusy(true); setError(null);
        void Promise.resolve().then(() => api.draftModelComparison(project, JSON.parse(editor))).then(value => { if (captured === liveKey.current) { setDocument(value); setPending(previous => ({ ...previous, comparison: true })); } }).catch((error: unknown) => setError(String(error))).finally(() => setBusy(false));
      }}>Create new comparison draft</button></details>
      <ul>{current.limitations.map(value => <li key={value}>{value}</li>)}</ul>
      <button type="button" onClick={() => { download(current.comparison, "model-comparison.json"); setPending(previous => ({ ...previous, comparison: false })); }}>Export current model comparison</button>{" "}<button type="button" onClick={() => download(current, "model-comparison-inspection.json")}>Export both model runs and questions</button>{" "}<button type="button" onClick={() => download(original, "original-model-comparison.json")}>Download original opened artifact</button>{" "}<button type="button" onClick={() => { setDocument(original && typeof original === "object" && "inspection" in original ? (original as ModelComparisonCompilation).inspection.comparison : original); setPending({ comparison: false, bundle: false, checked: false }); }}>Discard changes since opening</button>
    </>}
  </section>;
}

function ModelView({ spec, snapshot }: { spec: ModelOutputSpec; snapshot: ModelComparisonInspection["left"] }) {
  return <article aria-label={spec.label}><h4>{spec.label}</h4><p>Output: {spec.formula_id}. Range kind: <strong>{spec.range.kind}</strong>.</p>
    <dl>{Object.entries(spec.scope).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{value ?? "unknown"}</dd></div>)}</dl>
    {snapshot.run ? <><p>Deterministic output: <strong>{snapshot.run.value} {snapshot.run.unit}</strong>.</p><p>Declared range: <strong>{snapshot.run.range.lower} to {snapshot.run.range.upper}</strong>. {snapshot.run.range.interpretation}</p><p>Draws: {snapshot.run.draw_count}; seed: {snapshot.run.seed ?? "none"}; quantile algorithm: {snapshot.run.range.quantile_algorithm ?? "not applicable"}.</p><p>Omitted unrelated quantities: {snapshot.run.omitted_quantity_ids.join(", ") || "none"}.</p><button type="button" onClick={() => download(snapshot.run, `${spec.id}-model-output.json`)}>Download {spec.label} run</button></> : <p role="status">Unavailable: {snapshot.reason}</p>}
    <ul aria-label={`${spec.label} formula graph`}>{spec.model.formulas.map(formula => <li key={formula.id}><code>{formula.id} ← {formula.expression}</code> [{formula.unit}]; {formula.review?.status ?? "unreviewed"}; {formula.alternative_id ? `measurement target ${formula.alternative_id}/${formula.criterion_id}` : "intermediate"}</li>)}</ul>
    <table><caption>{spec.label} factors and source relationships</caption><thead><tr><th>Factor</th><th>Value / unit</th><th>Source</th><th>Review</th></tr></thead><tbody>{spec.model.sources.map(source => <tr key={source.id}><th>{source.id}</th><td>{source.value ?? "missing"} {source.unit}</td><td>{source.source.classification}; {source.source.date}; {source.source.reference}; {source.source.location}</td><td>{source.review?.status ?? "unreviewed"}</td></tr>)}</tbody></table>
    <details><summary>Exact model, factor distributions, quantity checks, reviews and run</summary><pre>{JSON.stringify({ specification: spec, snapshot }, null, 2)}</pre></details>
  </article>;
}
