import { useState } from "react";
import type { EvidenceInspection, Project } from "../api/types";
import { InfoDisclosure } from "./InfoDisclosure";
import { displayNumber } from "./results/numberDisplay";
import { CompanyName } from "./companyExploration";

export function EvidenceClaims({ result, project, stale, onReview, onMeasurement }: {
  result: EvidenceInspection; project: Project; stale: boolean;
  onReview: (id: string) => void; onMeasurement: (alternative: string, criterion: string) => void;
}) {
  const [filter, setFilter] = useState("All");
  const disputed = (c: EvidenceInspection["dossier"]["claims"][number]) => result.preview.conflicting_cells.some(cell => cell.alternative_id === c.alternative_id && cell.criterion_id === c.criterion_id);
  const outdated = (id: string) => result.preview.outdated_claims.includes(id);
  const judgement = (c: EvidenceInspection["dossier"]["claims"][number]) => /^Judgement\s*:/i.test(c.source.description);
  const shown = result.dossier.claims.filter(c => filter === "All" || (filter === "Disputed" ? disputed(c) : filter === "Outdated" ? outdated(c.id) : judgement(c)));
  const companies = [...new Set(result.dossier.claims.map(c => c.alternative_id))];
  const number = (value: string | number | null | undefined) => typeof value === "number" ? displayNumber(value) : value;
  return <section aria-label="Evidence claims">
    <div role="group" aria-label="Filter claims">{["All", "Disputed", "Outdated", "Judgement"].map(label => <button key={label} type="button" aria-pressed={filter === label} onClick={() => setFilter(label)}>{label}</button>)}</div>
    {companies.map(id => {
      const claims = shown.filter(c => c.alternative_id === id);
      if (!claims.length) return null;
      const company = project.alternatives.find(a => a.id === id);
      return <section key={id} className="evidence-company">
        <h3>{company ? <CompanyName id={id}>{company.name}</CompanyName> : id}</h3>
        <details open={result.dossier.claims.some(c => c.alternative_id === id && disputed(c))}>
        <summary aria-label={`Claims for ${company?.name ?? id}`}>Claims</summary>
        {[...new Set(claims.map(c => c.criterion_id))].map(criterion => <section key={criterion}>
          <h4>{project.criteria.find(c => c.id === criterion)?.name ?? criterion}</h4>
          <ul>{claims.filter(c => c.criterion_id === criterion).map((c, k) => <li key={`${c.id}-${k}`} data-claim-id={c.id}>
            <p><strong>{c.review?.status ?? "unreviewed"}</strong>{disputed(c) && " · Disputed"}{outdated(c.id) && " · Outdated"}{judgement(c) && " · Judgement"}</p>
            <p>Proposed {number(c.value)} {c.unit}.</p>
            {c.review?.status === "corrected" && <p>Accepted correction: {number(c.review.corrected_value)} {c.unit}. Original proposal retained.</p>}
            {c.uncertainty_lower != null && <p>Stated range: {number(c.uncertainty_lower)} to {number(c.uncertainty_upper)}; this is not a probability distribution.</p>}
            <p>Source: {/^https?:\/\//i.test(c.source.reference) ? <a href={c.source.reference} target="_blank" rel="noreferrer">{c.source.name}</a> : c.source.name} · {c.source.classification} · {c.source.date}. {c.source.description}</p>
            <InfoDisclosure label={`Claim details for ${c.source.name}`}>
              <code>{c.id}</code> · Reference: {c.source.reference} {c.source.location}<br/>
              Proposed by {c.origin.proposed_by} ({c.origin.kind}) {c.origin.tool_id} {c.origin.tool_version}
              {c.review && <> · Reviewed by {c.review.reviewer} at {c.review.reviewed_at}. {c.review.note}</>}
            </InfoDisclosure>
            <button type="button" disabled={stale || result.dossier.claims.filter(other => other.id === c.id).length !== 1} onClick={() => onReview(c.id)}>Review {c.source.name}</button>
            <button type="button" onClick={() => onMeasurement(c.alternative_id, c.criterion_id)}>Inspect affected measurement</button>
          </li>)}</ul>
        </section>)}
        </details>
      </section>;
    })}
    {!shown.length && <p>No claims match this filter.</p>}
  </section>;
}
