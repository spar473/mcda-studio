import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { StarterMaterialization, StarterTemplate } from "../api/types";
import { download } from "./CalculationWorkspaceView";
import { saveDownload } from "./results/downloads";

export function StarterGallery({ title, description, decisionMaker, onOpen, focusId }: {
  title: string; description: string; decisionMaker: string; onOpen: (id: string) => void;
  /** A starter chosen on the start page: scrolled into view and highlighted. */
  focusId?: string;
}) {
  const [templates, setTemplates] = useState<StarterTemplate[]>([]);
  const [optional, setOptional] = useState<Record<string, string[]>>({});
  const [materials, setMaterials] = useState<StarterMaterialization | null>(null);
  const [exported, setExported] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const sequence = useRef(0);
  useEffect(() => {
    let alive = true;
    void api.starterTemplates().then(value => { if (alive) setTemplates(value); }).catch((error: unknown) => { if (alive) setError(String(error)); });
    return () => { alive = false; };
  }, []);
  const focused = useRef<HTMLElement>(null);
  useEffect(() => { focused.current?.scrollIntoView({ block: "nearest" }); }, [templates]);
  async function prepare(template: StarterTemplate, mode: "fresh" | "worked_example") {
    const current = ++sequence.current;
    setBusy(true); setError(null); setMaterials(null); setExported(false);
    try {
      const value = await api.instantiateStarter({ template_id: template.id, mode, optional_artifact_ids: optional[template.id] ?? [], ...(mode === "fresh" ? { title, description, decision_maker: decisionMaker } : { title: "", description: "", decision_maker: "" }) });
      if (current === sequence.current) setMaterials(value);
    } catch (error) { if (current === sequence.current) setError(String(error)); }
    finally { if (current === sequence.current) setBusy(false); }
  }
  async function open() {
    if (!materials) return;
    setBusy(true); setError(null);
    try {
      const projects = await api.listProjects();
      const existing = projects.projects.find(item => item.id === materials.project.id);
      if (existing) {
        const saved = await api.getProject(existing.id);
        if (saved.fingerprint !== materials.receipt.project_fingerprint) throw Error("An edited project already uses this worked-example ID. Keep that project or remove it explicitly before opening this intact example.");
      } else await api.importProject(materials.project);
      onOpen(materials.project.id);
    } catch (error) { setError(String(error)); setBusy(false); }
  }
  return <section aria-label="Starter gallery">
    <h3>Starter gallery</h3>
    <p>Illustrative data. Create my project keeps structural IDs and example values, clears human acceptances and saved runs, and records lineage. Open worked example retains the original invented reviews and fingerprint.</p>
    <div className="starter-grid">{templates.map(template => <article className={`panel${template.id === focusId ? " focused" : ""}`} key={template.id}
      ref={template.id === focusId ? focused : undefined} aria-label={`${template.title} starter`}>
      <h4>{template.title}</h4><p>{template.description}</p><strong>Illustrative data</strong>
      <ul>{template.tasks.map(task => <li key={task}>{task}</li>)}</ul>
      <p>Version {template.version}; {template.artifacts.length} local materials. Manifest digest: <code className="digest">{template.digest}</code></p>
      {template.artifacts.filter(artifact => artifact.optional).map(artifact => <label key={artifact.id}><input type="checkbox" checked={(optional[template.id] ?? []).includes(artifact.id)} disabled={busy} onChange={event => setOptional(previous => ({ ...previous, [template.id]: event.target.checked ? [...(previous[template.id] ?? []), artifact.id] : (previous[template.id] ?? []).filter(id => id !== artifact.id) }))}/>{artifact.label} (optional, unattached, off by default)</label>)}
      <button type="button" disabled={busy} onClick={() => void prepare(template, "fresh")}>Create my project — {template.title}</button>{" "}
      <button type="button" disabled={busy} onClick={() => void prepare(template, "worked_example")}>Open worked example — {template.title}</button>
    </article>)}</div>
    <label>Reopen starter materials and lineage<input type="file" accept=".json" disabled={busy} onChange={event => {
      const file = event.target.files?.[0]; const current = ++sequence.current;
      setMaterials(null); setError(null); setExported(false);
      if (!file) return;
      if (file.size > 8_000_000) { setError("Starter materials exceed the 8 MB limit."); return; }
      setBusy(true);
      void file.text().then(text => api.verifyStarter(JSON.parse(text))).then(value => { if (current === sequence.current) setMaterials(value); }).catch((error: unknown) => { if (current === sequence.current) setError(String(error)); }).finally(() => { if (current === sequence.current) setBusy(false); });
    }}/></label>
    {busy && <p role="status">Preparing local materials…</p>}
    {error && <p role="alert">{error}</p>}
    {materials && <section aria-label="Starter lineage">
      <h4>{materials.project.title}: {materials.receipt.request.mode === "fresh" ? "Fresh unreviewed project" : "Intact worked example"}</h4>
      <p>{materials.receipt.request.mode === "fresh" ? "Illustrative inputs require your review. No carried acceptance applies to your decision." : "Invented reviews demonstrate the worked example only."}</p>
      <p>Project fingerprint: <code className="digest">{materials.receipt.project_fingerprint}</code></p>
      <p>Cleared fields: {materials.receipt.cleared_fields.length}. Omitted materials: {materials.receipt.omitted_artifact_ids.join(", ") || "none"}.</p>
      <details><summary>Exact lineage receipt and reset fields</summary><pre>{JSON.stringify(materials.receipt, null, 2)}</pre></details>
      <p>Keep these files before opening the project. Sidecars are opened explicitly in Evidence or Calculated measurements.</p>
      <button type="button" onClick={() => { download(materials, "starter-materials.json"); setExported(true); }}>Download materials and lineage</button>{" "}
      <button type="button" disabled={busy} onClick={() => {
        setBusy(true); setError(null);
        void api.archiveStarter(materials).then(blob => { saveDownload(blob, "starter-materials.zip"); setExported(true); }).catch((error: unknown) => setError(String(error))).finally(() => setBusy(false));
      }}>Download all files as ZIP</button>{" "}
      <button type="button" onClick={() => download(materials.receipt, "starter-lineage.json")}>Download lineage receipt</button>
      <ul>{Object.entries(materials.artifacts).map(([id, item]) => <li key={id}>{item.label} ({item.kind}) <button type="button" onClick={() => download(item.value, `${id}.json`)}>Download {item.label}</button></li>)}</ul>
      <button type="button" disabled={busy || !exported} onClick={() => void open()}>Save and open prepared project</button>
    </section>}
  </section>;
}
