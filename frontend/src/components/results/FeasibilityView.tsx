import { RESET_DOWNLOAD, useTrialDownloadGuard } from "../WeightTrialGate";
import { useRef, useState } from "react";
import { api } from "../../api/client";
import type { AlternativeFeasibility, FeasibilityResult, Project } from "../../api/types";
import { InfoDisclosure } from "../InfoDisclosure";
import { displayNumber } from "./numberDisplay";
import { saveDownload } from "./downloads";
import { CompanyName, companyRow, useCompanyExploration } from "../companyExploration";

/** How each status reads; unknown is never shown as pass or fail. */
export const STATUS_TEXT: Record<AlternativeFeasibility["status"], string> = { pass: "passes", fail: "fails", unknown: "unknown" };

export function requirementReason(check: AlternativeFeasibility["checks"][number], result: Pick<FeasibilityResult, "requirements">): string {
  const requirement = result.requirements.find(r => r.id === check.requirement_id);
  if (!requirement || check.measurement == null) return check.reason;
  if (requirement.kind === "bound") {
    const measurement = typeof check.measurement === "number" ? displayNumber(check.measurement) : check.measurement;
    const limits = [requirement.minimum == null ? null : `${requirement.minimum_inclusive ? "at least" : "more than"} ${displayNumber(requirement.minimum)}`,
      requirement.maximum == null ? null : `${requirement.maximum_inclusive ? "at most" : "less than"} ${displayNumber(requirement.maximum)}`].filter(Boolean);
    return `${measurement} ${requirement.unit ?? ""}; requires ${limits.join(" and ")} ${requirement.unit ?? ""}`;
  }
  const measurement = typeof check.measurement === "number" ? displayNumber(check.measurement) : check.measurement;
  if (check.status === "unknown") return `${requirement.name}: measurement could not be checked`;
  return check.status === "fail"
    ? `${measurement} is outside ${requirement.name} (${requirement.allowed.join(", ")})`
    : `${measurement} meets ${requirement.name}`;
}

/** One alternative's overall status, with the requirements behind it. */
export function StatusBadge({ result, alternativeId }: { result: FeasibilityResult; alternativeId: string }) {
  const row = result.alternatives.find((a) => a.alternative_id === alternativeId);
  if (!row) return null;
  const names = Object.fromEntries(result.requirements.map((r) => [r.id, r.name]));
  const behind = row.status === "fail" ? row.failed : row.status === "unknown" ? row.unknown : [];
  return <span className={`feasibility ${row.status}`} data-feasibility={row.status}
    title={row.checks.filter((c) => c.status !== "pass").map((c) => `${names[c.requirement_id] ?? c.requirement_id}: ${requirementReason(c, result)}`).join("\n")}>
    {STATUS_TEXT[row.status]}{behind.length > 0 && ` (${behind.map((id) => names[id] ?? id).join(", ")})`}
  </span>;
}

/** Feasibility beside a ranking: every alternative, in project order, with its status and reasons.
 * It hides and reorders nothing. With the project, it offers its own JSON and CSV downloads. */
export function FeasibilityView({ result, project }: { result: FeasibilityResult; project?: Project }) {
  const exploration = useCompanyExploration();
  const downloadGuard = useTrialDownloadGuard();
  const names = Object.fromEntries(result.requirements.map((r) => [r.id, r.name]));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  async function download(format: "json" | "csv") {
    const ticket = downloadGuard.ticket();
    if (ticket === null) return;
    if (!project) return;
    controller.current?.abort();
    const c = new AbortController(); controller.current = c;
    setBusy(true); setError(null);
    try {
      const file = await api.exportFeasibility({ project: structuredClone(project), expected_project_fingerprint: result.project_fingerprint, format }, c.signal);
      if (!c.signal.aborted && downloadGuard.permits(ticket)) saveDownload(file.blob, file.filename);
    } catch (e: unknown) {
      if (!c.signal.aborted && downloadGuard.permits(ticket)) setError(e instanceof Error ? e.message : String(e));
    } finally { if (controller.current === c) setBusy(false); }
  }
  return <div className="feasibility-view" aria-label="Feasibility">
    <p className="note" aria-label="Feasibility label">{result.label[0]?.toUpperCase()}{result.label.slice(1)}. It does not change any ranking.</p>
    <div className="table-scroll" tabIndex={0}><table className="grid" aria-label="Feasibility by alternative">
      <thead><tr><th>Alternative</th><th>Overall</th>{result.requirements.map((r) => <th key={r.id}>{r.name}</th>)}</tr></thead>
      <tbody>{result.alternatives.map((a) => <tr key={a.alternative_id} data-alternative-id={a.alternative_id} {...companyRow(exploration, a.alternative_id)}>
        <th scope="row"><CompanyName id={a.alternative_id}>{a.name}</CompanyName></th>
        <td data-feasibility={a.status}>{STATUS_TEXT[a.status]}</td>
        {a.checks.map((c) => <td key={c.requirement_id} data-feasibility={c.status} title={requirementReason(c, result)}>
          {STATUS_TEXT[c.status]}<div className="muted small">{requirementReason(c, result)} <InfoDisclosure label="Requirement details">{c.reason}</InfoDisclosure></div></td>)}
      </tr>)}</tbody>
    </table></div>
    {project && <p className="results-controls">
      <button type="button" disabled={busy || downloadGuard.disabled} onClick={() => void download("json")}>Download feasibility JSON</button>
      <button type="button" disabled={busy || downloadGuard.disabled} onClick={() => void download("csv")}>Download feasibility CSV</button>
    </p>}
    {downloadGuard.disabled && <p className="muted small">{RESET_DOWNLOAD}</p>}
    {error && <p role="alert">{error}</p>}
    <p className="muted small">{result.summary.map((s) => `${names[s.requirement_id] ?? s.requirement_id}: ${String(s.passed)} pass, ${String(s.failed)} fail, ${String(s.unknown)} unknown`).join(" · ")}</p>
  </div>;
}
