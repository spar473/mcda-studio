import { useCallback, useLayoutEffect, useRef, useState, type SyntheticEvent } from "react";
import { api, ApiError } from "../api/client";
import type { CalculationAssignment, CalculationEvent, CalculationInspection, CalculationWorkspace, DerivedCompilation,
  DerivedFormulaInput, Project, SourceFactorInput } from "../api/types";
import { canonical } from "../state/analysisContext";
import { useAnalysisRequest } from "../state/useAnalysisRequest";
import { saveDownload } from "./results/downloads";

type Model = CalculationInspection["model"];
type Factor = Model["sources"][number];
type Formula = Model["formulas"][number];
type Editor =
  | { kind: "factor"; id: string | null }
  | { kind: "formula"; id: string | null }
  | { kind: "unit" }
  | { kind: "review"; entry: "source" | "formula"; id: string };

export function download(value: unknown, name: string) {
  saveDownload(new Blob([JSON.stringify(value, null, 2) + "\n"], { type: "application/json" }), name);
}

const number = (value: number) => value.toLocaleString("en-NZ", { maximumSignificantDigits: 12 });
const show = (value: number | string | null | undefined) => value === null || value === undefined ? "missing" : typeof value === "number" ? number(value) : value;
const message = (e: unknown) => e instanceof ApiError
  ? [e.message, ...e.details.map(detail => detail.message)].filter(Boolean).join(" ")
  : e instanceof Error ? e.message : String(e);
const today = () => new Date().toISOString().slice(0, 10);
const unitText = (unit: string) => unit === "1" ? "(dimensionless)" : unit;

/** Parses "NZD customer^-1 year^-1" into base-dimension exponents; Python validates the result. */
export function parseDimension(text: string): Record<string, number> | null {
  const out: Record<string, number> = {};
  for (const token of text.split(/[\s×*·]+/).filter(Boolean)) {
    const match = /^([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\^(-?\d+))?$/.exec(token);
    if (!match?.[1]) return null;
    out[match[1]] = (out[match[1]] ?? 0) + Number(match[2] ?? 1);
  }
  return out;
}

const dimensionText = (dimension: Record<string, number>) =>
  Object.entries(dimension).map(([name, power]) => power === 1 ? name : `${name}^${String(power)}`).join(" × ") || "dimensionless";

/** Authoring and review of a calculation workspace. Python replays, checks and calculates. */
export function CalculationWorkspaceView({ project, fingerprint, document, version, onChange, onApply, busy }: {
  project: Project; fingerprint: string; document: unknown; version: number;
  onChange: (workspace: CalculationWorkspace, exported?: boolean) => void;
  onApply?: (assignments: CalculationAssignment[]) => Promise<string | null>;
  busy: boolean;
}) {
  const [person, setPerson] = useState("");
  const [editor, setEditor] = useState<Editor | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [run, setRun] = useState(0);
  const [applyKey, setApplyKey] = useState<string | null>(null);
  const [applied, setApplied] = useState<{ fingerprint: string; bundle: DerivedCompilation } | null>(null);
  const [copyKey, setCopyKey] = useState<string | null>(null);
  const [compiled, setCompiled] = useState<{ key: string; bundle: DerivedCompilation } | null>(null);
  // Sections stay open across recalculation, which hides the previous result while it reloads.
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const section = (id: string) => ({
    open: expanded[id] ?? false,
    onToggle: (e: SyntheticEvent<HTMLDetailsElement>) => {
      const open = e.currentTarget.open;
      setExpanded(current => current[id] === open ? current : { ...current, [id]: open });
    },
  });
  const key = canonical({ fingerprint, version, run });
  const liveKey = useRef(key);
  useLayoutEffect(() => { liveKey.current = key; }, [key]);
  const load = useCallback(async (signal: AbortSignal) => {
    const result = await api.inspectCalculations(project, document, signal);
    if (result.preview.project_fingerprint !== fingerprint) throw Error("Calculation does not match this project revision.");
    return result;
  }, [project, fingerprint, document]);
  const request = useAnalysisRequest(key, true, load);
  const result = request.status === "ready" ? request.result : null;
  const bound = result?.relationship === "bound" && result.workspace_exportable;
  const name = person.trim();
  const locked = !bound || pending || busy || !name;

  const record = async (event: CalculationEvent) => {
    if (!result || pending) return;
    const captured = key;
    setError(null); setPending(true);
    try {
      const next = await api.proposeCalculation(project, result.workspace, event, result.preview.review_digest);
      if (liveKey.current !== captured) return;
      if (next.preview.project_fingerprint !== fingerprint) throw Error("Change does not match this project revision.");
      setEditor(null);
      onChange(next.workspace);
    } catch (e) { if (liveKey.current === captured) setError(message(e)); }
    finally { setPending(false); }
  };

  const applyNow = async () => {
    if (!result || !onApply || applyKey !== key || pending || busy) return;
    const captured = key;
    setError(null); setPending(true);
    try {
      const application = await api.applyCalculation(project, result.workspace, result.preview.review_digest, name, new Date().toISOString());
      if (liveKey.current !== captured) return;
      if (application.bundle.preview.review_digest !== result.preview.review_digest || application.bundle.compiled_fingerprint !== application.project_fingerprint)
        throw Error("Application does not match the reviewed calculation.");
      const after = await onApply(application.assignments);
      if (after === null) throw Error("The project edit was not applied, so nothing was recorded.");
      if (after !== application.project_fingerprint) throw Error("The edited project does not match the reviewed application. Undo the edit; nothing was recorded.");
      setApplied({ fingerprint: after, bundle: application.bundle });
      onChange(application.inspection.workspace);
    } catch (e) { setError(message(e)); }
    finally { setPending(false); }
  };

  const compile = async () => {
    if (!result || copyKey !== key || pending) return;
    const captured = key;
    setError(null); setPending(true);
    try {
      const bundle = await api.compileDerived(project, result.preview.model, result.preview.review_digest);
      if (liveKey.current !== captured) return;
      if (bundle.preview.project_fingerprint !== fingerprint || bundle.preview.review_digest !== result.preview.review_digest || bundle.preview.model_digest !== result.preview.model_digest)
        throw Error("Compiled calculation does not match the reviewed preview.");
      setCompiled({ key: captured, bundle });
    } catch (e) { if (liveKey.current === captured) setError(message(e)); }
    finally { setPending(false); }
  };

  if (request.status === "loading") return <p role="status">Calculating…</p>;
  if (request.status === "error") return <><p role="alert">{request.message}</p><button type="button" onClick={request.retry}>Retry calculation</button></>;
  if (!result) return null;
  const model = result.model;
  const preview = result.preview;
  const calculations = new Map(preview.calculations.map(c => [c.id, c]));
  const factors = new Map(model.sources.map(s => [s.id, s]));
  const uses = new Map(result.factor_uses.map(u => [u.factor_id, u]));
  const checks = new Map(result.checks.map(c => [c.formula_id, c]));
  const alternative = (id: string | null | undefined) => project.alternatives.find(a => a.id === id)?.name ?? id ?? "";
  const criterion = (id: string | null | undefined) => project.criteria.find(c => c.id === id)?.name ?? id ?? "";
  const errors = preview.issues.some(i => i.severity === "error");
  const targets = preview.calculations.some(c => c.alternative_id !== null);
  const compilation = compiled?.key === key ? compiled.bundle : null;
  const appliedBundle = applied?.fingerprint === fingerprint && result.relationship === "bound" ? applied.bundle : null;
  const now = () => new Date().toISOString();

  return <>
    <section aria-label="Calculation workspace status">
      {result.relationship === "bound" && result.workspace_exportable && <p role="status">Bound to this project revision · {result.workspace.events.length} recorded change{result.workspace.events.length === 1 ? "" : "s"} · {result.bindings.length - 1} application{result.bindings.length === 2 ? "" : "s"} or rebind{result.bindings.length === 2 ? "" : "s"}.</p>}
      {result.relationship === "earlier" && <p role="alert">The open project is an earlier revision of this calculation workspace, for example after undoing an application. Redo returns to the bound revision. Rebinding records the open revision instead.</p>}
      {result.relationship === "different" && <p role="alert">{result.workspace_exportable ? "This calculation workspace belongs to another revision of the project. Editing is blocked until you return to that revision or rebind the workspace to the open project." : "This calculation model was written for another project revision and has no snapshot of it. It can be read but not edited, applied or exported as a workspace."}</p>}
      {result.relationship !== "bound" && result.workspace_exportable && <button type="button" disabled={pending || busy || !name}
        onClick={() => { void record({ kind: "rebind", project, recorded_by: name, recorded_at: now(), note: "" }); }}>Rebind workspace to the open project</button>}
      <label>Your name (recorded with each change)<input value={person} onChange={e => setPerson(e.target.value)}/></label>
      {!name && <p>Enter your name to record changes, reviews or applications.</p>}
    </section>
    {error && <p role="alert">{error}</p>}
    {preview.issues.map((issue, i) => <p role={issue.severity === "error" ? "alert" : undefined} key={i}>{issue.code}: {issue.message}</p>)}

    <ul aria-label="Calculated measurements">{preview.calculations.map(c => <li key={c.id}>
      <strong>{c.id}: {number(c.value)} {c.unit}</strong>
      <p><code>{c.expression}</code></p>
      {c.alternative_id && <p>For {alternative(c.alternative_id)}: {criterion(c.criterion_id)}.</p>}
      {c.alternative_id && <p>Current measurement: {show(c.before)} → calculated estimate: {String(c.value)} {c.unit}.</p>}
      <p>Inputs: {c.dependencies.join(", ")}. Source factors: {c.source_ids.join(", ")}.</p>
      <details {...section(`graph:${c.id}`)}><summary>Dependency graph for {c.id}</summary><Dependencies id={c.id} calculations={calculations} factors={factors} seen={[]}/></details>
    </li>)}</ul>

    <section aria-label="Measurement changes">
      <h4>Measurement changes</h4>
      {result.changes.length === 0 ? <p>No formula targets a measurement yet.</p> : <table>
        <thead><tr><th scope="col">Alternative</th><th scope="col">Criterion</th><th scope="col">Current</th><th scope="col">Calculated</th><th scope="col">Change</th></tr></thead>
        <tbody>{result.changes.map(c => <tr key={c.formula_id}>
          <td>{alternative(c.alternative_id)}</td><td>{criterion(c.criterion_id)}</td><td>{show(c.before)}</td><td>{number(c.after)}</td><td>{c.changed ? "Would change" : "Unchanged"}</td>
        </tr>)}</tbody></table>}
      <p>Applying replaces only these measurements in the open project, as one edit you can undo. It never clears a measurement. Calculated values are model estimates, not validated evidence.</p>
      {result.applicable && onApply ? <>
        <label><input type="checkbox" checked={applyKey === key} onChange={e => setApplyKey(e.target.checked ? key : null)}/>I reviewed every measurement change to apply</label>
        <button type="button" disabled={applyKey !== key || locked} onClick={() => { void applyNow(); }}>Apply to this project</button>
      </> : bound && !errors && targets && <p>Every calculated value already equals its measurement.</p>}
      {appliedBundle && <section aria-label="Applied calculation">
        <p>Applied. The project now holds the calculated values, unsaved until you Save. Export the workspace to keep the formula history; the calculation bundle documents this application for decision records.</p>
        <button type="button" onClick={() => download(appliedBundle, "calculation-bundle.json")}>Export calculation bundle for this application</button>
      </section>}
    </section>

    <details aria-label="Calculation source inputs" {...section("sources")}><summary>Source inputs and review</summary>
      <ul>{model.sources.map(s => {
        const use = uses.get(s.id);
        return <li key={s.id}>
          <strong>{s.id}</strong>: recorded {show(s.value)} {unitText(s.unit)}; review {s.review?.status ?? "pending"}{s.review?.corrected_value !== null && s.review?.corrected_value !== undefined ? `, corrected value ${String(s.review.corrected_value)}` : ""}.
          <p>{s.source.name}, {s.source.reference}{s.source.location ? `, ${s.source.location}` : ""}, {s.source.date} ({s.source.classification}). {s.source.description}</p>
          <p>Proposed by {s.origin.proposed_by} ({s.origin.kind === "tool" ? "tool proposal" : "human"}){s.origin.tool_id ? `, tool ${s.origin.tool_id} ${s.origin.tool_version ?? ""}` : ""}; reviewed by {s.review?.reviewer ?? "no reviewer"}.</p>
          {use && <p>{use.formula_ids.length ? `Used by ${use.formula_ids.join(", ")}` : "Not used by any formula"}{use.alternative_ids.length ? ` for ${use.alternative_ids.map(alternative).join(", ")}` : ""}.{use.shared ? " Shared across alternatives: one value, one review." : ""}</p>}
          <button type="button" disabled={locked} onClick={() => setEditor({ kind: "factor", id: s.id })}>Revise {s.id}</button>
          <button type="button" disabled={locked} onClick={() => setEditor({ kind: "review", entry: "source", id: s.id })}>Review {s.id}</button>
          <button type="button" disabled={locked} onClick={() => { void record({ kind: "remove", entry: "source", id: s.id, recorded_by: name, recorded_at: now() }); }}>Remove {s.id}</button>
        </li>;
      })}</ul>
      <button type="button" disabled={locked} onClick={() => setEditor({ kind: "factor", id: null })}>Add source factor</button>
    </details>

    <details aria-label="Formula definitions" {...section("formulas")}><summary>Formula definitions and review</summary>
      <ul>{model.formulas.map(f => {
        const check = checks.get(f.id);
        return <li key={f.id}>
          <strong>{f.id}</strong>: <code>{f.expression}</code> · {f.unit} · {f.review?.status ?? "unreviewed"}{f.alternative_id ? ` · target ${alternative(f.alternative_id)} / ${criterion(f.criterion_id)}` : " · intermediate"}.
          <p>Proposed by {f.origin.proposed_by}{f.origin.tool_id ? `, tool ${f.origin.tool_id} ${f.origin.tool_version ?? ""}` : ""}; reviewed by {f.review?.reviewer ?? "no reviewer"}. {f.review?.note}</p>
          {check && <p aria-label={`Check for ${f.id}`}>{check.status === "calculates" ? "Check: " : "Check failed: "}{check.explanation}</p>}
          <button type="button" disabled={locked} onClick={() => setEditor({ kind: "formula", id: f.id })}>Edit {f.id}</button>
          <button type="button" disabled={locked} onClick={() => setEditor({ kind: "review", entry: "formula", id: f.id })}>Review {f.id}</button>
          <button type="button" disabled={locked} onClick={() => { void record({ kind: "remove", entry: "formula", id: f.id, recorded_by: name, recorded_at: now() }); }}>Remove {f.id}</button>
        </li>;
      })}</ul>
      <button type="button" disabled={locked} onClick={() => setEditor({ kind: "formula", id: null })}>Add formula</button>
    </details>

    <details aria-label="Declared unit dimensions" {...section("units")}><summary>Declared unit dimensions</summary>
      <ul>{Object.entries(model.units).map(([unit, dimension]) => <li key={unit}>{unit}: {dimensionText(dimension)}.</li>)}</ul>
      <p>Unit 1 is dimensionless. No implicit scaling or conversion. A unit is never redefined; use a new name for a different dimension.</p>
      <button type="button" disabled={locked} onClick={() => setEditor({ kind: "unit" })}>Add unit</button>
    </details>

    {editor && bound && <EditorForm editor={editor} model={model} project={project} person={name} disabled={pending || busy || !name}
      onCancel={() => { setEditor(null); setError(null); }} onRecord={event => { void record(event); }}/>}

    <details aria-label="Calculation history" {...section("history")}><summary>Calculation history ({result.workspace.events.length})</summary>
      <p>Started from the project revision {result.workspace.source_project.title} with {result.workspace.original_model.sources.length} factors and {result.workspace.original_model.formulas.length} formulas. Each later change is appended; earlier definitions and reviews are kept.</p>
      <ol>{result.workspace.events.map((event, i) => <li key={i}>{describe(event)}</li>)}</ol>
    </details>

    <ul>{preview.limitations.map(s => <li key={s}>{s}</li>)}</ul>
    <button type="button" onClick={() => { setRun(n => n + 1); setError(null); }}>Recalculate preview</button>
    {result.workspace_exportable && <button type="button" onClick={() => { download(result.workspace, "calculation-workspace.json"); onChange(result.workspace, true); }}>Export calculation workspace</button>}
    <button type="button" onClick={() => download(preview, "calculation-preview.json")}>Download calculation preview</button>

    {targets && !errors && <section aria-label="Separate calculated copy">
      <p>Alternatively, compile a separate static project copy, leaving this project unchanged. Keep the calculation bundle for the original assumptions and trace; the project file alone does not contain them.</p>
      <label><input type="checkbox" checked={copyKey === key} onChange={e => setCopyKey(e.target.checked ? key : null)}/>I reviewed all target changes for the separate copy</label>
      <button type="button" disabled={copyKey !== key || pending} onClick={() => { void compile(); }}>Compile reviewed copy</button>
    </section>}
    {compilation && <section aria-label="Compiled calculation copy">
      <p>Compiled reproducibly from the reviewed preview. Export both files to retain the project and its calculation provenance. Open Projects → Import to analyse the exported copy; choose a separate copy if the project ID already exists.</p>
      <button type="button" onClick={() => download(compilation.project, "calculated-project.json")}>Export compiled project copy</button>
      <button type="button" onClick={() => download(compilation, "calculation-bundle.json")}>Export calculation bundle</button>
    </section>}
  </>;
}

type WorkspaceEvent = CalculationWorkspace["events"][number];

function describe(event: WorkspaceEvent): string {
  switch (event.kind) {
    case "unit": return `${event.recorded_by} declared unit ${event.unit} (${dimensionText(event.dimension)}) at ${event.recorded_at}.`;
    case "source": return `${event.factor.origin.proposed_by} ${event.factor.origin.kind === "tool" ? `(tool ${event.factor.origin.tool_id ?? ""}) ` : ""}defined factor ${event.factor.id} = ${show(event.factor.value)} ${event.factor.unit}, pending review, at ${event.recorded_at}.`;
    case "formula": return `${event.formula.origin.proposed_by} defined formula ${event.formula.id} = ${event.formula.expression}, pending review, at ${event.recorded_at}.`;
    case "review": return `${event.review.reviewer} ${event.review.status} ${event.entry === "source" ? "factor" : "formula"} ${event.id}${event.review.status === "corrected" ? ` as ${String(event.review.corrected_value)}` : ""} at ${event.review.reviewed_at}.`;
    case "remove": return `${event.recorded_by} removed ${event.entry === "source" ? "factor" : "formula"} ${event.id} at ${event.recorded_at}.`;
    case "rebind": return `${event.recorded_by} rebound the workspace to project revision ${event.project.title} at ${event.recorded_at}.`;
    case "apply": return `${event.recorded_by} applied the reviewed calculation at ${event.recorded_at}, giving project revision ${event.project_fingerprint.slice(0, 12)}.`;
  }
}

function Dependencies({ id, calculations, factors, seen }: {
  id: string; calculations: Map<string, CalculationInspection["preview"]["calculations"][number]>; factors: Map<string, Factor>; seen: string[];
}) {
  const calculation = calculations.get(id);
  if (!calculation) return null;
  return <ul>{calculation.dependencies.map(dependency => {
    const factor = factors.get(dependency);
    const inner = calculations.get(dependency);
    if (factor) {
      const value = factor.review?.status === "corrected" ? factor.review.corrected_value : factor.value;
      return <li key={dependency}>Factor {dependency} = {show(value)} {unitText(factor.unit)} ({factor.review?.status ?? "pending"} by {factor.review?.reviewer ?? "no reviewer"})</li>;
    }
    return <li key={dependency}>Formula {dependency} = <code>{inner?.expression}</code> = {inner ? `${number(inner.value)} ${unitText(inner.unit)}` : "unavailable"}
      {inner && !seen.includes(dependency) && <Dependencies id={dependency} calculations={calculations} factors={factors} seen={[...seen, id]}/>}</li>;
  })}</ul>;
}

function EditorForm({ editor, model, project, person, disabled, onCancel, onRecord }: {
  editor: Editor; model: Model; project: Project; person: string; disabled: boolean;
  onCancel: () => void; onRecord: (event: CalculationEvent) => void;
}) {
  if (editor.kind === "factor") return <FactorForm factor={model.sources.find(s => s.id === editor.id) ?? null} units={Object.keys(model.units)}
    person={person} disabled={disabled} onCancel={onCancel} onRecord={onRecord}/>;
  if (editor.kind === "formula") return <FormulaForm formula={model.formulas.find(f => f.id === editor.id) ?? null} units={Object.keys(model.units)}
    project={project} person={person} disabled={disabled} onCancel={onCancel} onRecord={onRecord}/>;
  if (editor.kind === "unit") return <UnitForm person={person} disabled={disabled} onCancel={onCancel} onRecord={onRecord}/>;
  return <ReviewForm entry={editor.entry} id={editor.id} person={person} disabled={disabled} onCancel={onCancel} onRecord={onRecord}/>;
}

function FactorForm({ factor, units, person, disabled, onCancel, onRecord }: {
  factor: Factor | null; units: string[]; person: string; disabled: boolean; onCancel: () => void; onRecord: (event: CalculationEvent) => void;
}) {
  const [id, setId] = useState(factor?.id ?? "");
  const [value, setValue] = useState(factor?.value === null || factor?.value === undefined ? "" : String(factor.value));
  const [unit, setUnit] = useState(factor?.unit ?? "1");
  const [sourceName, setSourceName] = useState(factor?.source.name ?? "");
  const [reference, setReference] = useState(factor?.source.reference ?? "");
  const [location, setLocation] = useState(factor?.source.location ?? "");
  const [date, setDate] = useState(factor?.source.date ?? today());
  const [description, setDescription] = useState(factor?.source.description ?? "");
  const [classification, setClassification] = useState(factor?.source.classification ?? "unknown");
  const [kind, setKind] = useState<"human" | "tool">("human");
  const [proposer, setProposer] = useState("");
  const [toolId, setToolId] = useState("");
  const [toolVersion, setToolVersion] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const label = factor ? `Revise factor ${factor.id}` : "New source factor";
  return <form aria-label={label} onSubmit={e => {
    e.preventDefault();
    const numeric = value.trim() === "" ? null : Number(value);
    if (numeric !== null && !Number.isFinite(numeric)) { setProblem("Enter a finite number, or leave the value empty."); return; }
    const definition: SourceFactorInput = {
      id: id.trim(), value: numeric, unit,
      source: { name: sourceName, reference, location, date, description, classification },
      origin: kind === "tool"
        ? { kind, proposed_by: proposer.trim() || person, tool_id: toolId.trim(), tool_version: toolVersion.trim() || null }
        : { kind, proposed_by: person, tool_id: null, tool_version: null },
      review: null,
    };
    setProblem(null);
    onRecord({ kind: "source", factor: definition, recorded_at: new Date().toISOString() });
  }}>
    <h4>{label}</h4>
    <p>A new definition is a proposal: the factor stays pending, and every calculation using it is unavailable, until it is reviewed. Earlier definitions and reviews stay in the history.</p>
    <label>Factor ID (used in formulas)<input required readOnly={factor !== null} value={id} onChange={e => setId(e.target.value)}/></label>
    <label>Value<input inputMode="decimal" value={value} onChange={e => setValue(e.target.value)}/></label>
    <label>Unit<select value={unit} onChange={e => setUnit(e.target.value)}>
      <option value="1">1 (dimensionless)</option>{units.map(u => <option key={u} value={u}>{u}</option>)}
    </select></label>
    <label>Source name<input required value={sourceName} onChange={e => setSourceName(e.target.value)}/></label>
    <label>Source reference<input required value={reference} onChange={e => setReference(e.target.value)}/></label>
    <label>Location in source<input value={location} onChange={e => setLocation(e.target.value)}/></label>
    <label>Source date<input type="date" required value={date} onChange={e => setDate(e.target.value)}/></label>
    <label>Source description<input required value={description} onChange={e => setDescription(e.target.value)}/></label>
    <label>Source relationship<select value={classification} onChange={e => setClassification(e.target.value as typeof classification)}>
      <option value="unknown">Unknown</option><option value="independent">Independent</option><option value="self_reported">Self-reported</option>
    </select></label>
    <label>Proposed by<select value={kind} onChange={e => setKind(e.target.value as typeof kind)}>
      <option value="human">Me (human-provided)</option><option value="tool">An identified tool</option>
    </select></label>
    {kind === "tool" && <>
      <label>Tool operator or proposer<input value={proposer} onChange={e => setProposer(e.target.value)}/></label>
      <label>Tool ID<input required value={toolId} onChange={e => setToolId(e.target.value)}/></label>
      <label>Tool version<input value={toolVersion} onChange={e => setToolVersion(e.target.value)}/></label>
    </>}
    {problem && <p role="alert">{problem}</p>}
    <button type="submit" disabled={disabled}>Record factor definition</button>
    <button type="button" onClick={onCancel}>Cancel</button>
  </form>;
}

function FormulaForm({ formula, units, project, person, disabled, onCancel, onRecord }: {
  formula: Formula | null; units: string[]; project: Project; person: string; disabled: boolean; onCancel: () => void; onRecord: (event: CalculationEvent) => void;
}) {
  const [id, setId] = useState(formula?.id ?? "");
  const [expression, setExpression] = useState(formula?.expression ?? "");
  const [unit, setUnit] = useState(formula?.unit ?? "1");
  const [target, setTarget] = useState(formula?.alternative_id ? `${formula.alternative_id}\u0000${formula.criterion_id ?? ""}` : "");
  const parents = new Set(project.criteria.map(c => c.parent_id).filter(Boolean));
  const leaves = project.criteria.filter(c => !parents.has(c.id) && c.scale && (c.scale.type === "ratio" || c.scale.type === "interval"));
  const label = formula ? `Edit formula ${formula.id}` : "New formula";
  return <form aria-label={label} onSubmit={e => {
    e.preventDefault();
    const [alternativeId, criterionId] = target ? target.split("\u0000") : [null, null];
    const definition: DerivedFormulaInput = {
      id: id.trim(), expression, unit, origin: { kind: "human", proposed_by: person, tool_id: null, tool_version: null },
      review: null, alternative_id: alternativeId ?? null, criterion_id: criterionId ?? null,
    };
    onRecord({ kind: "formula", formula: definition, recorded_at: new Date().toISOString() });
  }}>
    <h4>{label}</h4>
    <p>Use factor and formula IDs, numbers, + − × ÷ (written + - * /), brackets and min/max. The formula stays unreviewed until accepted; acceptance requires it to calculate with consistent dimensions.</p>
    <label>Formula ID<input required readOnly={formula !== null} value={id} onChange={e => setId(e.target.value)}/></label>
    <label>Expression<textarea required value={expression} onChange={e => setExpression(e.target.value)}/></label>
    <label>Result unit<select value={unit} onChange={e => setUnit(e.target.value)}>
      <option value="1">1 (dimensionless)</option>{units.map(u => <option key={u} value={u}>{u}</option>)}
    </select></label>
    <label>Target measurement<select value={target} onChange={e => setTarget(e.target.value)}>
      <option value="">None (intermediate result)</option>
      {project.alternatives.flatMap(a => leaves.map(c => <option key={`${a.id}/${c.id}`} value={`${a.id}\u0000${c.id}`}>{a.name} / {c.name} ({c.scale?.unit ?? "1"})</option>))}
    </select></label>
    <button type="submit" disabled={disabled}>Record formula definition</button>
    <button type="button" onClick={onCancel}>Cancel</button>
  </form>;
}

function UnitForm({ person, disabled, onCancel, onRecord }: {
  person: string; disabled: boolean; onCancel: () => void; onRecord: (event: CalculationEvent) => void;
}) {
  const [unit, setUnit] = useState("");
  const [text, setText] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  return <form aria-label="New unit" onSubmit={e => {
    e.preventDefault();
    const dimension = parseDimension(text);
    if (!dimension) { setProblem("Write base dimensions as names with optional powers, for example NZD customer^-1 year^-1."); return; }
    setProblem(null);
    onRecord({ kind: "unit", unit: unit.trim(), dimension, recorded_by: person, recorded_at: new Date().toISOString() });
  }}>
    <h4>New unit</h4>
    <label>Unit name<input required value={unit} onChange={e => setUnit(e.target.value)}/></label>
    <label>Base dimensions<input required value={text} onChange={e => setText(e.target.value)} placeholder="NZD customer^-1 year^-1"/></label>
    {problem && <p role="alert">{problem}</p>}
    <button type="submit" disabled={disabled}>Record unit</button>
    <button type="button" onClick={onCancel}>Cancel</button>
  </form>;
}

function ReviewForm({ entry, id, person, disabled, onCancel, onRecord }: {
  entry: "source" | "formula"; id: string; person: string; disabled: boolean; onCancel: () => void; onRecord: (event: CalculationEvent) => void;
}) {
  const [status, setStatus] = useState<"accepted" | "corrected" | "rejected">("accepted");
  const [corrected, setCorrected] = useState("");
  const [note, setNote] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const label = `Review ${entry === "source" ? "factor" : "formula"} ${id}`;
  return <form aria-label={label} onSubmit={e => {
    e.preventDefault();
    const value = Number(corrected);
    if (status === "corrected" && (!corrected.trim() || !Number.isFinite(value))) { setProblem("Enter a valid corrected number."); return; }
    setProblem(null);
    onRecord({ kind: "review", entry, id, review: { status, reviewer: person, reviewed_at: new Date().toISOString(), note, corrected_value: status === "corrected" ? value : null } });
  }}>
    <h4>{label}</h4>
    <label>Review decision<select aria-label="Review decision" value={status} onChange={e => setStatus(e.target.value as typeof status)}>
      <option value="accepted">Accept</option>
      {entry === "source" && <option value="corrected">Accept a corrected value</option>}
      <option value="rejected">Reject</option>
    </select></label>
    {status === "corrected" && <label>Corrected value<input required inputMode="decimal" value={corrected} onChange={e => setCorrected(e.target.value)}/></label>}
    <label>Review note<textarea value={note} onChange={e => setNote(e.target.value)}/></label>
    {problem && <p role="alert">{problem}</p>}
    <button type="submit" disabled={disabled}>Record review</button>
    <button type="button" onClick={onCancel}>Cancel</button>
  </form>;
}
