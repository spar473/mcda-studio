import { useState } from "react";
import type { Issue, Operation, PreferenceFunction, Project, PrometheeCriterion, PrometheeModel } from "../api/types";
import { buildTree, flatten, isLeaf } from "../model/tree";
import { canonical, type AnalysisContext } from "../state/analysisContext";
import { useMethodIssues } from "../state/useMethodIssues";
import { ConfirmDialog } from "./ui";
import { IssueText } from "./IssueText";

const PROMETHEE = "promethee2";
type Kind = PreferenceFunction["kind"];
interface DraftRow { criterion: string; direction: "" | "maximise" | "minimise"; weight: string; kind: Kind; q: string; p: string; codes: Record<string, string> }

const prometheeIssue = (i: Issue) => i.path === "promethee" || i.path.startsWith("promethee.") || i.code === "PROMETHEE_TOO_FEW_ALTERNATIVES";
const KINDS: { kind: Kind; label: string }[] = [
  { kind: "usual", label: "Usual: any difference is full preference" },
  { kind: "u_shape", label: "U-shape: none up to q, then full" },
  { kind: "v_shape", label: "V-shape: grows to full at p" },
  { kind: "linear", label: "Linear: none up to q, grows to full at p" },
];
const usesQ = (kind: Kind) => kind === "u_shape" || kind === "linear";
const usesP = (kind: Kind) => kind === "v_shape" || kind === "linear";

/** A labelled scale's labels; a numeric scale's labels are ignored, so it takes no codes. */
const labelsOf = (scale: Project["criteria"][number]["scale"]) =>
  scale && (scale.type === "categorical" || scale.type === "ordinal") ? scale.labels : [];

function leavesOf(project: Project) {
  return flatten(buildTree(project.criteria)).map((e) => e.node).filter((n) => isLeaf(project.criteria, n.id));
}

function draftOf(model: PrometheeModel | null | undefined, project: Project): DraftRow[] {
  return leavesOf(project).map((leaf): DraftRow => {
    const given = model?.criteria.find((c) => c.criterion_id === leaf.id);
    const f = given?.function;
    return {
      criterion: leaf.id, direction: given?.direction ?? "", weight: given ? String(given.weight) : "", kind: f?.kind ?? "usual",
      q: f && (f.kind === "u_shape" || f.kind === "linear") ? String(f.q) : "",
      p: f && (f.kind === "v_shape" || f.kind === "linear") ? String(f.p) : "",
      codes: Object.fromEntries(labelsOf(leaf.scale).map((label) => {
        const code = given?.coding ? given.coding[label] : undefined;
        return [label, code === undefined ? "" : String(code)];
      })),
    };
  });
}

/** The draft as a PROMETHEE section, or the first entry that cannot be read. Rules are the engine's. */
function modelOf(rows: DraftRow[], project: Project): PrometheeModel | string {
  const name = (id: string) => project.criteria.find((c) => c.id === id)?.name ?? id;
  const num = (text: string, what: string) => { const v = Number(text.trim()); if (text.trim() === "" || !Number.isFinite(v)) throw Error(`${what} must be a number.`); return v; };
  try {
    const criteria = rows.map((r): PrometheeCriterion => {
      const n = name(r.criterion);
      if (!r.direction) throw Error(`Choose whether ${n} is maximised or minimised.`);
      const weight = num(r.weight, `The weight of ${n}`);
      const q = () => num(r.q, `q for ${n}`), p = () => num(r.p, `p for ${n}`);
      const fn: PreferenceFunction = r.kind === "usual" ? { kind: "usual" } : r.kind === "u_shape" ? { kind: "u_shape", q: q() }
        : r.kind === "v_shape" ? { kind: "v_shape", p: p() } : { kind: "linear", q: q(), p: p() };
      const labelled = Object.keys(r.codes).length > 0;
      const coding = labelled ? Object.fromEntries(Object.entries(r.codes).map(([label, code]) => [label, num(code, `The code for ${label} on ${n}`)])) : null;
      const entry: PrometheeCriterion = { criterion_id: r.criterion, direction: r.direction, weight, function: fn };
      return coding ? { ...entry, coding } : entry;
    });
    return { criteria };
  } catch (error: unknown) {
    return error instanceof Error ? error.message : String(error);
  }
}

/** PROMETHEE II's own inputs as a draft, applied as one undoable change. */
export function OutrankingPanel({ project, context, busy, apply }: {
  project: Project; context: AnalysisContext; busy: boolean; apply: (ops: Operation[]) => Promise<boolean>;
}) {
  const saved = project.promethee ?? null;
  // A new saved section or a changed tree (apply, undo, reload) restarts the draft from them.
  const key = canonical([saved, leavesOf(project).map((l) => [l.id, l.scale?.labels ?? []])]);
  return <OutrankingEditor key={key} project={project} context={context} busy={busy} apply={apply} saved={saved}/>;
}

function OutrankingEditor({ project, context, busy, apply, saved }: {
  project: Project; context: AnalysisContext; busy: boolean; apply: (ops: Operation[]) => Promise<boolean>; saved: PrometheeModel | null;
}) {
  const [rows, setRows] = useState<DraftRow[]>(() => draftOf(saved, project));
  const [showUnweighted, setShowUnweighted] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const issues = useMethodIssues(project, context, PROMETHEE, prometheeIssue);
  const leaves = leavesOf(project);
  const model = modelOf(rows, project);
  const changed = typeof model === "string" || canonical(model) !== canonical(saved);
  const set = (i: number, patch: (r: DraftRow) => void) => setRows((all) => { const next = structuredClone(all); const row = next[i]; if (row) patch(row); return next; });

  return <section className="panel outranking-editor" aria-label="Outranking">
    <h2>Outranking</h2>
    <p className="muted">PROMETHEE II’s own inputs. Each criterion compares every pair of alternatives on its measurements through a
      preference function: a difference up to q counts as no preference, and a difference at or beyond p counts as full preference, however
      large. Thresholds are in the criterion’s units, or in its codes when it is labelled.</p>
    <p className="note" aria-label="Why swing weights are not reused">Swing weights are not reused here. They are trade-offs that depend on the
      measurement ranges in MAVT, whereas these weights are importances applied to preference degrees. Directions and codes are stated here
      too, never read from value functions.</p>
    {context.configuration.method !== PROMETHEE && <p role="status">Choose the method “PROMETHEE II (outranking flows)” in the header to see
      flows in Results.</p>}
    {leaves.length === 0 && <p>Add criteria first.</p>}
    <label><input type="checkbox" checked={showUnweighted} onChange={e => setShowUnweighted(e.target.checked)}/>Show unweighted criteria (screened only)</label>
    <div className="table-scroll"><table className="grid compact" aria-label="PROMETHEE inputs"><thead><tr>
      <th>Criterion</th><th>Direction</th><th>Weight</th><th>Function</th><th>q</th><th>p</th><th>Label codings</th>
    </tr></thead><tbody>{rows.map((r, i) => {
      const leaf = leaves.find(l => l.id === r.criterion), name = leaf?.name ?? r.criterion;
      const unweighted = saved?.criteria.find(c => c.criterion_id === r.criterion)?.weight === 0;
      if (unweighted && !showUnweighted) return null;
      const unit = Object.keys(r.codes).length ? "codes" : leaf?.scale?.unit ?? "";
      return <tr key={r.criterion} aria-label={`PROMETHEE inputs for ${name}`} data-criterion-id={r.criterion}>
        <th scope="row">{name}</th>
        <td><select aria-label={`Direction for ${name}`} value={r.direction} onChange={e => set(i, row => { row.direction = e.target.value as DraftRow["direction"]; })}>
          <option value="">Choose…</option><option value="maximise">Maximise (higher is better)</option><option value="minimise">Minimise (lower is better)</option>
        </select></td>
        <td><input aria-label={`Weight for ${name}`} inputMode="decimal" value={r.weight} onChange={e => set(i, row => { row.weight = e.target.value; })}/></td>
        <td><select aria-label={`Preference function for ${name}`} value={r.kind} onChange={e => set(i, row => { row.kind = e.target.value as Kind; })}>
          {KINDS.map(k => <option key={k.kind} value={k.kind}>{k.label}</option>)}
        </select></td>
        <td>{usesQ(r.kind) ? <label><input aria-label={`q for ${name}`} inputMode="decimal" value={r.q} onChange={e => set(i, row => { row.q = e.target.value; })}/>{unit}</label> : "—"}</td>
        <td>{usesP(r.kind) ? <label><input aria-label={`p for ${name}`} inputMode="decimal" value={r.p} onChange={e => set(i, row => { row.p = e.target.value; })}/>{unit}</label> : "—"}</td>
        <td>{Object.keys(r.codes).length > 0 ? <details><summary>Label codings for {name}</summary>
          <span className="class-row" aria-label={`Codes for ${name}`}>
            {Object.entries(r.codes).map(([label, code]) => <label key={label}>{label}<input aria-label={`Code for ${label} on ${name}`} inputMode="decimal" value={code} onChange={e => set(i, row => { row.codes[label] = e.target.value; })}/></label>)}
            {leaf?.scale?.type === "ordinal" && <button type="button" onClick={() => set(i, row => { Object.keys(row.codes).forEach((label, k) => { row.codes[label] = String(k + 1); }); })}>Number in label order</button>}
          </span></details> : "—"}</td>
      </tr>;
    })}</tbody></table></div>
    {typeof model === "string" && <p role="alert">{model}</p>}
    <p>
      <button type="button" className="primary" disabled={busy || !changed || typeof model === "string" || leaves.length === 0}
        onClick={() => { if (typeof model !== "string") void apply([{ op: "set_promethee_model", promethee: model }]); }}>Apply outranking inputs</button>{" "}
      <button type="button" disabled={!changed} onClick={() => setRows(draftOf(saved, project))}>Cancel changes</button>{" "}
      <button type="button" disabled={busy || saved === null} onClick={() => setConfirmRemove(true)}>Remove all outranking inputs</button>
    </p>
    <h3>Checks on the saved inputs</h3>
    {issues.status === "loading" && <p role="status">Checking outranking inputs…</p>}
    {issues.status === "error" && <><p role="alert">{issues.message}</p><button type="button" onClick={issues.retry}>Retry check</button></>}
    {issues.status === "ready" && issues.result.length === 0 && <p role="status">No problems with the saved outranking inputs.</p>}
    {issues.status === "ready" && issues.result.some(i => i.severity === "error") && <ul className="issue-list inline" aria-label="Outranking errors">{issues.result.filter(i => i.severity === "error").map((issue, i) =>
      <li key={i} className={issue.severity}><IssueText code={issue.code} message={issue.message} path={issue.path}/></li>)}</ul>}
    {issues.status === "ready" && issues.result.some(i => i.severity !== "error") && <details><summary>Notes on saved inputs</summary><ul className="issue-list inline" aria-label="Outranking issues">{issues.result.filter(i => i.severity !== "error").map((issue, i) =>
      <li key={i} className={issue.severity}><IssueText code={issue.code} message={issue.message} path={issue.path}/></li>)}</ul></details>}
    {confirmRemove && <ConfirmDialog title="Remove all outranking inputs" danger
      message="The PROMETHEE section is removed from the project, which is then saved at the lowest schema version it needs. You can undo this."
      confirmLabel="Remove outranking inputs" onCancel={() => setConfirmRemove(false)}
      onConfirm={() => { setConfirmRemove(false); void apply([{ op: "clear_promethee_model" }]); }}/>}
  </section>;
}
