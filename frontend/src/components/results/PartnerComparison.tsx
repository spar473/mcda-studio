import { useMemo, useState, type KeyboardEvent, type MouseEvent } from "react";
import type { EvidenceDossier, ProfileComparison, Project } from "../../api/types";
import type { AnalysisContext } from "../../state/analysisContext";
import { useProfileComparison } from "../../state/useProfileComparison";
import { CompanyName, companyRow, useCompanyExploration } from "../companyExploration";
import { Caveat, InfoDisclosure } from "../InfoDisclosure";
import { MessageText } from "../IssueText";
import { palette } from "./ResultsCharts";
import { displayNumber } from "./numberDisplay";

export function PartnerComparison({ project, context, dossier }: {
  project: Project; context: AnalysisContext; dossier: EvidenceDossier | null;
}) {
  const defaultLeft = context.resolvedProfileId ?? project.weight_profiles[0]?.id ?? "";
  const defaultRight = project.weight_profiles.find(profile => profile.id !== defaultLeft)?.id ?? "";
  const [selected, setSelected] = useState<[string, string]>([defaultLeft, defaultRight]);
  // A removed profile cannot linger as an invisible selection or an old result.
  const pair = useMemo<[string, string]>(() => {
    const left = project.weight_profiles.some(profile => profile.id === selected[0]) ? selected[0] : defaultLeft;
    const right = selected[1] !== left && project.weight_profiles.some(profile => profile.id === selected[1])
      ? selected[1] : project.weight_profiles.find(profile => profile.id !== left)?.id ?? "";
    return [left, right];
  }, [project.weight_profiles, selected, defaultLeft]);
  const request = useProfileComparison(project, context, pair, dossier);
  function choose(side: 0 | 1, id: string) {
    setSelected(side === 0 ? [id, id === pair[1] ? pair[0] : pair[1]] : [id === pair[0] ? pair[1] : pair[0], id]);
  }
  return <section aria-label="Profile comparison" className="partner-comparison">
    <h3>{["mavt", "mavt_sorting"].includes(context.configuration.method) ? "Compare profiles" : "MAVT profile comparison"}</h3>
    <p>Separate MAVT screenings under each profile. No combined ranking is calculated.</p>
    {project.weight_profiles.length < 2 ? <p role="status">Two weight profiles are needed to compare profiles.</p> : <>
      <div className="toolbar">
        <label>Left profile<select aria-label="Left profile" value={pair[0]} onChange={event => choose(0, event.target.value)}>
          {project.weight_profiles.map(profile => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
        </select></label>
        <label>Right profile<select aria-label="Right profile" value={pair[1]} onChange={event => choose(1, event.target.value)}>
          {project.weight_profiles.map(profile => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
        </select></label>
        <button type="button" onClick={() => setSelected([pair[1], pair[0]])}>Swap profiles</button>
      </div>
      {request.status === "loading" ? <p role="status">Calculating profile comparison…</p>
        : request.status === "error" ? <><p role="alert"><MessageText message={request.message}/></p><button type="button" onClick={request.retry}>Retry profile comparison</button></>
          : <ProfileReadings project={project} comparison={request.result}/>}
    </>}
    <Caveat caption="Preference values under each profile; not probabilities or predictions.">
      The two readings use the same model and measurements with different stated swing ratings. They show preference sensitivity, not independent validation or a prediction of outcomes. Printed ranks are the engine's competition ranks, including ties. Thick lines mark movements of at least two places. Ties share endpoint positions; separate alternative labels connect to those same ranks.
    </Caveat>
  </section>;
}

function ProfileReadings({ comparison, project }: { comparison: ProfileComparison; project: Project }) {
  const exploration = useCompanyExploration();
  const [left, right] = comparison.profiles;
  if (!left || !right) return null;
  if (left.summary.status !== "available" || right.summary.status !== "available") return <>
    {comparison.profiles.filter(profile => profile.summary.status !== "available").map(profile => <p role="status" key={profile.profile_id}>{profile.name}: <MessageText message={profile.summary.reason}/></p>)}
  </>;
  const height = 64 + Math.max(left.summary.rows.length, right.summary.rows.length) * 42;
  // Slots follow each Python summary's order. No client sorting or rank assignment.
  const leftLabelY = new Map(left.summary.rows.map((row, index) => [row.alternative_id, 52 + index * 42]));
  const rightLabelY = new Map(right.summary.rows.map((row, index) => [row.alternative_id, 52 + index * 42]));
  const rightRows = new Map(right.summary.rows.map(row => [row.alternative_id, row]));
  const movements = new Map(comparison.movements.map(movement => [movement.alternative_id, movement]));
  const open = (event: MouseEvent<SVGElement> | KeyboardEvent<SVGElement>, id: string, profileId: string) => {
    if ("key" in event && event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault(); event.currentTarget.focus(); exploration?.open(id, profileId);
  };
  return <>
    {comparison.profiles.map(profile => {
      const missingClass = profile.summary.columns.find(column => column.column === "classes" && !column.available);
      return missingClass ? <p key={profile.profile_id} className="muted small">Classes are not available under {profile.name}. <InfoDisclosure label={`Class details for ${profile.name}`}>{missingClass.reason}</InfoDisclosure></p> : null;
    })}
    <svg className="partner-slopes" viewBox={`0 0 900 ${String(height)}`} role="group" aria-label="Rankings by weight profile">
      <text x="20" y="22">{left.name}</text><text x="880" y="22" textAnchor="end">{right.name}</text>
      {left.summary.rows.map(row => {
        const other = rightRows.get(row.alternative_id), movement = movements.get(row.alternative_id);
        const labelY1 = leftLabelY.get(row.alternative_id), labelY2 = rightLabelY.get(row.alternative_id);
        if (!other || !movement || labelY1 === undefined || labelY2 === undefined) return null;
        // Scale the engine's competition ranks. Separate labels remain linked to
        // coincident tie endpoints; layout positions never replace those ranks.
        const y1 = 52 + (row.rank - 1) * 42, y2 = 52 + (other.rank - 1) * 42;
        const classColor = (id: string | null) => {
          const index = project.sorting?.classes.findIndex(item => item.id === id) ?? -1;
          return index < 0 ? "var(--muted)" : palette[index % palette.length];
        };
        const color = classColor(movement.line_class_id), rightColor = classColor(other.class_id);
        return <g key={row.alternative_id} data-company-id={row.alternative_id}>
          {labelY1 !== y1 && <line x1="264" y1={labelY1} x2="282" y2={y1} stroke="var(--border-strong)"/>}
          {labelY2 !== y2 && <line x1="618" y1={y2} x2="636" y2={labelY2} stroke="var(--border-strong)"/>}
          <path d={`M 286 ${String(y1)} L 614 ${String(y2)}`} stroke={color} strokeWidth={movement.emphasize ? 4 : 1.5} fill="none"
            role="button" tabIndex={0} aria-label={`Open ${row.name} screening detail under ${left.name}`}
            onClick={event => open(event, row.alternative_id, left.profile_id)} onKeyDown={event => open(event, row.alternative_id, left.profile_id)}/>
          <g role="button" tabIndex={0} aria-label={`Open ${row.name} screening detail under ${left.name}, rank ${String(row.rank)}`}
            onClick={event => open(event, row.alternative_id, left.profile_id)} onKeyDown={event => open(event, row.alternative_id, left.profile_id)}>
            <foreignObject x="20" y={labelY1 - 18} width="244" height="38"><div className="partner-company-label" title={row.name}>{row.rank}. {row.name}</div></foreignObject><circle cx="286" cy={y1} r="4" fill={color}/>
          </g>
          <g role="button" tabIndex={0} aria-label={`Open ${other.name} screening detail under ${right.name}, rank ${String(other.rank)}`}
            onClick={event => open(event, other.alternative_id, right.profile_id)} onKeyDown={event => open(event, other.alternative_id, right.profile_id)}>
            <circle cx="614" cy={y2} r="4" fill={rightColor}/><foreignObject x="636" y={labelY2 - 18} width="244" height="38"><div className="partner-company-label right" title={other.name}>{other.rank}. {other.name}</div></foreignObject>
          </g>
        </g>;
      })}
    </svg>
    {project.sorting && comparison.profiles.some(profile => profile.summary.rows.some(row => row.class_id !== null)) && <p className="muted small" aria-label="Profile class colours">Class colours: {project.sorting.classes.map((item, index) =>
      <span key={item.id} style={{ color: palette[index % palette.length] }}>{index ? "; " : ""}{item.name}</span>)}. Lines use the left class; endpoint dots use each profile's class.</p>}
    <div className="table-scroll" tabIndex={0}><table className="grid" aria-label="Profile rankings and movements">
      <thead><tr><th>Alternative</th><th>{left.name}: rank, value and class</th><th>{right.name}: rank, value and class</th><th>Places moved</th></tr></thead>
      <tbody>{left.summary.rows.map(row => {
        const other = rightRows.get(row.alternative_id), movement = movements.get(row.alternative_id);
        return <tr key={row.alternative_id} {...companyRow(exploration, row.alternative_id, left.profile_id)}>
          <th scope="row"><CompanyName id={row.alternative_id} profileId={left.profile_id}>{row.name}</CompanyName></th>
          <td>{row.rank} · {displayNumber(row.value)}{row.class_name ? ` · ${row.class_name}` : ""}</td>
          <td>{other ? <><CompanyName id={other.alternative_id} profileId={right.profile_id}>{String(other.rank)} · {displayNumber(other.value)}{other.class_name ? ` · ${other.class_name}` : ""}</CompanyName></> : "Unavailable"}</td>
          <td>{movement ? movement.places_changed === 0 ? "Unchanged" : `${movement.places_changed > 0 ? "+" : ""}${String(movement.places_changed)}` : "Unavailable"}</td>
        </tr>;
      })}</tbody>
    </table></div>
  </>;
}
