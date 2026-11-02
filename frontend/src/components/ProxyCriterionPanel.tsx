import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { ExternalProposals, Project, ProxyComparisonBundle, ProxyInputs, ProxyInspection, ProxyOperation, ProxyPlanState } from "../api/types";
import { canonical, type AnalysisContext } from "../state/analysisContext";
import { ExternalProposalsPanel } from "./ExternalProposalsPanel";
import { saveDownload } from "./results/downloads";
import { FeasibilityView, StatusBadge } from "./results/FeasibilityView";

const download = (value: unknown, name: string) => saveDownload(new Blob([JSON.stringify(value, null, 2) + "\n"], { type: "application/json" }), name);
const errorText = (error: unknown) => error instanceof ApiError ? [error.message, ...error.details.map(i => i.message)].join(" ") : error instanceof Error ? error.message : String(error);

/** A retained, off-by-default local workspace. Every analysis runs both copies on the server. */
export function ProxyCriterionPanel({ project, context, onDirty, onInputs }: {
  project: Project; context: AnalysisContext; onDirty: (dirty: boolean) => void; onInputs?: (inputs: ProxyInputs | null) => void;
}) {
  const [inputs, setInputs] = useState<ProxyInputs | null>(null);
  const [text, setText] = useState("");
  const [declarationPending, setDeclarationPending] = useState(false);
  const [inspection, setInspection] = useState<{ key: string; result: ProxyInspection } | null>(null);
  const [pair, setPair] = useState<{ key: string; result: ProxyComparisonBundle } | null>(null);
  const [history, setHistory] = useState<ProxyComparisonBundle | null>(null);
  const [reviewer, setReviewer] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [scoreDirty, setScoreDirty] = useState(false);
  const [scores, setScores] = useState<ExternalProposals | null>(null);
  const [acks, setAcks] = useState<string[]>([]);
  const [cardId, setCardId] = useState("");
  const [sourceId, setSourceId] = useState("");
  const inspectionKey = canonical({ inputs, fingerprint: context.fingerprint, configuration: context.configuration });
  const key = canonical({ inputs, fingerprint: context.fingerprint, configuration: context.configuration, text, reviewer, note, scores, cardId, sourceId });
  const [epoch, setEpoch] = useState({ key, generation: 0 });
  if (epoch.key !== key) setEpoch({ key, generation: epoch.generation + 1 });
  const candidateKey = canonical({ key, generation: epoch.generation });
  const live = useRef(candidateKey);
  useLayoutEffect(() => { live.current = candidateKey; }, [candidateKey]);
  useEffect(() => { onDirty(dirty || scoreDirty); }, [dirty, scoreDirty, onDirty]);
  useEffect(() => { onInputs?.(inputs); }, [inputs, onInputs]);
  const preview = inspection?.key === inspectionKey ? inspection.result : null;
  const completed = pair?.key === candidateKey ? pair.result : null;
  const currentInputs = (value: ProxyInputs): ProxyInputs => ({ ...value, project, configuration: context.configuration });
  const reviewed = () => ({ status: "accepted" as const, reviewer, reviewed_at: new Date().toISOString(), corrected_value: null, note });
  const canReview = reviewer.trim() !== "" && note.trim() !== "";
  const cards = { ...scores?.intake.model_cards };
  const sources = { ...scores?.intake.sources };
  scores?.registry_supplies.forEach(s => { Object.assign(cards, s.model_cards); Object.assign(sources, s.sources); });
  async function act(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError(null);
    try { await action(); } catch (e: unknown) { setError(errorText(e)); } finally { setBusy(false); }
  }
  async function revise(kind: ProxyOperation["kind"], extras: Partial<ProxyOperation> = {}) {
    if (!inputs || !canReview) return;
    const captured = candidateKey;
    const plan = await api.reviseProxy(inputs.plan, { kind, review: reviewed(), ...extras });
    if (captured !== live.current) return;
    setInputs(currentInputs({ ...inputs, plan })); setDirty(true); setAcks([]);
  }
  async function inspect() {
    if (!inputs) return;
    const captured = candidateKey;
    const result = await api.inspectProxy(currentInputs(inputs));
    if (captured === live.current) setInspection({ key: inspectionKey, result });
  }
  function begin() {
    const state: ProxyPlanState = {
      project_fingerprint: context.fingerprint,
      criterion: { id: "disclosed_proxy_score", name: "Disclosed model proxy: reviewed external score", parent_id: null, order: project.criteria.length,
        description: "Optional disclosed input in a separate copy", scale: { type: "interval", unit: null, lower: 0, upper: 1, anchor_mode: "fixed", labels: [] }, value_function: { kind: "linear", direction: "increasing", out_of_domain: "error" } },
      score_meaning: "State the external score's declared meaning and unit", compared_profile_ids: project.weight_profiles.map(p => p.id),
      swing_ratings: Object.fromEntries(project.weight_profiles.map(p => [p.id, null])), card_id: null, card_digest: null,
      card_facts: {}, licence_compatible: null, licence_review: null, features: [], overlaps: [], score_workspace_digest: null, enabled: false, plan_review: null,
    };
    setText(JSON.stringify(state, null, 2)); setDeclarationPending(true); setDirty(true);
  }
  async function applyDeclaration() {
    const state = JSON.parse(text) as ProxyPlanState;
    const captured = candidateKey;
    const plan = inputs ? await api.reviseProxy(inputs.plan, { kind: "edit", state, review: reviewed() }) : await api.startProxy(state);
    if (captured !== live.current) return;
    setInputs({ project, plan, configuration: context.configuration, scores: inputs?.scores ?? null, model: inputs?.model ?? null, uncertainty: inputs?.uncertainty ?? null, factor_parameters: inputs?.factor_parameters ?? null });
    setDirty(true); setAcks([]); setDeclarationPending(false);
  }
  async function open(file: File | undefined, kind: "inputs" | "bundle") {
    if (!file || dirty || scoreDirty) return;
    const captured = candidateKey;
    if (file.size > 8_000_000) throw Error("Proxy document exceeds 8 MB.");
    const value: unknown = JSON.parse(await file.text());
    if (kind === "bundle") {
      const result = await api.verifyProxy(value);
      if (captured === live.current) setHistory(result);
    } else {
      const candidate = value as ProxyInputs;
      const result = await api.inspectProxy(candidate);
      if (captured === live.current) {
        setInputs(result.inputs); setText(JSON.stringify(result.state, null, 2)); setScores(result.inputs.scores ?? null); setAcks([]); setDeclarationPending(false);
      }
    }
  }
  const canRun = Boolean(preview && !declarationPending && preview.state.enabled && !preview.issues.length && canReview
    && ["card", "overlap", "weight_changes", ...(preview.unknown_facts.length ? ["unknown_facts"] : [])].every(a => acks.includes(candidateKey + a)));
  return <section className="panel" aria-label="Disclosed model proxy comparison">
    <h2>Optional disclosed model proxy</h2>
    <p>The original project is the without-proxy baseline. Enabling creates a separate preview. The imported score is a fixed reviewed input, with its declared meaning; engine preference values are not outcome probabilities.</p>
    <p>PROMETHEE II and AHP are unavailable for this paired comparison. Their ordinary comparison remains separate.</p>
    {!inputs && <button type="button" disabled={busy || text !== ""} onClick={begin}>Prepare an optional proxy declaration</button>}
    <label>Open proxy inputs<input type="file" accept=".json" disabled={busy || dirty || scoreDirty} onChange={e => { void act(() => open(e.target.files?.[0], "inputs")); }}/></label>
    <label>Reopen complete pair<input type="file" accept=".json" disabled={busy || dirty || scoreDirty} onChange={e => { void act(() => open(e.target.files?.[0], "bundle")); }}/></label>
    {(text || inputs) && <>
      <label>Proxy declaration JSON<textarea rows={16} value={text} onChange={e => { setText(e.target.value); setDeclarationPending(true); setDirty(true); }}/></label>
      <p className="small">State a fixed numeric scale, meaning, chosen parent, profile IDs, explicit swing ratings, model-card facts, feature lineage and overlap resolutions. Missing ratings stay empty. Editing clears reviews and disables the plan.</p>
      <label>Proxy reviewer<input value={reviewer} onChange={e => setReviewer(e.target.value)}/></label>
      <label>Proxy review reason<textarea value={note} onChange={e => setNote(e.target.value)}/></label>
      <button type="button" disabled={busy || !text || Boolean(inputs && !canReview)} onClick={() => { void act(applyDeclaration); }}>{inputs ? "Record declaration edit and clear reviews" : "Create disabled proxy plan"}</button>
    </>}
    {declarationPending && <p role="status">Declaration edits are pending. Record the edit and review the new inputs before a paired run.</p>}
    {inputs && <>
      <button type="button" disabled={busy} onClick={() => { void act(inspect); }}>Inspect both proxy copies</button>
      <button type="button" disabled={busy} onClick={() => { download(currentInputs(inputs), "proxy-inputs.json"); setDirty(false); }}>Export proxy inputs and history</button>
      <button type="button" disabled={busy || scoreDirty} onClick={() => { setInputs(null); setText(""); setDeclarationPending(false); setScores(null); setDirty(false); setAcks([]); setHistory(null); }}>Discard proxy workspace</button>
    </>}
    {preview && <>
      <p role="status">Proxy {preview.state.enabled ? "enabled for separate paired analysis" : "disabled"}. {preview.state.score_meaning}</p>
      {preview.issues.length > 0 && <ul>{preview.issues.map((i,n) => <li key={n}>{i.code}: {i.message}</li>)}</ul>}
      <h3>Model-card disclosure</h3>
      {preview.model_card && <pre>{JSON.stringify(preview.model_card, null, 2)}</pre>}
      {Object.entries(preview.state.card_facts).map(([id,fact]) => <div key={id}><strong>{id}</strong>: {fact.value} {fact.unknown && ` — explicitly unknown: ${fact.reason}`} · {fact.review?.status ?? "unreviewed"}
        <button type="button" disabled={busy || !canReview} onClick={() => { void act(() => revise("review_card_fact", { id })); }}>Review card fact {id}</button></div>)}
      <h3>Declared feature overlap</h3>
      {preview.overlap_findings.map((f,i) => <p key={i}>{f}</p>)}
      {preview.state.features.map(f => <div key={f.id}>{f.description} · {f.observed_at} · sources {f.source_ids.join(", ")} · {f.review?.status ?? "unreviewed"}
        <button type="button" disabled={busy || !canReview} onClick={() => { void act(() => revise("review_feature", { id: f.id })); }}>Review feature {f.id}</button></div>)}
      {preview.state.overlaps.map(o => <div key={o.feature_id}>{o.relation} · {o.resolution} · {o.rationale} · {o.review?.status ?? "unreviewed"}
        <button type="button" disabled={busy || !canReview} onClick={() => { void act(() => revise("review_overlap", { id: o.feature_id })); }}>Review overlap {o.feature_id}</button></div>)}
      <button type="button" disabled={busy || !canReview} onClick={() => { void act(() => revise("review_licence", { licence_compatible: true })); }}>Review licence and restrictions as compatible</button>
      <button type="button" disabled={busy || !canReview} onClick={() => { void act(() => revise("review_licence", { licence_compatible: false })); }}>Record licence as incompatible</button>
      <h3>Before and after normalized weight shares</h3>
      {Object.entries(preview.weight_shares).map(([profile,shares]) => <div key={profile}><h4>{profile}</h4><table><thead><tr><th>Criterion</th><th>Without disclosed proxy</th><th>With disclosed proxy</th></tr></thead><tbody>
        {[...new Set([...Object.keys(shares.before ?? {}),...Object.keys(shares.after ?? {})])].map(id => <tr key={id}><th>{id}</th><td>{shares.before?.[id] ?? "absent"}</td><td>{shares.after?.[id] ?? "absent"}</td></tr>)}
      </tbody></table></div>)}
      {preview.calculation && <details><summary>Score identity formulas and reviews</summary><pre>{JSON.stringify(preview.calculation.preview.model, null, 2)}</pre></details>}
      <button type="button" disabled={busy || !canReview} onClick={() => { void act(() => revise("review_plan")); }}>Review complete proxy plan</button>
      <label><input type="checkbox" checked={preview.state.enabled} disabled={busy || !canReview} onChange={e => { void act(() => revise("set_enabled", { enabled: e.target.checked })); }}/>Enable separate proxy preview</label>
      {["card", "overlap", "weight_changes", ...(preview.unknown_facts.length ? ["unknown_facts"] : [])].map(ack => <label key={ack}><input type="checkbox" checked={acks.includes(candidateKey+ack)} onChange={e => setAcks(previous => e.target.checked ? [...previous,candidateKey+ack] : previous.filter(a => a !== candidateKey+ack))}/>I acknowledge {ack.replaceAll("_", " ")}</label>)}
      <button type="button" disabled={busy || !canRun} onClick={() => { if (inputs) void act(async () => {
        const captured = candidateKey;
        const result = await api.runProxy({ ...currentInputs(inputs), expected_review_digest: preview.review_digest,
          acknowledgements: { card: true, overlap: true, weight_changes: true, unknown_facts: acks.includes(candidateKey+"unknown_facts") }, review: reviewed() });
        if (captured === live.current) { setPair({ key: captured, result }); setDirty(true); }
      }); }}>Run with and without disclosed proxy</button>
      {preview.limitations.map((l,i) => <p className="muted small" key={i}>{l}</p>)}
    </>}
      {inputs && inspection?.result.score_draft && inspection.result.score_draft_fingerprint && <>
        <h3>Review fixed numeric scores against this separate draft</h3>
        <button type="button" onClick={() => download(inspection.result.score_draft, "proxy-score-review-draft.json")}>Export score review draft</button>
        <ExternalProposalsPanel key={inspection.result.score_draft_fingerprint} project={inspection.result.score_draft} fingerprint={inspection.result.score_draft_fingerprint} onDirty={setScoreDirty} onWorkspace={setScores}/>
        <label>Declared score model card<select value={cardId} onChange={e => setCardId(e.target.value)}><option value="">Choose a model card</option>{Object.keys(cards).map(id => <option key={id}>{id}</option>)}</select></label>
        <label>Card fact source<select value={sourceId} onChange={e => setSourceId(e.target.value)}><option value="">Choose a source</option>{Object.keys(sources).map(id => <option key={id}>{id}</option>)}</select></label>
        <button type="button" disabled={!scores || !cardId || !sourceId || busy} onClick={() => {
          const card = cards[cardId], proposal = scores?.intake.proposals.find(p => p.model_card_id === cardId);
          if (!card || !proposal) return;
          const facts = { purpose: card.purpose, model_version: card.model_version, ...card.details };
          setText(JSON.stringify({ ...inspection.result.state, card_id: cardId, card_digest: proposal.model_card_digest,
            card_facts: Object.fromEntries(Object.entries(facts).filter(([id]) => id !== "limitations").map(([id,value]) => [id,{ value, unknown: false, reason: "", source_ids: [sourceId], review: null }])) }, null, 2)); setDeclarationPending(true); setDirty(true);
        }}>Copy declared card facts for explicit review</button>
        <button type="button" disabled={busy || !scores || !canReview || !preview} onClick={() => { if (scores) void act(async () => {
          const captured = candidateKey;
          const plan = await api.reviseProxy(inputs.plan, { kind: "bind_scores", workspace_digest: scores.digest, review: reviewed() });
          if (captured === live.current) { setInputs(currentInputs({ ...inputs, plan, scores })); setDirty(true); setAcks([]); }
        }); }}>Bind this reviewed score workspace</button>
      </>}

    {completed && <PairView bundle={completed} onExport={() => { download(completed, "proxy-comparison.json"); setDirty(false); }}/>} 
    {history && <><h3>Verified historical pair</h3><p>This retained pair uses its original project and configuration.</p><PairView bundle={history}/></>}
    {busy && <p role="status">Checking proxy inputs…</p>}{error && <p role="alert">{error}</p>}
  </section>;
}

function PairView({ bundle, onExport }: { bundle: ProxyComparisonBundle; onExport?: () => void }) {
  const halves = [bundle.without_proxy, bundle.with_proxy];
  return <section aria-label="Complete proxy pair"><h3>Pair {bundle.status}</h3>
    <div className="proxy-pair">{halves.map((half,i) => <section key={i}><h4>{i ? "With disclosed proxy" : "Without disclosed proxy"}</h4>
      <p>{half.status}: {half.reason}</p>
      {half.result && <div className="table-scroll" tabIndex={0}><table aria-label={i ? "With disclosed proxy ranking" : "Without disclosed proxy ranking"}><thead><tr><th>Alternative</th><th>Rank</th><th>Preference value</th><th>Class</th><th>Feasibility</th></tr></thead><tbody>{[...half.result.ranking].sort((a,b) => bundle.request.project.alternatives.findIndex(x => x.id === a.alternative_id) - bundle.request.project.alternatives.findIndex(x => x.id === b.alternative_id)).map(row => <tr key={row.alternative_id}><th>{row.name}</th><td>{row.rank}</td><td>{row.value}<meter min={0} max={1} value={row.value}/></td><td>{half.result?.method === "mavt_sorting" ? half.result.assignments.find(a => a.alternative_id === row.alternative_id)?.class_id : "—"}</td><td>{half.feasibility ? <StatusBadge result={half.feasibility} alternativeId={row.alternative_id}/> : "No requirements"}</td></tr>)}</tbody></table></div>}
      {half.factor_run && <details><summary>Fixed-weight factor acceptability and coupling</summary><p>{half.coupling_draws} shared draws · {half.coupling_digest}</p><pre>{JSON.stringify(half.factor_run.result.acceptability, null, 2)}</pre></details>}
      {half.feasibility && <details><summary>Feasibility beside this result</summary><FeasibilityView result={half.feasibility}/></details>}
      <button type="button" onClick={() => download(half.project, i ? "with-proxy-project.json" : "without-proxy-project.json")}>Export {i ? "with" : "without"} proxy copy</button>
    </section>)}</div>
    {onExport && <button type="button" onClick={onExport}>Export complete proxy pair</button>}
  </section>;
}
