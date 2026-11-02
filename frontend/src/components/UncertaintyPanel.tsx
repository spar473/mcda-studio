import { useState } from "react";
import type { Distribution, Issue, Operation, Project, SmaaModel } from "../api/types";
import { buildTree, flatten, isLeaf } from "../model/tree";
import { canonical, type AnalysisContext } from "../state/analysisContext";
import { useMethodIssues } from "../state/useMethodIssues";
import { ConfirmDialog } from "./ui";

const SMAA = "smaa2";
type Kind = Distribution["kind"];
type GroupKind = "fixed" | "unknown" | "rating_intervals";

interface DraftCell {
  alternative: string; criterion: string; kind: Kind;
  lower: string; mode: string; upper: string; outcomes: string; shared: string;
}
interface DraftGroup { parent: string | null; kind: GroupKind; intervals: Record<string, [string, string]> }
interface Draft { cells: DraftCell[]; groups: DraftGroup[] }

const smaaIssue = (i: Issue) => i.path === "smaa" || i.path.startsWith("smaa.") || i.code === "NOTHING_UNCERTAIN";
const slug = (name: string) => name.trim().replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").toLowerCase().slice(0, 48) || "shared";

/** Sibling groups that can vary: the top level and every criterion with two or more children. */
function siblingGroups(project: Project): { parent: string | null; name: string; children: string[] }[] {
  const parents = [null, ...project.criteria.filter((c) => !isLeaf(project.criteria, c.id)).map((c) => c.id)];
  return parents.map((parent) => ({
    parent,
    name: parent === null ? "Top level" : project.criteria.find((c) => c.id === parent)?.name ?? parent,
    children: project.criteria.filter((c) => (c.parent_id ?? null) === parent).sort((a, b) => a.order - b.order).map((c) => c.id),
  })).filter((g) => g.children.length > 1);
}

function draftOf(model: SmaaModel | null | undefined, project: Project): Draft {
  const sharedOf = new Map<string, string>();
  for (const s of model?.shared_draws ?? []) for (const c of s.cells) sharedOf.set(`${c.alternative_id}:${c.criterion_id}`, s.id);
  const cells = (model?.cells ?? []).map((c): DraftCell => {
    const d = c.distribution;
    const base = { alternative: c.alternative_id, criterion: c.criterion_id, kind: d.kind, lower: "", mode: "", upper: "", outcomes: "",
      shared: sharedOf.get(`${c.alternative_id}:${c.criterion_id}`) ?? "" };
    if (d.kind === "uniform") return { ...base, lower: String(d.lower), upper: String(d.upper) };
    if (d.kind === "triangular") return { ...base, lower: String(d.lower), mode: String(d.mode), upper: String(d.upper) };
    if (d.kind === "discrete") return { ...base, outcomes: d.values.map((v, i) => `${String(v)}=${String(d.probabilities[i])}`).join(", ") };
    return { ...base, outcomes: d.labels.map((v, i) => `${v}=${String(d.probabilities[i])}`).join(", ") };
  });
  const groups = siblingGroups(project).map(({ parent, children }): DraftGroup => {
    const given = model?.groups.find((g) => g.parent_id === parent);
    return { parent, kind: given?.kind ?? "fixed",
      intervals: Object.fromEntries(children.map((c) => {
        const pair = given?.intervals[c];
        return [c, pair ? [String(pair[0]), String(pair[1])] : ["", ""]];
      })) };
  });
  return { cells, groups };
}

/** The draft as an uncertainty section, or the first entry that cannot be read. Rules are the engine's. */
function modelOf(draft: Draft, cellName: (c: DraftCell) => string, criterionName: (id: string) => string): SmaaModel | string {
  const num = (text: string, what: string) => { const v = Number(text.trim()); if (text.trim() === "" || !Number.isFinite(v)) throw Error(`${what} must be a number.`); return v; };
  try {
    const cells = draft.cells.map((c) => {
      const where = cellName(c);
      let distribution: Distribution;
      if (c.kind === "uniform") distribution = { kind: "uniform", lower: num(c.lower, `The lower bound for ${where}`), upper: num(c.upper, `The upper bound for ${where}`) };
      else if (c.kind === "triangular") distribution = { kind: "triangular", lower: num(c.lower, `The lower bound for ${where}`), mode: num(c.mode, `The mode for ${where}`), upper: num(c.upper, `The upper bound for ${where}`) };
      else {
        const pairs = c.outcomes.split(",").map((p) => p.trim()).filter(Boolean).map((p) => {
          const at = p.lastIndexOf("="); if (at < 0) throw Error(`Write each outcome for ${where} as OUTCOME=PROBABILITY.`);
          return [p.slice(0, at).trim(), num(p.slice(at + 1), `A probability for ${where}`)] as const;
        });
        distribution = c.kind === "discrete"
          ? { kind: "discrete", values: pairs.map(([v]) => num(v, `An outcome for ${where}`)), probabilities: pairs.map(([, p]) => p) }
          : { kind: "categorical", labels: pairs.map(([v]) => v), probabilities: pairs.map(([, p]) => p) };
      }
      return { alternative_id: c.alternative, criterion_id: c.criterion, distribution };
    });
    const groups = draft.groups.filter((g) => g.kind !== "fixed").map((g) => ({
      parent_id: g.parent, kind: g.kind as "unknown" | "rating_intervals",
      intervals: g.kind === "unknown" ? {} : Object.fromEntries(Object.entries(g.intervals).map(([child, [lo, hi]]) =>
        [child, [num(lo, `The lower rating for ${criterionName(child)}`), num(hi, `The upper rating for ${criterionName(child)}`)] as [number, number]])),
    }));
    const shared = new Map<string, { alternative_id: string; criterion_id: string }[]>();
    for (const c of draft.cells) if (c.shared.trim()) {
      const id = slug(c.shared); shared.set(id, [...(shared.get(id) ?? []), { alternative_id: c.alternative, criterion_id: c.criterion }]);
    }
    return { dependence: "independent", cells, groups, shared_draws: [...shared].map(([id, refs]) => ({ id, cells: refs })) };
  } catch (error: unknown) {
    return error instanceof Error ? error.message : String(error);
  }
}

/** State uncertainty for SMAA-2 as a draft and apply it as one undoable change. */
export function UncertaintyPanel({ project, context, busy, apply }: {
  project: Project; context: AnalysisContext; busy: boolean; apply: (ops: Operation[]) => Promise<boolean>;
}) {
  const saved = project.smaa ?? null;
  // A new saved section (apply, undo, reload) restarts the draft from it.
  return <UncertaintyEditor key={canonical(saved)} project={project} context={context} busy={busy} apply={apply} saved={saved}/>;
}

function UncertaintyEditor({ project, context, busy, apply, saved }: {
  project: Project; context: AnalysisContext; busy: boolean; apply: (ops: Operation[]) => Promise<boolean>; saved: SmaaModel | null;
}) {
  const [draft, setDraft] = useState<Draft>(() => draftOf(saved, project));
  const [adding, setAdding] = useState({ alternative: project.alternatives[0]?.id ?? "", criterion: "" });
  const [confirmRemove, setConfirmRemove] = useState(false);
  const issues = useMethodIssues(project, context, SMAA, smaaIssue);
  const leaves = flatten(buildTree(project.criteria)).map((e) => e.node).filter((n) => isLeaf(project.criteria, n.id));
  const criterionName = (id: string) => project.criteria.find((c) => c.id === id)?.name ?? id;
  const alternativeName = (id: string) => project.alternatives.find((a) => a.id === id)?.name ?? id;
  const labelled = (id: string) => { const s = project.criteria.find((c) => c.id === id)?.scale; return s?.type === "categorical" || s?.type === "ordinal"; };
  const cellName = (c: DraftCell) => `${alternativeName(c.alternative)} on ${criterionName(c.criterion)}`;
  const model = modelOf(draft, cellName, criterionName);
  const empty = draftOf(null, project);
  const changed = typeof model === "string" || canonical(model) !== canonical(saved ?? modelOf(empty, cellName, criterionName));
  const set = (patch: (d: Draft) => void) => setDraft((d) => { const next = structuredClone(d); patch(next); return next; });
  const criterion = adding.criterion || leaves[0]?.id || "";
  const taken = draft.cells.some((c) => c.alternative === adding.alternative && c.criterion === criterion);

  return <section className="panel uncertainty-editor" aria-label="Uncertainty">
    <h2>Uncertainty</h2>
    <p className="muted">Stated uncertainty for SMAA-2. A distribution replaces a measurement only in SMAA-2 runs; MAVT and sorting keep
      the entered value. A missing measurement stays missing: enter it first. Supports must lie inside the value-function domain and are
      never clamped. Inputs are independent, except cells given the same shared-draw name, which move together.</p>
    {context.configuration.method !== SMAA && <p role="status">Choose the method “SMAA-2 (sampled acceptability)” in the header to see
      acceptabilities in Results.</p>}

    <h3>Measurements</h3>
    <div className="table-scroll" tabIndex={0}><table className="grid" aria-label="Uncertain measurements">
      <thead><tr><th>Measurement</th><th>Distribution</th><th>Parameters</th><th>Shared draw</th><th/></tr></thead>
      <tbody>{draft.cells.map((c, i) => {
        const name = cellName(c);
        const field = (key: "lower" | "mode" | "upper" | "outcomes", label: string) =>
          <label key={key}>{label} <input aria-label={`${label} for ${name}`} value={c[key]}
            onChange={(e) => set((d) => { const row = d.cells[i]; if (row) row[key] = e.target.value; })}/></label>;
        return <tr key={`${c.alternative}:${c.criterion}`}>
          <th scope="row">{name}</th>
          <td><select aria-label={`Distribution for ${name}`} value={c.kind}
            onChange={(e) => set((d) => { const row = d.cells[i]; if (row) row.kind = e.target.value as Kind; })}>
            {labelled(c.criterion) ? <option value="categorical">Categorical</option> : <>
              <option value="uniform">Uniform</option><option value="triangular">Triangular</option><option value="discrete">Discrete</option></>}
          </select></td>
          <td>{c.kind === "uniform" ? <>{field("lower", "Lower")}{field("upper", "Upper")}</>
            : c.kind === "triangular" ? <>{field("lower", "Lower")}{field("mode", "Mode")}{field("upper", "Upper")}</>
              : field("outcomes", "Outcomes (OUTCOME=P, …)")}</td>
          <td><input aria-label={`Shared draw for ${name}`} value={c.shared}
            onChange={(e) => set((d) => { const row = d.cells[i]; if (row) row.shared = e.target.value; })}/></td>
          <td><button type="button" aria-label={`Remove distribution for ${name}`} onClick={() => set((d) => { d.cells.splice(i, 1); })}>Remove</button></td>
        </tr>;
      })}</tbody>
    </table></div>
    {draft.cells.length === 0 && <p>No measurement has a stated distribution.</p>}
    <p className="class-row">
      <label>Alternative <select aria-label="New uncertain alternative" value={adding.alternative}
        onChange={(e) => setAdding((a) => ({ ...a, alternative: e.target.value }))}>
        {project.alternatives.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
      <label>Criterion <select aria-label="New uncertain criterion" value={criterion}
        onChange={(e) => setAdding((a) => ({ ...a, criterion: e.target.value }))}>
        {leaves.map((n) => <option key={n.id} value={n.id}>{n.name}</option>)}</select></label>
      <button type="button" disabled={!adding.alternative || !criterion || taken} onClick={() => set((d) => {
        d.cells.push({ alternative: adding.alternative, criterion, kind: labelled(criterion) ? "categorical" : "uniform",
          lower: "", mode: "", upper: "", outcomes: "", shared: "" });
      })}>Add distribution</button>
    </p>

    <h3>Weights</h3>
    <p className="muted small">Fixed keeps the profile’s ratings. Unknown draws local weights uniformly within the group. Rating intervals draw
      each raw swing rating uniformly between its bounds, then normalise within the group.</p>
    {draft.groups.map((g, i) => {
      const group = siblingGroups(project)[i];
      const name = group?.name ?? "group";
      return <fieldset key={String(g.parent)} aria-label={`Weights under ${name}`}>
        <legend>{name}</legend>
        <select aria-label={`Weight uncertainty under ${name}`} value={g.kind}
          onChange={(e) => set((d) => { const row = d.groups[i]; if (row) row.kind = e.target.value as GroupKind; })}>
          <option value="fixed">Fixed</option><option value="unknown">Unknown</option><option value="rating_intervals">Rating intervals</option>
        </select>
        {g.kind === "rating_intervals" && Object.entries(g.intervals).map(([child, [lo, hi]]) => <span key={child} className="class-row">
          {criterionName(child)}
          <input aria-label={`Lower rating for ${criterionName(child)}`} value={lo}
            onChange={(e) => set((d) => { const row = d.groups[i]; if (row) row.intervals[child] = [e.target.value, row.intervals[child]?.[1] ?? ""]; })}/>
          to <input aria-label={`Upper rating for ${criterionName(child)}`} value={hi}
            onChange={(e) => set((d) => { const row = d.groups[i]; if (row) row.intervals[child] = [row.intervals[child]?.[0] ?? "", e.target.value]; })}/>
        </span>)}
      </fieldset>;
    })}

    {typeof model === "string" && <p role="alert">{model}</p>}
    <p>
      <button type="button" className="primary" disabled={busy || !changed || typeof model === "string"}
        onClick={() => { if (typeof model !== "string") void apply([{ op: "set_smaa_model", smaa: model }]); }}>Apply uncertainty</button>{" "}
      <button type="button" disabled={!changed} onClick={() => setDraft(draftOf(saved, project))}>Cancel changes</button>{" "}
      <button type="button" disabled={busy || saved === null} onClick={() => setConfirmRemove(true)}>Remove all uncertainty</button>
    </p>
    <h3>Checks on the saved uncertainty</h3>
    {issues.status === "loading" && <p role="status">Checking uncertainty…</p>}
    {issues.status === "error" && <><p role="alert">{issues.message}</p><button type="button" onClick={issues.retry}>Retry check</button></>}
    {issues.status === "ready" && (issues.result.length === 0
      ? <p role="status">No problems with the saved uncertainty.</p>
      : <ul className="issue-list inline" aria-label="Uncertainty issues">{issues.result.map((issue, i) =>
        <li key={i} className={issue.severity}><code>{issue.code}</code> {issue.message} <span>{issue.path}</span></li>)}</ul>)}
    {confirmRemove && <ConfirmDialog title="Remove all uncertainty" danger
      message="The uncertainty section is removed from the project, which is then saved at the lowest schema version it needs. You can undo this."
      confirmLabel="Remove uncertainty" onCancel={() => setConfirmRemove(false)}
      onConfirm={() => { setConfirmRemove(false); void apply([{ op: "clear_smaa_model" }]); }}/>}
  </section>;
}
