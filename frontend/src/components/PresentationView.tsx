import { useEffect, useMemo, useRef, useState } from "react";
import type { Project, ValidationReport } from "../api/types";
import { indexTree } from "../model/visibleTree";
import type { AnalysisContext } from "../state/analysisContext";
import { ModelTree, type DiagramWeights, type TreePresentation } from "./ModelTree";

interface Props {
  project: Project;
  validation: ValidationReport;
  context: AnalysisContext;
  fingerprint: string;
  dirty: boolean;
  presentation: TreePresentation;
  onPresentation: (value: TreePresentation) => void;
  weights: DiagramWeights;
  onExit: () => void;
}

/** A read-only discussion view of the live draft (decision conferencing). Selecting and collapsing
 * stay local to this view; nothing here edits, saves or evaluates the project. */
export function PresentationView({ project, validation, context, fingerprint, dirty, presentation, onPresentation, weights, onExit }: Props) {
  const index = useMemo(() => indexTree(project.criteria), [project.criteria]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, []);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onExit(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onExit]);
  const errors = validation.issues.filter(issue => issue.severity === "error");
  const profile = project.weight_profiles.find(p => p.id === context.resolvedProfileId)?.name;
  const scenario = project.scenarios.find(s => s.id === context.scenarioId)?.name;
  const goal = <div className="model-goal-card canvas">
    <div className="model-goal canvas"><span className="model-kind">Goal</span><strong>{project.title}</strong></div>
  </div>;
  return <section className="presentation" aria-labelledby="presentation-title">
    <header className="presentation-header">
      <div>
        <p className="model-kind">Discussion view · live draft, not a frozen snapshot</p>
        <h2 id="presentation-title" tabIndex={-1} ref={heading}>{project.title}</h2>
        <p className="muted" data-testid="presentation-context">
          Profile {profile ?? "none"} · {scenario ? `scenario ${scenario}` : "base model"} · {dirty
            ? "unsaved changes: this view shows the current draft"
            : `saved revision ${fingerprint.slice(0, 12)}`}
        </p>
      </div>
      <button type="button" className="primary" onClick={onExit}>Exit presentation</button>
    </header>
    {project.description && <p className="presentation-description">{project.description}</p>}
    <div className="tree-panel presentation-diagram">
      <ModelTree project={project} index={index} validation={validation} selectedId={selectedId}
        presentation={{ ...presentation, mode: "canvas" }} onPresentation={onPresentation} onSelect={setSelectedId}
        onRemove={() => undefined} onFocusRemoved={() => heading.current?.focus()} busy={false} readOnly
        diagram={{ goal, profileId: context.resolvedProfileId, weights }} />
    </div>
    <section className="presentation-inputs" aria-labelledby="presentation-inputs">
      <h3 id="presentation-inputs">Open input problems</h3>
      {errors.length ? <>
        <ul>{errors.slice(0, 12).map((issue, i) => <li key={i}>{issue.message} <code className="muted small">{issue.code}</code></li>)}</ul>
        {errors.length > 12 && <p className="muted small">and {String(errors.length - 12)} more in the editor’s Problems panel.</p>}
      </> : <p>The engine reports no errors in the current draft.</p>}
    </section>
    <p className="muted small">Scores express the decision maker’s preferences over the stated ranges; they are not predictions of
      success. Entered inputs are not verified evidence, and input coverage is not confidence.</p>
  </section>;
}
