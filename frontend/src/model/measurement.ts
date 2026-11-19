// Turning an edit in the measurement-settings form into server operations. Labels, preference
// values and entered measurements are coupled (a renamed label must be renamed everywhere), so
// each label edit is one atomic multi-operation request.
import type {
  CriterionNode,
  Meta,
  Operation,
  Project,
  QualitativeVF,
  Scale,
  ScaleType,
  ValueFunction,
  ValueFunctionKind,
} from "../api/types";
import { changeScaleType, defaultValueFunction } from "./defaults";

function leafPerformances(project: Project, criterionId: string) {
  return project.performances.filter((p) => p.criterion_id === criterionId);
}

export function hasMeasurements(project: Project, criterionId: string): boolean {
  return leafPerformances(project, criterionId).length > 0;
}

export function opsChangeScaleType(
  project: Project,
  node: CriterionNode,
  type: ScaleType,
  meta: Meta,
): Operation[] {
  const change = changeScaleType(node, type, meta);
  const ops: Operation[] = [];
  if (change.clearsMeasurements && hasMeasurements(project, node.id)) {
    ops.push({ op: "clear_criterion_performances", criterion_id: node.id });
  }
  ops.push({ op: "set_scale", criterion_id: node.id, scale: change.scale });
  ops.push({ op: "set_value_function", criterion_id: node.id, value_function: change.valueFunction });
  return ops;
}

export function opsPatchScale(node: CriterionNode, patch: Partial<Scale>): Operation[] {
  if (!node.scale) return [];
  return [{ op: "set_scale", criterion_id: node.id, scale: { ...node.scale, ...patch } }];
}

export function opsSetValueFunction(node: CriterionNode, vf: ValueFunction): Operation[] {
  return [{ op: "set_value_function", criterion_id: node.id, value_function: vf }];
}

export function opsSetKind(node: CriterionNode, kind: ValueFunctionKind): Operation[] {
  if (!node.scale) return [];
  return opsSetValueFunction(node, defaultValueFunction(kind, node.scale));
}

function qualitative(node: CriterionNode): QualitativeVF | null {
  return node.value_function?.kind === "qualitative" ? node.value_function : null;
}

export function opsSetLabelValue(node: CriterionNode, label: string, value: number): Operation[] {
  const vf = qualitative(node);
  if (!vf) return [];
  return opsSetValueFunction(node, { ...vf, mapping: { ...vf.mapping, [label]: value } });
}

/** Rename a label everywhere: scale, preference mapping and entered measurements. */
export function opsRenameLabel(
  project: Project,
  node: CriterionNode,
  index: number,
  newName: string,
): Operation[] | { error: string } {
  const labels = node.scale?.labels ?? [];
  const old = labels[index];
  const name = newName.trim();
  if (old === undefined || !node.scale) return [];
  if (name === "") return { error: "A label cannot be empty." };
  if (name === old) return [];
  if (labels.includes(name)) return { error: `The label “${name}” already exists.` };
  const next = labels.map((l, i) => (i === index ? name : l));
  const ops: Operation[] = [
    { op: "set_scale", criterion_id: node.id, scale: { ...node.scale, labels: next } },
  ];
  const vf = qualitative(node);
  if (vf) {
    const mapping = Object.fromEntries(
      Object.entries(vf.mapping).map(([k, v]) => [k === old ? name : k, v]),
    );
    ops.push({
      op: "set_value_function",
      criterion_id: node.id,
      value_function: { ...vf, mapping },
    });
  }
  for (const p of leafPerformances(project, node.id)) {
    if (p.value === old) {
      ops.push({
        op: "set_performance",
        alternative_id: p.alternative_id,
        criterion_id: node.id,
        value: name,
      });
    }
  }
  return ops;
}

export function opsRemoveLabel(project: Project, node: CriterionNode, index: number): Operation[] {
  const labels = node.scale?.labels ?? [];
  const old = labels[index];
  if (old === undefined || !node.scale) return [];
  const ops: Operation[] = [
    {
      op: "set_scale",
      criterion_id: node.id,
      scale: { ...node.scale, labels: labels.filter((_, i) => i !== index) },
    },
  ];
  const vf = qualitative(node);
  if (vf) {
    const mapping = Object.fromEntries(Object.entries(vf.mapping).filter(([k]) => k !== old));
    ops.push({
      op: "set_value_function",
      criterion_id: node.id,
      value_function: { ...vf, mapping },
    });
  }
  for (const p of leafPerformances(project, node.id)) {
    if (p.value === old) {
      ops.push({ op: "clear_performance", alternative_id: p.alternative_id, criterion_id: node.id });
    }
  }
  return ops;
}

/** Append a label as the new best (preference value 1). */
export function opsAddLabel(node: CriterionNode): Operation[] {
  if (!node.scale) return [];
  const labels = node.scale.labels;
  let n = labels.length + 1;
  while (labels.includes(`Level ${String(n)}`)) n += 1;
  const name = `Level ${String(n)}`;
  const ops: Operation[] = [
    { op: "set_scale", criterion_id: node.id, scale: { ...node.scale, labels: [...labels, name] } },
  ];
  const vf = qualitative(node);
  if (vf) {
    ops.push({
      op: "set_value_function",
      criterion_id: node.id,
      value_function: { ...vf, mapping: { ...vf.mapping, [name]: 1 } },
    });
  }
  return ops;
}

export function opsMoveLabel(node: CriterionNode, index: number, delta: -1 | 1): Operation[] {
  if (!node.scale) return [];
  const labels = [...node.scale.labels];
  const target = index + delta;
  const a = labels[index];
  const b = labels[target];
  if (a === undefined || b === undefined) return [];
  labels[index] = b;
  labels[target] = a;
  return [{ op: "set_scale", criterion_id: node.id, scale: { ...node.scale, labels } }];
}
