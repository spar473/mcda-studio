import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TreePanel } from "../../src/components/TreePanel";
import { projectWith, sampleProject } from "../fixtures";

function setup(selectedId: string | null = null, overrides: { busy?: boolean; empty?: boolean } = {}) {
  const sample = sampleProject();
  const project = overrides.empty ? projectWith([]) : projectWith(sample.criteria, { performances: sample.performances });
  const onSelect = vi.fn();
  const onAdd = vi.fn(() => Promise.resolve());
  const apply = vi.fn(() => Promise.resolve(true));
  render(
    <TreePanel
      project={project}
      validation={{ issues: [] }}
      selectedId={selectedId}
      busy={overrides.busy ?? false}
      onSelect={onSelect}
      onAdd={onAdd}
      apply={apply}
    />,
  );
  return { onSelect, onAdd, apply, user: userEvent.setup() };
}

describe("TreePanel", () => {
  it("shows the tree with levels, and arbitrary depth", () => {
    setup();
    const levels = screen.getAllByRole("treeitem").map((el) => Number(el.getAttribute("aria-level")));
    expect(levels).toEqual([1, 2, 2, 1, 2, 3, 2, 1]);
  });

  it("an empty project explains what to do first", () => {
    setup(null, { empty: true });
    expect(screen.getByText("No criteria yet.")).toBeInTheDocument();
    expect(screen.queryByRole("tree")).not.toBeInTheDocument();
  });

  it("toolbar actions that need a selection are disabled without one; adding a top-level objective is not", () => {
    setup();
    expect(screen.getByRole("button", { name: "Add top-level objective" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Add child" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Add sibling" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Remove" })).toBeDisabled();
  });

  it("moves are enabled exactly where they are possible", () => {
    setup("a"); // first top-level item: cannot go up, cannot indent, cannot outdent
    expect(screen.getByRole("button", { name: "Move up" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move down" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Indent" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Outdent" })).toBeDisabled();
  });

  it("while an edit is in flight every editing control is disabled", () => {
    setup("a2", { busy: true });
    for (const name of ["Add top-level objective", "Add child", "Add sibling", "Move up", "Indent", "Outdent", "Remove"]) {
      expect(screen.getByRole("button", { name })).toBeDisabled();
    }
  });

  it("adding a child to an unmeasured item goes straight through", async () => {
    const { onAdd, user } = setup("a2");
    await user.click(screen.getByRole("button", { name: "Add child" }));
    expect(onAdd).toHaveBeenCalledExactlyOnceWith("a2", null, false);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("adding a child to a measured criterion asks first, and cancelling changes nothing", async () => {
    const { onAdd, user } = setup("a1");
    await user.click(screen.getByRole("button", { name: "Add child" }));
    const dialog = screen.getByRole("dialog", { name: "Turn a measured criterion into a group?" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(onAdd).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Add child" }));
    await user.click(screen.getByRole("button", { name: "Discard its data and add the child" }));
    expect(onAdd).toHaveBeenCalledExactlyOnceWith("a1", null, true);
  });

  it("indenting under a measured criterion asks first; under an unmeasured one it does not", async () => {
    const { apply, user } = setup("a2"); // the item above a2 is a1, which is measured
    await user.click(screen.getByRole("button", { name: "Indent" }));
    expect(apply).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Move under a measured criterion?" })).toBeInTheDocument();
  });

  it("removing names what goes with it and only acts after confirmation", async () => {
    const { apply, onSelect, user } = setup("b");
    await user.click(screen.getByRole("button", { name: "Remove" }));
    const dialog = screen.getByRole("dialog", { name: "Remove criterion" });
    expect(dialog).toHaveTextContent("B and its 3 sub-item(s)");
    expect(apply).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Remove" }));
    expect(apply).toHaveBeenCalledExactlyOnceWith([{ op: "remove_criterion", criterion_id: "b" }]);
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it("the measured-data count appears in the removal warning", async () => {
    const { user } = setup("a");
    await user.click(screen.getByRole("button", { name: "Remove" }));
    expect(screen.getByRole("dialog", { name: "Remove criterion" })).toHaveTextContent("1 entered measurement(s)");
  });

  it("clicking an item selects it", async () => {
    const { onSelect, user } = setup();
    await user.click(screen.getByText("B2"));
    expect(onSelect).toHaveBeenCalledWith("b2");
  });
});
