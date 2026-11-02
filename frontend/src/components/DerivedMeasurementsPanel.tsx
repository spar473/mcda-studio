import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { AnalysisConfiguration, CalculationAssignment, CalculationWorkspace, ModelComparison, Project } from "../api/types";
import { canonical } from "../state/analysisContext";
import { useAnalysisRequest } from "../state/useAnalysisRequest";
import { ModelComparisonsPanel } from "./ModelComparisonsPanel";
import { FactorUncertaintyPanel } from "./FactorUncertaintyPanel";
import { ArtifactBindingStatus } from "./ArtifactBindingStatus";
import { CalculationWorkspaceView, download } from "./CalculationWorkspaceView";

const isCompilation = (value: unknown) => typeof value === "object" && value !== null && "compilation_version" in value;

export function DerivedMeasurementsPanel({ project, fingerprint, onDirty, onApply, busy = false, configuration, onComparison }: {
  project: Project; fingerprint: string;
  onDirty?: (dirty: boolean) => void;
  onApply?: (assignments: CalculationAssignment[]) => Promise<string | null>;
  busy?: boolean; configuration?: AnalysisConfiguration; onComparison?: (value: ModelComparison | null) => void;
}) {
  const [document, setDocument] = useState<unknown>(null);
  const [original, setOriginal] = useState<unknown>(null);
  const [version, setVersion] = useState(0);
  const [factorDirty, setFactorDirty] = useState(false);
  const [modelDirty, setModelDirty] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Opened by the user; unexported changes also keep it open, so Save's redirect shows why.
  const [expanded, setExpanded] = useState(false);
  const sequence = useRef(0);
  useEffect(() => { onDirty?.(dirty || factorDirty || modelDirty); }, [dirty, factorDirty, modelDirty, onDirty]);
  const open = (value: unknown) => { setDocument(value); setOriginal(value); setVersion(v => v + 1); setDirty(false); };
  return <details className="panel" aria-label="Calculated measurements preview" open={expanded || dirty || factorDirty || modelDirty}
    onToggle={e => { const open = e.currentTarget.open; if (open !== expanded) setExpanded(open); }}><summary>Calculated measurements</summary>
    <p>Author source factors and formulas, or open a calculation model, workspace or bundle, to see how accepted source inputs produce a measurement. Changes are recorded in a calculation workspace in this session; export it to keep them. Project measurements change only when you apply a reviewed calculation (one undoable edit) or compile a separate copy.</p>
    <label>Calculation model
      <input type="file" accept=".json,application/json" disabled={dirty || factorDirty || modelDirty} onChange={event => {
        const file = event.target.files?.[0];
        const current = ++sequence.current;
        setDocument(null); setOriginal(null); setError(null); setDirty(false);
        if (!file) return;
        if (file.size > 8_000_000) { setError("Calculation file exceeds the 8 MB limit."); return; }
        void file.text().then(text => {
          const value: unknown = JSON.parse(text);
          if (sequence.current === current) open(value);
        }).catch(() => { if (sequence.current === current) setError("Could not read calculation model JSON."); });
      }}/>
    </label>
    {document === null && <button type="button" onClick={() => open({ schema_version: 1, project_fingerprint: fingerprint, units: {}, sources: [], formulas: [] })}>Start a new calculation model</button>}
    {dirty && <>
      <p role="status">Calculation changes have not been exported. Saving the project does not store them: export the calculation workspace to keep the formula history before saving or closing.</p>
      <button type="button" onClick={() => { setDocument(original); setVersion(v => v + 1); setDirty(false); }}>Discard calculation changes since export</button>
    </>}
    {factorDirty && <p role="status">Factor uncertainty changes or a completed run have not been exported. Export them before saving or leaving.</p>}
    {error && <p role="alert">{error}</p>}
    {document !== null && (isCompilation(document)
      ? <BundleView project={project} fingerprint={fingerprint} bundle={document}/>
      : <CalculationWorkspaceView project={project} fingerprint={fingerprint} document={document} version={version} busy={busy} onApply={onApply}
        onChange={(workspace: CalculationWorkspace, exported?: boolean) => {
          setDocument(workspace); setVersion(v => v + 1);
          if (exported) { setOriginal(workspace); setDirty(false); } else setDirty(true);
        }}/>)}
    {document !== null && !isCompilation(document) && <FactorUncertaintyPanel project={project} fingerprint={fingerprint} document={document} onDirty={setFactorDirty} configuration={configuration}/>}
    <ModelComparisonsPanel project={project} fingerprint={fingerprint} configuration={configuration} onDirty={setModelDirty} onComparison={onComparison}/>
  </details>;
}

/** A reopened calculation bundle: verified and reconstructed in Python, then read historically. */
function BundleView({ project, fingerprint, bundle }: { project: Project; fingerprint: string; bundle: unknown }) {
  const [run, setRun] = useState(0);
  const key = canonical({ fingerprint, bundle, run });
  const liveKey = useRef(key);
  useLayoutEffect(() => { liveKey.current = key; }, [key]);
  const load = useCallback(async (signal: AbortSignal) => {
    const result = await api.previewDerived(project, bundle, signal);
    if (result.project_fingerprint !== fingerprint) throw Error("Calculation does not match this project revision.");
    return result;
  }, [project, fingerprint, bundle]);
  const request = useAnalysisRequest(key, true, load);
  return <>
    <ArtifactBindingStatus project={project} fingerprint={fingerprint} artifact={bundle} label="Calculation bundle"/>
    {request.status === "loading" && <p role="status">Calculating…</p>}
    {request.status === "error" && <><p role="alert">{request.message}</p><button type="button" onClick={request.retry}>Retry calculation</button></>}
    {request.status === "ready" && <>
      {request.result.issues.map((issue, i) => <p role={issue.severity === "error" ? "alert" : undefined} key={i}>{issue.code}: {issue.message}</p>)}
      <ul aria-label="Calculated measurements">{request.result.calculations.map(c => <li key={c.id}>
        <strong>{c.id}: {c.value.toLocaleString("en-NZ", { maximumSignificantDigits: 12 })} {c.unit}</strong>
        <p><code>{c.expression}</code></p>
        {c.alternative_id && <p>For {project.alternatives.find(a => a.id === c.alternative_id)?.name}: {project.criteria.find(n => n.id === c.criterion_id)?.name}.</p>}
        {c.alternative_id && <p>Current measurement: {c.before ?? "missing"} → calculated estimate: {String(c.value)} {c.unit}.</p>}
        <p>Inputs: {c.dependencies.join(", ")}. Source factors: {c.source_ids.join(", ")}.</p>
      </li>)}</ul>
      <p>This bundle records one reviewed compilation. To continue editing, open the calculation workspace exported with it, or start a workspace from its model on its source project.</p>
      <ul>{request.result.limitations.map(s => <li key={s}>{s}</li>)}</ul>
      <button type="button" onClick={() => setRun(n => n + 1)}>Recalculate preview</button>
      <button type="button" onClick={() => download(request.result, "calculation-preview.json")}>Download calculation preview</button>
    </>}
  </>;
}
