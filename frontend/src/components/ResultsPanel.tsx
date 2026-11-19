import { useWeightTrial, type WeightTrial } from "../state/useWeightTrial";
import { useScreeningWhatIf } from "../state/useScreeningWhatIf";
import { WhatIfWeights } from "./WhatIfWeights";
import { WeightTrialGate, RESET_TRIAL, RESET_DOWNLOAD, useTrialDownloadGuard } from "./WeightTrialGate";
import { PartnerComparison } from "./results/PartnerComparison";
import { useLayoutEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { isAhpRecord, isPrometheeRecord, isSmaaRecord, type AnalysisPresentation, type EvidenceDossier, type ExportTable, type MethodInfo, type Project, type ValidationReport } from "../api/types";
import type { EditorTab } from "../model/issues";
import { canonical, type AnalysisContext } from "../state/analysisContext";
import { useAnalysisRecord } from "../state/useAnalysisRecord";
import { RankingChart, ContributionsChart, ScenarioComparisonChart, palette, formatValue } from "./results/ResultsCharts";
import { ContributionTable, CriterionDetails, DominanceView, PartialHeatmap, RankingTable } from "./results/ResultsTables";
import { AcceptabilityView } from "./results/AcceptabilityView";
import { ClassesView } from "./results/ClassesView";
import { AhpView } from "./results/AhpView";
import { FeasibilityView } from "./results/FeasibilityView";
import { FlowsView } from "./results/FlowsView";
import { useFeasibility } from "../state/useFeasibility";
import { useScreeningSummary } from "../state/useScreeningSummary";
import { ScreeningSummaryView } from "./results/ScreeningSummaryView";
import { ScreeningReportButton } from "./results/ScreeningReportButton";
import { saveDownload } from "./results/downloads";
import { panelsFor } from "./results/panels";
import { RunSettings } from "./AnalysisControls";
import { Caveat } from "./InfoDisclosure";
import { IssueText } from "./IssueText";

const TABLE_LABELS: Record<ExportTable, string> = {
  ranking: "Overall ranking", classes: "Classes", contributions: "Weighted contributions",
  partial_values: "Partial values and measurements", dominance: "Dominance matrix", comparison: "Base versus scenario",
  rank_acceptability: "Rank acceptability", class_acceptability: "Class acceptability", inputs_to_check: "Inputs to check",
  flows: "Outranking flows", criterion_flows: "Single-criterion flows", partial_order: "PROMETHEE I relations", explanation: "Explanation against MAVT",
  priorities: "AHP priorities", criterion_priorities: "Criterion priorities", local_priorities: "Local priorities by leaf", consistency: "Consistency",
};
const MAVT_TABLES: ExportTable[] = ["ranking", "contributions", "partial_values", "dominance", "comparison"];

interface Props {
  project: Project; context: AnalysisContext; validation: ValidationReport; weightTrial?: WeightTrial; onExploreMavt?: () => void;
  onSelectCriterion?: (id: string) => void;
  /** Registered methods from /api/meta; panels and CSV tables follow the viewed method's entry. */
  methods?: MethodInfo[];
  onOpenTab?: (tab: EditorTab) => void;
  onParameters?: (patch: Record<string, unknown>) => void;
  /** The reviewed dossier from the Evidence Workspace, when one is open: it feeds the summary's
   * open-question counts exactly as it feeds Open Questions. */
  workspaceDossier?: EvidenceDossier | null;
}
export function ResultsPanel({ project, context, validation, onSelectCriterion, methods, workspaceDossier, onParameters, onOpenTab, weightTrial, onExploreMavt }: Props) {
  const method = context.configuration.method;
  const localTrial = useWeightTrial(canonical({ fingerprint: context.fingerprint, configuration: context.configuration, dossier: workspaceDossier }));
  const trial = weightTrial ?? localTrial;
  const supported = method === "mavt" || method === "mavt_sorting";
  const trialRequest = useScreeningWhatIf(project, context, trial.ratings, workspaceDossier ?? null, trial.open && supported, trial.generation);
  const trialRecord = trial.active && trialRequest.status === "ready" && trialRequest.result.status === "available" ? trialRequest.result.record : null;
  const trialSummary = trial.active && trialRequest.status === "ready" && trialRequest.result.summary;
  const downloadGuard = useTrialDownloadGuard({ active: trial.active, generation: trial.generation });
  const info = methods?.find(m => m.name === method);
  const panels = panelsFor(method, info);
  const has = (id: string) => panels.shown.some(p => p.id === id);
  const tables = info?.export_tables ?? MAVT_TABLES;
  const missingSetup = validation.issues.some(i => ["NO_SORTING_MODEL", "PROMETHEE_NOT_STATED", "AHP_NOT_STATED"].includes(i.code));
  const evaluation = useAnalysisRecord(project, validation, context);
  const feasibility = useFeasibility(project, context.fingerprint);
  const screening = useScreeningSummary(project, context, workspaceDossier);
  const sections = useRef<Record<string, HTMLElement | null>>({});
  function jump(id: string) { const target = sections.current[id]; target?.scrollIntoView({ block: "start" }); target?.focus({ preventScroll: true }); }
  const fullRecord = evaluation.status === "ready" ? evaluation.result : null;
  // SMAA-2 and PROMETHEE II records carry acceptabilities or flows, not MAVT values: own views.
  const record = fullRecord && !isSmaaRecord(fullRecord) && !isPrometheeRecord(fullRecord) && !isAhpRecord(fullRecord) ? fullRecord : null;
  const ahpRecord = fullRecord && isAhpRecord(fullRecord) ? fullRecord : null;
  const smaaRecord = fullRecord && isSmaaRecord(fullRecord) ? fullRecord : null;
  const prometheeRecord = fullRecord && isPrometheeRecord(fullRecord) ? fullRecord : null;
  const unavailable = (t: ExportTable) => t === "explanation" && prometheeRecord !== null && !prometheeRecord.result.explanation.available;
  const [comparePartners, setComparePartners] = useState(false);
  const [selectedAlternative, setAlternative] = useState<string | null>(null);
  const [localCriterion, setLocalCriterion] = useState<string | null>(null);
  const [pair, setPair] = useState<{ first: string; second: string } | null>(null);
  const [presentation, setPresentation] = useState<AnalysisPresentation>({ sort: "rank", precision: "4", hidden_alternative_ids: [], hidden_criterion_ids: [] });
  const [chosenTable, setCsvTable] = useState<ExportTable>("ranking");
  const csvTable = tables.includes(chosenTable) ? chosenTable : tables[0] ?? "ranking";
  const [exporting, setExporting] = useState<string | null>(null);
  const [exportError, setExportError] = useState<{ key: string; message: string } | null>(null);
  const liveRecord = useRef<string | null>(null), exportController = useRef<AbortController | null>(null);
  const identity = fullRecord?.record_digest ?? null;
  useLayoutEffect(() => {
    liveRecord.current = identity;
    return () => { liveRecord.current = null; exportController.current?.abort(); };
  }, [identity]);
  function criterion(id: string) { if (onSelectCriterion) onSelectCriterion(id); else setLocalCriterion(id); }
  const selectedCriterion = onSelectCriterion ? context.criterionId : localCriterion;
  const result = record?.result;
  const view: AnalysisPresentation = { ...presentation,
    hidden_alternative_ids: presentation.hidden_alternative_ids.filter(id => fullRecord?.alternative_order.includes(id)),
    hidden_criterion_ids: presentation.hidden_criterion_ids.filter(id => result?.leaf_order.includes(id)),
  };
  const order = (view.sort === "project" ? record?.alternative_order : result?.ranking.map(a => a.alternative_id)) ?? [];
  const validAlternative = result?.alternatives.some(a => a.alternative_id === selectedAlternative) ? selectedAlternative : null;
  function toggle(kind: "hidden_alternative_ids" | "hidden_criterion_ids", id: string) {
    setPresentation(p => ({ ...p, [kind]: p[kind].includes(id) ? p[kind].filter(value => value !== id) : [...p[kind], id] }));
  }
  async function download(format: "json" | "csv") {
    const ticket = downloadGuard.ticket();
    if (!fullRecord || trial.active || ticket === null) return;
    const token = fullRecord.record_digest;
    exportController.current?.abort();
    const controller = new AbortController(); exportController.current = controller;
    setExporting(token); setExportError(null);
    try {
      const file = await api.exportAnalysis({ project: structuredClone(project), configuration: fullRecord.result.configuration,
        expected_project_fingerprint: fullRecord.result.project_fingerprint, expected_record_digest: token,
        format, table: csvTable, presentation: structuredClone(view) }, controller.signal);
      if (controller.signal.aborted || !downloadGuard.permits(ticket) || liveRecord.current !== token || exportController.current !== controller) return;
      saveDownload(file.blob, file.filename);
    } catch (error: unknown) {
      if (!controller.signal.aborted && downloadGuard.permits(ticket) && liveRecord.current === token) setExportError({ key: token, message: error instanceof Error ? error.message : String(error) });
    } finally { if (liveRecord.current === token && exportController.current === controller) setExporting(null); }
  }
  return <WeightTrialGate value={{ active: trial.active, generation: trial.generation, reset: trial.reset }}><section className="panel results-workspace" aria-label="Results">
    <h2>Results</h2>
    <WhatIfWeights trial={trial} request={trialRequest} supported={supported} onExplore={onExploreMavt}/>
    {trial.active && <><p className="note">What-if, not saved. Other Results views use the saved weights.</p><p className="muted small">Open-question counts reflect the saved weights</p><p>{RESET_DOWNLOAD}</p></>}
    {trial.active && project.weight_profiles.length >= 2 ? <p>Compare profiles: {RESET_TRIAL}</p> : project.weight_profiles.length >= 2 ? <label className="partner-toggle"><input type="checkbox" checked={comparePartners} onChange={event => setComparePartners(event.target.checked)}/> Compare profiles</label>
      : <p className="muted small">Two weight profiles are needed to compare profiles.</p>}
    {comparePartners && project.weight_profiles.length >= 2 && !trial.active && <PartnerComparison project={project} context={context} dossier={workspaceDossier ?? null}/>}

    {info?.capabilities.includes("acceptability") && <details><summary>Run settings</summary><RunSettings parameters={context.configuration.parameters} disabled={false} onChange={patch => onParameters?.({ ...context.configuration.parameters, ...patch })}/></details>}
    {trial.active ? <section className="screening-summary-section" aria-label="Screening summary"><h3>What-if screening summary</h3>
      {trialSummary ? <ScreeningSummaryView summary={trialSummary} project={project} hideOpenQuestions/> : <p role="status">{trialRequest.status === "loading" ? "Calculating what-if screening…" : "What-if screening unavailable. Reset to return to the saved reading."}</p>}
    </section> : <ScreeningSummarySection project={project} request={screening} collapsed={method !== "mavt" && method !== "mavt_sorting"}/>}
    {supported && <ScreeningReportButton project={project} context={context} dossier={workspaceDossier ?? null} trial={{ active: trial.active, generation: trial.generation }}/>}
    {record && result && has("overall") && <><h3 tabIndex={-1} ref={element => { sections.current.overall = element; }}>Overall values and competition ranks</h3>
      {trial.active ? trialRecord && <RankingChart record={trialRecord} view={view} order={trialRecord.result.ranking.map(row => row.alternative_id)} selectedAlternative={null} selectedCriterion={null} onAlternative={() => undefined} onCriterion={() => undefined}/>
        : <RankingChart record={record} view={view} order={order} selectedAlternative={validAlternative} selectedCriterion={selectedCriterion} onAlternative={setAlternative} onCriterion={criterion}/>}
      {trial.active && <p className="muted small">The table below uses the saved weights.</p>}
      <RankingTable record={record} order={order} precision="4" selectedAlternative={validAlternative} selectedCriterion={selectedCriterion} onAlternative={setAlternative} onCriterion={criterion}/></>}
    {(record || prometheeRecord || ahpRecord) && <nav className="results-jump" aria-label="Results views">{panels.shown.map(({ id, label }) =>
      <button type="button" key={id} onClick={() => jump(id)}>{label}</button>)}</nav>}
    {panels.shown.length === 0 && <p role="status">This version has no Results views for the method {info?.label ?? method}.</p>}
    {(panels.missing.length > 0 || (record && result)) && <details className="results-details"><summary>Details</summary>
      {record && result && <p className="note" aria-label="Results analysis context">{record.project_title} · project <code>{result.project_id}</code> · {result.method} · {record.scenario_name} · Resolved profile: {record.resolved_profile_name} ({result.weight_profile_id}) · Explicit profile: {result.configuration.weight_profile_id ?? "Automatic"} · revision <code>{result.project_fingerprint}</code></p>}
      {record && <details><summary>Exact engine values</summary><pre tabIndex={0} aria-label="Exact analysis record">{JSON.stringify(record, null, 2)}</pre></details>}
      {panels.shown.length > 0 && panels.missing.length > 0 && <p className="muted small" aria-label="Views not offered">{info?.label ?? method} does not offer: {panels.missing.map(p => p.label).join(", ")}.</p>}
    </details>}
    {missingSetup && <p role="status">{info?.label ?? method} is not set up for this study. {onOpenTab && <button type="button" onClick={() => onOpenTab(method === "ahp" ? "pairwise" : method === "promethee2" ? "outranking" : "classes")}>Open setup</button>}</p>}
    {evaluation.status === "blocked" && !missingSetup && <p role="status">The selected model has {evaluation.errors} validation error(s); complete it before analysing or exporting.</p>}
    {evaluation.status === "loading" && <p role="status">Calculating completed analysis…</p>}
    {evaluation.status === "error" && (missingSetup ? <p role="status">{info?.label ?? method} is not set up for this study. Configure its inputs in Builder view.</p> : <><p role="alert">{evaluation.message}</p>
      <button type="button" onClick={evaluation.retry}>Retry analysis</button></>)}
    {smaaRecord && <>
      <AcceptabilityView record={smaaRecord}/>
      <div className="results-controls" aria-label="Analysis downloads">
        <button type="button" disabled={trial.active || downloadGuard.disabled || exporting === identity} onClick={() => void download("json")}>Download analysis JSON</button>
        <label>CSV table<select aria-label="CSV table" value={csvTable} onChange={e => setCsvTable(e.target.value as ExportTable)}>{tables.map(t => <option key={t} value={t} disabled={t === "class_acceptability" && smaaRecord.result.classes.length === 0}>{TABLE_LABELS[t]}</option>)}</select></label>
        <button type="button" disabled={trial.active || downloadGuard.disabled || exporting === identity || csvTable === "class_acceptability" && smaaRecord.result.classes.length === 0} onClick={() => void download("csv")}>Download CSV</button>
        {exporting === identity && <span role="status">Verifying export context…</span>}
      </div>
      {exportError?.key === identity && <p role="alert">{exportError.message}</p>}
    </>}
    {prometheeRecord && <>
      <FlowsView record={prometheeRecord} show={has} register={(id, element) => { sections.current[id] = element; }}/>
      <div className="results-controls" aria-label="Analysis downloads">
        <button type="button" disabled={trial.active || downloadGuard.disabled || exporting === identity} onClick={() => void download("json")}>Download analysis JSON</button>
        <label>CSV table<select aria-label="CSV table" value={csvTable} onChange={e => setCsvTable(e.target.value as ExportTable)}>{tables.map(t => <option key={t} value={t} disabled={unavailable(t)}>{TABLE_LABELS[t]}</option>)}</select></label>
        <button type="button" disabled={trial.active || downloadGuard.disabled || exporting === identity || unavailable(csvTable)} onClick={() => void download("csv")}>Download CSV</button>
        {exporting === identity && <span role="status">Verifying export context…</span>}
      </div>
      {exportError?.key === identity && <p role="alert">{exportError.message}</p>}
    </>}
    {ahpRecord && <>
      <AhpView record={ahpRecord} show={has} register={(id, element) => { sections.current[id] = element; }}
        criterionName={id => project.criteria.find(c => c.id === id)?.name ?? id}/>
      <div className="results-controls" aria-label="Analysis downloads">
        <button type="button" disabled={trial.active || downloadGuard.disabled || exporting === identity} onClick={() => void download("json")}>Download analysis JSON</button>
        <label>CSV table<select aria-label="CSV table" value={csvTable} onChange={e => setCsvTable(e.target.value as ExportTable)}>{tables.map(t => <option key={t} value={t}>{TABLE_LABELS[t]}</option>)}</select></label>
        <button type="button" disabled={trial.active || downloadGuard.disabled || exporting === identity} onClick={() => void download("csv")}>Download CSV</button>
        {exporting === identity && <span role="status">Verifying export context…</span>}
      </div>
      {exportError?.key === identity && <p role="alert">{exportError.message}</p>}
    </>}
    {project.requirements && project.requirements.length > 0 && <section aria-label="Feasibility beside the ranking" className="feasibility-beside">
      <h3>Feasibility</h3>
      {feasibility.status === "loading" && <p role="status">Checking requirements…</p>}
      {feasibility.status === "error" && <><p role="alert">{feasibility.message}</p><button type="button" onClick={feasibility.retry}>Retry feasibility</button></>}
      {feasibility.status === "ready" && <FeasibilityView result={feasibility.result} project={project}/>}
    </section>}
    {record && result && <>
      <Caveat id="mavt" caption="Preference values under this profile; not probabilities or predictions.">Scores are compensatory MAVT preference values on a common 0–1 scale, not probabilities, success rates or financial returns. Competition ranks come from the engine; ties share a rank. All charts and downloads use this one completed record.</Caveat>
      <div className="results-controls">
        <label>Table order<select aria-label="Results order" value={view.sort} onChange={e => setPresentation(p => ({ ...p, sort: e.target.value as AnalysisPresentation["sort"] }))}><option value="rank">Engine ranking order</option><option value="project">Project alternative order</option></select></label>
        <label title="Controls SVG labels. Primary values use four decimals; exact values are in Details.">SVG label precision<select aria-label="Results precision" value={view.precision} onChange={e => setPresentation(p => ({ ...p, precision: e.target.value as AnalysisPresentation["precision"] }))}><option value="4">4 decimals</option><option value="full">Full precision</option></select></label>
        <label>Alternative to inspect<select aria-label="Alternative to inspect" value={validAlternative ?? ""} onChange={e => setAlternative(e.target.value || null)}><option value="">Choose alternative…</option>{result.alternatives.map(a => <option key={a.alternative_id} value={a.alternative_id}>{a.name} ({a.alternative_id})</option>)}</select></label>
        <label>Criterion to inspect<select aria-label="Criterion to inspect" value={record.criteria.some(c => c.criterion_id === selectedCriterion) ? selectedCriterion ?? "" : ""} onChange={e => { if (e.target.value) criterion(e.target.value); }}><option value="">Choose leaf criterion…</option>{record.criteria.map(c => <option key={c.criterion_id} value={c.criterion_id}>{c.path_names.join(" / ")}</option>)}</select></label>
      </div>
      <div className="results-controls" aria-label="Analysis downloads">
        <button type="button" disabled={trial.active || downloadGuard.disabled || exporting === identity} onClick={() => void download("json")}>Download analysis JSON</button>
        <label>CSV table<select aria-label="CSV table" value={csvTable} onChange={e => setCsvTable(e.target.value as ExportTable)}>{tables.map(t => <option key={t} value={t} disabled={t === "comparison" && !record.comparison}>{TABLE_LABELS[t]}</option>)}</select></label>
        <button type="button" disabled={trial.active || downloadGuard.disabled || exporting === identity || csvTable === "comparison" && !record.comparison} onClick={() => void download("csv")}>Download CSV</button>
        {exporting === identity && <span role="status">Verifying export context…</span>}
      </div>
      <details><summary>Export data and CSV text policy</summary><p className="muted small">JSON includes the source project for reproduction. Numerical downloads contain all alternatives and leaves, with current table order and presentation metadata; chart filters never change values. CSV quotes fields, escapes controls and prefixes potentially active text with TEXT:. JSON retains original text.</p></details>
      {exportError?.key === identity && <p role="alert">{exportError.message}</p>}
      <details className="results-visibility"><summary>Chart visibility and accessible criterion legend</summary>
        <p>Visibility affects ranking/contribution bars only. Hidden criteria remain hatched gaps in the complete stack; tables and the heatmap retain every value. Selecting a criterion also highlights its heatmap column and definition.</p>
        <fieldset><legend>Alternative bars</legend>{result.alternatives.map(a => <label key={a.alternative_id}><input type="checkbox" aria-label={`Show alternative ${a.name}`} checked={!view.hidden_alternative_ids.includes(a.alternative_id)} onChange={() => toggle("hidden_alternative_ids", a.alternative_id)}/>{a.name} · {a.alternative_id}</label>)}</fieldset>
        <fieldset><legend>Leaf contribution segments</legend>{record.criteria.map((c, i) => <label key={c.criterion_id}><input type="checkbox" aria-label={`Show criterion ${c.name}`} checked={!view.hidden_criterion_ids.includes(c.criterion_id)} onChange={() => toggle("hidden_criterion_ids", c.criterion_id)}/><span className="legend-swatch" aria-hidden="true" style={{ background: palette[i % palette.length] }}/><button type="button" onClick={() => criterion(c.criterion_id)}>{c.path_names.join(" / ")}{selectedCriterion === c.criterion_id ? " — selected" : ""}</button></label>)}</fieldset>
      </details>
      <p aria-label="Chart visibility summary">Hidden alternative bars: {view.hidden_alternative_ids.join(", ") || "none"}. Hidden criterion segments: {view.hidden_criterion_ids.join(", ") || "none"}. Totals and ranks include all criteria.</p>
      {record.record_version === "2" && has("classes") && <>
        <h3 tabIndex={-1} ref={element => { sections.current.classes = element; }}>Classes</h3>
        <ClassesView result={record.result} order={order} precision="4" selectedAlternative={validAlternative} onAlternative={setAlternative}/>
      </>}
      {has("inspection") && <div ref={element => { sections.current.inspection = element; }} tabIndex={-1}><CriterionDetails record={record} criterion={record.criteria.find(c => c.criterion_id === selectedCriterion)} alternativeId={validAlternative} precision="4"/></div>}
      {has("contributions") && <><h3 tabIndex={-1} ref={element => { sections.current.contributions = element; }}>Where each value comes from</h3><p>Every segment is the engine’s weighted leaf contribution. Full stacks reconcile with engine totals; hidden segments are not renormalised. Use the legend or a segment to inspect its partial value, global weight and value-function context.</p>
      <ContributionsChart record={record} view={view} order={order} selectedAlternative={validAlternative} selectedCriterion={selectedCriterion} onAlternative={setAlternative} onCriterion={criterion}/>
      <ContributionTable record={record} order={order} precision="4" selectedAlternative={validAlternative} selectedCriterion={selectedCriterion} onAlternative={setAlternative} onCriterion={criterion}/></>}
      {has("partial") && <><h3 tabIndex={-1} ref={element => { sections.current.partial = element; }}>Partial preference values and raw measurements</h3>
      <PartialHeatmap record={record} order={order} precision="4" selectedAlternative={validAlternative} selectedCriterion={selectedCriterion} onAlternative={setAlternative} onCriterion={criterion}/></>}
      {has("dominance") && <><h3 tabIndex={-1} ref={element => { sections.current.dominance = element; }}>Dominance diagnostics</h3>
      <DominanceView record={record} order={order} precision="4" pair={pair} selectedAlternative={validAlternative} selectedCriterion={selectedCriterion} onAlternative={setAlternative} onCriterion={criterion} onPair={(first, second) => { setPair({ first, second }); setAlternative(first); }}/></>}
      {has("comparison") && <><h3 tabIndex={-1} ref={element => { sections.current.comparison = element; }}>Base versus selected scenario</h3>
      {record.comparison ? <>
        <ScenarioComparisonChart comparison={record.comparison} alternatives={project.alternatives} projectId={result.project_id} onAlternative={setAlternative} selectedAlternative={validAlternative}/>
        <p>Base profile: {record.comparison.baseline.weight_profile_id}. Scenario profile: {record.comparison.scenarios[0]?.weight_profile_id}. {record.comparison.baseline.weight_profile_id !== record.comparison.scenarios[0]?.weight_profile_id ? "Changes may reflect different preference weights as well as functions." : "Both contexts use the same profile."} Applied overrides: {Object.keys(record.comparison.scenarios[0]?.applied_overrides ?? {}).join(", ") || "none"}.</p>
        <div className="table-scroll" tabIndex={0}><table className="grid" aria-label="Results scenario comparison"><thead><tr><th>Alternative / ID</th><th>Base value</th><th>Scenario value</th><th>Change</th><th>Base rank</th><th>Scenario rank</th></tr></thead><tbody>{order.map(id => {
          const comparison = record.comparison; const scenario = comparison?.scenarios[0]; if (!comparison || !scenario) return null;
          return <tr key={id}><th scope="row">{result.alternatives.find(a => a.alternative_id === id)?.name} <code>{id}</code></th><td>{formatValue(comparison.baseline.values[id] ?? 0, "4")}</td><td>{formatValue(scenario.values[id] ?? 0, "4")}</td><td>{formatValue(scenario.delta_from_baseline[id] ?? 0, "4")}</td><td>{comparison.baseline.rank_by_alternative[id]}</td><td>{scenario.rank_by_alternative[id]}</td></tr>;
        })}</tbody></table></div>
      </> : <p>{context.scenarioId ? "The selected scenario is evaluable, but Base comparison is unavailable. See the diagnostics; no Base result is substituted." : "Select a scenario above to compare it with Base. The saved default does not override an explicit Base view."}</p>}</>}
      <h3>Notes from the analysis</h3><ul className="issue-list inline" aria-label="Result diagnostics">{[...result.diagnostics, ...record.comparison_diagnostics, ...(record.comparison?.baseline.diagnostics ?? [])].map((d, i) => <li key={i} className={d.severity}><IssueText code={d.code} message={d.message} path={d.path}/></li>)}</ul>
      <details className="assumptions"><summary>Assumptions and provenance</summary><ul>{result.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul><p>{result.weight_basis}</p>
        <p>Record version {record.record_version}; digest <code>{record.record_digest}</code>; calculation {record.calculation_path}. Configuration: <code>{JSON.stringify(result.configuration)}</code>.</p>
        <p>Values here use the evaluation / math.fsum path. The sensitivity sweep’s plotting path can differ by one binary rounding unit; sweep values are not combined into this record.</p></details>
    </>}
  </section></WeightTrialGate>;
}

/** The summary leads Results for MAVT and sorting; under another method it stays available, collapsed
 * and labelled as MAVT's reading, so it is never mistaken for that method's own result. */
export function ScreeningSummarySection({ project, request, collapsed = false }: {
  project: Project; request: ReturnType<typeof useScreeningSummary>; collapsed?: boolean;
}) {
  const body = <>
    {request.status === "loading" && <p role="status">Preparing the screening summary…</p>}
    {request.status === "error" && <><p role="alert">{request.message}</p><button type="button" onClick={request.retry}>Retry summary</button></>}
    {request.status === "ready" && <ScreeningSummaryView summary={request.result} project={project}/>}
  </>;
  return collapsed
    ? <details className="screening-summary-section" aria-label="MAVT screening summary"><summary>MAVT screening summary</summary>{body}</details>
    : <section className="screening-summary-section" aria-label="Screening summary"><h3>Screening summary</h3>{body}</section>;
}
