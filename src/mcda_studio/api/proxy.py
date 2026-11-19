"""Stateless local disclosure-plan and paired-analysis endpoints."""

from fastapi import APIRouter

from mcda_studio.api.model_comparisons import LocalArtifactRequest
from mcda_studio.domain.proxy_criterion import ProxyCriterionPlan, ProxyOperation, ProxyPlanState
from mcda_studio.domain.sidecar_common import SidecarModel
from mcda_studio.services import proxy_criterion_service as proxy
from mcda_studio.services import proxy_plan_service as plans

router = APIRouter(prefix="/api/proxy", tags=["disclosed proxy"])


class ProxyRevisionRequest(SidecarModel):
    plan: ProxyCriterionPlan
    operation: ProxyOperation
    expected_digest: str


@router.post("/start", response_model=ProxyCriterionPlan)
def start(state: ProxyPlanState) -> ProxyCriterionPlan:
    return plans.start(state)


@router.post("/revise", response_model=ProxyCriterionPlan)
def revise(req: ProxyRevisionRequest) -> ProxyCriterionPlan:
    return plans.revise(req.plan, req.operation, req.expected_digest)


@router.post("/inspect", response_model=proxy.ProxyInspection)
@router.post("/preview-pair", response_model=proxy.ProxyInspection)
def inspect(req: proxy.ProxyInputs) -> proxy.ProxyInspection:
    return proxy.inspect(req)


@router.post("/run-pair", response_model=proxy.ProxyComparisonBundle)
def run(req: proxy.ProxyPairRequest) -> proxy.ProxyComparisonBundle:
    return proxy.run_pair(req)


@router.post("/verify", response_model=proxy.ProxyComparisonBundle)
def verify(req: LocalArtifactRequest) -> proxy.ProxyComparisonBundle:
    return proxy.verify(req.document)
