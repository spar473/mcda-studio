import { useCallback, useRef, useState } from "react";
import { api } from "../api/client";
import type { Project, ReferenceCasesResult, ReferenceCasesValidation } from "../api/types";
import { canonical, type AnalysisContext } from "../state/analysisContext";
import { useAnalysisRequest } from "../state/useAnalysisRequest";
import { InfoDisclosure } from "./InfoDisclosure";
import { MessageText } from "./IssueText";
import { displayNumber } from "./results/numberDisplay";

type CaseMatch = ReferenceCasesResult["alternatives"][number]["cases"][number];
type Leaf = CaseMatch["same"][number];

const GROUPS = [
  ["same", "Same label"],
  ["one_step", "One step apart"],
  ["further", "Further apart"],
  ["not_compared", "Not compared"],
] as const;
const MISSING: Record<string, string> = {
  alternative: "not rated for this alternative",
  reference_case: "not rated for this case",
  both: "not rated on either side",
};
const MAX_FILE = 2_000_000;

/** One leaf as a chip: both labels as Python returned them; nothing is computed here. */
function LeafChip({ leaf }: { leaf: Leaf }) {
  const text = leaf.missing
    ? `${leaf.criterion_name}: ${MISSING[leaf.missing] ?? leaf.missing}`
    : leaf.alternative_label === leaf.case_label
      ? `${leaf.criterion_name}: ${leaf.case_label ?? ""}`
      : `${leaf.criterion_name}: ${leaf.alternative_label ?? ""} here, ${leaf.case_label ?? ""} then${leaf.steps != null ? ` (${String(leaf.steps)} ${leaf.steps === 1 ? "step" : "steps"})` : ""}`;
  return <li className="reference-chip" title={leaf.case_note || undefined}>{text}</li>;
}

function CaseCard({ match, outcomes }: { match: CaseMatch; outcomes: boolean }) {
  return <li className="reference-card">
    <article aria-label={`Reference case ${match.name}`}>
      <h4>{match.name}</h4>
      <p className="muted small">Snapshot {match.snapshot_date}</p>
      <dl className="company-facts">{match.context.map(row => <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}</dl>
      <p><strong>Similarity {displayNumber(match.similarity)}</strong> · {match.shared_count} of {match.compared_count} compared criteria rated on both sides</p>
      <InfoDisclosure label={`Similarity details for ${match.name}`}>Exact similarity {match.similarity_exact}. One minus the mean label gap over the criteria rated on both sides.</InfoDisclosure>
      {GROUPS.map(([key, title]) => match[key].length > 0 && <section key={key} aria-label={`${title} for ${match.name}`}>
        <h5>{title} ({match[key].length})</h5>
        <ul className="reference-chips">{match[key].map(leaf => <LeafChip key={leaf.criterion_id} leaf={leaf}/>)}</ul>
      </section>)}
      {outcomes && match.outcome && <section aria-label={`What happened next for ${match.name}`} className="reference-outcome">
        <h5>What happened next</h5>
        <p><strong>{match.outcome.label}</strong> · as of {match.outcome.as_of}</p>
        {match.outcome.note && <p>{match.outcome.note}</p>}
      </section>}
    </article>
  </li>;
}

/** The engine's answer for one alternative, in the engine's order. */
export function ReferenceCasesView({ result }: { result: ReferenceCasesResult }) {
  if (result.status !== "available") return <p role="status"><MessageText message={result.reason}/></p>;
  const row = result.alternatives[0];
  if (!row) return <p role="status">No alternative was compared.</p>;
  return <section aria-label="Reference cases result" className="reference-cases">
    <p className="note">{result.label}</p>
    {row.excluded_case_ids.length > 0 && <p className="muted small">{row.alternative_name}'s own reference case is left out of this comparison.</p>}
    {row.cases.length === 0
      ? <p role="status">No reference case shares enough rated criteria with {row.alternative_name} to be compared.</p>
      : <ol className="reference-cards" aria-label={`Most similar reference cases for ${row.alternative_name}`}>
        {row.cases.map(match => <CaseCard key={match.case_id} match={match} outcomes={result.include_outcomes}/>)}
      </ol>}
    {row.remaining_count > 0 && <p className="muted small">{row.remaining_count} more comparable {row.remaining_count === 1 ? "case is" : "cases are"} not shown.</p>}
    {row.not_comparable.length > 0 && <section aria-label="Not comparable reference cases">
      <h4>Not comparable</h4>
      <p className="muted small">Too few criteria rated on both sides (fewer than {result.min_shared_fraction} of the compared criteria).</p>
      <ul>{row.not_comparable.map(item => <li key={item.case_id}>{item.name} (snapshot {item.snapshot_date}): {item.shared_count} of {item.compared_count} compared criteria rated on both sides</li>)}</ul>
    </section>}
    <ul>{result.limitations.map(item => <li key={item} className="muted small">{item}</li>)}</ul>
  </section>;
}

/** Opt-in and view-only: opens a reference-cases file and shows Python's comparison for the
 * selected alternative. Nothing here edits, saves or reorders anything. */
export function ReferenceCasesPanel({ project, context }: { project: Project; context: AnalysisContext }) {
  const [referenceSet, setReferenceSet] = useState<{ name: string; value: unknown } | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [outcomes, setOutcomes] = useState(false);
  const [leaveOut, setLeaveOut] = useState(false);
  const sequence = useRef(0);
  const alternativeId = chosen && project.alternatives.some(a => a.id === chosen) ? chosen : project.alternatives[0]?.id ?? null;
  const { fingerprint, configuration } = context;

  const validationKey = canonical({ kind: "reference-cases-validate", fingerprint, set: referenceSet?.value ?? null });
  const loadValidation = useCallback(async (signal: AbortSignal): Promise<ReferenceCasesValidation> =>
    api.validateReferenceCases(project, referenceSet?.value, signal), [project, referenceSet]);
  const validation = useAnalysisRequest(validationKey, referenceSet !== null, loadValidation);
  const valid = validation.status === "ready" && validation.result.valid;

  const key = canonical({ kind: "reference-cases", fingerprint, configuration, set: referenceSet?.value ?? null, alternativeId, outcomes, leaveOut });
  const load = useCallback(async (signal: AbortSignal) => {
    const result = await api.referenceCases(project, configuration, referenceSet?.value, alternativeId, outcomes, leaveOut, signal);
    if (result.project_fingerprint !== fingerprint || canonical(result.configuration) !== canonical(configuration)) {
      throw Error("Reference cases do not match the selected analysis context.");
    }
    return result;
  }, [project, configuration, fingerprint, referenceSet, alternativeId, outcomes, leaveOut]);
  const request = useAnalysisRequest(key, valid && alternativeId !== null, load);

  return <section className="panel" aria-label="Reference cases">
    <h2>Reference cases</h2>
    <p>Past alternatives rated on the same criteria as they stood at a dated snapshot. Read-only: nothing here changes the project.</p>
    <label>Open a reference-cases file
      <input type="file" accept=".json,application/json" onChange={event => {
        const file = event.target.files?.[0];
        const current = ++sequence.current;
        setReferenceSet(null); setFileError(null);
        if (!file) return;
        if (file.size > MAX_FILE) { setFileError("The reference-cases file exceeds the 2 MB limit."); return; }
        void file.text().then(text => {
          const value: unknown = JSON.parse(text);
          if (sequence.current === current) setReferenceSet({ name: file.name, value });
        }).catch(() => { if (sequence.current === current) setFileError("Could not read the reference-cases file as JSON."); });
      }}/>
    </label>
    {fileError && <p role="alert">{fileError}</p>}
    {referenceSet === null && !fileError && <p className="muted small">No reference set is open.</p>}
    {referenceSet !== null && validation.status === "loading" && <p role="status">Checking {referenceSet.name}…</p>}
    {referenceSet !== null && validation.status === "error" && <><p role="alert"><MessageText message={validation.message}/></p>
      <button type="button" onClick={validation.retry}>Retry the check</button></>}
    {validation.status === "ready" && !validation.result.valid && <div role="alert">
      <p>This reference set cannot be used with this project ({validation.result.issues.length} {validation.result.issues.length === 1 ? "problem" : "problems"}):</p>
      <ul>{validation.result.issues.map((issue, index) => <li key={index}><code>{issue.path}</code>: {issue.message}</li>)}</ul>
    </div>}
    {valid && <>
      <p className="muted small">{referenceSet?.name}: {validation.result.case_count} reference cases, {validation.result.rating_count} ratings.</p>
      <label>Alternative
        <select value={alternativeId ?? ""} onChange={event => setChosen(event.target.value)}>
          {project.alternatives.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </label>
      <label className="partner-toggle"><input type="checkbox" checked={leaveOut} onChange={event => setLeaveOut(event.target.checked)}/> Leave out this alternative's own case</label>
      <label className="partner-toggle"><input type="checkbox" checked={outcomes} onChange={event => setOutcomes(event.target.checked)}/> Show what happened next</label>
      {request.status === "loading" && <p role="status">Comparing reference cases…</p>}
      {request.status === "error" && <><p role="alert"><MessageText message={request.message}/></p><button type="button" onClick={request.retry}>Retry reference cases</button></>}
      {request.status === "ready" && <ReferenceCasesView result={request.result}/>}
    </>}
  </section>;
}
