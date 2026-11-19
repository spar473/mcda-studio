import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { Operation, Project, SortingModel } from "../../src/api/types";
import { ClassesPanel } from "../../src/components/ClassesPanel";
import { BASE_SELECTION, resolveContext } from "../../src/state/analysisContext";
import { node, projectWith } from "../fixtures";

const SAVED: SortingModel = {
  classes: [
    { id: "go", name: "Go", description: "", lower_boundary: 0.6 },
    { id: "hold", name: "Hold", description: "", lower_boundary: 0.3 },
    { id: "stop", name: "Stop", description: "", lower_boundary: null },
  ],
  audit: null,
};

function setup(sorting: SortingModel | null = SAVED, issues: { code: string; path: string }[] = []) {
  const project: Project = projectWith([node("cost")], {
    analysis: { method: "mavt", scenario_id: null, weight_profile_id: null, parameters: {} },
    ...(sorting ? { sorting } : {}),
  });
  const context = resolveContext(project, "fp", BASE_SELECTION);
  vi.spyOn(api, "validateAnalysis").mockImplementation((_p, configuration) => Promise.resolve({
    project_fingerprint: "fp", configuration, scenario_id: null, weight_profile_id: null,
    validation: { issues: issues.map((i) => ({ severity: "error" as const, message: i.code, ...i })) },
  }));
  const apply = vi.fn<(ops: Operation[]) => Promise<boolean>>(() => Promise.resolve(true));
  render(<ClassesPanel project={project} context={context} busy={false} apply={apply}/>);
  return { apply };
}
const applied = (apply: ReturnType<typeof setup>["apply"]) => apply.mock.calls.map((c) => c[0]);
async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(125); }); }
beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

describe("the Classes editor", () => {
  it("applies a draft as one sorting-model edit, with numeric boundaries and none on the lowest class", () => {
    const { apply } = setup(null);
    fireEvent.click(screen.getByRole("button", { name: "Add class" }));
    fireEvent.click(screen.getByRole("button", { name: "Add class" }));
    fireEvent.change(screen.getByLabelText("Class 1 name"), { target: { value: "Qualified" } });
    fireEvent.change(screen.getByLabelText("Lower boundary of Qualified"), { target: { value: "0.7" } });
    fireEvent.change(screen.getByLabelText("Class 2 name"), { target: { value: "Other" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply classes" }));
    expect(applied(apply)).toEqual([[{ op: "set_sorting_model", sorting: {
      classes: [
        { id: "new_class", name: "Qualified", description: "", lower_boundary: 0.7 },
        { id: "new_class_2", name: "Other", description: "", lower_boundary: null },
      ],
      audit: null,
    } }]]);
  });
  it("moves a class with its boundary and never re-sorts boundaries", () => {
    const { apply } = setup();
    fireEvent.click(screen.getByRole("button", { name: "Move Hold up" }));
    const rows = within(screen.getByRole("list", { name: "Class list" })).getAllByRole("listitem");
    expect(rows.map((r) => r.getAttribute("data-class-id"))).toEqual(["hold", "go", "stop"]);
    fireEvent.click(screen.getByRole("button", { name: "Apply classes" }));
    expect(applied(apply)[0]?.[0]).toMatchObject({ sorting: { classes: [
      { id: "hold", lower_boundary: 0.3 }, { id: "go", lower_boundary: 0.6 }, { id: "stop", lower_boundary: null },
    ] } });
  });
  it("refuses a boundary that is not a number and applies nothing", () => {
    const { apply } = setup();
    fireEvent.change(screen.getByLabelText("Lower boundary of Go"), { target: { value: "high" } });
    expect(screen.getByRole("alert")).toHaveTextContent("The boundary of Go must be a number.");
    expect(screen.getByRole("button", { name: "Apply classes" })).toBeDisabled();
    expect(apply).not.toHaveBeenCalled();
  });
  it("cancels a draft back to the saved classes, and applies nothing unchanged", () => {
    setup();
    expect(screen.getByRole("button", { name: "Apply classes" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Class 1 name"), { target: { value: "Proceed" } });
    expect(screen.getByRole("button", { name: "Apply classes" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Cancel changes" }));
    expect(screen.getByLabelText("Class 1 name")).toHaveValue("Go");
  });
  it("sets an audit sample below a chosen class", () => {
    const { apply } = setup();
    fireEvent.click(screen.getByLabelText("Audit sample"));
    fireEvent.change(screen.getByLabelText("Audit cut-off class"), { target: { value: "hold" } });
    fireEvent.change(screen.getByLabelText("Audit sample size"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Audit seed"), { target: { value: "9" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply classes" }));
    expect(applied(apply)[0]?.[0]).toMatchObject({ sorting: { audit: { below_class_id: "hold", sample_size: 2, seed: 9 } } });
  });
  it("removes every class only after confirmation", () => {
    const { apply } = setup();
    fireEvent.click(screen.getByRole("button", { name: "Remove all classes" }));
    expect(apply).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Remove classes" }));
    expect(applied(apply)).toEqual([[{ op: "clear_sorting_model" }]]);
  });
  it("shows only the sorting issues from the engine, checked under the sorting method", async () => {
    setup(SAVED, [{ code: "BOUNDARIES_NOT_DECREASING", path: "sorting.classes[hold].lower_boundary" }, { code: "MISSING_JUDGEMENT", path: "weight_profiles[d].judgements" }]);
    await settle();
    expect(vi.mocked(api.validateAnalysis).mock.calls[0]?.[1]).toMatchObject({ method: "mavt_sorting", parameters: {} });
    const list = screen.getByRole("list", { name: "Class issues" });
    expect(list).toHaveTextContent("BOUNDARIES_NOT_DECREASING");
    expect(list).not.toHaveTextContent("MISSING_JUDGEMENT");
  });
});
