import { describe, expect, it, vi } from "vitest";
import { analysisKey, BASE_SELECTION, reconcileSelection, resolveContext } from "../../src/state/analysisContext";
import { EditorStore } from "../../src/state/editorStore";
import { doc, node, projectWith } from "../fixtures";

function model() {
  return projectWith([node("cost")], {
    analysis: { method: "mavt", scenario_id: "scenario", weight_profile_id: "other", parameters: { nested: { b: 2, a: 1 } } },
    weight_profiles: [
      { id: "first", name: "First", method: "swing", judgements: {} },
      { id: "other", name: "Other", method: "swing", judgements: {} },
    ],
    scenarios: [{ id: "scenario", name: "Scenario", weight_profile_id: "other", value_function_overrides: {} }],
  });
}

describe("shared analysis context", () => {
  it("explicit base view clears the persisted scenario/profile; resolution follows engine precedence", () => {
    const p = model();
    expect(resolveContext(p, "fp", BASE_SELECTION)).toMatchObject({ scenarioId: null, resolvedProfileId: "first",
      configuration: { scenario_id: null, weight_profile_id: null, method: "mavt" } });
    const scenario = { ...BASE_SELECTION, scenarioId: "scenario" };
    expect(resolveContext(p, "fp", scenario).resolvedProfileId).toBe("other");
    expect(resolveContext(p, "fp", { ...scenario, profileId: "first" }).resolvedProfileId).toBe("first");
  });
  it("drops deleted references and preserves surviving stable ids after revisions/undo", () => {
    const p = model();
    expect(reconcileSelection(p, { scenarioId: "gone", profileId: "gone", criterionId: "cost" }))
      .toEqual({ ...BASE_SELECTION, criterionId: "cost" });
    p.criteria = [];
    expect(reconcileSelection(p, { ...BASE_SELECTION, criterionId: "cost" }).criterionId).toBeNull();
  });
  it("keys include revision, complete parameters, criterion, kind and pending candidate identity", () => {
    const p = model(); const before = structuredClone(p);
    const ctx = resolveContext(p, "fp1", BASE_SELECTION);
    const key = analysisKey(ctx, "preview", { candidate: { x: 1 } });
    for (const other of [analysisKey({ ...ctx, fingerprint: "fp2" }, "preview", { candidate: { x: 1 } }),
      analysisKey({ ...ctx, criterionId: "cost" }, "preview", { candidate: { x: 1 } }),
      analysisKey({ ...ctx, configuration: { ...ctx.configuration, parameters: { nested: { a: 9 } } } }, "preview"),
      analysisKey(ctx, "weights"), analysisKey(ctx, "preview", { candidate: { x: 2 } })]) expect(other).not.toBe(key);
    expect(analysisKey(ctx, "x", { b: 2, a: 1 })).toBe(analysisKey(ctx, "x", { a: 1, b: 2 }));
    ctx.configuration.parameters.changed = true;
    expect(p).toEqual(before);
  });
  it("store selection and review acknowledgement never edit project, history, fingerprint or library", async () => {
    const p = model(); const original = doc("original", p);
    const api = { getProject: vi.fn(() => Promise.resolve(original)), edit: vi.fn(), saveProject: vi.fn(), importProject: vi.fn() };
    const store = new EditorStore(p.id, api); await store.load();
    const session = store.getState().session;
    store.selectAnalysis({ scenarioId: "scenario", profileId: "first", criterionId: "cost" });
    store.acknowledgeAnchorReview();
    expect(store.getState().session).toBe(session);
    expect(store.getState().session?.past).toHaveLength(0);
    expect(api.edit).not.toHaveBeenCalled(); expect(api.saveProject).not.toHaveBeenCalled();
    expect(p).toEqual(original.project);
  });
  it("alternative-set revisions require reviewing local-anchor swings, with no fabricated data", async () => {
    const p = model(); const next = structuredClone(p);
    next.alternatives.push({ id: "new", name: "New", metadata: {} });
    const warning = { severity: "warning" as const, code: "LOCAL_ANCHORS", path: "criteria[cost]", message: "local" };
    const api = { getProject: vi.fn(() => Promise.resolve(doc("old", p, [warning]))),
      edit: vi.fn(() => Promise.resolve(doc("new", next, [warning]))), saveProject: vi.fn(), importProject: vi.fn() };
    const store = new EditorStore(p.id, api); await store.load();
    await store.apply([{ op: "add_alternative", name: "New" }]);
    expect(store.getState().anchorReview).toBe(true);
    expect(store.getState().session?.draft.project.performances).toEqual([]);
    expect(resolveContext(next, "new", BASE_SELECTION).fingerprint).not.toBe("old");
    store.acknowledgeAnchorReview(); expect(store.getState().anchorReview).toBe(false);
    await store.undo(); expect(store.getState().session?.draft.fingerprint).toBe("old");
  });
  it("reconciles a selected criterion removed through an edit", async () => {
    const p = model(); const after = { ...p, criteria: [] };
    const api = { getProject: vi.fn(() => Promise.resolve(doc("old", p))), edit: vi.fn(() => Promise.resolve(doc("new", after))),
      saveProject: vi.fn(), importProject: vi.fn() };
    const store = new EditorStore(p.id, api); await store.load(); store.selectAnalysis({ criterionId: "cost" });
    await store.apply([{ op: "remove_criterion", criterion_id: "cost" }]);
    expect(store.getState().analysis.criterionId).toBeNull();
  });
});
