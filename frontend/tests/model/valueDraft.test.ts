import { describe, expect, it } from "vitest";
import { candidateFromDraft, initialValueDraft, insertControlPoint, moveHandle, setDraftNumber } from "../../src/model/valueDraft";
import { ordinalScale, ratioScale } from "../fixtures";
const piecewise = () => initialValueDraft(ratioScale, { kind: "piecewise_linear", out_of_domain: "error", points: [{x:0,value:0},{x:4,value:.3},{x:10,value:1}] });
describe("value candidates contain judgements, never an independent evaluator", () => {
  it.each(["", "-", "NaN", "Infinity", "1e999"])("retains invalid numeric text %s and blocks a valid-looking fallback", (raw) => {
    const draft = setDraftNumber(piecewise(), "point.1.value", raw);
    expect(draft.text["point.1.value"]).toBe(raw);
    expect(candidateFromDraft(draft).errors).toHaveLength(1);
  });
  it("pointer/keyboard coordinate inputs use the same raw candidate path as table input", () => {
    const base = piecewise(), before = structuredClone(base);
    expect(candidateFromDraft(moveHandle(base,1,5,.4))).toEqual(candidateFromDraft(setDraftNumber(setDraftNumber(base,"point.1.x","5"),"point.1.value","0.4")));
    expect(base).toEqual(before);
  });
  it("keeps endpoint preference judgements fixed while editing endpoint measurements", () => {
    const result = candidateFromDraft(moveHandle(piecewise(),0,-1,.2));
    expect(result.candidate.value_function).toMatchObject({points:[{x:-1,value:0},{x:4,value:.3},{x:10,value:1}]});
  });
  it("requires explicit new coordinates and preserves invalid order for server validation", () => {
    expect(insertControlPoint({...piecewise(),newX:"5"})).toBeNull();
    const draft = insertControlPoint({...piecewise(),newX:"2",newValue:".4"});
    expect(draft?.valueFunction).toMatchObject({ points:[{x:0,value:0},{x:4,value:.3},{x:2,value:.4},{x:10,value:1}] });
    expect(candidateFromDraft({...piecewise(),newX:"5"}).errors).toHaveLength(1);
  });
  it("does not fill missing qualitative judgements", () => {
    const result = candidateFromDraft(initialValueDraft(ordinalScale,{kind:"qualitative",mapping:{Low:0,High:1}}));
    expect(result.candidate.value_function).toEqual({kind:"qualitative",mapping:{Low:0,High:1}});
  });
  it("preserves hidden anchors and refuses local linear handle edits", () => {
    const draft = initialValueDraft({...ratioScale,anchor_mode:"local"},{kind:"linear",direction:"decreasing",out_of_domain:"error"});
    expect(moveHandle(draft,0,5,1)).toBe(draft);
    expect(candidateFromDraft(draft).candidate.scale).toEqual({...ratioScale,anchor_mode:"local"});
  });
  it("direct and qualitative handles change only explicit inputs", () => {
    const direct = initialValueDraft({...ratioScale,type:"interval"},{kind:"direct_rating",min_rating:0,max_rating:10,out_of_domain:"error"});
    expect(candidateFromDraft(moveHandle(direct,1,20,.8)).candidate.value_function).toMatchObject({max_rating:20});
    const labels = initialValueDraft(ordinalScale,{kind:"qualitative",mapping:{Low:0,Mid:.3,High:1}});
    expect(candidateFromDraft(moveHandle(labels,1,99,.6)).candidate.value_function).toMatchObject({mapping:{Low:0,Mid:.6,High:1}});
  });
});
