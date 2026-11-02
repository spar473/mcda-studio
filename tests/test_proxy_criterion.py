"""Exact baseline preservation, explicit disclosure gates and complete paired replay."""

import json

import pytest
from pydantic import ValidationError

from mcda_studio.domain.errors import ModelEditError, StaleRevisionError
from mcda_studio.domain.external_proposals import ProposalConfidence
from mcda_studio.domain.proxy_criterion import ProxyCriterionPlan, ProxyOperation
from mcda_studio.services import analysis_service, factor_analysis_service
from mcda_studio.services import proxy_criterion_service as proxy
from mcda_studio.services import proxy_plan_service as plans
from proxy_builders import REVIEW, inputs, request, with_factors


def edit(value, change):
    result = value.model_copy(deep=True)
    state = plans.current(result.plan)
    change(state)
    result.plan = plans.revise(
        result.plan, ProxyOperation(kind="edit", state=state, review=REVIEW), result.plan.digest
    )
    return result


def test_proxy_is_off_by_default_and_initial_reviews_cannot_be_smuggled():
    value = inputs(enabled=False)
    before = value.project.model_dump_json()
    with pytest.raises(ModelEditError, match="PROXY_DISABLED"):
        proxy.run_pair(request(value))
    assert value.project.model_dump_json() == before
    state = plans.current(value.plan)
    with pytest.raises(ModelEditError, match="PROXY_INITIAL"):
        plans.start(state)


def test_complete_pair_preserves_baseline_and_roundtrips_every_detail():
    value = inputs()
    before = value.project.model_dump_json()
    bundle = proxy.run_pair(request(value))
    assert bundle.status == "completed"
    assert bundle.without_proxy.project.model_dump_json() == before
    assert (
        bundle.without_proxy.result.model_dump_json()
        == analysis_service.evaluate_project(value.project, value.configuration).model_dump_json()
    )
    assert bundle.with_proxy.result.project_fingerprint != value.project.fingerprint()
    assert len(bundle.with_proxy.result.leaf_order) == 3
    assert len(bundle.inspection.calculation.preview.calculations) == 2
    assert (
        proxy.verify(json.loads(bundle.model_dump_json())).model_dump_json()
        == bundle.model_dump_json()
    )
    assert value.project.model_dump_json() == before
    assert bundle.inspection.weight_shares["balanced"]["before"] == {
        "quality": 0.5,
        "capacity": 0.5,
    }
    assert bundle.inspection.weight_shares["balanced"]["after"] == {
        "quality": 0.25,
        "capacity": 0.25,
        "disclosed_proxy_score": 0.5,
    }


def test_all_non_proxy_factor_draws_and_original_record_are_bit_exact():
    value = with_factors(inputs())
    bundle = proxy.run_pair(request(value))
    ordinary = factor_analysis_service.run(
        value.project, value.model, value.uncertainty, value.factor_parameters
    )
    assert bundle.without_proxy.factor_run.model_dump_json() == ordinary.model_dump_json()
    assert bundle.without_proxy.coupling_draws == 64
    assert bundle.without_proxy.coupling_digest == bundle.with_proxy.coupling_digest
    assert len(bundle.without_proxy.factor_run.result.trace) == 16
    for left, right in zip(
        bundle.without_proxy.factor_run.result.trace,
        bundle.with_proxy.factor_run.result.trace,
        strict=True,
    ):
        assert left.factors["quality_a"] == right.factors["quality_a"]
        assert right.factors["proxy_score_0"] == 0.25
        assert right.factors["proxy_score_1"] == 0.75
    assert proxy.verify(bundle.model_dump(mode="json")) == bundle


@pytest.mark.parametrize("method", ["promethee2", "ahp"])
def test_unsupported_methods_retain_both_unavailable_halves(method):
    value = inputs()
    value.configuration.method = method
    result = proxy.run_pair(request(value))
    assert result.status == "unavailable"
    assert result.without_proxy.status == result.with_proxy.status == "unavailable"
    assert "UNAVAILABLE" in result.with_proxy.reason
    assert result.without_proxy.project.model_dump_json() == value.project.model_dump_json()
    assert result.with_proxy.project != value.project


def test_failed_half_makes_pair_unavailable_and_retains_both_reasons_and_projects():
    from mcda_studio.domain.criteria import ControlPoint, PiecewiseLinearValueFunction

    def restrict(state):
        state.criterion.value_function = PiecewiseLinearValueFunction(
            points=[ControlPoint(x=0, value=0), ControlPoint(x=0.5, value=1)]
        )

    value = inputs(state_change=restrict)
    bundle = proxy.run_pair(request(value))
    assert bundle.status == "unavailable"
    assert bundle.without_proxy.status == "completed"
    assert bundle.without_proxy.result is not None
    assert bundle.with_proxy.status == "unavailable"
    assert bundle.with_proxy.result is None
    assert bundle.with_proxy.reason
    assert bundle.without_proxy.project.model_dump_json() == value.project.model_dump_json()
    assert proxy.verify(bundle.model_dump(mode="json")) == bundle


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.card_facts.pop("training_population"),
        lambda s: setattr(s.card_facts["licence"], "unknown", True),
        lambda s: setattr(s, "licence_compatible", False),
        lambda s: s.features.clear(),
        lambda s: s.overlaps.clear(),
        lambda s: setattr(s.overlaps[0], "resolution", "baseline_only"),
        lambda s: s.swing_ratings.pop("quality_led"),
        lambda s: s.swing_ratings.__setitem__("balanced", None),
        lambda s: setattr(s.criterion, "name", "Ordinary score"),
        lambda s: setattr(s.criterion, "id", "hidden_score"),
    ],
)
def test_edits_clear_reviews_disable_and_block_activation(change):
    value = edit(inputs(), change)
    state = plans.current(value.plan)
    assert not state.enabled and state.plan_review is None
    assert state.score_workspace_digest is None
    assert proxy.inspect(value).issues
    with pytest.raises(ModelEditError, match="PROXY_DISABLED"):
        proxy.run_pair(request(value))


def test_unknown_fact_requires_acknowledgement_and_is_preserved_as_limitation():
    value = inputs(unknown=True)
    with pytest.raises(ModelEditError, match="PROXY_ACKNOWLEDGEMENTS"):
        proxy.run_pair(request(value))
    bundle = proxy.run_pair(request(value, acknowledge_unknown=True))
    assert bundle.inspection.unknown_facts == ["calibration_evidence"]
    assert any("calibration_evidence" in item for item in bundle.limitations)


@pytest.mark.parametrize("ack", ["card", "overlap", "weight_changes"])
def test_each_acknowledgement_is_required(ack):
    value = request(inputs())
    setattr(value.acknowledgements, ack, False)
    with pytest.raises(ModelEditError, match="ACKNOWLEDGEMENTS"):
        proxy.run_pair(value)


def test_confidence_metadata_never_changes_projects_weights_or_results():
    value = inputs()
    original = proxy.run_pair(request(value))
    value.scores.intake.proposals[0].confidence = ProposalConfidence(
        value=0.99, scale="unit_interval", meaning="Arbitrary supplier metadata"
    )
    value.scores.digest = proxy.proposals.workspace_digest(value.scores)
    for operation in [
        ProxyOperation(kind="bind_scores", workspace_digest=value.scores.digest, review=REVIEW),
        ProxyOperation(kind="review_plan", review=REVIEW),
        ProxyOperation(kind="set_enabled", enabled=True, review=REVIEW),
    ]:
        value.plan = plans.revise(value.plan, operation, value.plan.digest)
    revised = proxy.run_pair(request(value))
    for name in ["without_proxy", "with_proxy"]:
        assert (
            getattr(revised, name).project.model_dump_json()
            == getattr(original, name).project.model_dump_json()
        )
        assert (
            getattr(revised, name).result.model_dump_json()
            == getattr(original, name).result.model_dump_json()
        )
    assert revised.digest != original.digest


def test_history_tampering_stale_preview_and_changed_score_are_refused():
    value = inputs()
    old = request(value)
    value.plan.revisions[0].operation.review.note = "Unrecorded change"
    with pytest.raises(ModelEditError, match="PROXY_HISTORY"):
        proxy.inspect(value)
    old.expected_review_digest = "0" * 64
    with pytest.raises(StaleRevisionError):
        proxy.run_pair(old)
    value = inputs()
    value.scores.intake.proposals[0].payload.value = 0.5
    assert any("digest" in i.message.lower() for i in proxy.inspect(value).issues)
    with pytest.raises(ModelEditError, match="PROXY_BLOCKED"):
        proxy.run_pair(request(value))
    with pytest.raises(ValidationError):
        ProxyCriterionPlan.model_validate_json(
            inputs().plan.model_dump_json().replace('"version":1', '"version":2', 1)
        )


def test_export_cannot_drop_baseline_or_change_complete_pair():
    bundle = proxy.run_pair(request(inputs()))
    document = bundle.model_dump(mode="json")
    document.pop("without_proxy")
    with pytest.raises(ValidationError):
        proxy.verify(document)
    document = bundle.model_dump(mode="json")
    document["with_proxy"]["result"]["ranking"][0]["value"] += 0.01
    with pytest.raises(ModelEditError, match="PROXY_BUNDLE_DIGEST"):
        proxy.verify(document)


def test_reviewed_baseline_only_overlap_still_blocks_activation():
    value = inputs(state_change=lambda s: setattr(s.overlaps[0], "resolution", "baseline_only"))
    assert plans.current(value.plan).enabled
    assert any(i.code == "PROXY_BASELINE_ONLY" for i in proxy.inspect(value).issues)
    with pytest.raises(ModelEditError, match="PROXY_BLOCKED"):
        proxy.run_pair(request(value))


def test_explicit_zero_rating_is_retained_without_silently_removing_the_proxy():
    value = inputs(state_change=lambda s: s.swing_ratings.__setitem__("balanced", 0.0))
    bundle = proxy.run_pair(request(value))
    assert bundle.with_proxy.result.global_weights["disclosed_proxy_score"] == 0.0
    assert "disclosed_proxy_score" in bundle.with_proxy.result.leaf_order
    assert bundle.with_proxy.project.weight_profiles[0].judgements["disclosed_proxy_score"] == 0.0
    assert {r.alternative_id: r.value for r in bundle.without_proxy.result.ranking} == {
        r.alternative_id: r.value for r in bundle.with_proxy.result.ranking
    }


def test_explicit_removal_preserves_additional_model_and_baseline():
    def remove(s):
        s.overlaps[0].resolution = "remove_criterion"
        s.overlaps[0].remove_criterion_ids = ["quality"]

    value = inputs(state_change=remove)
    bundle = proxy.run_pair(request(value))
    assert bundle.inspection.overlap_removed is not None
    assert bundle.inspection.overlap_removed.tree().leaves() == ["capacity"]
    assert bundle.with_proxy.project.tree().leaves() == ["capacity", "disclosed_proxy_score"]
    assert bundle.without_proxy.project.tree().leaves() == ["quality", "capacity"]
    assert proxy.verify(bundle.model_dump(mode="json")) == bundle


def test_removal_cannot_erase_a_feasibility_requirement():
    from mcda_studio.domain.requirements import BoundRequirement

    value = inputs()
    value.project.requirements = [
        BoundRequirement(
            id="minimum", name="Required quality", criterion_id="quality", minimum=0.5, unit=None
        )
    ]
    state = plans.current(value.plan)
    state.overlaps[0].resolution = "remove_criterion"
    state.overlaps[0].remove_criterion_ids = ["quality"]
    with pytest.raises(ModelEditError, match="every feasibility requirement"):
        proxy._draft(value.project, state)


def test_missing_non_proxy_measurement_remains_missing_in_both_copies():
    value = inputs(project_change=lambda p: p.performances.pop())
    bundle = proxy.run_pair(request(value))
    assert bundle.status == "unavailable"
    assert bundle.without_proxy.status == bundle.with_proxy.status == "unavailable"
    assert bundle.without_proxy.result is bundle.with_proxy.result is None
    assert "capacity" in bundle.without_proxy.reason
    assert "capacity" in bundle.with_proxy.reason
    for half in [bundle.without_proxy, bundle.with_proxy]:
        assert ("b", "capacity") not in half.project.performance_index()


def test_changed_or_missing_card_score_and_licence_never_activate():
    for field in ["purpose", "training_period", "model_version", "licence"]:
        value = inputs()
        state = plans.current(value.plan)
        state.card_facts.pop(field)
        # Inspect each guard directly with reviewed state to avoid merely testing edit invalidation.
        intake = proxy.proposals.resolved_intake(value.scores)
        issues, _, _ = proxy._disclosures(
            value, state, intake.model_cards["card"], set(intake.sources)
        )
        assert any(i.code == "PROXY_CARD_FACT" and field in i.message for i in issues)
    value = inputs()
    value.scores.intake.model_cards.clear()
    value.scores.digest = proxy.proposals.workspace_digest(value.scores)
    assert proxy.inspect(value).issues


def test_stale_review_operation_and_unknown_observation_date_are_refused():
    value = inputs()
    with pytest.raises(StaleRevisionError):
        plans.revise(
            value.plan, ProxyOperation(kind="set_enabled", enabled=True, review=REVIEW), "0" * 64
        )
    from mcda_studio.domain.proxy_criterion import ProxyFeature

    with pytest.raises(ValidationError):
        ProxyFeature(id="x", description="Example", source_ids=["source"], observed_at=123)


def test_unknown_licence_and_incompatible_restrictions_remain_blockers_after_review():
    value = inputs()
    state = plans.current(value.plan)
    for field in ["licence", "use_restrictions"]:
        copy = state.model_copy(deep=True)
        copy.card_facts[field].unknown = True
        copy.card_facts[field].reason = "No permission supplied"
        intake = proxy.proposals.resolved_intake(value.scores)
        issues, _, _ = proxy._disclosures(
            value, copy, intake.model_cards["card"], set(intake.sources)
        )
        assert any(i.code == "PROXY_LICENCE" for i in issues)
    state.licence_compatible = False
    intake = proxy.proposals.resolved_intake(value.scores)
    issues, _, _ = proxy._disclosures(value, state, intake.model_cards["card"], set(intake.sources))
    assert any(i.code == "PROXY_LICENCE" for i in issues)


def test_proxy_schemas_and_ui_fixtures_are_current():
    import runpy
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    module = runpy.run_path(str(root / "scripts/export_proxy_schemas.py"))
    for name, model in module["MODELS"].items():
        assert json.loads((root / "docs/schemas" / name).read_text()) == {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            **model.model_json_schema(mode="validation"),
        }
    fixture_module = runpy.run_path(str(root / "scripts/export_proxy_test_fixtures.py"))
    for name, value in fixture_module["fixtures"]().items():
        assert json.loads((root / "frontend/tests/fixtures" / name).read_text()) == value


def test_proxy_open_questions_report_pending_disclosures_without_changing_result_schema():
    from mcda_studio.services.questions_service import open_questions

    value = edit(inputs(), lambda state: state.card_facts.pop("licence"))
    questions = open_questions(
        value.project, value.configuration, proxy=value.model_dump(mode="json")
    )
    assert any(q.code == "PROXY_LICENCE" for q in questions.questions)
    assert set(questions.model_dump()) == {
        "project_fingerprint",
        "configuration",
        "questions",
        "coverage",
        "limitations",
    }


def test_feature_factor_links_cannot_refer_to_a_model_from_another_project_revision():
    value = with_factors(
        inputs(state_change=lambda state: state.features[0].factor_ids.append("quality_a"))
    )
    value.factor_parameters = None
    assert not proxy.inspect(value).issues
    value.model.project_fingerprint = "0" * 64
    assert any(issue.code == "PROXY_MODEL_STALE" for issue in proxy.inspect(value).issues)
    with pytest.raises(ModelEditError, match="PROXY_BLOCKED"):
        proxy.run_pair(request(value))


def test_tool_wrapper_version_and_model_card_version_keep_their_distinct_meanings():
    value = inputs(tool_version="wrapper-release-7")
    bundle = proxy.run_pair(request(value))
    assert bundle.status == "completed"
    assert bundle.inspection.model_card.model_version == "1"
    assert bundle.request.scores.intake.proposals[0].tool_version == "wrapper-release-7"
    assert (
        bundle.inspection.calculation.preview.model.sources[0].origin.tool_version
        == "wrapper-release-7"
    )
    assert proxy.verify(bundle.model_dump(mode="json")) == bundle


def test_new_feature_observation_date_requires_newly_reviewed_score_proposals():
    from datetime import date

    value = inputs()
    state = plans.current(value.plan)
    old_draft = proxy.inspect(value).score_draft
    state.features[0].observed_at = date(2026, 10, 2)
    new_draft, _ = proxy._draft(value.project, state)
    assert old_draft.fingerprint() != new_draft.fingerprint()
    # All other facts and reviews remain accepted here so the exact source binding is reached.
    with pytest.raises(StaleRevisionError, match="exact analysis draft"):
        proxy._scores(value, new_draft, state)


def test_feasibility_cannot_be_compensated_and_survives_browser_number_normalization():
    from mcda_studio.domain.requirements import BoundRequirement

    def requirement(project):
        project.performances[0].value = 1.0
        project.requirements = [
            BoundRequirement(
                id="minimum_quality",
                name="Minimum quality",
                criterion_id="quality",
                minimum=0.5,
                maximum=1.0,
                unit=None,
            )
        ]

    value = inputs(project_change=requirement)
    bundle = proxy.run_pair(request(value))
    assert bundle.status == "completed"
    assert bundle.with_proxy.result.ranking[0].alternative_id == "b"
    for half in [bundle.without_proxy, bundle.with_proxy]:
        statuses = {row.alternative_id: row.status for row in half.feasibility.alternatives}
        assert statuses == {"a": "pass", "b": "fail"}
    # Browser JSON serializes integral doubles as integers. Typed replay restores their
    # declared binary64 values; no changed value or digest is accepted.
    document = json.loads(
        bundle.model_dump_json(),
        parse_float=lambda text: int(float(text)) if float(text).is_integer() else float(text),
    )
    assert proxy.verify(document).model_dump_json() == bundle.model_dump_json()


def rebound(value):
    value.scores.digest = proxy.proposals.workspace_digest(value.scores)
    for operation in [
        ProxyOperation(kind="bind_scores", workspace_digest=value.scores.digest, review=REVIEW),
        ProxyOperation(kind="review_plan", review=REVIEW),
        ProxyOperation(kind="set_enabled", enabled=True, review=REVIEW),
    ]:
        value.plan = plans.revise(value.plan, operation, value.plan.digest)
    return value


@pytest.mark.parametrize("human_value", [0.25, 0.5])
def test_reviewed_human_comparison_is_preserved_with_one_explicitly_selected_tool_score(
    human_value,
):
    from mcda_studio.domain.evidence import Claim, EvidenceDossier, Origin

    value = inputs()
    state = plans.current(value.plan)
    value.scores.intake.human_dossier = EvidenceDossier(
        project_fingerprint=value.scores.intake.project_fingerprint,
        claims=[
            Claim(
                id="human_proxy",
                alternative_id="a",
                criterion_id=state.criterion.id,
                value=human_value,
                unit=None,
                source=value.scores.intake.sources["source"],
                origin=Origin(kind="human", proposed_by="Local reviewer"),
                review=REVIEW,
            )
        ],
    )
    value = rebound(value)
    historical = value.scores.intake.human_dossier.model_dump_json()
    bundle = proxy.run_pair(request(value))
    assert bundle.status == "completed"
    assert bundle.request.scores.intake.human_dossier.model_dump_json() == historical
    assert len(bundle.inspection.calculation.preview.calculations) == 2
    selected = [
        calculation
        for calculation in bundle.inspection.calculation.preview.calculations
        if calculation.alternative_id == "a"
    ]
    assert len(selected) == 1
    assert selected[0].value == 0.25
    inspection = proxy.proposals.inspect(
        bundle.inspection.score_draft, bundle.request.scores, "human"
    )
    cell = next(cell for cell in inspection.comparisons if cell.alternative_id == "a")
    assert any(
        column.origin == "human" and column.effective_value == human_value
        for column in cell.columns
    )
    assert proxy.verify(bundle.model_dump(mode="json")) == bundle


def test_reviewed_supporting_assertion_is_retained_without_becoming_another_score():
    from mcda_studio.domain.external_proposals import (
        ProposalReview,
        ProposalReviewDetails,
        SuggestedSourceClaim,
    )

    value = inputs()
    assertion = value.scores.intake.proposals[0].model_copy(deep=True)
    assertion.id = "supporting_assertion"
    assertion.payload = SuggestedSourceClaim(
        source_id="source",
        assertion="Illustrative supporting statement",
        excerpt="Invented supporting statement",
        location="Synthetic appendix",
    )
    value.scores.intake.proposals.append(assertion)
    value.scores.digest = proxy.proposals.workspace_digest(value.scores)
    draft = value.scores.source_project
    inspection = proxy.proposals.inspect(draft, value.scores)
    value.scores = proxy.proposals.review(
        draft,
        value.scores,
        [
            ProposalReview(
                proposal_id=assertion.id,
                review=ProposalReviewDetails(
                    status="accepted",
                    reviewer=REVIEW.reviewer,
                    reviewed_at=REVIEW.reviewed_at,
                    note=REVIEW.note,
                    primary_source_id="source",
                ),
            )
        ],
        inspection.review_digest,
        value.scores.digest,
    ).workspace
    value = rebound(value)
    bundle = proxy.run_pair(request(value))
    assert bundle.status == "completed"
    assert len(bundle.request.scores.intake.proposals) == 3
    assert bundle.request.scores.intake.proposals[-1].payload.kind == "source_claim"
    assert bundle.request.scores.reviews[-1].review.status == "accepted"
    assert len(bundle.inspection.calculation.preview.calculations) == 2
    assert proxy.verify(bundle.model_dump(mode="json")) == bundle
