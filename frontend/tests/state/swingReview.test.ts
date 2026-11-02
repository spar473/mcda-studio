import { describe, expect, it, vi } from "vitest";
import { EditorStore } from "../../src/state/editorStore";
import type { Project } from "../../src/api/types";
import { doc, node, projectWith, ratioScale } from "../fixtures";

async function fixture(local = false) {
  let p = projectWith([node("cost",null,0,{ scale:{...ratioScale,anchor_mode:local?"local":"fixed"},
    value_function:{kind:"linear",direction:"increasing",out_of_domain:"error"} })], {
    alternatives:[{id:"a",name:"A",metadata:{}},{id:"b",name:"B",metadata:{}}],
    performances:[{alternative_id:"a",criterion_id:"cost",value:2},{alternative_id:"b",criterion_id:"cost",value:8}],
    analysis:{method:"mavt",scenario_id:null,weight_profile_id:null,parameters:{}},
    weight_profiles:[{id:"one",name:"One",method:"swing",judgements:{}},{id:"two",name:"Two",method:"swing",judgements:{}}],
    scenarios:[{id:"s",name:"S",weight_profile_id:"two",value_function_overrides:{}}],
  });
  let revision=0;
  const api={getProject:vi.fn(() => Promise.resolve(doc("initial",p))),
    edit:vi.fn(() => Promise.resolve(doc(`fp${++revision}`,p))),saveProject:vi.fn(),importProject:vi.fn()};
  const store=new EditorStore("p1",api);await store.load();
  const change=async (mutate:(draft:Project)=>void) => { p=structuredClone(p);mutate(p);await store.apply([{op:"update_project",title:p.title}]); };
  return {store,api,change};
}

describe("context-bound session swing review", () => {
  it("resets acknowledgement on each new fixed range/direction and on A-B-A transitions", async () => {
    const {store,change}=await fixture();
    await change(p => { if(p.criteria[0]?.scale)p.criteria[0].scale.upper=20; });
    expect(store.getState().anchorReview).toBe(true);store.acknowledgeAnchorReview();
    const key=store.getState().acknowledgedSwingReviewKey;
    await change(p => { p.title="Only title"; });expect(store.getState().anchorReview).toBe(false);
    store.selectAnalysis({criterionId:"cost"});expect(store.getState().anchorReview).toBe(false);
    await change(p => { if(p.criteria[0]?.scale)p.criteria[0].scale.upper=30; });
    expect(store.getState().anchorReview).toBe(true);expect(store.getState().acknowledgedSwingReviewKey).toBeNull();
    store.acknowledgeAnchorReview();
    await change(p => { if(p.criteria[0]?.scale)p.criteria[0].scale.upper=20; });
    expect(store.getState().anchorReview).toBe(true);expect(store.getState().swingReviewKey).toBe(key);
  });
  it("tracks local measurements and alternative completeness, but not fixed in-range measurement edits", async () => {
    const fixed=await fixture();await fixed.change(p => { if(p.performances[0])p.performances[0].value=3; });
    expect(fixed.store.getState().anchorReview).toBe(false);
    const {store,change}=await fixture(true);
    await change(p => { if(p.performances[0])p.performances[0].value=3; });
    expect(store.getState().anchorReview).toBe(true);store.acknowledgeAnchorReview();
    await change(p => { p.alternatives.push({id:"c",name:"C",metadata:{}}); });
    expect(store.getState().anchorReview).toBe(true);
  });
  it("resets for scenario/profile/preference changes and acknowledgement is explicitly non-mutating", async () => {
    const {store,api,change}=await fixture();
    store.selectAnalysis({scenarioId:"s"});expect(store.getState().anchorReview).toBe(true);
    const before=store.getState().session;const data=JSON.stringify(before);
    const edits=api.edit.mock.calls.length;store.acknowledgeAnchorReview();
    expect(store.getState().session).toBe(before);expect(JSON.stringify(store.getState().session)).toBe(data);
    expect(api.edit).toHaveBeenCalledTimes(edits);expect(api.saveProject).not.toHaveBeenCalled();
    store.selectAnalysis({profileId:"one"});expect(store.getState().anchorReview).toBe(true);
    store.acknowledgeAnchorReview();
    await change(p => { const vf=p.criteria[0]?.value_function;if(vf?.kind==="linear")vf.direction="decreasing"; });
    expect(store.getState().anchorReview).toBe(true);
    store.acknowledgeAnchorReview();await store.reload();expect(store.getState().acknowledgedSwingReviewKey).toBeNull();
  });
});
