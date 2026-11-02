import { describe, expect, it, vi } from "vitest";
import type { Operation, Project } from "../../src/api/types";
import { analysisKey, BASE_SELECTION, reconcileSelection, resolveContext } from "../../src/state/analysisContext";
import { EditorStore } from "../../src/state/editorStore";
import { swingReviewIdentity } from "../../src/state/swingReview";
import { doc, node, projectWith } from "../fixtures";

function model(): Project {
  return projectWith([node("cost")], {
    analysis: { method: "mavt", scenario_id: null, weight_profile_id: null, parameters: { dominance_check: false } },
  });
}

describe("the transient method view", () => {
  it("views another method with its own default parameters, and the saved one with the saved parameters", () => {
    const p = model();
    const saved = resolveContext(p, "fp", BASE_SELECTION);
    expect(saved.configuration).toMatchObject({ method: "mavt", parameters: { dominance_check: false } });
    const viewed = resolveContext(p, "fp", { ...BASE_SELECTION, method: "mavt_sorting" });
    expect(viewed.configuration.method).toBe("mavt_sorting");
    expect(viewed.configuration.parameters).toEqual({}); // exactly the defaults, nothing carried over
    expect(analysisKey(viewed, "analysis-record")).not.toBe(analysisKey(saved, "analysis-record"));
    expect(resolveContext(p, "fp", { ...BASE_SELECTION, method: "mavt" }).configuration).toEqual(saved.configuration);
  });
  it("keeps the viewed method through revisions, and never changes swing-review identity", () => {
    const p = model();
    expect(reconcileSelection(p, { ...BASE_SELECTION, method: "mavt_sorting" }).method).toBe("mavt_sorting");
    expect(swingReviewIdentity(p, { ...BASE_SELECTION, method: "mavt_sorting" })).toBe(swingReviewIdentity(p, BASE_SELECTION));
  });
  it("viewing a method creates no edit, while using it as the saved default is one undo step", async () => {
    let current = model();
    const api = {
      getProject: vi.fn(() => Promise.resolve(doc("fp0", current))),
      edit: vi.fn((project: Project, ops: Operation[]) => {
        const op = ops[0];
        current = structuredClone(project);
        if (op?.op === "set_analysis_method") current.analysis = { ...current.analysis, method: op.method, parameters: {} };
        return Promise.resolve(doc("fp1", current));
      }),
      saveProject: vi.fn(), importProject: vi.fn(),
    };
    const store = new EditorStore("p1", api); await store.load();
    store.selectAnalysis({ method: "mavt_sorting" });
    expect(store.getState().session?.past).toHaveLength(0);
    expect(store.getState().anchorReview).toBe(false);
    expect(api.edit).not.toHaveBeenCalled();
    expect(await store.apply([{ op: "set_analysis_method", method: "mavt_sorting" }])).toBe(true);
    expect(api.edit).toHaveBeenCalledTimes(1);
    expect(store.getState().session?.past).toHaveLength(1);
    expect(store.getState().session?.draft.project.analysis.method).toBe("mavt_sorting");
    await store.undo();
    expect(store.getState().session?.draft.project.analysis.method).toBe("mavt");
    expect(store.getState().analysis.method).toBe("mavt_sorting"); // undo never moves the view
  });
});
