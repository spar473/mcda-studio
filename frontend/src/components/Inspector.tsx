import { useEffect, useRef } from "react";
import type { CriterionNode, Meta, Operation, Project, ValidationReport } from "../api/types";
import { issuesForCriterion } from "../model/issues";
import { childrenOf, pathNames } from "../model/tree";
import type { AnalysisContext } from "../state/analysisContext";
import { CriterionPreview } from "./CriterionPreview";
import { MeasurementEditor } from "./MeasurementEditor";
import { CommitText, Field } from "./ui";

interface Props {
  project: Project;
  context: AnalysisContext;
  node: CriterionNode | null;
  meta: Meta | null;
  validation: ValidationReport;
  apply: (ops: Operation[]) => Promise<boolean>;
  busy: boolean;
  onEditFunction: () => void;
  /** Increment to move keyboard focus to the name field (after adding an item). */
  focusNameKey: number;
  /** Increment to move focus to the measurement type of an unconfigured criterion. */
  focusSetupKey?: number;
  /** Open the swing weights of this group's children (keyboard route for the canvas chip). */
  onEditWeights?: (groupId: string) => void;
}

export function Inspector({ project, context, node, meta, validation, apply, busy, focusNameKey, focusSetupKey = 0, onEditFunction, onEditWeights }: Props) {
  const setupFocus = useRef<Element | null | undefined>(undefined);
  useEffect(() => {
    setupFocus.current = focusSetupKey > 0 ? document.activeElement : undefined;
  }, [focusSetupKey]);
  useEffect(() => {
    if (busy || !meta || setupFocus.current === undefined) return;
    const element = document.getElementById("me-type");
    if (!element) return;
    const from = setupFocus.current; setupFocus.current = undefined;
    if (document.activeElement === document.body || document.activeElement === from) element.focus();
  }, [focusSetupKey, busy, meta, node?.id]);
  if (!node) {
    return (
      <section className="inspector" aria-label="Criterion settings">
        <div className="empty small-empty">
          <p>Select an item in the tree to edit it.</p>
        </div>
      </section>
    );
  }
  const children = childrenOf(project.criteria, node.id);
  const issues = issuesForCriterion(validation, node.id);
  const path = pathNames(project.criteria, node.id);
  return (
    <section className="inspector" aria-label="Criterion settings">
      <div className="crumbs muted small">{path.length <= 8 ? path.join("  ›  ") : <details><summary>{[...path.slice(0, 2), "…", ...path.slice(-3)].join(" › ")}</summary><p>{path.join(" › ")}</p></details>}</div>
      <h2 className="inspector-title">{children.length ? "Objective" : "Criterion"}</h2>
      <Field label="Name" htmlFor="insp-name">
        <CommitText
          label="Name"
          disabled={busy}
          value={node.name}
          required
          selectOnFocus
          focusKey={focusNameKey}
          onCommit={(name) => void apply([{ op: "update_criterion", criterion_id: node.id, name }])}
        />
      </Field>
      <Field label="Description" htmlFor="insp-desc">
        <CommitText
          label="Description"
          disabled={busy}
          multiline
          value={node.description}
          onCommit={(description) => void apply([{ op: "update_criterion", criterion_id: node.id, description }])}
        />
      </Field>
      <div className="muted small">
        Identifier <code>{node.id}</code> (fixed; renaming never changes it)
      </div>

      {(children.length > 0 || node.parent_id === null) && (
        <p className="model-hint" role="note">
          <strong>Fundamental or means?</strong> Ask why this objective matters. If the answer is another
          objective already in the tree, this one may be a means to it, and measuring both can count the
          same benefit twice.
        </p>
      )}
      {children.length > 0 ? (
        <>
          <p className="note">
            A group of {children.length} item(s). A group is not measured itself; how much each child
            matters is set on the <strong>Weights</strong> tab.
          </p>
          {onEditWeights && <p><button type="button" onClick={() => onEditWeights(node.id)}>Edit swing weights for this group</button></p>}
        </>
      ) : meta ? (
        <MeasurementEditor project={project} node={node} meta={meta} apply={apply} busy={busy} />
      ) : (
        <p className="muted">Loading settings…</p>
      )}

      {children.length === 0 && node.scale && node.value_function && <p><button type="button" disabled={busy} onClick={onEditFunction}>Open graphical value-function editor</button></p>}
      {children.length === 0 && <CriterionPreview project={project} context={context} />}

      {issues.length > 0 && (
        <ul className="issue-list inline" aria-label="Problems with this item">
          {issues.map((i, k) => (
            <li key={k} className={i.severity}>
              <span className="code">{i.code}</span> {i.message}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
