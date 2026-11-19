import { useId, useRef, type ReactNode } from "react";
import type { ValueRecord, AnalysisPresentation, Alternative, ClassBand, ScenarioComparison } from "../../api/types";
import { saveDownload } from "./downloads";

export const palette = ["#236b8e", "#a86114", "#5b7a32", "#8a508b", "#267b74", "#a34c57", "#6264a5", "#736044"];
export const formatValue = (value: number, precision: AnalysisPresentation["precision"]) => precision === "full" ? String(value) : value.toFixed(4);
export const chunks = (text: string, length = 90) => text.match(new RegExp(`.{1,${String(length)}}`, "gu")) ?? [""];

interface FrameProps {
  title: string; lines: string[]; height: number; children: ReactNode;
  filename: string; metadata: unknown; exportLabel: string; legend?: { label: string; colour: string }[];
}
function Frame({ title, lines, height, children, filename, metadata, exportLabel, legend = [] }: FrameProps) {
  const ref = useRef<SVGSVGElement>(null);
  const titleId = useId();
  const wrapped = lines.flatMap(line => chunks(line));
  const top = 45 + wrapped.length * 17;
  const legendHeight = Math.ceil(legend.length / 4) * 42;
  function download() {
    if (!ref.current) return;
    const source = new XMLSerializer().serializeToString(ref.current);
    saveDownload(new Blob([source], { type: "image/svg+xml;charset=utf-8" }), filename);
  }
  return <figure className="results-figure">
    <figcaption><strong>{title}</strong> <button type="button" onClick={download}>{exportLabel}</button></figcaption>
    <div className="results-chart-scroll" tabIndex={0} role="region" aria-label={`${title} scroll area`}>
      <svg ref={ref} viewBox={`0 0 1100 ${String(top + legendHeight + height)}`}
        role="group" aria-labelledby={titleId} className="results-chart">
        <title id={titleId}>{title}</title>
        <desc>{lines.join(". ")} Common preference-value axis from zero to one. Numerical tables accompany this chart.</desc>
        <metadata>{JSON.stringify(metadata)}</metadata>
        <rect width="1100" height={top + legendHeight + height} fill="white"/>
        <g fontFamily="system-ui, sans-serif" fontSize="12" fill="#1c2025">
          <text x="12" y="20" fontSize="15" fontWeight="600">{title}</text>
          {wrapped.map((line, i) => <text key={i} x="12" y={40 + i * 17}>{line}</text>)}
          {legend.length > 0 && <g role="list" aria-label="Leaf criterion legend">{legend.map((entry, i) => <g key={entry.label} role="listitem" aria-label={entry.label} transform={`translate(${String((i % 4) * 270 + 10)} ${String(top + Math.floor(i / 4) * 42)})`}>
            <title>{entry.label}</title><rect width="12" height="12" fill={entry.colour} stroke="#596773"/>
            <text x="18" y="11">{chunks(entry.label, 34).slice(0, 2).map((line, j) => <tspan key={j} x="18" dy={j ? 15 : 0}>{line}</tspan>)}</text>
          </g>)}</g>}
          <g transform={`translate(0 ${String(top + legendHeight)})`}>{children}</g>
        </g>
      </svg>
    </div>
  </figure>;
}
function Axis({ y }: { y: number }) {
  return <g aria-label="Preference value axis zero to one">
    {[0, .25, .5, .75, 1].map(value => <g key={value}>
      <line x1={280 + value * 650} x2={280 + value * 650} y1="0" y2={y} stroke="#e3e7eb"/>
      <text x={280 + value * 650} y={y + 18} textAnchor="middle">{value}</text>
    </g>)}<text x="605" y={y + 42} textAnchor="middle">MAVT preference value (0–1, dimensionless)</text>
  </g>;
}
/** Class bands behind value bars: positions come from the engine's boundary values only. */
function ClassBands({ bands, height }: { bands: readonly ClassBand[]; height: number }) {
  return <g aria-label="Class bands" data-testid="class-bands">
    {bands.map((band, i) => {
      const x0 = 280 + (band.lower_boundary ?? 0) * 650, x1 = 280 + (band.upper_boundary ?? 1) * 650;
      return <g key={band.class_id} data-class-id={band.class_id}>
        <rect x={x0} y={0} width={Math.max(0, x1 - x0)} height={height} fill={i % 2 ? "#e8eef3" : "#f6f8fa"}/>
        {band.lower_boundary !== null && <line x1={x0} x2={x0} y1={0} y2={height} stroke="#596773" strokeDasharray="4 3"/>}
        <text x={(x0 + x1) / 2} y={height + 62} textAnchor="middle">{band.name}</text>
      </g>;
    })}
  </g>;
}
export const classLine = (bands: readonly ClassBand[]) => `Classes (best first): ${bands.map(b =>
  b.lower_boundary === null ? `${b.name} below` : `${b.name} from ${String(b.lower_boundary)}`).join(", ")}. A value within 1e-12 of a boundary goes to the higher class.`;
const keyboard = (event: React.KeyboardEvent<SVGGElement | SVGRectElement>, action: () => void) => {
  if (event.key === "Enter" || event.key === " ") { event.preventDefault(); action(); }
};
function AlternativeLabel({ name, selected, y }: { name: string; selected: boolean; y: number }) {
  return <text x="8" y={y} fontWeight={selected ? "700" : "400"}>
    <title>{name}</title>{chunks(name, 32).slice(0, 2).map((line, i) => <tspan key={i} x="8" dy={i ? 15 : 0}>{line}</tspan>)}
    {selected && <tspan x="8" dy="15">Selected</tspan>}
  </text>;
}
const contextLines = (record: ValueRecord, view: AnalysisPresentation) => [
  `Project: ${record.result.project_id} · ${record.project_title}`,
  `Revision: ${record.result.project_fingerprint}`,
  `Method: ${record.result.method} · Scenario: ${record.result.scenario_id ?? "Base"} · Resolved profile: ${record.result.weight_profile_id ?? "none"} · Explicit profile: ${record.result.configuration.weight_profile_id ?? "Automatic"}`,
  `Hidden alternatives: ${view.hidden_alternative_ids.join(", ") || "none"}. Hidden criteria: ${view.hidden_criterion_ids.join(", ") || "none"}. Model totals and ranks are unchanged.`,
];

interface ChartsProps {
  record: ValueRecord; view: AnalysisPresentation; order: string[];
  selectedAlternative: string | null; selectedCriterion: string | null;
  onAlternative: (id: string) => void; onCriterion: (id: string) => void;
}
export function RankingChart({ record, view, order, selectedAlternative, onAlternative }: ChartsProps) {
  const details = new Map(record.result.alternatives.map(a => [a.alternative_id, a]));
  const shown = order.filter(id => !view.hidden_alternative_ids.includes(id));
  const bands = record.record_version === "2" ? record.result.classes : null;
  return <Frame title="Overall MAVT values" lines={bands ? [...contextLines(record, view), classLine(bands)] : contextLines(record, view)}
    height={shown.length * 62 + 70 + (bands ? 30 : 0)}
    filename={`mcda-${record.result.project_id}-${record.record_digest.slice(0, 12)}-ranking.svg`}
    metadata={{ record_digest: record.record_digest, result: record.result, presentation: view }} exportLabel="Download ranking SVG">
    {bands && <ClassBands bands={bands} height={shown.length * 62}/>}
    <Axis y={shown.length * 62}/>
    {shown.map((id, i) => {
      const alt = details.get(id); if (!alt) return null;
      const selected = id === selectedAlternative;
      return <g key={id} role="button" tabIndex={0} aria-label={`Inspect alternative ${alt.name} (${id}), rank ${String(alt.rank)}, value ${String(alt.overall_value)}`}
        onClick={() => onAlternative(id)} onKeyDown={e => keyboard(e, () => onAlternative(id))} data-alternative-id={id}>
        <AlternativeLabel name={alt.name} selected={selected} y={i * 62 + 16}/>
        <rect x="280" y={i * 62 + 7} width={alt.overall_value * 650} height="27" fill="#236b8e" stroke={selected ? "#111" : "none"} strokeWidth="3"/>
        <text x="945" y={i * 62 + 25}>{formatValue(alt.overall_value, view.precision)} · rank {alt.rank}</text>
      </g>;
    })}
  </Frame>;
}

export function ContributionsChart({ record, view, order, selectedAlternative, selectedCriterion, onAlternative, onCriterion }: ChartsProps) {
  const details = new Map(record.result.alternatives.map(a => [a.alternative_id, a]));
  const shown = order.filter(id => !view.hidden_alternative_ids.includes(id));
  return <Frame title="Weighted leaf contributions" lines={contextLines(record, view)} height={shown.length * 62 + 70}
    filename={`mcda-${record.result.project_id}-${record.record_digest.slice(0, 12)}-contributions.svg`}
    metadata={{ record_digest: record.record_digest, result: record.result, presentation: view }}
    legend={record.criteria.map((criterion, i) => ({ label: `${view.hidden_criterion_ids.includes(criterion.criterion_id) ? "[hidden] " : ""}${criterion.name} (${criterion.criterion_id})`, colour: view.hidden_criterion_ids.includes(criterion.criterion_id) ? "#eee" : palette[i % palette.length] ?? "#236b8e" }))}
    exportLabel="Download contributions SVG">
    <defs><pattern id={`hidden-${record.record_digest}`} width="6" height="6" patternUnits="userSpaceOnUse"><path d="M0 6L6 0" stroke="#9da8b0" strokeWidth="1"/></pattern></defs>
    <Axis y={shown.length * 62}/>
    {shown.map((id, i) => {
      const alt = details.get(id); if (!alt) return null;
      let offset = 0; // coordinate layout only; totals always use alt.overall_value from Python
      return <g key={id} data-alternative-id={id}>
        <AlternativeLabel name={alt.name} selected={id === selectedAlternative} y={i * 62 + 16}/>
        {record.criteria.map((criterion, index) => {
          const value = alt.weighted_contributions[criterion.criterion_id]; if (value === undefined) return null;
          const x = 280 + offset * 650; offset += value;
          const hidden = view.hidden_criterion_ids.includes(criterion.criterion_id);
          return <rect key={criterion.criterion_id} x={x} y={i * 62 + 7} width={value * 650} height="27"
            data-criterion-id={criterion.criterion_id} data-contribution={value} data-hidden={hidden}
            fill={hidden ? `url(#hidden-${record.record_digest})` : palette[index % palette.length]}
            stroke={criterion.criterion_id === selectedCriterion ? "#111" : "white"} strokeWidth={criterion.criterion_id === selectedCriterion ? 2 : 1}
            role="button" tabIndex={0} aria-label={`${hidden ? "Hidden criterion" : "Inspect contribution"} ${criterion.name} (${criterion.criterion_id}) for ${alt.name}: ${String(value)}`}
            onClick={() => { onAlternative(id); onCriterion(criterion.criterion_id); }} onKeyDown={e => keyboard(e, () => { onAlternative(id); onCriterion(criterion.criterion_id); })}>
            <title>{criterion.path_names.join(" / ")}: {String(value)}; partial {String(alt.partial_values[criterion.criterion_id])}; global weight {String(record.result.global_weights[criterion.criterion_id])}{hidden ? " (hidden, unrenormalised gap)" : ""}</title>
          </rect>;
        })}
        <text x="945" y={i * 62 + 25}>{formatValue(alt.overall_value, view.precision)} · rank {alt.rank}</text>
      </g>;
    })}
  </Frame>;
}

/** The existing selected-scenario-versus-Base contract; no frontend score or rank calculation. */
export function ScenarioComparisonChart({ comparison, alternatives, projectId, onAlternative, selectedAlternative = null }: {
  comparison: ScenarioComparison; alternatives: Pick<Alternative, "id" | "name">[]; projectId: string;
  onAlternative?: (id: string) => void; selectedAlternative?: string | null;
}) {
  const scenario = comparison.scenarios[0]; if (!scenario) return null;
  const lines = [
    `Project: ${projectId}`,
    `Revision: ${comparison.project_fingerprint}`,
    `Base profile: ${comparison.baseline.weight_profile_id ?? "none"} · Scenario: ${scenario.scenario_id ?? "Base"} · Scenario profile: ${scenario.weight_profile_id ?? "none"}`,
    `Winner change: ${scenario.winner_differs_from_baseline ? "yes" : "no"}; ranking change: ${scenario.ranking_differs_from_baseline ? "yes" : "no"}. Hidden alternatives: none.`,
    "Base clears the scenario and retains any explicitly selected profile. Blue: Base. Amber: scenario. All values are engine preference values.",
  ];
  return <Frame title="Base versus selected scenario" lines={lines} height={alternatives.length * 76 + 70}
    metadata={{ project_id: projectId, comparison, hidden_alternative_ids: [], calculation_path: "mavt.math_fsum.v1" }}
    filename={`mcda-${scenario.scenario_id ?? "base"}-${comparison.project_fingerprint.slice(0, 12)}-comparison.svg`} exportLabel="Download comparison SVG">
    <Axis y={alternatives.length * 76}/>
    {alternatives.map((a, i) => <g key={a.id} data-alternative-id={a.id} role={onAlternative ? "button" : undefined}
      tabIndex={onAlternative ? 0 : undefined} aria-label={`${a.name}: Base ${String(comparison.baseline.values[a.id])}; scenario ${String(scenario.values[a.id])}; change ${String(scenario.delta_from_baseline[a.id])}`}
      onClick={() => onAlternative?.(a.id)} onKeyDown={e => keyboard(e, () => onAlternative?.(a.id))}>
      <AlternativeLabel name={a.name} selected={a.id === selectedAlternative} y={i * 76 + 18}/>
      <rect x="280" y={i * 76 + 5} width={(comparison.baseline.values[a.id] ?? 0) * 650} height="17" fill="#236b8e"/>
      <rect x="280" y={i * 76 + 27} width={(scenario.values[a.id] ?? 0) * 650} height="17" fill="#a86114"/>
      <text x="945" y={i * 76 + 18}>Base {comparison.baseline.values[a.id]?.toFixed(4)} · r{comparison.baseline.rank_by_alternative[a.id]}</text>
      <text x="945" y={i * 76 + 38}>Scenario {scenario.values[a.id]?.toFixed(4)} · r{scenario.rank_by_alternative[a.id]}</text>
      <text x="945" y={i * 76 + 58}>Δ {scenario.delta_from_baseline[a.id]?.toFixed(4)}</text>
    </g>)}
  </Frame>;
}
