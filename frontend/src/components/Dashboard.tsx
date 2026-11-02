import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type {
  ExampleInfo,
  ProjectCopyReceipt,
  ProjectList,
  ProjectSummary,
  StarterTemplate,
  TemplateInfo,
} from "../api/types";
import { saveDownload } from "./results/downloads";
import { Banner, ConfirmDialog, Field, formatDateTime, Modal } from "./ui";

import { StarterGallery } from "./StarterGallery";

import { RecentlyDeleted } from "./RecentlyDeleted";

interface Props {
  onOpen: (id: string) => void;
}

type Dialog =
  | { kind: "none" }
  | { kind: "new"; starter?: string }
  | { kind: "examples" }
  | { kind: "delete"; project: ProjectSummary }
  | { kind: "import-conflict"; raw: unknown; id: string; title: string }
  | { kind: "example-conflict"; example: ExampleInfo };

export function Dashboard({ onOpen }: Props) {
  const [list, setList] = useState<ProjectList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<ProjectCopyReceipt | null>(null);
  const [dialog, setDialog] = useState<Dialog>({ kind: "none" });
  const fileInput = useRef<HTMLInputElement>(null);

  const [reloadKey, setReloadKey] = useState(0);
  const refresh = useCallback(() => {
    setReloadKey((k) => k + 1);
    return Promise.resolve();
  }, []);

  useEffect(() => {
    let alive = true;
    api
      .listProjects()
      .then((l) => {
        if (alive) {
          setList(l);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof ApiError ? e.message : String(e));
      });
    return () => {
      alive = false;
    };
  }, [reloadKey]);

  const [starters, setStarters] = useState<StarterTemplate[]>([]);
  useEffect(() => {
    let alive = true;
    api.starterTemplates().then((value) => { if (alive) setStarters(value); }).catch(() => undefined);
    return () => { alive = false; };
  }, []);

  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : String(e));

  async function duplicate(p: ProjectSummary) {
    try {
      const doc = await api.duplicateProject(p.id);
      setMessage(`Created “${doc.project.title}”.`);
      await refresh();
    } catch (e) {
      fail(e);
    }
  }

  async function remove(p: ProjectSummary) {
    setDialog({ kind: "none" });
    try {
      await api.deleteProject(p.id);
      setMessage(`Moved “${p.title}” to the trash folder inside the project directory.`);
      await refresh();
    } catch (e) {
      fail(e);
    }
  }

  async function importFile(file: File) {
    let raw: unknown;
    try {
      raw = JSON.parse(await file.text());
    } catch {
      setError(`${file.name} is not valid JSON.`);
      return;
    }
    try {
      const doc = await api.importProject(raw, "error");
      setMessage(`Imported “${doc.project.title}”.`);
      setReceipt(doc.copy_receipt);
      await refresh();
    } catch (e) {
      if (e instanceof ApiError && e.code === "PROJECT_EXISTS") {
        const o = raw as { id?: string; title?: string };
        setDialog({ kind: "import-conflict", raw, id: o.id ?? "", title: o.title ?? file.name });
      } else {
        fail(e);
      }
    }
  }

  async function importAgain(raw: unknown) {
    setDialog({ kind: "none" });
    try {
      const doc = await api.importProject(raw, "new_id");
      setMessage(`Imported as a separate copy: “${doc.project.title}”.`);
      setReceipt(doc.copy_receipt);
      await refresh();
    } catch (e) {
      fail(e);
    }
  }

  async function addExample(ex: ExampleInfo, onConflict: "error" | "new_id") {
    try {
      const doc = await api.importExample(ex.name, onConflict);
      setDialog({ kind: "none" });
      onOpen(doc.project.id);
    } catch (e) {
      if (e instanceof ApiError && e.code === "PROJECT_EXISTS") {
        setDialog({ kind: "example-conflict", example: ex });
      } else {
        setDialog({ kind: "none" });
        fail(e);
      }
    }
  }

  return (
    <main className="dashboard">
      <section className="hero" aria-label="Start a decision">
        <h1>Make a structured decision</h1>
        <p className="hero-lead">
          Compare options against criteria, see why one ranks above another, and keep the evidence and
          checks behind every number.
        </p>
        {starters.length > 0 && (
          <div className="starter-cards">
            {[...starters].sort((a, b) => starterRank(a.id) - starterRank(b.id)).map((t) => (
              <button
                key={t.id}
                type="button"
                className="starter-card"
                aria-label={`Start from ${t.title}`}
                onClick={() => setDialog({ kind: "new", starter: t.id })}
              >
                <StarterIcon id={t.id} />
                <span className="starter-title">{t.title}</span>
                <span className="starter-desc">{STARTER_TAGLINES[t.id] ?? t.description}</span>
              </button>
            ))}
          </div>
        )}
      </section>
      <header className="page-header">
        <div>
          <h2>Projects</h2>
          <p className="muted">Decision models stored as JSON files on this computer.</p>
        </div>
        <div className="toolbar">
          <button type="button" className="primary" onClick={() => setDialog({ kind: "new" })}>
            New project…
          </button>
          <button type="button" onClick={() => fileInput.current?.click()}>
            Import file…
          </button>
          <button type="button" onClick={() => setDialog({ kind: "examples" })}>
            Examples…
          </button>
          <input
            ref={fileInput}
            type="file"
            accept=".json,application/json"
            hidden
            aria-label="Project file to import"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) void importFile(f);
            }}
          />
        </div>
      </header>

      {error && (
        <Banner kind="error" onDismiss={() => setError(null)}>
          {error}
        </Banner>
      )}
      {message && (
        <Banner kind="info" onDismiss={() => setMessage(null)}>
          {message}
        </Banner>
      )}
      {receipt && (
        <section className="panel" aria-label="Copy receipt">
          <p>
            The copy was stored under the new project ID <code>{receipt.copy_project_id}</code>,
            so its fingerprint differs from the imported file. If that file came from an evidence
            compilation or calculation bundle, keep this receipt with the bundle: it records that
            only the project ID changed, and is required to verify the copy against the bundle.
          </p>
          <button
            type="button"
            onClick={() =>
              saveDownload(
                new Blob([JSON.stringify(receipt, null, 2) + "\n"], { type: "application/json" }),
                `copy-receipt-${receipt.copy_project_id}.json`,
              )
            }
          >
            Download copy receipt
          </button>
          <button type="button" onClick={() => setReceipt(null)}>
            Dismiss
          </button>
        </section>
      )}
      {list && list.unreadable.length > 0 && (
        <Banner kind="warning">
          {list.unreadable.length} file(s) in the project folder could not be read and are not
          listed:{" "}
          {list.unreadable.map((u) => (
            <span key={u.file}>
              <code>{u.file}</code> ({u.error}){" "}
            </span>
          ))}
        </Banner>
      )}

      {list === null && !error && <p className="muted">Loading…</p>}
      {list?.projects.length === 0 && (
        <div className="empty">
          <h2>No projects yet</h2>
          <p>Create a new decision model, or add one of the bundled examples.</p>
        </div>
      )}
      {list && list.projects.length > 0 && (
        <table className="grid projects">
          <thead>
            <tr>
              <th>Title</th>
              <th className="num">Alternatives</th>
              <th className="num">Criteria</th>
              <th>Status</th>
              <th>Modified</th>
              <th>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {list.projects.map((p) => (
              <tr key={p.id}>
                <td>
                  <a
                    href={`#/p/${encodeURIComponent(p.id)}`}
                    className="project-link"
                    onClick={(e) => {
                      e.preventDefault();
                      onOpen(p.id);
                    }}
                  >
                    {p.title}
                  </a>
                  {p.description && <div className="muted small clip">{p.description}</div>}
                </td>
                <td className="num">{p.alternatives}</td>
                <td className="num">
                  {p.leaves} <span className="muted">of {p.criteria} nodes</span>
                </td>
                <td>
                  {p.validation.ok ? (
                    <span className="pill ok">
                      Complete{p.validation.warnings ? ` · ${String(p.validation.warnings)} warning(s)` : ""}
                    </span>
                  ) : (
                    <span className="pill bad">{p.validation.errors} to fix</span>
                  )}
                </td>
                <td>{formatDateTime(p.updated_at)}</td>
                <td className="actions">
                  <button type="button" onClick={() => onOpen(p.id)} aria-label={`Open ${p.title}`}>
                    Open
                  </button>
                  <button type="button" onClick={() => void duplicate(p)} aria-label={`Duplicate ${p.title}`}>
                    Duplicate
                  </button>
                  <a
                    className="button"
                    href={api.downloadUrl(p.id)}
                    download={`${p.id}.json`}
                    aria-label={`Download ${p.title}`}
                  >
                    Download
                  </a>
                  <button
                    type="button"
                    onClick={() => setDialog({ kind: "delete", project: p })}
                    aria-label={`Delete ${p.title}`}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <RecentlyDeleted reloadKey={reloadKey} onRestored={() => { void refresh(); }} />

      {dialog.kind === "new" && (
        <NewProjectDialog
          starter={dialog.starter}
          onClose={() => setDialog({ kind: "none" })}
          onCreated={(id) => {
            setDialog({ kind: "none" });
            onOpen(id);
          }}
        />
      )}
      {dialog.kind === "examples" && (
        <ExamplesDialog onClose={() => setDialog({ kind: "none" })} onAdd={(ex) => void addExample(ex, "error")} />
      )}
      {dialog.kind === "delete" && (
        <ConfirmDialog
          title="Delete project"
          danger
          confirmLabel="Delete"
          message={
            <>
              Delete <strong>{dialog.project.title}</strong>? The file is moved to a{" "}
              <code>.trash</code> folder inside the project directory. Restore it from Recently deleted.
            </>
          }
          onCancel={() => setDialog({ kind: "none" })}
          onConfirm={() => void remove(dialog.project)}
        />
      )}
      {dialog.kind === "import-conflict" && (
        <ConfirmDialog
          title="A project with this id already exists"
          confirmLabel="Import as a separate copy"
          message={
            <>
              <strong>{dialog.title}</strong> has the same id (<code>{dialog.id}</code>) as a stored
              project. The stored project is never overwritten by an import.
            </>
          }
          onCancel={() => setDialog({ kind: "none" })}
          onConfirm={() => void importAgain(dialog.raw)}
        />
      )}
      {dialog.kind === "example-conflict" && (
        <ConfirmDialog
          title="Example already added"
          confirmLabel="Add another copy"
          cancelLabel="Close"
          message={
            <>
              <strong>{dialog.example.title}</strong> is already in your projects.
            </>
          }
          extra={
            <button type="button" onClick={() => onOpen(dialog.example.project_id)}>
              Open the existing one
            </button>
          }
          onCancel={() => setDialog({ kind: "none" })}
          onConfirm={() => void addExample(dialog.example, "new_id")}
        />
      )}
    </main>
  );
}

// Blank first, then the venture example; any other starter keeps the gallery's order after them.
const STARTER_ORDER = ["blank", "venture_screening", "supplier_selection", "infrastructure_procurement"];

const starterRank = (id: string) => {
  const index = STARTER_ORDER.indexOf(id);
  return index < 0 ? STARTER_ORDER.length : index;
};

const STARTER_TAGLINES: Record<string, string> = {
  blank: "Start from an empty model",
  supplier_selection: "Cost, performance and risk",
  infrastructure_procurement: "Lifecycle cost, service and consent",
  venture_screening: "Evidence review, market models and a disclosed proxy",
};

/** Simple line icons for the starter cards; decorative only. */
function StarterIcon({ id }: { id: string }) {
  const paths: Record<string, string> = {
    blank: "M12 5v14M5 12h14",
    supplier_selection: "M3 7l9-4 9 4-9 4-9-4zm0 0v10l9 4 9-4V7M12 11v10",
    infrastructure_procurement: "M2 18h20M4 18V10M20 18V10M2 10c4-5 16-5 20 0M9 18v-5M15 18v-5",
    venture_screening: "M3 17l6-6 4 4 8-8M15 7h6v6",
  };
  return (
    <svg className="starter-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d={paths[id] ?? paths.blank} />
    </svg>
  );
}

function NewProjectDialog(props: { onClose: () => void; onCreated: (id: string) => void; starter?: string }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [decisionMaker, setDecisionMaker] = useState("");
  const [template, setTemplate] = useState("blank");
  const [templates, setTemplates] = useState<TemplateInfo[]>([{ name: "blank" }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .templates()
      .then(setTemplates)
      .catch(() => undefined);
  }, []);

  async function create() {
    if (title.trim() === "") {
      setError("Give the project a title.");
      return;
    }
    setBusy(true);
    try {
      const doc = await api.createProject({
        title: title.trim(),
        description,
        decision_maker: decisionMaker,
        method: "mavt",
        template,
      });
      props.onCreated(doc.project.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <Modal
      title="New project"
      onClose={props.onClose}
      footer={
        <>
          <button type="button" onClick={props.onClose}>
            Cancel
          </button>
          <button type="button" className="primary" disabled={busy} onClick={() => void create()}>
            Create
          </button>
        </>
      }
    >
      <h3>Create a blank or structure-only project</h3>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void create();
        }}
      >
        <Field label="Title" htmlFor="np-title">
          <input id="np-title" value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label="Description" htmlFor="np-desc">
          <textarea id="np-desc" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <Field label="Decision maker" htmlFor="np-dm">
          <input id="np-dm" value={decisionMaker} onChange={(e) => setDecisionMaker(e.target.value)} />
        </Field>
        <Field
          label="Start from"
          htmlFor="np-template"
          hint="A template only supplies a criteria structure; alternatives, measurements and weights are always yours."
        >
          <select id="np-template" value={template} onChange={(e) => setTemplate(e.target.value)}>
            {templates.map((t) => (
              <option key={t.name} value={t.name}>
                {t.name === "blank" ? "Blank project" : `Template: ${t.name}`}
              </option>
            ))}
          </select>
        </Field>
        {error && <Banner kind="error">{error}</Banner>}
        <button type="submit" hidden />
      </form>
      <StarterGallery title={title} description={description} decisionMaker={decisionMaker} onOpen={props.onCreated}
        focusId={props.starter === "blank" ? undefined : props.starter}/>
    </Modal>
  );
}

// Reader-facing summaries; the example files keep their original descriptions, which exports pin.
const EXAMPLE_SUMMARIES: Record<string, string> = {
  infrastructure_procurement:
    "Four objectives with a three-level branch, a zero-rated criterion and two disagreeing preference profiles.",
  supplier_selection: "Cost, performance and risk of five suppliers.",
};

function ExamplesDialog(props: { onClose: () => void; onAdd: (e: ExampleInfo) => void }) {
  const [examples, setExamples] = useState<ExampleInfo[] | null>(null);
  useEffect(() => {
    api
      .examples()
      .then(setExamples)
      .catch(() => setExamples([]));
  }, []);
  return (
    <Modal
      title="Bundled examples"
      wide
      onClose={props.onClose}
      footer={
        <button type="button" onClick={props.onClose}>
          Close
        </button>
      }
    >
      {examples === null && <p className="muted">Loading…</p>}
      {examples?.length === 0 && (
        <p className="muted">
          No examples were found next to this installation (they live in the repository’s{" "}
          <code>examples</code> folder).
        </p>
      )}
      <ul className="example-list">
        {examples?.map((ex) => (
          <li key={ex.name}>
            <div>
              <strong>{ex.title}</strong>
              <div className="muted small">
                {ex.alternatives} alternatives · {ex.criteria} criteria nodes
              </div>
              {(EXAMPLE_SUMMARIES[ex.name] ?? ex.description) && (
                <div className="small">{EXAMPLE_SUMMARIES[ex.name] ?? ex.description}</div>
              )}
            </div>
            <button type="button" className="primary" onClick={() => props.onAdd(ex)} aria-label={`Add ${ex.title}`}>
              Add to my projects
            </button>
          </li>
        ))}
      </ul>
    </Modal>
  );
}
