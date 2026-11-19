// Presentation-only geometry and input-presence facts for the left-to-right model diagram.
// Weights, values and validity remain engine results; nothing here computes or judges them.
import type { CriterionNode, Project } from "../api/types";
import type { TreeIndex, TreeRow } from "./visibleTree";

/** 1-based CSS grid lines; a branch spans the rows of its visible descendants. */
export interface DiagramCell {
  column: number;
  rowStart: number;
  rowEnd: number;
}

/**
 * Each visible terminal row (a leaf, or a collapsed branch) gets its own grid row, and a visible
 * branch spans its descendants so the grid centres it beside them. Iterative and O(n), so deep
 * trees cannot exhaust the stack. Rows must be the visible pre-order rows of one tree.
 */
export function diagramLayout(rows: readonly TreeRow[]): { cells: Map<string, DiagramCell>; rowCount: number; columns: number } {
  const cells = new Map<string, DiagramCell>();
  const open: { row: TreeRow; start: number }[] = [];
  let next = 0, columns = 0;
  const closeFrom = (depth: number) => {
    for (let top = open.at(-1); top && top.row.depth >= depth; top = open.at(-1)) {
      open.pop();
      cells.set(top.row.node.id, { column: top.row.depth, rowStart: top.start + 1, rowEnd: next + 1 });
    }
  };
  rows.forEach((row, i) => {
    closeFrom(row.depth);
    columns = Math.max(columns, row.depth);
    const after = rows[i + 1];
    if (!after || after.depth <= row.depth) {
      cells.set(row.node.id, { column: row.depth, rowStart: next + 1, rowEnd: next + 2 });
      next++;
    } else {
      open.push({ row, start: next });
    }
  });
  closeFrom(0);
  return { cells, rowCount: next, columns };
}

/** Structural leaves, counted whether or not their branch is collapsed. */
export function leafIds(index: TreeIndex): string[] {
  return index.rows.filter(row => !index.children.get(row.node.id)?.length).map(row => row.node.id);
}

export function hasValueFunction(node: CriterionNode): boolean {
  return node.scale !== null && node.value_function !== null;
}

/**
 * Presence of swing ratings for one sibling group in the resolved profile: a fact about entered
 * judgements, not about their validity. An only child needs no rating (its local weight is one).
 */
export function swingRatings(project: Project, index: TreeIndex, profileId: string | null, parentId: string | null) {
  const children = index.children.get(parentId) ?? [];
  const profile = project.weight_profiles.find(p => p.id === profileId);
  if (!profile) return { children: children.length, missing: children.length > 1 ? children.length : 0, profile: false };
  const missing = children.length > 1 ? children.filter(child => profile.judgements[child.id] === undefined).length : 0;
  return { children: children.length, missing, profile: true };
}
