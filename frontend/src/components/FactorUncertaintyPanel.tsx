import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { AnalysisConfiguration, DecisionDetails, FactorRunParameters, FactorRunRecord, FactorUncertaintyModel, Project } from "../api/types";
import { canonical } from "../state/analysisContext";
import { useAnalysisRequest } from "../state/useAnalysisRequest";
import { download } from "./CalculationWorkspaceView";

const RUN_LABELS = { mavt: "MAVT draws", mavt_sorting: "Value-based sorting draws", smaa2_factors: "SMAA-2 with fundamental factors" };
const FEASIBILITY_LABELS = { checked: "Checked", no_requirements: "No requirements stated", unavailable: "Unavailable" };

type Marginal = FactorUncertaintyModel["distributions"][number]["distribution"];
const errorText = (error: unknown) => error instanceof ApiError ? [error.message, ...error.details.map(d => d.message)].join(" ") : error instanceof Error ? error.message : String(error);

/** A minimal local editor. Python validates distributions, dependence and every calculation. */
export function FactorUncertaintyPanel({ project, fingerprint, document, onDirty, configuration = project.analysis }: {
  project: Project; fingerprint: string; document: unknown; onDirty: (dirty: boolean) => void; configuration?: AnalysisConfiguration;
}) {
  const [specDirty, setSpecDirty] = useState(false);
  const [recordDirty, setRecordDirty] = useState(false);
  useEffect(() => { onDirty(specDirty || recordDirty); }, [specDirty, recordDirty, onDirty]);
  const [spec, setSpec] = useState<FactorUncertaintyModel | null>(null);
  const [factor, setFactor] = useState("");
  const [kind, setKind] = useState<Marginal["kind"]>("uniform");
  const [lower, setLower] = useState("");
  const [upper, setUpper] = useState("");
  const [mode, setMode] = useState("");
  const [atoms, setAtoms] = useState("[1, 2]");
  const [probabilities, setProbabilities] = useState("[0.5, 0.5]");
  const [group, setGroup] = useState("");
  const [members, setMembers] = useState("");
  const [rationale, setRationale] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [assumptions, setAssumptions] = useState<{ key: string; questions: FactorRunRecord["result"]["questions"]; issues: string[] } | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [run, setRun] = useState<FactorRunParameters["run"]>("smaa2_factors");
  const [evaluation, setEvaluation] = useState<FactorRunParameters["evaluation"]>("sampled");
  const [draws, setDraws] = useState("1000");
  const [seed, setSeed] = useState("7");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candidate, setCandidate] = useState<{ key: string; record: FactorRunRecord } | null>(null);
  const [historical, setHistorical] = useState<FactorRunRecord | null>(null);
  const [owner, setOwner] = useState("");
  const [reason, setReason] = useState("");
  const [selected, setSelected] = useState("");
  const [includeDecision, setIncludeDecision] = useState(false);
  const context = canonical({ project: fingerprint, document });
  const load = useCallback((signal: AbortSignal) => api.inspectCalculations(project, document, signal), [project, document]);
  const inspection = useAnalysisRequest(context, true, load);
  const model = inspection.status === "ready" ? inspection.result.model : null;
  const digest = inspection.status === "ready" ? inspection.result.preview.model_digest : null;
  const referenceConfiguration = { ...configuration, method: "mavt", parameters: {} };
  const key = canonical({ context, configuration: referenceConfiguration, spec, run, evaluation, draws, seed, accepted, reviewer, includeDecision, owner, reason, selected });
  const live = useRef(key);
  useLayoutEffect(() => { live.current = key; }, [key]);
  const fileSequence = useRef(0);
  const result = candidate?.key === key ? candidate.record : null;
  const bound = spec?.project_fingerprint === fingerprint && spec.model_digest === digest;
  const change = (next: FactorUncertaintyModel) => { setSpec(next); setAccepted(false); setHistorical(null); setSpecDirty(true); };
  const origin = () => ({ kind: "human" as const, proposed_by: reviewer.trim(), tool_id: null, tool_version: null });
  const reviewed = () => ({ status: "accepted" as const, reviewer: reviewer.trim(), reviewed_at: new Date().toISOString(), corrected_value: null, note: "Explicit acceptance of distribution or quantile coupling" });
  const currentSpec = () => {
    if (!spec) throw Error("Start or import a factor uncertainty sidecar first.");
    const review = reviewed();
    return { ...spec, distributions: spec.distributions.map(d => ({ ...d, review: d.review?.status === "accepted" ? d.review : review })), groups: spec.groups.map(g => ({ ...g, review: g.review?.status === "accepted" ? g.review : review })) };
  };
  const execute = async () => {
    if (!spec || !model || !bound || !accepted || !reviewer.trim() || busy || recordDirty) return;
    if (!draws.trim() || !seed.trim() || !Number.isSafeInteger(Number(seed))) { setError("Enter a draw count and a safe integer seed."); return; }
    const captured = key;
    setBusy(true); setError(null);
    try {
      const parameters: FactorRunParameters = { run, evaluation, draws: Number(draws), seed: Number(seed), confidence: 0.95,
        configuration: referenceConfiguration };
      const decision: DecisionDetails | null = includeDecision ? {
        owner: owner.trim(), date: new Date().toLocaleDateString("en-CA"), outcome: selected ? "selected" : "deferred", selected_alternative_id: selected || null,
        alternatives_considered: project.alternatives.map(a => a.id), rationale: reason.trim(),
        configurations: [referenceConfiguration], unresolved_assumptions: [], review_triggers: [],
      } : null;
      const prepared = await api.inspectFactorUncertainty(project, model, currentSpec());
      if (live.current !== captured) return;
      if (prepared.issues.some(i => i.severity === "error")) throw Error(prepared.issues.map(i => `${i.code}: ${i.message}`).join(" "));
      const record = await api.runFactorUncertainty(project, model, prepared.uncertainty, parameters, decision);
      if (live.current !== captured) return;
      if (record.result.project_fingerprint !== fingerprint || record.result.model_digest !== digest || record.result.uncertainty_digest !== prepared.uncertainty_digest || canonical(record.parameters) !== canonical(parameters)) throw Error("Factor run does not match the requested inputs.");
      setCandidate({ key: captured, record }); setHistorical(null); setRecordDirty(true);
    } catch (e) { if (live.current === captured) setError(errorText(e)); }
    finally { setBusy(false); }
  };
  const readFile = async (file: File | undefined, record: boolean) => {
    if (!file) return;
    const sequence = ++fileSequence.current;
    const captured = key;
    setError(null);
    if (file.size > 8_000_000) { setError("Factor file exceeds the 8 MB limit."); return; }
    try {
      const value: unknown = JSON.parse(await file.text());
      if (record) {
        const checked = await api.verifyFactorRun(value);
        if (sequence !== fileSequence.current || live.current !== captured) return;
        setHistorical(checked); setCandidate(null);
      } else {
        // Python is the authority at Run; importing never accepts the file anew.
        if (sequence !== fileSequence.current || live.current !== captured) return;
        if (typeof value !== "object" || value === null || !("model_digest" in value) || !("distributions" in value) || !Array.isArray(value.distributions) || !("groups" in value) || !Array.isArray(value.groups)) throw Error("Choose a factor uncertainty sidecar.");
        if (!model) throw Error("Open a calculation model first.");
        const checked = await api.inspectFactorUncertainty(project, model, value);
        if (sequence !== fileSequence.current || live.current !== captured) return;
        change(checked.uncertainty);
      }
    } catch (e) { if (sequence === fileSequence.current && live.current === captured) setError(errorText(e)); }
  };
  const shown = historical ?? result;
  return <details className="factor-uncertainty" aria-label="Fundamental-factor uncertainty"><summary>Fundamental-factor uncertainty</summary>
    <p>Separate factor-based runs use reviewed source distributions and fixed weights. No distribution is inferred from an evidence range. Export this sidecar and the completed run to retain them; Project Save does not store them.</p>
    {inspection.status === "error" && <p role="alert">{inspection.message}</p>}
    <button type="button" disabled={!model || model.project_fingerprint !== fingerprint || busy} onClick={() => { if (digest) change({ schema_version: 1, project_fingerprint: fingerprint, model_digest: digest, distributions: [], groups: [] }); }}>Start factor uncertainty sidecar</button>
    <label>Import factor uncertainty<input type="file" accept=".json" onChange={e => { void readFile(e.target.files?.[0], false); }}/></label>
    <label>Open factor run record<input type="file" accept=".json" onChange={e => { void readFile(e.target.files?.[0], true); }}/></label>
    {spec && <>
      {!bound && <p role="alert">This uncertainty sidecar belongs to another project or calculation revision. Export it to keep it; start a new sidecar for the current inputs. Nothing is rebound automatically.</p>}
      <button type="button" onClick={() => { download(spec, "factor-uncertainty-draft.json"); setSpecDirty(false); }}>Export factor uncertainty draft</button>
      <label>Distribution reviewer<input value={reviewer} onChange={e => { setReviewer(e.target.value); setAccepted(false); }}/></label>
      <form aria-label="Factor distribution" onSubmit={e => {
        e.preventDefault(); if (!factor || !reviewer.trim()) return;
        try {
          const distribution: Marginal = kind === "uniform" ? { kind, lower: Number(lower), upper: Number(upper) } : kind === "triangular" ? { kind, lower: Number(lower), mode: Number(mode), upper: Number(upper) } : { kind, values: JSON.parse(atoms) as number[], probabilities: JSON.parse(probabilities) as number[] };
          change({ ...spec, distributions: [...spec.distributions.filter(d => d.factor_id !== factor), { factor_id: factor, distribution, origin: origin(), review: null }] });
          setError(null);
        } catch { setError("Enter numeric arrays for discrete values and probabilities."); }
      }}>
        <label>Source factor<select required value={factor} onChange={e => setFactor(e.target.value)}><option value="">Choose a factor</option>{model?.sources.map(s => <option key={s.id} value={s.id}>{s.id} ({s.unit})</option>)}</select></label>
        <label>Distribution kind<select value={kind} onChange={e => setKind(e.target.value as Marginal["kind"])}><option value="uniform">Uniform</option><option value="triangular">Triangular</option><option value="discrete">Discrete</option></select></label>
        {kind === "discrete" ? <><label>Discrete values<textarea value={atoms} onChange={e => setAtoms(e.target.value)}/></label><label>Probabilities<textarea value={probabilities} onChange={e => setProbabilities(e.target.value)}/></label></> : <>
          <label>Lower bound<input required type="number" step="any" value={lower} onChange={e => setLower(e.target.value)}/></label>
          {kind === "triangular" && <label>Mode<input required type="number" step="any" value={mode} onChange={e => setMode(e.target.value)}/></label>}
          <label>Upper bound<input required type="number" step="any" value={upper} onChange={e => setUpper(e.target.value)}/></label>
        </>}
        <button type="submit" disabled={!bound || busy || !reviewer.trim()}>Set pending distribution</button>
      </form>
      <ul>{spec.distributions.map(d => <li key={d.factor_id}>{d.factor_id}: {JSON.stringify(d.distribution)} ({d.review?.status ?? "pending"}) <button type="button" disabled={!bound || busy} onClick={() => change({ ...spec, distributions: spec.distributions.filter(s => s.factor_id !== d.factor_id) })}>Hold {d.factor_id} deterministic</button></li>)}</ul>
      <form aria-label="Shared quantile group" onSubmit={e => { e.preventDefault(); if (reviewer.trim()) change({ ...spec, groups: [...spec.groups.filter(g => g.id !== group), { id: group, factor_ids: members.split(",").map(s => s.trim()), rationale, origin: origin(), review: null }] }); }}>
        <label>Quantile group ID<input required value={group} onChange={e => setGroup(e.target.value)}/></label>
        <label>Factor IDs (comma separated)<input required value={members} onChange={e => setMembers(e.target.value)}/></label>
        <label>Coupling rationale<input required value={rationale} onChange={e => setRationale(e.target.value)}/></label>
        <button type="submit" disabled={!bound || busy || !reviewer.trim()}>Set pending quantile group</button>
      </form>
      <p>Reusing a factor already shares its draw. A group declares perfectly shared quantiles for distinct factors; arbitrary correlation is unsupported.</p>
      <ul>{spec.groups.map(g => <li key={g.id}>{g.id}: {g.factor_ids.join(", ")} ({g.review?.status ?? "pending"}) <button type="button" disabled={!bound || busy} onClick={() => change({ ...spec, groups: spec.groups.filter(s => s.id !== g.id) })}>Remove group {g.id}</button></li>)}</ul>
      <label><input type="checkbox" checked={accepted} disabled={!reviewer.trim() || !bound} onChange={e => { if (e.target.checked) { setSpec(currentSpec()); setSpecDirty(true); } setAccepted(e.target.checked); }}/>I accept these distributions and dependence assumptions</label>
      <button type="button" disabled={!reviewer.trim() || !accepted || !bound} onClick={() => { download(currentSpec(), "factor-uncertainty.json"); setSpecDirty(false); }}>Export reviewed factor uncertainty</button>
      <label>Factor run<select value={run} onChange={e => setRun(e.target.value as FactorRunParameters["run"])}><option value="mavt">MAVT draws</option><option value="mavt_sorting">Value-based sorting draws</option><option value="smaa2_factors">SMAA-2 with fundamental factors</option></select></label>
      <label>Evaluation<select value={evaluation} onChange={e => setEvaluation(e.target.value as FactorRunParameters["evaluation"])}><option value="sampled">Seeded sampling</option><option value="exact_enumeration">Exact discrete enumeration</option></select></label>
      <label>Draw count<input type="number" min="1" max="100000" value={draws} onChange={e => setDraws(e.target.value)}/></label>
      <label>Seed<input type="number" min="0" value={seed} onChange={e => setSeed(e.target.value)}/></label>
      <label><input type="checkbox" checked={includeDecision} onChange={e => setIncludeDecision(e.target.checked)}/>Include a decision snapshot with this run</label>
      {includeDecision && <><label>Factor decision owner<input value={owner} onChange={e => setOwner(e.target.value)}/></label><label>Factor decision rationale<textarea value={reason} onChange={e => setReason(e.target.value)}/></label><label>Factor decision selection<select value={selected} onChange={e => setSelected(e.target.value)}><option value="">Defer</option>{project.alternatives.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label></>}
      <button type="button" disabled={busy || recordDirty || !bound || !accepted || !reviewer.trim() || (includeDecision && (!owner.trim() || !reason.trim()))} onClick={() => { void execute(); }}>Run factor uncertainty</button>
    </>}
    {spec && model && <button type="button" onClick={() => {
      const captured = key;
      void api.inspectFactorUncertainty(project, model, spec).then(checked => {
        if (live.current === captured) setAssumptions({ key: captured, questions: checked.questions, issues: checked.issues.map(i => `${i.code}: ${i.message}`) });
      }).catch((e: unknown) => { if (live.current === captured) setError(errorText(e)); });
    }}>Inspect factor assumptions</button>}
    {assumptions?.key === key && <section aria-label="Factor assumptions to review"><ul>{assumptions.questions.map((q, i) => <li key={i}>{q.question} {q.why} {q.evidence}</li>)}</ul>{assumptions.issues.map((s, i) => <p key={i}>{s}</p>)}</section>}
    {busy && <p role="status">Evaluating factor draws…</p>}
    {error && <p role="alert">{error}</p>}
    {recordDirty && candidate && candidate.key !== key && <p>A completed run belongs to earlier inputs. <button type="button" onClick={() => { download(candidate.record, "previous-factor-run.json"); setRecordDirty(false); }}>Export previous factor run</button></p>}
    {shown && <section aria-label="Completed factor run">
      {historical && <p>Verified historical snapshot. {shown.result.project_fingerprint === fingerprint ? "Its source matches the open project." : "Its source differs from the open project."}</p>}
      <p>{RUN_LABELS[shown.result.run]}: {shown.result.evaluation}, {shown.result.draw_count} {shown.result.evaluation === "sampled" ? `draws, seed ${shown.result.seed}` : "joint outcomes; no sampling, seed unused"}.</p>
      <p>Reference profile: {shown.source_project.weight_profiles.find(p => p.id === shown.result.reference.weight_profile_id)?.name ?? shown.result.reference.weight_profile_id}; scenario: {shown.source_project.scenarios.find(s => s.id === shown.result.reference.scenario_id)?.name ?? "Base model"}.</p>
      <p>Rank and class acceptabilities under the declared assumptions. Preference scores and frequencies are separate. The reference ranking uses deterministically compiled values.</p>
      <section aria-label="Reference feasibility"><p>Deterministic reference feasibility: {FEASIBILITY_LABELS[shown.result.feasibility.status]}. Rank/class draw counts are not conditioned on feasibility; no score offsets a failed requirement.</p>
        <ul>{shown.result.feasibility.result?.alternatives.map(a => <li key={a.alternative_id}>{a.name}: {a.status}{a.failed.length ? `; failed ${a.failed.join(", ")}` : ""}{a.unknown.length ? `; unknown ${a.unknown.join(", ")}` : ""}</li>)}</ul>
        {shown.result.feasibility.issues.map((i, k) => <p key={k}>{i.code}: {i.message}</p>)}
      </section>
      <table className="grid" aria-label="Deterministic factor reference"><thead><tr><th>Alternative</th><th>Preference value</th><th>Rank</th></tr></thead><tbody>{shown.result.reference.ranking.map(a => <tr key={a.alternative_id}><td>{a.name}</td><td>{String(a.value)}</td><td>{a.rank}</td></tr>)}</tbody></table>
      <table className="grid" aria-label="Factor acceptabilities"><thead><tr><th>Alternative</th><th>Rank acceptabilities</th><th>Class acceptabilities</th></tr></thead><tbody>{shown.result.acceptability.map(a => <tr key={a.alternative_id}><td>{a.name}</td><td>{a.ranks.map((r, i) => `${i + 1}: ${String(r.frequency)}${r.count === null ? " (exact)" : ` (${r.count}/${shown.result.draw_count}; ${r.lower}–${r.upper})`}`).join("; ")}</td><td>{Object.entries(a.classes).map(([c, r]) => `${c}: ${String(r.frequency)}`).join("; ") || "Classes not evaluated in this run"}</td></tr>)}</tbody></table>
      <details><summary>Factor trace and reproducibility</summary><p>{shown.result.algorithm}; {shown.result.sampler_algorithm}. {shown.result.rng}</p><pre>{JSON.stringify({ deterministic_inputs: shown.result.deterministic_inputs, trace: shown.result.trace, environment: shown.result.environment, draws_digest: shown.result.draws_digest, model_digest: shown.result.model_digest, uncertainty_digest: shown.result.uncertainty_digest }, null, 2)}</pre></details>
      <ul aria-label="Derived input questions">{shown.result.questions.map((q, i) => <li key={i}>{q.question} {q.why} {q.evidence}</li>)}</ul>
      {shown.decision && <p>Decision snapshot: {shown.decision.decision.owner}, {shown.decision.decision.outcome}. {shown.decision.decision.rationale}</p>}
      {shown.decision && <ul>{shown.decision.notices.map((notice, i) => <li key={i}>{notice.message}</li>)}</ul>}
      <ul>{shown.result.warnings.map((warning, i) => <li key={i}>{warning.code}: {warning.message}</li>)}</ul>
      <ul>{shown.result.limitations.map(s => <li key={s}>{s}</li>)}</ul>
      <button type="button" onClick={() => { download(shown, "factor-run.json"); if (!historical) { setSpecDirty(false); setRecordDirty(false); } }}>Export factor run record</button>
    </section>}
  </details>;
}
