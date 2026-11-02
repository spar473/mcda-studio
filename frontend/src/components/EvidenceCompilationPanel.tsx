import { useLayoutEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { EvidenceCompilation, EvidenceInspection, Project } from "../api/types";
import { canonical } from "../state/analysisContext";
import { saveDownload } from "./results/downloads";

function download(value: unknown, name: string) {
  saveDownload(new Blob([JSON.stringify(value, null, 2) + "\n"], { type: "application/json" }), name);
}

/** Current versus compiled measurement for every accepted or corrected claim, with its support. */
export function MeasurementChanges({ project, preview, dossier, label, before = "Current measurement" }: {
  project: Project; preview: EvidenceInspection["preview"]; dossier: EvidenceInspection["dossier"]; label: string; before?: string;
}) {
  if (preview.changes.length === 0) return <p>No accepted or corrected claim changes a measurement.</p>;
  return <table aria-label={label}>
    <thead><tr><th scope="col">Alternative</th><th scope="col">Criterion</th><th scope="col">Unit</th><th scope="col">{before}</th><th scope="col">Compiled value</th><th scope="col">Supporting claim</th></tr></thead>
    <tbody>{preview.changes.map(change => {
      const claim = dossier.claims.find(c => c.id === change.claim_id);
      const criterion = project.criteria.find(c => c.id === change.criterion_id);
      return <tr key={`${change.alternative_id}-${change.criterion_id}`}>
        <td>{project.alternatives.find(a => a.id === change.alternative_id)?.name ?? change.alternative_id}</td>
        <td>{criterion?.name ?? change.criterion_id}</td>
        <td>{criterion?.scale?.unit ?? "—"}</td>
        <td>{change.before ?? "missing"}</td>
        <td>{change.after}</td>
        <td>{change.claim_id} · {claim?.review?.status ?? "unreviewed"}{claim?.review ? ` by ${claim.review.reviewer}` : ""}{claim?.review?.status === "corrected" ? ` (proposed ${String(claim.value)})` : ""} · {claim?.source.name ?? "unknown source"}{claim?.outdated ? " · outdated" : ""}</td>
      </tr>;
    })}</tbody>
  </table>;
}

/** Acknowledge, compile in Python and export a separate copy; the current project never changes. */
export function EvidenceCompilationPanel({ project, fingerprint, inspection, contextKey, onHistoryExported }: {
  project: Project; fingerprint: string; inspection: EvidenceInspection; contextKey: string;
  onHistoryExported: () => void;
}) {
  const preview = inspection.preview;
  const [acknowledged, setAcknowledged] = useState<string | null>(null);
  const [compiled, setCompiled] = useState<{ key: string; bundle: EvidenceCompilation } | null>(null);
  const [failure, setFailure] = useState<{ key: string; message: string } | null>(null);
  const [compiling, setCompiling] = useState(false);
  // Any change of project, history, preview or review intent makes earlier candidates obsolete.
  const key = canonical({ contextKey, review: preview.review_digest, workspace: inspection.workspace.digest });
  const liveKey = useRef(key);
  useLayoutEffect(() => { liveKey.current = key; }, [key]);
  const bundle = compiled?.key === key ? compiled.bundle : null;
  const blocked = preview.issues.some(i => i.severity === "error");
  const compile = async () => {
    if (acknowledged !== key || compiling || blocked) return;
    const captured = key;
    setFailure(null); setCompiling(true);
    try {
      const result = await api.compileEvidence(project, inspection.workspace, preview.review_digest, inspection.workspace.digest);
      if (liveKey.current !== captured) return;
      if (result.preview.project_fingerprint !== fingerprint || result.preview.review_digest !== preview.review_digest || result.workspace.digest !== inspection.workspace.digest) throw Error("Compiled evidence does not match the acknowledged preview.");
      setCompiled({ key: captured, bundle: result });
    } catch (e) {
      if (liveKey.current === captured) setFailure({ key: captured, message: e instanceof ApiError
        ? [e.message, ...e.details.map(detail => detail.message)].filter(Boolean).join(" ")
        : e instanceof Error ? e.message : String(e) });
    } finally { setCompiling(false); }
  };
  return <section aria-label="Evidence compilation">
    <h3>Compile reviewed evidence into a separate copy</h3>
    <p>Accepting a claim records a review of a source; it does not change any measurement. Compilation is a separate step: Python copies the project and replaces only the measurements below with accepted or corrected claim values. The current project, its saved file and its undo history stay unchanged.</p>
    <MeasurementChanges project={project} preview={preview} dossier={inspection.dossier} label="Measurement changes for compilation"/>
    <p>Not resolved by compilation: {preview.unreviewed_claims.length} unreviewed and {preview.outdated_claims.length} outdated claims, {preview.conflicting_cells.length} cells with differing unrejected claims and {preview.missing_measurements.length} missing measurements. Unreviewed and rejected claims never fill a measurement; missing measurements stay missing, not zero.</p>
    {blocked && <p>Compilation is blocked until the errors listed above are resolved.</p>}
    {!blocked && preview.changes.length > 0 && <>
      <label><input type="checkbox" checked={acknowledged === key} onChange={e => setAcknowledged(e.target.checked ? key : null)}/>I reviewed every measurement change for the separate copy</label>
      <button type="button" disabled={acknowledged !== key || compiling} onClick={() => { void compile(); }}>Compile reviewed copy</button>
    </>}
    {failure?.key === key && <p role="alert">{failure.message}</p>}
    {bundle && <section aria-label="Compiled evidence copy">
      <p>Compiled in Python from the acknowledged preview and review history. Export both files: the project copy for analysis, and the bundle that retains the original project, original dossier, appended reviews, exact preview and compiled copy for later verification.</p>
      <button type="button" onClick={() => download(bundle.project, "evidence-compiled-project.json")}>Export compiled project copy</button>
      <button type="button" onClick={() => { download(bundle, "evidence-compilation.json"); onHistoryExported(); }}>Export evidence compilation bundle</button>
      <p>Import the project copy from Projects. If the original project is still in the library, choose Import as a separate copy and download the copy receipt it offers: the copy gets a new project ID, so only that receipt relates it to this bundle.</p>
    </section>}
  </section>;
}
