// An independent re-computation of the additive value model, written for the browser tests.
// It shares no code with the Python engine or with the application: it exists so that Case B's
// numbers are checked against a third implementation, not only against the engine that
// produced them.

export interface Linear {
  kind: "linear";
  lower: number;
  upper: number;
  /** "decreasing": the lower measurement is preferred. */
  direction: "increasing" | "decreasing";
}
export interface Labelled {
  kind: "labels";
  /** preference value per label */
  mapping: Record<string, number>;
}
export type Preference = Linear | Labelled;

export interface Leaf {
  name: string;
  preference: Preference;
}
export interface Group {
  name: string;
  /** swing rating of each child, keyed by child name */
  ratings: Record<string, number>;
  children: (Group | Leaf)[];
}

const isGroup = (n: Group | Leaf): n is Group => "children" in n;

export function partialValue(p: Preference, measurement: number | string): number {
  if (p.kind === "labels") {
    const v = p.mapping[String(measurement)];
    if (v === undefined) throw new Error(`unknown label ${String(measurement)}`);
    return v;
  }
  const x = Number(measurement);
  const t = (x - p.lower) / (p.upper - p.lower);
  return p.direction === "increasing" ? t : 1 - t;
}

/** Global weight of every leaf: the product of local weights (rating / sum of sibling ratings). */
export function globalWeights(root: Group, inherited = 1): Record<string, number> {
  const total = Object.values(root.ratings).reduce((a, b) => a + b, 0);
  const out: Record<string, number> = {};
  for (const child of root.children) {
    const local = root.children.length === 1 ? 1 : (root.ratings[child.name] ?? 0) / total;
    if (isGroup(child)) Object.assign(out, globalWeights(child, inherited * local));
    else out[child.name] = inherited * local;
  }
  return out;
}

export function leaves(root: Group): Leaf[] {
  return root.children.flatMap((c) => (isGroup(c) ? leaves(c) : [c]));
}

export function overallValue(root: Group, measurements: Record<string, number | string>): number {
  const w = globalWeights(root);
  return leaves(root).reduce((sum, leaf) => {
    const m = measurements[leaf.name];
    if (m === undefined) throw new Error(`no measurement for ${leaf.name}`);
    return sum + (w[leaf.name] ?? 0) * partialValue(leaf.preference, m);
  }, 0);
}
