import { useState } from "react";
import type { Issue, Operation, Project, SortingModel } from "../api/types";
import { canonical, type AnalysisContext } from "../state/analysisContext";
import { useMethodIssues } from "../state/useMethodIssues";
import { ConfirmDialog } from "./ui";

const SORTING = "mavt_sorting";

interface DraftClass { id: string; name: string; description: string; boundary: string }
interface Draft {
  classes: DraftClass[];
  audit: { enabled: boolean; below: string; size: string; seed: string };
}

function draftOf(model: SortingModel | null | undefined): Draft {
  return {
    classes: (model?.classes ?? []).map((c) => ({ id: c.id, name: c.name, description: c.description,
      boundary: c.lower_boundary === null ? "" : String(c.lower_boundary) })),
    audit: model?.audit
      ? { enabled: true, below: model.audit.below_class_id, size: String(model.audit.sample_size), seed: String(model.audit.seed) }
      : { enabled: false, below: "", size: "1", seed: "0" },
  };
}

const slug = (name: string) => name.trim().replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").toLowerCase().slice(0, 48) || "class";

/** The draft as a sorting section, or the first entry that is not a number. Rules are the engine's. */
function modelOf(draft: Draft): SortingModel | string {
  const classes: SortingModel["classes"] = [];
  for (const [i, c] of draft.classes.entries()) {
    const lowest = i === draft.classes.length - 1;
    const text = c.boundary.trim();
    const value = text === "" || lowest ? null : Number(text);
    if (value !== null && !Number.isFinite(value)) return `The boundary of ${c.name} must be a number.`;
    classes.push({ id: c.id, name: c.name, description: c.description, lower_boundary: value });
  }
  if (!draft.audit.enabled) return { classes, audit: null };
  const size = Number(draft.audit.size), seed = Number(draft.audit.seed);
  if (!Number.isInteger(size) || !Number.isInteger(seed)) return "The audit sample size and seed must be whole numbers.";
  return { classes, audit: { below_class_id: draft.audit.below, sample_size: size, seed } };
}

const sortingIssue = (i: Issue) => i.path === "sorting" || i.path.startsWith("sorting.");

/** Edit ordered classes as a draft and apply it as one undoable change. Boundaries are never sorted. */
export function ClassesPanel({ project, context, busy, apply }: {
  project: Project; context: AnalysisContext; busy: boolean; apply: (ops: Operation[]) => Promise<boolean>;
}) {
  const saved = project.sorting ?? null;
  // A new saved section (apply, undo, reload) restarts the draft from it.
  return <ClassesEditor key={canonical(saved)} project={project} context={context} busy={busy} apply={apply} saved={saved}/>;
}

function ClassesEditor({ project, context, busy, apply, saved }: {
  project: Project; context: AnalysisContext; busy: boolean; apply: (ops: Operation[]) => Promise<boolean>; saved: SortingModel | null;
}) {
  const [draft, setDraft] = useState<Draft>(() => draftOf(saved));
  const [confirmRemove, setConfirmRemove] = useState(false);
  const issues = useMethodIssues(project, context, SORTING, sortingIssue);
  const model = modelOf(draft);
  const changed = typeof model === "string" || canonical(model) !== canonical(saved ?? { classes: [], audit: null });
  const set = (patch: (d: Draft) => Draft) => setDraft((d) => patch(structuredClone(d)));
  const lowestIndex = draft.classes.length - 1;

  function add() {
    set((d) => {
      const taken = new Set(d.classes.map((c) => c.id));
      let id = slug("New class"), n = 2;
      while (taken.has(id)) id = `${slug("New class")}_${String(n++)}`;
      d.classes.push({ id, name: "New class", description: "", boundary: "" });
      return d;
    });
  }
  function move(i: number, by: number) {
    set((d) => { const [c] = d.classes.splice(i, 1); if (c) d.classes.splice(i + by, 0, c); return d; });
  }

  return <section className="panel classes-editor" aria-label="Classes">
    <h2>Classes</h2>
    <p className="muted">Ordered classes for value-based sorting, best first. Each class except the lowest has a lower boundary: the overall
      MAVT value needed to enter it. A value within 1e-12 of a boundary goes to the higher class. Boundaries are never reordered for you:
      if the list is out of order, the engine reports it. Classes are not probabilities or predictions.</p>
    {context.configuration.method !== SORTING && <p role="status">Choose the method “Value-based sorting (MAVT)” in the header to see these
      classes in Results and Sensitivity.</p>}
    <div className="class-rows" role="list" aria-label="Class list">
      {draft.classes.map((c, i) => <div className="class-row" role="listitem" key={c.id} data-class-id={c.id}>
        <span>{i + 1}.</span>
        <label>Name <input aria-label={`Class ${String(i + 1)} name`} value={c.name}
          onChange={(e) => set((d) => { const row = d.classes[i]; if (row) row.name = e.target.value; return d; })}/></label>
        {i === lowestIndex
          ? <span className="muted small">takes every remaining value</span>
          : <label>Lower boundary <input aria-label={`Lower boundary of ${c.name}`} inputMode="decimal" value={c.boundary}
            onChange={(e) => set((d) => { const row = d.classes[i]; if (row) row.boundary = e.target.value; return d; })}/></label>}
        <code>{c.id}</code>
        <button type="button" disabled={i === 0} aria-label={`Move ${c.name} up`} onClick={() => move(i, -1)}>↑</button>
        <button type="button" disabled={i === lowestIndex} aria-label={`Move ${c.name} down`} onClick={() => move(i, 1)}>↓</button>
        <button type="button" aria-label={`Remove ${c.name}`} onClick={() => set((d) => { d.classes.splice(i, 1); return d; })}>Remove</button>
      </div>)}
    </div>
    {draft.classes.length === 0 && <p>This project has no classes yet.</p>}
    <p><button type="button" onClick={add}>Add class</button></p>
    <fieldset>
      <legend>Audit sample</legend>
      <label><input type="checkbox" checked={draft.audit.enabled} aria-label="Audit sample"
        onChange={(e) => set((d) => { d.audit.enabled = e.target.checked; if (!d.audit.below) d.audit.below = d.classes[0]?.id ?? ""; return d; })}/>
        Sample alternatives sorted below a cut-off, for manual review of possible false negatives</label>
      {draft.audit.enabled && <div className="class-row">
        <label>Below class <select aria-label="Audit cut-off class" value={draft.audit.below}
          onChange={(e) => set((d) => { d.audit.below = e.target.value; return d; })}>
          {draft.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select></label>
        <label>Sample size <input aria-label="Audit sample size" inputMode="numeric" value={draft.audit.size}
          onChange={(e) => set((d) => { d.audit.size = e.target.value; return d; })}/></label>
        <label>Seed <input aria-label="Audit seed" inputMode="numeric" value={draft.audit.seed}
          onChange={(e) => set((d) => { d.audit.seed = e.target.value; return d; })}/></label>
      </div>}
    </fieldset>
    {typeof model === "string" && <p role="alert">{model}</p>}
    <p>
      <button type="button" className="primary" disabled={busy || !changed || typeof model === "string"}
        onClick={() => { if (typeof model !== "string") void apply([{ op: "set_sorting_model", sorting: model }]); }}>Apply classes</button>{" "}
      <button type="button" disabled={!changed} onClick={() => setDraft(draftOf(saved))}>Cancel changes</button>{" "}
      <button type="button" disabled={busy || saved === null} onClick={() => setConfirmRemove(true)}>Remove all classes</button>
    </p>
    <h3>Checks on the saved classes</h3>
    {issues.status === "loading" && <p role="status">Checking classes…</p>}
    {issues.status === "error" && <><p role="alert">{issues.message}</p><button type="button" onClick={issues.retry}>Retry check</button></>}
    {issues.status === "ready" && (issues.result.length === 0
      ? <p role="status">No problems with the saved classes.</p>
      : <ul className="issue-list inline" aria-label="Class issues">{issues.result.map((issue, i) =>
        <li key={i} className={issue.severity}><code>{issue.code}</code> {issue.message} <span>{issue.path}</span></li>)}</ul>)}
    {confirmRemove && <ConfirmDialog title="Remove all classes" danger
      message="The sorting section is removed from the project. A project without it is saved as schema version 1 again. You can undo this."
      confirmLabel="Remove classes" onCancel={() => setConfirmRemove(false)}
      onConfirm={() => { setConfirmRemove(false); void apply([{ op: "clear_sorting_model" }]); }}/>}
  </section>;
}
