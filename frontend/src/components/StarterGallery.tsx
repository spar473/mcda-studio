import { useEffect, useRef, useState } from "react";
import { rememberWorkedEntry } from "../state/viewMode";
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
      if (current !== sequence.current) return;
      setMaterials(value);
      // A worked example can be prepared again, identically, at any time: it opens in one action.
      if (mode === "worked_example") await open(value);
    } catch (error) { if (current === sequence.current) setError(String(error)); }
    finally { if (current === sequence.current) setBusy(false); }
  }
  async function open(prepared: StarterMaterialization | null = materials) {
    if (!prepared) return;
    setBusy(true); setError(null);
    try {
      const projects = await api.listProjects();
      const existing = projects.projects.find(item => item.id === prepared.project.id);
      if (existing) {
        const saved = await api.getProject(existing.id);
        if (saved.fingerprint !== prepared.receipt.project_fingerprint) throw Error("An edited project already uses this worked-example ID. Keep that project or remove it explicitly before opening this intact example.");
      } else await api.importProject(prepared.project);
      rememberWorkedEntry(prepared);
      onOpen(prepared.project.id);
    } catch (error) { setError(String(error)); setBusy(false); }
  }
  return <section aria-label="Starter gallery">
    <h3>Starter gallery</h3>
    <p>Each starter is an example project. Open worked example opens it exactly as shipped, with its own reviews. Create my project gives you an unreviewed copy to make your own: it keeps the structure and example values, and clears reviews and saved runs.</p>
    <div className="starter-grid">{templates.map(template => <article className={`panel${template.id === focusId ? " focused" : ""}`} key={template.id}
      ref={template.id === focusId ? focused : undefined} aria-label={`${template.title} starter`}>
      <h4>{template.title}</h4><p>{template.description}</p>
      <ul>{template.tasks.map(task => <li key={task}>{task}</li>)}</ul>
      <details><summary>Details</summary><p>Version {template.version}; {template.artifacts.length} local materials. Manifest digest: <code className="digest">{template.digest}</code></p></details>
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
      <p>{materials.receipt.request.mode === "fresh" ? "The example values are yours to review; none of the example's reviews apply to your decision." : "The example's own reviews are kept to demonstrate it; they are not reviews of your decision."}</p>
      <button type="button" className="primary" disabled={busy} onClick={() => void open()}>Save and open prepared project</button>
      <details><summary>Details and optional downloads</summary>
        <p>Downloads are optional. {materials.receipt.request.mode === "fresh" ? "This copy's draft sidecars are made for its new project ID and are not stored in the library: keep them to continue those workflows later." : "These materials can be prepared again, identically, at any time."} Sidecars are opened explicitly in Evidence or Calculated measurements.</p>
        <p>Project fingerprint: <code className="digest">{materials.receipt.project_fingerprint}</code></p>
        <p>Cleared fields: {materials.receipt.cleared_fields.length}. Omitted materials: {materials.receipt.omitted_artifact_ids.join(", ") || "none"}.</p>
        <details><summary>Exact lineage receipt and reset fields</summary><pre>{JSON.stringify(materials.receipt, null, 2)}</pre></details>
        <button type="button" onClick={() => { download(materials, "starter-materials.json"); setExported(true); }}>Download materials and lineage</button>{" "}
        <button type="button" disabled={busy} onClick={() => {
          setBusy(true); setError(null);
          void api.archiveStarter(materials).then(blob => { saveDownload(blob, "starter-materials.zip"); setExported(true); }).catch((error: unknown) => setError(String(error))).finally(() => setBusy(false));
        }}>Download all files as ZIP</button>{" "}
        <button type="button" onClick={() => download(materials.receipt, "starter-lineage.json")}>Download lineage receipt</button>
        <ul>{Object.entries(materials.artifacts).map(([id, item]) => <li key={id}>{item.label} ({item.kind}) <button type="button" onClick={() => download(item.value, `${id}.json`)}>Download {item.label}</button></li>)}</ul>
        {exported && <p className="muted small" role="status">Materials downloaded.</p>}
      </details>
    </section>}
  </section>;
}
