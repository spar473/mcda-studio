import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { Operation, Project, SmaaModel } from "../../src/api/types";
import { UncertaintyPanel } from "../../src/components/UncertaintyPanel";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import { node, projectWith, ratioScale } from "../fixtures";

const vf = { kind: "linear" as const, direction: "increasing" as const, out_of_domain: "error" as const };
const labels = { type: "ordinal" as const, unit: null, lower: null, upper: null, anchor_mode: "fixed" as const, labels: ["low", "high"] };

function setup(smaa: SmaaModel | null = null, issues: { code: string; path: string }[] = []) {
  const project: Project = projectWith([
    node("cost", null, 0, { name: "Cost", scale: ratioScale, value_function: vf }),
    node("looks", null, 1, { name: "Looks", scale: labels, value_function: { kind: "qualitative", mapping: { low: 0, high: 1 } } }),
  ], {
    alternatives: [{ id: "a", name: "Alpha", metadata: {} }, { id: "b", name: "Beta", metadata: {} }],
    analysis: { method: "mavt", scenario_id: null, weight_profile_id: null, parameters: {} },
    ...(smaa ? { smaa } : {}),
  });
  vi.spyOn(api, "validateAnalysis").mockImplementation((_p, configuration) => Promise.resolve({
    project_fingerprint: "fp", configuration, scenario_id: null, weight_profile_id: null,
    validation: { issues: issues.map((i) => ({ severity: "error" as const, message: i.code, ...i })) },
  }));
  const apply = vi.fn<(ops: Operation[]) => Promise<boolean>>(() => Promise.resolve(true));
  render(<UncertaintyPanel project={project} context={resolveContext(project, "fp", BASE_SELECTION)} busy={false} apply={apply}/>);
  return { apply };
}
const applied = (apply: ReturnType<typeof setup>["apply"]) => apply.mock.calls.map((c) => c[0]);
async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(125); }); }
beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

describe("the Uncertainty editor", () => {
  it("states distributions, a shared draw and weight intervals, applied as one edit", () => {
    const { apply } = setup();
    fireEvent.click(screen.getByRole("button", { name: "Add distribution" }));
    fireEvent.change(screen.getByLabelText("Lower for Alpha on Cost"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Upper for Alpha on Cost"), { target: { value: "6" } });
    fireEvent.change(screen.getByLabelText("New uncertain alternative"), { target: { value: "b" } });
    fireEvent.click(screen.getByRole("button", { name: "Add distribution" }));
    fireEvent.change(screen.getByLabelText("Distribution for Beta on Cost"), { target: { value: "discrete" } });
    fireEvent.change(screen.getByLabelText("Outcomes (OUTCOME=P, …) for Beta on Cost"), { target: { value: "3=0.5, 5=0.5" } });
    fireEvent.change(screen.getByLabelText("Shared draw for Alpha on Cost"), { target: { value: "Supplier A" } });
    fireEvent.change(screen.getByLabelText("Shared draw for Beta on Cost"), { target: { value: "supplier a" } });
    fireEvent.change(screen.getByLabelText("Weight uncertainty under Top level"), { target: { value: "rating_intervals" } });
    fireEvent.change(screen.getByLabelText("Lower rating for Cost"), { target: { value: "50" } });
    fireEvent.change(screen.getByLabelText("Upper rating for Cost"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("Lower rating for Looks"), { target: { value: "20" } });
    fireEvent.change(screen.getByLabelText("Upper rating for Looks"), { target: { value: "40" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply uncertainty" }));
    expect(applied(apply)).toEqual([[{ op: "set_smaa_model", smaa: {
      dependence: "independent",
      cells: [
        { alternative_id: "a", criterion_id: "cost", distribution: { kind: "uniform", lower: 2, upper: 6 } },
        { alternative_id: "b", criterion_id: "cost", distribution: { kind: "discrete", values: [3, 5], probabilities: [0.5, 0.5] } },
      ],
      groups: [{ parent_id: null, kind: "rating_intervals", intervals: { cost: [50, 100], looks: [20, 40] } }],
      shared_draws: [{ id: "supplier_a", cells: [{ alternative_id: "a", criterion_id: "cost" }, { alternative_id: "b", criterion_id: "cost" }] }],
    } }]]);
  });
  it("offers only a categorical distribution for a labelled scale", () => {
    setup();
    fireEvent.change(screen.getByLabelText("New uncertain criterion"), { target: { value: "looks" } });
    fireEvent.click(screen.getByRole("button", { name: "Add distribution" }));
    const kinds = within(screen.getByLabelText("Distribution for Alpha on Looks")).getAllByRole("option").map((o) => o.textContent);
    expect(kinds).toEqual(["Categorical"]);
  });
  it("refuses an entry that is not a number and applies nothing", () => {
    const { apply } = setup();
    fireEvent.click(screen.getByRole("button", { name: "Add distribution" }));
    fireEvent.change(screen.getByLabelText("Lower for Alpha on Cost"), { target: { value: "low" } });
    expect(screen.getByRole("alert")).toHaveTextContent("The lower bound for Alpha on Cost must be a number.");
    expect(screen.getByRole("button", { name: "Apply uncertainty" })).toBeDisabled();
    expect(apply).not.toHaveBeenCalled();
  });
  it("loads the saved section, removes it only after confirmation, and shows only its own issues", async () => {
    const saved: SmaaModel = { dependence: "independent", shared_draws: [], groups: [],
      cells: [{ alternative_id: "a", criterion_id: "cost", distribution: { kind: "triangular", lower: 1, mode: 2, upper: 4 } }] };
    const { apply } = setup(saved, [{ code: "DISTRIBUTION_OUTSIDE_DOMAIN", path: "smaa.cells[a,cost]" }, { code: "MISSING_JUDGEMENT", path: "weight_profiles[d].judgements" }]);
    expect(screen.getByLabelText("Mode for Alpha on Cost")).toHaveValue("2");
    expect(screen.getByRole("button", { name: "Apply uncertainty" })).toBeDisabled(); // nothing changed yet
    await settle();
    expect(vi.mocked(api.validateAnalysis).mock.calls[0]?.[1]).toMatchObject({ method: "smaa2", parameters: {} });
    const list = screen.getByRole("list", { name: "Uncertainty issues" });
    expect(list).toHaveTextContent("DISTRIBUTION_OUTSIDE_DOMAIN");
    expect(list).not.toHaveTextContent("MISSING_JUDGEMENT");
    fireEvent.click(screen.getByRole("button", { name: "Remove all uncertainty" }));
    expect(apply).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Remove uncertainty" }));
    expect(applied(apply)).toEqual([[{ op: "clear_smaa_model" }]]);
  });
});
