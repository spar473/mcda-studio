import { useEffect, useRef } from "react";
import type { CriterionNode, Operation, Project, SwingRangePreview, ValidationReport, WeightPreview, WeightProfile } from "../api/types";
import { buildTree, childrenOf, flatten, isLeaf, pathNames, pathNodes, type TreeNode } from "../model/tree";
import type { AnalysisContext } from "../state/analysisContext";
import { useWeightPreview } from "../state/usePreviews";
import { CommitNumber } from "./ui";
import { ProfileManager } from "./ProfileManager";

interface Props {
  project: Project; context: AnalysisContext; validation: ValidationReport; busy: boolean;
  apply: (ops: Operation[]) => Promise<boolean>;
  manage: (operation: Operation) => Promise<boolean>;
  onSelectProfile: (profileId: string | null) => void;
  onSelectCriterion: (criterionId: string) => void;
  /** A sibling group to bring into view (null: top level); a new key repeats the request. */
  focusGroup?: { id: string | null; key: number } | null;
}
function SwingRange({ node, range }: { node: CriterionNode; range: SwingRangePreview | undefined }) {
  return <li><strong>{node.name}</strong>: {!range ? "Resolving stated range…" : range.readiness !== "ready" ? <>
    <span className="range-unresolved">Range {range.readiness}; review the definition{range.domain?.source === "local" ? " and local readings" : " or required local readings"}.</span>
    <ul className="small">{range.diagnostics.filter((i) => i.severity === "error").map((issue,i) => <li key={i}><code>{issue.code}</code> {issue.message}</li>)}</ul>
  </> : <>
    <span>Worst {range.worst.join(" / ")} → Best {range.best.join(" / ")} {range.unit ?? ""}</span>
    <span className="muted small"> · {range.domain?.source ?? "explicit labels"} · {range.scale_type}</span>
    {range.domain?.source === "local" && <span className="muted small"> · complete current alternative set; changed ranges require swing review</span>}
    {range.scale_type === "categorical" && <span className="muted small"> · no intrinsic category order</span>}
  </>}</li>;
}

/** Explains one global weight with the engine's own numbers; the browser multiplies nothing. */
function Derivation({ project, criterionId, profile, result }: {
  project: Project; criterionId: string; profile: WeightProfile | undefined; result: WeightPreview | null;
}) {
  const steps = pathNodes(project.criteria, criterionId);
  const target = steps.at(-1);
  if (!target) return null;
  const leaf = isLeaf(project.criteria, target.id);
  const share = (id: string) => result?.path_shares[id];
  return <section className="weight-derivation" aria-label={`Weight derivation for ${target.name}`}>
    <h3>How {target.name}’s weight is derived</h3>
    <p className="muted small">Overall goal › {pathNames(project.criteria, criterionId).join(" › ")}</p>
    {!result ? <p role="status">Derived weights are unavailable until every sibling group is valid.</p> : <>
      <table className="grid compact" aria-label={`Derivation steps for ${target.name}`}>
        <thead><tr><th>Step</th><th className="num">Raw swing rating</th><th className="num">Local weight in its group</th><th className="num">Share of the overall goal</th></tr></thead>
        <tbody>{steps.map((step) => {
          const rating = profile?.judgements[step.id];
          return <tr key={step.id}><th scope="row">{step.name}</th>
            <td className="num">{rating === undefined ? <span className="muted">not supplied</span> : rating}</td>
            <td className="num">{result.local_weights[step.id]?.toFixed(4) ?? "—"}</td>
            <td className="num">{share(step.id)?.toFixed(4) ?? "—"}</td>
          </tr>;
        })}</tbody>
      </table>
      <p className="small">{leaf
        ? <>Each share is the share above it times that step’s local weight, so the global weight of {target.name} is <strong>{share(target.id)?.toFixed(4) ?? "—"}</strong> ({((share(target.id) ?? 0) * 100).toFixed(2)}% of the overall goal). Only leaf criteria carry global weights, and together they sum to one.</>
        : <>{target.name} is an objective, not a leaf. Its branch carries <strong>{share(target.id)?.toFixed(4) ?? "—"}</strong> of the overall goal, divided among its own children. Select a leaf criterion for a complete global weight.</>}</p>
    </>}
  </section>;
}

export function WeightsPanel({ project, context, apply, busy, manage, onSelectProfile, onSelectCriterion, focusGroup }: Props) {
  const request = useWeightPreview(project, context);
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!focusGroup) return;
    const group = panel.current?.querySelector<HTMLElement>(`[data-group-id="${focusGroup.id ?? ""}"]`);
    if (!group) return;
    group.scrollIntoView({ block: "start" });
    (group.querySelector<HTMLInputElement>("input:not(:disabled)") ?? group.querySelector<HTMLElement>("h3"))?.focus();
  }, [focusGroup]);
  const preview = request.status === "ready" ? request.result : null;
  const result = preview?.weights_ready ? preview : null;
  const profile = project.weight_profiles.find((p) => p.id === context.resolvedProfileId);
  const tree = buildTree(project.criteria), ordered = flatten(tree);
  const parents: (CriterionNode | null)[] = [null, ...ordered.map((t) => t.node).filter((n) => !isLeaf(project.criteria,n.id))];
  const showTree = (nodes: TreeNode[]) => <ol>{nodes.map((entry) => {
    const id = entry.node.id, rating = profile?.judgements[id];
    const local = result?.local_weights[id], share = result?.path_shares[id];
    return <li key={id}>
      <button type="button" className="link" title={pathNames(project.criteria,id).join(" › ")} onClick={() => onSelectCriterion(id)}>{entry.node.name}</button>
      <span className="muted small"> · raw {rating === undefined ? "not supplied" : rating} · local {local?.toFixed(4) ?? "unavailable"}
        {entry.children.length === 0
          ? <> · global {result?.global_weights[id]?.toFixed(4) ?? "unavailable"}</>
          : <> · branch share {share?.toFixed(4) ?? "unavailable"}</>}</span>
      {local !== undefined && <meter aria-label={`Tree local weight for ${entry.node.name}`} min={0} max={1} value={local}/>}
      {entry.children.length > 0 && showTree(entry.children)}
    </li>;
  })}</ol>;
  return <section className="panel" aria-label="Weights" ref={panel}>
    <h2>Weights</h2>
    <ProfileManager project={project} context={context} busy={busy} manage={manage} onSelect={onSelectProfile}/>
    <p>Compare the value of each <strong>worst-to-best swing over its stated performance range</strong>, holding other branches at their worst levels. For a group, compare the combined descendant swings, then elicit ratings within that group.</p>
    <p className="muted">You may use 100 as a reference; raw ratings have no upper cap and need not sum to 100. Zero means no value for that swing; missing means no judgement has been supplied. Derived weights are read-only.</p>
    {preview && <p className="note" aria-label="Engine weight interpretation">{preview.weight_basis}</p>}
    {context.criterionId && <div className="selected-weight-path" role="status">
      <Derivation project={project} criterionId={context.criterionId} profile={profile} result={result}/>
    </div>}
    {request.status === "loading" && <p role="status">Previewing weights…</p>}
    {request.status === "error" && <p role="alert">{request.message}</p>}
    {preview && !preview.weights_ready && <p role="status">Weight set incomplete or invalid. Derived weights and bars are unavailable until every sibling group is valid; stated ranges can still be reviewed.</p>}
    {preview && <ul className="issue-list inline" aria-label="Weight preview diagnostics">{preview.diagnostics.map((issue,i) =>
      <li key={i} className={issue.severity}><span className="code">{issue.code}</span> {issue.message}<div className="muted small">{issue.path}</div></li>)}</ul>}
    {project.criteria.length === 0 && <p>Add criteria to elicit swing judgements.</p>}
    {!profile && (context.resolvedProfileId
      ? <p role="alert">The resolved preference profile <code>{context.resolvedProfileId}</code> does not exist in this project. No other profile was substituted, so no weights are shown. Repair the scenario or saved analysis reference, or choose an existing profile above.</p>
      : <p>This project has no weight profile. Create one to begin; no ratings are assumed.</p>)}
    {profile && parents.map((parent) => {
      const kids = childrenOf(project.criteria,parent?.id ?? null);
      if (!kids.length) return null;
      const only = kids.length === 1;
      return <section key={parent?.id ?? "top"} className="weight-group" data-group-id={parent?.id ?? ""} aria-label={`Weight group ${parent ? pathNames(project.criteria,parent.id).join(" › ") : "Top level"}`}>
        <h3 tabIndex={-1}>{parent ? pathNames(project.criteria,parent.id).join(" › ") : "Top level"}</h3>
        <p className="muted small">Sibling raw-rating total: {preview?.sibling_rating_totals[parent?.id ?? "<root>"] ?? "not supplied for every child"}. {only && "An only child has local weight one without a fabricated rating. If a rating is explicitly supplied, it must satisfy the engine’s validity rules."}</p>
        <div className="weight-group-content">
          <fieldset disabled={busy} className="weight-fields"><table className="grid compact" aria-label={`Swing ratings under ${parent ? parent.name : "top level"}`}>
            <thead><tr><th>Item</th><th className="num">Swing rating</th><th className="num">Local weight</th><th className="num">Global weight</th></tr></thead>
            <tbody>{kids.map((kid) => {
              const rating = profile.judgements[kid.id];
              const issues = preview?.diagnostics.filter((issue) => issue.path === `weight_profiles[${profile.id}].judgements.${kid.id}`) ?? [];
              const local = result?.local_weights[kid.id], global = isLeaf(project.criteria,kid.id) ? result?.global_weights[kid.id] : undefined;
              return <tr key={kid.id}><th scope="row"><button type="button" className="link" title={pathNames(project.criteria,kid.id).join(" › ")} onClick={() => onSelectCriterion(kid.id)}>{kid.name}</button></th>
                <td className="num" title={issues.map((i) => i.message).join("\n") || undefined}>
                  <CommitNumber label={`Swing rating for ${kid.name}`} value={rating ?? null} allowEmpty invalid={issues.some((i) => i.severity === "error")}
                    onCommit={(value) => void apply(value === null ? [{op:"clear_judgement",node_id:kid.id,profile_id:profile.id}] : [{op:"set_judgement",node_id:kid.id,rating:value,profile_id:profile.id}])}/>
                  <span className="muted small rating-state">{rating === undefined ? only ? "Not supplied; not required" : "Missing rating" : rating === 0 ? "Zero rating" : "Raw rating"}</span>
                  {only && <span className="muted small rating-state">only item (weight 1)</span>}
                </td>
                <td className="num" title={local === undefined ? undefined : String(local)}>{local === undefined ? "—" : <>{local.toFixed(4)}<meter aria-label={`Local weight for ${kid.name}`} min={0} max={1} value={local}/></>}</td>
                <td className="num" title={global === undefined ? undefined : String(global)}>{global?.toFixed(4) ?? ""}</td>
              </tr>;
            })}</tbody>
          </table></fieldset>
          <div className="swing-cards" aria-label={`Stated swings under ${parent?.name ?? "top level"}`}>
            {kids.map((kid) => {
              const entry=ordered.find((e) => e.node.id===kid.id);
              const leaves=entry ? flatten([entry]).filter((e) => e.children.length===0) : [];
              return <details key={kid.id} open className="swing-card"><summary>{kid.name} · {leaves.length === 1 ? "stated swing" : `${leaves.length} descendant swings`}</summary>
                <ul>{leaves.map((leaf) => <SwingRange key={leaf.node.id} node={leaf.node} range={preview?.swing_ranges[leaf.node.id]}/>)}</ul>
              </details>;
            })}
          </div>
        </div>
      </section>;
    })}
    {ordered.length > 0 && <details className="weight-tree" open><summary>Read-only hierarchical weight tree</summary>
      <dl className="weight-legend" aria-label="What each weight means">
        <dt>Raw swing rating</dt><dd>your elicited judgement of that worst-to-best swing; uncapped and comparable only within one group.</dd>
        <dt>Local weight</dt><dd>that item’s share <em>of its own sibling group</em>; each group’s local weights sum to one.</dd>
        <dt>Branch share</dt><dd>an objective’s share <em>of the overall goal</em>, divided among its children.</dd>
        <dt>Global weight</dt><dd>a leaf criterion’s share <em>of the overall goal</em>; all leaves sum to one. Derived, never edited directly.</dd>
      </dl>
      <p className="muted small">Bars show local weights only, so lengths are comparable within a group but not between groups. Select any item to see how its weight is derived.</p>
      {showTree(tree)}</details>}
  </section>;
}
