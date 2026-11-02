import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../src/api/client";
import type { Operation, Project, ProjectDocument } from "../../src/api/types";
import { EditorStore } from "../../src/state/editorStore";
import { doc, projectWith } from "../fixtures";

/** A tiny fake server: the "project" is a title; fingerprint = `fp:<title>`; edits set the title. */
function fakeApi(initialTitle = "t0") {
  const state = { stored: initialTitle, storedFp: `fp:${initialTitle}`, log: [] as string[] };
  const mk = (title: string): ProjectDocument => doc(`fp:${title}`, projectWith([], { title }));
  const api = {
    getProject: vi.fn(() => Promise.resolve(mk(state.stored))),
    edit: vi.fn(async (project: Project, ops: Operation[]) => {
      state.log.push(`edit:${ops.map((o) => o.op).join(",")}`);
      await new Promise((r) => setTimeout(r, 5));
      const op = ops[0];
      if (op?.op === "update_project" && op.title === "boom") throw new ApiError(422, "EDIT_REFUSED", "refused");
      const title = op?.op === "update_project" && op.title ? op.title : project.title;
      return mk(title);
    }),
    saveProject: vi.fn((project: Project, ifMatch: string) => {
      if (ifMatch !== state.storedFp) return Promise.reject(new ApiError(412, "STALE_REVISION", "stale"));
      state.stored = project.title;
      state.storedFp = `fp:${project.title}`;
      return Promise.resolve(mk(project.title));
    }),
    importProject: vi.fn((project: unknown) => Promise.resolve({ ...doc("fp:copy", projectWith([], { id: "copy-id", title: (project as Project).title })), copy_receipt: null })),
  };
  return { api, state };
}

const rename = (title: string): Operation[] => [{ op: "update_project", title }];

async function ready(title = "t0") {
  const f = fakeApi(title);
  const store = new EditorStore("p1", f.api);
  await store.load();
  return { store, ...f };
}
const titleOf = (s: EditorStore) => s.getState().session?.draft.project.title;
const dirty = (s: EditorStore) => {
  const x = s.getState().session;
  return x ? x.draft.fingerprint !== x.saved.fingerprint : false;
};

describe("EditorStore", () => {
  it("loads, and reports a load failure instead of throwing", async () => {
    const { store } = await ready();
    expect(store.getState().status).toBe("ready");
    const failing = new EditorStore("nope", {
      ...fakeApi().api,
      getProject: () => Promise.reject(new ApiError(404, "PROJECT_NOT_FOUND", "no such project")),
    });
    await failing.load();
    expect(failing.getState().status).toBe("error");
    expect(failing.getState().loadError?.code).toBe("PROJECT_NOT_FOUND");
  });

  it("edits go through the server and mark the project dirty", async () => {
    const { store, api } = await ready();
    expect(await store.apply(rename("t1"))).toBe(true);
    expect(titleOf(store)).toBe("t1");
    expect(dirty(store)).toBe(true);
    expect(api.edit).toHaveBeenCalledTimes(1);
    expect(api.saveProject).not.toHaveBeenCalled();
  });

  it("edits fired together are applied one after another, each on the result of the previous", async () => {
    const { store, api } = await ready();
    const seen: string[] = [];
    api.edit.mockImplementation(async (project: Project, ops: Operation[]) => {
      seen.push(project.title);
      await new Promise((r) => setTimeout(r, 5));
      const op = ops[0];
      return doc(`fp:${op?.op === "update_project" ? String(op.title) : ""}`, projectWith([], { title: op?.op === "update_project" ? String(op.title) : "" }));
    });
    const results = await Promise.all([store.apply(rename("a")), store.apply(rename("b")), store.apply(rename("c"))]);
    expect(results).toEqual([true, true, true]);
    expect(seen).toEqual(["t0", "a", "b"]); // never two requests on the same base
    expect(titleOf(store)).toBe("c");
    expect(store.getState().pending).toBe(0);
  });

  it("a refused edit leaves the working copy alone, reports the reason, and does not block later edits", async () => {
    const { store } = await ready();
    expect(await store.apply(rename("boom"))).toBe(false);
    expect(titleOf(store)).toBe("t0");
    expect(store.getState().notice).toMatchObject({ kind: "error", code: "EDIT_REFUSED" });
    expect(await store.apply(rename("ok"))).toBe(true);
    expect(store.getState().notice).toBeNull();
  });

  it("undo and redo walk the history; undoing back to the saved state is clean", async () => {
    const { store, api } = await ready();
    await store.apply(rename("t1"));
    await store.apply(rename("t2"));
    await store.undo();
    expect(titleOf(store)).toBe("t1");
    await store.undo();
    expect(titleOf(store)).toBe("t0");
    expect(dirty(store)).toBe(false);
    await store.redo();
    expect(titleOf(store)).toBe("t1");
    expect(api.edit).toHaveBeenCalledTimes(2); // undo/redo never call the server
  });

  it("saving sends the draft with the saved revision, and clears the dirty state", async () => {
    const { store, api, state } = await ready();
    await store.apply(rename("t1"));
    expect(await store.save()).toBe("saved");
    expect(api.saveProject).toHaveBeenCalledWith(expect.objectContaining({ title: "t1" }), "fp:t0");
    expect(state.stored).toBe("t1");
    expect(dirty(store)).toBe(false);
    expect(store.getState().saving).toBe(false);
  });

  it("saving a clean project does nothing", async () => {
    const { store, api } = await ready();
    expect(await store.save()).toBe("nothing-to-save");
    expect(api.saveProject).not.toHaveBeenCalled();
  });

  it("a save queued behind an edit includes that edit", async () => {
    const { store, state } = await ready();
    const edit = store.apply(rename("t1"));
    const save = store.save();
    await Promise.all([edit, save]);
    expect(state.stored).toBe("t1");
  });

  it("a stale revision (HTTP 412) writes nothing and asks the user to choose", async () => {
    const { store, state } = await ready();
    await store.apply(rename("mine"));
    state.storedFp = "fp:someone-else"; // another program saved meanwhile
    state.stored = "theirs";
    expect(await store.save()).toBe("conflict");
    expect(store.getState().conflict).toBe(true);
    expect(state.stored).toBe("theirs");
    expect(titleOf(store)).toBe("mine"); // the user's work is kept
    expect(dirty(store)).toBe(true);
    store.dismissConflict();
    expect(store.getState().conflict).toBe(false);
  });

  it("reload after a conflict adopts the stored version and drops the draft", async () => {
    const { store, state } = await ready();
    await store.apply(rename("mine"));
    state.storedFp = "fp:theirs";
    state.stored = "theirs";
    await store.save();
    await store.reload();
    expect(titleOf(store)).toBe("theirs");
    expect(dirty(store)).toBe(false);
    expect(store.getState().conflict).toBe(false);
  });

  it("'save as copy' stores the draft under a new id and leaves the original session as it is", async () => {
    const { store, api } = await ready();
    await store.apply(rename("mine"));
    expect(await store.saveCopy()).toBe("copy-id");
    expect(api.importProject).toHaveBeenCalledWith(expect.objectContaining({ title: "mine" }), "new_id");
    expect(dirty(store)).toBe(true);
  });

  it("other save failures are reported with the server's reason and keep the draft dirty", async () => {
    const { store, api } = await ready();
    await store.apply(rename("t1"));
    api.saveProject.mockRejectedValueOnce(new ApiError(0, "NETWORK", "Cannot reach the server"));
    expect(await store.save()).toBe("failed");
    expect(store.getState().notice?.message).toContain("Cannot reach the server");
    expect(dirty(store)).toBe(true);
    expect(await store.save()).toBe("saved"); // and a retry works
  });

  it("notifies subscribers of every change and stops after unsubscribe", async () => {
    const { store } = await ready();
    const listener = vi.fn();
    const off = store.subscribe(listener);
    await store.apply(rename("t1"));
    expect(listener).toHaveBeenCalled();
    const n = listener.mock.calls.length;
    off();
    await store.apply(rename("t2"));
    expect(listener.mock.calls.length).toBe(n);
  });
});
