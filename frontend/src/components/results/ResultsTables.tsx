import type { KeyboardEvent } from "react";
import type { AnalysisPresentation, ValueRecord, CriterionContext } from "../../api/types";
import { formatValue } from "./ResultsCharts";

/** Arrow navigation moves focus by table coordinates, independently of numerical values. */
function gridKey(event: KeyboardEvent<HTMLButtonElement>, row: number, column: number, rows: number, columns: number) {
  const moves: Record<string, [number, number]> = { ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [-1, 0], ArrowDown: [1, 0] };
  const move = moves[event.key]; if (!move) return;
  event.preventDefault();
  const nextRow = Math.max(0, Math.min(rows - 1, row + move[0]));
  const nextColumn = Math.max(0, Math.min(columns - 1, column + move[1]));
  event.currentTarget.closest("table")?.querySelector<HTMLButtonElement>(`[data-grid-row="${String(nextRow)}"][data-grid-column="${String(nextColumn)}"]`)?.focus();
}

interface DataProps {
  record: ValueRecord; order: string[]; precision: AnalysisPresentation["precision"];
  selectedAlternative: string | null; selectedCriterion: string | null;
  onAlternative: (id: string) => void; onCriterion: (id: string) => void;
}
export function RankingTable({ record, order, precision, selectedAlternative, onAlternative }: DataProps) {
  const details = new Map(record.result.alternatives.map(a => [a.alternative_id, a]));
  return <div className="table-scroll" tabIndex={0}><table className="grid ranking" aria-label="Ranking"><thead><tr>
    <th>Rank</th><th>Alternative</th><th>Overall value</th><th>ID</th>
  </tr></thead><tbody>{order.map(id => {
    const alt = details.get(id); if (!alt) return null;
    return <tr key={id} className={id === selectedAlternative ? "result-selected" : ""}>
      <td>{alt.rank}</td><th scope="row"><button type="button" aria-pressed={id === selectedAlternative} onClick={() => onAlternative(id)}>{alt.name}</button></th>
      <td title={String(alt.overall_value)}>{formatValue(alt.overall_value, precision)}</td><td><code>{id}</code></td>
    </tr>;
  })}</tbody></table></div>;
}
export function ContributionTable({ record, order, precision, selectedAlternative, selectedCriterion, onAlternative, onCriterion }: DataProps) {
  const details = new Map(record.result.alternatives.map(a => [a.alternative_id, a]));
  return <div className="table-scroll" tabIndex={0}><table className="grid compact" aria-label="Contributions"><thead><tr>
    <th>Alternative</th>{record.criteria.map(c => <th key={c.criterion_id} className={c.criterion_id === selectedCriterion ? "result-selected" : ""}>
      <button type="button" onClick={() => onCriterion(c.criterion_id)} title={c.path_names.join(" / ")}>{c.name}</button></th>)}<th>Engine total</th>
  </tr><tr className="subhead"><th>Global weight</th>{record.criteria.map(c => <td key={c.criterion_id} title={String(record.result.global_weights[c.criterion_id])}>{formatValue(record.result.global_weights[c.criterion_id] ?? 0, precision)}</td>)}<th>Overall MAVT value</th></tr></thead>
    <tbody>{order.map(id => { const alt = details.get(id); if (!alt) return null; return <tr key={id} className={id === selectedAlternative ? "result-selected" : ""}>
      <th scope="row"><button type="button" onClick={() => onAlternative(id)}>{alt.name}</button></th>
      {record.criteria.map(c => <td key={c.criterion_id} data-criterion-id={c.criterion_id} title={`Partial ${String(alt.partial_values[c.criterion_id])}; global weight ${String(record.result.global_weights[c.criterion_id])}; contribution ${String(alt.weighted_contributions[c.criterion_id])}`}>
        {formatValue(alt.weighted_contributions[c.criterion_id] ?? 0, precision)}</td>)}
      <td data-testid={`contribution-total-${id}`} title={String(alt.overall_value)}>{formatValue(alt.overall_value, precision)}</td>
    </tr>; })}</tbody>
  </table></div>;
}

export function PartialHeatmap({ record, order, precision, selectedAlternative, selectedCriterion, onAlternative, onCriterion }: DataProps) {
  const details = new Map(record.result.alternatives.map(a => [a.alternative_id, a]));
  return <div className="table-scroll" tabIndex={0} role="region" aria-label="Partial-value heatmap scroll area">
    <table className="grid partial-heatmap" aria-label="Partial-value heatmap"><caption>
      Colour and fill encode preference values on the common 0–1 scale, never raw measurements with different units. Each cell includes its numeric preference and raw measurement. Zero is a real preference value.
    </caption><thead><tr><th>Alternative</th>{record.criteria.map(c => <th key={c.criterion_id} className={c.criterion_id === selectedCriterion ? "result-selected" : ""}>
      <button type="button" onClick={() => onCriterion(c.criterion_id)} title={c.path_names.join(" / ")}>{c.name}</button><small>{c.scale.unit ?? c.scale.type}</small>
    </th>)}</tr></thead><tbody>{order.map((id, rowIndex) => { const alt = details.get(id); if (!alt) return null; return <tr key={id} className={id === selectedAlternative ? "result-selected" : ""}>
      <th scope="row"><button type="button" onClick={() => onAlternative(id)}>{alt.name}</button><small><code>{id}</code></small></th>
      {record.criteria.map((c, columnIndex) => {
        const partial = alt.partial_values[c.criterion_id]; if (partial === undefined) return null;
        return <td key={c.criterion_id} data-criterion-id={c.criterion_id} className={c.criterion_id === selectedCriterion ? "result-selected" : ""}>
          <button type="button" className="heatmap-cell" data-grid-row={rowIndex} data-grid-column={columnIndex}
            onKeyDown={e => gridKey(e, rowIndex, columnIndex, order.length, record.criteria.length)} style={{ backgroundColor: "#fff", backgroundImage: `linear-gradient(rgba(35,107,142,${String(.08 + partial * .32)}),rgba(35,107,142,${String(.08 + partial * .32)}))` }}
            aria-label={`Inspect ${alt.name}, ${c.name}: preference ${String(partial)}, raw ${String(alt.raw_measurements[c.criterion_id])} ${c.scale.unit ?? ""}`}
            onClick={() => { onAlternative(id); onCriterion(c.criterion_id); }}>
            <strong>{formatValue(partial, precision)}</strong><small>Raw: {String(alt.raw_measurements[c.criterion_id])} {c.scale.unit}</small>
            <span className="heatmap-meter" aria-hidden="true" style={{ width: `${String(partial * 100)}%` }}/>
          </button>
        </td>;
      })}
    </tr>; })}</tbody></table>
  </div>;
}

export function CriterionDetails({ record, criterion, alternativeId, precision }: {
  record: ValueRecord; criterion: CriterionContext | undefined; alternativeId: string | null;
  precision: AnalysisPresentation["precision"];
}) {
  const alt = record.result.alternatives.find(a => a.alternative_id === alternativeId);
  return <section className="result-inspector" aria-label="Selected criterion and alternative">
    <h3>Linked inspection</h3><p>Selected alternative: <strong>{alt ? `${alt.name} (${alt.alternative_id})` : "None — select a bar, table row or heatmap cell"}</strong></p>
    {criterion ? <>
      <p>Selected criterion: <strong>{criterion.path_names.join(" / ")}</strong> · <code>{criterion.criterion_id}</code></p>
      <p>{criterion.description || "No criterion description provided."}</p>
      <p>Scale: {criterion.scale.type} · Unit: {criterion.scale.unit ?? "label / dimensionless"} · Function source: {criterion.function_source} · Stored anchor policy: {criterion.scale.anchor_mode}.</p>
      <p>Effective domain: {criterion.resolved_domain ? `${String(criterion.resolved_domain.lower)} – ${String(criterion.resolved_domain.upper)}; source ${criterion.resolved_domain.source}` : "Qualitative labels and explicit preference judgements"}.</p>
      <p>Global leaf weight: {String(record.result.global_weights[criterion.criterion_id])}. Engine path shares: {criterion.path_ids.map(id => `${id}: ${String(record.path_shares[id])}`).join(" → ")}.</p>
      {alt && <p>Raw measurement: {String(alt.raw_measurements[criterion.criterion_id])} {criterion.scale.unit}. Partial preference: {formatValue(alt.partial_values[criterion.criterion_id] ?? 0, precision)}. Backend weighted contribution: {formatValue(alt.weighted_contributions[criterion.criterion_id] ?? 0, precision)}.</p>}
      <details><summary>Stored effective value-function definition</summary><pre>{JSON.stringify(criterion.value_function, null, 2)}</pre>
        <p>Control points are the stored judgements. Rounded published controls do not imply access to unrounded original inputs.</p></details>
    </> : <p>Select a leaf criterion from the contribution chart, legend, heatmap or selector.</p>}
  </section>;
}

const relationNames = { same_alternative: "Same alternative", dominates: "Dominates", dominated_by: "Dominated by", equal: "Equal partial values", incomparable: "Incomparable", not_checked: "Not checked" };
const relationSymbols = { same_alternative: "—", dominates: "D →", dominated_by: "← D", equal: "=", incomparable: "∥", not_checked: "?" };
export function DominanceView({ record, order, precision, pair, onPair, onCriterion }: DataProps & {
  pair: { first: string; second: string } | null; onPair: (first: string, second: string) => void;
}) {
  const details = new Map(record.result.alternatives.map(a => [a.alternative_id, a]));
  const first = pair ? details.get(pair.first) : undefined, second = pair ? details.get(pair.second) : undefined;
  const relation = pair ? record.dominance_relations[pair.first]?.[pair.second] : undefined;
  return <>
    <p>Dominance uses the engine’s partial values over these criteria, with tolerance {String(record.numerical_tolerance)}. It is a diagnostic, distinct from weighted overall ranking; zero-weight criteria still participate. No alternatives are removed.</p>
    {!record.dominance_enabled && <p role="status">Dominance checking is disabled in this analysis configuration. Relationships are not checked.</p>}
    <ul aria-label="Dominance pairs">{record.result.dominance.length ? record.result.dominance.map(pair => <li key={`${pair.dominator_id}:${pair.dominated_id}`}>
      <button type="button" onClick={() => onPair(pair.dominator_id, pair.dominated_id)}>{details.get(pair.dominator_id)?.name} dominates {details.get(pair.dominated_id)?.name}</button>
    </li>) : <li>No dominance pairs reported. Equal and incomparable partial vectors are distinguished in the matrix when checking is enabled.</li>}</ul>
    <p>D →: row dominates column · ← D: row is dominated · =: equal partial values · ∥: incomparable · ?: not checked. Select a pair for its supporting partial values.</p>
    <div className="table-scroll" tabIndex={0}><table className="grid dominance-matrix" aria-label="Dominance matrix"><thead><tr><th>Row / compared alternative</th>{order.map(id => <th key={id}>{details.get(id)?.name}<small><code>{id}</code></small></th>)}</tr></thead><tbody>
      {order.map((a, rowIndex) => <tr key={a}><th scope="row">{details.get(a)?.name}</th>{order.map((b, columnIndex) => {
        const relation = record.dominance_relations[a]?.[b];
        return <td key={b}>{relation && <button type="button" data-grid-row={rowIndex} data-grid-column={columnIndex}
          onKeyDown={e => gridKey(e, rowIndex, columnIndex, order.length, order.length)}
          aria-label={`${details.get(a)?.name ?? a} versus ${details.get(b)?.name ?? b}: ${relationNames[relation]}`}
          onClick={() => onPair(a, b)}>{relationSymbols[relation]}<small>{relationNames[relation]}</small></button>}</td>;
      })}</tr>)}
    </tbody></table></div>
    {first && second && relation && <section aria-label="Dominance pair inspection"><h4>{first.name} / {second.name}: {relationNames[relation]}</h4>
      <div className="table-scroll" tabIndex={0}><table className="grid" aria-label="Dominance supporting partial values"><thead><tr><th>Criterion</th><th>{first.name}</th><th>{second.name}</th></tr></thead><tbody>
        {record.criteria.map(c => <tr key={c.criterion_id}><th scope="row"><button type="button" onClick={() => onCriterion(c.criterion_id)}>{c.path_names.join(" / ")}</button></th>
          <td>{formatValue(first.partial_values[c.criterion_id] ?? 0, precision)}</td><td>{formatValue(second.partial_values[c.criterion_id] ?? 0, precision)}</td></tr>)}
      </tbody></table></div></section>}
  </>;
}
