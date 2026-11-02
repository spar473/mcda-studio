import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { ExternalProposals, Project, ProposalCompilation, ProposalInspection, ProposalPayload, ProposalReview, ProposalRegistrySupply } from "../api/types";
import { canonical } from "../state/analysisContext";
import { useAnalysisRequest } from "../state/useAnalysisRequest";
import { MeasurementChanges } from "./EvidenceCompilationPanel";
import { saveDownload } from "./results/downloads";

const download = (value: unknown, filename: string) => saveDownload(new Blob([JSON.stringify(value, null, 2) + "\n"], { type: "application/json" }), filename);
const message = (e: unknown) => e instanceof ApiError ? [e.message, ...e.details.map(d => d.message)].join(" ") : e instanceof Error ? e.message : String(e);
const PAGE_SIZE = 20;
const normaliseEvents = (events: ProposalReview[]) => events.map(e => ({ ...e, review: { ...e.review, reviewed_at: new Date(e.review.reviewed_at).toISOString() } }));

/** Local proposals remain separate from the project and from ordinary evidence dossiers. */
export function ExternalProposalsPanel({ project, fingerprint, onDirty, onWorkspace }: {
  project: Project; fingerprint: string; onDirty: (dirty: boolean) => void;
  onWorkspace?: (workspace: ExternalProposals | null) => void;
}) {
  const [document, setDocument] = useState<ExternalProposals | null>(null);
  const [dirty, setDirty] = useState(false);
  const [format, setFormat] = useState<"json" | "csv">("json");
  const [registries, setRegistries] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tool, setTool] = useState("");
  const [kind, setKind] = useState("");
  const [criterion, setCriterion] = useState("");
  const [relation, setRelation] = useState("");
  const [phase, setPhase] = useState<"original" | "effective">("original");
  const [comparison, setComparison] = useState<string | null>(null);
  const [cell, setCell] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [selection, setSelection] = useState<string[]>([]);
  const [individual, setIndividual] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [status, setStatus] = useState<ProposalReview["review"]["status"] | "">("");
  const [note, setNote] = useState("");
  const [correction, setCorrection] = useState("");
  const [supporting, setSupporting] = useState("");
  const [primary, setPrimary] = useState<Record<string, string>>({});
  const [candidateState, setCandidate] = useState<{ key: string; result: ProposalInspection; events: ProposalReview[] } | null>(null);
  const [acknowledgement, setAcknowledged] = useState<string | null>(null);
  const [compiledState, setCompiled] = useState<{ key: string; bundle: ProposalCompilation } | null>(null);
  const [historical, setHistorical] = useState<ProposalCompilation | null>(null);
  const inspectionKey = canonical({ fingerprint, document, comparison });
  const key = canonical({ inspectionKey, tool, kind, criterion, relation, phase, selection, individual, reviewer, status, note, correction, supporting, primary, format, registries });
  const live = useRef(key);
  useLayoutEffect(() => { live.current = key; }, [key]);
  const candidate = candidateState?.key === key ? candidateState : null;
  const compiled = compiledState?.key === key ? compiledState.bundle : null;
  const acknowledged = acknowledgement === key;
  // This is the single publication guard for asynchronous import, review and compilation replies.
  const acceptsResponse = (captured: string) => live.current === captured;
  const sequence = useRef(0);
  useEffect(() => { onDirty(dirty); }, [dirty, onDirty]);
  useEffect(() => { onWorkspace?.(document); }, [document, onWorkspace]);
  const load = useCallback((signal: AbortSignal) => {
    if (!document) throw Error("Import a proposal sidecar first.");
    return api.inspectProposals(project, document, comparison, signal).then(result => {
      if (result.current_fingerprint !== fingerprint || result.workspace.digest !== document.digest) throw Error("Proposal inspection does not match this context.");
      return result;
    });
  }, [project, fingerprint, document, comparison]);
  const request = useAnalysisRequest(inspectionKey, document !== null, load);
  const result = request.status === "ready" ? request.result : null;
  const rows = result?.rows ?? [];
  const selectedIds = individual ? [individual] : selection;
  const selected = selectedIds.map(id => rows.find(r => r.original.id === id)).filter(r => r !== undefined);
  const sources = { ...document?.intake.sources };
  const cards = { ...document?.intake.model_cards };
  document?.registry_supplies.forEach(s => { Object.assign(sources, s.sources); Object.assign(cards, s.model_cards); });
  const filtered = rows.filter(r => (!tool || r.original.tool_id === tool) && (!kind || r.original.payload.kind === kind) && (!criterion || r.original.subject.criterion_id === criterion) && (!relation || (phase === "original" ? r.original_relations : r.effective_relations).some(v => v === relation)));
  const shown = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const changeFilter = (change: () => void) => { change(); setSelection([]); setIndividual(""); setPage(0); };
  const openFile = async (file: File | undefined, mode: "import" | "bundle" | "registry-file") => {
    if (!file || dirty || busy) return;
    const captured = key, currentSequence = ++sequence.current;
    setError(null); setBusy(true);
    try {
      if (file.size > 8_000_000) throw Error("Proposal file exceeds the 8 MB limit.");
      const text = await file.text();
      if (!acceptsResponse(captured) || sequence.current !== currentSequence) return;
      if (mode === "registry-file") { setRegistries(text); return; }
      if (mode === "bundle") {
        const verified = await api.verifyProposals(JSON.parse(text) as unknown);
        if (!acceptsResponse(captured) || sequence.current !== currentSequence) return;
        setHistorical(verified); setDocument(verified.workspace);
      } else {
        const checked = await api.importProposals(project, text, format, format === "csv" ? registries : null);
        if (!acceptsResponse(captured) || sequence.current !== currentSequence) return;
        if (checked.current_fingerprint !== fingerprint) throw Error("Proposal import does not match this project revision.");
        setDocument(checked.workspace); setHistorical(null);
      }
      setSelection([]); setIndividual(""); setComparison(null); setCell(null);
    } catch (e) { if (acceptsResponse(captured)) setError(message(e)); }
    finally { setBusy(false); }
  };
  const preview = async () => {
    if (!result || !document || result.stale || !status || !reviewer.trim() || !selected.length || busy) return;
    const captured = key;
    setBusy(true); setError(null);
    try {
      const correctedPayload = status === "corrected" ? JSON.parse(correction) as ProposalPayload : null;
      const reviewedAt = new Date().toISOString();
      const events: ProposalReview[] = selected.map(r => ({ proposal_id: r.original.id, review: {
        status, reviewer: reviewer.trim(), reviewed_at: reviewedAt, note, corrected_payload: correctedPayload,
        primary_source_id: primary[r.original.id] || null, supporting_source_ids: supporting.split(",").map(s => s.trim()).filter(Boolean),
      } }));
      const checked = await api.reviewProposals(project, document, events, result.review_digest, !individual, comparison);
      if (!acceptsResponse(captured)) return;
      if (checked.current_fingerprint !== fingerprint || checked.workspace.reviews.length !== document.reviews.length + events.length || canonical(checked.workspace.intake) !== canonical(document.intake) || canonical(normaliseEvents(checked.workspace.reviews.slice(-events.length))) !== canonical(normaliseEvents(events))) throw Error("Proposal review does not match the selected items and history.");
      setCandidate({ key: captured, result: checked, events });
    } catch (e) { if (acceptsResponse(captured)) setError(message(e)); }
    finally { setBusy(false); }
  };
  const compile = async () => {
    if (!result || !document || result.stale || !acknowledged || busy) return;
    const captured = key;
    setBusy(true); setError(null);
    try {
      const bundle = await api.compileProposals(project, document, result.review_digest, comparison);
      if (!acceptsResponse(captured)) return;
      if (bundle.workspace.digest !== document.digest || bundle.evidence.preview.project_fingerprint !== fingerprint || bundle.evidence.preview.review_digest !== result.preview.review_digest) throw Error("Proposal compilation does not match the acknowledged preview.");
      setCompiled({ key: captured, bundle });
    } catch (e) { if (acceptsResponse(captured)) setError(message(e)); }
    finally { setBusy(false); }
  };
  return <details className="external-proposals" aria-label="External proposals"><summary>External proposals</summary>
    <p>Import local files from any external classifier tool or model. Outputs require human review. Confidence remains metadata; tags and source assertions do not become preference penalties. Project Save does not store these sidecars.</p>
    <label>Proposal import format<select value={format} disabled={dirty || busy} onChange={e => setFormat(e.target.value as "json" | "csv")}><option value="json">JSON intake or review workspace</option><option value="csv">CSV with local registries</option></select></label>
    <label>Local proposal registries<input type="file" accept=".json" disabled={dirty || busy} onChange={e => { void openFile(e.target.files?.[0], "registry-file"); }}/></label>
    {registries && <p>Local registries selected; nothing fetched.</p>}
    <label>Import proposal file<input type="file" accept=".json,.csv" disabled={dirty || busy || (format === "csv" && !registries)} onChange={e => { void openFile(e.target.files?.[0], "import"); }}/></label>
    <label>Open proposal compilation<input type="file" accept=".json" disabled={dirty || busy} onChange={e => { void openFile(e.target.files?.[0], "bundle"); }}/></label>
    {busy && <p role="status">Checking proposals in Python…</p>}
    {error && <p role="alert">{error}</p>}
    {document && <button type="button" onClick={() => { download(document, "external-proposals-workspace.json"); setDirty(false); }}>Export proposal review workspace</button>}
    {dirty && <p role="status">Proposal history has not been exported. Export it before Save or leaving.</p>}
    {request.status === "error" && <><p role="alert">{request.message}</p><button type="button" onClick={request.retry}>Retry proposal inspection</button></>}
    {result && <>
      {result.stale && <p role="alert">The exact source project is unavailable or differs from this revision. Export remains available; new reviews and compilation are blocked.</p>}
      <fieldset><legend>Filter proposals without selecting them</legend>
        <label>Proposal tool<select value={tool} onChange={e => changeFilter(() => setTool(e.target.value))}><option value="">All tools</option>{[...new Set(rows.map(r => r.original.tool_id))].map(id => <option key={id}>{id}</option>)}</select></label>
        <label>Proposal kind<select value={kind} onChange={e => changeFilter(() => setKind(e.target.value))}><option value="">All kinds</option>{[...new Set(rows.map(r => r.original.payload.kind))].map(id => <option key={id}>{id}</option>)}</select></label>
        <label>Proposal criterion<select value={criterion} onChange={e => changeFilter(() => setCriterion(e.target.value))}><option value="">All criteria</option>{[...new Set(rows.map(r => r.original.subject.criterion_id).filter(id => id !== null))].map(id => <option key={id} value={id}>{project.criteria.find(c => c.id === id)?.name ?? id}</option>)}</select></label>
        <label>Compare proposals with<select value={comparison ?? ""} onChange={e => changeFilter(() => setComparison(e.target.value || null))}><option value="">Choose a comparison</option>{result.comparison_targets.map(id => <option key={id}>{id}</option>)}</select></label>
        <label>Comparison values<select value={phase} onChange={e => changeFilter(() => setPhase(e.target.value as "original" | "effective"))}><option value="original">Original proposals</option><option value="effective">Effective reviewed values</option></select></label>
        <label>Proposal agreement<select value={relation} disabled={!comparison} onChange={e => changeFilter(() => setRelation(e.target.value))}><option value="">All relations</option><option value="agreement">Agreement</option><option value="disagreement">Disagreement</option><option value="incomparable">Incomparable units or types</option></select></label>
      </fieldset>
      <p>{filtered.length} matching proposals. {selection.length} explicitly selected for bulk review. No items are selected automatically.</p>
      <button type="button" onClick={() => { setSelection([]); setIndividual(""); }}>Clear proposal selection</button>
      <div className="table-scroll"><table className="grid" aria-label="External proposal review table"><thead><tr><th>Select for bulk</th><th>Proposal and subject</th><th>Original and effective payload</th><th>Provenance and issues</th><th>Review</th></tr></thead><tbody>{shown.map(r => <tr key={r.original.id}>
        <td><input type="checkbox" aria-label={`Select proposal ${r.original.id}`} disabled={!r.bulk_eligible || busy} checked={selection.includes(r.original.id)} onChange={e => { setIndividual(""); setSelection(e.target.checked ? [...selection, r.original.id] : selection.filter(id => id !== r.original.id)); }}/></td>
        <td>{r.original.id}<br/>{r.original.subject.alternative_id} / {r.original.subject.criterion_id ?? "annotation"}<br/>{r.review?.status ?? "pending"}</td>
        <td><p>Original: {JSON.stringify(r.original.payload)}</p><p>Effective: {JSON.stringify(r.effective)}</p>{r.original.confidence && <p>Confidence metadata only: {JSON.stringify(r.original.confidence)}</p>}</td>
        <td><p>{r.original.tool_id} {r.original.tool_version}, {r.original.run_at}</p><p>Sources: {r.original.source_ids.map(id => `${id}: ${sources[id]?.classification ?? "unresolved"}; ${sources[id]?.reference ?? "missing"}`).join(" | ") || "missing"}</p>
          <details><summary>Model card for {r.original.id}</summary><pre>{JSON.stringify(cards[r.original.model_card_id] ?? "missing", null, 2)}</pre><p>Expected card digest: {r.original.model_card_digest}</p></details>
          {r.issues.map((i, k) => <p key={k}>{i.code}: {i.message}</p>)}
          <button type="button" onClick={() => setCell(`${r.original.subject.alternative_id}/${r.original.subject.criterion_id ?? ""}`)}>Compare cell {r.original.id}</button>
        </td><td>{r.review && <><p>{r.review.reviewer}, {r.review.reviewed_at}. {r.review.note}</p><p>Primary source: {r.review.primary_source_id ? `${r.review.primary_source_id}: ${sources[r.review.primary_source_id]?.classification ?? "unresolved"}; ${sources[r.review.primary_source_id]?.reference ?? "missing"}` : "none"}. Supporting sources: {r.review.supporting_source_ids.map(id => `${id}: ${sources[id]?.classification ?? "unresolved"}; ${sources[id]?.reference ?? "missing"}`).join(" | ") || "none"}</p></>}<button type="button" disabled={result.stale || busy} onClick={() => { setSelection([]); setIndividual(r.original.id); }}>Review proposal {r.original.id}</button></td>
      </tr>)}</tbody></table></div>
      <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous proposal page</button>
      <button type="button" disabled={(page + 1) * PAGE_SIZE >= filtered.length} onClick={() => setPage(page + 1)}>Next proposal page</button>
      {result.comparisons.filter(c => `${c.alternative_id}/${c.criterion_id}` === cell).map(c => <section key={cell} aria-label="Proposal cell comparison"><h4>{c.alternative_id} / {c.criterion_id}</h4><p>Original disagreement stays visible after review. Human columns are comparison references, outside this intake’s compilation selection. Agreement is descriptive; shared sources do not establish independent validation.</p><div className="table-scroll"><table className="grid"><thead><tr><th>Input</th>{c.columns.map(col => <th key={col.id}>{col.id} · {col.tool_id ?? "human"} · {col.status}</th>)}</tr></thead><tbody>
        <tr><th>Original</th>{c.columns.map(col => <td key={col.id}>{col.original_value ?? "no explicit measurement"} {col.original_unit}</td>)}</tr>
        <tr><th>Effective</th>{c.columns.map(col => <td key={col.id}>{col.effective_value ?? "no explicit measurement"} {col.effective_unit}</td>)}</tr>
        <tr><th>Sources and stated ranges</th>{c.columns.map(col => <td key={col.id}>{col.sources.join("; ")} · {col.source_classifications.join("; ")}{col.range_lower !== null && <p>Stated range: {col.range_lower} to {col.range_upper}; no distribution inferred.</p>}</td>)}</tr>
      </tbody></table></div></section>)}
      {selected.length > 0 && <fieldset><legend>{individual ? "Individual proposal review" : "Explicit bulk review"}</legend>
        <p>A correction retains the entire original. A bulk action writes one separate event per selected proposal with the same reviewer, time and note.</p>
        <label>Proposal reviewer<input value={reviewer} onChange={e => setReviewer(e.target.value)}/></label>
        <label>Proposal review decision<select value={status} onChange={e => setStatus(e.target.value as typeof status)}><option value="">Choose a decision</option><option value="accepted">Accept</option><option value="corrected">Correct</option><option value="rejected">Reject</option></select></label>
        <label>Proposal review note<textarea value={note} onChange={e => setNote(e.target.value)}/></label>
        <label>Supporting proposal source IDs (comma separated)<input value={supporting} onChange={e => setSupporting(e.target.value)}/></label>
        {status === "corrected" && <label>Corrected proposal payload (JSON)<textarea value={correction} onChange={e => setCorrection(e.target.value)}/></label>}
        {status !== "rejected" && <>
          <button type="button" disabled={selected.some(r => r.original.source_ids.length !== 1 || !sources[r.original.source_ids[0] ?? ""])} onClick={() => setPrimary(Object.fromEntries(selected.map(r => [r.original.id, r.original.source_ids[0] ?? ""])))}>Use each selected proposal's sole cited source</button>
          {selected.map(r => <label key={r.original.id}>Primary source for {r.original.id}<select value={primary[r.original.id] ?? ""} onChange={e => setPrimary({ ...primary, [r.original.id]: e.target.value })}><option value="">Choose a source</option>{Object.entries(sources).map(([id, source]) => <option key={id} value={id}>{id}: {source.name} ({source.classification})</option>)}</select></label>)}
        </>}
        <button type="button" disabled={busy || result.stale || !reviewer.trim() || !status || (status !== "rejected" && selected.some(r => !primary[r.original.id])) || (status === "corrected" && !correction.trim())} onClick={() => { void preview(); }}>Preview selected proposal reviews</button>
      </fieldset>}
      {candidate && <section aria-label="Proposal review confirmation"><h4>Confirm every affected proposal</h4><ol>{candidate.events.map(e => <li key={e.proposal_id}><strong>{e.proposal_id}</strong> · {e.review.status} · {e.review.reviewer} at {e.review.reviewed_at}<p>{e.review.note}</p><p>Original: {JSON.stringify(document?.intake.proposals.find(p => p.id === e.proposal_id)?.payload)}</p><p>Correction: {JSON.stringify(e.review.corrected_payload)}; primary source {e.review.primary_source_id ?? "none"}</p></li>)}</ol>
        <button type="button" onClick={() => { setDocument(candidate.result.workspace); setDirty(true); setHistorical(null); setSelection([]); setIndividual(""); }}>Confirm listed proposal reviews</button>
      </section>}
      <details><summary>Proposal review history ({document?.reviews.length ?? 0} events)</summary><ol>{document?.reviews.map((e, i) => <li key={i}>{e.proposal_id} · {e.review.status} · {e.review.reviewer}, {e.review.reviewed_at}: {e.review.note}</li>)}</ol></details>
      <fieldset><legend>Supply missing local registry entries</legend><p>Original proposals and existing registry entries cannot be replaced. Registry JSON uses sources and model_cards objects.</p>
        <label>Registry recorder<input value={reviewer} onChange={e => setReviewer(e.target.value)}/></label>
        <label>Supply proposal registry JSON<input type="file" accept=".json" disabled={busy || result.stale || !reviewer.trim()} onChange={e => {
          const file = e.target.files?.[0]; if (!file || !document) return;
          const captured = key; setBusy(true); setError(null);
          void (async () => {
            if (file.size > 8_000_000) throw Error("Registry file exceeds the 8 MB limit.");
            const supplied = JSON.parse(await file.text()) as Pick<ProposalRegistrySupply, "sources" | "model_cards">;
            if (!acceptsResponse(captured)) return;
            const checked = await api.supplyProposalRegistries(project, document, { sources: supplied.sources, model_cards: supplied.model_cards, recorded_by: reviewer.trim(), recorded_at: new Date().toISOString(), note });
            if (!acceptsResponse(captured)) return;
            if (checked.current_fingerprint !== fingerprint || canonical(checked.workspace.intake) !== canonical(document.intake) || canonical(checked.workspace.reviews) !== canonical(document.reviews)) throw Error("Registry addition changed original proposal or review history.");
            setDocument(checked.workspace); setDirty(true);
          })().catch((err: unknown) => { if (acceptsResponse(captured)) setError(message(err)); }).finally(() => setBusy(false));
        }}/></label>
      </fieldset>
      <section aria-label="Proposal compilation preview"><h4>Compile reviewed proposals into a separate copy</h4>
        <MeasurementChanges project={project} preview={result.preview} dossier={result.dossier} label="Proposal measurement changes"/>
        <p>{result.annotations.length} reviewed annotations stay in the compilation bundle; {result.rows.filter(r => !r.review).length} proposals remain pending. Pending, rejected and blocked rows never enter the numerical subset.</p>
        {result.annotations.map(a => <p key={a.proposal_id}>{a.proposal_id}: {JSON.stringify(a.payload)}</p>)}
        {result.preview.issues.map((i, n) => <p key={n}>{i.code}: {i.message}</p>)}
        <label><input type="checkbox" checked={acknowledged} disabled={result.stale || result.preview.issues.some(i => i.severity === "error")} onChange={e => setAcknowledged(e.target.checked ? key : null)}/>I reviewed every proposal measurement change and retained annotation</label>
        <button type="button" disabled={!acknowledged || result.stale || busy} onClick={() => { void compile(); }}>Compile reviewed proposal copy</button>
      </section>
      <section aria-label="Proposal questions"><h4>Open proposal questions</h4><ul>{result.questions.map((q, n) => <li key={n}>{q.question} {q.why} {q.evidence}</li>)}</ul></section>
    </>}
    {(compiled ?? historical) && (() => {
      const bundle = compiled ?? historical; if (!bundle) return null;
      return <section aria-label="Proposal compilation bundle"><p>{historical && !compiled ? "Verified historical compilation. " : "Compiled separate copy. "}The original project and library are unchanged. Keep the full proposal bundle for originals, cards, all sources, reviews and annotations.</p>
        <button type="button" onClick={() => download(bundle.evidence.project, "proposal-compiled-project.json")}>Export proposal project copy</button>
        <button type="button" onClick={() => { download(bundle, "proposal-compilation.json"); if (compiled) setDirty(false); }}>Export proposal compilation bundle</button>
        <button type="button" onClick={() => download(bundle.evidence, "proposal-evidence-compilation.json")}>Export nested evidence bundle for decision record</button>
      </section>;
    })()}
  </details>;
}
