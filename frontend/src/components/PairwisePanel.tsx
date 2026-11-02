import { useCallback, useState } from "react";
import { api } from "../api/client";
import type { AhpModel, Issue, Operation, PairwiseJudgement, Project } from "../api/types";
import { buildTree, flatten, isLeaf } from "../model/tree";
import { canonical, type AnalysisContext } from "../state/analysisContext";
import { useAnalysisRequest } from "../state/useAnalysisRequest";
import { useMethodIssues } from "../state/useMethodIssues";
import { judgementText, triadText } from "./results/AhpView";
import { ConfirmDialog } from "./ui";

const AHP = "ahp";
const ahpIssue = (i: Issue) => i.path === "ahp" || i.path.startsWith("ahp.") || i.code === "AHP_TOO_FEW_ALTERNATIVES";
const VERBAL: Record<number, string> = { 1: "equal", 2: "", 3: "moderate", 4: "", 5: "strong", 6: "", 7: "very strong", 8: "", 9: "extreme" };

/** One matrix of the section: what it judges and the items it compares, in order. */
interface Matrix { key: string; kind: "criteria" | "alternatives"; group: string | null; title: string; items: string[] }
/** A cell holds a signed strength: s > 0 favours the earlier item s times, s < 0 the later one |s| times,
 * 1 is equal and 0 is not judged. */
type Draft = Record<string, Record<string, number>>;
const pairKey = (i: number, j: number) => `${String(i)}|${String(j)}`;

function matricesOf(project: Project): Matrix[] {
  const nodes = flatten(buildTree(project.criteria)).map((e) => e.node);
  const name = (id: string) => project.criteria.find((c) => c.id === id)?.name ?? id;
  const children = (parent: string | null) => project.criteria.filter((c) => (c.parent_id ?? null) === parent)
    .sort((a, b) => a.order - b.order).map((c) => c.id);
  const parents = [null, ...nodes.filter((n) => !isLeaf(project.criteria, n.id)).map((n) => n.id)];
  const criteria = parents.filter((p) => children(p).length >= 2).map((p): Matrix => ({
    key: `criteria:${p ?? "top"}`, kind: "criteria", group: p, items: children(p),
    title: p === null ? "Top-level criteria" : `Criteria under ${name(p)}`,
  }));
  const alternatives = project.alternatives.map((a) => a.id);
  const leaves = nodes.filter((n) => isLeaf(project.criteria, n.id)).map((n): Matrix => ({
    key: `alternatives:${n.id}`, kind: "alternatives", group: n.id, items: alternatives, title: `Alternatives on ${n.name}`,
  }));
  return [...criteria, ...leaves];
}

function stored(model: AhpModel | null | undefined, m: Matrix): PairwiseJudgement[] {
  if (!model) return [];
  return m.kind === "criteria"
    ? model.criteria.find((g) => g.parent_id === m.group)?.judgements ?? []
    : model.alternatives.find((a) => a.criterion_id === m.group)?.judgements ?? [];
}

function draftOf(model: AhpModel | null | undefined, matrices: Matrix[]): Draft {
  return Object.fromEntries(matrices.map((m) => {
    const cells: Record<string, number> = {};
    for (const j of stored(model, m)) {
      const r = m.items.indexOf(j.row), c = m.items.indexOf(j.column);
      if (r < 0 || c < 0 || r === c) continue;
      cells[pairKey(Math.min(r, c), Math.max(r, c))] = r < c || j.value === 1 ? j.value : -j.value;
    }
    return [m.key, cells];
  }));
}

function judgementsOf(m: Matrix, cells: Record<string, number> | undefined): PairwiseJudgement[] {
  const out: PairwiseJudgement[] = [];
  m.items.forEach((a, i) => m.items.forEach((b, j) => {
    if (j <= i) return;
    const s = cells?.[pairKey(i, j)] ?? 0;
    if (s >= 1) out.push({ row: a, column: b, value: s });
    else if (s < 0) out.push({ row: b, column: a, value: -s });
  }));
  return out;
}

function modelOf(draft: Draft, matrices: Matrix[]): AhpModel {
  const model: AhpModel = { criteria: [], alternatives: [] };
  for (const m of matrices) {
    const judgements = judgementsOf(m, draft[m.key]);
    if (judgements.length === 0) continue;
    if (m.kind === "criteria") model.criteria.push({ parent_id: m.group, judgements });
    else if (m.group !== null) model.alternatives.push({ criterion_id: m.group, judgements });
  }
  return model;
}

/** AHP's pairwise judgements as a draft, applied as one undoable change. */
export function PairwisePanel({ project, context, busy, apply }: {
  project: Project; context: AnalysisContext; busy: boolean; apply: (ops: Operation[]) => Promise<boolean>;
}) {
  const saved = project.ahp ?? null;
  const matrices = matricesOf(project);
  // A new saved section or a changed tree or alternative set (apply, undo, reload) restarts the draft.
  const key = canonical([saved, matrices.map((m) => [m.key, m.items])]);
  return <PairwiseEditor key={key} project={project} context={context} busy={busy} apply={apply} saved={saved} matrices={matrices}/>;
}

function PairwiseEditor({ project, context, busy, apply, saved, matrices }: {
  project: Project; context: AnalysisContext; busy: boolean; apply: (ops: Operation[]) => Promise<boolean>;
  saved: AhpModel | null; matrices: Matrix[];
}) {
  const [draft, setDraft] = useState<Draft>(() => draftOf(saved, matrices));
  const [confirmRemove, setConfirmRemove] = useState(false);
  const issues = useMethodIssues(project, context, AHP, ahpIssue);
  const model = modelOf(draft, matrices);
  const changed = canonical(model) !== canonical(saved ?? { criteria: [], alternatives: [] });
  const name = (id: string) => project.alternatives.find((a) => a.id === id)?.name ?? project.criteria.find((c) => c.id === id)?.name ?? id;
  const set = (matrix: string, pair: string, value: number) => setDraft((d) => ({ ...d, [matrix]: { ...d[matrix], [pair]: value } }));

  return <section className="panel pairwise-editor" aria-label="Pairwise">
    <h2>Pairwise</h2>
    <p className="muted">AHP’s own judgements on Saaty’s 1–9 scale: for each pair, which item is more important (or preferred) and how
      many times. Criteria are compared within each group of siblings, and the alternatives on each leaf criterion. Each pair is stored once;
      its reverse is derived. Priorities and consistency are computed in Python as you go; nothing is saved until you apply.</p>
    <p className="note" aria-label="AHP inputs are its own">These judgements are AHP’s alone: they never change MAVT’s swing weights or value
      functions, and AHP reads no measurements, weight profile or scenario.</p>
    {context.configuration.method !== AHP && <p role="status">Choose the method “AHP (pairwise priorities)” in the header to see AHP
      priorities in Results.</p>}
    {matrices.length === 0 && <p>Add criteria and alternatives first.</p>}
    {matrices.map((m) => <MatrixEditor key={m.key} matrix={m} cells={draft[m.key] ?? {}} name={name}
      onChange={(pair, value) => set(m.key, pair, value)}/>)}
    <p>
      <button type="button" className="primary" disabled={busy || !changed} onClick={() => void apply([{ op: "set_ahp_model", ahp: model }])}>
        Apply judgements</button>{" "}
      <button type="button" disabled={!changed} onClick={() => setDraft(draftOf(saved, matrices))}>Cancel changes</button>{" "}
      <button type="button" disabled={busy || saved === null} onClick={() => setConfirmRemove(true)}>Remove all judgements</button>
    </p>
    <h3>Checks on the saved judgements</h3>
    {issues.status === "loading" && <p role="status">Checking judgements…</p>}
    {issues.status === "error" && <><p role="alert">{issues.message}</p><button type="button" onClick={issues.retry}>Retry check</button></>}
    {issues.status === "ready" && (issues.result.length === 0
      ? <p role="status">No problems with the saved judgements.</p>
      : <ul className="issue-list inline" aria-label="Pairwise issues">{issues.result.map((issue, i) =>
        <li key={i} className={issue.severity}><code>{issue.code}</code> {issue.message} <span>{issue.path}</span></li>)}</ul>)}
    {confirmRemove && <ConfirmDialog title="Remove all judgements" danger
      message="The AHP section is removed from the project, which is then saved at the lowest schema version it needs. You can undo this."
      confirmLabel="Remove judgements" onCancel={() => setConfirmRemove(false)}
      onConfirm={() => { setConfirmRemove(false); void apply([{ op: "clear_ahp_model" }]); }}/>}
  </section>;
}

function useMatrixPreview(items: string[], judgements: PairwiseJudgement[]) {
  const key = canonical({ kind: "ahp-preview", items, judgements });
  const load = useCallback((signal: AbortSignal) => api.previewAhpMatrix(items, judgements, signal), [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return useAnalysisRequest(key, items.length > 0, load);
}

function options(a: string, b: string, current: number) {
  const strength = (s: number) => `${String(s)}×${VERBAL[s] ? ` (${VERBAL[s] ?? ""})` : ""}`;
  const list: [number, string][] = [[0, "Not judged"]];
  for (let s = 9; s >= 2; s--) list.push([s, `${a} ${strength(s)}`]);
  list.push([1, "Equal (1)"]);
  for (let s = 2; s <= 9; s++) list.push([-s, `${b} ${strength(s)}`]);
  if (!list.some(([v]) => v === current)) list.push([current, `custom: ${current > 0 ? a : b} ${judgementText(Math.abs(current))}×`]);
  return list;
}

function MatrixEditor({ matrix, cells, name, onChange }: {
  matrix: Matrix; cells: Record<string, number>; name: (id: string) => string; onChange: (pair: string, value: number) => void;
}) {
  const judgements = judgementsOf(matrix, cells);
  const preview = useMatrixPreview(matrix.items, judgements);
  const ready = preview.status === "ready" ? preview.result : null;
  const analysis = ready?.analysis ?? null;
  const triad = analysis?.most_inconsistent_triad ?? null;
  const inTriad = (a: string, b: string) => triad !== null && triad.items.includes(a) && triad.items.includes(b);
  return <fieldset className="pairwise-matrix" aria-label={matrix.title} data-matrix={matrix.key}>
    <legend>{matrix.title}</legend>
    <table className="grid compact" aria-label={`Judgements: ${matrix.title}`}><tbody>
      {matrix.items.flatMap((a, i) => matrix.items.map((b, j) => {
        if (j <= i) return null;
        const pair = pairKey(i, j);
        const value = cells[pair] ?? 0;
        const marked = inTriad(a, b) && analysis?.inconsistent === true;
        return <tr key={pair} className={marked ? "triad" : undefined} data-in-triad={marked ? "true" : undefined}>
          <th scope="row">{name(a)} vs {name(b)}</th>
          <td><select aria-label={`Judgement of ${name(a)} against ${name(b)}`} value={String(value)}
            onChange={(e) => onChange(pair, Number(e.target.value))}>
            {options(name(a), name(b), value).map(([v, text]) => <option key={v} value={String(v)}>{text}</option>)}
          </select>{marked && <span className="muted small"> in the most inconsistent triad</span>}</td>
        </tr>;
      }))}
    </tbody></table>
    <div className="pairwise-preview" aria-label={`Consistency: ${matrix.title}`}>
      {preview.status === "loading" && <p role="status">Computing priorities…</p>}
      {preview.status === "error" && <p role="alert">{preview.message}</p>}
      {ready && !analysis && <p className="muted small">{ready.issues.map((i) => i.message).join("; ")}</p>}
      {ready && analysis && <>
        <ul className="priority-list">{analysis.items.map((id) => <li key={id}>
          {name(id)} <meter min={0} max={1} value={analysis.priorities[id] ?? 0} aria-label={`Priority of ${name(id)}`}/>{" "}
          {(analysis.priorities[id] ?? 0).toFixed(4)}</li>)}</ul>
        <p className="muted small">λmax {analysis.lambda_max.toFixed(4)} · CI {analysis.consistency_index.toFixed(4)} · RI{" "}
          {analysis.random_index.toFixed(2)} ({ready.random_index_table}) · CR {analysis.consistency_ratio.toFixed(4)}</p>
        {analysis.inconsistent && <p role="status" className="warning" aria-label={`Consistency warning: ${matrix.title}`}>Consistency ratio{" "}
          {analysis.consistency_ratio.toFixed(3)} is above {ready.consistency_threshold.toFixed(2)}: review the judgements.
          {triad && <> Most inconsistent triad: {triadText(triad, name)}.</>}</p>}
      </>}
    </div>
  </fieldset>;
}
