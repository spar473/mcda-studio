import { useState } from "react";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, expect, it, vi } from "vitest";
import { CoverageMatrix } from "../../src/components/CoverageMatrix";
import { buildCoverage, type CoverageCell } from "../../src/model/coverage";
import type { Issue, Project } from "../../src/api/types";
import { node, projectWith, ratioScale } from "../fixtures";

beforeAll(() => { Element.prototype.scrollIntoView = vi.fn(); });

const linear = { kind: "linear", direction: "increasing", out_of_domain: "error" } as const;
function fixture(size = 2) {
  return projectWith(Array.from({ length: size }, (_, i) => node(`c${String(i)}`, null, i, { scale: ratioScale, value_function: linear })), {
    alternatives: Array.from({ length: size }, (_, i) => ({ id: `a${String(i)}`, name: `Option ${String(i)}`, metadata: {} })),
    performances: [{ alternative_id: "a0", criterion_id: "c0", value: 0 }],
  });
}
function Harness({ project = fixture(), issues = [], opened = vi.fn(), issue = vi.fn(), criterion = vi.fn(), selected: initial = null, focusKey = 0 }: {
  project?: Project; issues?: Issue[]; opened?: (cell: CoverageCell) => void; issue?: (i: Issue) => void; criterion?: (id: string) => void;
  selected?: CoverageCell | null; focusKey?: number;
}) {
  const [selected, setSelected] = useState<CoverageCell | null>(initial);
  return <CoverageMatrix index={buildCoverage(project, { issues })} selected={selected} onSelect={setSelected}
    onOpen={opened} onIssue={issue} onCriterion={criterion} onAlternative={vi.fn()} focusKey={focusKey} />;
}
const cell = (a: number, c: number) => screen.getByRole("button", { name: new RegExp(`^Option ${String(a)} \\(a${String(a)}\\) on C${String(c)} \\(c${String(c)}\\):`) });

it("labels presence, attention and setup in text and exposes the engine issue as a link", async () => {
  const user = userEvent.setup(), onIssue = vi.fn();
  const p = fixture(); p.criteria.push(node("unset"));
  const issue: Issue = { severity: "error", code: "OUT_OF_DOMAIN", path: "performances[a0,c0]", message: "Outside the stated range" };
  render(<Harness project={p} issues={[issue]} issue={onIssue} />);
  expect(screen.getByRole("table", { name: "Measurement coverage: alternatives by leaf criteria" })).toBeVisible();
  expect(cell(0, 0)).toHaveTextContent("Entered · needs attention"); expect(cell(0, 0)).toHaveTextContent("Stored: 0");
  expect(cell(0, 1)).toHaveTextContent("Missing");
  expect(screen.getByRole("button", { name: /^Option 0.*UNSET/ })).toHaveTextContent("Missing · setup needed");
  expect(screen.getByTestId("coverage-summary")).toHaveTextContent("1/6 entered; 5 missing; 1 entered cell needs attention");
  expect(screen.getByText(/Evidence provenance not recorded/)).toBeVisible();
  await user.click(cell(0, 0));
  const detail = screen.getByRole("region", { name: "Selected coverage cell" });
  await user.click(within(detail).getByRole("button", { name: /OUT_OF_DOMAIN: Outside/ }));
  expect(onIssue).toHaveBeenCalledExactlyOnceWith(issue);
});

it("opens every pair by stable IDs and uses the existing criterion setup destination", async () => {
  const user = userEvent.setup(), opened = vi.fn(), criterion = vi.fn();
  const p = fixture(); p.criteria.push(node("unset"));
  render(<Harness project={p} opened={opened} criterion={criterion} />);
  for (let a = 0; a < 2; a++) for (let c = 0; c < 2; c++) {
    await user.click(cell(a, c)); expect(opened).toHaveBeenLastCalledWith({ alternativeId: `a${String(a)}`, criterionId: `c${String(c)}` });
  }
  await user.click(screen.getByRole("button", { name: /^Option 0.*UNSET/ }));
  await user.click(screen.getByRole("button", { name: "Open criterion setup" }));
  expect(criterion).toHaveBeenCalledWith("unset");
});

it("uses one cell tab stop, crosses page boundaries with arrows and reaches the final cell", async () => {
  const user = userEvent.setup(); render(<Harness project={fixture(21)} />);
  const table = screen.getByRole("table");
  expect(table.querySelectorAll("tbody button")).toHaveLength(420); // 400 cells + row headings
  expect(table.querySelectorAll(".coverage-cell[tabindex='0']")).toHaveLength(1);
  act(() => { cell(0, 0).focus(); }); await user.keyboard("{End}"); expect(cell(0, 20)).toHaveFocus();
  await user.keyboard("{ArrowLeft}"); expect(cell(0, 19)).toHaveFocus();
  await user.keyboard("{ArrowRight}"); expect(cell(0, 20)).toHaveFocus();
  for (let r = 0; r < 20; r++) await user.keyboard("{ArrowDown}");
  expect(cell(20, 20)).toHaveFocus(); expect(screen.getByRole("group", { name: "Measurement pages" })).toHaveTextContent("Alternatives 21–21 of 21; criteria 21–21 of 21");
  expect(table.querySelectorAll(".coverage-cell")).toHaveLength(1);
  await user.keyboard("{Home}"); expect(cell(20, 0)).toHaveFocus();
  await user.keyboard("{ArrowLeft}"); expect(cell(20, 0)).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "Previous alternatives" }));
  expect(screen.getByTestId("coverage-summary")).toHaveTextContent("1/441 entered; 440 missing");
});

it("reveals the selected cell's pages and restores focus on an explicit return token", () => {
  const p = fixture(41), selected = { alternativeId: "a40", criterionId: "c40" };
  const view = render(<Harness project={p} selected={selected} />);
  expect(cell(40, 40)).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "Previous criteria" }));
  expect(screen.queryByRole("button", { name: /^Option 40.*C40/ })).toBeNull();
  view.rerender(<Harness project={p} selected={selected} focusKey={1} />);
  expect(cell(40, 40)).toHaveFocus();
});

it("explains empty and malformed models without claiming complete inputs", () => {
  const view = render(<Harness project={projectWith([])} />);
  expect(screen.getByTestId("coverage-summary")).toHaveTextContent("Add alternatives/criteria · 0 expected cells");
  expect(screen.queryByRole("table")).toBeNull();
  view.rerender(<Harness project={projectWith([node("a", "b"), node("b", "a")])} />);
  expect(screen.getByText(/Coverage table unavailable/)).toBeVisible();
  view.rerender(<Harness project={fixture(101)} />);
  expect(screen.getByText(/Display performance has been measured up to/)).toBeVisible();
  expect(screen.getByTestId("coverage-summary")).toHaveTextContent("1/10201 entered");
  expect(screen.getByRole("table").querySelectorAll(".coverage-cell")).toHaveLength(400);
});

it("keeps the selected IDs visible when unrelated deletions move them across a page boundary", () => {
  const project = fixture(21), selected = { alternativeId: "a20", criterionId: "c20" };
  const view = render(<Harness project={project} selected={selected} />);
  expect(cell(20, 20)).toHaveAttribute("aria-pressed", "true");
  const next = { ...project, alternatives: project.alternatives.slice(1), criteria: project.criteria.slice(1) };
  view.rerender(<Harness project={next} selected={selected} />);
  expect(cell(20, 20)).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("group", { name: "Measurement pages" })).toHaveTextContent("Alternatives 1–20 of 20; criteria 1–20 of 20");
});
