import type { DecisionImpact, Project } from "../api/types";
import { CompanyName } from "./companyExploration";

const REASONS: Record<string, string> = {
  judgement_only: "rests on judgement alone", disputed: "disputed", outdated: "its source may be out of date",
  missing: "no accepted claim supports it", proposal_pending: "a model proposal awaits review",
  proposal_rejected: "a model proposal was rejected", tool_human_disagreement: "tools and people disagree",
};
const TIERS = {
  leader_or_class: "Could change the leader or a class",
  rank: "Could change a rank, but not the leader or a class",
  none: "No other label changes a rank, the leader or a class",
} as const;

/** Cells in the order Python gives them: the ones that could change the decision first. Every label
 * list and reason comes from the opt-in decision-impact route; nothing is computed here. */
export function DecisionImpactList({ project, impact }: { project: Project; impact: DecisionImpact }) {
  if (impact.status !== "available") return <p role="status">{impact.reason}</p>;
  const criterion = (id: string) => project.criteria.find(c => c.id === id)?.name ?? id;
  return <section aria-label="Decision impact" className="decision-impact">
    <h3>Sorted by decision impact</h3>
    <p className="muted small">{impact.label}</p>
    <p className="muted small">{impact.analysed_cells} rated cells checked.</p>
    <ol>{impact.cells.map(cell => <li key={`${cell.alternative_id}:${cell.criterion_id}`}>
      <strong><CompanyName id={cell.alternative_id}>{cell.alternative_name}</CompanyName> · {criterion(cell.criterion_id)}</strong>
      <p>Currently “{cell.current_label}”. {TIERS[cell.tier]}.</p>
      {cell.leader_labels.length > 0 && <p>Changes the leader: {cell.leader_labels.join(", ")}.</p>}
      {cell.target_class_labels.length > 0 && <p>Changes {cell.alternative_name}’s class: {cell.target_class_labels.join(", ")}.</p>}
      {cell.target_rank_labels.length > 0 && <p>Changes {cell.alternative_name}’s rank: {cell.target_rank_labels.join(", ")}.</p>}
      {cell.any_rank_labels.length > 0 && <p>Changes someone’s rank: {cell.any_rank_labels.join(", ")}.</p>}
      {cell.smallest_changes.length > 0 && <p>Nearest label that changes something: {cell.smallest_changes.join(" or ")}{cell.ordered ? "" : " (the listed order, not a ranking of labels)"}.</p>}
      <p className="muted small">{cell.reasons.length ? cell.reasons.map(r => REASONS[r] ?? r).join("; ") : "No open reason"}.</p>
    </li>)}</ol>
    <ul>{impact.limitations.map(item => <li key={item} className="muted small">{item}</li>)}</ul>
  </section>;
}
