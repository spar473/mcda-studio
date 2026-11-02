import { useCallback, useRef, useState } from "react";
import { api } from "../api/client";
import type { ArtifactBinding, Project, ProjectCopyReceipt } from "../api/types";
import { canonical } from "../state/analysisContext";
import { useAnalysisRequest } from "../state/useAnalysisRequest";

const short = (fingerprint: string) => fingerprint.slice(0, 12);

/** Python verifies the artifact and relates it to the current project by exact fingerprints only. */
export function ArtifactBindingStatus({ project, fingerprint, artifact, label }: {
  project: Project; fingerprint: string; artifact: unknown; label: string;
}) {
  const [receipt, setReceipt] = useState<ProjectCopyReceipt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sequence = useRef(0);
  const key = canonical({ fingerprint, artifact, receipt });
  const load = useCallback(async (signal: AbortSignal) => {
    const result = await api.bindArtifact(project, artifact, receipt, signal);
    if (result.current_fingerprint !== fingerprint) throw Error("Provenance check does not match this project revision.");
    return result;
  }, [project, fingerprint, artifact, receipt]);
  const request = useAnalysisRequest(key, true, load);
  return <section aria-label={`${label} provenance`}>
    <h4>Relationship to the current project</h4>
    {request.status === "loading" && <p role="status">Checking provenance…</p>}
    {request.status === "error" && <><p role="alert">{request.message}</p><button type="button" onClick={request.retry}>Retry provenance check</button></>}
    {request.status === "ready" && <Relationship binding={request.result}/>}
    <label>Copy receipt (optional)
      <input type="file" accept=".json,application/json" onChange={event => {
        const file = event.target.files?.[0];
        const current = ++sequence.current;
        setReceipt(null); setError(null);
        if (!file) return;
        if (file.size > 1_000_000) { setError("Copy receipt exceeds the 1 MB limit."); return; }
        void file.text().then(text => {
          const parsed = JSON.parse(text) as ProjectCopyReceipt;
          if (sequence.current === current) setReceipt(parsed);
        }).catch(() => { if (sequence.current === current) setError("Could not read copy receipt JSON."); });
      }}/>
    </label>
    {error && <p role="alert">{error}</p>}
    <p>A copy receipt is issued when an import stores a project under a new ID. It records that single change; it never makes different fingerprints equal or rebinds earlier evidence. Checksums detect accidental changes. They do not authenticate reviewers or establish that evidence or calculations are accurate.</p>
  </section>;
}

function Relationship({ binding }: { binding: ArtifactBinding }) {
  const receipt = binding.copy_receipt;
  return <>
    <p role="status">{binding.relationship === "compiled"
      ? "The current project is exactly this artifact's compiled project (identical fingerprint)."
      : binding.relationship === "source"
        ? "The current project is this artifact's original project, before compilation."
        : binding.relationship === "verified_copy" && receipt
          ? `The current project is a verified separate copy of this artifact's compiled project. Import replaced project ID ${receipt.original_project_id} with ${receipt.copy_project_id}; the copy receipt shows nothing else differs. The two fingerprints remain different and both are recorded.`
          : "The current project matches neither this artifact's original nor its compiled project. The artifact remains available for historical inspection only; actions that need a matching project are blocked. If this project was imported as a separate copy of the compiled project, select the copy receipt issued on import."}</p>
    <p>Fingerprints: original {short(binding.source_fingerprint)}…, compiled {short(binding.compiled_fingerprint)}…, current {short(binding.current_fingerprint)}….</p>
  </>;
}
