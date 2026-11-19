import { expect, it } from "vitest";
import { diagramLayout, leafIds, swingRatings } from "../../src/model/diagram";
import { indexTree, visibleRows } from "../../src/model/visibleTree";
import { node, projectWith } from "../fixtures";

const tree = () => indexTree([
  node("team"), node("founder", "team"), node("coverage", "team", 1),
  node("market", null, 1), node("size", "market"), node("growth", "market", 1), node("solo", null, 2),
]);
const spans = (layout: ReturnType<typeof diagramLayout>) =>
  Object.fromEntries([...layout.cells].map(([id, c]) => [id, [c.column, c.rowStart, c.rowEnd]]));

it("gives each visible leaf its own row and centres each branch over its descendants", () => {
  const layout = diagramLayout(tree().rows);
  expect(layout).toMatchObject({ rowCount: 5, columns: 2 });
  expect(spans(layout)).toEqual({
    team: [1, 1, 3], founder: [2, 1, 2], coverage: [2, 2, 3],
    market: [1, 3, 5], size: [2, 3, 4], growth: [2, 4, 5], solo: [1, 5, 6],
  });
});

it("a collapsed branch becomes one terminal row and its hidden children are not placed", () => {
  const index = tree();
  const layout = diagramLayout(visibleRows(index, new Set(["team"]), null).rows);
  expect(spans(layout)).toEqual({ team: [1, 1, 2], market: [1, 2, 4], size: [2, 2, 3], growth: [2, 3, 4], solo: [1, 4, 5] });
  // presence counts still use every structural leaf, collapsed or not
  expect(leafIds(index)).toEqual(["founder", "coverage", "size", "growth", "solo"]);
});

it("lays out 10,000 nested levels iteratively", () => {
  const index = indexTree(Array.from({ length: 10000 }, (_, i) => node(`n${String(i)}`, i ? `n${String(i - 1)}` : null)));
  const layout = diagramLayout(index.rows);
  expect(layout).toMatchObject({ rowCount: 1, columns: 10000 });
  expect(layout.cells.get("n0")).toEqual({ column: 1, rowStart: 1, rowEnd: 2 });
});

it("reports missing swing ratings as presence only; an only child needs none; no profile is explicit", () => {
  const criteria = [node("a"), node("b", null, 1), node("only", "a"), node("c", null, 2)];
  const index = indexTree(criteria);
  const project = projectWith(criteria, { weight_profiles: [{ id: "p", name: "P", method: "swing", judgements: { a: 100, b: 0 } }] });
  expect(swingRatings(project, index, "p", null)).toEqual({ children: 3, missing: 1, profile: true });
  expect(swingRatings(project, index, "p", "a")).toEqual({ children: 1, missing: 0, profile: true });
  expect(swingRatings(project, index, "absent", null)).toEqual({ children: 3, missing: 3, profile: false });
});
