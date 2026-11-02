import { expect, it } from "vitest";
import { ancestors, descendantIds, indexTree, treeIssues, visibleRows } from "../../src/model/visibleTree";
import { node } from "../fixtures";

it("orders siblings by order then original position, preserving stable identities", () => {
  const index = indexTree([node("b", null, 1), node("a"), node("a2", "a", 1), node("a1", "a")]);
  expect(index.rows.map(r => [r.node.id, r.depth, r.position, r.siblings])).toEqual([
    ["a", 1, 1, 2], ["a1", 2, 1, 2], ["a2", 2, 2, 2], ["b", 1, 2, 2],
  ]);
});

it("draws 10,000 deep nodes iteratively, without silently dropping a node", () => {
  const index = indexTree(Array.from({ length: 10000 }, (_, i) => node(`n${String(i)}`, i ? `n${String(i - 1)}` : null)));
  expect(index.errors).toEqual([]);
  expect(index.rows.at(-1)?.depth).toBe(10000);
  expect(ancestors(index, "n9999").size).toBe(9999);
  expect(descendantIds(index, "n0").size).toBe(10000);
  expect(visibleRows(index, new Set(["n0"]), null).rows).toHaveLength(1);
});

it.each([
  [node("duplicate"), node("duplicate")],
  [node("orphan", "missing")],
  [node("a", "b"), node("b", "a")],
  [node("self", "self")],
])("detects malformed structure without recursion", (...nodes) => {
  expect(indexTree(nodes).errors.length).toBeGreaterThan(0);
});

it("reveals ancestors of external selection and removes collapsed IDs that no longer exist", () => {
  const index = indexTree([node("a"), node("b", "a"), node("c", "b")]);
  const view = visibleRows(index, new Set(["a", "b", "gone"]), "c");
  expect(view.closed.size).toBe(0);
  expect(view.rows).toHaveLength(3);
});

it("aggregates only actual engine issues and does not invent a validity judgement", () => {
  const index = indexTree([node("a"), node("leaf", "a")]);
  const counts = treeIssues(index, { issues: [
    { severity: "error", code: "MISSING_MEASUREMENT", message: "Missing", path: "performances[x,leaf]" },
    { severity: "warning", code: "LOCAL_ANCHORS", message: "Review", path: "criteria[leaf]" },
    { severity: "error", code: "NO_ALTERNATIVES", message: "Add alternatives", path: "" },
  ] });
  expect(counts.get("a")).toEqual({ errors: 1, warnings: 1 });
  expect(counts.get("leaf")).toEqual({ errors: 1, warnings: 1 });
});
