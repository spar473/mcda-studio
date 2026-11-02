import type { AnalysisPresentation, ClassBand, MavtSortingResult } from "../../api/types";
import { formatValue } from "./ResultsCharts";

type Precision = AnalysisPresentation["precision"];

/** The band's value range in words, from the engine's boundaries; nothing is recomputed here. */
export function bandRange(band: ClassBand, precision: Precision): string {
  const lower = band.lower_boundary, upper = band.upper_boundary;
  if (lower === null && upper === null) return "every value";
  if (lower === null) return `below ${formatValue(upper ?? 0, precision)}`;
  if (upper === null) return `${formatValue(lower, precision)} or more`;
  return `${formatValue(lower, precision)} to below ${formatValue(upper, precision)}`;
}

/** Classes, each alternative's class and distance to the nearest boundary, and the audit sample. */
export function ClassesView({ result, order, precision, selectedAlternative, onAlternative }: {
  result: MavtSortingResult; order: string[]; precision: Precision;
  selectedAlternative: string | null; onAlternative: (id: string) => void;
}) {
  const names = new Map(result.alternatives.map((a) => [a.alternative_id, a.name]));
  const classNames = new Map(result.classes.map((c) => [c.class_id, c.name]));
  const assigned = new Map(result.assignments.map((a) => [a.alternative_id, a]));
  const values = new Map(result.ranking.map((r) => [r.alternative_id, r]));
  const sample = result.audit_sample;
  const sampled = new Set(sample?.alternative_ids ?? []);
  return <div className="classes-view">
    <p>Classes are fixed boundaries on the overall MAVT value; an alternative belongs to the best class whose lower boundary it
      reaches, and a value within {String(result.boundary_tolerance)} of a boundary goes to the higher class. Classes inherit every MAVT
      assumption, including compensation. They are not probabilities, predictions or tests of single measurements.</p>
    <div className="table-scroll" tabIndex={0}><table className="grid" aria-label="Results classes">
      <thead><tr><th>Rank</th><th>Class</th><th>Overall value</th><th>Members</th></tr></thead>
      <tbody>{result.classes.map((c) => <tr key={c.class_id} data-class-id={c.class_id}>
        <td>{c.rank}</td><th scope="row">{c.name} <code>{c.class_id}</code></th><td>{bandRange(c, precision)}</td>
        <td>{c.alternative_ids.length ? c.alternative_ids.map((id) => names.get(id) ?? id).join(", ") : "none (empty class)"}</td>
      </tr>)}</tbody>
    </table></div>
    <div className="table-scroll" tabIndex={0}><table className="grid" aria-label="Class assignments">
      <thead><tr><th>Alternative / ID</th><th>Rank</th><th>Value</th><th>Class</th><th>To nearest boundary</th><th>Audit sample</th></tr></thead>
      <tbody>{order.map((id) => {
        const a = assigned.get(id); const r = values.get(id); if (!a || !r) return null;
        const nearest = a.nearest_boundary_class_id ? classNames.get(a.nearest_boundary_class_id) : null;
        return <tr key={id} className={id === selectedAlternative ? "selected" : undefined} data-alternative-id={id}>
          <th scope="row"><button type="button" className="link" onClick={() => onAlternative(id)}>{names.get(id)}</button> <code>{id}</code></th>
          <td>{r.rank}</td><td>{formatValue(r.value, precision)}</td><td>{classNames.get(a.class_id)}</td>
          <td>{a.distance_to_nearest_boundary === null ? "no boundary (one class)"
            : <>{formatValue(a.distance_to_nearest_boundary, precision)} from {nearest}{a.on_boundary && " — on the boundary, given the higher class"}</>}</td>
          <td>{sampled.has(id) ? "sampled" : ""}</td>
        </tr>;
      })}</tbody>
    </table></div>
    {sample ? <p aria-label="Audit sample">Audit sample below {classNames.get(sample.below_class_id)}: {sample.alternative_ids.length} of {sample.pool_size} sorted
      below the cut-off (seed {sample.seed}, {sample.selection_rule}){sample.alternative_ids.length ? `: ${sample.alternative_ids.map((id) => names.get(id) ?? id).join(", ")}` : ""}.
      A sample for manual review of possible false negatives; it estimates nothing and never changes a class.</p>
      : <p className="muted small">No audit sample is configured. The Classes tab can add one.</p>}
  </div>;
}
