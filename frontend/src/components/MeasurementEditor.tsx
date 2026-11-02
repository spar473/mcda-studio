import { useState } from "react";
import type {
  AnchorMode,
  ControlPoint,
  CriterionNode,
  Direction,
  Meta,
  Operation,
  PiecewiseVF,
  Project,
  ScaleType,
  ValueFunction,
  ValueFunctionKind,
} from "../api/types";
import {
  allowedKinds,
  directionOf,
  isNumeric,
  SCALE_TYPE_LABEL,
  VALUE_FUNCTION_LABEL,
} from "../model/defaults";
import {
  hasMeasurements,
  opsAddLabel,
  opsChangeScaleType,
  opsMoveLabel,
  opsPatchScale,
  opsRemoveLabel,
  opsRenameLabel,
  opsSetKind,
  opsSetLabelValue,
  opsSetValueFunction,
} from "../model/measurement";
import { Banner, CommitNumber, CommitText, ConfirmDialog, Field } from "./ui";

interface Props {
  project: Project;
  node: CriterionNode;
  meta: Meta;
  apply: (ops: Operation[]) => Promise<boolean>;
  busy: boolean;
}

const DIRECTION_TEXT: Record<Direction | "mixed", string> = {
  increasing: "Higher is preferred",
  decreasing: "Lower is preferred",
  mixed: "Not monotone (needs fixing)",
};

export function MeasurementEditor({ project, node, meta, apply, busy }: Props) {
  const scale = node.scale ?? null;
  const vf = node.value_function ?? null;
  const [pendingType, setPendingType] = useState<ScaleType | null>(null);
  const [labelError, setLabelError] = useState<string | null>(null);

  function chooseType(type: ScaleType) {
    if (scale && type === scale.type) return;
    const ops = opsChangeScaleType(project, node, type, meta);
    if (ops.some((o) => o.op === "clear_criterion_performances")) {
      setPendingType(type);
      return;
    }
    void apply(ops);
  }

  const count = project.performances.filter((p) => p.criterion_id === node.id).length;
  const kinds = scale ? allowedKinds(meta, scale.type) : [];

  return (
    <div className="measurement-editor">
      <fieldset disabled={busy} className="measurement-fields">
      <h3>Measurement</h3>
      <Field
        label="Measurement type"
        htmlFor="me-type"
        hint={
          scale
            ? undefined
            : "Choose how this criterion is measured. This also decides which preference functions are possible."
        }
      >
        <select
          id="me-type"
          value={scale?.type ?? ""}
          disabled={busy}
          onChange={(e) => {
            if (e.target.value) chooseType(e.target.value as ScaleType);
          }}
        >
          {!scale && <option value="">Choose…</option>}
          {meta.scale_types.map((t) => (
            <option key={t.type} value={t.type}>
              {SCALE_TYPE_LABEL[t.type]}
            </option>
          ))}
        </select>
      </Field>

      {scale && isNumeric(scale.type) && (
        <>
          <div className="row">
            <Field label="Unit" htmlFor="me-unit">
              <CommitText
                label="Unit"
                value={scale.unit ?? ""}
                placeholder="e.g. NZD, %, days"
                onCommit={(v) => void apply(opsPatchScale(node, { unit: v.trim() === "" ? null : v.trim() }))}
              />
            </Field>
          </div>
          <div className="row">
            <Field label="Numeric lower bound" htmlFor="me-lower">
              <CommitNumber
                label="Lower bound"
                value={scale.lower ?? null}
                allowEmpty
                onCommit={(v) => void apply(opsPatchScale(node, { lower: v }))}
              />
            </Field>
            <Field label="Numeric upper bound" htmlFor="me-upper">
              <CommitNumber
                label="Upper bound"
                value={scale.upper ?? null}
                allowEmpty
                onCommit={(v) => void apply(opsPatchScale(node, { upper: v }))}
              />
            </Field>
          </div>
          {vf?.kind === "linear" && (
            <Field
              label="Anchors"
              htmlFor="me-anchor"
              hint={
                scale.anchor_mode === "local"
                  ? "Local anchors are the smallest and largest measurement among the current alternatives. Adding or removing an alternative can change every score."
                  : "Fixed anchors are the bounds above and never depend on which alternatives are present."
              }
            >
              <select
                id="me-anchor"
                value={scale.anchor_mode}
                disabled={busy}
                onChange={(e) => void apply(opsPatchScale(node, { anchor_mode: e.target.value as AnchorMode }))}
              >
                {meta.anchor_modes.map((m) => (
                  <option key={m} value={m}>
                    {m === "fixed" ? "Fixed (stated bounds)" : "Local (min / max of alternatives)"}
                  </option>
                ))}
              </select>
            </Field>
          )}
        </>
      )}

      {scale && (
        <>
          <h3>Preference</h3>
          {isNumeric(scale.type) && (
            <Field label="Preference function" htmlFor="me-kind">
              <select
                id="me-kind"
                value={vf?.kind ?? ""}
                disabled={busy}
                onChange={(e) => void apply(opsSetKind(node, e.target.value as ValueFunctionKind))}
              >
                {!vf && <option value="">Choose…</option>}
                {kinds.map((k) => (
                  <option key={k} value={k}>
                    {VALUE_FUNCTION_LABEL[k]}
                  </option>
                ))}
              </select>
            </Field>
          )}
          {vf?.kind === "linear" && (
            <Field label="Preference direction" htmlFor="me-direction">
              <select
                id="me-direction"
                value={vf.direction}
                disabled={busy}
                onChange={(e) => void apply(opsSetValueFunction(node, { ...vf, direction: e.target.value as Direction }))}
              >
                {meta.directions.map((d) => (
                  <option key={d} value={d}>
                    {d === "increasing" ? "Higher is better" : "Lower is better"}
                  </option>
                ))}
              </select>
            </Field>
          )}
          {vf?.kind === "piecewise_linear" && <PiecewiseEditor node={node} vf={vf} apply={apply} />}
          {vf?.kind === "direct_rating" && (
            <div className="row">
              <Field label="Rating that means worst (0)">
                <CommitNumber
                  label="Minimum rating"
                  value={vf.min_rating}
                  onCommit={(v) => v !== null && void apply(opsSetValueFunction(node, { ...vf, min_rating: v }))}
                />
              </Field>
              <Field label="Rating that means best (1)">
                <CommitNumber
                  label="Maximum rating"
                  value={vf.max_rating}
                  onCommit={(v) => v !== null && void apply(opsSetValueFunction(node, { ...vf, max_rating: v }))}
                />
              </Field>
            </div>
          )}
          {vf && vf.kind !== "qualitative" && (
            <Field
              label="Outside the function’s range"
              htmlFor="me-ood"
              hint="Error stops the analysis for such a measurement; clamp uses the nearest end and says so in the results."
            >
              <select
                id="me-ood"
                value={vf.out_of_domain}
                disabled={busy}
                onChange={(e) =>
                  void apply(opsSetValueFunction(node, { ...vf, out_of_domain: e.target.value as "error" | "clamp" }))
                }
              >
                <option value="error">Report an error</option>
                <option value="clamp">Clamp and report</option>
              </select>
            </Field>
          )}
          {vf?.kind === "qualitative" && (
            <>
              <LabelTable
                project={project}
                node={node}
                apply={apply}
                busy={busy}
                setError={setLabelError}
              />
              {labelError && <Banner kind="error" onDismiss={() => setLabelError(null)}>{labelError}</Banner>}
            </>
          )}
          {vf && (
            <p className="muted small" data-testid="direction-readout">
              {(() => {
                const d = directionOf(vf, scale.labels);
                return d ? DIRECTION_TEXT[d] : "";
              })()}
              {count > 0 ? ` · ${String(count)} measurement(s) entered` : ""}
            </p>
          )}
        </>
      )}

      </fieldset>
      {pendingType && (
        <ConfirmDialog
          title="Change measurement type?"
          danger
          confirmLabel="Change type and clear measurements"
          message={
            <>
              {hasMeasurements(project, node.id) ? `${String(count)} entered measurement(s)` : "Entered measurements"}{" "}
              for <strong>{node.name}</strong> are numbers or labels of the old type and would no longer
              make sense, so they are cleared. You can undo this.
            </>
          }
          onCancel={() => setPendingType(null)}
          onConfirm={() => {
            const type = pendingType;
            setPendingType(null);
            void apply(opsChangeScaleType(project, node, type, meta));
          }}
        />
      )}
    </div>
  );
}

function PiecewiseEditor(props: {
  node: CriterionNode;
  vf: PiecewiseVF;
  apply: (ops: Operation[]) => Promise<boolean>;
}) {
  const { node, vf, apply } = props;
  const set = (points: ControlPoint[]) => void apply(opsSetValueFunction(node, { ...vf, points }));
  const last = vf.points[vf.points.length - 1];
  return (
    <div className="field">
      <span className="label">Control points</span>
      <table className="grid compact" aria-label="Control points">
        <thead>
          <tr>
            <th>Measurement</th>
            <th>Preference value (0–1)</th>
            <th>
              <span className="sr-only">Remove</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {vf.points.map((p, i) => (
            <tr key={i}>
              <td>
                <CommitNumber
                  label={`Control point ${String(i + 1)} measurement`}
                  value={p.x}
                  onCommit={(v) => v !== null && set(vf.points.map((q, j) => (j === i ? { ...q, x: v } : q)))}
                />
              </td>
              <td>
                <CommitNumber
                  label={`Control point ${String(i + 1)} value`}
                  value={p.value}
                  onCommit={(v) => v !== null && set(vf.points.map((q, j) => (j === i ? { ...q, value: v } : q)))}
                />
              </td>
              <td>
                <button
                  type="button"
                  className="link"
                  disabled={vf.points.length <= 2}
                  aria-label={`Remove control point ${String(i + 1)}`}
                  onClick={() => set(vf.points.filter((_, j) => j !== i))}
                >
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        type="button"
        onClick={() => set([...vf.points, { x: (last?.x ?? 0) + 1, value: last?.value ?? 1 }])}
      >
        Add control point
      </button>
      <div className="hint">
        x must increase strictly; values must lie in [0, 1], be monotone, and the worst end must be 0
        and the best end 1.
      </div>
    </div>
  );
}

function LabelTable(props: {
  project: Project;
  node: CriterionNode;
  apply: (ops: Operation[]) => Promise<boolean>;
  busy: boolean;
  setError: (message: string | null) => void;
}) {
  const { project, node, apply, busy, setError } = props;
  const labels = node.scale?.labels ?? [];
  const vf: ValueFunction | null | undefined = node.value_function;
  const mapping = vf?.kind === "qualitative" ? vf.mapping : {};
  const ordinal = node.scale?.type === "ordinal";
  return (
    <div className="field">
      <span className="label">
        {ordinal ? "Levels, worst to best, with preference values" : "Categories with preference values"}
      </span>
      <table className="grid compact" aria-label="Labels and preference values">
        <thead>
          <tr>
            <th>{ordinal ? "Level" : "Category"}</th>
            <th>Preference value (0–1)</th>
            <th>
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {labels.map((label, i) => (
            <tr key={`${String(i)}-${label}`}>
              <td>
                <CommitText
                  label={`Label ${String(i + 1)} name`}
                  value={label}
                  required
                  onCommit={(v) => {
                    const result = opsRenameLabel(project, node, i, v);
                    if (Array.isArray(result)) {
                      setError(null);
                      if (result.length) void apply(result);
                    } else {
                      setError(result.error);
                    }
                  }}
                />
              </td>
              <td>
                <CommitNumber
                  label={`Label ${String(i + 1)} preference value`}
                  value={mapping[label] ?? null}
                  onCommit={(v) => v !== null && void apply(opsSetLabelValue(node, label, v))}
                />
              </td>
              <td className="actions">
                <button type="button" className="link" disabled={busy || i === 0} aria-label={`Move ${label} up`} onClick={() => void apply(opsMoveLabel(node, i, -1))}>
                  ↑
                </button>
                <button
                  type="button"
                  className="link"
                  disabled={busy || i === labels.length - 1}
                  aria-label={`Move ${label} down`}
                  onClick={() => void apply(opsMoveLabel(node, i, 1))}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="link"
                  disabled={busy || labels.length <= 2}
                  aria-label={`Remove ${label}`}
                  onClick={() => void apply(opsRemoveLabel(project, node, i))}
                >
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button type="button" disabled={busy} onClick={() => void apply(opsAddLabel(node))}>
        Add {ordinal ? "level" : "category"}
      </button>
      <div className="hint">
        The worst label must have value 0 and the best 1
        {ordinal ? "; values may not decrease from worst to best" : ""}. Renaming or removing a label
        also updates the measurements already entered.
      </div>
    </div>
  );
}
