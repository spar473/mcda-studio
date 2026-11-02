import type { AhpAnalysisRecord, AhpMatrixResult, AhpTriad } from "../../api/types";

const capital = (text: string) => `${text[0]?.toUpperCase() ?? ""}${text.slice(1)}`;
const share = (x: number) => x.toFixed(4);
/** A matrix entry as a judgement reads: 3, or 1/3 for its reciprocal. */
export const judgementText = (x: number) => x >= 1 ? String(Number(x.toPrecision(4))) : `1/${String(Number((1 / x).toPrecision(4)))}`;

type Register = (id: string, element: HTMLElement | null) => void;

export function triadText(triad: AhpTriad, name: (id: string) => string): string {
  const [a, b, c] = triad.items.map(name);
  const [x, y, z] = triad.judgements;
  return `${a ?? ""} over ${b ?? ""}: ${judgementText(x)}; ${b ?? ""} over ${c ?? ""}: ${judgementText(y)}; ${a ?? ""} over ${c ?? ""}: ` +
    `${judgementText(z)}, where consistency would need ${judgementText(triad.consistent_value)}`;
}

/** AHP priorities and every matrix's consistency. Every number is the engine's; the label travels
 * with every view and no priority is called a value. */
export function AhpView({ record, show, register, criterionName }: {
  record: AhpAnalysisRecord; show: (id: string) => boolean; register: Register; criterionName: (id: string) => string;
}) {
  const result = record.result;
  const names: Record<string, string> = Object.fromEntries(result.alternatives.map(a => [a.alternative_id, a.name]));
  const name = (id: string) => names[id] ?? criterionName(id);
  const ideal = result.synthesis === "ideal";
  return <div className="ahp-view">
    <p className="banner info" role="note" aria-label="AHP label"><strong>{capital(result.label)}.</strong> Each priority comes from the
      pairwise judgements alone; a consistency ratio above {result.consistency_threshold.toFixed(2)} is a warning about those judgements.</p>
    <p className="note" aria-label="AHP provenance">{record.project_title} · {record.method_label} · {result.synthesis} synthesis · random index{" "}
      {result.random_index_table} · calculation {record.calculation_path} · reads no weight profile or scenario · revision{" "}
      <code>{result.project_fingerprint.slice(0, 12)}</code></p>
    {show("priorities") && <>
      <h3 tabIndex={-1} ref={e => register("priorities", e)}>AHP priorities and ranks</h3>
      <div className="table-scroll" tabIndex={0}><table className="grid" aria-label="AHP priorities">
        <thead><tr><th>Rank</th><th>Alternative</th><th>AHP priority</th>{ideal && <th>Ideal score</th>}</tr></thead>
        <tbody>{result.alternatives.map(a => <tr key={a.alternative_id} data-alternative-id={a.alternative_id}>
          <td>{a.rank}</td><th scope="row">{a.name} <code>{a.alternative_id}</code></th><td>{share(a.priority)}</td>
          {ideal && <td>{a.ideal_score === null ? "—" : share(a.ideal_score)}</td>}
        </tr>)}</tbody>
      </table></div>
      <svg viewBox={`0 0 1100 ${String(result.alternatives.length * 34 + 40)}`} className="results-chart" role="img" data-testid="ahp-bars"
        aria-label="AHP priorities as shares of the goal from 0 to 1; the table above holds the same numbers">
        <g fontFamily="system-ui, sans-serif" fontSize="12" fill="#1c2025">
          {result.alternatives.map((a, i) => <g key={a.alternative_id} data-alternative-id={a.alternative_id}>
            <text x="8" y={i * 34 + 22}>{a.name}</text>
            <rect x="280" y={i * 34 + 8} width={a.priority * 650} height="20" fill="#5b6fb0" data-priority={a.priority}>
              <title>{a.name}: AHP priority {share(a.priority)}</title></rect>
          </g>)}
          <text x="605" y={result.alternatives.length * 34 + 30} textAnchor="middle">AHP priority (shares sum to 1), not a preference value</text>
        </g>
      </svg>
      <div className="table-scroll" tabIndex={0}><table className="grid" aria-label="Criterion priorities">
        <thead><tr><th>Criterion</th><th>Local priority</th><th>Global priority</th></tr></thead>
        <tbody>{Object.entries(result.local_priorities).map(([id, local]) => <tr key={id}>
          <th scope="row">{criterionName(id)}</th><td>{share(local)}</td><td>{id in result.global_priorities ? share(result.global_priorities[id] ?? 0) : "—"}</td>
        </tr>)}</tbody>
      </table></div>
      <div className="table-scroll" tabIndex={0}><table className="grid" aria-label="Local priorities by leaf">
        <thead><tr><th>Alternative</th>{result.leaf_order.map(leaf => <th key={leaf}>{criterionName(leaf)}</th>)}</tr></thead>
        <tbody>{result.alternatives.map(a => <tr key={a.alternative_id}>
          <th scope="row">{a.name}</th>{result.leaf_order.map(leaf => <td key={leaf}>{share(a.local_priorities[leaf] ?? 0)}</td>)}
        </tr>)}</tbody>
      </table></div>
    </>}
    {show("consistency") && <ConsistencySection matrices={result.matrices} name={name} criterionName={criterionName} register={register}/>}
    <details><summary>Notes and assumptions</summary>
      <ul className="issue-list inline" aria-label="AHP notes">{result.diagnostics.map((d, i) => <li key={i} className={d.severity}><code>{d.code}</code> {d.message}</li>)}</ul>
      <ul>{result.assumptions.map((text, i) => <li key={i}>{text}</li>)}</ul>
      <p>Random indices ({result.random_index_table}, 1 to {result.random_indices.length} items): {result.random_indices.join(", ")}.
        Power iteration to {result.tolerance} within {result.max_iterations} iterations. Record version {record.record_version}; digest{" "}
        <code>{record.record_digest}</code>.</p>
    </details>
  </div>;
}

function matrixTitle(m: AhpMatrixResult, criterionName: (id: string) => string): string {
  if (m.kind === "alternatives") return `Alternatives on ${criterionName(m.group_id ?? "")}`;
  return m.group_id === null ? "Top-level criteria" : `Criteria under ${criterionName(m.group_id)}`;
}

function ConsistencySection({ matrices, name, criterionName, register }: {
  matrices: AhpMatrixResult[]; name: (id: string) => string; criterionName: (id: string) => string; register: Register;
}) {
  const ordered = [...matrices].sort((a, b) => Number(b.inconsistent) - Number(a.inconsistent));
  return <>
    <h3 tabIndex={-1} ref={e => register("consistency", e)}>Consistency of the judgements</h3>
    <div className="table-scroll" tabIndex={0}><table className="grid" aria-label="AHP consistency">
      <thead><tr><th>Matrix</th><th>Items</th><th>λmax</th><th>CI</th><th>RI</th><th>CR</th><th>Most inconsistent triad</th></tr></thead>
      <tbody>{ordered.map(m => <tr key={`${m.kind}:${m.group_id ?? "top"}`} className={m.inconsistent ? "warning" : undefined}
        data-matrix={`${m.kind}:${m.group_id ?? "top"}`}>
        <th scope="row">{matrixTitle(m, criterionName)}</th><td>{m.items.length}</td><td>{m.lambda_max.toFixed(4)}</td>
        <td>{m.consistency_index.toFixed(4)}</td><td>{m.random_index.toFixed(2)}</td>
        <td>{m.consistency_ratio.toFixed(4)}{m.inconsistent && <strong> above 0.10</strong>}</td>
        <td>{m.most_inconsistent_triad ? triadText(m.most_inconsistent_triad, name) : "—"}</td>
      </tr>)}</tbody>
    </table></div>
  </>;
}
