// Presentation-only indexing. The engine remains the authority on model validity.
import type { CriterionNode, ValidationReport } from "../api/types";
import { parseIssuePath } from "./issues";

export interface TreeRow {
  node: CriterionNode;
  depth: number;
  position: number;
  siblings: number;
}
export interface TreeIndex {
  byId: Map<string, CriterionNode>;
  children: Map<string | null, CriterionNode[]>;
  rows: TreeRow[];
  errors: string[];
}

export function indexTree(nodes: readonly CriterionNode[]): TreeIndex {
  const byId = new Map<string, CriterionNode>();
  const children = new Map<string | null, CriterionNode[]>();
  const errors = new Set<string>();
  const positions = new Map<string, number>();
  nodes.forEach((node, i) => {
    if (byId.has(node.id)) errors.add("Duplicate criterion IDs make selection ambiguous.");
    else { byId.set(node.id, node); positions.set(node.id, i); }
    const parent = node.parent_id ?? null;
    const siblings = children.get(parent) ?? [];
    siblings.push(node); children.set(parent, siblings);
  });
  for (const node of nodes) {
    if (node.parent_id != null && !byId.has(node.parent_id)) errors.add("A criterion refers to a missing parent.");
  }
  for (const siblings of children.values()) siblings.sort((a, b) => a.order - b.order || (positions.get(a.id) ?? 0) - (positions.get(b.id) ?? 0));
  const rows: TreeRow[] = [];
  const seen = new Set<string>();
  const stack: TreeRow[] = [];
  const push = (siblings: CriterionNode[], depth: number) => {
    for (let i = siblings.length - 1; i >= 0; i--) {
      const node = siblings[i];
      if (node) stack.push({ node, depth, position: i + 1, siblings: siblings.length });
    }
  };
  push(children.get(null) ?? [], 1);
  while (stack.length) {
    const row = stack.pop();
    if (!row) break;
    if (seen.has(row.node.id)) continue;
    seen.add(row.node.id); rows.push(row);
    push(children.get(row.node.id) ?? [], row.depth + 1);
  }
  if (seen.size !== byId.size && !errors.size) errors.add("The hierarchy contains a cycle or unreachable nodes.");
  return { byId, children, rows, errors: [...errors] };
}

export function ancestors(index: TreeIndex, id: string | null): Set<string> {
  const out = new Set<string>();
  let parent = id ? index.byId.get(id)?.parent_id : null;
  while (parent && !out.has(parent)) {
    out.add(parent); parent = index.byId.get(parent)?.parent_id;
  }
  return out;
}

export function visibleRows(index: TreeIndex, collapsed: ReadonlySet<string>, selectedId: string | null) {
  // External selection reveals its ancestors immediately, including on a return from another tab.
  const revealed = ancestors(index, selectedId);
  const closed = new Set([...collapsed].filter(id => index.byId.has(id) && !revealed.has(id)));
  let hiddenDepth: number | null = null;
  const rows = index.rows.filter(row => {
    if (hiddenDepth !== null && row.depth > hiddenDepth) return false;
    hiddenDepth = closed.has(row.node.id) ? row.depth : null;
    return true;
  });
  return { rows, closed };
}

export function descendantIds(index: TreeIndex, id: string): Set<string> {
  const ids = new Set<string>();
  const stack = [id];
  while (stack.length) {
    const next = stack.pop();
    if (!next || ids.has(next)) continue;
    ids.add(next);
    for (const child of index.children.get(next) ?? []) stack.push(child.id);
  }
  return ids;
}

export function treeIssues(index: TreeIndex, report: ValidationReport) {
  const counts = new Map(index.rows.map(row => [row.node.id, { errors: 0, warnings: 0 }]));
  for (const issue of report.issues) {
    const target = parseIssuePath(issue.path);
    const id = target.kind === "criterion" ? target.id : target.kind === "performance" ? target.criterionId : target.kind === "judgement" ? target.nodeId : null;
    const count = id ? counts.get(id) : null;
    if (count) {
      if (issue.severity === "error") count.errors++; else count.warnings++;
    }
  }
  for (let i = index.rows.length - 1; i >= 0; i--) {
    const row = index.rows[i];
    if (!row?.node.parent_id) continue;
    const own = counts.get(row.node.id), parent = counts.get(row.node.parent_id);
    if (own && parent) { parent.errors += own.errors; parent.warnings += own.warnings; }
  }
  return counts;
}
