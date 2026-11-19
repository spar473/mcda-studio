import { useCallback, useState } from "react";
import { api } from "../api/client";
import type { CriterionNode, Operation, Project, Requirement } from "../api/types";
import { buildTree, flatten, isLeaf } from "../model/tree";
import { canonical } from "../state/analysisContext";
import { useAnalysisRequest } from "../state/useAnalysisRequest";
import { FeasibilityView } from "./results/FeasibilityView";
import { ConfirmDialog } from "./ui";

interface DraftRow {
  id: string; name: string; criterion: string; rationale: string;
  unit: string; minimum: string; minimumInclusive: boolean; maximum: string; maximumInclusive: boolean; allowed: string[];
}
const numeric = (leaf: CriterionNode | undefined) => leaf?.scale?.type === "interval" || leaf?.scale?.type === "ratio";
const slug = (name: string) => name.trim().replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").toLowerCase().slice(0, 48) || "requirement";

function draftOf(requirements: Requirement[] | null | undefined): DraftRow[] {
  return (requirements ?? []).map((r): DraftRow => r.kind === "bound"
    ? { id: r.id, name: r.name, criterion: r.criterion_id, rationale: r.rationale, unit: r.unit ?? "", allowed: [],
      minimum: r.minimum === null ? "" : String(r.minimum), minimumInclusive: r.minimum_inclusive,
      maximum: r.maximum === null ? "" : String(r.maximum), maximumInclusive: r.maximum_inclusive }
    : { id: r.id, name: r.name, criterion: r.criterion_id, rationale: r.rationale, unit: "", allowed: [...r.allowed],
      minimum: "", minimumInclusive: true, maximum: "", maximumInclusive: true });
}

/** The draft as requirements, or the first entry that cannot be read. The rules are the engine's. */
function modelOf(rows: DraftRow[], leaves: CriterionNode[]): Requirement[] | string {
  const limit = (text: string, what: string) => {
    if (text.trim() === "") return null;
    const v = Number(text.trim()); if (!Number.isFinite(v)) throw Error(`${what} must be a number.`); return v;
  };
  try {
    return rows.map((r): Requirement => {
      if (!r.name.trim()) throw Error("Every requirement needs a name.");
      const leaf = leaves.find((l) => l.id === r.criterion);
      if (numeric(leaf)) {
        return { kind: "bound", id: r.id, name: r.name.trim(), criterion_id: r.criterion, rationale: r.rationale,
          unit: r.unit.trim() === "" ? null : r.unit.trim(),
          minimum: limit(r.minimum, `The minimum of ${r.name}`), minimum_inclusive: r.minimumInclusive,
          maximum: limit(r.maximum, `The maximum of ${r.name}`), maximum_inclusive: r.maximumInclusive };
      }
      return { kind: "labels", id: r.id, name: r.name.trim(), criterion_id: r.criterion, rationale: r.rationale, allowed: r.allowed };
    });
  } catch (error: unknown) {
    return error instanceof Error ? error.message : String(error);
  }
}

/** Mandatory requirements as a draft, applied as one undoable change. No method reads them. */
export function RequirementsPanel({ project, busy, apply }: {
  project: Project; busy: boolean; apply: (ops: Operation[]) => Promise<boolean>;
}) {
  const saved = project.requirements ?? null;
  return <RequirementsEditor key={canonical(saved)} project={project} busy={busy} apply={apply} saved={saved}/>;
}

function RequirementsEditor({ project, busy, apply, saved }: {
  project: Project; busy: boolean; apply: (ops: Operation[]) => Promise<boolean>; saved: Requirement[] | null;
}) {
  const leaves = flatten(buildTree(project.criteria)).map((e) => e.node).filter((n) => isLeaf(project.criteria, n.id));
  const [rows, setRows] = useState<DraftRow[]>(() => draftOf(saved));
  const [adding, setAdding] = useState(leaves[0]?.id ?? "");
  const [confirmRemove, setConfirmRemove] = useState(false);
  const model = modelOf(rows, leaves);
  const changed = typeof model === "string" || canonical(model) !== canonical(saved ?? []);
  const set = (i: number, patch: (r: DraftRow) => void) => setRows((all) => { const next = structuredClone(all); const row = next[i]; if (row) patch(row); return next; });
  const draft = typeof model === "string" || model.length === 0 ? null : model;
  const key = canonical({ kind: "feasibility-draft", project: project.id, draft, performances: project.performances, criteria: project.criteria, alternatives: project.alternatives });
  const load = useCallback((signal: AbortSignal) => api.checkFeasibility({ ...project, requirements: draft }, signal), [key]); // eslint-disable-line react-hooks/exhaustive-deps
  const preview = useAnalysisRequest(key, draft !== null, load);

  function add() {
    const leaf = leaves.find((l) => l.id === adding);
    if (!leaf) return;
    const taken = new Set(rows.map((r) => r.id));
    let id = slug(leaf.name); for (let k = 2; taken.has(id); k++) id = `${slug(leaf.name)}_${String(k)}`;
    setRows((all) => [...all, { id, name: `${leaf.name} requirement`, criterion: leaf.id, rationale: "", unit: leaf.scale?.unit ?? "",
      minimum: "", minimumInclusive: true, maximum: "", maximumInclusive: true, allowed: [] }]);
  }

  return <section className="panel requirements-editor" aria-label="Requirements">
    <h2>Requirements</h2>
    <p className="muted">Mandatory requirements on individual measurements, such as a price ceiling or a required certification. Each
      alternative passes, fails or is unknown (a missing measurement is unknown, never a failure). No method reads them, no score offsets a
      failure, and no ranking is changed or filtered: the result is shown beside every ranking. Limits are compared exactly, in the unit
      you state, which must be the criterion’s own; nothing is converted.</p>
    {rows.length === 0 && <p>No requirements yet.</p>}
    {rows.map((r, i) => {
      const leaf = leaves.find((l) => l.id === r.criterion);
      const labels = leaf?.scale?.labels ?? [];
      const ordinal = leaf?.scale?.type === "ordinal";
      return <fieldset key={r.id} aria-label={`Requirement ${r.name}`} data-requirement-id={r.id}>
        <legend>{r.name || r.id}</legend>
        <span className="class-row">
          <label>Name <input aria-label={`Name of ${r.id}`} value={r.name} onChange={(e) => set(i, (row) => { row.name = e.target.value; })}/></label>
          <span className="muted small">on {leaf?.name ?? r.criterion}</span>
          <button type="button" aria-label={`Remove requirement ${r.name}`} onClick={() => setRows((all) => all.filter((_, k) => k !== i))}>Remove</button>
        </span>
        {numeric(leaf) ? <span className="class-row">
          <label>Minimum <input aria-label={`Minimum of ${r.name}`} inputMode="decimal" value={r.minimum} onChange={(e) => set(i, (row) => { row.minimum = e.target.value; })}/></label>
          <label><input type="checkbox" aria-label={`Minimum of ${r.name} itself passes`} checked={r.minimumInclusive}
            onChange={(e) => set(i, (row) => { row.minimumInclusive = e.target.checked; })}/> itself passes</label>
          <label>Maximum <input aria-label={`Maximum of ${r.name}`} inputMode="decimal" value={r.maximum} onChange={(e) => set(i, (row) => { row.maximum = e.target.value; })}/></label>
          <label><input type="checkbox" aria-label={`Maximum of ${r.name} itself passes`} checked={r.maximumInclusive}
            onChange={(e) => set(i, (row) => { row.maximumInclusive = e.target.checked; })}/> itself passes</label>
          <label>Unit <input aria-label={`Unit of ${r.name}`} value={r.unit} onChange={(e) => set(i, (row) => { row.unit = e.target.value; })}/></label>
          <span className="muted small">the criterion is measured in {leaf?.scale?.unit ?? "no unit"}</span>
        </span> : <span className="class-row" aria-label={`Allowed labels of ${r.name}`}>
          {labels.map((label) => <label key={label}><input type="checkbox" aria-label={`Allow ${label} for ${r.name}`} checked={r.allowed.includes(label)}
            onChange={(e) => set(i, (row) => { row.allowed = labels.filter((l) => l === label ? e.target.checked : row.allowed.includes(l)); })}/> {label}</label>)}
          {ordinal && labels.map((label, k) => <button key={`least-${label}`} type="button" onClick={() => set(i, (row) => { row.allowed = labels.slice(k); })}>
            At least {label}</button>)}
          {ordinal && labels.map((label, k) => <button key={`most-${label}`} type="button" onClick={() => set(i, (row) => { row.allowed = labels.slice(0, k + 1); })}>
            At most {label}</button>)}
        </span>}
        <label>Rationale <input aria-label={`Rationale of ${r.name}`} value={r.rationale} onChange={(e) => set(i, (row) => { row.rationale = e.target.value; })}/></label>
      </fieldset>;
    })}
    <p className="class-row">
      <label>Criterion <select aria-label="New requirement criterion" value={adding} onChange={(e) => setAdding(e.target.value)}>
        {leaves.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
      <button type="button" disabled={!adding} onClick={add}>Add requirement</button>
    </p>
    {typeof model === "string" && <p role="alert">{model}</p>}
    <p>
      <button type="button" className="primary" disabled={busy || !changed || typeof model === "string"}
        onClick={() => { if (typeof model !== "string") void apply([{ op: "set_requirements", requirements: model }]); }}>Apply requirements</button>{" "}
      <button type="button" disabled={!changed} onClick={() => setRows(draftOf(saved))}>Cancel changes</button>{" "}
      <button type="button" disabled={busy || saved === null} onClick={() => setConfirmRemove(true)}>Remove all requirements</button>
    </p>
    <h3>Result of the draft</h3>
    {draft === null && <p className="muted small">Add a requirement to see who passes.</p>}
    {draft !== null && preview.status === "loading" && <p role="status">Checking requirements…</p>}
    {draft !== null && preview.status === "error" && <p role="alert" aria-label="Requirement problems">{preview.message}</p>}
    {draft !== null && preview.status === "ready" && <FeasibilityView result={preview.result}/>}
    {confirmRemove && <ConfirmDialog title="Remove all requirements" danger
      message="The requirements are removed from the project, which is then saved at the lowest schema version it needs. You can undo this."
      confirmLabel="Remove requirements" onCancel={() => setConfirmRemove(false)}
      onConfirm={() => { setConfirmRemove(false); void apply([{ op: "clear_requirements" }]); }}/>}
  </section>;
}
