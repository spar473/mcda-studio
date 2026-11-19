import type { Project, ScreeningSummary, ScreeningSummaryRow } from "../../api/types";
import { CompanyName, companyRow, ratingExplanation, useCompanyExploration } from "../companyExploration";
import { RatingHint } from "../RatingHint";

const COLUMN_LABELS: Record<ScreeningSummary["columns"][number]["column"], string> = {
  classes: "Class", requirements: "Requirements", fragility: "Closest change", open_questions: "Open questions",
};
import { displayNumber as fixed } from "./numberDisplay";
import { Caveat } from "../InfoDisclosure";

function requirementsText(row: ScreeningSummaryRow, names: Record<string, string>): string {
  const r = row.requirements;
  if (!r) return "";
  const list = (ids: string[]) => ids.map((id) => names[id] ?? id).join(", ");
  if (r.status === "fail") return `Fails: ${list(r.failed)}`;
  if (r.status === "unknown") return `Unknown: ${list(r.unknown)}`;
  return "Meets all";
}

function closestChange(row: ScreeningSummaryRow, names: Record<string, string>, classes: Record<string, string>): string {
  const f = row.fragility;
  if (!f) return "";
  if (f.status === "tied") return `Tied now with ${f.tied_with.map((id) => names[id] ?? id).join(", ")}`;
  if (f.status === "none") return "No one-way change in range";
  const sign = f.direction === "raise" ? "+" : "−";
  const what = f.kind === "rank" ? `swaps with ${names[f.other_alternative_id ?? ""] ?? f.other_alternative_id}`
    : `moves to ${classes[f.class_after_id ?? ""] ?? f.class_after_id}`;
  return `${sign}${fixed(f.weight_change ?? 0)} of total weight on ${f.criterion_name} → ${what}`;
}

/** The engine's screening summary as a table: one row per alternative, nothing computed here. */
export function ScreeningSummaryView({ summary, project, hideOpenQuestions = false }: { summary: ScreeningSummary; project: Project; hideOpenQuestions?: boolean }) {
  const exploration = useCompanyExploration();
  if (summary.status === "unavailable") return <p role="status" aria-label="Screening summary unavailable">{summary.reason}</p>;
  const names = Object.fromEntries(project.alternatives.map((a) => [a.id, a.name]));
  const requirementNames = Object.fromEntries((project.requirements ?? []).map((r) => [r.id, r.name]));
  const classNames = Object.fromEntries((project.sorting?.classes ?? []).map((c) => [c.id, c.name]));
  const shown = new Set(summary.columns.filter((c) => c.available && !(hideOpenQuestions && c.column === "open_questions")).map((c) => c.column));
  const absent = summary.columns.filter((c) => !c.available && !(hideOpenQuestions && c.column === "open_questions"));
  return <div className="screening-summary">
    <div className="table-scroll" tabIndex={0}>
      <table className="grid" aria-label="Screening summary">
        <thead><tr>
          <th scope="col">Rank</th><th scope="col">Alternative</th><th scope="col">Overall value</th>
          {shown.has("classes") && <th scope="col">Class (margin)</th>}
          {shown.has("requirements") && <th scope="col">Requirements</th>}
          <th scope="col">Largest contributions</th>
          {shown.has("fragility") && <th scope="col" title={summary.fragility_definition}>Closest change</th>}
          {shown.has("open_questions") && <th scope="col">Open questions</th>}
        </tr></thead>
        <tbody>{summary.rows.map((row) => <tr key={row.alternative_id} {...companyRow(exploration, row.alternative_id)}>
          <td>{row.rank}</td>
          <th scope="row"><CompanyName id={row.alternative_id}>{row.name}</CompanyName></th>
          <td>{fixed(row.value)}</td>
          {shown.has("classes") && <td>{row.class_name}{row.margin != null && ` (${fixed(row.margin)})`}</td>}
          {shown.has("requirements") && <td data-requirements={row.requirements?.status}>{requirementsText(row, requirementNames)}</td>}
          <td>{row.drivers.length ? row.drivers.map((driver, index) => <span className="summary-driver" key={driver.criterion_id}><RatingHint
            text={ratingExplanation(project, row.alternative_id, driver.criterion_id, driver.contribution)}>{driver.name} {fixed(driver.contribution)}{index < row.drivers.length - 1 ? ";" : ""}</RatingHint>{index < row.drivers.length - 1 ? " " : ""}</span>) : "none"}</td>
          {shown.has("fragility") && <td>{closestChange(row, names, classNames)}</td>}
          {shown.has("open_questions") && <td>{row.open_questions}</td>}
        </tr>)}</tbody>
      </table>
    </div>
    <Caveat id="screening" caption="Preference values under this profile; not probabilities or predictions.">{summary.label} {summary.fragility_definition}
      {!hideOpenQuestions && summary.project_open_questions ? ` ${String(summary.project_open_questions)} open question(s) concern the whole project.` : ""}</Caveat>
    {absent.length > 0 && <p className="muted small" aria-label="Summary columns not shown">Not shown: {absent.map((c) => `${COLUMN_LABELS[c.column]} (${c.reason})`).join("; ")}</p>}
  </div>;
}
