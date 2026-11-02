import { ProxyCriterionPanel } from "./ProxyCriterionPanel";
import type { ProxyInputs } from "../api/types";
import type { ModelComparison } from "../api/types";
import type { ExternalProposals } from "../api/types";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { CalculationAssignment, EvidenceDossier, Issue, Meta, Operation, Project } from "../api/types";
import { buildCoverage, reconcileCoverageCell, type CoverageCell } from "../model/coverage";
import { parseIssuePath, tabForIssue, type EditorTab } from "../model/issues";
import { isDirty } from "../model/session";
import { resolveContext, type AnalysisContext } from "../state/analysisContext";
import { useStructureWeights } from "../state/usePreviews";
import { AnalysisControls } from "./AnalysisControls";
import { ClassesPanel } from "./ClassesPanel";
import { ComparePanel } from "./ComparePanel";
import { OutrankingPanel } from "./OutrankingPanel";
import { PairwisePanel } from "./PairwisePanel";
import { QuestionsPanel } from "./QuestionsPanel";
import { EvidenceWorkspacePanel } from "./EvidenceWorkspacePanel";
import { DecisionRecordPanel } from "./DecisionRecordPanel";
import { RequirementsPanel } from "./RequirementsPanel";
import { UncertaintyPanel } from "./UncertaintyPanel";
import { useEditorStore } from "../state/editorStore";
import { setLeaveGuard } from "../state/navigation";
import { AlternativesPanel } from "./AlternativesPanel";
import { CoverageMatrix } from "./CoverageMatrix";
import { Inspector } from "./Inspector";
import { MeasurementsPanel } from "./MeasurementsPanel";
import { DerivedMeasurementsPanel } from "./DerivedMeasurementsPanel";
import { ProjectPanel } from "./ProjectPanel";
import { ResultsPanel } from "./ResultsPanel";
import { ScenarioPanel } from "./ScenarioPanel";
import { ScopedAnalysis } from "../state/useScenarioAnalysis";
import { SensitivityPanel } from "./SensitivityPanel";
import type { DiagramWeights, TreePresentation } from "./ModelTree";
import { PresentationView } from "./PresentationView";
import { TreePanel } from "./TreePanel";
import { Banner, ConfirmDialog } from "./ui";
import { ValidationPanel } from "./ValidationPanel";
import { ValueFunctionEditor, type CandidateGuard } from "./ValueFunctionEditor";
import { WeightsPanel } from "./WeightsPanel";

// The sections are grouped into the four stages of a decision; method editors join Build when used.
const STAGES: { name: string; icon: string; tabs: { id: EditorTab; label: string }[] }[] = [
  { name: "Build", icon: "M4 20h16M6 20V9l6-5 6 5v11M10 20v-6h4v6", tabs: [
    { id: "project", label: "Project" },
    { id: "model", label: "Model" },
    { id: "alternatives", label: "Alternatives" },
    { id: "measurements", label: "Measurements" },
    { id: "weights", label: "Weights" },
    { id: "requirements", label: "Requirements" },
    { id: "classes", label: "Classes" },
    { id: "uncertainty", label: "Uncertainty" },
    { id: "outranking", label: "Outranking" },
    { id: "pairwise", label: "Pairwise" },
  ] },
  { name: "Analyse", icon: "M4 20V10M10 20V4M16 20v-8M22 20H2", tabs: [
    { id: "results", label: "Results" },
    { id: "sensitivity", label: "Sensitivity" },
    { id: "scenarios", label: "Scenarios" },
    { id: "compare", label: "Compare" },
  ] },
  { name: "Evidence", icon: "M7 3h7l5 5v13H7zM14 3v5h5M10 14l2 2 4-4", tabs: [
    { id: "evidence", label: "Evidence" },
    { id: "questions", label: "Open Questions" },
  ] },
  { name: "Decide", icon: "M5 21V4M5 4h11l-2 4 2 4H5", tabs: [{ id: "decision", label: "Decision" }] },
];

interface Props {
  projectId: string;
  onClose: () => void;
  onOpenOther: (id: string) => void;
}

function isTextTarget(t: EventTarget | null): boolean {
  return t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement || t instanceof HTMLSelectElement;
}

/** Engine weights for the canvas and presentation, requested only while one of them shows them. */
function StructureWeights({ project, context, enabled, children }: {
  project: Project; context: AnalysisContext; enabled: boolean; children: (weights: DiagramWeights) => ReactNode;
}) {
  const request = useStructureWeights(project, context, enabled);
  const profile = project.weight_profiles.find((p) => p.id === context.resolvedProfileId)?.name;
  const scenario = project.scenarios.find((s) => s.id === context.scenarioId)?.name;
  const weights: DiagramWeights = !enabled ? { status: "off" }
    : request.status === "loading" ? { status: "loading" }
      : request.status === "error" ? { status: "error", message: request.message }
        : request.result.weights_ready
          ? { status: "ready", preview: request.result, context: `profile ${profile ?? "none"} · ${scenario ? `scenario ${scenario}` : "base model"}` }
          : { status: "incomplete" };
  return <>{children(weights)}</>;
}

export function EditorScreen({ projectId, onClose, onOpenOther }: Props) {
  const { store, state } = useEditorStore(projectId);
  const [tab, setTab] = useState<EditorTab>("model");
  const [treePresentation, setTreePresentation] = useState<TreePresentation>({ mode: "canvas", collapsed: new Set() });
  const [goalSelected, setGoalSelected] = useState(false);
  const [focusTitleKey, setFocusTitleKey] = useState(0);
  const [focusNameKey, setFocusNameKey] = useState(0);
  const selectedId = state.analysis.criterionId;
  const setSelectedId = useCallback((criterionId: string | null) => { setGoalSelected(false); setFocusNameKey(0); store.selectAnalysis({ criterionId }); }, [store]);
  const nameFocusSequence = useRef(0);
  const [focusCell, setFocusCell] = useState<{ alternativeId: string; criterionId: string } | null>(null);
  const [coverageSelection, setCoverageSelection] = useState<CoverageCell | null>(null);
  const [coverageFocusKey, setCoverageFocusKey] = useState(0);
  const [coverageReturn, setCoverageReturn] = useState(false);
  // Canvas destinations and presentation: transient view state, never project data or history.
  const focusSequence = useRef(0);
  const [focusSetupKey, setFocusSetupKey] = useState(0);
  const [weightsFocus, setWeightsFocus] = useState<{ id: string | null; key: number } | null>(null);
  const [alternativeFocus, setAlternativeFocus] = useState<{ id: string; key: number } | null>(null);
  const [showWeights, setShowWeights] = useState(true);
  const [presenting, setPresenting] = useState(false);
  const presentButton = useRef<HTMLButtonElement>(null);
  const wasPresenting = useRef(false);
  useEffect(() => {
    if (wasPresenting.current && !presenting) presentButton.current?.focus();
    wasPresenting.current = presenting;
  }, [presenting]);
  const editWeights = useCallback((groupId: string | null) => {
    setWeightsFocus({ id: groupId, key: ++focusSequence.current }); setTab("weights");
  }, []);
  const editAlternative = useCallback((id: string) => {
    setAlternativeFocus({ id, key: ++focusSequence.current }); setTab("alternatives");
  }, []);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [evidenceDossier, setEvidenceDossier] = useState<EvidenceDossier | null>(null);
  const [proxyInputs, setProxyInputs] = useState<ProxyInputs | null>(null);
  const [proxyDirty, setProxyDirty] = useState(false);
  const proxyDirtyRef = useRef(false);
  const proxyDirtyChanged = useCallback((value: boolean) => { proxyDirtyRef.current = value; setProxyDirty(value); }, []);
  const [modelComparison, setModelComparison] = useState<ModelComparison | null>(null);
  const [proposalWorkspace, setProposalWorkspace] = useState<ExternalProposals | null>(null);
  const [evidenceDirty, setEvidenceDirty] = useState(false);
  const evidenceDirtyRef = useRef(false);
  const evidenceDirtyChanged = useCallback((value: boolean) => { evidenceDirtyRef.current = value; setEvidenceDirty(value); }, []);
  // A previewed decision record that has not been exported is protected like unexported reviews.
  const [decisionDirty, setDecisionDirty] = useState(false);
  const decisionDirtyRef = useRef(false);
  const decisionDirtyChanged = useCallback((value: boolean) => { decisionDirtyRef.current = value; setDecisionDirty(value); }, []);
  // Unexported calculation history is protected the same way: Save stores the project only.
  const [calculationDirty, setCalculationDirty] = useState(false);
  const calculationDirtyRef = useRef(false);
  const calculationDirtyChanged = useCallback((value: boolean) => { calculationDirtyRef.current = value; setCalculationDirty(value); }, []);

  useEffect(() => {
    api
      .meta()
      .then(setMeta)
      .catch(() => undefined);
  }, []);

  const [functionEditor, setFunctionEditor] = useState(false);
  const [editorScenario, setEditorScenario] = useState<string | null>(null);
  const [candidateDirty, setCandidateDirty] = useState(false);
  const candidateGuard = useRef<CandidateGuard | null>(null);
  const onCandidateGuard = useCallback((guard: CandidateGuard | null) => {
    candidateGuard.current = guard; setCandidateDirty(guard?.dirty ?? false);
  }, []);
  const saveCurrent = useCallback(async () => {
    if (proxyDirtyRef.current) { setTab("compare"); return false; }
    if (evidenceDirtyRef.current) { setTab("evidence"); return false; }
    if (decisionDirtyRef.current) { setTab("decision"); return false; }
    if (calculationDirtyRef.current) { setTab("measurements"); return false; }
    if (candidateGuard.current?.dirty && !await candidateGuard.current.commit()) return false;
    const outcome = await store.save();
    return outcome === "saved" || outcome === "nothing-to-save";
  }, [store]);
  const session = state.session;
  const coverage = useMemo(() => session ? buildCoverage(session.draft.project, session.draft.validation) : null,
    [session?.draft]); // eslint-disable-line react-hooks/exhaustive-deps
  const coverageCell = coverage ? reconcileCoverageCell(coverage, coverageSelection) : null;
  // Clear on the accepted revision itself. Undo may restore data, but cannot resurrect selection.
  if (coverageSelection && !coverageCell) { setCoverageSelection(null); setCoverageReturn(false); setFocusCell(null); }
  const dirty = proxyDirty || evidenceDirty || decisionDirty || calculationDirty || candidateDirty || (session ? isDirty(session) : false);
  const context = useMemo(() => session ? resolveContext(session.draft.project, session.draft.fingerprint, state.analysis) : null,
    [session, state.analysis]);

  // Leaving the editor (Close, browser back, a typed address) is confirmed while dirty.
  useEffect(() => {
    if (!session) return;
    setLeaveGuard({
      title: session.draft.project.title,
      isDirty: () => {
        const s = store.getState().session;
        return proxyDirtyRef.current || evidenceDirtyRef.current || decisionDirtyRef.current || calculationDirtyRef.current || (candidateGuard.current?.dirty ?? false) || (s ? isDirty(s) : false);
      },
      save: saveCurrent,
    });
    return () => setLeaveGuard(null);
  }, [store, saveCurrent, session?.draft.project.title]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault(); // asks the browser to confirm leaving the page
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.altKey || presenting) return;
      const key = e.key.toLowerCase();
      if (key === "s") {
        e.preventDefault();
        void saveCurrent();
      } else if (key === "z" && !isTextTarget(e.target) && !functionEditor) {
        e.preventDefault();
        void (e.shiftKey ? store.redo() : store.undo());
      } else if (key === "y" && !isTextTarget(e.target) && !functionEditor) {
        e.preventDefault();
        void store.redo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [store, saveCurrent, functionEditor, presenting]);

  const apply = useCallback((ops: Operation[]) => store.apply(ops), [store]);
  // A reviewed calculation is applied as one batch, hence one undo step; the panel checks the result.
  const applyCalculated = useCallback(async (assignments: CalculationAssignment[]) => {
    const ok = await store.apply(assignments.map(a => ({ op: "set_performance" as const, alternative_id: a.alternative_id, criterion_id: a.criterion_id, value: a.value })));
    return ok ? store.getState().session?.draft.fingerprint ?? null : null;
  }, [store]);

  const manageProfile = useCallback(async (operation: Operation) => {
    const before = new Set(store.getState().session?.draft.project.weight_profiles.map((p) => p.id));
    if (!await store.apply([operation])) return false;
    const current = store.getState().session?.draft.project;
    if (operation.op === "create_weight_profile" || operation.op === "duplicate_weight_profile") {
      const added = current?.weight_profiles.find((p) => !before.has(p.id));
      if (added) store.selectAnalysis({ profileId: added.id });
    } else if (operation.op === "remove_weight_profile") {
      store.selectAnalysis({ profileId: operation.replacement_profile_id ?? null });
    }
    return true;
  }, [store]);

  const manageScenario = useCallback(async (operation: Operation) => {
    const before = new Set(store.getState().session?.draft.project.scenarios.map(s=>s.id));
    if(!await store.apply([operation]))return false;
    if(operation.op === "create_scenario" || operation.op === "duplicate_scenario") {
      const added=store.getState().session?.draft.project.scenarios.find(s=>!before.has(s.id));
      if(added)store.selectAnalysis({scenarioId:added.id});
    } else if(operation.op === "remove_scenario") {
      store.selectAnalysis({scenarioId:operation.replacement_scenario_id ?? null});
    }
    return true;
  },[store]);

  const addCriterion = useCallback(
    async (parentId: string | null, position: number | null, discard: boolean) => {
      const before = new Set(store.getState().session?.draft.project.criteria.map((n) => n.id));
      const ok = await store.apply([
        {
          op: "add_criterion",
          name: "New criterion",
          parent_id: parentId,
          position,
          discard_leaf_data: discard,
        },
      ]);
      if (!ok) return;
      const added = store
        .getState()
        .session?.draft.project.criteria.find((n) => !before.has(n.id));
      if (added) {
        setSelectedId(added.id);
        setFocusNameKey(++nameFocusSequence.current);
      }
    },
    [store, setSelectedId],
  );

  const goToIssue = useCallback((issue: Issue) => {
    const target = parseIssuePath(issue.path);
    setTab(tabForIssue(issue));
    if (target.kind === "scenario") store.selectAnalysis({scenarioId:target.id});
    if (target.kind === "criterion") { setSelectedId(target.id); setFocusSetupKey(++focusSequence.current); }
    if (target.kind === "performance") {
      const cell = { alternativeId: target.alternativeId, criterionId: target.criterionId };
      if (coverage && reconcileCoverageCell(coverage, cell)) {
        setCoverageSelection(cell); setCoverageReturn(true); setSelectedId(target.criterionId);
      }
      setFocusCell(cell);
      const node = coverage?.tree.byId.get(target.criterionId);
      if (node && (!node.scale || !node.value_function)) {
        setSelectedId(node.id); setFocusSetupKey(++focusSequence.current); setTab("model");
      }
    }
  }, [coverage, setSelectedId, store]);

  const selectedNode = useMemo(
    () => session?.draft.project.criteria.find((n) => n.id === selectedId) ?? null,
    [session, selectedId],
  );

  if (state.status === "loading") {
    return (
      <div className="editor-loading" role="status">
        Loading project…
      </div>
    );
  }
  if (state.status === "error" || !session || !context) {
    return (
      <main className="dashboard">
        <Banner kind="error">
          {state.loadError?.code === "PROJECT_NOT_FOUND"
            ? "This project does not exist (it may have been deleted)."
            : (state.loadError?.message ?? "The project could not be opened.")}
        </Banner>
        <p>
          <button type="button" onClick={onClose}>
            Back to projects
          </button>
        </p>
      </main>
    );
  }

  const { project, validation } = session.draft;
  const busy = state.pending > 0 || state.saving;
  // Method-specific editors appear only when the viewed method uses them or the project holds their section.
  const viewedMethod = meta?.methods.find((m) => m.name === context.configuration.method);
  const showClasses = Boolean(project.sorting) || Boolean(viewedMethod?.capabilities.includes("classes"));
  const showUncertainty = Boolean(project.smaa) || Boolean(viewedMethod?.capabilities.includes("acceptability"));
  const showOutranking = Boolean(project.promethee) || Boolean(viewedMethod?.capabilities.includes("flows"));
  const showPairwise = Boolean(project.ahp) || Boolean(viewedMethod?.capabilities.includes("consistency"));
  // A method editor opened from elsewhere (for example a comparison column's link) shows its tab too.
  const shown = (id: EditorTab) => id === tab || ((id !== "classes" || showClasses) && (id !== "uncertainty" || showUncertainty) &&
    (id !== "outranking" || showOutranking) && (id !== "pairwise" || showPairwise));
  const useMethodAsDefault = () => { void apply([{ op: "set_analysis_method", method: context.configuration.method }]); };
  const selectCoverage = (cell: CoverageCell) => {
    setCoverageSelection(current => current?.alternativeId === cell.alternativeId && current.criterionId === cell.criterionId ? current : cell);
    if (selectedId !== cell.criterionId) setSelectedId(cell.criterionId);
  };
  const setupCriterion = (id: string) => {
    setSelectedId(id); setFocusSetupKey(++focusSequence.current); setTab("model");
  };
  const openCoverage = (cell: CoverageCell) => {
    setCoverageReturn(true);
    const node = coverage?.tree.byId.get(cell.criterionId);
    if (!node?.scale || !node.value_function) setupCriterion(cell.criterionId);
    else { setFocusCell({ ...cell }); setTab("measurements"); }
  };
  const returnToCoverage = () => {
    setTab("model"); setTreePresentation(p => ({ ...p, mode: "canvas" }));
    setFocusSetupKey(0); setFocusNameKey(0);
    setCoverageReturn(false); setCoverageFocusKey(k => k + 1);
  };
  const openCoverageAlternative = (id: string) => {
    const criterionId = coverageCell?.criterionId ?? coverage?.leaves[0]?.id;
    if (criterionId) { selectCoverage({ alternativeId: id, criterionId }); setCoverageReturn(true); }
    editAlternative(id);
  };
  // A configured leaf opens its value-function editor; an unconfigured one leads to its setup.
  const editFunction = (id: string) => {
    const node = project.criteria.find((n) => n.id === id);
    setSelectedId(id);
    if (node?.scale && node.value_function) { setEditorScenario(null); setFunctionEditor(true); }
    else setFocusSetupKey(++focusSequence.current);
  };

  if (presenting) {
    return (
      <div className="editor presenting">
        <StructureWeights project={project} context={context} enabled={showWeights}>{(weights) =>
          <PresentationView project={project} validation={validation} context={context} fingerprint={session.draft.fingerprint}
            dirty={dirty} presentation={treePresentation} onPresentation={setTreePresentation} weights={weights}
            onExit={() => setPresenting(false)} />}
        </StructureWeights>
      </div>
    );
  }

  return (
    <div className="editor">
      <header className="appbar editor-bar">
        <button type="button" className="link back" onClick={onClose}>
          ← Projects
        </button>
        <h1 className="project-title" title={project.title}>
          {project.title}
        </h1>
        <span
          className={`save-state ${dirty ? "dirty" : "clean"}`}
          role="status"
          data-testid="save-state"
          aria-live="polite"
        >
          {state.saving ? "Saving…" : candidateDirty ? "● Pending candidate (not applied)" : dirty ? "● Unsaved changes" : "All changes saved"}
        </span>
        <span className="spacer" />
        <button type="button" disabled={session.past.length === 0 || busy || functionEditor} onClick={() => void store.undo()} title="Undo (Ctrl/⌘+Z)">
          Undo
        </button>
        <button type="button" disabled={session.future.length === 0 || busy || functionEditor} onClick={() => void store.redo()} title="Redo (Ctrl/⌘+Shift+Z)">
          Redo
        </button>
        <button type="button" className="primary" disabled={!dirty || busy} onClick={() => void saveCurrent()} title="Save (Ctrl/⌘+S)">
          Save
        </button>
      </header>

      {state.notice && (
        <Banner kind={state.notice.kind === "error" ? "error" : "info"} onDismiss={() => store.dismissNotice()}>
          {state.notice.message}
        </Banner>
      )}

      <AnalysisControls project={project} context={context} disabled={busy} onSelect={(patch) => store.selectAnalysis(patch)}
        methods={meta?.methods} onUseMethodAsDefault={useMethodAsDefault} />
      {project.description.startsWith("Illustrative starter inputs require your review;") && <Banner kind="info">Illustrative starter inputs require your review. Carried human acceptances and saved runs were cleared; keep the exported lineage receipt and sidecars.</Banner>}
      {state.anchorReview && <div className="banner warning" role="status">
        Preference ranges or analysis context changed. Local anchors may also change with measurements or alternatives. Review swing judgements over the applicable worst-to-best ranges.
        <button type="button" onClick={() => setTab("weights")}>Review swing judgements</button>
        <button type="button" onClick={() => store.acknowledgeAnchorReview()}>I have reviewed the swing judgements</button>
      </div>}
      <div className="editor-body">
        <div className="editor-side">
          <nav className="stage-nav" aria-label="Editor sections">
            {STAGES.map((stage) => (
              <div key={stage.name} className="stage">
                <h2 className="stage-name" id={`stage-${stage.name}`}>
                  <svg className="stage-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={stage.icon} /></svg>
                  {stage.name}
                </h2>
                <div role="tablist" aria-labelledby={`stage-${stage.name}`} aria-orientation="vertical">
                  {stage.tabs.filter((t) => shown(t.id)).map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      role="tab"
                      id={`tab-${t.id}`}
                      aria-selected={tab === t.id}
                      aria-controls="tabpanel"
                      className={tab === t.id ? "active" : ""}
                      onClick={() => {
                        setWeightsFocus(null); setAlternativeFocus(null);
                        if (t.id === "model" && coverageReturn && coverageCell) returnToCoverage(); else setTab(t.id);
                      }}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </nav>
          <ValidationPanel report={validation} onGo={goToIssue} />
        </div>
        <div className="tabpanel" id="tabpanel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
          {coverageReturn && coverageCell && <p><button type="button" onClick={returnToCoverage}>Return to coverage</button></p>}
          {tab === "project" && <ProjectPanel project={project} apply={apply} />}
          {tab === "model" && (
            <div className={`split model-workspace ${treePresentation.mode}`}>
              <StructureWeights project={project} context={context} enabled={treePresentation.mode === "canvas" && showWeights}>{(weights) =>
                <TreePanel
                  project={project}
                  validation={validation}
                  selectedId={selectedId}
                  busy={busy}
                  onSelect={setSelectedId}
                  onAdd={addCriterion}
                  apply={apply}
                  presentation={treePresentation}
                  onPresentation={setTreePresentation}
                  onEdit={() => setFocusNameKey(++nameFocusSequence.current)}
                  onGoal={() => { store.selectAnalysis({ criterionId: null }); setGoalSelected(true); setFocusTitleKey(k => k + 1); }}
                  goalSelected={goalSelected && selectedId === null}
                  diagram={{ profileId: context.resolvedProfileId, weights, onEditWeights: editWeights, onEditFunction: editFunction,
                    selectedAlternativeId: coverageCell?.alternativeId,
                    onEditAlternative: openCoverageAlternative, onAddAlternatives: () => setTab("alternatives") }}
                  viewExtras={<>
                    <button type="button" aria-pressed={showWeights} onClick={() => setShowWeights((v) => !v)}>Show weights</button>
                    <button type="button" ref={presentButton} onClick={() => setPresenting(true)}>Present</button>
                  </>}
                />}
              </StructureWeights>
              {goalSelected && selectedId === null ? <ProjectPanel project={project} apply={apply} focusTitleKey={focusTitleKey} busy={busy} /> : <Inspector
                project={project}
                context={context}
                node={selectedNode}
                meta={meta}
                validation={validation}
                apply={apply}
                busy={busy}
                focusNameKey={focusNameKey}
                focusSetupKey={focusSetupKey}
                onEditFunction={() => {setEditorScenario(null);setFunctionEditor(true);}}
                onEditWeights={editWeights}
              />}
              {treePresentation.mode === "canvas" && coverage && <CoverageMatrix index={coverage} selected={coverageCell}
                onSelect={selectCoverage} onOpen={openCoverage} onCriterion={setupCriterion} onAlternative={openCoverageAlternative}
                onIssue={goToIssue} focusKey={coverageFocusKey} />}
            </div>
          )}
          {tab === "alternatives" && <AlternativesPanel project={project} busy={busy} apply={apply} focusAlternative={alternativeFocus} />}
          {tab === "measurements" && <>
            <MeasurementsPanel
              project={project}
              validation={validation}
              busy={busy}
              apply={apply}
              focusCell={focusCell}
              coverage={coverage ?? undefined}
              onGoToCriterion={(id) => {
                setSelectedId(id);
                setTab("model");
              }}
            />
          </>}
          <div hidden={tab !== "measurements"}><DerivedMeasurementsPanel project={project} fingerprint={context.fingerprint}
            onDirty={calculationDirtyChanged} onApply={applyCalculated} busy={busy} configuration={context.configuration} onComparison={setModelComparison}/></div>
          {tab === "weights" && (
            <WeightsPanel project={project} context={context} validation={validation} busy={busy} apply={apply} manage={manageProfile}
              onSelectProfile={(profileId) => store.selectAnalysis({ profileId })} onSelectCriterion={setSelectedId} focusGroup={weightsFocus}/>
          )}
          {tab === "scenarios" && <ScenarioPanel project={project} context={context} busy={busy} manage={manageScenario}
            onSelect={scenarioId=>store.selectAnalysis({scenarioId})} onEdit={criterionId=>{setSelectedId(criterionId);setEditorScenario(context.scenarioId);setFunctionEditor(true);}}/>}
          {tab === "classes" && <ClassesPanel project={project} context={context} busy={busy} apply={apply}/>}
          {tab === "uncertainty" && <UncertaintyPanel project={project} context={context} busy={busy} apply={apply}/>}
          {tab === "outranking" && <OutrankingPanel project={project} context={context} busy={busy} apply={apply}/>}
          {tab === "pairwise" && <PairwisePanel project={project} context={context} busy={busy} apply={apply}/>}
          {tab === "requirements" && <RequirementsPanel project={project} busy={busy} apply={apply}/>}
          <EvidenceWorkspacePanel project={project} fingerprint={context.fingerprint} active={tab === "evidence"}
            onDossier={setEvidenceDossier} onProposals={setProposalWorkspace} onDirty={evidenceDirtyChanged} onMeasurement={(alternativeId, criterionId) => {
              setFocusCell({ alternativeId, criterionId }); setTab("measurements");
            }}/>
          <DecisionRecordPanel project={project} fingerprint={context.fingerprint} active={tab === "decision"} methods={meta?.methods}
            onDirty={decisionDirtyChanged}/>
          {tab === "questions" && <QuestionsPanel project={project} context={context} onOpenTab={setTab} workspaceDossier={evidenceDossier} workspaceProposals={proposalWorkspace} workspaceModels={modelComparison} workspaceProxy={proxyInputs}/>}
          {tab === "sensitivity" && <ScopedAnalysis project={project} context={context}>{report =>
            <SensitivityPanel project={project} context={context} validation={report} onSelectCriterion={setSelectedId}/>}</ScopedAnalysis>}
          {tab === "results" && <ScopedAnalysis project={project} context={context}>{report =>
            <ResultsPanel project={project} context={context} validation={report} onSelectCriterion={setSelectedId} methods={meta?.methods}/>}</ScopedAnalysis>}
          <div hidden={tab !== "compare"}><ProxyCriterionPanel project={project} context={context} onDirty={proxyDirtyChanged} onInputs={setProxyInputs}/></div>
          {tab === "compare" && <ComparePanel project={project} context={context} onOpenTab={setTab}/>}
        </div>
      </div>

      {functionEditor && selectedNode?.scale && (selectedNode.value_function || project.scenarios.find(s=>s.id===context.scenarioId)?.value_function_overrides[selectedNode.id]) && meta && <ValueFunctionEditor
        project={project} context={context} node={selectedNode} meta={meta} apply={apply} targetScenarioId={editorScenario}
        onClose={() => setFunctionEditor(false)} onGuard={onCandidateGuard}/>}
      {state.conflict && (
        <ConfirmDialog
          title="This project was changed elsewhere"
          message="The stored project is no longer the version you started from (it was saved by another window or program). Saving now would overwrite that work, so nothing was written."
          confirmLabel="Reload and discard my changes"
          cancelLabel="Keep editing"
          onCancel={() => store.dismissConflict()}
          onConfirm={() => void store.reload()}
          extra={
            <button
              type="button"
              onClick={() => {
                void store.saveCopy().then((id) => {
                  if (id) {
                    store.dismissConflict();
                    setLeaveGuard(null);
                    onOpenOther(id);
                  }
                });
              }}
            >
              Save mine as a separate copy
            </button>
          }
        />
      )}
    </div>
  );
}
