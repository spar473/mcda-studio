import type { AnySensitivityResult, SensitivityResult } from "../api/types";

const LEFT = 62, TOP = 16, WIDTH = 520, HEIGHT = 250, BOTTOM = TOP + HEIGHT;

export const SERIES_COLOURS = [
  "#2f6fb5", "#b5522f", "#2f8f5b", "#8a4fb5", "#b58a2f", "#2f9aa8", "#b52f6f", "#5b6b7a",
];
export const colourFor = (index: number): string =>
  SERIES_COLOURS[index % SERIES_COLOURS.length] ?? "#2f6fb5";

export interface ChartExtent { lo: number; hi: number }

/** Y-extent across the *visible* series (and any class boundaries); never a renormalisation. */
export function valueExtent(result: SensitivityResult, visible: readonly string[], boundaries: readonly number[] = []): ChartExtent {
  const all = [...visible.flatMap((a) => result.values[a] ?? []), ...boundaries];
  if (all.length === 0) return { lo: 0, hi: 1 };
  const lo = Math.min(...all), hi = Math.max(...all);
  if (!(hi - lo > 1e-9)) return { lo: Math.max(0, lo - 0.05), hi: Math.min(1, hi + 0.05) };
  const pad = (hi - lo) * 0.12;
  return { lo: Math.max(0, lo - pad), hi: Math.min(1, hi + pad) };
}

interface Props {
  result: AnySensitivityResult;
  names: Map<string, string>;
  visible: string[];
  cursor: number;
  onCursor: (weight: number) => void;
}

export function SensitivityChart({ result, names, visible, cursor, onCursor }: Props) {
  const bands = result.method === "mavt_sorting" ? result.classes : [];
  const boundaries = bands.flatMap((b) => b.lower_boundary === null ? [] : [b.lower_boundary]);
  const extent = valueExtent(result, visible, boundaries);
  const x = (t: number) => LEFT + t * WIDTH;
  const y = (v: number) => BOTTOM - ((v - extent.lo) / (extent.hi - extent.lo)) * HEIGHT;
  const order = result.baseline_ranking;
  const path = (alt: string) => (result.values[alt] ?? [])
    .map((v, i) => `${i === 0 ? "M" : "L"}${x(result.grid[i] ?? 0).toFixed(2)},${y(v).toFixed(2)}`).join(" ");

  // Snap a pointer position to the nearest server grid point: the chart never invents a weight.
  const snap = (clientX: number, target: SVGSVGElement) => {
    const box = target.getBoundingClientRect();
    const t = ((clientX - box.left) / box.width * (WIDTH + LEFT + 24) - LEFT) / WIDTH;
    let best = result.grid[0] ?? 0;
    for (const g of result.grid) if (Math.abs(g - t) < Math.abs(best - t)) best = g;
    onCursor(best);
  };

  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const yTicks = [extent.lo, (extent.lo + extent.hi) / 2, extent.hi];
  return <svg className="sensitivity-chart" viewBox={`0 0 ${LEFT + WIDTH + 24} ${BOTTOM + 48}`}
    role="img" data-testid="sensitivity-chart"
    aria-label={`Overall value against the local weight of ${result.node_name}. The equivalent numbers are in the table below.`}
    onClick={(e) => { snap(e.clientX, e.currentTarget); }}>
    <rect x={LEFT} y={TOP} width={WIDTH} height={HEIGHT} className="plot-area"/>
    {ticks.map((t) => <g key={`x${t}`}>
      <line x1={x(t)} y1={BOTTOM} x2={x(t)} y2={BOTTOM + 5}/>
      <text x={x(t)} y={BOTTOM + 18} textAnchor="middle" className="tick">{t.toFixed(2)}</text>
    </g>)}
    {yTicks.map((v, i) => <g key={`y${i}`}>
      <line x1={LEFT - 5} y1={y(v)} x2={LEFT} y2={y(v)}/>
      <text x={LEFT - 9} y={y(v) + 4} textAnchor="end" className="tick">{v.toFixed(3)}</text>
    </g>)}
    <text x={LEFT + WIDTH / 2} y={BOTTOM + 40} textAnchor="middle" className="axis-label">
      Local weight of {result.node_name} (share of its sibling group)
    </text>
    <text x={14} y={TOP + HEIGHT / 2} textAnchor="middle" className="axis-label"
      transform={`rotate(-90 14 ${TOP + HEIGHT / 2})`}>Overall MAVT value</text>

    {/* Class bands and first class changes from the engine's boundaries and roots. */}
    {bands.map((b, i) => {
      const top = y(Math.min(b.upper_boundary ?? extent.hi, extent.hi)), bottom = y(Math.max(b.lower_boundary ?? extent.lo, extent.lo));
      return bottom > top && <g key={b.class_id} data-testid={`class-band-${b.class_id}`}>
        <rect x={LEFT} y={top} width={WIDTH} height={bottom - top} className={i % 2 ? "class-band alt" : "class-band"}/>
        {b.lower_boundary !== null && <line className="class-boundary" x1={LEFT} x2={LEFT + WIDTH} y1={y(b.lower_boundary)} y2={y(b.lower_boundary)}/>}
        <text x={LEFT + WIDTH - 4} y={top + 12} textAnchor="end" className="tick">{b.name}</text>
      </g>;
    })}
    {result.method === "mavt_sorting" && result.class_changes.flatMap((c) => visible.includes(c.alternative_id)
      ? [c.first_change_up, c.first_change_down].flatMap((change) => {
        const boundary = change && bands.find((b) => b.class_id === change.boundary_class_id)?.lower_boundary;
        return change && boundary !== null && boundary !== undefined
          ? [<circle key={`${c.alternative_id}-${String(change.weight)}`} className="class-change" cx={x(change.weight)} cy={y(boundary)} r={4}
            data-testid={`class-change-${c.alternative_id}`}><title>{names.get(c.alternative_id) ?? c.alternative_id}: class changes at {change.weight}</title></circle>]
          : [];
      }) : [])}
    {/* Exact crossovers from the engine; never read off the grid. */}
    {result.rank_change_points.map((t) => <line key={`c${t}`} className="crossover-line"
      x1={x(t)} y1={TOP} x2={x(t)} y2={BOTTOM}/>)}
    <line className="baseline-line" x1={x(result.base_weight)} y1={TOP} x2={x(result.base_weight)} y2={BOTTOM}/>
    <text x={x(result.base_weight)} y={TOP - 4} textAnchor="middle" className="tick">baseline</text>
    <line className="cursor-line" data-testid="cursor-line" x1={x(cursor)} y1={TOP} x2={x(cursor)} y2={BOTTOM}/>

    {order.map((alt, i) => visible.includes(alt) && <path key={alt} d={path(alt)} fill="none"
      stroke={colourFor(i)} strokeWidth={2} data-testid={`series-${alt}`}>
      <title>{names.get(alt) ?? alt}</title>
    </path>)}
  </svg>;
}
