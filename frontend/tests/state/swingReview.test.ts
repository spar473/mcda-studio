import { describe, expect, it, vi } from "vitest";
import { EditorStore } from "../../src/state/editorStore";
import type { Project } from "../../src/api/types";
import { doc, node, projectWith, ratioScale } from "../fixtures";

async function fixture(local = false) {
  let p = projectWith([node("cost", null, 0, { scale: { ...ratioScale, anchor_mode: local ? "local" : "fixed" },
    value_function: { kind: "linear", direction: "increasing", out_of_domain: "error" } })], {
    alternatives: [{ id: "a", name: "A", metadata: {} }, { id: "b", name: "B", metadata: {} }],
    performances: [{ alternative_id: "a", criterion_id: "cost", value: 2 }, { alternative_id: "b", criterion_id: "cost", value: 8 }],
    analysis: { method: "mavt", scenario_id: null, weight_profile_id: null, parameters: {} },
    weight_profiles: [{ id: "one", name: "One", method: "swing", judgements: {} }, { id: "two", name: "Two", method: "swing", judgements: {} }],
    scenarios: [{ id: "s", name: "S", weight_profile_id: "two", value_function_overrides: {} }],
  });
  let revision = 0;
  const issues = local ? [{ severity: "warning" as const, code: "LOCAL_ANCHORS", path: "criteria[cost]", message: "Local anchors" }] : [];
  const api = { getProject: vi.fn(() => Promise.resolve(doc("initial", p, issues))),
    edit: vi.fn(() => Promise.resolve(doc(`fp${++revision}`, p, issues))), saveProject: vi.fn(), importProject: vi.fn() };
  const store = new EditorStore("p1", api); await store.load();
  const change = async (mutate: (draft: Project) => void) => { p = structuredClone(p); mutate(p); await store.apply([{ op: "update_project", title: p.title }]); };
  return { store, api, change };
}

describe("context-bound session swing review", () => {
  it("resets acknowledgement on each new fixed range/direction and on A-B-A transitions", async () => {
    const { store, change } = await fixture();
    await change(p => { if (p.criteria[0]?.scale) p.criteria[0].scale.upper = 20; });
    expect(store.getState().anchorReview).toBe(true); store.acknowledgeAnchorReview();
    const key = store.getState().acknowledgedSwingReviewKey;
    await change(p => { p.title = "Only title"; }); expect(store.getState().anchorReview).toBe(false);
    store.selectAnalysis({ criterionId: "cost" }); expect(store.getState().anchorReview).toBe(false);
    await change(p => { if (p.criteria[0]?.scale) p.criteria[0].scale.upper = 30; });
    expect(store.getState().anchorReview).toBe(true); expect(store.getState().acknowledgedSwingReviewKey).toBeNull();
    store.acknowledgeAnchorReview();
    await change(p => { if (p.criteria[0]?.scale) p.criteria[0].scale.upper = 20; });
    expect(store.getState().anchorReview).toBe(true); expect(store.getState().swingReviewKey).toBe(key);
  });

  it("tracks local measurements and alternative completeness, but not fixed in-range measurement edits", async () => {
    const fixed = await fixture(); await fixed.change(p => { if (p.performances[0]) p.performances[0].value = 3; });
    expect(fixed.store.getState().anchorReview).toBe(false);
    await fixed.change(p => { p.alternatives.push({ id: "c", name: "C", metadata: {} }); });
    expect(fixed.store.getState().anchorReview).toBe(false);
    const { store, change } = await fixture(true);
    await change(p => { if (p.performances[0]) p.performances[0].value = 3; });
    expect(store.getState().anchorReview).toBe(true); store.acknowledgeAnchorReview();
    await change(p => { p.alternatives.push({ id: "c", name: "C", metadata: {} }); });
    expect(store.getState().anchorReview).toBe(true);
  });

  it("keeps fixed-range profile/scenario viewing quiet and acknowledgement explicitly non-mutating", async () => {
    const { store, api, change } = await fixture();
    const before = store.getState().session, data = JSON.stringify(before);
    store.selectAnalysis({ scenarioId: "s" }); expect(store.getState().anchorReview).toBe(false);
    store.selectAnalysis({ profileId: "one" }); expect(store.getState().anchorReview).toBe(false);
    store.selectAnalysis({ profileId: "two" }); expect(store.getState().anchorReview).toBe(false);
    expect(store.getState().session).toBe(before); expect(JSON.stringify(store.getState().session)).toBe(data);
    expect(api.edit).not.toHaveBeenCalled(); expect(api.saveProject).not.toHaveBeenCalled();
    store.acknowledgeAnchorReview();
    expect(store.getState().session).toBe(before); expect(JSON.stringify(store.getState().session)).toBe(data);
    expect(api.edit).not.toHaveBeenCalled(); expect(api.saveProject).not.toHaveBeenCalled();
    await change(p => { const vf = p.criteria[0]?.value_function; if (vf?.kind === "linear") vf.direction = "decreasing"; });
    expect(store.getState().anchorReview).toBe(true);
    const edited = store.getState().session, edits = api.edit.mock.calls.length;
    store.acknowledgeAnchorReview();
    expect(store.getState().session).toBe(edited); expect(api.edit).toHaveBeenCalledTimes(edits);
    await store.reload(); expect(store.getState().acknowledgedSwingReviewKey).toBeNull();
  });

  it("does not treat a rating edit or another scenario with the same domain as a range change", async () => {
    const { store, change } = await fixture();
    await change(p => { const profile = p.weight_profiles[0]; if (profile) profile.judgements.cost = 70; });
    expect(store.getState().anchorReview).toBe(false);
    await change(p => { const scenario = p.scenarios[0]; if (scenario) scenario.value_function_overrides.cost = {
      kind: "piecewise_linear", points: [{ x: 0, value: 0 }, { x: 5, value: 0.25 }, { x: 10, value: 1 }], out_of_domain: "error",
    }; });
    expect(store.getState().anchorReview).toBe(false);
    store.selectAnalysis({ scenarioId: "s" }); expect(store.getState().anchorReview).toBe(false);
    await change(p => { const vf = p.scenarios[0]?.value_function_overrides.cost; if (vf?.kind === "piecewise_linear" && vf.points[1]) vf.points[1].value = 0.75; });
    expect(store.getState().anchorReview).toBe(false);
    await change(p => { if (p.criteria[0]?.scale) p.criteria[0].scale.upper = 50; });
    expect(store.getState().anchorReview).toBe(false); // inactive linear bounds are not this scenario's domain
    await change(p => { const scenario = p.scenarios[0]; if (scenario) p.scenarios.push({ ...structuredClone(scenario), id: "same", name: "Same ranges" }); });
    expect(store.getState().anchorReview).toBe(false);
    store.selectAnalysis({ scenarioId: "same" }); expect(store.getState().anchorReview).toBe(false);
  });

  it("reviews a scenario only when its domain or worst-to-best endpoints change", async () => {
    const { store, change } = await fixture();
    await change(p => { const scenario = p.scenarios[0]; if (scenario) scenario.value_function_overrides.cost = {
      kind: "piecewise_linear", points: [{ x: 0, value: 0 }, { x: 20, value: 1 }], out_of_domain: "error",
    }; });
    expect(store.getState().anchorReview).toBe(false);
    store.selectAnalysis({ scenarioId: "s" }); expect(store.getState().anchorReview).toBe(true);
    store.acknowledgeAnchorReview();
    store.selectAnalysis({ scenarioId: null }); expect(store.getState().anchorReview).toBe(true);
    store.acknowledgeAnchorReview();
    await change(p => { const vf = p.criteria[0]?.value_function; if (vf?.kind === "linear") vf.direction = "decreasing"; });
    expect(store.getState().anchorReview).toBe(true);
  });

  it("tracks direct-rating domains and explicit qualitative anchors without curve arithmetic", async () => {
    const { store, change } = await fixture();
    await change(p => { const n = p.criteria[0]; if (n?.scale) { n.scale.type = "interval"; n.value_function = { kind: "direct_rating", min_rating: 0, max_rating: 10, out_of_domain: "error" }; } });
    store.acknowledgeAnchorReview();
    await change(p => { const vf = p.criteria[0]?.value_function; if (vf?.kind === "direct_rating") vf.max_rating = 12; });
    expect(store.getState().anchorReview).toBe(true); store.acknowledgeAnchorReview();
    await change(p => { const n = p.criteria[0]; if (n?.scale) { n.scale = { type: "ordinal", unit: null, lower: null, upper: null, anchor_mode: "fixed", labels: ["Low", "Mid", "High"] }; n.value_function = { kind: "qualitative", mapping: { Low: 0, Mid: 0.5, High: 1 } }; } });
    store.acknowledgeAnchorReview();
    await change(p => { const vf = p.criteria[0]?.value_function; if (vf?.kind === "qualitative") vf.mapping.Mid = 0.75; });
    expect(store.getState().anchorReview).toBe(false);
    await change(p => { const vf = p.criteria[0]?.value_function; if (vf?.kind === "qualitative") { vf.mapping.Low = 1; vf.mapping.High = 0; } });
    expect(store.getState().anchorReview).toBe(true);
  });

  it("does not inherit base local-observation changes when the viewed scenario fixes the domain", async () => {
    const { store, change } = await fixture(true);
    await change(p => { const scenario = p.scenarios[0]; if (scenario) scenario.value_function_overrides.cost = {
      kind: "piecewise_linear", points: [{ x: 0, value: 0 }, { x: 10, value: 1 }], out_of_domain: "error",
    }; });
    expect(store.getState().anchorReview).toBe(false);
    store.selectAnalysis({ scenarioId: "s" });
    expect(store.getState().anchorReview).toBe(true);
    store.acknowledgeAnchorReview();
    expect(store.getState().session?.draft.validation.issues.some(i => i.code === "LOCAL_ANCHORS")).toBe(true);
    await change(p => { if (p.performances[0]) p.performances[0].value = 3; });
    expect(store.getState().anchorReview).toBe(false);
    await change(p => { p.alternatives.push({ id: "c", name: "C", metadata: {} }); });
    expect(store.getState().anchorReview).toBe(false);
  });
});
