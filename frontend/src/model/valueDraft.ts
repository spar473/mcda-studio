import type { Scale, ValueFunction, ValueFunctionCandidate } from "../api/types";

/** Raw text is retained separately so incomplete/invalid typing cannot disappear behind a valid preview. */
export interface ValueDraft {
  scale: Scale;
  valueFunction: ValueFunction;
  text: Record<string, string>;
  newX: string;
  newValue: string;
}
export function initialValueDraft(scale: Scale, valueFunction: ValueFunction): ValueDraft {
  return { scale: structuredClone(scale), valueFunction: structuredClone(valueFunction), text: {}, newX: "", newValue: "" };
}
export function candidateFromDraft(draft: ValueDraft): { candidate: ValueFunctionCandidate & { scale: Scale; value_function: ValueFunction }; errors: string[] } {
  const scale = structuredClone(draft.scale);
  const vf = structuredClone(draft.valueFunction);
  const errors: string[] = [];
  function number(key: string, fallback: number | null, nullable = false): number | null {
    const raw = draft.text[key];
    if (raw === undefined) return fallback;
    if (nullable && raw.trim() === "") return null;
    const value = Number(raw);
    if (raw.trim() === "" || !Number.isFinite(value)) {
      errors.push(`${key}: enter a finite number`); return fallback;
    }
    return value;
  }
  scale.lower = number("lower", scale.lower, true);
  scale.upper = number("upper", scale.upper, true);
  if (vf.kind === "piecewise_linear") vf.points = vf.points.map((point, i) => ({
    x: number(`point.${i}.x`, point.x) ?? point.x,
    value: number(`point.${i}.value`, point.value) ?? point.value,
  }));
  if (vf.kind === "direct_rating") {
    vf.min_rating = number("min_rating", vf.min_rating) ?? vf.min_rating;
    vf.max_rating = number("max_rating", vf.max_rating) ?? vf.max_rating;
  }
  if (vf.kind === "qualitative") for (const label of scale.labels) {
    const value = number(`label.${label}`, vf.mapping[label] ?? null);
    if (value !== null) vf.mapping[label] = value;
  }
  if (draft.newX !== "" || draft.newValue !== "") errors.push("Add the new control point or clear both new-point fields.");
  return { candidate: { scale, value_function: vf }, errors };
}

export function setDraftNumber(draft: ValueDraft, key: string, value: string): ValueDraft {
  return { ...draft, text: { ...draft.text, [key]: value } };
}

/** Maps a user-supplied handle position into input fields; never evaluates preferences. */
export function moveHandle(draft: ValueDraft, index: number, x: number, value: number): ValueDraft {
  const vf = draft.valueFunction;
  if (vf.kind === "piecewise_linear") {
    const text = { ...draft.text, [`point.${index}.x`]: String(x) };
    if (index > 0 && index < vf.points.length - 1) text[`point.${index}.value`] = String(value);
    return { ...draft, text };
  }
  if (vf.kind === "linear" && draft.scale.anchor_mode === "fixed") return setDraftNumber(draft, index === 0 ? "lower" : "upper", String(x));
  if (vf.kind === "direct_rating") return setDraftNumber(draft, index === 0 ? "min_rating" : "max_rating", String(x));
  if (vf.kind === "qualitative") {
    const label = draft.scale.labels[index];
    if (label !== undefined) return setDraftNumber(draft, `label.${label}`, String(value));
  }
  return draft;
}

export function insertControlPoint(draft: ValueDraft): ValueDraft | null {
  const x = Number(draft.newX), value = Number(draft.newValue);
  if (draft.newX.trim() === "" || draft.newValue.trim() === "" || !Number.isFinite(x) || !Number.isFinite(value)) return null;
  const parsed = candidateFromDraft({ ...draft, newX: "", newValue: "" });
  const vf = parsed.candidate.value_function;
  if (parsed.errors.length || vf.kind !== "piecewise_linear") return null;
  // Preserve user ordering; the backend, not a silent sort, validates the new position.
  const points = [...vf.points]; points.splice(Math.max(1, points.length - 1), 0, { x, value });
  return { ...draft, valueFunction: { ...vf, points }, text: {}, newX: "", newValue: "" };
}
