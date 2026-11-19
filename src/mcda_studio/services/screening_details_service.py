"""Stateless exploration detail assembled from existing engines; no stored schema."""

from typing import Literal

from mcda_studio.domain.common import DomainModel, Id
from mcda_studio.domain.errors import ModelStructureError
from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.feasibility import AlternativeFeasibility
from mcda_studio.domain.measurements import Measurement
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import MavtResult
from mcda_studio.methods.mavt.aggregation import prepare_mavt
from mcda_studio.services import analysis_service, evidence_service, feasibility_service
from mcda_studio.services.questions_service import Question, open_questions
from mcda_studio.services.screening_summary_service import Driver, SummaryRow, screening_summary
from mcda_studio.services.sensitivity_eligibility import eligible_nodes, node_global_weight


class SensitivityCriterion(DomainModel):
    criterion_id: Id
    name: str
    parent_id: Id | None
    global_weight: float
    local_weight: float
    eligible: bool
    unweighted: bool


class ExplorationSensitivity(DomainModel):
    suggested_criterion_id: Id | None
    criteria: list[SensitivityCriterion]


class HeaderFact(DomainModel):
    criterion_id: Id
    label: str
    measurement: Measurement | None


class Rating(DomainModel):
    criterion_id: Id
    name: str
    measurement: Measurement | None
    rubric_text: str
    claim_ids: list[Id]


class AlternativeScreeningDetail(DomainModel):
    row: SummaryRow
    header_facts: list[HeaderFact]
    requirements: AlternativeFeasibility | None
    contributions: list[Driver]
    ratings: list[Rating]
    questions: list[Question]


class ScreeningDetails(DomainModel):
    project_fingerprint: str
    configuration: AnalysisConfiguration
    weight_profile_id: Id | None
    scenario_id: Id | None
    status: Literal["available", "unavailable"]
    reason: str = ""
    sensitivity: ExplorationSensitivity | None = None
    alternative: AlternativeScreeningDetail | None = None


def screening_details(
    project: Project,
    configuration: AnalysisConfiguration | None = None,
    dossier: EvidenceDossier | None = None,
    alternative_id: str | None = None,
) -> ScreeningDetails:
    if alternative_id is not None and alternative_id not in project.alternative_ids():
        raise ModelStructureError(f"Unknown alternative: {alternative_id}")
    summary = screening_summary(project, configuration, dossier)
    response = ScreeningDetails(
        project_fingerprint=summary.project_fingerprint,
        configuration=summary.configuration,
        weight_profile_id=summary.weight_profile_id,
        scenario_id=summary.scenario_id,
        status=summary.status,
        reason=summary.reason,
    )
    if summary.status != "available":
        return response
    cfg = summary.configuration.model_copy(update={"method": "mavt", "parameters": {}})
    prep = prepare_mavt(project, cfg)
    tree = prep.tree
    eligible, _excluded = eligible_nodes(tree, prep.local)
    weights = {n: node_global_weight(tree, prep.local, n) for n in tree.all_ids()}
    candidates = sorted(eligible, key=lambda n: -weights[n])  # stable tree-order ties
    objectives = [n for n in candidates if tree.child_ids(n)]
    fragility = summary.rows[0].fragility if summary.rows else None
    preferred = fragility.criterion_id if fragility else None
    suggested = preferred if preferred in eligible else next(iter(objectives or candidates), None)
    response.sensitivity = ExplorationSensitivity(
        suggested_criterion_id=suggested,
        criteria=[
            SensitivityCriterion(
                criterion_id=n,
                name=tree.node(n).name,
                parent_id=tree.node(n).parent_id,
                global_weight=weights[n],
                local_weight=prep.local[n],
                eligible=n in eligible,
                unweighted=weights[n] == 0,
            )
            for n in tree.all_ids()
        ],
    )
    if alternative_id is None:
        return response
    result = analysis_service.evaluate_project(project, cfg)
    assert isinstance(result, MavtResult)
    detail = next(a for a in result.alternatives if a.alternative_id == alternative_id)
    scored = [n for n in result.leaf_order if result.global_weights[n] > 0]
    contributions = [
        Driver(
            criterion_id=n, name=tree.node(n).name, contribution=detail.weighted_contributions[n]
        )
        for n in sorted(scored, key=lambda n: -detail.weighted_contributions[n])
    ]
    checked = feasibility_service.check_feasibility(project) if project.requirements else None
    # A dossier is usable only under its original binding and reference checks.
    verified = (
        dossier
        if dossier
        and not any(
            issue.severity.value == "error"
            for issue in evidence_service.preview(project, dossier).issues
        )
        else None
    )
    claims = verified.claims if verified else []
    raw = project.performance_index()
    facts = list(dict.fromkeys(r.criterion_id for r in project.requirements or []))
    response.alternative = AlternativeScreeningDetail(
        row=next(r for r in summary.rows if r.alternative_id == alternative_id),
        header_facts=[
            HeaderFact(
                criterion_id=n, label=tree.node(n).name, measurement=raw.get((alternative_id, n))
            )
            for n in facts
        ],
        requirements=next(
            (a for a in checked.alternatives if a.alternative_id == alternative_id), None
        )
        if checked
        else None,
        contributions=contributions,
        ratings=[
            Rating(
                criterion_id=n,
                name=tree.node(n).name,
                measurement=raw.get((alternative_id, n)),
                rubric_text=(
                    str(raw[(alternative_id, n)])
                    if isinstance(raw.get((alternative_id, n)), str)
                    else tree.node(n).description
                ),
                claim_ids=[
                    c.id
                    for c in claims
                    if c.alternative_id == alternative_id and c.criterion_id == n
                ],
            )
            for n in scored
        ],
        questions=[
            q
            for q in open_questions(project, summary.configuration, dossier).questions
            if q.alternative_id == alternative_id
        ],
    )
    return response
