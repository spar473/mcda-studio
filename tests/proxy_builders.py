"""Invented local disclosure inputs. All ratings are explicit analyst judgements."""

from datetime import UTC, date, datetime

from mcda_studio.domain.alternatives import Alternative
from mcda_studio.domain.criteria import CriterionNode, LinearValueFunction
from mcda_studio.domain.derived import DerivedFormula, DerivedModel, SourceFactor
from mcda_studio.domain.evidence import Origin, Review, Source
from mcda_studio.domain.external_proposals import (
    ExternalProposal,
    LocalModelCard,
    NumericProposal,
    ProposalIntake,
    ProposalReview,
    ProposalReviewDetails,
    ProposalSubject,
)
from mcda_studio.domain.factor_uncertainty import FactorDistribution, FactorUncertaintyModel
from mcda_studio.domain.measurements import Performance
from mcda_studio.domain.preferences import AnalysisConfiguration, WeightProfile
from mcda_studio.domain.project import Project
from mcda_studio.domain.proxy_criterion import (
    ProxyAcknowledgements,
    ProxyCardFact,
    ProxyFeature,
    ProxyOperation,
    ProxyOverlap,
    ProxyPlanState,
)
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.domain.sorting import SortingClass, SortingModel
from mcda_studio.domain.uncertainty import DiscreteDistribution
from mcda_studio.services import derived_service as derived
from mcda_studio.services import proposal_service as proposals
from mcda_studio.services import proxy_criterion_service as proxy
from mcda_studio.services import proxy_plan_service as plans

TIME = datetime(2026, 11, 1, tzinfo=UTC)
REVIEW = Review(
    status="accepted",
    reviewer="Local reviewer",
    reviewed_at=TIME,
    note="Illustrative review of stated inputs and disclosed limitations",
)
SOURCE = Source(
    name="Invented evidence",
    reference="local:illustrative",
    date=date(2026, 10, 1),
    description="Invented data for a generic verification fixture",
    classification="self_reported",
)
ORIGIN = Origin(kind="human", proposed_by="Local analyst")


def leaf(id: str, name: str) -> CriterionNode:
    return CriterionNode(
        id=id,
        name=name,
        scale=Scale(type=ScaleType.INTERVAL, lower=0, upper=1),
        value_function=LinearValueFunction(),
    )


def inputs(
    *,
    unknown: bool = False,
    enabled: bool = True,
    project_change=None,
    state_change=None,
    tool_version="1",
) -> proxy.ProxyInputs:
    project = Project(
        id="proxy_fixture",
        title="Illustrative optional proxy",
        alternatives=[Alternative(id="a", name="Option A"), Alternative(id="b", name="Option B")],
        criteria=[leaf("quality", "Quality"), leaf("capacity", "Capacity")],
        performances=[
            Performance(alternative_id=a, criterion_id=c, value=v)
            for a, c, v in [
                ("a", "quality", 0.75),
                ("a", "capacity", 0.25),
                ("b", "quality", 0.25),
                ("b", "capacity", 0.75),
            ]
        ],
        weight_profiles=[
            WeightProfile(
                id="balanced", name="Balanced", judgements={"quality": 1.0, "capacity": 1.0}
            ),
            WeightProfile(
                id="quality_led", name="Quality led", judgements={"quality": 3.0, "capacity": 1.0}
            ),
        ],
        sorting=SortingModel(
            classes=[
                SortingClass(id="high", name="High", lower_boundary=0.5),
                SortingClass(id="low", name="Low"),
            ]
        ),
    )
    if project_change:
        project_change(project)
    card = LocalModelCard(
        purpose="Illustrative fixed proxy",
        limitations="Invented fixture; no predictive claim",
        model_version="1",
        details={
            name: "Illustrative declared " + name
            for name in plans.CARD_FIELDS
            if name not in {"purpose", "model_version"}
        },
    )
    card.details["observation_cutoff"] = "2026-10-31"
    if unknown:
        card.details["calibration_evidence"] = "unknown"
    state = ProxyPlanState(
        project_fingerprint=project.fingerprint(),
        criterion=leaf("disclosed_proxy_score", "Disclosed model proxy: fixed score"),
        score_meaning="Illustrative external score; no probability meaning",
        compared_profile_ids=["balanced", "quality_led"],
        swing_ratings={"balanced": 2.0, "quality_led": 4.0},
        card_id="card",
        card_digest=derived._digest(card.model_dump(mode="json")),
        card_facts={
            name: ProxyCardFact(
                value=getattr(card, name, card.details.get(name)),
                unknown=unknown and name == "calibration_evidence",
                reason="No study supplied" if unknown and name == "calibration_evidence" else "",
                source_ids=["source"],
            )
            for name in plans.CARD_FIELDS
        },
        features=[
            ProxyFeature(
                id="reported_quality",
                description="A declared quality input",
                source_ids=["source"],
                observed_at=date(2026, 10, 1),
                criterion_ids=["quality"],
            )
        ],
        overlaps=[
            ProxyOverlap(
                feature_id="reported_quality",
                relation="same_concept",
                resolution="retain_with_rationale",
                rationale="Retain both explicitly to demonstrate the weight consequence",
            )
        ],
    )
    if state_change:
        state_change(state)
    plan = plans.start(state)
    draft = proxy.inspect(proxy.ProxyInputs(project=project, plan=plan)).score_draft
    assert draft is not None
    intake = ProposalIntake(
        project_fingerprint=draft.fingerprint(),
        sources={"source": SOURCE},
        model_cards={"card": card},
        proposals=[
            ExternalProposal(
                id="score_" + a,
                subject=ProposalSubject(alternative_id=a, criterion_id=state.criterion.id),
                payload=NumericProposal(value=v, unit=None),
                tool_id="Local model",
                tool_version=tool_version,
                model_card_id="card",
                model_card_digest=state.card_digest,
                run_at=TIME,
                source_ids=["source"],
            )
            for a, v in [("a", 0.25), ("b", 0.75)]
        ],
    )
    workspace = proposals.start(draft, intake)
    events = [
        ProposalReview(
            proposal_id=p.id,
            review=ProposalReviewDetails(
                status="accepted",
                reviewer=REVIEW.reviewer,
                reviewed_at=TIME,
                note=REVIEW.note,
                primary_source_id="source",
            ),
        )
        for p in intake.proposals
    ]
    workspace = proposals.review(
        draft,
        workspace,
        events,
        proposals.inspect(draft, workspace).review_digest,
        workspace.digest,
        bulk=True,
    ).workspace
    operations = [
        ProxyOperation(kind="review_card_fact", id=name, review=REVIEW)
        for name in plans.CARD_FIELDS
    ]
    operations += [
        ProxyOperation(kind="review_feature", id="reported_quality", review=REVIEW),
        ProxyOperation(kind="review_overlap", id="reported_quality", review=REVIEW),
        ProxyOperation(kind="review_licence", licence_compatible=True, review=REVIEW),
        ProxyOperation(kind="bind_scores", workspace_digest=workspace.digest, review=REVIEW),
        ProxyOperation(kind="review_plan", review=REVIEW),
    ]
    if enabled:
        operations.append(ProxyOperation(kind="set_enabled", enabled=True, review=REVIEW))
    for operation in operations:
        plan = plans.revise(plan, operation, plan.digest)
    return proxy.ProxyInputs(
        project=project,
        plan=plan,
        scores=workspace,
        configuration=AnalysisConfiguration(method="mavt"),
    )


def request(
    value: proxy.ProxyInputs, *, acknowledge_unknown: bool = False
) -> proxy.ProxyPairRequest:
    return proxy.ProxyPairRequest(
        **value.model_dump(),
        expected_review_digest=proxy.inspect(value).review_digest,
        acknowledgements=ProxyAcknowledgements(
            card=True, overlap=True, weight_changes=True, unknown_facts=acknowledge_unknown
        ),
        review=REVIEW,
    )


def with_factors(value: proxy.ProxyInputs) -> proxy.ProxyInputs:
    result = value.model_copy(deep=True)
    result.configuration.method = "mavt_sorting"
    model = DerivedModel(
        project_fingerprint=value.project.fingerprint(),
        sources=[
            SourceFactor(
                id="quality_a", value=0.75, unit="1", source=SOURCE, origin=ORIGIN, review=REVIEW
            )
        ],
        formulas=[
            DerivedFormula(
                id="quality_measure",
                expression="quality_a",
                unit="1",
                origin=ORIGIN,
                review=REVIEW,
                alternative_id="a",
                criterion_id="quality",
            )
        ],
    )
    result.model = model
    result.uncertainty = FactorUncertaintyModel(
        project_fingerprint=value.project.fingerprint(),
        model_digest=derived.preview(value.project, model).model_digest,
        distributions=[
            FactorDistribution(
                factor_id="quality_a",
                distribution=DiscreteDistribution(values=[0.25, 0.75], probabilities=[0.5, 0.5]),
                origin=ORIGIN,
                review=REVIEW,
            )
        ],
    )
    result.factor_parameters = proxy.factors.FactorRunParameters(
        draws=64, seed=47, configuration=result.configuration
    )
    return result
