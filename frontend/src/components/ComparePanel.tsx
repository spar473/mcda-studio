import { useCallback, useRef, useState } from "react";
import { api } from "../api/client";
import type { ComparisonCell, ComparisonColumn, MethodComparison, Project } from "../api/types";
import type { EditorTab } from "../model/issues";
import { analysisKey, type AnalysisContext } from "../state/analysisContext";
import { useAnalysisRequest } from "../state/useAnalysisRequest";
import { saveDownload } from "./results/downloads";
import { StatusBadge } from "./results/FeasibilityView";
import { useFeasibility } from "../state/useFeasibility";
import type { FeasibilityResult } from "../api/types";

/** The editor tab that states each method's own inputs, for a column that could not run. */
const FIX_TAB: Record<string, EditorTab> = {
  mavt: "model", mavt_sorting: "classes", smaa2: "uncertainty", promethee2: "outranking", ahp: "pairwise",
};
/** Each column's own axis: its quantity's range, never shared with another method's. */
export function axisOf(column: ComparisonColumn): [number, number] {
  return column.method === "promethee2" ? [-1, 1] : [0, 1];
}
const percent = (x: number) => `${(x * 100).toFixed(1)} %`;

function quantityText(column: ComparisonColumn, cell: ComparisonCell): string {
  if (column.method === "smaa2") {
    return cell.interval ? `${percent(cell.quantity)} (${percent(cell.interval[0])}–${percent(cell.interval[1])})` : percent(cell.quantity);
  }
  const signed = column.method === "promethee2" && cell.quantity > 0 ? "+" : "";
  return `${signed}${cell.quantity.toFixed(4)}`;
}

/** Every method's own reading of the model, side by side. Python computes every number and reason;
 * there is no consensus score and no shared axis. */
export function ComparePanel({ project, context, onOpenTab }: {
  project: Project; context: AnalysisContext; onOpenTab?: (tab: EditorTab) => void;
}) {
  const key = analysisKey({ ...context, criterionId: null }, "method-comparison");
  const { fingerprint, configuration } = context;
  const load = useCallback(async (signal: AbortSignal) => {
    const result = await api.compareMethods(project, configuration, signal);
    if (result.project_fingerprint !== fingerprint) throw Error("Comparison does not match the selected revision.");
    return result;
  }, [project, configuration, fingerprint]);
  const request = useAnalysisRequest(key, true, load);
  const feasibility = useFeasibility(project, fingerprint);
  return <section className="panel compare-methods" aria-label="Compare methods">
    <h2>Compare methods</h2>
    <p className="muted">Each column is one method’s own reading of this model, with the profile and scenario selected above. Numbers are
      never combined across methods: there is no consensus score, and each quantity keeps its own name, units and axis.</p>
    {request.status === "loading" && <p role="status">Running every method…</p>}
    {request.status === "error" && <><p role="alert">{request.message}</p><button type="button" onClick={request.retry}>Retry comparison</button></>}
    {Boolean(project.requirements?.length) && feasibility.status === "loading" && <p role="status">Checking requirements…</p>}
    {Boolean(project.requirements?.length) && feasibility.status === "error" && <>
      <p role="alert">Feasibility could not be checked: {feasibility.message}</p>
      <button type="button" onClick={feasibility.retry}>Retry feasibility</button>
    </>}
    {request.status === "ready" && <ComparisonView comparison={request.result} project={project} onOpenTab={onOpenTab}
      feasibility={feasibility.status === "ready" ? feasibility.result : null}/>}
  </section>;
}

function ComparisonView({ comparison, project, onOpenTab, feasibility }: {
  comparison: MethodComparison; project: Project; onOpenTab?: (tab: EditorTab) => void; feasibility: FeasibilityResult | null;
}) {
  const [orderBy, setOrderBy] = useState("project");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const names = comparison.alternative_names;
  const ok = comparison.columns.filter((c) => c.status === "ok");
  const sorter = ok.find((c) => c.method === orderBy);
  const ranks = new Map(sorter?.cells.map((c) => [c.alternative_id, c.rank]));
  const rows = [...comparison.alternative_order].sort((a, b) => sorter ? (ranks.get(a) ?? 0) - (ranks.get(b) ?? 0) : 0);
  const cellOf = (column: ComparisonColumn, id: string) => column.cells.find((c) => c.alternative_id === id);
  const agreement = comparison.agreement;
  async function download(format: "json" | "csv") {
    controller.current?.abort();
    const c = new AbortController(); controller.current = c;
    setBusy(true); setError(null);
    try {
      const file = await api.exportComparison({ project: structuredClone(project), configuration: comparison.configuration,
        expected_project_fingerprint: comparison.project_fingerprint, format }, c.signal);
      if (!c.signal.aborted) saveDownload(file.blob, file.filename);
    } catch (e: unknown) {
      if (!c.signal.aborted) setError(e instanceof Error ? e.message : String(e));
    } finally { if (controller.current === c) setBusy(false); }
  }
  return <>
    <div aria-label="Agreement" className="comparison-agreement">
      {agreement.leaders_agree === null && <p role="status">Fewer than two methods ran, so there is nothing to compare yet.</p>}
      {agreement.leaders_agree === true && <p role="status">Every method that ran puts {names[agreement.leader_groups[0]?.leaders[0] ?? ""]} first.</p>}
      {agreement.leaders_agree === false && <><p role="status">The methods differ on what comes first:</p>
        <ul aria-label="First place by method">{agreement.leader_groups.map((g) => <li key={g.methods.join(",")}>
          {g.leaders.map((i) => names[i]).join(" and ")}: {g.methods.map((m) => comparison.columns.find((c) => c.method === m)?.method_label ?? m).join(", ")}
        </li>)}</ul></>}
      {agreement.classes.some((c) => !c.agree) && <ul aria-label="Class differences">{agreement.classes.filter((c) => !c.agree).map((c) =>
        <li key={c.alternative_id}>{names[c.alternative_id]}: sorting places it in {c.sorting_class_id}; SMAA-2 most often in {c.smaa_class_id}{" "}
          ({percent(c.smaa_class_share)} of draws)</li>)}</ul>}
      {agreement.reasons.map((r) => <div key={r.method} aria-label={`Why ${r.method} differs`}>
        <strong>{comparison.columns.find((c) => c.method === r.method)?.method_label ?? r.method}</strong> puts {r.leaders.map((i) => names[i]).join(" and ")} first
        where MAVT puts {r.mavt_leaders.map((i) => names[i]).join(" and ")}:
        <ul>{r.reasons.map((text, i) => <li key={i}>{text}</li>)}</ul>
      </div>)}
      <p className="note" aria-label="Comparison context">{agreement.context}</p>
    </div>
    <p className="results-controls">
      <label>Order rows by<select aria-label="Order rows by" value={orderBy} onChange={(e) => setOrderBy(e.target.value)}>
        <option value="project">Project order</option>
        {ok.map((c) => <option key={c.method} value={c.method}>{c.method_label} rank</option>)}
      </select></label>
      <button type="button" disabled={busy} onClick={() => void download("json")}>Download comparison JSON</button>
      <button type="button" disabled={busy} onClick={() => void download("csv")}>Download comparison CSV</button>
    </p>
    {error && <p role="alert">{error}</p>}
    <div className="table-scroll" tabIndex={0}><table className="grid" aria-label="Methods side by side">
      <thead><tr><th>Alternative</th>{feasibility && <th scope="col">Feasibility</th>}{comparison.columns.map((c) => <th key={c.method} scope="col" data-method={c.method}>
        <span className="column-method">{c.method_label}</span>
        {c.status === "ok" ? <><br/><span className="muted small">{c.quantity_name} ({c.quantity_range}) · rank</span>
          <br/><span className="muted small" aria-label={`Inputs of ${c.method_label}`}>Reads: {c.inputs.join("; ")}</span>
          <br/><span className="muted small">Parameters: {Object.keys(c.configuration.parameters).length ? JSON.stringify(c.configuration.parameters) : "defaults"}</span>
          {c.label && <><br/><em className="small">{c.label}</em></>}</>
          : <><br/><span className="muted small">Reads: {c.inputs.join("; ")}</span></>}
      </th>)}</tr></thead>
      <tbody>{rows.map((id) => <tr key={id} data-alternative-id={id}><th scope="row">{names[id]}</th>
        {feasibility && <td><StatusBadge result={feasibility} alternativeId={id}/></td>}
        {comparison.columns.map((c) => {
          if (c.error) {
            const tab = FIX_TAB[c.method];
            return <td key={c.method} className="warning" data-method={c.method}>
              {id === comparison.alternative_order[0] ? <>Did not run: <code>{c.error.code}</code>{c.error.issue_codes.length > 0 && <> ({c.error.issue_codes.join(", ")})</>}
                {tab && onOpenTab && <> <button type="button" onClick={() => onOpenTab(tab)}>Open {tab}</button></>}</> : "—"}
            </td>;
          }
          const cell = cellOf(c, id);
          if (!cell) return <td key={c.method}/>;
          const [min, max] = axisOf(c);
          return <td key={c.method} data-method={c.method}>
            <strong>{cell.rank}</strong> · {quantityText(c, cell)}
            <meter min={min} max={max} value={cell.quantity} aria-label={`${c.method_label} ${c.quantity_name ?? ""} for ${names[id] ?? id}`}/>
            {cell.class_id && <div className="small">class {cell.class_id}{cell.class_share !== null && ` (${percent(cell.class_share)})`}</div>}
            {cell.notes.map((n, i) => <div key={i} className="muted small">{n}</div>)}
          </td>;
        })}</tr>)}</tbody>
    </table></div>
  </>;
}
