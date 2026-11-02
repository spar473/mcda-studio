import { useState } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { TreePanel } from "../../src/components/TreePanel";
import { node, projectWith } from "../fixtures";
import type { TreePresentation } from "../../src/components/ModelTree";

function Harness({ failed = false }: { failed?: boolean }) {
  const [selectedId, select] = useState<string | null>(null);
  const [presentation, setPresentation] = useState<TreePresentation>({ mode: "canvas", collapsed: new Set() });
  const [criteria, setCriteria] = useState([node("parent"), node("one", "parent", 0, { name: "Same" }), node("two", "parent", 1, { name: "Same" })]);
  const [edited, setEdited] = useState("");
  return <><TreePanel project={projectWith(criteria)} validation={{ issues: [] }} selectedId={selectedId} onSelect={select}
    busy={false} apply={ops => { if (failed) return Promise.resolve(false); if (ops[0]?.op === "remove_criterion") setCriteria(c => c.filter(n => n.id !== (ops[0] as { criterion_id: string }).criterion_id)); return Promise.resolve(true); }}
    onAdd={() => Promise.resolve()} presentation={presentation} onPresentation={setPresentation}
    onEdit={setEdited} onGoal={() => setEdited("goal")} />
    <output aria-label="Selection">{selectedId ?? "none"}</output><output aria-label="Editing">{edited}</output>
    <button onClick={() => select("two")}>External selection</button></>;
}

it("distinguishes duplicate names by ID and offers an explicit existing-editor destination", async () => {
  const user = userEvent.setup(); render(<Harness />);
  await user.click(within(screen.getByRole("treeitem", { name: /Same \(two\)/ })).getByRole("button"));
  expect(screen.getByLabelText("Selection")).toHaveTextContent("two");
  await user.click(screen.getByRole("button", { name: "Edit selected item" }));
  expect(screen.getByLabelText("Editing")).toHaveTextContent("two");
});

it("navigates with arrows/Home/End/Space and collapses a selected descendant to its parent", async () => {
  const user = userEvent.setup(); render(<Harness />);
  const parent = screen.getByRole("treeitem", { name: /PARENT \(parent\)/ });
  parent.focus(); await user.keyboard("{ArrowRight}");
  expect(screen.getByRole("treeitem", { name: /Same \(one\)/ })).toHaveFocus();
  await user.keyboard("{End} ");
  expect(screen.getByLabelText("Selection")).toHaveTextContent("two");
  await user.click(screen.getByRole("button", { name: "Collapse PARENT" }));
  expect(parent).toHaveFocus(); expect(parent).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByLabelText("Selection")).toHaveTextContent("parent");
  await user.keyboard("{ArrowRight}{End}{Home}"); expect(parent).toHaveFocus();
});

it("external selection reveals collapsed ancestors without transferring identity", async () => {
  const user = userEvent.setup(); render(<Harness />);
  await user.click(screen.getByRole("button", { name: "Collapse PARENT" }));
  expect(screen.getAllByRole("treeitem")).toHaveLength(1);
  await user.click(screen.getByRole("button", { name: "External selection" }));
  expect(screen.getByRole("treeitem", { name: /Same \(two\)/ })).toHaveAttribute("aria-selected", "true");
  expect(screen.getAllByRole("treeitem")).toHaveLength(3);
});

it("mode switching changes presentation, preserving selection and collapsed state", async () => {
  const user = userEvent.setup(); render(<Harness />);
  await user.click(within(screen.getByRole("treeitem", { name: /PARENT \(parent\)/ })).getByRole("button", { name: /Objective/ }));
  await user.click(screen.getByRole("button", { name: "Collapse PARENT" }));
  await user.click(screen.getByRole("button", { name: "Outline" }));
  expect(screen.getByRole("button", { name: "Outline" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getAllByRole("treeitem")).toHaveLength(1);
  expect(screen.getByLabelText("Selection")).toHaveTextContent("parent");
});

it("failed deletion keeps the selected node; cancelled deletion never removes it", async () => {
  const user = userEvent.setup(); render(<Harness failed />);
  await user.click(within(screen.getByRole("treeitem", { name: /Same \(two\)/ })).getByRole("button"));
  await user.click(screen.getByRole("button", { name: "Remove" }));
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.getByLabelText("Selection")).toHaveTextContent("two");
  await user.click(screen.getByRole("button", { name: "Remove" }));
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Remove" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(screen.getByRole("treeitem", { name: /Same \(two\)/ })).toHaveAttribute("aria-selected", "true");
});

it("malformed incoming nodes stay visible in a labelled nonrecursive fallback", () => {
  render(<TreePanel project={projectWith([node("a", "b"), node("b", "a"), node("a")])}
    validation={{ issues: [] }} selectedId={null} busy={false} onSelect={vi.fn()} onAdd={vi.fn()} apply={vi.fn()} />);
  expect(screen.getByRole("region", { name: "Structure cannot be drawn safely" })).toBeVisible();
  expect(within(screen.getByRole("list", { name: "Incoming criteria (flat fallback)" })).getAllByRole("listitem")).toHaveLength(3);
  expect(screen.getByRole("button", { name: "Add top-level objective" })).toBeDisabled();
});

it("Enter edits the focused ID and Delete confirms that ID even before pointer selection", async () => {
  const user = userEvent.setup(); render(<Harness failed />);
  const second = screen.getByRole("treeitem", { name: /Same \(two\)/ });
  second.focus(); await user.keyboard("{Enter}");
  expect(screen.getByLabelText("Selection")).toHaveTextContent("two");
  expect(screen.getByLabelText("Editing")).toHaveTextContent("two");
  const first = screen.getByRole("treeitem", { name: /Same \(one\)/ });
  first.focus(); await user.keyboard("{Delete}");
  expect(screen.getByRole("dialog")).toBeVisible();
  expect(screen.getByLabelText("Selection")).toHaveTextContent("one");
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(first).toHaveFocus();
});
