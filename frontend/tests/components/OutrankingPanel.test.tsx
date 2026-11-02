import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { Operation, Project, PrometheeModel } from "../../src/api/types";
import { OutrankingPanel } from "../../src/components/OutrankingPanel";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import { node, projectWith, ratioScale } from "../fixtures";

const labels = { type: "ordinal" as const, unit: null, lower: null, upper: null, anchor_mode: "fixed" as const, labels: ["low", "mid", "high"] };

function setup(promethee: PrometheeModel | null = null, issues: { code: string; path: string; severity?: "error" | "warning" }[] = [], method = "mavt") {
  const project: Project = projectWith([
    node("cost", null, 0, { name: "Cost", scale: ratioScale }),
    node("grade", null, 1, { name: "Grade", scale: labels }),
  ], {
    alternatives: [{ id: "a", name: "Alpha", metadata: {} }, { id: "b", name: "Beta", metadata: {} }],
    analysis: { method: "mavt", scenario_id: null, weight_profile_id: null, parameters: {} },
    ...(promethee ? { promethee } : {}),
  });
  const validate = vi.spyOn(api, "validateAnalysis").mockImplementation((_p, configuration) => Promise.resolve({
    project_fingerprint: "fp", configuration, scenario_id: null, weight_profile_id: null,
    validation: { issues: issues.map((i) => ({ severity: "error" as const, message: i.code, ...i })) },
  }));
  const apply = vi.fn<(ops: Operation[]) => Promise<boolean>>(() => Promise.resolve(true));
  render(<OutrankingPanel project={project} context={resolveContext(project, "fp", { ...BASE_SELECTION, method })} busy={false} apply={apply}/>);
  return { apply, validate };
}
const applied = (apply: ReturnType<typeof setup>["apply"]) => apply.mock.calls.map((c) => c[0]);
async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(125); }); }
beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

const SECTION: PrometheeModel = { criteria: [
  { criterion_id: "cost", direction: "minimise", weight: 3, function: { kind: "linear", q: 1, p: 4 } },
  { criterion_id: "grade", direction: "maximise", weight: 1, function: { kind: "usual" }, coding: { low: 1, mid: 2, high: 3 } },
] };

describe("the Outranking editor", () => {
  it("states every leaf's direction, weight, function and codes, applied as one edit", () => {
    const { apply } = setup();
    expect(screen.getByLabelText("Why swing weights are not reused")).toHaveTextContent("Swing weights are not reused here");
    fireEvent.change(screen.getByLabelText("Direction for Cost"), { target: { value: "minimise" } });
    fireEvent.change(screen.getByLabelText("Weight for Cost"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Preference function for Cost"), { target: { value: "linear" } });
    fireEvent.change(screen.getByLabelText("q for Cost"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("p for Cost"), { target: { value: "4" } });
    fireEvent.change(screen.getByLabelText("Direction for Grade"), { target: { value: "maximise" } });
    fireEvent.change(screen.getByLabelText("Weight for Grade"), { target: { value: "1" } });
    expect(screen.getByRole("alert")).toHaveTextContent("The code for low on Grade must be a number.");
    fireEvent.click(screen.getByRole("button", { name: "Number in label order" }));
    fireEvent.click(screen.getByRole("button", { name: "Apply outranking inputs" }));
    expect(applied(apply)).toEqual([[{ op: "set_promethee_model", promethee: SECTION }]]);
  });
  it("asks for a direction instead of assuming one", () => {
    setup();
    expect(screen.getByRole("alert")).toHaveTextContent("Choose whether Cost is maximised or minimised.");
    expect(screen.getByRole("button", { name: "Apply outranking inputs" })).toBeDisabled();
  });
  it("draws each function's shape from its thresholds alone", () => {
    setup(SECTION);
    const shape = screen.getByTestId("shape-cost");
    expect(shape).toHaveAccessibleName("Function shape for Cost");
    expect([...shape.querySelectorAll("text")].map((t) => t.textContent)).toEqual(["q", "p"]);
    expect(shape.textContent).not.toMatch(/\d/);
    fireEvent.change(screen.getByLabelText("p for Cost"), { target: { value: "0.5" } });
    expect(screen.queryByTestId("shape-cost")).toBeNull();
    expect(screen.getByLabelText("Codes for Grade")).toBeInTheDocument();
    expect(screen.queryByLabelText("Codes for Cost")).toBeNull();
  });
  it("shows the engine's issues for the saved section, checked under PROMETHEE II", async () => {
    const { validate } = setup(SECTION, [{ code: "PROMETHEE_CRITERION_INERT", path: "promethee.criteria[cost]", severity: "warning" },
      { code: "MISSING_VALUE_FUNCTION", path: "criteria[cost]" }]);
    await settle();
    expect(validate.mock.calls[0]?.[1]).toMatchObject({ method: "promethee2", parameters: {} });
    const list = screen.getByRole("list", { name: "Outranking issues" });
    expect(within(list).getAllByRole("listitem").map((li) => li.querySelector("code")?.textContent)).toEqual(["PROMETHEE_CRITERION_INERT"]);
    expect(screen.getByRole("status")).toHaveTextContent("Choose the method “PROMETHEE II (outranking flows)”");
  });
  it("removes the section only after confirmation", () => {
    const { apply } = setup(SECTION, [], "promethee2");
    expect(screen.getByRole("button", { name: "Apply outranking inputs" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Remove all outranking inputs" }));
    expect(apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Remove outranking inputs" }));
    expect(applied(apply)).toEqual([[{ op: "clear_promethee_model" }]]);
  });
});
