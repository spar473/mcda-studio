import { useState } from "react";
import type { AnySensitivityProbe, AnySensitivityResult, Project, SensitivityResult, SortingSensitivityResult, ValidationReport } from "../api/types";
import { errorsOf } from "../model/issues";
import { buildTree, flatten, isLeaf, pathNames } from "../model/tree";
import type { AnalysisContext } from "../state/analysisContext";
import { useSensitivity, useSensitivityProbe } from "../state/useSensitivity";
import { colourFor, SensitivityChart } from "./SensitivityChart";
import { CommitNumber } from "./ui";

interface Props {
  project: Project;
  context: AnalysisContext;
  validation: ValidationReport;
  onSelectCriterion: (criterionId: string) => void;
}

const fmt = (v: number | null | undefined, digits = 4) =>
  v === null || v === undefined ? "—" : v.toFixed(digits);

/** Which criteria the engine will vary: it needs a sibling, and a baseline below one. */
function eligibility(project: Project) {
  const out = new Map<string, string | null>();
  for (const entry of flatten(buildTree(project.criteria))) {
    const id = entry.node.id;
    const siblings = project.criteria.filter(
      (c) => (c.parent_id ?? null) === (entry.node.parent_id ?? null),
    );
    out.set(id, siblings.length < 2
      ? "Only child: its local weight is fixed at 1, so there is nothing to redistribute."
      : null);
  }
  return out;
}

function Stability({ result, names }: { result: SensitivityResult; names: Map<string, string> }) {
  const [rlo, rhi] = result.ranking_stable_range;
  const [wlo, whi] = result.winner_stable_range;
  const zero = rhi - rlo < 1e-12;
  return <dl className="stability" aria-label="Stability intervals">
    <dt>Winner unchanged over</dt>
    <dd>{fmt(wlo, 3)} – {fmt(whi, 3)}{wlo <= 0 && whi >= 1 && " (the whole range)"}</dd>
    <dt>Full ranking unchanged over</dt>
    <dd>{zero
      ? <>a single point ({fmt(rlo, 3)}): the baseline sits exactly on a crossover, where alternatives are tied</>
      : <>{fmt(rlo, 3)} – {fmt(rhi, 3)}</>}</dd>
    <dt>First winner change below baseline</dt>
    <dd>{result.first_winner_change_down
      ? <>at {fmt(result.first_winner_change_down.weight, 4)} → {names.get(result.first_winner_change_down.to_winner) ?? result.first_winner_change_down.to_winner}</>
      : "none in this direction"}</dd>
    <dt>First winner change above baseline</dt>
    <dd>{result.first_winner_change_up
      ? <>at {fmt(result.first_winner_change_up.weight, 4)} → {names.get(result.first_winner_change_up.to_winner) ?? result.first_winner_change_up.to_winner}</>
      : "none in this direction"}</dd>
  </dl>;
}

/** First class change either way, per alternative, from the engine's exact roots. */
function ClassChanges({ result, names, onProbe }: {
  result: SortingSensitivityResult; names: Map<string, string>; onProbe: (weight: number) => void;
}) {
  const classes = new Map(result.classes.map((c) => [c.class_id, c.name]));
  // Raising the weight past a change leads to the class above it; lowering it, to the class below.
  const change = (c: SortingSensitivityResult["class_changes"][number]["first_change_up"], raising: boolean) => c
    ? <><button type="button" className="link" onClick={() => onProbe(c.weight)}>{fmt(c.weight)}</button> → {classes.get(raising ? c.class_after : c.class_before)}</>
    : "none in this direction";
  return <>
    <h3>Class changes</h3>
    <p className="muted small">The exact local weight at which each alternative's class first changes, where its overall value meets a class
      boundary (within 1e-12, a value on a boundary is in the higher class). Boundaries stay fixed on the value scale.</p>
    <table className="grid compact" aria-label="Class changes">
      <thead><tr><th>Alternative</th><th>Class at baseline</th><th>First change below baseline</th><th>First change above baseline</th></tr></thead>
      <tbody>{result.class_changes.map((c) => <tr key={c.alternative_id}>
        <th scope="row">{names.get(c.alternative_id) ?? c.alternative_id}</th>
        <td>{classes.get(c.base_class_id)}</td>
        <td>{change(c.first_change_down, false)}</td>
        <td>{change(c.first_change_up, true)}</td>
      </tr>)}</tbody>
    </table>
  </>;
}

export function SensitivityPanel({ project, context, validation, onSelectCriterion }: Props) {
  const [nodeId, setNodeId] = useState<string | null>(null);
  const [cursor, setCursor] = useState<number | null>(null);
  const [hidden, setHidden] = useState<string[]>([]);

  const errors = errorsOf(validation).length;
  const reasons = eligibility(project);
  const ordered = flatten(buildTree(project.criteria));
  const selectable = ordered.filter((e) => reasons.get(e.node.id) === null);
  const blockedReason = nodeId ? reasons.get(nodeId) ?? null : null;

  const request = useSensitivity(project, context, nodeId, errors === 0 && !blockedReason);
  const result: AnySensitivityResult | null = request.status === "ready" ? request.result : null;
  // The cursor defaults to the baseline, and follows the engine's own grid until probed.
  const at = cursor ?? result?.base_weight ?? null;
  const probe = useSensitivityProbe(project, context, nodeId, at, errors === 0 && !blockedReason);
  const probed: AnySensitivityProbe | null = probe.status === "ready" ? probe.result : null;

  const names = new Map(project.alternatives.map((a) => [a.id, a.name]));
  const visible = (result?.baseline_ranking ?? []).filter((a) => !hidden.includes(a));
  const profile = project.weight_profiles.find((p) => p.id === context.resolvedProfileId);
  const scenario = project.scenarios.find((s) => s.id === context.scenarioId);

  return <section className="panel" aria-label="Sensitivity">
    <h2>Sensitivity</h2>
    <p className="muted">
      Explore how the ranking would respond if one criterion's <strong>local weight</strong> changed,
      holding every other branch in its current proportion. This is a what-if view only: nothing here
      edits a swing judgement, a profile or the saved project.
    </p>
    <p className="note" aria-label="Sensitivity context">
      Profile “{profile?.name ?? context.resolvedProfileId ?? "none"}” · {scenario ? `scenario “${scenario.name}”` : "base model"} · revision <code>{context.fingerprint.slice(0, 12)}</code>
    </p>

    <label className="sensitivity-select">Criterion to vary
      <select aria-label="Criterion to vary" value={nodeId ?? ""}
        onChange={(e) => { setNodeId(e.target.value || null); setCursor(null); if (e.target.value) onSelectCriterion(e.target.value); }}>
        <option value="">Choose a criterion…</option>
        {ordered.map((e) => <option key={e.node.id} value={e.node.id} disabled={reasons.get(e.node.id) !== null}>
          {" ".repeat((e.depth - 1) * 3)}{e.node.name}
          {isLeaf(project.criteria, e.node.id) ? "" : " (objective)"}
          {reasons.get(e.node.id) !== null ? " — cannot vary" : ""}
        </option>)}
      </select>
    </label>
    {selectable.length === 0 && <p role="status">No criterion in this model can be varied: every sibling group has a single child.</p>}

    {errors > 0 && <p role="status">The model has {errors} validation error(s), so it cannot be evaluated. Fix them in the Problems panel first.</p>}
    {blockedReason && <p role="status" className="banner warning">{blockedReason} Choose another criterion.</p>}
    {nodeId && !blockedReason && request.status === "loading" && <p role="status">Calculating sensitivity…</p>}
    {request.status === "error" && <><p role="alert">{request.message}</p>
      <button type="button" onClick={request.retry}>Retry sensitivity</button></>}

    {result && <>
      <p className="selected-weight-path">
        {pathNames(project.criteria, result.node_id).join(" › ")} · baseline local weight <strong>{fmt(result.base_weight)}</strong>
      </p>
      {result.diagnostics.map((d, i) => <p key={i} className={`banner ${d.severity}`} role="status">
        <span className="code">{d.code}</span> {d.message}
      </p>)}

      <div className="sensitivity-layout">
        <div>
          <SensitivityChart result={result} names={names} visible={visible}
            cursor={at ?? result.base_weight} onCursor={(w) => { setCursor(w); }}/>
          <ul className="legend" aria-label="Alternatives shown">
            {result.baseline_ranking.map((alt, i) => <li key={alt}>
              <label>
                <input type="checkbox" checked={!hidden.includes(alt)}
                  onChange={(e) => { setHidden((h) => e.target.checked ? h.filter((x) => x !== alt) : [...h, alt]); }}/>
                <span className="swatch" style={{ background: colourFor(i) }} aria-hidden="true"/>
                {names.get(alt) ?? alt}
              </label>
            </li>)}
          </ul>
          {hidden.length > 0 && <p className="muted small" role="status">
            {hidden.length} alternative(s) hidden from the chart. Hiding changes the view only — every
            number below still comes from the complete model.
          </p>}
        </div>

        <div className="sensitivity-side">
          <h3>Hypothetical weight</h3>
          <label>Local weight
            <CommitNumber label="Hypothetical local weight" value={at}
              onCommit={(v) => { if (v !== null && v >= 0 && v <= 1) setCursor(v); }}/>
          </label>
          <p className="muted small">
            Clicking the chart snaps to the engine's own grid. Typing a number, or choosing a crossover
            below, probes that exact weight on the server.
          </p>
          {result.crossovers.length > 0 && <>
            <h3>Exact crossovers</h3>
            <ul className="crossovers" aria-label="Exact crossovers">
              {result.crossovers.map((c, i) => <li key={i}>
                <button type="button" className="link" onClick={() => { setCursor(c.weight); }}>
                  {fmt(c.weight)}
                </button>{" "}
                {names.get(c.alternative_a) ?? c.alternative_a} / {names.get(c.alternative_b) ?? c.alternative_b}
                <span className="muted small"> · leader {names.get(c.leader_before) ?? c.leader_before} → {names.get(c.leader_after) ?? c.leader_after}</span>
              </li>)}
            </ul>
          </>}
          {result.crossovers.length === 0 && <p className="muted small">
            No two alternatives swap order anywhere in [0, 1] for this criterion. That says nothing
            about changing several weights at once.
          </p>}
          <Stability result={result} names={names}/>
        </div>
      </div>
      {result.method === "mavt_sorting" && <ClassChanges result={result} names={names} onProbe={(w) => { setCursor(w); }}/>}

      <h3>Values at the probed weight</h3>
      {probe.status === "loading" && <p role="status">Probing…</p>}
      {probe.status === "error" && <><p role="alert">{probe.message}</p>
        <button type="button" onClick={probe.retry}>Retry probe</button></>}
      {probed && <>
        <p className="muted small">
          Local weight <strong>{fmt(probed.weight)}</strong>{Math.abs(probed.weight - probed.base_weight) < 1e-12 && " (the baseline)"} ·
          every value, rank and weight below is computed by the engine at exactly this weight.
          {probed.winner_differs_from_baseline
            ? " The rank-one winner set differs from the baseline (including ties)."
            : probed.ranking_differs_from_baseline
              ? " Competition ranks change below the top; the rank-one winner set is unchanged."
              : " The ranking is unchanged."}
        </p>
        {probed.diagnostics.map((d, i) => <p key={i} className="muted small"><span className="code">{d.code}</span> {d.message}</p>)}
        <table className="grid compact" aria-label="Sensitivity values">
          <thead><tr>
            <th className="num">Rank</th><th>Alternative</th>
            <th className="num">Value here</th><th className="num">Baseline value</th>
            <th className="num">Baseline rank</th><th className="num">Change</th>
            {probed.method === "mavt_sorting" && <><th>Class here</th><th>Baseline class</th></>}
          </tr></thead>
          <tbody>{probed.alternatives.map((a) => <tr key={a.alternative_id}>
            <td className="num">{a.rank}</td>
            <th scope="row">{a.name}</th>
            <td className="num" title={String(a.value)}>{fmt(a.value)}</td>
            <td className="num" title={String(a.baseline_value)}>{fmt(a.baseline_value)}</td>
            <td className="num">{a.baseline_rank}</td>
            <td className="num">{a.rank === a.baseline_rank ? "—" : a.rank < a.baseline_rank ? `▲ ${a.baseline_rank - a.rank}` : `▼ ${a.rank - a.baseline_rank}`}</td>
            {probed.method === "mavt_sorting" && <>
              <td>{probed.classes.find((c) => c.class_id === probed.class_by_alternative[a.alternative_id])?.name}</td>
              <td>{probed.classes.find((c) => c.class_id === probed.baseline_class_by_alternative[a.alternative_id])?.name}</td>
            </>}
          </tr>)}</tbody>
        </table>
        <details className="weight-tree">
          <summary>Hypothetical weights at this point</summary>
          <p className="muted small">The varied group's local weights, redistributed proportionally by the engine.</p>
          <ul className="plain">{Object.entries(probed.local_weights).map(([id, w]) => <li key={id}>
            {project.criteria.find((c) => c.id === id)?.name ?? id}: <strong>{fmt(w)}</strong>
            {id === probed.node_id && " (the varied criterion)"}
          </li>)}</ul>
        </details>
      </>}
    </>}
  </section>;
}
