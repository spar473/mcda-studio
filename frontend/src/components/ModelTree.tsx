import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode, type RefObject } from "react";
import type { Project, ValidationReport, WeightPreview } from "../api/types";
import { diagramLayout, hasValueFunction, leafIds, swingRatings } from "../model/diagram";
import { ancestors, treeIssues, visibleRows, type TreeIndex, type TreeRow } from "../model/visibleTree";

export interface TreePresentation {
  mode: "canvas" | "outline";
  collapsed: ReadonlySet<string>;
}

/** Engine weight preview state for the diagram; the numbers are never computed here. */
export type DiagramWeights =
  | { status: "off" | "loading" | "incomplete" }
  | { status: "error"; message: string }
  | { status: "ready"; preview: WeightPreview; context: string };

/** Canvas extras. Chips are pointer shortcuts; the Inspector offers the same destinations by keyboard. */
export interface DiagramOptions {
  goal: ReactNode;
  profileId: string | null;
  weights: DiagramWeights;
  onEditWeights?: (groupId: string | null) => void;
  onEditFunction?: (id: string) => void;
  onEditAlternative?: (id: string) => void;
  onAddAlternatives?: () => void;
  selectedAlternativeId?: string;
}

interface Props {
  project: Project;
  index: TreeIndex;
  validation: ValidationReport;
  selectedId: string | null;
  presentation: TreePresentation;
  onPresentation: (value: TreePresentation) => void;
  onSelect: (id: string | null) => void;
  onEdit?: (id: string) => void;
  onRemove: (id: string) => void;
  onFocusRemoved: () => void;
  busy: boolean;
  diagram?: DiagramOptions;
  /** Presentation: selection and collapse only; no editing destinations. */
  readOnly?: boolean;
}

const plural = (n: number, word: string) => `${String(n)} ${word}${n === 1 ? "" : "s"}`;
const fixed = (n: number | undefined) => n === undefined ? "unavailable" : n.toFixed(3);

export function ModelTree({ project, index, validation, selectedId, presentation, onPresentation, onSelect, onEdit, onRemove, onFocusRemoved, busy, diagram, readOnly = false }: Props) {
  const refs = useRef(new Map<string, HTMLLIElement>());
  const canvas = presentation.mode === "canvas" && diagram !== undefined;
  const counts = useMemo(() => treeIssues(index, validation), [index, validation]);
  const { rows, closed } = useMemo(() => visibleRows(index, presentation.collapsed, selectedId), [index, presentation.collapsed, selectedId]);
  const layout = useMemo(() => diagramLayout(rows), [rows]);
  // The canvas shows IDs only where names repeat; the accessible name always includes the ID.
  const duplicates = useMemo(() => {
    const seen = new Set<string>(), repeated = new Set<string>();
    for (const node of project.criteria) { if (seen.has(node.name)) repeated.add(node.name); seen.add(node.name); }
    return repeated;
  }, [project.criteria]);
  const selectedAncestors = useMemo(() => ancestors(index, selectedId), [index, selectedId]);
  const lastFocused = useRef<string | null>(null);
  useEffect(() => {
    if (closed.size !== presentation.collapsed.size || [...closed].some(id => !presentation.collapsed.has(id))) {
      onPresentation({ ...presentation, collapsed: closed });
    }
  }, [closed, presentation, onPresentation]);
  useLayoutEffect(() => {
    if (lastFocused.current && !index.byId.has(lastFocused.current) && document.activeElement === document.body) onFocusRemoved();
  }, [index, onFocusRemoved]);
  const activeId = rows.some(row => row.node.id === selectedId) ? selectedId : rows[0]?.node.id;
  const select = (id: string) => { onSelect(id); refs.current.get(id)?.focus(); };
  function toggle(id: string) {
    const next = new Set(closed);
    if (!next.delete(id)) {
      next.add(id);
      if (selectedAncestors.has(id)) select(id);
    }
    onPresentation({ ...presentation, collapsed: next });
  }
  function key(event: KeyboardEvent<HTMLUListElement>) {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    if ((event.target as HTMLElement).closest("button") && ["Enter", " "].includes(event.key)) return;
    const id = (event.target as HTMLElement).closest<HTMLElement>("[data-node-id]")?.dataset.nodeId;
    const at = rows.findIndex(row => row.node.id === id);
    const row = rows[at]; if (!row) return;
    const children = index.children.get(row.node.id) ?? [];
    const go = (i: number) => { const target = rows[i]; if (target) select(target.node.id); };
    switch (event.key) {
      case "ArrowDown": event.preventDefault(); go(Math.min(rows.length - 1, at + 1)); break;
      case "ArrowUp": event.preventDefault(); go(Math.max(0, at - 1)); break;
      case "Home": event.preventDefault(); go(0); break;
      case "End": event.preventDefault(); go(rows.length - 1); break;
      case "ArrowRight":
        event.preventDefault();
        if (closed.has(row.node.id)) toggle(row.node.id);
        else if (children[0]) select(children[0].id);
        break;
      case "ArrowLeft":
        event.preventDefault();
        if (children.length && !closed.has(row.node.id)) toggle(row.node.id);
        else if (row.node.parent_id) select(row.node.parent_id);
        break;
      case " ": event.preventDefault(); select(row.node.id); break;
      case "Enter": event.preventDefault(); onSelect(row.node.id); if (!readOnly) onEdit?.(row.node.id); break;
      case "Delete": if (!busy && !readOnly) { event.preventDefault(); onSelect(row.node.id); onRemove(row.node.id); } break;
    }
  }
  if (index.errors.length) return <div className="structural-fallback" role="region" aria-label="Structure cannot be drawn safely">
    <h3>Structure cannot be drawn safely</h3>
    <p>Check the Problems panel and correct the source hierarchy before editing. Every incoming item is listed below; no scores are available from this view.</p>
    <ul>{index.errors.map(error => <li key={error}>{error}</li>)}</ul>
    <ol aria-label="Incoming criteria (flat fallback)">{project.criteria.map((node, i) => <li key={i}>
      <strong>{node.name}</strong> · ID {node.id} · Parent {node.parent_id ?? "Goal"}
    </li>)}</ol>
  </div>;

  const weights = canvas && diagram.weights.status === "ready" ? diagram.weights.preview : null;
  const item = ({ node, depth, position, siblings }: TreeRow) => {
    const group = (index.children.get(node.id)?.length ?? 0) > 0;
    const count = counts.get(node.id);
    const setup = !group && !hasValueFunction(node);
    const attention = setup || Boolean(count?.errors) || Boolean(count?.warnings);
    const status =setup ? "Setup needed" : count?.errors ? "Inputs need attention" : count?.warnings ? "Review warnings" : group ? "Groups criteria" : "Definition entered";
    const issueText = `${count?.errors ? ` · ${plural(count.errors, "issue")}` : ""}${count?.warnings ? ` · ${plural(count.warnings, "warning")}` : ""}`;
    const goalShare = weights ? fixed(group ? weights.path_shares[node.id] : weights.global_weights[node.id]) : "";
    const weightText = weights ? `local ${fixed(weights.local_weights[node.id])} · of goal ${goalShare}` : null;
    const weightLabel = weights ? `local weight ${fixed(weights.local_weights[node.id])}, ${group ? "branch share" : "global weight"} ${goalShare}` : null;
    const swing = group ? swingRatings(project, index, diagram?.profileId ?? null, node.id) : null;
    const selected = selectedId === node.id;
    const cell = layout.cells.get(node.id);
    const style = canvas && cell
      ? { gridColumn: String(cell.column), gridRow: `${String(cell.rowStart)} / ${String(cell.rowEnd)}` }
      : { "--node-indent": `${String(Math.min(depth - 1, 6) * 20)}px` } as CSSProperties;
    return <li key={node.id} ref={el => { if (el) refs.current.set(node.id, el); else refs.current.delete(node.id); }}
      role="treeitem" aria-level={depth} aria-posinset={position} aria-setsize={siblings}
      aria-selected={selected} aria-expanded={group ? !closed.has(node.id) : undefined}
      aria-label={`${node.name} (${node.id}), ${group ? "Objective" : "Criterion"}, ${status}${issueText}${weightLabel ? `, ${weightLabel}` : ""}`}
      tabIndex={activeId === node.id ? 0 : -1} data-node-id={node.id}
      className={`model-row${selected ? " selected" : ""}${count?.errors ? " needs-attention" : ""}`} style={style}>
      <div className={`tree-row model-card${selected ? " selected" : ""}${group ? " group" : " leaf"}`}>
        {group ? <button type="button" className="twisty" tabIndex={-1}
          aria-label={`${closed.has(node.id) ? "Expand" : "Collapse"} ${node.name}`}
          onClick={() => toggle(node.id)}>{closed.has(node.id) ? "▸" : "▾"}</button> : <span className="model-leaf" aria-hidden="true">◇</span>}
        <button type="button" className="tree-label" tabIndex={-1} onClick={() => select(node.id)}>
          {!canvas && <span className="model-kind">{group ? "Objective" : "Criterion"}</span>}
          <span className="tree-name">{node.name}</span>
          {canvas
            ? <span className={`model-node-id${attention ? " attention" : ""}`}>{group ? "Objective" : "Criterion"}{duplicates.has(node.name) ? ` · ${node.id}` : ""}{attention ? ` · ${status}${issueText}` : ""}{group && closed.has(node.id) ? ` · ${String(index.children.get(node.id)?.length ?? 0)} hidden` : ""}</span>
            : <>
              <span className="model-node-id">{depth > 1 ? `${node.id} · Level ${String(depth)} · under ${node.parent_id ?? "Goal"}` : `${node.id} · under Goal`}</span>
              <span className={`model-status${attention ? " attention" : ""}`}>{status}{issueText}</span>
            </>}
        </button>
        {canvas && (weightText || !readOnly) && <div className="model-card-foot">
          {weightText && <span className="model-weight">{weightText}</span>}
          {!readOnly && group && diagram.onEditWeights && swing && <button type="button" className={`model-chip${swing.missing ? " attention" : ""}`} tabIndex={-1}
            aria-label={`Edit swing weights under ${node.name}`} onClick={() => diagram.onEditWeights?.(node.id)}>
            Swing{swing.missing ? ` · ${String(swing.missing)} missing` : ""}</button>}
          {!readOnly && !group && diagram.onEditFunction && <button type="button" className={`model-chip${setup ? " attention" : ""}`} tabIndex={-1}
            aria-label={setup ? `Set up measurement for ${node.name}` : `Edit value function for ${node.name}`} onClick={() => diagram.onEditFunction?.(node.id)}>
            {setup ? "Value fn needed" : "Value fn"}</button>}
        </div>}
      </div>
    </li>;
  };
  const tree = <ul className={`tree model-tree ${canvas ? "canvas" : "outline"}`} role="tree" aria-label="Criteria tree" aria-describedby="model-tree-help" onKeyDown={key}
    style={canvas ? { "--columns": String(Math.max(layout.columns, 1)) } as CSSProperties : undefined}
    onFocusCapture={event => { lastFocused.current = (event.target as HTMLElement).closest<HTMLElement>("[data-node-id]")?.dataset.nodeId ?? null; }}>
    {rows.map(item)}
  </ul>;
  const help = <p className="muted small model-key-help" id="model-tree-help">Arrow keys explore branches · Home/End jump · {readOnly ? "Space or Enter selects" : "Enter edits · Space selects · Delete asks to remove"}</p>;

  if (!canvas) {
    if (!rows.length) return <div className="empty small-empty model-empty">
      <p>No criteria yet.</p><p>Start with an objective such as “Cost”, or a criterion you can measure directly. Use Add top-level objective above; add children to create a group.</p>
    </div>;
    return <>{help}{tree}</>;
  }
  return <ModelDiagram project={project} index={index} rows={rows} diagram={diagram} readOnly={readOnly} help={rows.length ? help : null} tree={rows.length ? tree : null} />;
}

function ModelDiagram({ project, index, rows, diagram, readOnly, help, tree }: { project: Project; index: TreeIndex; rows: TreeRow[];
  diagram: DiagramOptions; readOnly: boolean; help: ReactNode; tree: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  const leaves = useMemo(() => leafIds(index).length, [index]);
  // Selection rebuilds the row array without changing which cards are shown; only remeasure on real change.
  const shownKey = rows.map(row => row.node.id).join("\n");
  const shown = useMemo(() => rows, [shownKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const alternatives = project.alternatives;
  const w = diagram.weights;
  return <>
    {!readOnly && <ModelHints project={project} index={index} />}
    {w.status !== "off" && rows.length > 0 && <p className="muted small diagram-legend">{
      w.status === "ready" ? <>Engine weights · {w.context}. <strong>Local</strong>: share within its sibling group. <strong>Branch share</strong> / <strong>global</strong>: share of the goal, which line thickness also follows. Exact values are on the Weights tab.</>
        : w.status === "incomplete" ? "Weights appear here once every sibling group has valid swing ratings; none are shown or assumed until then."
          : w.status === "error" ? `Weights unavailable: ${w.message}` : "Previewing weights…"}</p>}
    {help}
    <div className="diagram-scroll" role="region" aria-label="Model diagram">
      <div className="diagram" ref={root}>
        <DiagramLinks root={root} rows={shown} index={index} weights={w.status === "ready" ? w.preview : null} alternatives={alternatives.length} />
        <div className="diagram-goal">{diagram.goal}</div>
        {tree ?? <div className="empty small-empty model-empty diagram-empty">
          <p>No criteria yet.</p>
          <p>Use Add top-level objective above to begin the value tree.</p>
        </div>}
        <section className="diagram-alternatives" aria-label="Alternatives in the model diagram">
          <h3 className="model-kind">Alternatives</h3>
          {alternatives.length ? <ul>{alternatives.map(a => <li key={a.id}>
            {readOnly || !diagram.onEditAlternative ? <span className="diagram-alt">{a.name}</span>
              : <button type="button" className="diagram-alt" aria-pressed={diagram.selectedAlternativeId === a.id} aria-label={`Edit alternative: ${a.name}`} onClick={() => diagram.onEditAlternative?.(a.id)}>{a.name}</button>}
          </li>)}</ul> : <p className="muted small">None yet.{!readOnly && diagram.onAddAlternatives && <> <button type="button" className="link" onClick={diagram.onAddAlternatives}>Add alternatives</button></>}</p>}
          <p className="muted small diagram-alt-note">{alternatives.length
            ? `Each option is scored on all ${String(leaves)} leaf ${leaves === 1 ? "criterion" : "criteria"}; options are not part of the hierarchy.`
            : "Options are compared on every leaf criterion once objectives are in place."}</p>
        </section>
      </div>
    </div>
  </>;
}

/** Structuring prompts from value-focused thinking: objectives before options, ranges before weights.
 * They describe what is present, never whether the model is good. */
function ModelHints({ project, index }: { project: Project; index: TreeIndex }) {
  const leaves = leafIds(index);
  const setup = leaves.filter(id => { const node = index.byId.get(id); return node && !hasValueFunction(node); }).length;
  const options = project.alternatives.length;
  const hint = (title: string, text: string) => <p className="model-hint" role="note"><strong>{title}</strong> {text}</p>;
  if (!project.criteria.length) return options
    ? hint("Objectives first.", `You already have ${plural(options, "option")}. Decide what matters before judging them, so they are compared on your objectives rather than on whatever happens to differ between them.`)
    : hint("Objectives first.", "Ask what would make this decision a success. Add each fundamental objective, such as “Cost”, then the criteria that measure it. Options come after.");
  if (setup) return hint("Ranges before weights.", `Swing weights compare each criterion’s worst-to-best range, so define those ranges first: ${String(setup)} of ${String(leaves.length)} leaf criteria still need a measurement and range.`);
  if (!options) return hint("Then options.", "Every leaf criterion has a measurement. Add the alternatives you are comparing; each will be scored on every leaf.");
  return null;
}

interface Box { x: number; y: number; w: number; h: number }
interface Geometry { width: number; height: number; links: { key: string; d: string; width: number }[]; bundle: string[]; arrow: string | null }

/** Position relative to the diagram in CSS pixels (unaffected by scrolling or page zoom factors). */
function within(el: HTMLElement, root: HTMLElement): Box {
  let x = 0, y = 0;
  for (let n: HTMLElement | null = el; n && n !== root; n = n.offsetParent as HTMLElement | null) { x += n.offsetLeft; y += n.offsetTop; }
  return { x, y, w: el.offsetWidth, h: el.offsetHeight };
}

/** Decorative connectors measured from the laid-out cards; hidden from assistive technology. */
function DiagramLinks({ root, rows, index, weights, alternatives }: { root: RefObject<HTMLDivElement | null>; rows: TreeRow[];
  index: TreeIndex; weights: WeightPreview | null; alternatives: number }) {
  const [geometry, setGeometry] = useState<Geometry | null>(null);
  useLayoutEffect(() => {
    const el = root.current;
    if (!el) return;
    const measure = () => {
      const boxes = new Map<string, Box>();
      el.querySelectorAll<HTMLElement>("[data-node-id] > .model-card").forEach(card => {
        const id = card.parentElement?.dataset.nodeId;
        if (id) boxes.set(id, within(card, el));
      });
      const goalEl = el.querySelector<HTMLElement>(".diagram-goal > *");
      const goal = goalEl ? within(goalEl, el) : null;
      const curve = (from: Box, to: Box) => {
        const x1 = from.x + from.w, y1 = from.y + from.h / 2, x2 = to.x, y2 = to.y + to.h / 2, dx = Math.max(12, (x2 - x1) / 2);
        return `M${String(x1)} ${String(y1)} C${String(x1 + dx)} ${String(y1)} ${String(x2 - dx)} ${String(y2)} ${String(x2)} ${String(y2)}`;
      };
      const share = (id: string) => weights ? (index.children.get(id)?.length ? weights.path_shares[id] : weights.global_weights[id]) : undefined;
      const links = rows.flatMap(row => {
        const to = boxes.get(row.node.id), from = row.node.parent_id ? boxes.get(row.node.parent_id) : goal;
        if (!to || !from) return [];
        const s = share(row.node.id);
        return [{ key: row.node.id, d: curve(from, to), width: s === undefined ? 1.25 : 1 + 7 * s }];
      });
      // Every visible terminal (leaf or collapsed branch) feeds one shared bracket to the options.
      const altEl = el.querySelector<HTMLElement>(".diagram-alternatives");
      const terminals = rows.filter((row, i) => !rows[i + 1] || (rows[i + 1]?.depth ?? 0) <= row.depth).flatMap(row => boxes.get(row.node.id) ?? []);
      let bundle: string[] = [], arrow: string | null = null;
      if (altEl && alternatives > 0 && terminals.length) {
        const alt = within(altEl, el);
        const bus = Math.max(...[...boxes.values()].map(b => b.x + b.w)) + 22;
        const mids = terminals.map(b => b.y + b.h / 2), target = alt.y + alt.h / 2;
        bundle = [...terminals.map(b => `M${String(b.x + b.w)} ${String(b.y + b.h / 2)} H${String(bus)}`),
          `M${String(bus)} ${String(Math.min(...mids, target))} V${String(Math.max(...mids, target))}`];
        arrow = `M${String(bus)} ${String(target)} H${String(alt.x - 6)}`;
      }
      setGeometry({ width: el.offsetWidth, height: el.offsetHeight, links, bundle, arrow });
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [root, rows, index, weights, alternatives]);
  if (!geometry) return null;
  return <svg className="diagram-links" aria-hidden="true" focusable="false" width={geometry.width} height={geometry.height}>
    <defs><marker id="diagram-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
      <path d="M0 0 L8 4 L0 8 z" className="diagram-arrow-head" /></marker></defs>
    {geometry.links.map(link => <path key={link.key} d={link.d} className="diagram-link" style={{ strokeWidth: link.width }} />)}
    {geometry.bundle.map((d, i) => <path key={i} d={d} className="diagram-bundle" />)}
    {geometry.arrow && <path d={geometry.arrow} className="diagram-bundle" markerEnd="url(#diagram-arrow)" />}
  </svg>;
}
