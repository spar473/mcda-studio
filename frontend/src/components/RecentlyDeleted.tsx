import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { TrashEntry } from "../api/types";
import { formatDateTime } from "./ui";

export function RecentlyDeleted({ reloadKey, onRestored }: { reloadKey: number; onRestored: () => void }) {
  const [entries, setEntries] = useState<TrashEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let alive = true;
    api.listTrash().then(items => { if (alive) setEntries(items); })
      .catch((e: unknown) => { if (alive) setError(e instanceof Error ? e.message : String(e)); });
    return () => { alive = false; };
  }, [reloadKey, retry]);

  async function restore(entry: TrashEntry, asCopy: boolean) {
    setBusy(entry.entry); setError(null); setNotice(null);
    try {
      const restored = await api.restoreProject(entry.entry, asCopy);
      setNotice(`Restored “${restored.project.title}”${asCopy ? " as a new copy" : ""}. The recovery entry is retained.`);
      onRestored();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null); setRetry(n => n + 1);
    }
  }
  return <section className="panel" aria-label="Recently deleted">
    <details>
      <summary>Recently deleted{entries ? ` (${String(entries.length)})` : ""}</summary>
      <p className="muted">Restore without overwriting active projects. Recovery entries remain here after restoration; there is no permanent-delete action.</p>
      {error && <p role="alert">{error} <button type="button" disabled={busy !== null} onClick={() => { setError(null); setRetry(n => n + 1); }}>Refresh deleted entries</button></p>}
      {notice && <p role="status">{notice}</p>}
      {entries === null && !error && <p role="status">Loading deleted entries…</p>}
      {entries?.length === 0 && <p>No deleted entries.</p>}
      {entries && entries.length > 0 && <div className="table-scroll"><table className="grid" aria-label="Deleted projects">
        <thead><tr><th>Project</th><th>Deleted</th><th>Status</th><th>Action</th></tr></thead>
        <tbody>{entries.map(entry => <tr key={entry.entry}>
          <td>{entry.title ?? entry.entry}<div className="muted small">{entry.entry}</div></td>
          <td>{entry.deleted_at ? formatDateTime(entry.deleted_at) : "Unknown"}</td>
          <td>{!entry.readable ? `Unreadable: ${entry.error ?? "Cannot interpret recovery data"}` : entry.conflict ? "Original ID is active. Restore as a copy." : "Ready to restore"}</td>
          <td>{entry.readable && <button type="button" disabled={busy !== null}
            aria-label={`${entry.conflict ? "Restore as copy" : "Restore"} ${entry.title ?? entry.entry}`}
            onClick={() => void restore(entry, entry.conflict)}>
            {busy === entry.entry ? "Restoring…" : entry.conflict ? "Restore as copy" : "Restore"}
          </button>}</td>
        </tr>)}</tbody>
      </table></div>}
    </details>
  </section>;
}
