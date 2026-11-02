import { useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import type { Issue } from "../api/types";
import { coverageCell, coveragePage, coverageSummary, pagesForCell, pairKey,
  reconcileCoverageCell, type CoverageCell, type CoverageIndex } from "../model/coverage";

interface Props {
  index: CoverageIndex;
  selected: CoverageCell | null;
  onSelect: (cell: CoverageCell) => void;
  onOpen: (cell: CoverageCell) => void;
  onCriterion: (id: string) => void;
  onAlternative: (id: string) => void;
  onIssue: (issue: Issue) => void;
  focusKey: number;
}

export function CoverageMatrix({ index, selected: incoming, onSelect, onOpen, onCriterion, onAlternative, onIssue, focusKey }: Props) {
  const selected = reconcileCoverageCell(index, incoming);
  const selectedKey = selected ? pairKey(selected) : "";
  const selectedPosition = selected ? `${String(index.alternativePositions.get(selected.alternativeId))}:${String(index.leafPositions.get(selected.criterionId))}` : "";
  const [pages, setPages] = useState(() => pagesForCell(index, selected));
  const [seen, setSeen] = useState({ selectedKey, selectedPosition, focusKey });
  if (seen.selectedKey !== selectedKey || seen.selectedPosition !== selectedPosition || seen.focusKey !== focusKey) {
    setSeen({ selectedKey, selectedPosition, focusKey });
    if (selected) setPages(pagesForCell(index, selected));
  }
  const rows = coveragePage(index.alternatives.length, pages.row);
  const columns = coveragePage(index.leaves.length, pages.column);
  const refs = useRef(new Map<string, HTMLButtonElement>());
  const heading = useRef<HTMLHeadingElement>(null);
  const pendingFocus = useRef<CoverageCell | null>(null);
  const consumedFocus = useRef(0);
  const lastFocused = useRef<CoverageCell | null>(null);
  const pointerFocus = useRef<string | null>(null);
  useLayoutEffect(() => {
    if (focusKey !== consumedFocus.current) { consumedFocus.current = focusKey; pendingFocus.current = selected; }
    const target = pendingFocus.current;
    const element = target ? refs.current.get(pairKey(target)) : null;
    if (element) {
      pendingFocus.current = null; element.focus(); element.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
    if (lastFocused.current && !reconcileCoverageCell(index, lastFocused.current)) {
      lastFocused.current = null;
      if (document.activeElement === document.body) heading.current?.focus();
    }
  }, [index, selected, focusKey, rows.start, columns.start]);

  function key(event: KeyboardEvent<HTMLButtonElement>, row: number, column: number) {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    let r = row, c = column;
    switch (event.key) {
      case "ArrowRight": c++; break;
      case "ArrowLeft": c--; break;
      case "ArrowDown": r++; break;
      case "ArrowUp": r--; break;
      case "Home": c = 0; break;
      case "End": c = index.leaves.length - 1; break;
      default: return;
    }
    event.preventDefault();
    const alternative = index.alternatives[Math.max(0, Math.min(index.alternatives.length - 1, r))];
    const criterion = index.leaves[Math.max(0, Math.min(index.leaves.length - 1, c))];
    if (!alternative || !criterion) return;
    const cell = { alternativeId: alternative.id, criterionId: criterion.id };
    pendingFocus.current = cell; setPages(pagesForCell(index, cell)); onSelect(cell);
    // At an edge the selected IDs may be unchanged, so no React render is necessary.
    const rendered = refs.current.get(pairKey(cell));
    if (rendered) { pendingFocus.current = null; rendered.focus(); rendered.scrollIntoView({ block: "nearest", inline: "nearest" }); }
  }
  const displayedAlternatives = index.alternatives.slice(rows.start, rows.end);
  const displayedLeaves = index.leaves.slice(columns.start, columns.end);
  const selectedVisible = selected && displayedAlternatives.some(a => a.id === selected.alternativeId) && displayedLeaves.some(c => c.id === selected.criterionId);
  const activeKey = selectedVisible ? selectedKey : pairKey({ alternativeId: displayedAlternatives[0]?.id ?? "", criterionId: displayedLeaves[0]?.id ?? "" });
  const selectedState = selected ? coverageCell(index, selected) : null;
  return <section className="panel coverage-panel" aria-label="Measurement coverage">
    <h2 ref={heading} tabIndex={-1}>Measurement coverage</h2>
    <p role="status" data-testid="coverage-summary">{coverageSummary(index)}</p>
    <p className="muted small">Evidence provenance not recorded. Entry and engine issues are shown separately.</p>
    {(index.alternatives.length > 100 || index.leaves.length > 100 || index.tree.byId.size > 1000) &&
      <p className="note">Display performance has been measured up to 100 alternatives, 100 leaf criteria and 1,000 nodes. Larger drafts remain paged; analysis has separate engine limits.</p>}
    <div className="coverage-links">
      <details><summary>Setup and criterion issues · {index.setupIds.size} criteria need setup</summary>
        <ul>{index.leaves.filter(n => index.setupIds.has(n.id) || index.criterionIssues.has(n.id)).map(n => <li key={n.id}>
          <button type="button" className="link" onClick={() => onCriterion(n.id)}>Set up {n.name} ({n.id})</button>
          {index.criterionIssues.get(n.id)?.map((issue, i) => <p key={i}><button type="button" className="link" onClick={() => onIssue(issue)}>{issue.code}: {issue.message}</button></p>)}
        </li>)}</ul>
      </details>
      <details><summary>Preference issues · {index.preferenceIssues.length}</summary>
        <ul>{index.preferenceIssues.map((issue, i) => <li key={i}><button type="button" className="link" onClick={() => onIssue(issue)}>{issue.code}: {issue.message}</button></li>)}</ul>
      </details>
    </div>
    {index.tree.errors.length > 0 ? <p>Coverage table unavailable: correct the hierarchy using the Problems panel and the incoming criteria list above.</p>
      : index.expected > 0 && <>
        <p id="coverage-help" className="muted small">Arrow keys move between cells and pages · Home/End reach the first/last criterion · Enter opens the existing editor. Return to coverage restores cell focus.</p>
        <CoveragePaging rows={rows} columns={columns} alternatives={index.alternatives.length} criteria={index.leaves.length}
          onRows={row => setPages(p => ({ ...p, row }))} onColumns={column => setPages(p => ({ ...p, column }))} />
        <div className="table-scroll" role="region" aria-label="Measurement coverage table scroll area" tabIndex={0}>
          <table className="grid coverage-matrix" aria-label="Measurement coverage: alternatives by leaf criteria" aria-describedby="coverage-help">
            <thead><tr><th scope="col">Alternative</th>{displayedLeaves.map(c => <th scope="col" key={c.id}>
              <button type="button" className="link" onClick={() => onCriterion(c.id)}>{c.name}</button><small>{c.id}</small>
            </th>)}</tr></thead>
            <tbody>{displayedAlternatives.map((a, r) => <tr key={a.id} data-selected={selected?.alternativeId === a.id ? "true" : undefined}>
              <th scope="row"><button type="button" className="link" onClick={() => onAlternative(a.id)} aria-label={`Edit coverage alternative ${a.name} (${a.id})`}>{a.name}</button><small>{a.id}</small></th>
              {displayedLeaves.map((c, col) => {
                const cell = { alternativeId: a.id, criterionId: c.id }, id = pairKey(cell);
                const state = coverageCell(index, cell);
                return <td key={c.id}><button type="button" className={`coverage-cell ${state.entered ? "entered" : "missing"}`}
                  ref={element => { if (element) refs.current.set(id, element); else refs.current.delete(id); }}
                  tabIndex={activeKey === id ? 0 : -1} aria-pressed={selectedKey === id}
                  aria-label={`${a.name} (${a.id}) on ${c.name} (${c.id}): ${state.status}`}
                  onPointerDown={() => { pointerFocus.current = id; }}
                  onPointerUp={() => { pointerFocus.current = null; }} onPointerCancel={() => { pointerFocus.current = null; }}
                  onFocus={() => {
                    lastFocused.current = cell;
                    // Revealing a collapsed ancestor can move the table between pointer down/up.
                    // Select pointer targets on click; keyboard focus still selects immediately.
                    if (pointerFocus.current !== id) onSelect(cell);
                    pointerFocus.current = null;
                  }}
                  onClick={() => { onSelect(cell); onOpen(cell); }} onKeyDown={event => key(event, rows.start + r, columns.start + col)}>
                  <span>{state.status}</span>{state.entered && <small>Stored: {String(state.value)}</small>}
                  {state.issues.map((issue, i) => <small key={i}>{issue.message}</small>)}
                </button></td>;
              })}
            </tr>)}</tbody>
          </table>
        </div>
        {selected && selectedState && <div className="coverage-selection" role="region" aria-label="Selected coverage cell">
          <p>{index.alternatives[index.alternativePositions.get(selected.alternativeId) ?? -1]?.name} on {index.tree.byId.get(selected.criterionId)?.name}: {selectedState.status}</p>
          {selectedState.setup && <button type="button" onClick={() => onCriterion(selected.criterionId)}>Open criterion setup</button>}
          {selectedState.issues.map((issue, i) => <p key={i}><button type="button" className="link" onClick={() => onIssue(issue)}>{issue.code}: {issue.message}</button></p>)}
        </div>}
      </>}
  </section>;
}

/** The same explicit page sizes and range labels are used at the existing input destination. */
export function CoveragePaging({ rows, columns, alternatives, criteria, onRows, onColumns }: {
  rows: ReturnType<typeof coveragePage>; columns: ReturnType<typeof coveragePage>; alternatives: number; criteria: number;
  onRows: (page: number) => void; onColumns: (page: number) => void;
}) {
  return <div className="coverage-paging" role="group" aria-label="Measurement pages">
    <span>Alternatives {rows.start + 1}–{rows.end} of {alternatives}; criteria {columns.start + 1}–{columns.end} of {criteria}</span>
    {rows.pages > 1 && <><button type="button" disabled={rows.page === 0} onClick={() => onRows(rows.page - 1)}>Previous alternatives</button>
      <button type="button" disabled={rows.page + 1 === rows.pages} onClick={() => onRows(rows.page + 1)}>Next alternatives</button></>}
    {columns.pages > 1 && <><button type="button" disabled={columns.page === 0} onClick={() => onColumns(columns.page - 1)}>Previous criteria</button>
      <button type="button" disabled={columns.page + 1 === columns.pages} onClick={() => onColumns(columns.page + 1)}>Next criteria</button></>}
  </div>;
}
