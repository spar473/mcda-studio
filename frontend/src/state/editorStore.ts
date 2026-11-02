// The editor's working state as a plain (non-React) store, so its behaviour - serial edits,
// undo/redo, dirty tracking, conflict handling - is testable without a DOM.
import { useEffect, useState, useSyncExternalStore } from "react";
import { api as defaultApi, ApiError } from "../api/client";
import type { Operation } from "../api/types";
import { swingReviewIdentity } from "./swingReview";
import { BASE_SELECTION, canonical, reconcileSelection, type AnalysisSelection } from "./analysisContext";
import { initialSession, isDirty, sessionReducer, type SessionState } from "../model/session";

export interface Notice {
  kind: "error" | "info";
  message: string;
  code?: string;
}

export interface EditorState {
  analysis: AnalysisSelection;
  anchorReview: boolean;
  swingReviewKey: string | null;
  acknowledgedSwingReviewKey: string | null;
  status: "loading" | "ready" | "error";
  loadError: ApiError | null;
  session: SessionState | null;
  /** Edits/undo/redo waiting for or awaiting the server. */
  pending: number;
  saving: boolean;
  notice: Notice | null;
  /** The stored project changed behind our back (HTTP 412); the user must choose. */
  conflict: boolean;
}

type Api = Pick<typeof defaultApi, "getProject" | "edit" | "saveProject" | "importProject">;

const INITIAL: EditorState = {
  analysis: BASE_SELECTION,
  anchorReview: false,
  swingReviewKey: null,
  acknowledgedSwingReviewKey: null,
  status: "loading",
  loadError: null,
  session: null,
  pending: 0,
  saving: false,
  notice: null,
  conflict: false,
};

export type SaveOutcome = "saved" | "conflict" | "failed" | "nothing-to-save";

export class EditorStore {
  private state: EditorState = INITIAL;
  private readonly listeners = new Set<() => void>();
  private chain: Promise<unknown> = Promise.resolve();
  private loadEpoch = 0;

  constructor(
    readonly projectId: string,
    private readonly api: Api = defaultApi,
  ) {}

  // ---- store plumbing (useSyncExternalStore) -------------------------------------------------
  getState = (): EditorState => this.state;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private set(patch: Partial<EditorState>): void {
    const next = { ...this.state, ...patch };
    if (next.session) {
      next.analysis = reconcileSelection(next.session.draft.project, next.analysis);
      const localAlternatives = next.session.draft.validation.issues.some((i) => i.code === "LOCAL_ANCHORS")
        ? next.session.draft.project.alternatives.map((a) => a.id).sort() : null;
      const key = swingReviewIdentity(next.session.draft.project, next.analysis) + canonical(localAlternatives);
      if (this.state.swingReviewKey !== null && key !== this.state.swingReviewKey) {
        next.anchorReview = true;
        next.acknowledgedSwingReviewKey = null;
      }
      next.swingReviewKey = key;
    }
    this.state = next;
    this.listeners.forEach((l) => l());
  }

  private reduce(action: Parameters<typeof sessionReducer>[1]): void {
    if (this.state.session) this.set({ session: sessionReducer(this.state.session, action) });
  }

  /** Run `job` after every previously queued job, whatever their outcome. */
  private enqueue<T>(job: () => Promise<T>, cancelled: T): Promise<T> {
    const epoch = this.loadEpoch;
    const original = job;
    job = () => epoch === this.loadEpoch ? original() : Promise.resolve(cancelled);
    this.set({ pending: this.state.pending + 1 });
    const run = this.chain.then(job);
    this.chain = run.then(
      () => undefined,
      () => undefined,
    );
    return run.finally(() => {
      if (epoch === this.loadEpoch) this.set({ pending: this.state.pending - 1 });
    });
  }

  // ---- commands ------------------------------------------------------------------------------
  async load(): Promise<void> {
    const epoch = ++this.loadEpoch;
    this.set({ ...INITIAL });
    try {
      const doc = await this.api.getProject(this.projectId);
      if (epoch !== this.loadEpoch) return;
      this.set({ status: "ready", session: initialSession(doc), loadError: null });
    } catch (e) {
      if (epoch !== this.loadEpoch) return;
      this.set({ status: "error", loadError: toApiError(e) });
    }
  }

  /** Apply operations through the server; resolves true if they were applied. */
  apply(operations: Operation[]): Promise<boolean> {
    return this.enqueue(async () => {
      const session = this.state.session;
      if (!session) return false;
      try {
        const doc = await this.api.edit(session.draft.project, operations);
        if (this.state.session !== session) return false;
        this.reduce({ type: "edited", doc });
        this.set({ notice: null });
        return true;
      } catch (e) {
        if (this.state.session !== session) return false;
        const err = toApiError(e);
        this.set({ notice: { kind: "error", message: err.message, code: err.code } });
        return false;
      }
    }, false);
  }

  undo(): Promise<void> {
    return this.enqueue(() => {
      this.reduce({ type: "undo" });
      return Promise.resolve();
    }, undefined);
  }

  redo(): Promise<void> {
    return this.enqueue(() => {
      this.reduce({ type: "redo" });
      return Promise.resolve();
    }, undefined);
  }

  save(): Promise<SaveOutcome> {
    return this.enqueue<SaveOutcome>(async () => {
      const session = this.state.session;
      if (!session) return "failed";
      if (!isDirty(session)) return "nothing-to-save";
      this.set({ saving: true, notice: null });
      try {
        const doc = await this.api.saveProject(session.draft.project, session.saved.fingerprint);
        if (this.state.session !== session) return "failed";
        this.reduce({ type: "saved", doc });
        this.set({ saving: false });
        return "saved";
      } catch (e) {
        if (this.state.session !== session) return "failed";
        const err = toApiError(e);
        if (err.code === "STALE_REVISION") {
          this.set({ saving: false, conflict: true });
          return "conflict";
        }
        this.set({
          saving: false,
          notice: { kind: "error", message: `Not saved: ${err.message}`, code: err.code },
        });
        return "failed";
      }
    }, "failed");
  }

  /** Keep the working copy as a separate new project (fresh id); returns its id. */
  async saveCopy(): Promise<string | null> {
    const session = this.state.session;
    if (!session) return null;
    try {
      const doc = await this.api.importProject(session.draft.project, "new_id");
      return doc.project.id;
    } catch (e) {
      const err = toApiError(e);
      this.set({ notice: { kind: "error", message: `Copy not saved: ${err.message}`, code: err.code } });
      return null;
    }
  }

  /** Discard the working copy and re-read the stored project (used after a conflict). */
  async reload(): Promise<void> {
    await this.load();
  }

  selectAnalysis(patch: Partial<AnalysisSelection>): void {
    this.set({ analysis: { ...this.state.analysis, ...patch } });
  }

  acknowledgeAnchorReview(): void {
    this.set({ anchorReview: false, acknowledgedSwingReviewKey: this.state.swingReviewKey });
  }

  dismissNotice(): void {
    this.set({ notice: null });
  }

  dismissConflict(): void {
    this.set({ conflict: false });
  }
}

export function toApiError(e: unknown): ApiError {
  if (e instanceof ApiError) return e;
  return new ApiError(0, "UNEXPECTED", e instanceof Error ? e.message : String(e));
}

/** React binding: one store per project id, loaded on mount. */
export function useEditorStore(projectId: string): { store: EditorStore; state: EditorState } {
  const [store] = useState(() => new EditorStore(projectId));
  useEffect(() => {
    void store.load();
  }, [store]);
  const state = useSyncExternalStore(store.subscribe, store.getState);
  return { store, state };
}
