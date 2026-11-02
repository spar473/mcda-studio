import { describe, expect, it, vi } from "vitest";
import type { ProjectDocument } from "../../src/api/types";
import { EditorStore } from "../../src/state/editorStore";
import { doc } from "../fixtures";
function deferred() { let resolve!: (v: ProjectDocument) => void; let reject!: (e: Error) => void;
  const promise = new Promise<ProjectDocument>((yes,no) => { resolve=yes; reject=no; }); return { promise,resolve,reject }; }

describe("project revision lifecycle", () => {
  it.each([false,true])("ignores an obsolete load success/failure after a newer reload: %s", async (fail) => {
    const old=deferred();const fresh=deferred();
    const api={ getProject:vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise), edit:vi.fn(),saveProject:vi.fn(),importProject:vi.fn() };
    const store=new EditorStore("p1",api);const first=store.load();const second=store.reload();
    fresh.resolve(doc("fresh"));await second;
    if(fail)old.reject(new Error("old failure"));else old.resolve(doc("old"));await first;
    expect(store.getState().session?.draft.fingerprint).toBe("fresh");expect(store.getState().status).toBe("ready");
  });
  it("an edit response from before reload cannot replace the reloaded revision", async () => {
    const pending=deferred();
    const api={ getProject:vi.fn().mockResolvedValueOnce(doc("old")).mockResolvedValueOnce(doc("fresh")),
      edit:vi.fn(() => pending.promise),saveProject:vi.fn(),importProject:vi.fn() };
    const store=new EditorStore("p1",api);await store.load();const edit=store.apply([{op:"update_project",title:"old edit"}]);
    const queued=store.apply([{op:"update_project",title:"queued before reload"}]);
    await Promise.resolve();await store.reload();pending.resolve(doc("obsolete edit"));
    expect(await edit).toBe(false);expect(await queued).toBe(false);
    expect(api.edit).toHaveBeenCalledTimes(1);expect(store.getState().pending).toBe(0);
    expect(store.getState().session?.draft.fingerprint).toBe("fresh");
  });
});
