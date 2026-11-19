import { useEffect, useMemo, useRef, useState } from "react";
import type { CriterionNode, Measurement, Operation, Project, ValidationReport } from "../api/types";
import { isNumeric } from "../model/defaults";
import { buildCoverage, coveragePage, pagesForCell, pairKey, type CoverageIndex } from "../model/coverage";
import { pathNames } from "../model/tree";
import { CoveragePaging } from "./CoverageMatrix";
import { CommitNumber } from "./ui";

interface Props {
  project: Project;
  validation: ValidationReport;
  busy: boolean;
  apply: (ops: Operation[]) => Promise<boolean>;
  focusCell: { alternativeId: string; criterionId: string } | null;
  onGoToCriterion: (id: string) => void;
  coverage?: CoverageIndex;
}

export function MeasurementsPanel({ project, validation, busy, apply, focusCell, onGoToCriterion, coverage: supplied }: Props) {
  const coverage = useMemo(() => supplied ?? buildCoverage(project, validation), [supplied, project, validation]);
  const [pages, setPages] = useState(() => pagesForCell(coverage, focusCell));
  const focusPosition = focusCell ? `${String(coverage.alternativePositions.get(focusCell.alternativeId))}:${String(coverage.leafPositions.get(focusCell.criterionId))}` : "";
  const [seenFocus, setSeenFocus] = useState({ cell: focusCell, position: focusPosition });
  if (seenFocus.cell !== focusCell || seenFocus.position !== focusPosition) {
    setSeenFocus({ cell: focusCell, position: focusPosition }); if (focusCell) setPages(pagesForCell(coverage, focusCell));
  }
  const rows = coveragePage(coverage.alternatives.length, pages.row), columns = coveragePage(coverage.leaves.length, pages.column);
  const leafNodes = coverage.leaves.slice(columns.start, columns.end);
  const alternatives = coverage.alternatives.slice(rows.start, rows.end);
  const cells = useRef(new Map<string, HTMLTableCellElement>());
  const pendingFocus = useRef<{ cell: NonNullable<Props["focusCell"]>; from: Element | null } | null>(null);
  const value = (alt: string, crit: string): Measurement | undefined =>
    coverage.measurements.get(pairKey({ alternativeId: alt, criterionId: crit }));

  useEffect(() => {
    pendingFocus.current = focusCell ? { cell: focusCell, from: document.activeElement } : null;
  }, [focusCell]);
  useEffect(() => {
    const request = pendingFocus.current;
    if (!request || busy) return;
    const el = cells.current.get(pairKey(request.cell))?.querySelector<HTMLElement>("input, select");
    if (!el) return;
    pendingFocus.current = null;
    if (document.activeElement !== document.body && document.activeElement !== request.from) return;
    el.focus();
    el.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [focusCell, busy, rows.start, columns.start]);

  if (project.alternatives.length === 0 || leafNodes.length === 0) {
    return (
      <section className="panel" aria-label="Measurements">
        <h2>Measurements</h2>
        <div className="empty small-empty">
          <p>
            {project.alternatives.length === 0 ? "Add alternatives" : "Add criteria"} first. The table
            has one row per alternative and one column per criterion that is measured (a criterion
            with no children).
          </p>
        </div>
      </section>
    );
  }

  function cell(altId: string, altName: string, crit: CriterionNode) {
    const alt = altId;
    const current = value(alt, crit.id);
    const issues = coverage.pairIssues.get(pairKey({ alternativeId: alt, criterionId: crit.id })) ?? [];
    const invalid = issues.some((i) => i.severity === "error");
    const title = issues.map((i) => i.message).join("\n") || undefined;
    const scale = crit.scale;
    if (!scale) return <span className="muted small">set the measurement type</span>;
    if (isNumeric(scale.type)) {
      return (
        <CommitNumber
          label={`${altName} on ${crit.name}`}
          value={typeof current === "number" ? current : null}
          allowEmpty
          disabled={busy}
          invalid={invalid || typeof current === "string"}
          onCommit={(v) =>
            void apply(
              v === null
                ? [{ op: "clear_performance", alternative_id: alt, criterion_id: crit.id }]
                : [{ op: "set_performance", alternative_id: alt, criterion_id: crit.id, value: v }],
            )
          }
        />
      );
    }
    return (
      <select
        aria-label={`${altName} on ${crit.name}`}
        aria-invalid={invalid ? true : undefined}
        title={title}
        disabled={busy}
        value={typeof current === "string" ? current : ""}
        onChange={(e) =>
          void apply(
            e.target.value === ""
              ? [{ op: "clear_performance", alternative_id: alt, criterion_id: crit.id }]
              : [{ op: "set_performance", alternative_id: alt, criterion_id: crit.id, value: e.target.value }],
          )
        }
      >
        <option value="">—</option>
        {scale.labels.map((l) => (
          <option key={l} value={l}>
            {l}
          </option>
        ))}
        {typeof current === "string" && !scale.labels.includes(current) && (
          <option value={current}>{current} (not a level)</option>
        )}
      </select>
    );
  }

  return (
    <section className="panel" aria-label="Measurements">
      <h2>Measurements</h2>
      <p className="muted">
        How each alternative performs on each criterion. Leave a cell empty if unknown; the model is
        incomplete until every cell is filled.
      </p>
      <CoveragePaging rows={rows} columns={columns} alternatives={coverage.alternatives.length} criteria={coverage.leaves.length}
        onRows={row => setPages(p => ({ ...p, row }))} onColumns={column => setPages(p => ({ ...p, column }))} />
      <div className="table-scroll">
        <table className="grid matrix" aria-label="Performance table">
          <thead>
            <tr>
              <th>Alternative</th>
              {leafNodes.map((c) => (
                <th key={c.id}>
                  <button type="button" className="link" onClick={() => onGoToCriterion(c.id)} title={pathNames(project.criteria, c.id).join(" › ")}>
                    {c.name}
                  </button>
                  <div className="muted small">
                    {c.scale ? (c.scale.unit ?? c.scale.type) : "no scale"}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {alternatives.map((a) => (
              <tr key={a.id}>
                <th scope="row">{a.name}</th>
                {leafNodes.map((c) => {
                  const key = pairKey({ alternativeId: a.id, criterionId: c.id });
                  const issues = coverage.pairIssues.get(key) ?? [];
                  const bad = issues.some((i) => i.severity === "error");
                  return (
                    <td
                      key={c.id}
                      ref={element => { if (element) cells.current.set(key, element); else cells.current.delete(key); }}
                      data-cell={`${a.id}|${c.id}`}
                      className={bad ? "cell-error" : issues.length ? "cell-warn" : ""}
                      title={issues.map((i) => i.message).join("\n") || undefined}
                    >
                      {cell(a.id, a.name, c)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
