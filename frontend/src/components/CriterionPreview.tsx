import type { Project } from "../api/types";
import type { AnalysisContext } from "../state/analysisContext";
import { useValueFunctionPreview } from "../state/usePreviews";

/** Read-only B1 summary; graphical manipulation is deliberately deferred to B2. */
export function CriterionPreview({ project, context }: { project: Project; context: AnalysisContext }) {
  const preview = useValueFunctionPreview(project, context);
  return <section aria-label="Value-function preview">
    <h3>Value-function preview</h3>
    {preview.status === "loading" && <p role="status">Previewing this criterion…</p>}
    {preview.status === "error" && <p role="alert">{preview.message}</p>}
    {preview.status === "ready" && <>
      <p>{preview.result.curve_ready ? "Function ready" : "Function unavailable: complete the definition and required local measurements."}
        {preview.result.measurements_complete ? " · Measurements complete" : " · Measurements incomplete"}</p>
      {preview.result.resolved_domain && <p>Effective domain: {preview.result.resolved_domain.lower} – {preview.result.resolved_domain.upper}
        {" "}({preview.result.resolved_domain.source})</p>}
      <ul className="issue-list inline" aria-label="Criterion preview diagnostics">
        {preview.result.diagnostics.map((issue, i) => <li key={i} className={issue.severity}>
          <span className="code">{issue.code}</span> {issue.message}
        </li>)}
      </ul>
    </>}
  </section>;
}
