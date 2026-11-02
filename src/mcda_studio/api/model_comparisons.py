"""Local model comparisons, checked runs and manifest-driven starter operations."""

import json
from typing import Any, Literal

from fastapi import APIRouter, Request, Response

from mcda_studio.domain.derived import DerivedModel
from mcda_studio.domain.evidence import Review
from mcda_studio.domain.factor_uncertainty import FactorUncertaintyModel
from mcda_studio.domain.model_comparison import ModelChecks, ModelComparison, ModelOutputSpec
from mcda_studio.domain.project import Project
from mcda_studio.domain.sidecar_common import SidecarModel
from mcda_studio.domain.starter_templates import (
    StarterInstantiationRequest,
    StarterMaterialization,
    StarterTemplate,
)
from mcda_studio.services import checked_factor_service as checked
from mcda_studio.services import factor_analysis_service as factors
from mcda_studio.services import model_checks_service as checks
from mcda_studio.services import model_comparison_service as comparisons
from mcda_studio.services import starter_template_service as starters

router = APIRouter(prefix="/api", tags=["local models and starters"])


class LocalArtifactRequest(SidecarModel):
    document: dict[str, Any]


class ComparisonRequest(SidecarModel):
    project: Project
    comparison: ModelComparison


class ComparisonReviewRequest(ComparisonRequest):
    review: Review
    expected_review_digest: str


class ModelInputReviewRequest(ComparisonReviewRequest):
    side: Literal["left", "right"]
    kind: Literal["source", "formula", "distribution", "group", "checks", "interval", "aggregation"]
    id: str


class ModelSelectionRequest(ComparisonRequest):
    selection: comparisons.ModelTargetSelection
    expected_review_digest: str


class OutputRunRequest(SidecarModel):
    project: Project
    specification: ModelOutputSpec


class CheckedFactorRequest(SidecarModel):
    project: Project
    model: DerivedModel
    uncertainty: FactorUncertaintyModel
    checks: ModelChecks
    parameters: factors.FactorRunParameters


@router.get("/starter-templates", response_model=list[StarterTemplate])
def list_starters(request: Request) -> list[StarterTemplate]:
    return starters.list_templates(request.app.state.examples_dir)


@router.post("/starter-templates/instantiate", response_model=StarterMaterialization)
def instantiate_starter(
    req: StarterInstantiationRequest, request: Request
) -> StarterMaterialization:
    return starters.instantiate(req, request.app.state.examples_dir)


@router.post("/starter-templates/verify", response_model=StarterMaterialization)
def verify_starter(req: StarterMaterialization, request: Request) -> StarterMaterialization:
    return starters.verify(req, request.app.state.examples_dir)


@router.post("/starter-templates/archive")
def archive_starter(req: StarterMaterialization, request: Request) -> Response:
    return Response(
        starters.archive(req, request.app.state.examples_dir),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="starter-materials.zip"'},
    )


@router.post("/model-comparisons/inspect", response_model=comparisons.ModelComparisonInspection)
@router.post("/model-comparisons/preview", response_model=comparisons.ModelComparisonInspection)
def inspect_comparison(req: ComparisonRequest) -> comparisons.ModelComparisonInspection:
    return comparisons.inspect(req.project, req.comparison)


@router.post("/model-comparisons/review", response_model=comparisons.ModelComparisonInspection)
def review_comparison(req: ComparisonReviewRequest) -> comparisons.ModelComparisonInspection:
    return comparisons.review(req.project, req.comparison, req.review, req.expected_review_digest)


@router.post("/model-comparisons/compile", response_model=comparisons.ModelComparisonCompilation)
def compile_comparison(req: ModelSelectionRequest) -> comparisons.ModelComparisonCompilation:
    return comparisons.compile_selection(
        req.project, req.comparison, req.selection, req.expected_review_digest
    )


@router.post("/model-comparisons/verify", response_model=comparisons.ModelComparisonCompilation)
def verify_comparison(
    req: LocalArtifactRequest,
) -> comparisons.ModelComparisonCompilation:
    return comparisons.verify(
        comparisons.ModelComparisonCompilation.model_validate_json(json.dumps(req.document))
    )


@router.post("/model-outputs/run", response_model=checks.ModelOutputRun)
def output_run(req: OutputRunRequest) -> checks.ModelOutputRun:
    return checks.run_output(req.project, req.specification)


@router.post("/model-outputs/verify", response_model=checks.ModelOutputRun)
def verify_output(req: checks.ModelOutputRun) -> checks.ModelOutputRun:
    return checks.verify_output(req)


@router.post("/checked-factor-runs/run", response_model=checked.CheckedFactorRun)
def checked_run(req: CheckedFactorRequest) -> checked.CheckedFactorRun:
    return checked.run(req.project, req.model, req.uncertainty, req.checks, req.parameters)


@router.post("/checked-factor-runs/verify", response_model=checked.CheckedFactorRun)
def verify_checked_run(req: LocalArtifactRequest) -> checked.CheckedFactorRun:
    return checked.verify(checked.CheckedFactorRun.model_validate_json(json.dumps(req.document)))


@router.post(
    "/model-comparisons/review-input", response_model=comparisons.ModelComparisonInspection
)
def review_model_input(req: ModelInputReviewRequest) -> comparisons.ModelComparisonInspection:
    return comparisons.review_input(
        req.project,
        req.comparison,
        req.side,
        req.kind,
        req.id,
        req.review,
        req.expected_review_digest,
    )


@router.post("/model-comparisons/draft", response_model=ModelComparison)
def draft_model_comparison(req: ComparisonRequest) -> ModelComparison:
    revised = req.comparison.model_copy(deep=True)
    revised.review = None
    revised.digest = comparisons.comparison_digest(revised)
    return revised
