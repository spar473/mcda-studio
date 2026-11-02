import { describe, expect, it } from "vitest";
import { HISTORY_LIMIT, initialSession, isDirty, sessionReducer } from "../../src/model/session";
import { doc } from "../fixtures";

describe("editing session", () => {
  it("starts clean", () => {
    const s = initialSession(doc("f0"));
    expect(isDirty(s)).toBe(false);
    expect(s.past).toEqual([]);
  });

  it("an edit makes it dirty; undoing back to the saved revision makes it clean again", () => {
    let s = initialSession(doc("f0"));
    s = sessionReducer(s, { type: "edited", doc: doc("f1") });
    expect(isDirty(s)).toBe(true);
    s = sessionReducer(s, { type: "undo" });
    expect(s.draft.fingerprint).toBe("f0");
    expect(isDirty(s)).toBe(false);
    s = sessionReducer(s, { type: "redo" });
    expect(s.draft.fingerprint).toBe("f1");
    expect(isDirty(s)).toBe(true);
  });

  it("an edit that changes nothing (same fingerprint) is not an undo step", () => {
    const s0 = initialSession(doc("f0"));
    const s1 = sessionReducer(s0, { type: "edited", doc: doc("f0") });
    expect(s1).toBe(s0);
  });

  it("a new edit discards the redo branch", () => {
    let s = initialSession(doc("f0"));
    s = sessionReducer(s, { type: "edited", doc: doc("f1") });
    s = sessionReducer(s, { type: "undo" });
    expect(s.future).toHaveLength(1);
    s = sessionReducer(s, { type: "edited", doc: doc("f2") });
    expect(s.future).toEqual([]);
  });

  it("undo and redo with nothing to do change nothing", () => {
    const s = initialSession(doc("f0"));
    expect(sessionReducer(s, { type: "undo" })).toBe(s);
    expect(sessionReducer(s, { type: "redo" })).toBe(s);
  });

  it("saving makes the draft the saved revision and keeps the history, so undo past a save is dirty", () => {
    let s = initialSession(doc("f0"));
    s = sessionReducer(s, { type: "edited", doc: doc("f1") });
    s = sessionReducer(s, { type: "saved", doc: doc("f1") });
    expect(isDirty(s)).toBe(false);
    expect(s.past).toHaveLength(1);
    s = sessionReducer(s, { type: "undo" });
    expect(isDirty(s)).toBe(true); // f0 differs from the saved f1
  });

  it("history is bounded", () => {
    let s = initialSession(doc("f0"));
    for (let i = 1; i <= HISTORY_LIMIT + 25; i++) s = sessionReducer(s, { type: "edited", doc: doc(`f${String(i)}`) });
    expect(s.past).toHaveLength(HISTORY_LIMIT);
    expect(s.draft.fingerprint).toBe(`f${String(HISTORY_LIMIT + 25)}`);
  });
});
