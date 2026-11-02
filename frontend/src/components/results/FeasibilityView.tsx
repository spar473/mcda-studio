import { useRef, useState } from "react";
import { api } from "../../api/client";
import type { AlternativeFeasibility, FeasibilityResult, Project } from "../../api/types";
import { saveDownload } from "./downloads";

/** How each status reads; unknown is never shown as pass or fail. */
export const STATUS_TEXT: Record<AlternativeFeasibility["status"], string> = { pass: "passes", fail: "fails", unknown: "unknown" };

/** One alternative's overall status, with the requirements behind it. */
export function StatusBadge({ result, alternativeId }: { result: FeasibilityResult; alternativeId: string }) {
  const row = result.alternatives.find((a) => a.alternative_id === alternativeId);
  if (!row) return null;
  const names = Object.fromEntries(result.requirements.map((r) => [r.id, r.name]));
  const behind = row.status === "fail" ? row.failed : row.status === "unknown" ? row.unknown : [];
  return <span className={`feasibility ${row.status}`} data-feasibility={row.status}
    title={row.checks.filter((c) => c.status !== "pass").map((c) => `${names[c.requirement_id] ?? c.requirement_id}: ${c.reason}`).join("\n")}>
    {STATUS_TEXT[row.status]}{behind.length > 0 && ` (${behind.map((id) => names[id] ?? id).join(", ")})`}
  </span>;
}

/** Feasibility beside a ranking: every alternative, in project order, with its status and reasons.
 * It hides and reorders nothing. With the project, it offers its own JSON and CSV downloads. */
export function FeasibilityView({ result, project }: { result: FeasibilityResult; project?: Project }) {
  const names = Object.fromEntries(result.requirements.map((r) => [r.id, r.name]));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  async function download(format: "json" | "csv") {
    if (!project) return;
    controller.current?.abort();
    const c = new AbortController(); controller.current = c;
    setBusy(true); setError(null);
    try {
      const file = await api.exportFeasibility({ project: structuredClone(project), expected_project_fingerprint: result.project_fingerprint, format }, c.signal);
      if (!c.signal.aborted) saveDownload(file.blob, file.filename);
    } catch (e: unknown) {
      if (!c.signal.aborted) setError(e instanceof Error ? e.message : String(e));
    } finally { if (controller.current === c) setBusy(false); }
  }
  return <div className="feasibility-view" aria-label="Feasibility">
    <p className="note" aria-label="Feasibility label">{result.label[0]?.toUpperCase()}{result.label.slice(1)}. It does not change any ranking.</p>
    <div className="table-scroll" tabIndex={0}><table className="grid" aria-label="Feasibility by alternative">
      <thead><tr><th>Alternative</th><th>Overall</th>{result.requirements.map((r) => <th key={r.id}>{r.name}</th>)}</tr></thead>
      <tbody>{result.alternatives.map((a) => <tr key={a.alternative_id} data-alternative-id={a.alternative_id}>
        <th scope="row">{a.name}</th>
        <td data-feasibility={a.status}>{STATUS_TEXT[a.status]}</td>
        {a.checks.map((c) => <td key={c.requirement_id} data-feasibility={c.status} title={c.reason}>
          {STATUS_TEXT[c.status]}<div className="muted small">{c.reason}</div></td>)}
      </tr>)}</tbody>
    </table></div>
    {project && <p className="results-controls">
      <button type="button" disabled={busy} onClick={() => void download("json")}>Download feasibility JSON</button>
      <button type="button" disabled={busy} onClick={() => void download("csv")}>Download feasibility CSV</button>
    </p>}
    {error && <p role="alert">{error}</p>}
    <p className="muted small">{result.summary.map((s) => `${names[s.requirement_id] ?? s.requirement_id}: ${String(s.passed)} pass, ${String(s.failed)} fail, ${String(s.unknown)} unknown`).join(" · ")}</p>
  </div>;
}
