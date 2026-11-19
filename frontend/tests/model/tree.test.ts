import { describe, expect, it } from "vitest";
import {
  addingChildDiscards,
  buildTree,
  childrenOf,
  flatten,
  isLeaf,
  leaves,
  maxDepth,
  pathNames,
  planMove,
  subtreeIds,
} from "../../src/model/tree";
import { node, sampleProject } from "../fixtures";

const p = sampleProject();
const ids = (xs: { node: { id: string } }[]) => xs.map((t) => t.node.id);

describe("tree description", () => {
  it("nests in sibling order with 1-based depth", () => {
    const flat = flatten(buildTree(p.criteria));
    expect(ids(flat)).toEqual(["a", "a1", "a2", "b", "b1", "b1x", "b2", "c"]);
    expect(flat.map((t) => t.depth)).toEqual([1, 2, 2, 1, 2, 3, 2, 1]);
  });

  it("orders by `order`, then by list position, whatever the list order", () => {
    const shuffled = [node("z", null, 5), node("y", null, 1), node("w", null, 1)];
    expect(childrenOf(shuffled, null).map((n) => n.id)).toEqual(["y", "w", "z"]);
  });

  it("never loops or repeats on a corrupt (cyclic or doubly-listed) list", () => {
    const cyclic = [node("a", "b"), node("b", "a"), node("r", null)];
    expect(flatten(buildTree(cyclic)).map((t) => t.node.id)).toEqual(["r"]);
    expect(pathNames(cyclic, "a").length).toBeLessThanOrEqual(2);
  });

  it("finds leaves, subtrees, paths and depth", () => {
    expect(leaves(p.criteria).map((n) => n.id)).toEqual(["a1", "a2", "b1x", "b2", "c"]);
    expect(isLeaf(p.criteria, "b1")).toBe(false);
    expect(isLeaf(p.criteria, "c")).toBe(true);
    expect(subtreeIds(p.criteria, "b")).toEqual(["b", "b1", "b1x", "b2"]);
    expect(pathNames(p.criteria, "b1x")).toEqual(["B", "B1", "B1X"]);
    expect(maxDepth(p.criteria)).toBe(3);
    expect(maxDepth([])).toBe(0);
  });
});

describe("planMove", () => {
  it("up and down stay within the parent and are impossible at the ends", () => {
    expect(planMove(p, "a2", "up")).toEqual({ new_parent_id: "a", position: 0, needsDiscard: false });
    expect(planMove(p, "a1", "up")).toBeNull();
    expect(planMove(p, "a1", "down")).toEqual({ new_parent_id: "a", position: 1, needsDiscard: false });
    expect(planMove(p, "a2", "down")).toBeNull();
    expect(planMove(p, "c", "down")).toBeNull();
    expect(planMove(p, "b", "up")).toEqual({ new_parent_id: null, position: 0, needsDiscard: false });
  });

  it("indent makes the item the last child of the sibling above", () => {
    expect(planMove(p, "b", "indent")).toEqual({ new_parent_id: "a", position: null, needsDiscard: false });
    expect(planMove(p, "a", "indent")).toBeNull(); // nothing above it
  });

  it("indenting under a measured leaf says the leaf's data would be discarded", () => {
    expect(planMove(p, "a2", "indent")).toEqual({ new_parent_id: "a1", position: null, needsDiscard: true });
  });

  it("outdent places the item just after its former parent", () => {
    expect(planMove(p, "a2", "outdent")).toEqual({ new_parent_id: null, position: 1, needsDiscard: false });
    expect(planMove(p, "b1x", "outdent")).toEqual({ new_parent_id: "b", position: 1, needsDiscard: false });
    expect(planMove(p, "a", "outdent")).toBeNull();
  });

  it("an unknown id has no plan", () => {
    expect(planMove(p, "nope", "up")).toBeNull();
  });

  it("an unmeasured leaf can be indented under without a warning", () => {
    expect(planMove(p, "b", "indent")?.needsDiscard).toBe(false);
  });
});

describe("addingChildDiscards", () => {
  it("is true only for a leaf that has a scale, a value function or measurements", () => {
    expect(addingChildDiscards(p, "a1")).toBe(true);
    expect(addingChildDiscards(p, "a2")).toBe(false);
    expect(addingChildDiscards(p, "a")).toBe(false); // already a group
    const onlyMeasurements = { criteria: [node("m")], performances: [{ criterion_id: "m" }] };
    expect(addingChildDiscards(onlyMeasurements, "m")).toBe(true);
    expect(addingChildDiscards(p, "ghost")).toBe(false);
  });
});
