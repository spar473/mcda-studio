import type { StudyEvidenceOffer } from "./CompanyExplorer";
import { EvidenceClaims } from "./EvidenceClaims";
import { ExternalProposalsPanel } from "./ExternalProposalsPanel";
import type { ExternalProposals } from "../api/types";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "../api/client";
import type { ClaimReview, EvidenceCompilation, EvidenceDossier, EvidenceInspection, Project } from "../api/types";
import { canonical } from "../state/analysisContext";
import { useAnalysisRequest } from "../state/useAnalysisRequest";
import { ArtifactBindingStatus } from "./ArtifactBindingStatus";
import { EvidenceCompilationPanel, MeasurementChanges } from "./EvidenceCompilationPanel";
import { saveDownload } from "./results/downloads";
import { InfoDisclosure } from "./InfoDisclosure";
import { displayNumber } from "./results/numberDisplay";
import { IssueText } from "./IssueText";

function download(value: unknown, name: string) {
  saveDownload(new Blob([JSON.stringify(value, null, 2) + "\n"], { type: "application/json" }), name);
}

const isCompilation = (value: unknown) => typeof value === "object" && value !== null && "compilation_version" in value;

export function EvidenceWorkspacePanel({ project, fingerprint, active, onDossier, onDirty, onMeasurement, onProposals, onStudyEvidence, renderWorkspace }: {
  project: Project; fingerprint: string; active: boolean;
  onProposals?: (workspace: ExternalProposals | null) => void;
  onStudyEvidence?: (offer: StudyEvidenceOffer | null) => void;
  renderWorkspace?: (workspace: ReactNode) => ReactNode;
  onDossier: (dossier: EvidenceDossier | null) => void;
  onDirty: (dirty: boolean) => void;
  onMeasurement: (alternativeId: string, criterionId: string) => void;
}) {
  const [document, setDocument] = useState<unknown>(null);
  const [original, setOriginal] = useState<unknown>(null);
  const [dirty, setDirty] = useState(false);
  const [proposalDirty, setProposalDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [claimId, setClaimId] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [status, setStatus] = useState<ClaimReview["review"]["status"]>("accepted");
  const [corrected, setCorrected] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [candidate, setCandidate] = useState<{ key: string; result: EvidenceInspection } | null>(null);
  const sequence = useRef(0);
  const key = canonical({ fingerprint, document, claimId, reviewer, status, corrected, note });
  const liveKey = useRef(key);
  useLayoutEffect(() => { liveKey.current = key; }, [key]);
  const load = useCallback(async (signal: AbortSignal) => {
    // A compilation bundle is verified by replay and reconstruction, then inspected like its history.
    const opened: { inspection: EvidenceInspection; compilation: EvidenceCompilation | null } = isCompilation(document)
      ? await api.inspectEvidenceCompilation(project, document, signal)
      : { inspection: await api.inspectEvidence(project, document, signal), compilation: null };
    if (opened.inspection.preview.project_fingerprint !== fingerprint) throw Error("Evidence inspection does not match this project revision.");
    return opened;
  }, [project, fingerprint, document]);
  const inspectionKey = canonical({ fingerprint, document });
  const request = useAnalysisRequest(inspectionKey, document !== null, load);
  const result = request.status === "ready" ? request.result.inspection : null;
  const recorded = request.status === "ready" ? request.result.compilation : null;
  const current = candidate?.key === key ? candidate.result : null;
  const stale = result?.preview.issues.some(i => i.code === "EVIDENCE_STALE_PROJECT") ?? false;
  const claim = result?.dossier.claims.find(c => c.id === claimId);
  // A starter whose worked example is exactly this project and that ships a dossier: offer it in
  // one action. Matching is by fingerprint and artifact kind only, never by template name.
  const [found, setFound] = useState<{ fingerprint: string; title: string; dossier: unknown } | null>(null);
  const bundled = found?.fingerprint === fingerprint ? found : null;
  useEffect(() => {
    const live = { current: true };
    void (async () => {
      const templates = await api.starterTemplates();
      for (const template of templates) {
        const dossier = template.artifacts.find(a => a.kind === "evidence_dossier");
        if (!dossier) continue;
        const worked = await api.instantiateStarter({ template_id: template.id, mode: "worked_example", optional_artifact_ids: [], title: "", description: "", decision_maker: "" });
        const item = worked.artifacts[dossier.id];
        if (worked.receipt.project_fingerprint === fingerprint && item) {
          if (live.current) setFound({ fingerprint, title: template.title, dossier: item.value });
          return;
        }
      }
    })().catch(() => undefined); // no offer; the file picker remains
    return () => { live.current = false; };
  }, [fingerprint]);
  const loadStudy = useCallback(() => {
    if (!bundled || document !== null || dirty) return;
    ++sequence.current; setError(null); setClaimId(""); setCandidate(null);
    setDocument(bundled.dossier); setOriginal(bundled.dossier);
  }, [bundled, document, dirty]);
  useEffect(() => {
    onStudyEvidence?.(bundled && document === null && !dirty ? { title: bundled.title, load: loadStudy } : null);
  }, [bundled, document, dirty, loadStudy, onStudyEvidence]);
  useEffect(() => { onDirty(dirty || proposalDirty); }, [dirty, proposalDirty, onDirty]);
  useEffect(() => { onDossier(result?.dossier ?? null); }, [result, onDossier]);
  const propose = async () => {
    if (!result || !claim || stale || busy) return;
    const captured = key;
    setError(null); setCandidate(null); setBusy(true);
    try {
      const numeric = project.criteria.find(c => c.id === claim.criterion_id)?.scale?.type;
      const value = numeric === "ratio" || numeric === "interval" ? Number(corrected) : corrected;
      if (status === "corrected" && (!corrected.trim() || typeof value === "number" && !Number.isFinite(value))) throw Error("Enter a valid corrected value.");
      const review: ClaimReview["review"] = { status, reviewer: reviewer.trim(), reviewed_at: new Date().toISOString(), note,
        corrected_value: status === "corrected" ? value : null };
      const proposed = await api.reviewEvidence(project, result.workspace, { claim_id: claimId, review }, result.preview.review_digest);
      if (liveKey.current === captured) {
        if (proposed.preview.project_fingerprint !== fingerprint) throw Error("Review does not match this project revision.");
        setCandidate({ key: captured, result: proposed });
      }
    } catch (e) {
      if (liveKey.current === captured) setError(e instanceof ApiError
        ? [e.message, ...e.details.map(detail => detail.message)].filter(Boolean).join(" ")
        : e instanceof Error ? e.message : String(e));
    }
    finally { setBusy(false); }
  };
  const workspace = <section className="panel" aria-label="Evidence Workspace" hidden={!active}>
    <h2>Evidence Workspace</h2>
    <ExternalProposalsPanel project={project} fingerprint={fingerprint} onDirty={setProposalDirty} onWorkspace={onProposals}/>
    {document === null && (bundled
      ? <p><button type="button" className="primary" disabled={dirty} onClick={loadStudy}>Open the study's evidence</button> <span className="muted small">The sourced claims shipped with {bundled.title}.</span></p>
      : <p>Load an evidence dossier: a JSON file of sourced claims about this project's measurements, such as one exported from this tab, a review workspace you exported earlier, or a compilation bundle.</p>)}
    <p>Inspect local sources and explicitly review claims. Reviews stay in this session until you export the workspace. Project measurements change only through separate compilation into a new copy. A compilation bundle can be reopened here for verification.</p>
    <label>Evidence dossier or review workspace
      <input type="file" accept=".json,application/json" disabled={dirty} onChange={event => {
        const file = event.target.files?.[0];
        const currentSequence = ++sequence.current;
        setDocument(null); setOriginal(null); setCandidate(null); setError(null); setClaimId("");
        if (!file) return;
        if (file.size > 8_000_000) { setError("Evidence file exceeds the 8 MB limit."); return; }
        void file.text().then(text => {
          const parsed: unknown = JSON.parse(text);
          if (sequence.current === currentSequence) { setDocument(parsed); setOriginal(parsed); }
        }).catch(() => { if (sequence.current === currentSequence) setError("Could not read evidence JSON."); });
      }}/>
    </label>
    {dirty && <p role="status">Reviews have not been exported. Export the review workspace to retain the original project, dossier and review history before closing.</p>}
    {dirty && <button type="button" onClick={() => { setDocument(original); setDirty(false); setCandidate(null); }}>Discard reviews since last export</button>}
    {error && <p role="alert">{error}</p>}
    {document !== null && request.status === "loading" && <p role="status">Inspecting evidence…</p>}
    {request.status === "error" && <><p role="alert">{request.message}</p><button type="button" onClick={request.retry}>Retry evidence inspection</button></>}
    {result && <>
      {result.preview.issues.map((i, k) => <p key={k} role={i.severity === "error" ? "alert" : undefined}><IssueText code={i.code} message={i.message}/></p>)}
      <p>Independent, self-reported and unknown describe the source relationship. Independence does not establish correctness. Outdated and conflicting are separate from review status.</p>
      <p>Only one claim can be accepted for a measurement. Reject an earlier accepted claim before accepting its replacement.</p>
      <EvidenceClaims result={result} project={project} stale={stale} onReview={id => { setClaimId(id); setCandidate(null); setError(null); }} onMeasurement={onMeasurement}/>
      {claim && !stale && <form aria-label="Claim review" onSubmit={e => { e.preventDefault(); void propose(); }}>
        <h3>Review {claim.source.name} <InfoDisclosure label="Review claim details"><code>{claim.id}</code></InfoDisclosure></h3>
        <label>Reviewer<input required value={reviewer} onChange={e => setReviewer(e.target.value)}/></label>
        <label>Review decision<select aria-label="Review decision" value={status} onChange={e => setStatus(e.target.value as typeof status)}>
          <option value="accepted">Accept claim</option><option value="rejected">Reject claim</option><option value="corrected">Accept corrected value</option>
        </select></label>
        {status === "corrected" && <label>Corrected value<input required value={corrected} onChange={e => setCorrected(e.target.value)}/></label>}
        <label>Review note<textarea value={note} onChange={e => setNote(e.target.value)}/></label>
        <button type="submit" disabled={busy || !reviewer.trim()}>Preview review</button>
      </form>}
      {current && <section aria-label="Proposed review">
        <h3>Proposed review</h3>
        <p>{claim?.source.name}: {current.dossier.claims.find(c => c.id === claimId)?.review?.status}. This appends a review; the original claim and earlier reviews remain in the workspace.</p>
        <p>Measurement changes after separate compilation:</p>
        <ChangeList inspection={current} project={project}/>
        <button type="button" onClick={() => {
          if (liveKey.current !== candidate?.key) return;
          setDocument(current.workspace); setDirty(true); setCandidate(null); setClaimId(""); setNote("");
        }}>Confirm review in workspace</button>
        <button type="button" onClick={() => setCandidate(null)}>Cancel review</button>
      </section>}
      <h3>Measurement support in the current project</h3>
      <p>Unsupported: no claim recorded here. Unverified: claims exist, but no accepted value matches the measurement. Missing: no measurement entered. These labels do not determine numerical validity. Supported means an accepted matching claim, not proof of accuracy.</p>
      {!result.support_available ? <p>Support assessment unavailable until dossier issues are resolved.</p> : <ul aria-label="Measurement support">{result.support.map(cell => <li key={`${cell.alternative_id}-${cell.criterion_id}`}>
        {project.alternatives.find(a => a.id === cell.alternative_id)?.name} / {project.criteria.find(c => c.id === cell.criterion_id)?.name}: {typeof cell.measurement === "number" ? displayNumber(cell.measurement) : cell.measurement ?? "no measurement"} · {cell.status}{cell.accepted_claim_ids.length > 0 && <InfoDisclosure label="Support details">Accepted claims: {cell.accepted_claim_ids.join(", ")}</InfoDisclosure>}.
      </li>)}</ul>}
      {recorded && <section aria-label="Recorded evidence compilation">
        <h3>Recorded compilation</h3>
        <p>Verified in Python: the bundle digest matches, the review history replays and the compilation reproduces exactly. The recorded changes below are historical and do not depend on the current project.</p>
        <MeasurementChanges project={recorded.workspace.source_project} preview={recorded.preview} dossier={result.dossier} label="Recorded measurement changes" before="Original measurement"/>
        <ArtifactBindingStatus project={project} fingerprint={fingerprint} artifact={recorded} label="Evidence compilation"/>
        <button type="button" onClick={() => download(recorded.project, "evidence-compiled-project.json")}>Export recorded compiled project</button>
      </section>}
      {stale
        ? <p>Compilation is unavailable: this dossier belongs to a different project revision. Open its original project to compile, or inspect the history read-only.</p>
        : <EvidenceCompilationPanel project={project} fingerprint={fingerprint} inspection={result} contextKey={key}
          onHistoryExported={() => { setOriginal(result.workspace); setDirty(false); }}/>}
      <details><summary>Review history ({result.workspace.reviews.length} appended)</summary>
        <p>Reviews already present on import remain in the original dossier.</p>
        <ol>{result.workspace.reviews.map((event, k) => <li key={k}>{event.claim_id}: {event.review.status} by {event.review.reviewer} at {event.review.reviewed_at}. {event.review.note}</li>)}</ol>
      </details>
      <button type="button" disabled={!result.workspace_exportable} onClick={() => {
        download(result.workspace, "evidence-workspace.json"); setOriginal(result.workspace); setDirty(false);
      }}>Export review workspace</button>
      <button type="button" disabled={stale} onClick={() => download(result.dossier, "reviewed-evidence.json")}>Export reviewed dossier</button>
      <button type="button" onClick={() => download(result.preview, "evidence-preview.json")}>Export compilation preview</button>
      <p>The evidence CLI can still compile the exported dossier with its preview digest. Exporting a dossier alone omits appended history; keep the workspace or compilation bundle as well. No source is fetched automatically.</p>
    </>}
  </section>;
  return renderWorkspace ? renderWorkspace(workspace) : workspace;
}

function ChangeList({ inspection, project }: { inspection: EvidenceInspection; project: Project }) {
  return inspection.preview.changes.length === 0 ? <p>No measurement changes proposed.</p> : <ul aria-label="Proposed measurement changes">{inspection.preview.changes.map(c => <li key={`${c.alternative_id}-${c.criterion_id}`}>
    {project.alternatives.find(a => a.id === c.alternative_id)?.name ?? c.alternative_id} / {project.criteria.find(n => n.id === c.criterion_id)?.name ?? c.criterion_id}: {typeof c.before === "number" ? displayNumber(c.before) : c.before ?? "missing"} → {typeof c.after === "number" ? displayNumber(c.after) : c.after} <InfoDisclosure label="Measurement change details">Claim <code>{c.claim_id}</code> · {c.alternative_id} / {c.criterion_id}</InfoDisclosure>.
  </li>)}</ul>;
}
