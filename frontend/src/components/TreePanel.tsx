import { useMemo, useRef, useState, type ReactNode } from "react";
import type { Operation, Project, ValidationReport } from "../api/types";
import { swingRatings } from "../model/diagram";
import { addingChildDiscards, childrenOf, planMove, type MoveDirection } from "../model/tree";
import { descendantIds, indexTree } from "../model/visibleTree";
import { ModelTree, type DiagramOptions, type TreePresentation } from "./ModelTree";
import { ConfirmDialog } from "./ui";

interface Props {
  project: Project;
  validation: ValidationReport;
  selectedId: string | null;
  busy: boolean;
  onSelect: (id: string | null) => void;
  onAdd: (parentId: string | null, position: number | null, discard: boolean) => Promise<void>;
  apply: (ops: Operation[]) => Promise<boolean>;
  presentation?: TreePresentation;
  onPresentation?: (value: TreePresentation) => void;
  onEdit?: (id: string) => void;
  onGoal?: () => void;
  goalSelected?: boolean;
  /** Canvas diagram extras; the goal card is built here. */
  diagram?: Omit<DiagramOptions, "goal">;
  /** Extra canvas controls for the view bar (weights display, presentation). */
  viewExtras?: ReactNode;
}

type Confirm =
  | { kind: "none" }
  | { kind: "remove"; id: string }
  | { kind: "add-child"; id: string }
  | { kind: "indent"; id: string };

export function TreePanel({ project, validation, selectedId, busy: pending, onSelect, onAdd, apply, presentation, onPresentation, onEdit, onGoal, goalSelected, diagram, viewExtras }: Props) {
  const index = useMemo(() => indexTree(project.criteria), [project.criteria]);
  const [local, setLocal] = useState<TreePresentation>({ mode: "outline", collapsed: new Set() });
  const view = presentation ?? local;
  const changeView = onPresentation ?? setLocal;
  const addButton = useRef<HTMLButtonElement>(null);
  const [confirm, setConfirm] = useState<Confirm>({ kind: "none" });
  const busy = pending || index.errors.length > 0;

  const selected = project.criteria.find((n) => n.id === selectedId) ?? null;
  const plan = (d: MoveDirection) => (selected ? planMove(project, selected.id, d) : null);

  async function move(d: MoveDirection, discard = false) {
    const p = selected && planMove(project, selected.id, d);
    if (!selected || !p) return;
    if (p.needsDiscard && !discard) {
      setConfirm({ kind: "indent", id: selected.id });
      return;
    }
    await apply([
      {
        op: "move_criterion",
        criterion_id: selected.id,
        new_parent_id: p.new_parent_id,
        position: p.position,
        discard_leaf_data: discard,
      },
    ]);
  }

  function addChild() {
    if (!selected) return;
    if (addingChildDiscards(project, selected.id)) {
      setConfirm({ kind: "add-child", id: selected.id });
      return;
    }
    void onAdd(selected.id, null, false);
  }

  function addSibling() {
    if (!selected) return;
    const siblings = childrenOf(project.criteria, selected.parent_id ?? null);
    const at = siblings.findIndex((n) => n.id === selected.id);
    void onAdd(selected.parent_id ?? null, at + 1, false);
  }

  const removing = confirm.kind === "remove" ? project.criteria.find((n) => n.id === confirm.id) : null;
  const removingIds = removing ? [...descendantIds(index, removing.id)] : [];
  const removingMeasurements = project.performances.filter((p) => removingIds.includes(p.criterion_id)).length;
  const inDiagram = view.mode === "canvas" && diagram !== undefined;
  const topSwing = diagram ? swingRatings(project, index, diagram.profileId, null) : null;
  const goal = onGoal && <div className={`model-goal-card ${view.mode}`}>
    <button type="button" className={`model-goal ${view.mode}`} aria-pressed={goalSelected}
      aria-label={`Edit goal: ${project.title}`} onClick={onGoal}>
      <span className="model-kind">Goal</span><strong>{project.title}</strong><span className="muted small">Edit project settings</span>
    </button>
    {inDiagram && diagram.onEditWeights && topSwing && topSwing.children > 0 && <button type="button"
      className={`model-chip${topSwing.missing ? " attention" : ""}`} aria-label="Edit swing weights for the top-level objectives"
      onClick={() => diagram.onEditWeights?.(null)}>Swing{topSwing.missing ? ` · ${String(topSwing.missing)} missing` : ""}</button>}
  </div>;

  return (
    <section className="tree-panel" aria-label="Objectives and criteria">
      <div className="model-view-bar">
        <div role="group" aria-label="Model view">
          <button type="button" aria-pressed={view.mode === "canvas"} onClick={() => changeView({ ...view, mode: "canvas" })}>Canvas</button>
          <button type="button" aria-pressed={view.mode === "outline"} onClick={() => changeView({ ...view, mode: "outline" })}>Outline</button>
        </div>
        {view.mode === "canvas" && viewExtras}
        {onEdit && <button type="button" disabled={busy || !selected} onClick={() => { if (selected) onEdit(selected.id); }}>Edit selected item</button>}
      </div>
      {!inDiagram && goal}
      <div className="panel-toolbar" role="toolbar" aria-label="Edit the criteria tree">
        <button ref={addButton} type="button" disabled={busy} onClick={() => void onAdd(null, null, false)}>
          Add top-level objective
        </button>
        <button type="button" disabled={busy || !selected} onClick={addChild}>
          Add child
        </button>
        <button type="button" disabled={busy || !selected} onClick={addSibling}>
          Add sibling
        </button>
        <span className="sep" />
        <button type="button" disabled={busy || !plan("up")} aria-label="Move up" title="Move up" onClick={() => void move("up")}>
          ↑
        </button>
        <button type="button" disabled={busy || !plan("down")} aria-label="Move down" title="Move down" onClick={() => void move("down")}>
          ↓
        </button>
        <button
          type="button"
          disabled={busy || !plan("indent")}
          aria-label="Indent"
          title="Indent: make it a child of the item above"
          onClick={() => void move("indent")}
        >
          →
        </button>
        <button
          type="button"
          disabled={busy || !plan("outdent")}
          aria-label="Outdent"
          title="Outdent: make it a sibling of its parent"
          onClick={() => void move("outdent")}
        >
          ←
        </button>
        <span className="sep" />
        <button type="button" className="danger-text" disabled={busy || !selected} onClick={() => selected && setConfirm({ kind: "remove", id: selected.id })}>
          Remove
        </button>
      </div>

      <ModelTree project={project} index={index} validation={validation} selectedId={selectedId}
        presentation={view} onPresentation={changeView} onSelect={onSelect} onEdit={onEdit}
        onRemove={id => setConfirm({ kind: "remove", id })} onFocusRemoved={() => addButton.current?.focus()} busy={busy}
        diagram={inDiagram ? { ...diagram, goal } : undefined} />

      {confirm.kind === "remove" && removing && (
        <ConfirmDialog
          title="Remove criterion"
          danger
          confirmLabel="Remove"
          message={
            <>
              Remove <strong>{removing.name}</strong>
              {removingIds.length > 1 ? ` and its ${String(removingIds.length - 1)} sub-item(s)` : ""}
              {removingMeasurements > 0
                ? `, together with ${String(removingMeasurements)} entered measurement(s)`
                : ""}
              ? Swing ratings of the remaining siblings are re-normalised automatically. You can undo
              this until you close the project.
            </>
          }
          onCancel={() => setConfirm({ kind: "none" })}
          onConfirm={() => {
            setConfirm({ kind: "none" });
            void apply([{ op: "remove_criterion", criterion_id: removing.id }]).then(ok => {
              if (!ok) return;
              if (selectedId && removingIds.includes(selectedId)) onSelect(null);
              addButton.current?.focus();
            });
          }}
        />
      )}
      {confirm.kind === "add-child" && (
        <ConfirmDialog
          title="Turn a measured criterion into a group?"
          danger
          confirmLabel="Discard its data and add the child"
          message="This criterion has a scale, a value function or entered measurements. A criterion with children is a group and cannot be measured itself, so that data would be discarded."
          onCancel={() => setConfirm({ kind: "none" })}
          onConfirm={() => {
            setConfirm({ kind: "none" });
            void onAdd(confirm.id, null, true);
          }}
        />
      )}
      {confirm.kind === "indent" && (
        <ConfirmDialog
          title="Move under a measured criterion?"
          danger
          confirmLabel="Discard its data and move"
          message="The item above is a measured criterion. Putting something under it turns it into a group, discarding its scale, value function and measurements."
          onCancel={() => setConfirm({ kind: "none" })}
          onConfirm={() => {
            setConfirm({ kind: "none" });
            void move("indent", true);
          }}
        />
      )}
    </section>
  );
}
