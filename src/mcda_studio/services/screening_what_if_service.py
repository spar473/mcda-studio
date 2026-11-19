"""Read-only top-level swing trials, evaluated by the existing engines."""

import math
from typing import Literal

from mcda_studio.domain.analysis_record import AnalysisRecord, SortingAnalysisRecord
from mcda_studio.domain.common import DomainModel, FiniteFloat, Id
from mcda_studio.domain.errors import McdaError, ModelStructureError
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.services import project_service, results_service
from mcda_studio.services.screening_summary_service import ScreeningSummary, screening_summary
from mcda_studio.services.sensitivity_eligibility import node_global_weight


class TrialControl(DomainModel):
    criterion_id: Id
    name: str
    raw_rating: FiniteFloat
    local_weight: FiniteFloat | None
    global_share: FiniteFloat | None
    slider_min: FiniteFloat = 0
    slider_max: FiniteFloat
    step: Literal["any"] = "any"


class ScreeningWhatIf(DomainModel):
    project_fingerprint: str
    configuration: AnalysisConfiguration
    weight_profile_id: Id | None = None
    scenario_id: Id | None = None
    status: Literal["available", "unavailable"] = "unavailable"
    reason: str = ""
    ratings: dict[Id, FiniteFloat]
    controls: list[TrialControl] = []
    trial_project_fingerprint: str | None = None
    summary: ScreeningSummary | None = None
    record: AnalysisRecord | SortingAnalysisRecord | None = None


def what_if_weights(
    project: Project,
    configuration: AnalysisConfiguration | None,
    ratings: dict[str, float],
) -> ScreeningWhatIf:
    for key, value in ratings.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            or value < 0
        ):
            raise ModelStructureError(f"Rating for {key!r} must be a finite nonnegative number.")
    cfg = (configuration or project.analysis).model_copy(deep=True)
    response = ScreeningWhatIf(
        project_fingerprint=project.fingerprint(), configuration=cfg, ratings=dict(ratings)
    )
    if cfg.method not in {"mavt", "mavt_sorting"}:
        response.reason = "Choose MAVT or value-based sorting to explore swing ratings."
        return response
    try:
        source = results_service.analysis_record(project, cfg)
    except McdaError as exc:
        response.reason = str(exc)
        return response
    except OverflowError:
        response.reason = "The source ratings exceed the engine's numerical range."
        return response
    assert isinstance(source, AnalysisRecord | SortingAnalysisRecord)
    response.weight_profile_id = source.result.weight_profile_id
    response.scenario_id = source.result.scenario_id
    profile = project.resolve_profile(cfg)
    if profile is None:
        if ratings:
            raise ModelStructureError("No stated raw swing ratings are available to vary.")
        response.reason = "No stated weight profile is available for this view."
        return response
    tree = project.tree()
    scored_roots = {
        tree.path(leaf)[0]
        for leaf in source.result.leaf_order
        if source.result.global_weights[leaf] > 0
    }
    roots = [
        node
        for node in tree.child_ids(None)
        if node in scored_roots
        and source.result.local_weights[node] > 0
        and node in profile.judgements
    ]
    if any(key not in roots for key in ratings):
        raise ModelStructureError(
            "Only stated, baseline-weighted top-level scored ratings can be varied."
        )
    if not roots:
        response.reason = "No stated, weighted top-level ratings are available for this view."
        return response
    trial = project.model_copy(deep=True)
    for node, value in ratings.items():
        trial = project_service.set_judgement(trial, node, value, profile.id)
    trial_profile = trial.resolve_profile(cfg)
    assert trial_profile is not None
    response.controls = [
        TrialControl(
            criterion_id=node,
            name=tree.node(node).name,
            raw_rating=trial_profile.judgements[node],
            local_weight=None,
            global_share=None,
            slider_max=max(100.0, profile.judgements[node], trial_profile.judgements[node]),
        )
        for node in roots
    ]
    try:
        record = source if not ratings else results_service.analysis_record(trial, cfg)
        assert isinstance(record, AnalysisRecord | SortingAnalysisRecord)
        summary = screening_summary(trial, cfg)
    except McdaError as exc:
        response.reason = str(exc)
        return response
    except OverflowError:
        response.reason = "The trial ratings exceed the engine's numerical range."
        return response
    if summary.status != "available":
        response.reason = summary.reason
        return response
    response.status = "available"
    response.trial_project_fingerprint = trial.fingerprint()
    response.summary = summary
    response.record = record
    for control in response.controls:
        control.local_weight = record.result.local_weights[control.criterion_id]
        control.global_share = node_global_weight(
            tree, record.result.local_weights, control.criterion_id
        )
    return response
