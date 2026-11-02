import { useState } from "react";
import type { Operation, Project } from "../api/types";
import { ConfirmDialog, CommitText } from "./ui";

interface Props {
  project: Project;
  busy: boolean;
  apply: (ops: Operation[]) => Promise<boolean>;
  /** Move focus into one alternative's name field; a new key repeats the request. */
  focusAlternative?: { id: string; key: number } | null;
}

export function AlternativesPanel({ project, busy, apply, focusAlternative }: Props) {
  const [name, setName] = useState("");
  const [removeId, setRemoveId] = useState<string | null>(null);
  const removing = project.alternatives.find((a) => a.id === removeId);
  const removingCount = project.performances.filter((p) => p.alternative_id === removeId).length;

  async function add() {
    const trimmed = name.trim();
    if (!trimmed) return;
    if (await apply([{ op: "add_alternative", name: trimmed }])) setName("");
  }

  return (
    <section className="panel" aria-label="Alternatives">
      <h2>Alternatives</h2>
      <p className="muted">The options being compared. Their measurements are entered on the Measurements tab.</p>
      <form
        className="inline-form"
        onSubmit={(e) => {
          e.preventDefault();
          void add();
        }}
      >
        <input
          aria-label="New alternative name"
          placeholder="Name of a new alternative"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button type="submit" className="primary" disabled={busy || name.trim() === ""}>
          Add alternative
        </button>
      </form>

      {project.alternatives.length === 0 ? (
        <div className="empty small-empty">
          <p>No alternatives yet.</p>
        </div>
      ) : (
        <table className="grid" aria-label="Alternatives">
          <thead>
            <tr>
              <th className="num">#</th>
              <th>Name</th>
              <th>Identifier</th>
              <th className="num">Measurements</th>
              <th>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {project.alternatives.map((a, i) => (
              <tr key={a.id}>
                <td className="num">{i + 1}</td>
                <td>
                  <CommitText
                    label={`Name of alternative ${a.name}`}
                    focusKey={focusAlternative?.id === a.id ? focusAlternative.key : 0}
                    value={a.name}
                    required
                    onCommit={(v) => void apply([{ op: "rename_alternative", alternative_id: a.id, name: v }])}
                  />
                </td>
                <td>
                  <code>{a.id}</code>
                </td>
                <td className="num">{project.performances.filter((p) => p.alternative_id === a.id).length}</td>
                <td className="actions">
                  <button type="button" className="danger-text" disabled={busy} aria-label={`Remove ${a.name}`} onClick={() => setRemoveId(a.id)}>
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {removing && (
        <ConfirmDialog
          title="Remove alternative"
          danger
          confirmLabel="Remove"
          message={
            <>
              Remove <strong>{removing.name}</strong>
              {removingCount > 0 ? ` and its ${String(removingCount)} entered measurement(s)` : ""}? You
              can undo this until you close the project.
            </>
          }
          onCancel={() => setRemoveId(null)}
          onConfirm={() => {
            setRemoveId(null);
            void apply([{ op: "remove_alternative", alternative_id: removing.id }]);
          }}
        />
      )}
    </section>
  );
}
