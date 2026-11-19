import { useCallback, useMemo, useState, type ReactNode } from "react";
import type { EvidenceDossier, Project, ScreeningDetails } from "../api/types";
import { canonical, resolveContext, type AnalysisContext } from "../state/analysisContext";
import { useScreeningDetails } from "../state/useScreeningDetails";
import { CompanyExplorationContext, ratingExplanation, type CompanyExploration } from "./companyExploration";
import { Caveat, InfoDisclosure } from "./InfoDisclosure";
import { Modal } from "./ui";
import { RatingHint } from "./RatingHint";
import { MessageText } from "./IssueText";
import { displayCompact, displayNumber } from "./results/numberDisplay";
import { requirementReason, STATUS_TEXT } from "./results/FeasibilityView";

export interface StudyEvidenceOffer { title: string; load: () => void }
export interface SensitivityDestination {
  criterionId: string; weight: number; context: AnalysisContext;
}
interface Props {
  project: Project; context: AnalysisContext; dossier: EvidenceDossier | null;
  studyEvidence: StudyEvidenceOffer | null;
  onSensitivity: (destination: SensitivityDestination) => void;
  children: ReactNode; blocked?: boolean;
}

/** Session-only exploration. No project edit, stored selection or URL state. */
export function CompanyExplorer({ project, context, dossier, studyEvidence, onSensitivity, children, blocked = false }: Props) {
  const [selected, setSelected] = useState<{ alternativeId: string; profileId?: string } | null>(null);
  const [tooltip, setTooltip] = useState<{ key: string; text: string; left: number; top: number } | null>(null);
  const sourceKey = canonical({ fingerprint: context.fingerprint, configuration: context.configuration });
  if (selected && (blocked || !project.alternatives.some(a => a.id === selected.alternativeId))) setSelected(null);
  const open = useCallback((alternativeId: string, profileId?: string) => {
    if (blocked) return;
    setTooltip(null); setSelected({ alternativeId, profileId });
  }, [blocked]);
  const clearHint = useCallback(() => setTooltip(null), []);
  const hint = useCallback((anchor: Element, alternativeId: string, criterionId: string, contribution: number) => {
    const rect = anchor.getBoundingClientRect();
    setTooltip({ key: sourceKey,
      text: ratingExplanation(project, alternativeId, criterionId, contribution),
      left: Math.max(8, Math.min(rect.left, window.innerWidth - Math.min(480, window.innerWidth - 16) - 8)),
      top: rect.bottom < window.innerHeight - 190 ? rect.bottom + 8 : Math.max(8, rect.top - 180),
    });
  }, [project, sourceKey]);
  const exploration = useMemo<CompanyExploration>(() => ({ open, hint, clearHint, blocked }), [open, hint, clearHint, blocked]);
  const close = () => setSelected(null);
  return <CompanyExplorationContext value={exploration}>
    <div className="company-exploration-content" inert={selected !== null}>
      {children}
      {tooltip?.key === sourceKey && !selected && <div className="rating-tooltip" role="tooltip" style={{ left: tooltip.left, top: tooltip.top }}>{tooltip.text}</div>}
    </div>
    {selected && project.alternatives.some(a => a.id === selected.alternativeId) && <CompanyDrawer
      key={canonical({ sourceKey, ...selected })} {...{ project, context, dossier, studyEvidence }} selection={selected} onClose={close}
      onSensitivity={destination => { close(); onSensitivity(destination); }}/>}
  </CompanyExplorationContext>;
}

function CompanyDrawer({ project, context: sourceContext, dossier, studyEvidence, selection, onClose, onSensitivity }: Omit<Props, "children"> & {
  selection: { alternativeId: string; profileId?: string }; onClose: () => void;
}) {
  const context = useMemo(() => selection.profileId
    ? resolveContext(project, sourceContext.fingerprint, { ...sourceContext, profileId: selection.profileId })
    : sourceContext, [project, sourceContext, selection.profileId]);
  const request = useScreeningDetails(project, context, dossier, selection.alternativeId);
  const company = project.alternatives.find(a => a.id === selection.alternativeId);
  const missingProfile = selection.profileId && !project.weight_profiles.some(p => p.id === selection.profileId);
  return <Modal title={company?.name ?? "Alternative detail"} className="company-drawer" closeLabel="Close alternative drawer" onClose={onClose}
    onFocusFallback={() => document.querySelector<HTMLElement>('[role="tab"][aria-selected="true"], .presentation h2')?.focus()}
    footer={<button type="button" onClick={onClose}>Close alternative detail</button>}>
    <p className="note">{["mavt", "mavt_sorting"].includes(sourceContext.configuration.method) ? "Screening detail" : "MAVT screening detail"} · {project.weight_profiles.find(p => p.id === context.resolvedProfileId)?.name ?? "No profile"} · {project.scenarios.find(s => s.id === context.scenarioId)?.name ?? "Base model"}</p>
    {missingProfile ? <p role="status">This weight profile is no longer available.</p>
      : request.status === "loading" ? <p role="status">Loading alternative detail…</p>
        : request.status === "error" ? <><p role="alert"><MessageText message={request.message}/></p><button type="button" onClick={request.retry}>Retry alternative detail</button></>
          : request.result.status === "unavailable" || !request.result.alternative ? <p role="status"><MessageText message={request.result.reason || "Alternative detail is unavailable."}/></p>
            : <DetailSections {...{ project, context, dossier, studyEvidence, onSensitivity }} result={request.result}/>}
  </Modal>;
}

function DetailSections({ result, project, context, dossier, studyEvidence, onSensitivity }: Omit<Props, "children"> & { result: ScreeningDetails }) {
  const detail = result.alternative;
  if (!detail) return null;
  const row = detail.row, fragility = row.fragility;
  const probeCriterion = fragility?.criterion_id, probeWeight = fragility?.local_weight;
  // Python's returned claim IDs carry validation; this check only enforces the source binding.
  const boundDossier = dossier?.project_fingerprint === result.project_fingerprint ? dossier : null;
  return <>
    <dl className="company-facts">{detail.header_facts.map(fact => <div key={fact.criterion_id}><dt>{fact.label}</dt><dd>{displayCompact(fact.measurement ?? "Not stated")} {project.criteria.find(c => c.id === fact.criterion_id)?.scale?.unit}</dd></div>)}</dl>
    <dl className="company-facts"><div><dt>Rank</dt><dd>{row.rank}</dd></div><div><dt>Overall value</dt><dd>{displayNumber(row.value)}</dd></div>
      {row.class_name && <div><dt>Class</dt><dd>{row.class_name}</dd></div>}{row.margin !== null && <div><dt>Margin to nearest class boundary</dt><dd>{displayNumber(row.margin)}</dd></div>}</dl>
    <Caveat caption="Preference values under this profile; not probabilities or predictions.">Screening orders further checking under these stated preferences. Values are compensatory MAVT preferences, not probabilities, success rates or financial returns.</Caveat>
    <section aria-label="Alternative requirements"><h3>Requirements</h3>{detail.requirements
      ? <><p className={`feasibility ${detail.requirements.status}`}>{STATUS_TEXT[detail.requirements.status]}</p><ul>{detail.requirements.checks.map(check => <li key={check.requirement_id}>
        {project.requirements?.find(r => r.id === check.requirement_id)?.name}: {STATUS_TEXT[check.status]} — {requirementReason(check, { requirements: project.requirements ?? [] })}
        <InfoDisclosure label="Requirement details">{check.reason}</InfoDisclosure>
      </li>)}</ul></> : <p>No requirements stated.</p>}</section>
    <section aria-label="Alternative contributions"><h3>All scored contributions</h3>
      <p className="muted small">Engine order, largest contribution first. Bar lengths share the overall preference-value scale.</p>
      <ul className="company-contributions">{detail.contributions.map(driver => {
        const rating = detail.ratings.find(r => r.criterion_id === driver.criterion_id);
        return <li key={driver.criterion_id}><InfoDisclosure label={`Rating details for ${driver.name}`}>
          {rating?.rubric_text || "No rubric text stated."} · Exact contribution: {String(driver.contribution)}
        </InfoDisclosure><RatingHint text={`${driver.name}: ${displayNumber(driver.contribution)}. ${rating?.rubric_text || "No rubric text stated."}`}>
          {driver.name} <span className="company-contribution-track"><span style={{ width: `${String(driver.contribution * 100)}%` }}/></span> {displayNumber(driver.contribution)}
        </RatingHint></li>;
      })}</ul>
    </section>
    <section aria-label="Alternative closest change"><h3>Closest change</h3>
      {fragility?.status === "change" && probeCriterion && probeWeight != null
        ? <><p>{fragility.criterion_name}: {fragility.direction === "raise" ? "raise" : "lower"} by {displayNumber(fragility.weight_change ?? 0)} of total weight to {fragility.kind === "rank" ? `exchange rank with ${project.alternatives.find(a => a.id === fragility.other_alternative_id)?.name ?? "another alternative"}` : `reach ${project.sorting?.classes.find(c => c.id === fragility.class_after_id)?.name ?? "another class"}`}.</p>
          <button type="button" onClick={() => onSensitivity({ criterionId: probeCriterion, weight: probeWeight, context })}>Show in Sensitivity</button>
          <InfoDisclosure label="Closest change details">Exact local weight {String(fragility.local_weight)}; baseline {String(fragility.base_local_weight)}. One weight varies at a time; its siblings retain their relative proportions.</InfoDisclosure></>
        : <p>{fragility?.status === "tied" ? `Tied now with ${fragility.tied_with.map(id => project.alternatives.find(a => a.id === id)?.name ?? id).join(", ")}` : fragility?.status === "none" ? "No one-way change in range." : "Closest change detail is unavailable."}</p>}
    </section>
    <section aria-label="Alternative ratings and sources"><h3>Ratings and sources</h3>
      {!boundDossier && <p>No verified evidence dossier is loaded. {studyEvidence && <button type="button" onClick={studyEvidence.load}>Load the study's evidence</button>}</p>}
      {detail.ratings.map(rating => <details key={rating.criterion_id}><summary>{rating.name} · {displayCompact(rating.measurement ?? "Not stated")}</summary>
        <p>{rating.rubric_text || "No rubric text stated."}</p>
        {rating.claim_ids.length ? <ul>{rating.claim_ids.map(id => {
          const claim = boundDossier?.claims.find(c => c.id === id);
          if (!claim) return null;
          const kind = /^(Observed|Judgement|Proxy)\s*:/i.exec(claim.source.description)?.[1] ?? "Unclassified";
          return <li key={id}><p><strong>{kind}</strong> · {claim.review?.status ?? "unreviewed"}</p>
            <p>{/^https?:\/\//i.test(claim.source.reference) ? <a href={claim.source.reference} target="_blank" rel="noreferrer">{claim.source.name}</a> : claim.source.name} · {claim.source.date}</p>
            <p>{claim.source.description}</p><InfoDisclosure label={`Claim details for ${claim.source.name}`}><code>{claim.id}</code> · {claim.source.reference} {claim.source.location} · {claim.source.classification}<br/>
              Proposed by {claim.origin.proposed_by} ({claim.origin.kind}) {claim.origin.tool_id} {claim.origin.tool_version}
              {claim.review && <> · Reviewed by {claim.review.reviewer} at {claim.review.reviewed_at}. {claim.review.note}</>}
            </InfoDisclosure></li>;
        })}</ul> : <p>No verified source claim is attached to this rating.</p>}
      </details>)}
    </section>
    <section aria-label="Alternative open questions"><h3>Open questions</h3>
      <ul>{detail.questions.map((question, index) => <li key={index}>
        <strong>{project.criteria.find(c => c.id === question.criterion_id)?.name ?? project.requirements?.find(r => r.id === question.requirement_id)?.name ?? "This alternative"}</strong>
        <p>{question.code === "CONFLICTING_CLAIMS" ? "Which conflicting claim is supported?" : question.code === "OUTDATED_CLAIM" ? "Is this evidence still current?" : question.code === "UNREVIEWED_CLAIM" ? "Should this claim be accepted, corrected or rejected?" : question.question}</p>
        <InfoDisclosure label="Question details"><code>{question.code}</code> · {question.question}<br/>{question.why}<br/>{question.evidence}</InfoDisclosure>
      </li>)}</ul>{!detail.questions.length && <p>No open questions were returned for this alternative.</p>}
      <p className="muted small">Prompts for further checking; no overall importance score is calculated.</p>
    </section>
  </>;
}
