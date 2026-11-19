import type { Operation, Project } from "../api/types";
import { useMemo } from "react";
import { indexTree } from "../model/visibleTree";
import { CommitText, Field } from "./ui";

interface Props {
  project: Project;
  apply: (ops: Operation[]) => Promise<boolean>;
  focusTitleKey?: number;
  busy?: boolean;
}

export function ProjectPanel({ project, apply, focusTitleKey, busy }: Props) {
  const index = useMemo(() => indexTree(project.criteria), [project.criteria]);
  return (
    <section className="panel" aria-label="Project details">
      <h2>Project</h2>
      <div className="form-narrow">
        <Field label="Title">
          <CommitText
            label="Project title"
            focusKey={focusTitleKey}
            disabled={busy}
            value={project.title}
            required
            onCommit={(title) => void apply([{ op: "update_project", title }])}
          />
        </Field>
        <Field label="Description">
          <CommitText
            label="Project description"
            disabled={busy}
            multiline
            value={project.description}
            onCommit={(description) => void apply([{ op: "update_project", description }])}
          />
        </Field>
        <Field label="Decision maker">
          <CommitText
            label="Decision maker"
            disabled={busy}
            value={project.decision_maker}
            onCommit={(decision_maker) => void apply([{ op: "update_project", decision_maker }])}
          />
        </Field>
      </div>

      <h3>Summary</h3>
      <dl className="facts">
        <dt>Method</dt>
        <dd>{project.analysis.method === "mavt" ? "Additive multi-attribute value (swing weights)" : project.analysis.method}</dd>
        <dt>Alternatives</dt>
        <dd>{project.alternatives.length}</dd>
        <dt>Criteria</dt>
        <dd>
          {index.errors.length ? `${String(project.criteria.length)} incoming nodes; hierarchy needs correction` : `${String(index.rows.filter(row => !index.children.has(row.node.id)).length)} leaf criteria, ${String(project.criteria.length)} nodes in total, ${String(index.rows.reduce((max, row) => Math.max(max, row.depth), 0))} level(s) deep`}
        </dd>
        <dt>Identifier</dt>
        <dd>
          <code>{project.id}</code>
        </dd>
      </dl>

      <h3>Weight profiles and scenarios</h3>
      <p className="muted small">
        Kept exactly as stored and used by Results. Edit weight profiles in Weights and scenarios
        in Scenarios.
      </p>
      <ul className="plain">
        {project.weight_profiles.map((p) => (
          <li key={p.id}>
            Weight profile <strong>{p.name}</strong> <span className="muted">({Object.keys(p.judgements).length} ratings)</span>
          </li>
        ))}
        {project.scenarios.map((s) => (
          <li key={s.id}>
            Scenario <strong>{s.name}</strong>{" "}
            <span className="muted">
              ({Object.keys(s.value_function_overrides).length} value-function override(s)
              {s.weight_profile_id ? `, profile ${s.weight_profile_id}` : ""})
            </span>
          </li>
        ))}
        {project.scenarios.length === 0 && <li className="muted">No scenarios.</li>}
      </ul>
    </section>
  );
}
