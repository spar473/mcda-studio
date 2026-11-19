// Read-only helpers over the flat criteria list. No editing rules live here: every change is an
// operation sent to the server (services layer). These helpers only *describe* the tree and
// work out the arguments for a requested move.
import type { CriterionNode } from "../api/types";

export interface TreeNode {
  node: CriterionNode;
  children: TreeNode[];
  depth: number; // 1 = top level
}

function orderedChildren(criteria: readonly CriterionNode[], parentId: string | null): CriterionNode[] {
  const position = new Map(criteria.map((n, i) => [n.id, i]));
  return criteria
    .filter((n) => (n.parent_id ?? null) === parentId)
    .sort((a, b) => a.order - b.order || (position.get(a.id) ?? 0) - (position.get(b.id) ?? 0));
}

/** Nested view in sibling order (same tie-break as the engine: order, then list position). */
export function buildTree(criteria: readonly CriterionNode[]): TreeNode[] {
  const seen = new Set<string>();
  const build = (parentId: string | null, depth: number): TreeNode[] =>
    orderedChildren(criteria, parentId)
      .filter((n) => !seen.has(n.id) && (seen.add(n.id), true))
      .map((node) => ({ node, depth, children: build(node.id, depth + 1) }));
  return build(null, 1);
}

export function flatten(roots: readonly TreeNode[]): TreeNode[] {
  return roots.flatMap((r) => [r, ...flatten(r.children)]);
}

export function childrenOf(criteria: readonly CriterionNode[], id: string | null): CriterionNode[] {
  return orderedChildren(criteria, id);
}

export function isLeaf(criteria: readonly CriterionNode[], id: string): boolean {
  return !criteria.some((n) => n.parent_id === id);
}

export function leaves(criteria: readonly CriterionNode[]): CriterionNode[] {
  return flatten(buildTree(criteria))
    .map((t) => t.node)
    .filter((n) => isLeaf(criteria, n.id));
}

/** The node and everything beneath it. */
export function subtreeIds(criteria: readonly CriterionNode[], id: string): string[] {
  const out = [id];
  for (const child of childrenOf(criteria, id)) out.push(...subtreeIds(criteria, child.id));
  return out;
}

/** Nodes from the top-level ancestor down to the node, matching the engine's `tree.path`. */
export function pathNodes(criteria: readonly CriterionNode[], id: string): CriterionNode[] {
  const byId = new Map(criteria.map((n) => [n.id, n]));
  const out: CriterionNode[] = [];
  const guard = new Set<string>();
  let current = byId.get(id);
  while (current && !guard.has(current.id)) {
    guard.add(current.id);
    out.unshift(current);
    current = current.parent_id ? byId.get(current.parent_id) : undefined;
  }
  return out;
}

/** Names from the top-level ancestor down to the node. */
export function pathNames(criteria: readonly CriterionNode[], id: string): string[] {
  const byId = new Map(criteria.map((n) => [n.id, n]));
  const out: string[] = [];
  const guard = new Set<string>();
  let current = byId.get(id);
  while (current && !guard.has(current.id)) {
    guard.add(current.id);
    out.unshift(current.name);
    current = current.parent_id ? byId.get(current.parent_id) : undefined;
  }
  return out;
}

export function maxDepth(criteria: readonly CriterionNode[]): number {
  return flatten(buildTree(criteria)).reduce((m, t) => Math.max(m, t.depth), 0);
}

export type MoveDirection = "up" | "down" | "indent" | "outdent";

export interface MovePlan {
  new_parent_id: string | null;
  position: number | null;
  /** True when the receiving parent is a measured leaf that would lose its data. */
  needsDiscard: boolean;
}

function hasLeafData(project: { criteria: readonly CriterionNode[]; performances: readonly { criterion_id: string }[] }, id: string): boolean {
  const node = project.criteria.find((n) => n.id === id);
  return (
    !!node &&
    isLeaf(project.criteria, id) &&
    (node.scale != null ||
      node.value_function != null ||
      project.performances.some((p) => p.criterion_id === id))
  );
}

/** Arguments for `move_criterion` that realise a toolbar move, or null if it is impossible. */
export function planMove(
  project: { criteria: readonly CriterionNode[]; performances: readonly { criterion_id: string }[] },
  id: string,
  direction: MoveDirection,
): MovePlan | null {
  const node = project.criteria.find((n) => n.id === id);
  if (!node) return null;
  const parentId = node.parent_id ?? null;
  const siblings = childrenOf(project.criteria, parentId);
  const index = siblings.findIndex((n) => n.id === id);
  switch (direction) {
    case "up":
      return index > 0 ? { new_parent_id: parentId, position: index - 1, needsDiscard: false } : null;
    case "down":
      return index >= 0 && index < siblings.length - 1
        ? { new_parent_id: parentId, position: index + 1, needsDiscard: false }
        : null;
    case "indent": {
      const previous = siblings[index - 1];
      if (!previous) return null;
      return {
        new_parent_id: previous.id,
        position: null,
        needsDiscard: hasLeafData(project, previous.id),
      };
    }
    case "outdent": {
      if (parentId === null) return null;
      const parent = project.criteria.find((n) => n.id === parentId);
      const grand = parent?.parent_id ?? null;
      const uncles = childrenOf(project.criteria, grand);
      const at = uncles.findIndex((n) => n.id === parentId);
      return { new_parent_id: grand, position: at + 1, needsDiscard: false };
    }
  }
}

/** Does making `id` a parent (adding a child) discard entered data? */
export function addingChildDiscards(
  project: { criteria: readonly CriterionNode[]; performances: readonly { criterion_id: string }[] },
  id: string,
): boolean {
  return hasLeafData(project, id);
}
