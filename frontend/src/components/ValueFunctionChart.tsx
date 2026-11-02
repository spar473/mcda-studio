import { useRef, useState } from "react";
import type { ValueFunctionPreview } from "../api/types";
import { candidateFromDraft, moveHandle, type ValueDraft } from "../model/valueDraft";

export interface PlotExtent { lower: number; upper: number }
export function plotExtent(lower: number, upper: number): PlotExtent | null {
  const span = upper - lower;
  if (!(span > 0) || !Number.isFinite(span)) return null;
  const lo = lower - span * .15, hi = upper + span * .15;
  return Number.isFinite(lo) && Number.isFinite(hi) ? { lower: lo, upper: hi } : { lower, upper };
}
interface Handle { x: number; value: number }
interface Props {
  draft: ValueDraft; onChange: (draft: ValueDraft) => void; preview: ValueFunctionPreview | null;
  extent: PlotExtent | null; onGesture: (active: boolean) => void;
  selected: number | null; onSelect: (index: number) => void; onRemove: (index: number) => void;
  onInsert: (x: number, value: number) => void;
  lockScale?: boolean;
  alternativeNames: Record<string, string>;
}
const LEFT = 65, TOP = 28, WIDTH = 500, HEIGHT = 235;

export function ValueFunctionChart({ draft, onChange, preview, extent, onGesture, selected, onSelect, onRemove, onInsert, alternativeNames, lockScale = false }: Props) {
  const svg = useRef<SVGSVGElement>(null);
  const gesture = useRef<{ index: number; snapshot: ValueDraft; handle: Handle } | null>(null);
  const [dragging, setDragging] = useState(false);
  const parsed = candidateFromDraft(draft);
  const vf = parsed.candidate.value_function;
  const labelled = vf.kind === "qualitative";
  // Endpoint values for affine/direct functions come from server samples, never a local evaluator.
  const [endpoints, setEndpoints] = useState<Handle[]>([]);
  const [seenPreview, setSeenPreview] = useState(preview);
  if (seenPreview !== preview) {
  setSeenPreview(preview);
  if (preview?.curve_ready && !labelled && vf.kind !== "piecewise_linear") {
    const first = preview.samples[0], last = preview.samples[preview.samples.length - 1];
    if (typeof first?.measurement === "number" && typeof last?.measurement === "number") setEndpoints([
      { x: first.measurement, value: first.partial_value }, { x: last.measurement, value: last.partial_value }]);
  }
  }
  let handles: Handle[];
  if (vf.kind === "piecewise_linear") handles = vf.points.map((p) => ({ x: p.x, value: p.value }));
  else if (vf.kind === "qualitative") handles = draft.scale.labels.map((label, i) => ({ x: i, value: vf.mapping[label] ?? NaN }));
  else handles = endpoints.map((h, i) => ({ ...h, x: vf.kind === "direct_rating" ? i === 0 ? vf.min_rating : vf.max_rating :
    i === 0 ? parsed.candidate.scale.lower ?? h.x : parsed.candidate.scale.upper ?? h.x }));
  const canMove = (vf.kind !== "linear" || !lockScale && draft.scale.anchor_mode === "fixed");
  const px = (x: number) => labelled ? LEFT + ((x + .5) / Math.max(1, draft.scale.labels.length)) * WIDTH :
    LEFT + ((x - (extent?.lower ?? 0)) / ((extent?.upper ?? 1) - (extent?.lower ?? 0))) * WIDTH;
  const py = (value: number) => TOP + (1 - value) * HEIGHT;
  const cancelGesture = () => {
    if (gesture.current) onChange(gesture.current.snapshot);
    gesture.current = null; setDragging(false); onGesture(false);
  };
  const editAtPointer = (event: React.PointerEvent<SVGCircleElement>) => {
    const current = gesture.current; const box = svg.current?.getBoundingClientRect();
    if (!current || !box || !extent && !labelled) return;
    const chartX = (event.clientX - box.left) * 640 / box.width;
    const chartY = (event.clientY - box.top) * 325 / box.height;
    const x = labelled ? current.handle.x : (extent?.lower ?? 0) + (chartX - LEFT) / WIDTH * ((extent?.upper ?? 1) - (extent?.lower ?? 0));
    const value = 1 - (chartY - TOP) / HEIGHT;
    onChange(moveHandle(current.snapshot, current.index, x, value));
  };
  const numericSamples = preview?.curve_ready && !labelled ? preview.samples.filter((s) => typeof s.measurement === "number") : [];
  const path = numericSamples.map((s, i) => `${i ? "L" : "M"}${px(Number(s.measurement))},${py(s.partial_value)}`).join(" ");
  return <div className="function-chart">
    <svg ref={svg} viewBox="0 0 640 325" role="group" aria-label="Value-function chart"
      onDoubleClick={(e) => {
        if (vf.kind !== "piecewise_linear" || !extent || e.target instanceof SVGCircleElement) return;
        const box = e.currentTarget.getBoundingClientRect();
        onInsert(extent.lower + ((e.clientX-box.left)*640/box.width-LEFT)/WIDTH*(extent.upper-extent.lower),
          1-((e.clientY-box.top)*325/box.height-TOP)/HEIGHT);
      }}>
      <title>Backend-calculated preference values and editable judgement inputs</title>
      {[0,.25,.5,.75,1].map((v) => <g key={v}><line x1={LEFT} x2={LEFT+WIDTH} y1={py(v)} y2={py(v)} className="plot-grid"/>
        <text x={LEFT-12} y={py(v)+4} textAnchor="end">{v}</text></g>)}
      <line x1={LEFT} x2={LEFT} y1={TOP} y2={TOP+HEIGHT} className="plot-axis"/>
      <line x1={LEFT} x2={LEFT+WIDTH} y1={TOP+HEIGHT} y2={TOP+HEIGHT} className="plot-axis"/>
      <text x={18} y={160} transform="rotate(-90 18 160)" textAnchor="middle">Preference value (0–1)</text>
      <text x={LEFT+WIDTH/2} y={318} textAnchor="middle">{labelled ? "Explicit labels (no interpolated spacing)" : `Measurement${draft.scale.unit ? ` (${draft.scale.unit})` : ""}`}</text>
      {extent && !labelled && <><text x={LEFT} y={288}>{extent.lower.toPrecision(4)}</text><text x={LEFT+WIDTH} y={288} textAnchor="end">{extent.upper.toPrecision(4)}</text></>}
      {path && <path d={path} className="preference-curve" data-testid="preference-curve"/>}
      {preview?.curve_ready && labelled && preview.samples.map((s, i) => <g key={String(s.measurement)}>
        <circle cx={px(i)} cy={py(s.partial_value)} r={5} className="label-value"/>
        <text x={px(i)} y={288} textAnchor="middle">{s.measurement}</text></g>)}
      {preview?.curve_ready && preview.markers.map((m, i) => m.partial_value !== null &&
        (typeof m.raw_measurement === "number" || labelled) ? <circle key={m.alternative_id}
          cx={Math.min(LEFT+WIDTH, Math.max(LEFT, px(labelled ? draft.scale.labels.indexOf(String(m.raw_measurement)) : Number(m.raw_measurement))))}
          cy={py(m.partial_value)} r={5} className="measurement-marker" aria-label={`Measurement ${m.alternative_id}`}>
          <title>{alternativeNames[m.alternative_id] ?? m.alternative_id}: raw {String(m.raw_measurement)}, partial {m.partial_value}{m.clamped ? " (clamped)" : ""} · marker {i+1}</title>
        </circle> : null)}
      {(extent || labelled) && canMove && handles.map((h, i) => Number.isFinite(h.value) ? <circle key={i} cx={px(h.x)} cy={py(h.value)} r={8}
        className={`control-handle${selected === i ? " selected" : ""}`} role="slider" tabIndex={0} aria-label={`Control point ${i+1}`}
        aria-valuemin={0} aria-valuemax={1} aria-valuenow={h.value}
        aria-valuetext={`Measurement input ${h.x}; preference input ${h.value}`}
        onPointerDown={(e) => { if (e.button !== 0) return; e.preventDefault(); e.currentTarget.focus(); onSelect(i);
          gesture.current = { index:i, snapshot:structuredClone(draft), handle:h };setDragging(true);onGesture(true);e.currentTarget.setPointerCapture(e.pointerId); }}
        onPointerMove={editAtPointer}
        onPointerUp={(e) => { if (!gesture.current) return; editAtPointer(e);gesture.current=null;setDragging(false);onGesture(false); }}
        onPointerCancel={cancelGesture} onLostPointerCapture={() => { if(gesture.current)cancelGesture(); }}
        onKeyDown={(e) => {
          if(e.key==="Delete" || e.key==="Backspace"){e.preventDefault();e.stopPropagation();onRemove(i);return;}
          if(e.key==="Escape" && gesture.current){e.preventDefault();e.stopPropagation();cancelGesture();return;}
          if(!["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(e.key))return;
          e.preventDefault();e.stopPropagation();
          const step = ((extent?.upper ?? 1)-(extent?.lower ?? 0))/100/(e.shiftKey?10:1);
          const x = h.x + (e.key==="ArrowRight"?step:e.key==="ArrowLeft"?-step:0);
          const value = h.value + (e.key==="ArrowUp"?.01:e.key==="ArrowDown"?-.01:0)/(e.shiftKey?10:1);
          onChange(moveHandle(draft,i,x,value));
        }}><title>Input handle {i+1}; arrows edit, Shift makes finer steps; Escape cancels</title></circle> : null)}
      {!preview?.curve_ready && <text x={LEFT+WIDTH/2} y={150} textAnchor="middle" className="plot-pending">Curve hidden until the backend preview is ready</text>}
    </svg>
    <p className="muted small">Blue line/dots: server preference values · outlined handles: judgement inputs · amber dots: alternative measurements (viewport-edge markers retain raw values in the table).
      {dragging ? " Drag in progress: Escape or interruption restores the previous candidate." : " Arrow keys move a focused handle; Shift uses finer steps. Endpoint values remain fixed; edit endpoint measurements horizontally."}</p>
  </div>;
}
