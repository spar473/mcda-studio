import { useState } from "react";
import type { Operation, Project } from "../api/types";
import type { AnalysisContext } from "../state/analysisContext";
import { Banner, Modal } from "./ui";

type Mode = "create" | "duplicate" | "rename" | "delete" | "default" | "automatic";
interface Props {
  project: Project; context: AnalysisContext; busy: boolean;
  manage: (operation: Operation) => Promise<boolean>;
  onSelect: (profileId: string | null) => void;
}

export function ProfileManager({ project, context, busy, manage, onSelect }: Props) {
  const profile = project.weight_profiles.find((p) => p.id === context.resolvedProfileId);
  const [dialog, setDialog] = useState<{ mode: Mode; profileId: string | null; revision: string } | null>(null);
  const [name, setName] = useState("");
  const [replacement, setReplacement] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  function open(mode: Mode) {
    setName(mode === "duplicate" ? `${profile?.name ?? "Profile"} (copy)` : mode === "rename" ? profile?.name ?? "" : "");
    setReplacement(""); setError(null);
    setDialog({ mode, profileId: profile?.id ?? null, revision: context.fingerprint });
  }
  const remaining = project.weight_profiles.filter((p) => p.id !== dialog?.profileId);
  const stale = !!dialog && dialog.revision !== context.fingerprint;
  const needsName = dialog && ["create", "duplicate", "rename"].includes(dialog.mode);
  const disabled = busy || submitting || stale || !!needsName && name.trim() === "" ||
    dialog?.mode === "delete" && !remaining.some((p) => p.id === replacement);
  async function submit() {
    if (!dialog || disabled) return;
    let op: Operation;
    switch (dialog.mode) {
      case "create": op = { op: "create_weight_profile", name: name.trim() }; break;
      case "duplicate": if (!dialog.profileId) return; op = { op: "duplicate_weight_profile", profile_id: dialog.profileId, name: name.trim() }; break;
      case "rename": if (!dialog.profileId) return; op = { op: "rename_weight_profile", profile_id: dialog.profileId, name: name.trim() }; break;
      case "delete": if (!dialog.profileId) return; op = { op: "remove_weight_profile", profile_id: dialog.profileId, replacement_profile_id: replacement }; break;
      case "default": if (!dialog.profileId) return; op = { op: "set_default_weight_profile", profile_id: dialog.profileId }; break;
      case "automatic": op = { op: "set_default_weight_profile", profile_id: null }; break;
    }
    setSubmitting(true);
    const ok = await manage(op); setSubmitting(false);
    if (ok) setDialog(null);
    else setError("The profile change was refused. Your project was retained; check the application message, or cancel and reopen this dialog.");
  }
  const labels: Record<Mode,string> = { create: "Create profile", duplicate: "Duplicate profile", rename: "Rename profile", delete: "Delete profile", default: "Change saved profile default", automatic: "Use automatic saved default" };
  const saved = project.weight_profiles.find((p) => p.id === project.analysis.weight_profile_id);
  return <section className="profile-manager" aria-label="Preference profiles">
    <h3>Preference profiles</h3>
    <div className="profile-toolbar">
      <label>Profile to edit<select aria-label="Profile to edit" value={context.profileId ?? ""} disabled={busy}
        onChange={(e) => onSelect(e.target.value || null)}>
        <option value="">Automatic (scenario, then first profile)</option>
        {project.weight_profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select></label>
      <button type="button" disabled={busy} onClick={() => open("create")}>Create profile</button>
      <button type="button" disabled={busy || !profile} onClick={() => open("duplicate")}>Duplicate profile</button>
      <button type="button" disabled={busy || !profile} onClick={() => open("rename")}>Rename profile</button>
      <button type="button" disabled={busy || !profile || project.weight_profiles.length <= 1} onClick={() => open("delete")}>Delete profile</button>
    </div>
    <p className="muted small">Viewing: {profile ? <>{profile.name} · stable ID <code>{profile.id}</code></>
      : context.resolvedProfileId ? <>unresolved reference <code>{context.resolvedProfileId}</code>, which no longer exists; nothing was substituted for it</>
      : "No profile"}. Switching profiles is session-only and creates no edit or undo entry.</p>
    <p className="muted small">Saved profile default: {project.analysis.weight_profile_id ? saved?.name ?? project.analysis.weight_profile_id : "Automatic (saved scenario, then first profile)"}.</p>
    <div className="row">
      <button type="button" disabled={busy || !profile || project.analysis.weight_profile_id === profile.id} onClick={() => open("default")}>Use viewed profile as saved default</button>
      <button type="button" disabled={busy || project.analysis.weight_profile_id === null} onClick={() => open("automatic")}>Use automatic saved default</button>
    </div>
    {project.weight_profiles.length === 1 && <p className="muted small">Keep at least one profile. Create or duplicate one before deleting.</p>}
    {dialog && <Modal title={labels[dialog.mode]} onClose={() => { if(!submitting)setDialog(null); }} footer={<>
      <button type="button" disabled={submitting} onClick={() => setDialog(null)}>Cancel</button>
      <button type="button" className={dialog.mode === "delete" ? "danger" : "primary"} disabled={disabled} onClick={() => void submit()}>{dialog.mode === "delete" ? "Delete and replace references" : "Confirm profile change"}</button>
    </>}>
      {stale && <Banner kind="error">The project revision changed. Cancel and reopen before changing profiles.</Banner>}
      {error && <Banner kind="error">{error}</Banner>}
      {needsName && <label>Profile name<input aria-label="Profile name" value={name} disabled={submitting} onChange={(e) => setName(e.target.value)}/></label>}
      {dialog.mode === "create" && <p>A new profile starts with missing ratings. No swing judgements will be invented.</p>}
      {dialog.mode === "duplicate" && <p>Copy the viewed profile’s raw ratings into an independent profile. Later edits will not change the source.</p>}
      {dialog.mode === "rename" && <p>Only the display name changes. Stable IDs, ratings and references remain intact.</p>}
      {dialog.mode === "delete" && <>
        <p>Choose a replacement explicitly. All scenarios and the saved analysis that use the deleted profile, including automatic first-profile references, will be updated in the same atomic edit. Other profiles and scenario functions remain intact. Undo restores the whole change.</p>
        <label>Replacement profile<select aria-label="Replacement profile" value={replacement} disabled={submitting} onChange={(e) => setReplacement(e.target.value)}>
          <option value="">Choose a replacement…</option>{remaining.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <p>The view will select that replacement. This does not otherwise change saved defaults.</p>
      </>}
      {(dialog.mode === "default" || dialog.mode === "automatic") && <p>This explicitly changes only the saved analysis weight-profile setting to {dialog.mode === "automatic" ? "automatic resolution" : profile?.name}. The saved scenario, method and parameters are preserved. Save the project to persist it.</p>}
    </Modal>}
  </section>;
}
