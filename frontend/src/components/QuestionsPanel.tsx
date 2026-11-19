import { Caveat, InfoDisclosure } from "./InfoDisclosure";
import { CompanyName } from "./companyExploration";
import { DecisionImpactList } from "./DecisionImpactList";
import { displayNumber } from "./results/numberDisplay";
import type { ExternalProposals, ModelComparison, ProxyInputs } from "../api/types";
import { useCallback, useRef, useState } from "react";
import { api } from "../api/client";
import type { EvidenceDossier, Project } from "../api/types";
import type { EditorTab } from "../model/issues";
import { analysisKey, canonical, type AnalysisContext } from "../state/analysisContext";
import { useAnalysisRequest } from "../state/useAnalysisRequest";

const questionOrder = (code: string) => code === "CONFLICTING_CLAIMS" ? 0 : code === "OUTDATED_CLAIM" ? 1 : code.startsWith("WEIGHT_") ? 2 : 3;
// Presentation joins only: original diagnostic prose is retained exactly in Details.
function questionText(text: string, dossier?: EvidenceDossier | null): string {
  return text.replace(/\b[a-z]+__[a-z_]+\b/g, id => dossier?.claims.find(c => c.id === id)?.source.name ?? "this evidence claim");
}
const DESTINATIONS: Record<string, { tab: EditorTab; label: string }> = {
  METHOD_LEADER_DISAGREEMENT: { tab: "compare", label: "Open comparison" },
  WEIGHT_WINNER_CHANGE: { tab: "weights", label: "Open weights" },
  WEIGHT_CLASS_CHANGE: { tab: "classes", label: "Open classes" },
  SMAA_INPUT_TO_CHECK: { tab: "uncertainty", label: "Open uncertainty" },
  INVALID_REQUIREMENTS: { tab: "requirements", label: "Open requirements" },
  UNKNOWN_REQUIREMENT: { tab: "requirements", label: "Open requirements" },
};

export function QuestionsPanel({ project, context, onOpenTab, workspaceDossier, workspaceProposals, workspaceModels, workspaceProxy }: {
  project: Project; context: AnalysisContext; onOpenTab: (tab: EditorTab) => void;
  workspaceDossier?: EvidenceDossier | null;
  workspaceProposals?: ExternalProposals | null;
  workspaceModels?: ModelComparison | null;
  workspaceProxy?: ProxyInputs | null;
}) {
  const [factorRecord, setFactorRecord] = useState<unknown>(null);
  const [localDossier, setDossier] = useState<unknown>(null);
  const dossier = workspaceDossier ?? localDossier;
  const [fileError, setFileError] = useState<string | null>(null);
  const fileSequence = useRef(0);
  const { fingerprint, configuration } = context;
  const key = canonical({ analysis: analysisKey({ ...context, criterionId: null }, "open-questions"), dossier, factorRecord, workspaceProposals, workspaceModels, workspaceProxy });
  const load = useCallback(async (signal: AbortSignal) => {
    const result = workspaceProxy ? await api.openQuestions(project, configuration, signal, dossier ?? undefined, factorRecord ?? undefined, workspaceProposals ?? undefined, workspaceModels ?? undefined, workspaceProxy) : workspaceModels ? await api.openQuestions(project, configuration, signal, dossier ?? undefined, factorRecord ?? undefined, workspaceProposals ?? undefined, workspaceModels) : workspaceProposals ? await api.openQuestions(project, configuration, signal, dossier ?? undefined, factorRecord ?? undefined, workspaceProposals) : factorRecord === null ? await api.openQuestions(project, configuration, signal, dossier ?? undefined) : await api.openQuestions(project, configuration, signal, dossier ?? undefined, factorRecord);
    if (result.project_fingerprint !== fingerprint || canonical(result.configuration) !== canonical(configuration)) {
      throw Error("Questions do not match the selected analysis context.");
    }
    return result;
  }, [project, configuration, fingerprint, dossier, factorRecord, workspaceProposals, workspaceModels, workspaceProxy]);
  const request = useAnalysisRequest(key, true, load);
  // Opt-in: the decision-impact route is called only when the toggle is on.
  const [byImpact, setByImpact] = useState(false);
  const impactKey = canonical({ analysis: analysisKey({ ...context, criterionId: null }, "decision-impact"), dossier, workspaceProposals });
  const loadImpact = useCallback(async (signal: AbortSignal) => {
    const result = await api.decisionImpact(project, configuration, signal, dossier ?? undefined, workspaceProposals ?? undefined);
    if (result.project_fingerprint !== fingerprint || canonical(result.configuration) !== canonical(configuration)) {
      throw Error("Decision impact does not match the selected analysis context.");
    }
    return result;
  }, [project, configuration, fingerprint, dossier, workspaceProposals]);
  const impact = useAnalysisRequest(impactKey, byImpact && project.alternatives.length > 0, loadImpact);
  return <section className="panel" aria-label="Open Questions">
    <h2>Open Questions</h2>
    <p>Use these prompts to decide what to check next. No overall importance score is calculated.</p>
    <label className="partner-toggle"><input type="checkbox" checked={byImpact} onChange={event => setByImpact(event.target.checked)}/> Sort by decision impact</label>
    {byImpact && impact.status === "loading" && <p role="status">Checking each rated cell…</p>}
    {byImpact && impact.status === "error" && <><p role="alert">{impact.message}</p><button type="button" onClick={impact.retry}>Retry decision impact</button></>}
    {byImpact && impact.status === "ready" && <DecisionImpactList project={project} impact={impact.result}/>}
    {!workspaceDossier && <label>Evidence dossier (optional)
      <input type="file" accept=".json,application/json" onChange={event => {
        const file = event.target.files?.[0];
        const sequence = ++fileSequence.current;
        setDossier(null); setFileError(null);
        if (!file) return;
        if (file.size > 2_000_000) { setFileError("Dossier exceeds the 2 MB limit."); return; }
        void file.text().then(text => {
          const value: unknown = JSON.parse(text);
          if (fileSequence.current === sequence) setDossier(value);
        }).catch(() => { if (fileSequence.current === sequence) setFileError("Could not read dossier JSON."); });
      }}/>
    </label>}
    {workspaceProposals && <p>Using the external proposal history from Evidence Workspace.</p>}
    {workspaceDossier ? <p>Using the reviewed dossier from Evidence Workspace.</p> : dossier !== null && <p className="muted small">Open Evidence to review claims; selecting a dossier does not accept its claims.</p>}
    <label>Factor run record (optional)<input type="file" accept=".json" onChange={event => {
      const file = event.target.files?.[0];
      const sequence = ++fileSequence.current;
      setFactorRecord(null); setFileError(null);
      if (!file) return;
      if (file.size > 8_000_000) { setFileError("Factor record exceeds the 8 MB limit."); return; }
      void file.text().then(text => {
        const value: unknown = JSON.parse(text);
        if (fileSequence.current === sequence) setFactorRecord(value);
      }).catch(() => { if (fileSequence.current === sequence) setFileError("Could not read factor record JSON."); });
    }}/></label>
    {fileError && <p role="alert">{fileError}</p>}
    {request.status === "loading" && <p role="status">Finding questions…</p>}
    {request.status === "error" && <><p role="alert">{request.message}</p><button type="button" onClick={request.retry}>Retry questions</button></>}
    {request.status === "ready" && <>
      {[...project.alternatives.map(a => ({ id: a.id, title: a.name })), { id: null, title: "Model-wide" }].map(group => {
        const items = request.result.questions.filter(q => group.id === null ? !project.alternatives.some(a => a.id === q.alternative_id) : q.alternative_id === group.id).toSorted((a, b) => questionOrder(a.code) - questionOrder(b.code));
        if (!items.length) return null;
        return <section key={group.id ?? "model"}><h3>{group.id ? <CompanyName id={group.id}>{group.title}</CompanyName> : group.title}</h3><ul>{items.map((q, index) =>
            <li key={`${q.code}-${q.alternative_id ?? ""}-${q.criterion_id ?? ""}-${q.requirement_id ?? ""}-${String(index)}`}>
              {q.criterion_id && <p className="muted small">{project.criteria.find(c => c.id === q.criterion_id)?.name ?? q.criterion_id}</p>}
              <strong>{q.code === "UNREVIEWED_CLAIM" ? `Should this ${project.criteria.find(c => c.id === q.criterion_id)?.name ?? "evidence"} claim be accepted, corrected or rejected?` : q.code === "OUTDATED_CLAIM" ? `Is this ${project.criteria.find(c => c.id === q.criterion_id)?.name ?? "evidence"} claim still current?` : questionText(q.question, workspaceDossier)}</strong><p>{q.code === "SMAA_INPUT_TO_CHECK" ? q.why.split(". Input:")[0] : questionText(q.why, workspaceDossier)}</p><p>{questionText(q.evidence, workspaceDossier)}</p>
              <InfoDisclosure label="Question details"><code>{q.code}</code> · {q.question}<br/>{q.why}<br/>{q.evidence}</InfoDisclosure>
              {workspaceDossier?.project_fingerprint === context.fingerprint && <span className="muted small">{workspaceDossier.claims.filter(c => c.alternative_id === q.alternative_id && c.criterion_id === q.criterion_id).map(c => <span key={c.id}>{c.source.name} · {c.source.date} </span>)}</span>}
              {q.measurement_range && <details><summary>Measurement range analysis</summary>
                <p>Only this measurement varies. A stated range is not a probability distribution.</p>
                <p>Current rank: {q.measurement_range.baseline_rank}. {q.measurement_range.baseline_class_id && `Current class: ${q.measurement_range.baseline_class_id}.`}</p>
                <ul aria-label="Range witnesses">{q.measurement_range.witnesses.map((w, k) => <li key={k}>
                  At {displayNumber(w.measurement)}: rank {w.rank}{w.class_id ? `, class ${w.class_id}` : ""}.
                </li>)}</ul>
                <p>Analytical boundary contacts (rounded; touching a boundary need not change the result):</p>
                <ul aria-label="Range boundary contacts">{q.measurement_range.boundary_contacts.map((c, k) => <li key={k}>
                  {c.kind === "rank" ? "Rank comparison with" : "Class boundary for"} {c.reference_id}: {displayNumber(c.lower)}{c.lower !== c.upper ? ` to ${displayNumber(c.upper)}` : ""}.
                </li>)}</ul>
                <ul>{q.measurement_range.limitations.map(s => <li key={s}>{s}</li>)}</ul>
              </details>}
              <button type="button" onClick={() => onOpenTab((q.code.startsWith("MODEL_") || q.code === "DERIVED_FACTOR_ASSUMPTION") ? "measurements" : q.group === "evidence_quality" ? "evidence" : (q.code.startsWith("PROXY_") ? { tab: "compare" as EditorTab, label: "Open proxy comparison" } : DESTINATIONS[q.code])?.tab ?? "measurements")}>
                {(q.code.startsWith("MODEL_") || q.code === "DERIVED_FACTOR_ASSUMPTION") ? "Open calculations" : q.group === "evidence_quality" ? "Open evidence" : (q.code.startsWith("PROXY_") ? { tab: "compare" as EditorTab, label: "Open proxy comparison" } : DESTINATIONS[q.code])?.label ?? "Open measurements"}
              </button>
            </li>)}</ul>
        </section>;
      })}
      <Caveat id="questions" caption="No overall importance score is calculated."><strong>Checks included:</strong> {request.result.coverage.join(", ")}.<span role="list" aria-label="Questions limitations">{request.result.limitations.map(item => <span role="listitem" key={item}>{item} </span>)}</span></Caveat>
    </>}
  </section>;
}
