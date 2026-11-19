import { useEffect, useState } from "react";
import type { ScreeningWhatIf } from "../api/types";
import type { AnalysisRequest } from "../state/useAnalysisRequest";
import type { WeightTrial } from "../state/useWeightTrial";
import { InfoDisclosure } from "./InfoDisclosure";
import { MessageText } from "./IssueText";
import { CommitNumber } from "./ui";
import { displayCompact, displayPercent } from "./results/numberDisplay";

export function WhatIfWeights({ trial, request, supported, onExplore }: {
  trial: WeightTrial; request: AnalysisRequest<ScreeningWhatIf>; supported: boolean; onExplore?: () => void;
}) {
  const ready = request.status === "ready" ? request.result : null;
  const { active, baseline, acceptBaseline } = trial;
  useEffect(() => {
    if (ready && !active && !baseline) acceptBaseline(ready.controls);
  }, [ready, active, baseline, acceptBaseline]);
  return <details className="what-if-weights" open={trial.open} onToggle={event => {
    if (event.currentTarget.open !== trial.open) trial.setOpen(event.currentTarget.open);
  }}>
    <summary>What-if weights</summary>
    {!supported ? <><p>Use MAVT swing ratings to explore a temporary screening.</p><button type="button" onClick={onExplore}>Explore MAVT weights</button></>
      : <>
        <p>{trial.active ? "What-if, not saved" : "Saved raw swing ratings"} <button type="button" disabled={!trial.active} onClick={() => trial.reset()}>Reset</button></p>
        <p className="muted small">Only the screening summary and ranking chart follow this trial.</p>
        {trial.baseline && <RawControls key={`${trial.sourceKey}:${String(trial.generation)}`} trial={trial} ready={ready} pending={request.status === "loading"}/>}
        {request.status === "loading" && trial.open && <p role="status">Calculating what-if screening…</p>}
        {request.status === "error" && <><p role="alert"><MessageText message={request.message}/></p><button type="button" onClick={request.retry}>Retry what-if screening</button></>}
        {ready?.status === "unavailable" && <p role="status"><MessageText message={ready.reason}/></p>}
        <InfoDisclosure label="What-if interpretation">This changes only the temporary raw ratings sent to the engine. No project, saved profile, source measurement, evidence dossier or review is changed. Normalised weights and results come from Python. Raw ratings are nonnegative and uncapped; 100 is a convention, not a validation maximum. Reset restores the saved reading.</InfoDisclosure>
      </>}
  </details>;
}
function RawControls({ trial, ready, pending }: { trial: WeightTrial; ready: ScreeningWhatIf | null; pending: boolean }) {
  const [invalid, setInvalid] = useState<string | null>(null);
  return <div className="what-if-controls">{trial.baseline?.map(control => {
    const rating = trial.ratings[control.criterion_id] ?? control.raw_rating;
    const evaluated = ready?.controls.find(item => item.criterion_id === control.criterion_id);
    return <section key={control.criterion_id} aria-label={`${control.name} trial weight`}>
      <label>{control.name}: raw rating {displayCompact(rating)}
        <input type="range" aria-label={`What-if ${control.name}`} aria-valuetext={`${displayCompact(rating)} raw rating`} min={control.slider_min}
          max={Math.max(control.slider_max, rating)} step={control.step} value={rating}
          onChange={event => trial.change(control.criterion_id, Number(event.currentTarget.value))}/>
      </label>
      <p className="muted small">Engine normalised weight: {pending ? "Calculating…" : evaluated?.local_weight == null ? "Unavailable" : displayPercent(evaluated.local_weight)}</p>
      <details><summary>Enter an exact raw rating for {control.name}</summary>
        <CommitNumber label={`Exact raw rating for ${control.name}`} value={rating} invalid={invalid === control.criterion_id} onCommit={value => {
          if (value === null || value < 0) { setInvalid(control.criterion_id); return; }
          setInvalid(null); trial.change(control.criterion_id, value);
        }}/>
        {invalid === control.criterion_id && <p role="alert">Enter a finite nonnegative rating.</p>}
      </details>
    </section>;
  })}</div>;
}
