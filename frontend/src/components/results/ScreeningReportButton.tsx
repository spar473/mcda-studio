import { useRef, useState, useLayoutEffect } from "react";
import { api } from "../../api/client";
import type { EvidenceDossier, Project } from "../../api/types";
import type { AnalysisContext } from "../../state/analysisContext";
import { RESET_DOWNLOAD, useTrialDownloadGuard } from "../WeightTrialGate";
import { saveDownload } from "./downloads";

/** Downloads one self-contained HTML screening report written by Python. Looking never changes the
 * project; a what-if trial blocks it with the same Reset message as every other download, and a
 * Reset or a change of revision permanently invalidates an earlier in-flight request. */
export function ScreeningReportButton({ project, context, dossier, trial }: {
  project: Project; context: AnalysisContext; dossier?: EvidenceDossier | null; trial: { active: boolean; generation: number };
}) {
  const guard = useTrialDownloadGuard(trial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  useLayoutEffect(() => () => { controller.current?.abort(); }, [context.fingerprint, context.configuration.scenario_id]);
  async function download() {
    const ticket = guard.ticket();
    if (ticket === null || trial.active) return;
    controller.current?.abort();
    const mine = new AbortController(); controller.current = mine;
    setBusy(true); setError(null);
    try {
      const file = await api.exportScreeningReport({ project: structuredClone(project), configuration: context.configuration, ...(dossier ? { dossier } : {}) }, context.fingerprint, mine.signal);
      if (mine.signal.aborted || !guard.permits(ticket) || controller.current !== mine) return;
      saveDownload(file.blob, file.filename);
    } catch (failure: unknown) {
      if (!mine.signal.aborted && guard.permits(ticket)) setError(failure instanceof Error ? failure.message : String(failure));
    } finally { if (controller.current === mine) setBusy(false); }
  }
  return <div className="results-controls" aria-label="Screening report">
    <button type="button" disabled={trial.active || guard.disabled || busy || project.alternatives.length === 0} onClick={() => void download()}>Download screening report</button>
    {trial.active && <span className="muted small">{RESET_DOWNLOAD}</span>}
    {busy && <span role="status">Preparing the report…</span>}
    {error && <p role="alert">{error}</p>}
  </div>;
}
