import type { AcceptabilityEstimate, SmaaAnalysisRecord } from "../../api/types";
import { palette } from "./ResultsCharts";

const percent = (value: number) => `${(value * 100).toFixed(1)} %`;
/** A frequency and, for sampled runs, its exact interval; both come from the engine. */
export function estimateText(e: AcceptabilityEstimate): string {
  return e.lower === null || e.upper === null ? percent(e.frequency) : `${percent(e.frequency)} (${percent(e.lower)}–${percent(e.upper)})`;
}

/** SMAA-2 acceptabilities. Every number is the engine's; the label travels with every view. */
export function AcceptabilityView({ record }: { record: SmaaAnalysisRecord }) {
  const result = record.result;
  const ranks = result.acceptability[0]?.ranks.length ?? 0;
  const run = result.evaluation === "sampled"
    ? `${String(result.samples)} draws, seed ${String(result.seed)}, ${percent(result.confidence)} Clopper–Pearson intervals`
    : `exact over ${String(result.outcomes)} joint outcomes; no sampling and no intervals`;
  const leader = result.acceptability.find((a) => a.alternative_id === result.leader_id)?.name ?? result.leader_id;
  return <div className="acceptability-view">
    <p className="banner info" role="note" aria-label="Acceptability label"><strong>{result.label[0]?.toUpperCase()}{result.label.slice(1)}.</strong> Each figure is how
      often an alternative took a rank or class in draws from the stated distributions. It is not a probability of success, nor confidence
      that a choice is right.</p>
    <p className="note" aria-label="Acceptability provenance">{record.project_title} · {record.method_label} · {result.run} run · {run} ·
      algorithm {result.algorithm} · {record.scenario_name} · profile {record.resolved_profile_name} · revision <code>{result.project_fingerprint.slice(0, 12)}</code> ·
      Python {result.environment.python}, NumPy {result.environment.numpy}, {result.environment.system}</p>
    <h3>Rank acceptability</h3>
    <div className="table-scroll" tabIndex={0}><table className="grid" aria-label="Rank acceptability">
      <thead><tr><th>Alternative</th>{Array.from({ length: ranks }, (_, r) => <th key={r}>Rank {r + 1}</th>)}<th>Sole first</th><th>Tied first</th></tr></thead>
      <tbody>{result.acceptability.map((a) => <tr key={a.alternative_id} data-alternative-id={a.alternative_id}>
        <th scope="row">{a.name} <code>{a.alternative_id}</code></th>
        {a.ranks.map((e, r) => <td key={r}>{estimateText(e)}</td>)}
        <td>{estimateText(a.sole_first)}</td><td>{estimateText(a.tied_first)}</td>
      </tr>)}</tbody>
    </table></div>
    <svg viewBox={`0 0 1100 ${String(result.acceptability.length * 34 + 40)}`} className="results-chart" role="img" data-testid="acceptability-bars"
      aria-label="Rank acceptability as shares of draws, one bar per alternative; the table above holds the same numbers">
      <g fontFamily="system-ui, sans-serif" fontSize="12" fill="#1c2025">
        {result.acceptability.map((a, i) => {
          let offset = 0;
          return <g key={a.alternative_id} data-alternative-id={a.alternative_id}>
            <text x="8" y={i * 34 + 20}>{a.name}</text>
            {a.ranks.map((e, r) => {
              const x = 280 + offset * 650; offset += e.frequency;
              return e.frequency > 0 && <rect key={r} x={x} y={i * 34 + 6} width={e.frequency * 650} height="20"
                fill={palette[r % palette.length]} data-rank={r + 1}><title>{a.name}, rank {r + 1}: {estimateText(e)}</title></rect>;
            })}
          </g>;
        })}
        <text x="605" y={result.acceptability.length * 34 + 30} textAnchor="middle">Share of draws at each rank (0–100 %), not a score</text>
      </g>
    </svg>
    {result.classes.length > 0 && <>
      <h3>Class acceptability</h3>
      <div className="table-scroll" tabIndex={0}><table className="grid" aria-label="Class acceptability">
        <thead><tr><th>Alternative</th>{result.classes.map((c) => <th key={c.class_id}>{c.name}</th>)}</tr></thead>
        <tbody>{result.acceptability.map((a) => <tr key={a.alternative_id}>
          <th scope="row">{a.name}</th>
          {result.classes.map((c) => { const e = a.classes[c.class_id]; return <td key={c.class_id}>{e ? estimateText(e) : ""}</td>; })}
        </tr>)}</tbody>
      </table></div>
    </>}
    <h3>Inputs to check</h3>
    {result.inputs_to_check.length > 0
      ? <><p className="muted small">The leading alternative, {leader}, and its rank-1 share with each input in the upper and lower half of
          its draws. {result.inputs_to_check_label[0]?.toUpperCase()}{result.inputs_to_check_label.slice(1)}.</p>
        <ol aria-label="Inputs to check">{result.inputs_to_check.map((x) => <li key={x.path}>
          {x.input}: {percent(x.leader_rank1_upper_half)} in the upper half, {percent(x.leader_rank1_lower_half)} in the lower half <code>{x.path}</code>
        </li>)}</ol></>
      : <p className="muted small">Not computed for this run (see the notes below).</p>}
    <details><summary>Reference ranking and notes</summary>
      <p>MAVT at the entered measurements and the profile’s ratings: {result.ranking.map((r) => `${String(r.rank)}. ${r.name}`).join(", ")}.</p>
      <ul className="issue-list inline" aria-label="Acceptability notes">{result.diagnostics.map((d, i) => <li key={i} className={d.severity}><code>{d.code}</code> {d.message}</li>)}</ul>
      <ul>{result.assumptions.map((text, i) => <li key={i}>{text}</li>)}</ul>
    </details>
  </div>;
}
