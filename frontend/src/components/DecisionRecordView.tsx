import type { DecisionRecordV1, DecisionRecordV2, Project } from "../api/types";

const short = (digest: string) => `${digest.slice(0, 12)}…`;
const alternative = (project: Project, id: string | null | undefined) =>
  project.alternatives.find(a => a.id === id)?.name ?? id ?? "none";
const criterion = (project: Project, id: string) => project.criteria.find(c => c.id === id)?.name ?? id;

/** Read-only view of a verified record; names come from the record's own project snapshot. */
export function DecisionRecordView({ record, label }: { record: DecisionRecordV2 | DecisionRecordV1; label: string }) {
  if (record.version === 1) return <V1View record={record} label={label}/>;
  const d = record.decision;
  const p = record.project;
  const chosen = d.selected_alternative_id;
  const feasibility = record.feasibility.result?.alternatives.find(a => a.alternative_id === chosen);
  const traced = record.measurement_trace.filter(t => t.origin !== "entered");
  return <section aria-label={label}>
    <p>Version 2 record {short(record.digest)} · {d.owner} · {d.date} · project “{p.title}” ({short(record.project_fingerprint)})</p>
    <p><strong>{d.outcome === "selected" ? `Selected: ${alternative(p, chosen)}` : "Decision deferred: no alternative selected"}</strong></p>
    {chosen && <p>Feasibility of the selection: {record.feasibility.status === "no_requirements" ? "no mandatory requirements recorded"
      : record.feasibility.status === "unavailable" ? `check unavailable (${record.feasibility.issues.map(i => i.code).join(", ")})`
        : feasibility ? `${feasibility.status}${feasibility.failed.length ? ` — fails ${feasibility.failed.join(", ")}` : ""}${feasibility.unknown.length ? ` — unresolved ${feasibility.unknown.join(", ")}` : ""}` : "not reported"}.
      Failed or unresolved requirements are shown beside the choice; they are not overridden.</p>}
    <p>Rationale: {d.rationale}</p>
    <p>Alternatives considered: {d.alternatives_considered.map(id => alternative(p, id)).join(", ")}.</p>
    <p>Unresolved assumptions: {d.unresolved_assumptions.length ? d.unresolved_assumptions.join("; ") : "none recorded"}.</p>
    <p>Review triggers: {d.review_triggers.length ? d.review_triggers.join("; ") : "none recorded"}.</p>
    {record.predecessor && <p>Revises record {short(record.predecessor.digest)} (version {record.predecessor.version}) by {record.predecessor.owner} on {record.predecessor.date}: {record.predecessor.outcome === "selected" ? `selected ${alternative(p, record.predecessor.selected_alternative_id)}` : "deferred"}. Earlier rationale: {record.predecessor.rationale}</p>}
    <h4>Analyses</h4>
    <ul aria-label={`${label} analyses`}>{record.analyses.map((a, k) => <li key={k}>
      {a.configuration.method} · profile {a.configuration.weight_profile_id ?? "default"} · scenario {a.configuration.scenario_id ?? "Base"}: {a.status === "completed" && a.record ? `completed (record ${short(a.record.record_digest)})` : `unavailable — ${a.reason}`}
    </li>)}</ul>
    <p>Analyses use all of the project's alternatives. Values are preferences, not probabilities; SMAA-2 frequencies are not outcome probabilities.</p>
    <h4>Supporting artifacts</h4>
    {record.anchors.length === 0 ? <p>No compilation or calculation bundle is cited.</p> : <ul aria-label={`${label} artifacts`}>{record.anchors.map(a => <li key={a.artifact_digest}>
      {a.artifact_kind === "evidence_compilation" ? "Evidence compilation" : "Calculation bundle"} {short(a.artifact_digest)}: {a.relationship === "verified_copy" ? "receipt-verified copy of its compiled project" : "exact compiled project"}, anchored to {a.anchored_to === "record_project" ? "this record's project" : `the original project of ${short(a.anchor_artifact_digest ?? "")}`}.
    </li>)}</ul>}
    <h4>Measurement provenance</h4>
    <p>{traced.length} measurement(s) trace to a cited artifact; {record.measurement_trace.length - traced.length} were entered directly.</p>
    {traced.length > 0 && <table aria-label={`${label} measurement provenance`}>
      <thead><tr><th scope="col">Alternative</th><th scope="col">Criterion</th><th scope="col">Value</th><th scope="col">Source</th><th scope="col">Original value</th></tr></thead>
      <tbody>{traced.map(t => <tr key={`${t.alternative_id}-${t.criterion_id}`}>
        <td>{alternative(p, t.alternative_id)}</td><td>{criterion(p, t.criterion_id)}</td><td>{t.value}</td>
        <td>{t.origin === "evidence" ? `claim ${t.reference_id ?? ""}` : `calculation ${t.reference_id ?? ""} from ${t.inputs.join(", ")}`} in {short(t.artifact_digest ?? "")}</td>
        <td>{t.original_value ?? "missing"}</td>
      </tr>)}</tbody>
    </table>}
    {record.notices.length > 0 && <ul aria-label={`${label} notices`}>{record.notices.map((n, k) => <li key={k}>{n.code}: {n.message}</li>)}</ul>}
  </section>;
}

function V1View({ record, label }: { record: DecisionRecordV1; label: string }) {
  const d = record.decision;
  return <section aria-label={label}>
    <p>Version 1 record {short(record.digest)} · {d.owner} · {d.date} · project “{record.project.title}”</p>
    <p><strong>Selected: {alternative(record.project, d.chosen_alternative_id)}</strong></p>
    <p>Rationale: {d.rationale}</p>
    <p>Unresolved assumptions: {d.unresolved_assumptions.join("; ") || "none recorded"}. Review triggers: {d.review_triggers.join("; ") || "none recorded"}.</p>
    <p>{record.analyses.length} completed analysis record(s). {record.evidence ? "Includes an evidence snapshot (dossier and source project)." : "No evidence snapshot."} Version 1 records do not cite compilation bundles or trace measurements.</p>
  </section>;
}
