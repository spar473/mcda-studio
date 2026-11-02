"""Replayable disclosure reviews; no proxy activation or project edits by implication."""

from mcda_studio.domain.errors import ModelEditError, StaleRevisionError
from mcda_studio.domain.evidence import Review
from mcda_studio.domain.proxy_criterion import (
    ProxyCardFact,
    ProxyCriterionPlan,
    ProxyFeature,
    ProxyOperation,
    ProxyOverlap,
    ProxyPlanState,
    ProxyRevision,
)
from mcda_studio.services.derived_service import _digest

CARD_FIELDS = (
    "purpose",
    "training_period",
    "training_population",
    "observation_cutoff",
    "label_definition",
    "base_rate",
    "population_denominator",
    "selection_bias",
    "survivorship_bias",
    "calibration_evidence",
    "calibration_population",
    "calibration_period",
    "licence",
    "use_restrictions",
    "model_version",
    "source_references",
)


def digest(plan: ProxyCriterionPlan) -> str:
    return _digest(plan.model_dump(mode="json", exclude={"digest"}))


def _review(review: Review) -> None:
    if not review.reviewer.strip() or not review.note.strip() or review.status == "corrected":
        raise ModelEditError("PROXY_REVIEW: name the reviewer and reason; edit facts separately")


def _unreviewed(state: ProxyPlanState) -> ProxyPlanState:
    result = state.model_copy(deep=True)
    result.enabled = False
    result.plan_review = None
    result.licence_review = None
    result.score_workspace_digest = None
    for fact in result.card_facts.values():
        fact.review = None
    for feature in result.features:
        feature.review = None
    for overlap in result.overlaps:
        overlap.review = None
    return result


def start(state: ProxyPlanState) -> ProxyCriterionPlan:
    if state != _unreviewed(state):
        raise ModelEditError("PROXY_INITIAL: a new plan starts disabled with no carried reviews")
    plan = ProxyCriterionPlan(initial=state.model_copy(deep=True), digest="")
    plan.digest = digest(plan)
    return plan


def _apply(state: ProxyPlanState, operation: ProxyOperation) -> ProxyPlanState:
    _review(operation.review)
    result = state.model_copy(deep=True)
    kind = operation.kind
    if kind == "edit":
        if (
            operation.state is None
            or operation.state.project_fingerprint != state.project_fingerprint
        ):
            raise ModelEditError("PROXY_EDIT: retain the original baseline binding")
        result = _unreviewed(operation.state)
    elif kind in {"review_card_fact", "review_feature", "review_overlap"}:
        item: ProxyCardFact | ProxyFeature | ProxyOverlap | None
        if kind == "review_card_fact":
            item = result.card_facts.get(operation.id or "")
        elif kind == "review_feature":
            item = next((f for f in result.features if f.id == operation.id), None)
        else:
            item = next((o for o in result.overlaps if o.feature_id == operation.id), None)
        if item is None:
            raise ModelEditError("PROXY_REVIEW_ID: review an existing declared fact or feature")
        item.review = operation.review.model_copy(deep=True)
        result.enabled = False
        result.plan_review = None
    elif kind == "review_licence":
        if operation.licence_compatible is None:
            raise ModelEditError("PROXY_LICENCE: state compatibility explicitly")
        result.licence_compatible = operation.licence_compatible
        result.licence_review = operation.review.model_copy(deep=True)
        result.enabled = False
        result.plan_review = None
    elif kind == "bind_scores":
        if operation.workspace_digest is None:
            raise ModelEditError("PROXY_SCORES: bind the reviewed proposal workspace")
        result.score_workspace_digest = operation.workspace_digest
        result.enabled = False
        result.plan_review = None
    elif kind == "review_plan":
        result.plan_review = operation.review.model_copy(deep=True)
        result.enabled = False
    elif kind == "set_enabled":
        if operation.enabled is None or operation.review.status != "accepted":
            raise ModelEditError("PROXY_CHOICE: record an explicit accepted activation choice")
        result.enabled = operation.enabled
    return result


def current(plan: ProxyCriterionPlan) -> ProxyPlanState:
    chain = start(plan.initial)
    state = plan.initial.model_copy(deep=True)
    for revision in plan.revisions:
        if revision.previous_digest != chain.digest:
            raise ModelEditError("PROXY_HISTORY: review chain does not reproduce")
        state = _apply(state, revision.operation)
        chain.revisions.append(revision.model_copy(deep=True))
        chain.digest = digest(chain)
    if chain.digest != plan.digest:
        raise ModelEditError("PROXY_DIGEST: plan contents changed")
    return state


def revise(
    plan: ProxyCriterionPlan, operation: ProxyOperation, expected_digest: str
) -> ProxyCriterionPlan:
    state = current(plan)
    if expected_digest != plan.digest:
        raise StaleRevisionError("Proxy plan changed; inspect it before another review")
    _apply(state, operation)
    result = plan.model_copy(deep=True)
    result.revisions.append(
        ProxyRevision(previous_digest=plan.digest, operation=operation.model_copy(deep=True))
    )
    result.digest = digest(result)
    # Assignment does not re-check list length; validate the sealed document before returning.
    return ProxyCriterionPlan.model_validate_json(result.model_dump_json())
