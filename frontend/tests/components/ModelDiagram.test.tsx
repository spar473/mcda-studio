import { useState } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { Project, WeightPreview } from "../../src/api/types";
import type { DiagramWeights, TreePresentation } from "../../src/components/ModelTree";
import { PresentationView } from "../../src/components/PresentationView";
import { TreePanel } from "../../src/components/TreePanel";
import { node, projectWith, ratioScale } from "../fixtures";

const linear = { kind: "linear", direction: "increasing", out_of_domain: "error" } as const;
const measured = (id: string, parent: string, order = 0) => node(id, parent, order, { scale: ratioScale, value_function: linear });

function vcLike(extra: Partial<Project> = {}): Project {
  return projectWith([node("team"), measured("founder", "team"), node("coverage", "team", 1), node("market", null, 1), measured("size", "market")], {
    title: "Prioritise startups",
    alternatives: [{ id: "h", name: "Hyades", metadata: {} }, { id: "k", name: "Kura", metadata: {} }],
    weight_profiles: [{ id: "p", name: "Default", method: "swing", judgements: { team: 100, founder: 100 } }],
    ...extra,
  });
}

function Diagram({ project, weights = { status: "off" }, handlers = {} }: { project: Project; weights?: DiagramWeights;
  handlers?: { onEditWeights?: (id: string | null) => void; onEditFunction?: (id: string) => void; onEditAlternative?: (id: string) => void } }) {
  const [presentation, setPresentation] = useState<TreePresentation>({ mode: "canvas", collapsed: new Set() });
  const [selectedId, select] = useState<string | null>(null);
  return <TreePanel project={project} validation={{ issues: [] }} selectedId={selectedId} onSelect={select} busy={false}
    apply={() => Promise.resolve(true)} onAdd={() => Promise.resolve()} presentation={presentation} onPresentation={setPresentation}
    onGoal={vi.fn()} diagram={{ profileId: "p", weights, ...handlers }} />;
}

it("draws goal, objectives, criteria and a separate options column fed by every leaf", () => {
  render(<Diagram project={vcLike()} />);
  const diagram = screen.getByRole("region", { name: "Model diagram" });
  expect(within(diagram).getByRole("button", { name: "Edit goal: Prioritise startups" })).toBeVisible();
  expect(within(diagram).getAllByRole("treeitem")).toHaveLength(5);
  const options = within(diagram).getByRole("region", { name: "Alternatives in the model diagram" });
  expect(within(options).getAllByRole("listitem").map(b => b.textContent)).toEqual(["Hyades", "Kura"]);
  // all structural leaves count, and the options are not presented as tree descendants
  expect(options).toHaveTextContent("scored on all 3 leaf criteria; options are not part of the hierarchy");
  expect(within(screen.getByRole("tree")).queryByText("Hyades")).toBeNull();
});

it("chips route to the existing editors by stable ID; swing chips report missing ratings as presence only", async () => {
  const onEditWeights = vi.fn(), onEditFunction = vi.fn(), onEditAlternative = vi.fn();
  const user = userEvent.setup();
  render(<Diagram project={vcLike()} handlers={{ onEditWeights, onEditFunction, onEditAlternative }} />);
  await user.click(screen.getByRole("button", { name: "Edit swing weights for the top-level objectives" }));
  expect(onEditWeights).toHaveBeenLastCalledWith(null);
  const teamChip = screen.getByRole("button", { name: "Edit swing weights under TEAM" });
  expect(teamChip).toHaveTextContent("Swing · 1 missing"); // coverage has no rating; founder has one
  await user.click(teamChip);
  expect(onEditWeights).toHaveBeenLastCalledWith("team");
  await user.click(screen.getByRole("button", { name: "Edit value function for FOUNDER" }));
  expect(onEditFunction).toHaveBeenLastCalledWith("founder");
  expect(screen.getByRole("button", { name: "Set up measurement for COVERAGE" })).toHaveTextContent("Value fn needed");
  await user.click(screen.getByRole("button", { name: "Edit alternative: Kura" }));
  expect(onEditAlternative).toHaveBeenLastCalledWith("k");
});

it("shows engine weights only when ready, with distinct local and share-of-goal labels", () => {
  const preview = { weights_ready: true, local_weights: { team: 0.6, founder: 0.25, coverage: 0.75, market: 0.4, size: 1 },
    global_weights: { founder: 0.15, coverage: 0.45, size: 0.4 }, path_shares: { team: 0.6, market: 0.4 } } as unknown as WeightPreview;
  const { unmount } = render(<Diagram project={vcLike()} weights={{ status: "ready", preview, context: "profile Default · base model" }} />);
  expect(screen.getByRole("treeitem", { name: /^FOUNDER \(founder\)/ })).toHaveAccessibleName(/local weight 0\.250, global weight 0\.150$/);
  expect(screen.getByRole("treeitem", { name: /^TEAM \(team\)/ })).toHaveAccessibleName(/local weight 0\.600, branch share 0\.600$/);
  expect(screen.getByText(/Engine weights · profile Default · base model/)).toBeVisible();
  unmount();
  render(<Diagram project={vcLike()} weights={{ status: "incomplete" }} />);
  expect(screen.getByText(/once every sibling group has valid swing ratings; none are shown or assumed/)).toBeVisible();
  expect(screen.queryByText(/local 0\./)).toBeNull();
});

it.each([
  [projectWith([], { alternatives: [{ id: "a", name: "A", metadata: {} }] }), /Objectives first\. You already have 1 option\./],
  [projectWith([]), /Objectives first\. Ask what would make this decision a success/],
  [vcLike(), /Ranges before weights\..*1 of 3 leaf criteria still need/],
  [projectWith([node("cost"), measured("price", "cost")]), /Then options\./],
])("structuring hints describe what is present, in objectives-first order", (project, text) => {
  render(<Diagram project={project} />);
  expect(screen.getByRole("note")).toHaveTextContent(text);
});

it("presentation is read-only, labels the live draft and exits on Escape", async () => {
  const onExit = vi.fn();
  const user = userEvent.setup();
  render(<PresentationView project={vcLike()} validation={{ issues: [{ severity: "error", code: "MISSING", message: "Kura has no Size", path: "performances[k,size]" }] }}
    context={{ fingerprint: "abcdef0123456789", configuration: {} as never, resolvedProfileId: "p", profileId: null, scenarioId: null, criterionId: null }}
    fingerprint="abcdef0123456789" dirty presentation={{ mode: "canvas", collapsed: new Set() }} onPresentation={vi.fn()}
    weights={{ status: "off" }} onExit={onExit} />);
  expect(screen.getByRole("heading", { name: "Prioritise startups", level: 2 })).toHaveFocus();
  expect(screen.getByTestId("presentation-context")).toHaveTextContent("Profile Default · base model · unsaved changes");
  expect(screen.queryByRole("button", { name: /Edit goal|Edit value function|Edit swing|Edit alternative|Add/ })).toBeNull();
  expect(screen.getByText(/Kura has no Size/)).toBeVisible();
  await user.click(screen.getByRole("treeitem", { name: /^TEAM/ }));
  await user.keyboard("{Enter}{Delete}{Escape}");
  expect(onExit).toHaveBeenCalledOnce();
  expect(screen.getAllByRole("treeitem")).toHaveLength(5); // Delete never removes anything here
});
