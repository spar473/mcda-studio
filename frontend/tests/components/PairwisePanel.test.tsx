import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { AhpMatrixPreview, AhpModel, Operation, PairwiseJudgement, Project } from "../../src/api/types";
import { PairwisePanel } from "../../src/components/PairwisePanel";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import { node, projectWith } from "../fixtures";

function preview(items: string[], judgements: PairwiseJudgement[]): AhpMatrixPreview {
  const pairs = items.length * (items.length - 1) / 2;
  if (judgements.length < pairs) return { random_index_table: "saaty-tran-2007", consistency_threshold: 0.1, ready: false,
    issues: [{ severity: "error", code: "AHP_JUDGEMENT_MISSING", message: "pairs not judged: a/b", path: "matrix" }], analysis: null };
  const inconsistent = items.length === 3 && judgements.some((j) => j.row === "c" && j.column === "a"); // the cyclic judgement
  return { random_index_table: "saaty-tran-2007", consistency_threshold: 0.1, ready: true, issues: [], analysis: {
    items, priorities: Object.fromEntries(items.map((i) => [i, 1 / items.length])), lambda_max: inconsistent ? 3.5 : items.length,
    consistency_index: inconsistent ? 0.25 : 0, random_index: items.length >= 3 ? 0.52 : 0, consistency_ratio: inconsistent ? 0.48 : 0,
    inconsistent, iterations: 3,
    most_inconsistent_triad: items.length >= 3 ? { items: [items[0] ?? "", items[1] ?? "", items[2] ?? ""], judgements: [9, 9, 1 / 9],
      index: 0.99, consistent_value: 81 } : null,
  } };
}

function setup(ahp: AhpModel | null = null, method = "mavt") {
  const project: Project = projectWith([node("cost", null, 0, { name: "Cost" }), node("risk", null, 1, { name: "Risk" })], {
    alternatives: [{ id: "a", name: "Alpha", metadata: {} }, { id: "b", name: "Beta", metadata: {} }, { id: "c", name: "Gamma", metadata: {} }],
    analysis: { method: "mavt", scenario_id: null, weight_profile_id: null, parameters: {} },
    ...(ahp ? { ahp } : {}),
  });
  const spy = vi.spyOn(api, "previewAhpMatrix").mockImplementation((items, judgements) => Promise.resolve(preview(items, judgements)));
  vi.spyOn(api, "validateAnalysis").mockImplementation((_p, configuration) => Promise.resolve({
    project_fingerprint: "fp", configuration, scenario_id: null, weight_profile_id: null, validation: { issues: [] } }));
  const apply = vi.fn<(ops: Operation[]) => Promise<boolean>>(() => Promise.resolve(true));
  render(<PairwisePanel project={project} context={resolveContext(project, "fp", { ...BASE_SELECTION, method })} busy={false} apply={apply}/>);
  return { apply, spy };
}
async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(130); }); }
const choose = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

describe("the Pairwise editor", () => {
  it("states every matrix with Saaty's verbal scale and applies one edit, each pair stored once", () => {
    const { apply } = setup();
    expect(screen.getAllByRole("group").map((g) => g.getAttribute("aria-label"))).toEqual(
      ["Top-level criteria", "Alternatives on Cost", "Alternatives on Risk"]);
    const options = within(screen.getByLabelText("Judgement of Cost against Risk")).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Not judged", "Cost 9× (extreme)", "Cost 8×", "Cost 7× (very strong)", "Cost 6×", "Cost 5× (strong)", "Cost 4×",
      "Cost 3× (moderate)", "Cost 2×", "Equal (1)", "Risk 2×", "Risk 3× (moderate)", "Risk 4×", "Risk 5× (strong)", "Risk 6×",
      "Risk 7× (very strong)", "Risk 8×", "Risk 9× (extreme)"]);
    choose("Judgement of Cost against Risk", "3");
    const cost = within(screen.getByRole("group", { name: "Alternatives on Cost" }));
    fireEvent.change(cost.getByLabelText("Judgement of Alpha against Beta"), { target: { value: "-2" } });
    fireEvent.change(cost.getByLabelText("Judgement of Alpha against Gamma"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply judgements" }));
    expect(apply.mock.calls.map((c) => c[0])).toEqual([[{ op: "set_ahp_model", ahp: {
      criteria: [{ parent_id: null, judgements: [{ row: "cost", column: "risk", value: 3 }] }],
      alternatives: [{ criterion_id: "cost", judgements: [{ row: "b", column: "a", value: 2 }, { row: "a", column: "c", value: 1 }] }],
    } }]]);
  });
  it("shows the live preview from Python, the warning and the triad's cells", async () => {
    const { spy } = setup({ criteria: [{ parent_id: null, judgements: [{ row: "cost", column: "risk", value: 2 }] }], alternatives: [
      { criterion_id: "cost", judgements: [{ row: "a", column: "b", value: 9 }, { row: "b", column: "c", value: 9 }, { row: "c", column: "a", value: 9 }] },
    ] });
    await settle();
    expect(spy).toHaveBeenCalledWith(["a", "b", "c"], [{ row: "a", column: "b", value: 9 }, { row: "c", column: "a", value: 9 },
      { row: "b", column: "c", value: 9 }], expect.any(AbortSignal));
    const cost = within(screen.getByRole("group", { name: "Alternatives on Cost" }));
    expect(cost.getByLabelText("Consistency warning: Alternatives on Cost")).toHaveTextContent(
      "Consistency ratio 0.480 is above 0.10: review the judgements. Most inconsistent triad: Alpha over Beta: 9; Beta over Gamma: 9; Alpha over Gamma: 1/9, where consistency would need 81.");
    expect(cost.getAllByRole("row").filter((r) => r.getAttribute("data-in-triad") === "true")).toHaveLength(3);
    expect(cost.getByLabelText("Consistency: Alternatives on Cost")).toHaveTextContent("CR 0.4800");
    const risk = within(screen.getByRole("group", { name: "Alternatives on Risk" }));
    expect(risk.getByLabelText("Consistency: Alternatives on Risk")).toHaveTextContent("pairs not judged");
    expect(screen.queryByLabelText("Consistency warning: Top-level criteria")).toBeNull();
    fireEvent.change(cost.getByLabelText("Judgement of Alpha against Gamma"), { target: { value: "2" } });
    await settle();
    expect(cost.queryByLabelText("Consistency warning: Alternatives on Cost")).toBeNull();
    expect(cost.getAllByRole("row").filter((r) => r.getAttribute("data-in-triad") === "true")).toHaveLength(0);
  });
  it("keeps a stored non-integer judgement as custom and removes the section only after confirmation", () => {
    const { apply } = setup({ criteria: [{ parent_id: null, judgements: [{ row: "risk", column: "cost", value: 2.5 }] }], alternatives: [] }, "ahp");
    expect(screen.getByLabelText("Judgement of Cost against Risk")).toHaveDisplayValue("custom: Risk 2.5×");
    expect(screen.getByRole("button", { name: "Apply judgements" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Remove all judgements" }));
    expect(apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Remove judgements" }));
    expect(apply.mock.calls.map((c) => c[0])).toEqual([[{ op: "clear_ahp_model" }]]);
  });
});
