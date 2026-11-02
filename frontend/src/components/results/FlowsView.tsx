import type { CriterionExplanation, PairExplanation, PartialOrderPair, PrometheeAnalysisRecord } from "../../api/types";

/** Net flows lie in [−1, 1]; the axis is fixed there and never the 0–1 value axis. */
export const FLOW_AXIS = { min: -1, max: 1 } as const;
const LEFT = 280, WIDTH = 650;
export const flowX = (flow: number) => LEFT + (flow - FLOW_AXIS.min) / (FLOW_AXIS.max - FLOW_AXIS.min) * WIDTH;

const signed = (x: number) => `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toFixed(4)}`;
const plain = (x: number) => x.toFixed(4);
const number = (x: number) => String(Number(x.toPrecision(6)));
const capital = (text: string) => `${text[0]?.toUpperCase() ?? ""}${text.slice(1)}`;

type Register = (id: string, element: HTMLElement | null) => void;

/** PROMETHEE II flows, the PROMETHEE I partial order and the explanation against MAVT. Every number
 * is the engine's; the label travels with every view and no flow is called a value. */
export function FlowsView({ record, show, register }: { record: PrometheeAnalysisRecord; show: (id: string) => boolean; register: Register }) {
  const result = record.result;
  const names = Object.fromEntries(result.flows.map(f => [f.alternative_id, f.name]));
  return <div className="flows-view">
    <p className="banner info" role="note" aria-label="Flow label"><strong>{capital(result.label)}.</strong> A positive flow is how strongly an
      alternative outranks the others on average, a negative flow how strongly the others outrank it. Adding or removing an alternative
      can change every flow.</p>
    <p className="note" aria-label="Flow provenance">{record.project_title} · {record.method_label} · calculation {record.calculation_path} ·
      thresholds compared within {result.threshold_tolerance} · revision <code>{result.project_fingerprint.slice(0, 12)}</code></p>
    {show("flows") && <FlowsSection record={record} register={register}/>}
    {show("partial_order") && <PartialOrderSection pairs={result.partial_order} order={result.flows.map(f => f.alternative_id)} names={names} register={register}/>}
    {show("explanation") && <ExplanationSection record={record} names={names} register={register}/>}
    <details><summary>Inputs, notes and assumptions</summary>
      <div className="table-scroll" tabIndex={0}><table className="grid" aria-label="PROMETHEE inputs used">
        <thead><tr><th>Criterion</th><th>Direction</th><th>Weight</th><th>Normalised weight</th><th>Preference function</th><th>Codes</th></tr></thead>
        <tbody>{result.criteria.map(c => <tr key={c.criterion_id}>
          <th scope="row">{c.name}</th><td>{c.direction}</td><td>{number(c.weight)}</td><td>{plain(c.normalised_weight)}</td>
          <td>{functionText(c.function, c.unit)}</td>
          <td>{c.coding ? Object.entries(c.coding).map(([label, code]) => `${label} = ${number(code)}`).join(", ") : "—"}</td>
        </tr>)}</tbody>
      </table></div>
      <ul className="issue-list inline" aria-label="Flow notes">{result.diagnostics.map((d, i) => <li key={i} className={d.severity}><code>{d.code}</code> {d.message}</li>)}</ul>
      <ul>{result.assumptions.map((text, i) => <li key={i}>{text}</li>)}</ul>
      <p>Record version {record.record_version}; digest <code>{record.record_digest}</code>.</p>
    </details>
  </div>;
}

function functionText(f: PrometheeAnalysisRecord["result"]["criteria"][number]["function"], unit: string | null): string {
  const u = unit ? ` ${unit}` : "";
  if (f.kind === "usual") return "usual (any difference is full preference)";
  if (f.kind === "u_shape") return `U-shape, q = ${number(f.q)}${u}`;
  if (f.kind === "v_shape") return `V-shape, p = ${number(f.p)}${u}`;
  return `linear, q = ${number(f.q)}${u}, p = ${number(f.p)}${u}`;
}

function FlowsSection({ record, register }: { record: PrometheeAnalysisRecord; register: Register }) {
  const flows = record.result.flows;
  const zero = flowX(0);
  const height = flows.length * 34 + 60;
  return <>
    <h3 tabIndex={-1} ref={e => register("flows", e)}>Outranking flows and PROMETHEE II ranks</h3>
    <div className="table-scroll" tabIndex={0}><table className="grid" aria-label="Outranking flows">
      <thead><tr><th>Rank</th><th>Alternative</th><th>Positive flow</th><th>Negative flow</th><th>Net flow</th></tr></thead>
      <tbody>{flows.map(f => <tr key={f.alternative_id} data-alternative-id={f.alternative_id}>
        <td>{f.rank}</td><th scope="row">{f.name} <code>{f.alternative_id}</code></th>
        <td>{plain(f.positive_flow)}</td><td>{plain(f.negative_flow)}</td><td>{signed(f.net_flow)}</td>
      </tr>)}</tbody>
    </table></div>
    <svg viewBox={`0 0 1100 ${String(height)}`} className="results-chart" role="img" data-testid="flow-bars"
      aria-label="Net flows as bars from zero on a fixed axis from −1 to 1; the table above holds the same numbers">
      <g fontFamily="system-ui, sans-serif" fontSize="12" fill="#1c2025">
        {[-1, -0.5, 0, 0.5, 1].map(t => <g key={t}>
          <line x1={flowX(t)} x2={flowX(t)} y1="4" y2={height - 40} stroke={t === 0 ? "#1c2025" : "#d0d5db"}/>
          <text x={flowX(t)} y={height - 24} textAnchor="middle" data-tick={t}>{t === 0 ? "0" : signed(t).replace(/0+$/, "").replace(/\.$/, "")}</text>
        </g>)}
        {flows.map((f, i) => <g key={f.alternative_id} data-alternative-id={f.alternative_id}>
          <text x="8" y={i * 34 + 22}>{f.name}</text>
          <rect x={Math.min(zero, flowX(f.net_flow))} y={i * 34 + 8} width={Math.abs(flowX(f.net_flow) - zero)} height="20"
            fill={f.net_flow >= 0 ? "#2f6f9f" : "#b5562b"} data-net-flow={f.net_flow}><title>{f.name}: net flow {signed(f.net_flow)}</title></rect>
        </g>)}
        <text x={flowX(0)} y={height - 6} textAnchor="middle">net flow (−1 to 1), not a preference value</text>
      </g>
    </svg>
  </>;
}

function PartialOrderSection({ pairs, order, names, register }: { pairs: PartialOrderPair[]; order: string[]; names: Record<string, string>; register: Register }) {
  const rows = order.map(id => {
    const others = (relation: PartialOrderPair["relation"], keep: (p: PartialOrderPair) => boolean) => pairs
      .filter(p => p.relation === relation && keep(p))
      .map(p => p.alternative_a === id ? p.alternative_b : p.alternative_a);
    const involved = (p: PartialOrderPair) => p.alternative_a === id || p.alternative_b === id;
    return { id, incomparable: others("incomparable", involved), preferred: others("preferred", p => p.alternative_a === id),
      below: others("preferred", p => p.alternative_b === id), indifferent: others("indifferent", involved) };
  });
  const list = (ids: string[]) => ids.map(i => names[i] ?? i).join(", ") || "—";
  const incomparable = pairs.filter(p => p.relation === "incomparable");
  return <>
    <h3 tabIndex={-1} ref={e => register("partial_order", e)}>PROMETHEE I partial order</h3>
    <p className="muted small">An alternative is preferred to another when it is at least as good on both the positive and the negative
      flow and better on one. When the two flows disagree the pair is incomparable: the net flow alone hides that.</p>
    <p role="status" aria-label="Incomparable pairs">{incomparable.length === 0 ? "No pair is incomparable."
      : `Incomparable: ${incomparable.map(p => `${names[p.alternative_a] ?? p.alternative_a} and ${names[p.alternative_b] ?? p.alternative_b}`).join("; ")}.`}</p>
    <div className="table-scroll" tabIndex={0}><table className="grid" aria-label="PROMETHEE I relations">
      <thead><tr><th>Alternative</th><th>Incomparable with</th><th>Preferred to</th><th>Indifferent to</th><th>Below</th></tr></thead>
      <tbody>{rows.map(r => <tr key={r.id} data-alternative-id={r.id}>
        <th scope="row">{names[r.id]}</th><td>{list(r.incomparable)}</td><td>{list(r.preferred)}</td><td>{list(r.indifferent)}</td><td>{list(r.below)}</td>
      </tr>)}</tbody>
    </table></div>
  </>;
}

const ZONES: Record<CriterionExplanation["zone"], string> = { no_preference: "no preference", partial: "partial preference", full: "full preference" };

function zoneText(row: CriterionExplanation): string {
  const thresholds = [row.q !== null && `q = ${number(row.q)}`, row.p !== null && `p = ${number(row.p)}`].filter(Boolean).join(", ");
  const capped = row.capped ? ", capped" : "";
  return `${ZONES[row.zone]}${row.zone === "partial" ? ` (${row.preference_degree.toFixed(3)})` : ""}${capped}${thresholds ? ` · ${thresholds}` : " · usual function"}`;
}

function ExplanationSection({ record, names, register }: { record: PrometheeAnalysisRecord; names: Record<string, string>; register: Register }) {
  const explanation = record.result.explanation;
  return <>
    <h3 tabIndex={-1} ref={e => register("explanation", e)}>Explanation against MAVT</h3>
    {!explanation.available ? <p role="status" aria-label="Explanation unavailable">{explanation.unavailable_reason}
      {explanation.unavailable_codes.length > 0 && <> (<code>{explanation.unavailable_codes.join(", ")}</code>)</>}.</p> : <>
      <p className="muted small">MAVT under {record.scenario_name} and the profile {record.resolved_profile_name || "—"}. Only orders are compared:
        each gap stays in its own method’s units, and no number combines a value with a flow.</p>
      <div className="table-scroll" tabIndex={0}><table className="grid" aria-label="Rank comparison">
        <thead><tr><th>Alternative</th><th>MAVT rank</th><th>PROMETHEE II rank</th></tr></thead>
        <tbody>{explanation.ranks.map(r => <tr key={r.alternative_id}><th scope="row">{r.name}</th><td>{r.mavt_rank}</td><td>{r.promethee_rank}</td></tr>)}</tbody>
      </table></div>
      {explanation.pairs.length === 0 ? <p role="status">MAVT and PROMETHEE II order every pair the same way.</p>
        : <ol className="explanation-pairs" aria-label="Pairs ordered differently">{explanation.pairs.map(pair =>
          <PairItem key={`${pair.alternative_a}|${pair.alternative_b}`} pair={pair} names={names} limit={explanation.detail_limit}/>)}</ol>}
    </>}
  </>;
}

function PairItem({ pair, names, limit }: { pair: PairExplanation; names: Record<string, string>; limit: number }) {
  const a = names[pair.alternative_a] ?? pair.alternative_a, b = names[pair.alternative_b] ?? pair.alternative_b;
  return <li data-pair={`${pair.alternative_a}|${pair.alternative_b}`}>
    <p><strong>{a} and {b}</strong>: MAVT ranks them {pair.mavt_rank_a} and {pair.mavt_rank_b}; PROMETHEE II ranks them {pair.promethee_rank_a} and {pair.promethee_rank_b}.
      Value gap {signed(pair.value_gap)} (MAVT). Flow gap {signed(pair.flow_gap)} (net flow) = head-to-head {signed(pair.head_to_head)} + via
      the other alternatives {signed(pair.via_others)}.</p>
    {pair.detailed ? <>
      {pair.reasons.length > 0 && <ul aria-label={`Reasons for ${a} and ${b}`}>{pair.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>}
      <div className="table-scroll" tabIndex={0}><table className="grid" aria-label={`Criteria for ${a} and ${b}`}>
        <thead><tr><th>Criterion</th><th>Difference</th><th>Favours</th><th>Zone</th><th>PROMETHEE part of the flow gap</th><th>of which head-to-head</th><th>MAVT part of the value gap</th></tr></thead>
        <tbody>{pair.criteria.map(row => <tr key={row.criterion_id}>
          <th scope="row">{row.name}</th><td>{number(row.difference)}</td><td>{row.favours ? names[row.favours] ?? row.favours : "—"}</td>
          <td>{zoneText(row)}</td><td>{signed(row.promethee_contribution)}</td><td>{signed(row.promethee_head_to_head)}</td><td>{signed(row.mavt_contribution)}</td>
        </tr>)}</tbody>
      </table></div>
    </> : <p className="muted small">Criterion detail is given for the first {limit} pairs; this pair lists its gaps only.</p>}
  </li>;
}
