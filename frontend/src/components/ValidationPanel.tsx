import { useState } from "react";
import type { Issue, ValidationReport } from "../api/types";
import { errorsOf, warningsOf } from "../model/issues";

interface Props {
  report: ValidationReport;
  onGo: (issue: Issue) => void;
}

export function ValidationPanel({ report, onGo }: Props) {
  const errors = errorsOf(report);
  const warnings = warningsOf(report);
  // Errors always open the list; warnings stay folded until asked for. An explicit toggle wins until errors change.
  const hasErrors = errors.length > 0;
  const [chosen, setChosen] = useState<{ open: boolean; hasErrors: boolean } | null>(null);
  const open = chosen?.hasErrors === hasErrors ? chosen.open : hasErrors;
  return (
    <aside className="validation" aria-label="Problems">
      <h2>
        Model checks{" "}
        <span className={`badge ${errors.length ? "bad" : "ok"}`} aria-label={`${String(errors.length)} errors`}>
          {errors.length}
        </span>{" "}
        <span className={`badge ${warnings.length ? "warn" : "ok"}`} aria-label={`${String(warnings.length)} warnings`}>
          {warnings.length}
        </span>
      </h2>
      {report.issues.length === 0 ? (
        <p className="ok-text">The model is complete and consistent.</p>
      ) : (
        <>
          <button type="button" className="link issue-toggle" aria-expanded={open} onClick={() => setChosen({ open: !open, hasErrors })}>
            {open ? "Hide details" : `Show ${String(report.issues.length)} note${report.issues.length === 1 ? "" : "s"}`}
          </button>
          <ul className="issue-list" hidden={!open}>
            {[...errors, ...warnings].map((i, k) => (
              <li key={`${i.code}-${i.path}-${String(k)}`} className={i.severity}>
                <button type="button" onClick={() => onGo(i)}>
                  <span className="sev">{i.severity === "error" ? "Error" : "Warning"}</span>
                  <span className="msg">{i.message}</span>
                  <span className="meta">
                    <span className="code">{i.code}</span>
                    {i.path && <span className="path"> · {i.path}</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </aside>
  );
}
