import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { DecisionDetails, DecisionRecordInspection, DecisionRecordV2, MethodInfo, Project } from "../api/types";
import { canonical } from "../state/analysisContext";
import { useAnalysisRequest } from "../state/useAnalysisRequest";
import { DecisionRecordView } from "./DecisionRecordView";
import { saveDownload } from "./results/downloads";

type Loaded = { name: string; value: unknown };
type Context = { method: string; weight_profile_id: string | null; scenario_id: string | null };
type AnyRecord = DecisionRecordInspection["record"];
const MAX_ANALYSES = 6;

const lines = (text: string) => text.split("\n").map(s => s.trim()).filter(Boolean);
const today = () => {
  const d = new Date();
  return `${String(d.getFullYear())}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const field = (value: unknown, key: string): unknown => typeof value === "object" && value !== null ? (value as Record<string, unknown>)[key] : undefined;
const isArtifact = (value: unknown) => field(value, "compilation_version") !== undefined;
const isReceipt = (value: unknown) => field(value, "receipt_version") !== undefined;
const message = (e: unknown) => e instanceof ApiError
  ? [e.message, ...e.details.map(detail => detail.message)].filter(Boolean).join(" ")
  : e instanceof Error ? e.message : String(e);

async function readFiles(files: FileList | null): Promise<Loaded[]> {
  const out: Loaded[] = [];
  for (const file of Array.from(files ?? [])) {
    if (file.size > 8_000_000) throw Error(`${file.name} exceeds the 8 MB limit.`);
    try { out.push({ name: file.name, value: JSON.parse(await file.text()) as unknown }); }
    catch { throw Error(`Could not read ${file.name} as JSON.`); }
  }
  return out;
}

/** Create, export, reopen and revise decision records. Python builds and verifies every record;
 * nothing is stored in the library, and an existing record file is never changed. */
export function DecisionRecordPanel({ project, fingerprint, active, methods, onDirty }: {
  project: Project; fingerprint: string; active: boolean; methods: MethodInfo[] | undefined;
  onDirty: (dirty: boolean) => void;
}) {
  const [owner, setOwner] = useState("");
  const [date, setDate] = useState(today);
  const [outcome, setOutcome] = useState<DecisionDetails["outcome"]>("selected");
  const [selected, setSelected] = useState("");
  const [considered, setConsidered] = useState<string[]>(() => project.alternatives.map(a => a.id));
  const [rationale, setRationale] = useState("");
  const [assumptions, setAssumptions] = useState("");
  const [triggers, setTriggers] = useState("");
  const [contexts, setContexts] = useState<Context[]>(() => [{ method: project.analysis.method, weight_profile_id: project.analysis.weight_profile_id, scenario_id: project.analysis.scenario_id }]);
  const [supporting, setSupporting] = useState<Loaded[]>([]);
  const [predecessor, setPredecessor] = useState<Loaded | null>(null);
  const [candidate, setCandidate] = useState<{ key: string; record: DecisionRecordV2 } | null>(null);
  const [exportedKey, setExportedKey] = useState<string | null>(null);
  const [failure, setFailure] = useState<{ key: string; message: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [opened, setOpened] = useState<Loaded | null>(null);
  const [openedPredecessor, setOpenedPredecessor] = useState<Loaded | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  const details: DecisionDetails = {
    owner: owner.trim(), date, outcome, selected_alternative_id: outcome === "selected" && selected ? selected : null,
    alternatives_considered: considered, rationale: rationale.trim(),
    // The saved parameters apply only to the saved method, as in the method comparison.
    configurations: contexts.map(c => ({ ...c, parameters: c.method === project.analysis.method ? project.analysis.parameters : {} })),
    unresolved_assumptions: lines(assumptions), review_triggers: lines(triggers),
  };
  const artifacts = supporting.filter(f => isArtifact(f.value)).map(f => ({
    artifact: f.value,
    // Pair by exact fingerprint for the request only; Python verifies the receipt itself.
    copy_receipt: supporting.find(r => isReceipt(r.value) && field(r.value, "original_fingerprint") === field(f.value, "compiled_fingerprint"))?.value ?? null,
  }));
  const unpaired = supporting.filter(f => !isArtifact(f.value) && !artifacts.some(a => a.copy_receipt === f.value));
  const ready = Boolean(details.owner && details.rationale && considered.length > 0 && (outcome === "deferred" || selected) && unpaired.length === 0);
  const key = canonical({ fingerprint, details, artifacts, predecessor: predecessor?.value ?? null });
  const liveKey = useRef(key);
  useLayoutEffect(() => { liveKey.current = key; }, [key]);
  const record = candidate?.key === key ? candidate.record : null;
  const dirty = record !== null && exportedKey !== key;
  useEffect(() => { onDirty(dirty); }, [dirty, onDirty]);

  const preview = async () => {
    if (!ready || busy) return;
    const captured = key;
    setFailure(null); setBusy(true);
    try {
      const result = await api.previewDecision(project, details, artifacts, predecessor?.value ?? null);
      if (liveKey.current !== captured) return;
      if (result.project_fingerprint !== fingerprint || result.previous_digest !== (field(predecessor?.value, "digest") ?? null)) throw Error("Decision record does not match the current project or predecessor.");
      setCandidate({ key: captured, record: result });
    } catch (e) { if (liveKey.current === captured) setFailure({ key: captured, message: message(e) }); }
    finally { setBusy(false); }
  };

  const openKey = canonical({ fingerprint, record: opened?.value ?? null, predecessor: openedPredecessor?.value ?? null });
  const load = useCallback(async (signal: AbortSignal) => {
    const result = await api.inspectDecision(project, opened?.value, openedPredecessor?.value ?? null, signal);
    if (result.record.digest !== field(opened?.value, "digest")) throw Error("Opened record does not match the selected file.");
    return result;
  }, [project, opened, openedPredecessor]);
  const inspection = useAnalysisRequest(openKey, opened !== null, load);

  const revise = (source: Loaded, verified: AnyRecord) => {
    if (verified.version === 2) {
      const d = verified.decision;
      setOwner(d.owner); setOutcome(d.outcome); setSelected(d.selected_alternative_id ?? ""); setConsidered(d.alternatives_considered);
      setRationale(d.rationale); setAssumptions(d.unresolved_assumptions.join("\n")); setTriggers(d.review_triggers.join("\n"));
      setContexts(d.configurations.map(c => ({ method: c.method, weight_profile_id: c.weight_profile_id, scenario_id: c.scenario_id })));
      setSupporting(verified.supporting_artifacts.flatMap((a, k) => [{ name: `artifact ${String(k + 1)}`, value: a.artifact },
        ...(a.copy_receipt ? [{ name: `receipt ${String(k + 1)}`, value: a.copy_receipt as unknown }] : [])]));
    } else {
      const d = verified.decision;
      setOwner(d.owner); setOutcome("selected"); setSelected(d.chosen_alternative_id); setConsidered(project.alternatives.map(a => a.id));
      setRationale(d.rationale); setAssumptions(d.unresolved_assumptions.join("\n")); setTriggers(d.review_triggers.join("\n"));
      setContexts(d.configurations.map(c => ({ method: c.method, weight_profile_id: c.weight_profile_id, scenario_id: c.scenario_id })));
    }
    setDate(today()); setPredecessor(source);
  };

  const methodOptions = methods?.length ? methods : [{ name: project.analysis.method, label: project.analysis.method }];
  // Stay mounted to keep the draft, but render no controls on other tabs: their generic labels
  // (method, scenario, profile) must never shadow the editor's own controls.
  if (!active) return null;
  return <section className="panel" aria-label="Decision records">
    <h2>Decision records</h2>
    <p>Record who decided what, on which analyses and evidence. Python snapshots the exact project, the selected analyses and the cited artifacts. Records are exported as files and never replaced: a revision is a new record linked to its predecessor. Nothing is saved in the project library.</p>
    {fileError && <p role="alert">{fileError}</p>}
    <form aria-label="Decision details" onSubmit={e => { e.preventDefault(); void preview(); }}>
      {predecessor && <p role="status">Revising {predecessor.name}. The earlier record is not changed. <button type="button" onClick={() => setPredecessor(null)}>Record as a new decision instead</button></p>}
      <label>Decision owner<input value={owner} onChange={e => setOwner(e.target.value)}/></label>
      <label>Decision date<input type="date" value={date} onChange={e => setDate(e.target.value)}/></label>
      <label>Outcome<select value={outcome} onChange={e => setOutcome(e.target.value as typeof outcome)}>
        <option value="selected">Select an alternative</option><option value="deferred">Defer the decision</option>
      </select></label>
      {outcome === "selected" && <label>Selected alternative<select value={selected} onChange={e => setSelected(e.target.value)}>
        <option value="">Choose…</option>
        {project.alternatives.filter(a => considered.includes(a.id)).map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
      </select></label>}
      <fieldset><legend>Alternatives considered</legend>
        <p>A declaration only: every recorded analysis still uses all {project.alternatives.length} project alternatives.</p>
        {project.alternatives.map(a => <label key={a.id}><input type="checkbox" checked={considered.includes(a.id)}
          onChange={e => {
            setConsidered(e.target.checked ? project.alternatives.map(x => x.id).filter(id => id === a.id || considered.includes(id)) : considered.filter(id => id !== a.id));
            if (!e.target.checked && selected === a.id) setSelected("");
          }}/>{a.name}</label>)}
      </fieldset>
      <label>Rationale<textarea value={rationale} onChange={e => setRationale(e.target.value)}/></label>
      <label>Unresolved assumptions (one per line)<textarea value={assumptions} onChange={e => setAssumptions(e.target.value)}/></label>
      <label>Review triggers (one per line)<textarea value={triggers} onChange={e => setTriggers(e.target.value)}/></label>
      <fieldset><legend>Analyses to record (at most {MAX_ANALYSES})</legend>
        {contexts.map((c, k) => <div key={k} role="group" aria-label={`Analysis ${String(k + 1)}`}>
          <label>Analysis {k + 1} method<select value={c.method} onChange={e => setContexts(contexts.map((x, j) => j === k ? { ...x, method: e.target.value } : x))}>
            {methodOptions.map(m => <option key={m.name} value={m.name}>{m.label}</option>)}
          </select></label>
          <label>Analysis {k + 1} weight profile<select value={c.weight_profile_id ?? ""} onChange={e => setContexts(contexts.map((x, j) => j === k ? { ...x, weight_profile_id: e.target.value || null } : x))}>
            <option value="">Scenario's or first profile</option>
            {project.weight_profiles.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select></label>
          <label>Analysis {k + 1} scenario<select value={c.scenario_id ?? ""} onChange={e => setContexts(contexts.map((x, j) => j === k ? { ...x, scenario_id: e.target.value || null } : x))}>
            <option value="">Base model</option>
            {project.scenarios.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select></label>
          {contexts.length > 1 && <button type="button" onClick={() => setContexts(contexts.filter((_, j) => j !== k))}>Remove analysis {k + 1}</button>}
        </div>)}
        {contexts.length < MAX_ANALYSES && <button type="button" onClick={() => setContexts([...contexts, { method: project.analysis.method, weight_profile_id: null, scenario_id: null }])}>Add analysis</button>}
      </fieldset>
      <label>Supporting bundles and copy receipts
        <input type="file" multiple accept=".json,application/json" onChange={event => {
          setFileError(null);
          void readFiles(event.target.files).then(setSupporting).catch((e: unknown) => { setSupporting([]); setFileError(message(e)); });
        }}/>
      </label>
      {supporting.length > 0 && <ul aria-label="Supporting files">{supporting.map(f => <li key={f.name}>{f.name}: {isArtifact(f.value) ? (artifacts.find(a => a.artifact === f.value)?.copy_receipt ? "bundle with copy receipt" : "bundle") : isReceipt(f.value) ? (unpaired.includes(f) ? "copy receipt matching no selected bundle" : "copy receipt") : "not a bundle or copy receipt"}</li>)}</ul>}
      {unpaired.length > 0 && <p role="alert">Remove files that are not a compilation bundle or a receipt for one of the selected bundles.</p>}
      <button type="submit" disabled={!ready || busy}>Preview decision record</button>
    </form>
    {failure?.key === key && <p role="alert">{failure.message}</p>}
    {record && <section aria-label="Decision record preview">
      <h3>Decision record preview</h3>
      <DecisionRecordView record={record} label="Previewed record"/>
      <button type="button" onClick={() => {
        saveDownload(new Blob([JSON.stringify(record, null, 2) + "\n"], { type: "application/json" }), `decision-record-${record.digest.slice(0, 12)}.json`);
        setExportedKey(key);
      }}>Export decision record</button>
      {dirty && <p role="status">This record has not been exported. Export it to keep it; previews are not saved.</p>}
    </section>}
    <h3>Open a decision record</h3>
    <label>Decision record file<input type="file" accept=".json,application/json" onChange={event => {
      setFileError(null); setOpened(null);
      void readFiles(event.target.files).then(files => setOpened(files[0] ?? null)).catch((e: unknown) => setFileError(message(e)));
    }}/></label>
    <label>Its predecessor record (optional)<input type="file" accept=".json,application/json" onChange={event => {
      setFileError(null); setOpenedPredecessor(null);
      void readFiles(event.target.files).then(files => setOpenedPredecessor(files[0] ?? null)).catch((e: unknown) => setFileError(message(e)));
    }}/></label>
    {opened && inspection.status === "loading" && <p role="status">Verifying record…</p>}
    {inspection.status === "error" && <><p role="alert">{inspection.message}</p><button type="button" onClick={inspection.retry}>Retry verification</button></>}
    {opened && inspection.status === "ready" && <section aria-label="Opened decision record">
      <p role="status">Verified in Python: the digest matches{inspection.result.record.version === 2 ? ", the cited artifacts verify and the anchors, measurement provenance, feasibility and notices reproduce" : ""}. {inspection.result.current_project_matches ? "It records exactly the current project." : "It records a different project revision; it is shown historically."}{inspection.result.predecessor_verified === true ? " The selected predecessor is the record it revises." : ""}</p>
      <DecisionRecordView record={inspection.result.record} label="Opened record"/>
      <button type="button" onClick={() => revise(opened, inspection.result.record)}>Revise this record</button>
    </section>}
  </section>;
}
