// User-interface policy for what a criterion looks like after a measurement-setting change.
// What is *admissible* comes from the server (`/api/meta`); nothing here decides mathematics.
import type {
  ControlPoint,
  CriterionNode,
  Direction,
  Meta,
  Scale,
  ScaleType,
  ValueFunction,
  ValueFunctionKind,
} from "../api/types";

export const SCALE_TYPE_LABEL: Record<ScaleType, string> = {
  ratio: "Ratio (numeric, true zero)",
  interval: "Interval (numeric, arbitrary zero)",
  ordinal: "Ordinal (ordered labels)",
  categorical: "Categorical (unordered labels)",
};

export const VALUE_FUNCTION_LABEL: Record<ValueFunctionKind, string> = {
  linear: "Linear between the scale bounds",
  piecewise_linear: "Piecewise linear (control points)",
  qualitative: "Qualitative (label → value)",
  direct_rating: "Direct rating",
};

export function isNumeric(type: ScaleType): boolean {
  return type === "ratio" || type === "interval";
}

export function allowedKinds(meta: Meta, type: ScaleType): ValueFunctionKind[] {
  const info = meta.scale_types.find((s) => s.type === type);
  return (info?.allowed_value_functions ?? []) as ValueFunctionKind[];
}

export function evenMapping(labels: readonly string[]): Record<string, number> {
  const n = labels.length;
  return Object.fromEntries(labels.map((l, i) => [l, n > 1 ? i / (n - 1) : 0]));
}

export function defaultValueFunction(kind: ValueFunctionKind, scale: Scale): ValueFunction {
  switch (kind) {
    case "linear":
      return { kind: "linear", direction: "increasing", out_of_domain: "error" };
    case "piecewise_linear": {
      const lo = scale.lower ?? 0;
      const hi = scale.upper ?? lo + 1;
      const points: ControlPoint[] = [
        { x: lo, value: 0 },
        { x: hi, value: 1 },
      ];
      return { kind: "piecewise_linear", points, out_of_domain: "error" };
    }
    case "qualitative":
      return { kind: "qualitative", mapping: evenMapping(scale.labels) };
    case "direct_rating":
      return {
        kind: "direct_rating",
        min_rating: scale.lower ?? 0,
        max_rating: scale.upper ?? 100,
        out_of_domain: "error",
      };
  }
}

export function defaultScale(type: ScaleType): Scale {
  return isNumeric(type)
    ? { type, unit: null, lower: 0, upper: 100, anchor_mode: "fixed", labels: [] }
    : { type, unit: null, lower: null, upper: null, anchor_mode: "fixed", labels: ["Low", "Medium", "High"] };
}

export interface ScaleChange {
  scale: Scale;
  valueFunction: ValueFunction;
  /** Entered measurements no longer make sense on the new scale (numbers vs labels). */
  clearsMeasurements: boolean;
}

/** What a leaf should become when its measurement type is changed. */
export function changeScaleType(node: CriterionNode, type: ScaleType, meta: Meta): ScaleChange {
  const old = node.scale;
  const crossesFamily = !old || isNumeric(old.type) !== isNumeric(type);
  const scale: Scale = crossesFamily ? defaultScale(type) : { ...old, type };
  const kinds = allowedKinds(meta, type);
  const current = node.value_function;
  const keep = !crossesFamily && current != null && kinds.includes(current.kind);
  const kind = kinds[0] ?? "linear";
  const valueFunction = keep ? current : defaultValueFunction(kind, scale);
  return { scale, valueFunction, clearsMeasurements: crossesFamily && old != null };
}

/** Display only: which way the preference runs, read off the function's own parameters. */
export function directionOf(vf: ValueFunction, labels: readonly string[] = []): Direction | "mixed" | null {
  switch (vf.kind) {
    case "linear":
      return vf.direction;
    case "direct_rating":
      return "increasing";
    case "piecewise_linear": {
      const v = vf.points.map((p) => p.value);
      if (v.length < 2) return null;
      const up = v.every((x, i) => i === 0 || x >= (v[i - 1] ?? x));
      const down = v.every((x, i) => i === 0 || x <= (v[i - 1] ?? x));
      return up && !down ? "increasing" : down && !up ? "decreasing" : "mixed";
    }
    case "qualitative": {
      const v = labels.map((l) => vf.mapping[l]).filter((x): x is number => x !== undefined);
      if (v.length < 2) return null;
      const up = v.every((x, i) => i === 0 || x >= (v[i - 1] ?? x));
      const down = v.every((x, i) => i === 0 || x <= (v[i - 1] ?? x));
      return up && !down ? "increasing" : down && !up ? "decreasing" : "mixed";
    }
  }
}

/** Parse a number the user typed. Returns null for empty, undefined for invalid. */
export function parseNumber(text: string): number | null | undefined {
  const t = text.trim();
  if (t === "") return null;
  if (!/^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(t)) return undefined;
  const n = Number(t);
  return Number.isFinite(n) ? n : undefined;
}
