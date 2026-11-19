import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import { EditorScreen } from "../../src/components/EditorScreen";
import { doc, META, node, projectWith, ratioScale } from "../fixtures";

beforeAll(() => { Element.prototype.scrollIntoView = vi.fn(); });
afterEach(() => vi.restoreAllMocks());
const linear = { kind: "linear", direction: "increasing", out_of_domain: "error" } as const;
function fixture() {
  return projectWith([node("group"), node("one", "group", 0, { scale: ratioScale, value_function: linear }),
    node("two", "group", 1, { scale: ratioScale, value_function: linear }), node("unset", null, 1)], {
    alternatives: [{ id: "x", name: "First option", metadata: {} }, { id: "y", name: "Second option", metadata: {} }],
  });
}
async function setup(project = fixture()) {
  let revision = 0;
  vi.spyOn(api, "getProject").mockResolvedValue(doc("original", project));
  vi.spyOn(api, "meta").mockResolvedValue(META);
  vi.spyOn(api, "previewWeights").mockRejectedValue(new Error("Preview unavailable in this fixture"));
  vi.spyOn(api, "previewValueFunction").mockRejectedValue(new Error("Preview unavailable in this fixture"));
  const edit = vi.spyOn(api, "edit").mockImplementation((project, operations) => {
    const next = structuredClone(project);
    for (const op of operations) {
      if (op.op === "set_performance") {
        next.performances = next.performances.filter(p => p.alternative_id !== op.alternative_id || p.criterion_id !== op.criterion_id);
        next.performances.push({ alternative_id: op.alternative_id, criterion_id: op.criterion_id, value: op.value });
      } else if (op.op === "update_criterion") {
        const n = next.criteria.find(n => n.id === op.criterion_id); if (n && op.name) n.name = op.name;
      } else if (op.op === "rename_alternative") {
        const a = next.alternatives.find(a => a.id === op.alternative_id); if (a) a.name = op.name;
      } else if (op.op === "remove_alternative") {
        next.alternatives = next.alternatives.filter(a => a.id !== op.alternative_id);
      } else if (op.op === "remove_criterion") {
        next.criteria = next.criteria.filter(n => n.id !== op.criterion_id);
      } else if (op.op === "add_criterion") {
        next.criteria.push(node("child", op.parent_id ?? null));
      }
    }
    return Promise.resolve(doc(`revision-${String(++revision)}`, next));
  });
  const save = vi.spyOn(api, "saveProject"), evaluate = vi.spyOn(api, "evaluate"), record = vi.spyOn(api, "analysisRecord");
  render(<EditorScreen projectId={project.id} onClose={vi.fn()} onOpenOther={vi.fn()} />);
  await screen.findByRole("table", { name: "Measurement coverage: alternatives by leaf criteria" });
  return { edit, save, evaluate, record, user: userEvent.setup(), before: JSON.stringify(project), project };
}
const cell = (a = "x", c = "one") => screen.getByRole("button", { name: new RegExp(`\\(${a}\\) on .*\\(${c}\\):`) });
const returnButton = () => screen.getByRole("button", { name: "Return to coverage" });

it("opens each existing measurement input by ID and returns focus after an accepted zero edit", async () => {
  const { user, edit, save, evaluate, record } = await setup();
  for (const [a, label] of [["x", "First option"], ["y", "Second option"]]) for (const c of ["one", "two"]) {
    await user.click(cell(a, c));
    expect(screen.getByRole("textbox", { name: `${label ?? ""} on ${c.toUpperCase()}` })).toHaveFocus();
    await user.click(returnButton()); expect(cell(a, c)).toHaveFocus();
  }
  expect(edit).not.toHaveBeenCalled(); expect(save).not.toHaveBeenCalled(); expect(evaluate).not.toHaveBeenCalled(); expect(record).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
  await user.click(cell());
  const input = screen.getByRole("textbox", { name: "First option on ONE" });
  await user.type(input, "0{Enter}");
  await waitFor(() => expect(edit).toHaveBeenCalledTimes(1));
  await user.click(returnButton()); expect(cell()).toHaveFocus();
  expect(cell()).toHaveTextContent("Entered");
  expect(screen.getByTestId("coverage-summary")).toHaveTextContent("1/6 entered; 5 missing");
  await user.click(screen.getByRole("button", { name: "Undo" }));
  expect(screen.getByTestId("coverage-summary")).toHaveTextContent("0/6 entered; 6 missing");
  await user.click(screen.getByRole("button", { name: "Redo" }));
  expect(screen.getByTestId("coverage-summary")).toHaveTextContent("1/6 entered; 5 missing");
  expect(edit).toHaveBeenCalledTimes(1); expect(save).not.toHaveBeenCalled(); expect(evaluate).not.toHaveBeenCalled(); expect(record).not.toHaveBeenCalled();
});

it("takes an unconfigured criterion to the existing Inspector and restores the exact cell", async () => {
  const { user, edit } = await setup();
  await user.click(cell("y", "unset"));
  expect(screen.getByLabelText("Measurement type")).toHaveFocus();
  expect(screen.getByLabelText("Name", { exact: true })).toHaveValue("UNSET");
  await user.click(returnButton()); expect(cell("y", "unset")).toHaveFocus();
  expect(edit).not.toHaveBeenCalled();
});

it("preserves selection and focus by ID through criterion and alternative renames", async () => {
  const { user } = await setup();
  await user.click(cell()); await user.click(returnButton());
  const table = screen.getByRole("table", { name: "Measurement coverage: alternatives by leaf criteria" });
  await user.click(within(table).getByRole("button", { name: "ONE" }));
  const name = screen.getByLabelText("Name", { exact: true });
  await user.clear(name); await user.type(name, "Renamed criterion{Enter}");
  await waitFor(() => expect(cell()).toHaveAccessibleName(/Renamed criterion/));
  expect(cell()).toHaveAttribute("aria-pressed", "true");
  await user.click(within(table).getByRole("button", { name: "Edit coverage alternative First option (x)" }));
  const alternative = screen.getByLabelText("Name of alternative First option");
  await user.clear(alternative); await user.type(alternative, "Renamed alternative{Enter}");
  await screen.findByLabelText("Name of alternative Renamed alternative");
  await user.click(returnButton());
  expect(cell()).toHaveFocus(); expect(cell()).toHaveAccessibleName(/Renamed alternative.*Renamed criterion/);
});

it.each(["alternative", "criterion", "branch"])("clears selection after accepted %s removal/conversion and does not resurrect it on undo", async kind => {
  const { user, edit } = await setup();
  await user.click(cell()); await user.click(returnButton());
  if (kind === "alternative") {
    await user.click(screen.getByRole("tab", { name: "Alternatives" }));
    await user.click(screen.getByRole("button", { name: "Remove First option" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Remove" }));
    await screen.findByRole("button", { name: "Remove Second option" });
    await waitFor(() => expect(screen.queryByRole("button", { name: "Return to coverage" })).toBeNull());
    await user.click(screen.getByRole("tab", { name: "Model" }));
  } else {
    await user.click(screen.getByRole("button", { name: kind === "branch" ? "Add child" : "Remove" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: kind === "branch" ? "Discard its data and add the child" : "Remove" }));
  }
  await waitFor(() => expect(edit).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(screen.queryByRole("region", { name: "Selected coverage cell" })).toBeNull());
  await user.click(screen.getByRole("button", { name: "Undo" }));
  expect(cell()).toHaveAttribute("aria-pressed", "false");
  expect(screen.queryByRole("region", { name: "Selected coverage cell" })).toBeNull();
});

it("keyboard selection, collapsing, paging and editor navigation cannot edit, save or evaluate", async () => {
  const project = fixture();
  for (let i = 0; i < 20; i++) {
    project.alternatives.push({ id: `more${String(i)}`, name: `Option ${String(i)}`, metadata: {} });
    project.criteria.push(node(`more${String(i)}`, null, i + 2, { scale: ratioScale, value_function: linear }));
  }
  const { user, edit, save, evaluate, record, before } = await setup(project);
  act(() => { cell().focus(); }); await user.keyboard("{End}{ArrowDown}{Home}");
  await user.click(screen.getByRole("button", { name: "Collapse GROUP" }));
  await user.click(screen.getByRole("button", { name: "Next alternatives" }));
  await user.click(screen.getByRole("button", { name: "Next criteria" }));
  const target = screen.getByRole("button", { name: /\(more19\) on .*\(more19\):/ });
  await user.click(target); await user.click(returnButton());
  expect(screen.getByRole("button", { name: /\(more19\) on .*\(more19\):/ })).toHaveFocus();
  expect(edit).not.toHaveBeenCalled(); expect(save).not.toHaveBeenCalled(); expect(evaluate).not.toHaveBeenCalled(); expect(record).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
  expect(screen.getByTestId("save-state")).toHaveTextContent("All changes saved");
  expect(JSON.stringify(project)).toBe(before);
});

it("clears an externally removed focused pair without transferring it to the next row", async () => {
  // The store response is accepted while the canvas still owns focus.
  const { user, edit } = await setup();
  await user.click(cell()); await user.click(returnButton());
  edit.mockImplementationOnce(project => Promise.resolve(doc("removed", { ...project, criteria: project.criteria.filter(n => n.id !== "one") })));
  const name = screen.getByLabelText("Name", { exact: true });
  await user.click(name); await user.clear(name); await user.type(name, "Rename{Enter}");
  await waitFor(() => expect(screen.queryByRole("button", { name: /\(x\) on .*\(one\):/ })).toBeNull());
  expect(cell("x", "two")).toHaveAttribute("aria-pressed", "false");
});

it("does not steal focus back to the opening cell after another measurement is edited", async () => {
  const { user, edit } = await setup();
  await user.click(cell());
  const opening = screen.getByLabelText("First option on ONE"), other = screen.getByLabelText("Second option on TWO");
  await user.click(other); await user.type(other, "3{Enter}");
  await waitFor(() => expect(edit).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(other).not.toBeDisabled());
  expect(opening).not.toHaveFocus();
  expect(other).toHaveValue("3");
});
