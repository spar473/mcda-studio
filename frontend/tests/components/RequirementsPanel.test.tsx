import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import type { FeasibilityResult, Operation, Project, Requirement } from "../../src/api/types";
import { RequirementsPanel } from "../../src/components/RequirementsPanel";
import { node, ordinalScale, projectWith, ratioScale } from "../fixtures";

const LABEL = "feasibility: each requirement is tested on its own measurement; no score offsets a failure";
const PRICE: Requirement = { kind: "bound", id: "price", name: "Price cap", criterion_id: "price", unit: "kg", minimum: null,
  minimum_inclusive: true, maximum: 5, maximum_inclusive: true, rationale: "" };

function result(project: Project): FeasibilityResult {
  const requirements = project.requirements ?? [];
  return { label: LABEL, project_id: project.id, project_fingerprint: "fp", requirements, diagnostics: [],
    alternatives: project.alternatives.map((a) => ({ alternative_id: a.id, name: a.name, status: "pass" as const, failed: [], unknown: [],
      checks: requirements.map((r) => ({ requirement_id: r.id, status: "pass" as const, measurement: 1, reason: "1 kg is within the limits" })) })),
    summary: requirements.map((r) => ({ requirement_id: r.id, name: r.name, criterion_id: r.criterion_id, passed: 2, failed: 0, unknown: 0 })) };
}

function setup(requirements: Requirement[] | null = null) {
  const project = projectWith([
    node("price", null, 0, { name: "Price", scale: ratioScale }),
    node("grade", null, 1, { name: "Grade", scale: ordinalScale }),
  ], {
    alternatives: [{ id: "a", name: "Alpha", metadata: {} }, { id: "b", name: "Beta", metadata: {} }],
    ...(requirements ? { requirements } : {}),
  });
  const spy = vi.spyOn(api, "checkFeasibility").mockImplementation((p) => Promise.resolve(result(p)));
  const apply = vi.fn<(ops: Operation[]) => Promise<boolean>>(() => Promise.resolve(true));
  render(<RequirementsPanel project={project} busy={false} apply={apply}/>);
  return { apply, spy };
}
async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(130); }); }
beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

describe("the Requirements tab", () => {
  it("adds a bound in the leaf's own unit, checks the draft live in Python and applies it as one change", async () => {
    const { apply, spy } = setup();
    expect(screen.getByText("No requirements yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply requirements" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Add requirement" }));
    const row = screen.getByRole("group", { name: "Requirement Price requirement" });
    expect(within(row).getByLabelText("Unit of Price requirement")).toHaveValue("kg");
    expect(row).toHaveTextContent("the criterion is measured in kg");
    fireEvent.change(within(row).getByLabelText("Maximum of Price requirement"), { target: { value: "5" } });
    fireEvent.click(within(row).getByLabelText("Maximum of Price requirement itself passes"));
    await settle();
    expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ requirements: [expect.objectContaining({
      kind: "bound", criterion_id: "price", unit: "kg", minimum: null, maximum: 5, maximum_inclusive: false })] }), expect.any(AbortSignal));
    expect(screen.getByRole("table", { name: "Feasibility by alternative" })).toHaveTextContent("Alpha");
    fireEvent.click(screen.getByRole("button", { name: "Apply requirements" }));
    expect(apply).toHaveBeenCalledWith([{ op: "set_requirements", requirements: [{ kind: "bound", id: "price", name: "Price requirement",
      criterion_id: "price", rationale: "", unit: "kg", minimum: null, minimum_inclusive: true, maximum: 5, maximum_inclusive: false }] }]);
  });
  it("writes an explicit label set from the ordinal helper", async () => {
    const { apply } = setup();
    fireEvent.change(screen.getByLabelText("New requirement criterion"), { target: { value: "grade" } });
    fireEvent.click(screen.getByRole("button", { name: "Add requirement" }));
    fireEvent.click(screen.getByRole("button", { name: "At least Mid" }));
    expect(screen.getByLabelText("Allow Low for Grade requirement")).not.toBeChecked();
    expect(screen.getByLabelText("Allow Mid for Grade requirement")).toBeChecked();
    expect(screen.getByLabelText("Allow High for Grade requirement")).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "At most Mid" }));
    expect(screen.getByLabelText("Allow Low for Grade requirement")).toBeChecked();
    expect(screen.getByLabelText("Allow High for Grade requirement")).not.toBeChecked();
    fireEvent.click(screen.getByLabelText("Allow Low for Grade requirement"));
    await settle();
    fireEvent.click(screen.getByRole("button", { name: "Apply requirements" }));
    expect(apply).toHaveBeenCalledWith([{ op: "set_requirements", requirements: [expect.objectContaining({ kind: "labels", allowed: ["Mid"] })] }]);
  });
  it("refuses an unreadable limit before anything is sent", async () => {
    const { apply, spy } = setup([PRICE]);
    await settle();
    expect(spy).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText("Maximum of Price cap"), { target: { value: "five" } });
    expect(screen.getByRole("alert")).toHaveTextContent("The maximum of Price cap must be a number.");
    expect(screen.getByRole("button", { name: "Apply requirements" })).toBeDisabled();
    await settle();
    expect(spy).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Cancel changes" }));
    expect(screen.getByLabelText("Maximum of Price cap")).toHaveValue("5");
    expect(apply).not.toHaveBeenCalled();
  });
  it("removes every requirement only after confirmation", () => {
    const { apply } = setup([PRICE]);
    fireEvent.click(screen.getByRole("button", { name: "Remove all requirements" }));
    expect(apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Remove requirements" }));
    expect(apply).toHaveBeenCalledWith([{ op: "clear_requirements" }]);
  });
});
