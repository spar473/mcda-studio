// The editing session: the saved snapshot, the working copy, and an undo/redo history of whole
// project snapshots. "Unsaved changes" means the working copy's fingerprint (computed by the
// server from the canonical project JSON) differs from the saved one, so undoing back to the
// saved state clears the indicator, and no hashing is duplicated in the browser.
import type { Project, ProjectDocument, ValidationReport } from "../api/types";

export interface Snapshot {
  project: Project;
  fingerprint: string;
  validation: ValidationReport;
}

export interface SessionState {
  saved: Snapshot;
  draft: Snapshot;
  past: Snapshot[];
  future: Snapshot[];
  updatedAt: string | null;
}

export type SessionAction =
  | { type: "edited"; doc: ProjectDocument }
  | { type: "undo" }
  | { type: "redo" }
  | { type: "saved"; doc: ProjectDocument };

export const HISTORY_LIMIT = 200;

export function snapshotOf(doc: ProjectDocument): Snapshot {
  return { project: doc.project, fingerprint: doc.fingerprint, validation: doc.validation };
}

export function initialSession(doc: ProjectDocument): SessionState {
  const snap = snapshotOf(doc);
  return { saved: snap, draft: snap, past: [], future: [], updatedAt: doc.updated_at ?? null };
}

export function isDirty(state: SessionState): boolean {
  return state.draft.fingerprint !== state.saved.fingerprint;
}

export function sessionReducer(state: SessionState, action: SessionAction): SessionState {
  switch (action.type) {
    case "edited": {
      if (action.doc.fingerprint === state.draft.fingerprint) return state; // a no-op edit
      return {
        ...state,
        draft: snapshotOf(action.doc),
        past: [...state.past, state.draft].slice(-HISTORY_LIMIT),
        future: [],
      };
    }
    case "undo": {
      const previous = state.past[state.past.length - 1];
      if (!previous) return state;
      return {
        ...state,
        draft: previous,
        past: state.past.slice(0, -1),
        future: [state.draft, ...state.future],
      };
    }
    case "redo": {
      const next = state.future[0];
      if (!next) return state;
      return {
        ...state,
        draft: next,
        past: [...state.past, state.draft],
        future: state.future.slice(1),
      };
    }
    case "saved": {
      const snap = snapshotOf(action.doc);
      return { ...state, saved: snap, draft: snap, updatedAt: action.doc.updated_at ?? null };
    }
  }
}
