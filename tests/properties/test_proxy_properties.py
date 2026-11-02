"""Exact invariants across generated disclosures and original preference inputs."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mcda_studio.domain.errors import ModelEditError
from mcda_studio.domain.external_proposals import ProposalConfidence
from mcda_studio.domain.proxy_criterion import ProxyOperation
from mcda_studio.services import analysis_service
from mcda_studio.services import proxy_criterion_service as proxy
from mcda_studio.services import proxy_plan_service as plans
from proxy_builders import REVIEW, inputs, request


@settings(max_examples=12, deadline=None)
@given(confidence=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False))
def test_declared_confidence_metadata_cannot_change_any_paired_project_or_result(confidence):
    value = inputs()
    original = proxy.run_pair(request(value))
    value.scores.intake.proposals[0].confidence = ProposalConfidence(
        value=confidence, scale="unit_interval", meaning="Declared supplier metadata only"
    )
    value.scores.digest = proxy.proposals.workspace_digest(value.scores)
    for operation in [
        ProxyOperation(kind="bind_scores", workspace_digest=value.scores.digest, review=REVIEW),
        ProxyOperation(kind="review_plan", review=REVIEW),
        ProxyOperation(kind="set_enabled", enabled=True, review=REVIEW),
    ]:
        value.plan = plans.revise(value.plan, operation, value.plan.digest)
    changed = proxy.run_pair(request(value))
    for name in ["without_proxy", "with_proxy"]:
        assert (
            getattr(changed, name).project.model_dump_json()
            == getattr(original, name).project.model_dump_json()
        )
        assert (
            getattr(changed, name).result.model_dump_json()
            == getattr(original, name).result.model_dump_json()
        )


@settings(max_examples=12, deadline=None)
@given(
    measurements=st.lists(st.integers(min_value=0, max_value=8), min_size=4, max_size=4),
    ratings=st.tuples(st.integers(min_value=1, max_value=8), st.integers(min_value=1, max_value=8)),
)
def test_disabled_proxy_preserves_original_bytes_and_ordinary_evaluation(measurements, ratings):
    def configure(project):
        for performance, number in zip(project.performances, measurements, strict=True):
            performance.value = number / 8
        project.weight_profiles[0].judgements = {
            "quality": float(ratings[0]),
            "capacity": float(ratings[1]),
        }

    value = inputs(enabled=False, project_change=configure)
    serialized = value.project.model_dump_json()
    expected = analysis_service.evaluate_project(
        value.project, value.configuration
    ).model_dump_json()
    view = proxy.inspect(value)
    assert view.baseline.model_dump_json() == serialized
    assert (
        analysis_service.evaluate_project(view.baseline, value.configuration).model_dump_json()
        == expected
    )
    assert value.project.model_dump_json() == serialized
    with pytest.raises(ModelEditError, match="PROXY_DISABLED"):
        proxy.run_pair(request(value))
