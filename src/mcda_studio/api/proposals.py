"""Stateless proposal HTTP operations; local bounded file content, never provider access."""

from typing import Literal

from fastapi import APIRouter
from pydantic import Field
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mcda_studio.domain.common import DomainModel
from mcda_studio.domain.external_proposals import (
    ExternalProposals,
    ProposalRegistrySupply,
    ProposalReview,
)
from mcda_studio.domain.project import Project
from mcda_studio.services import proposal_import_service as imports
from mcda_studio.services import proposal_service as proposals

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


class ProposalImportRequest(DomainModel):
    project: Project
    text: str = Field(max_length=imports.MAX_BYTES)
    format: Literal["json", "csv"] = "json"
    registries_text: str | None = Field(default=None, max_length=imports.MAX_BYTES)


class ProposalInspectRequest(DomainModel):
    project: Project
    workspace: ExternalProposals
    comparison_target: str | None = None


class ProposalReviewRequest(ProposalInspectRequest):
    events: list[ProposalReview] = Field(min_length=1, max_length=2000)
    expected_review_digest: str
    expected_workspace_digest: str
    bulk: bool = False


class ProposalCompileRequest(ProposalInspectRequest):
    expected_review_digest: str
    expected_workspace_digest: str


class ProposalRegistryRequest(ProposalInspectRequest):
    supply: ProposalRegistrySupply
    expected_workspace_digest: str


@router.post("/registries", response_model=proposals.ProposalInspection)
def supply_proposal_registries(req: ProposalRegistryRequest) -> proposals.ProposalInspection:
    return proposals.supply_registries(
        req.project, req.workspace, req.supply, req.expected_workspace_digest
    )


@router.post("/import", response_model=proposals.ProposalInspection)
def import_proposals(req: ProposalImportRequest) -> proposals.ProposalInspection:
    workspace = imports.parse(req.project, req.text, req.format, req.registries_text)
    return proposals.inspect(req.project, workspace)


@router.post("/inspect", response_model=proposals.ProposalInspection)
@router.post("/preview", response_model=proposals.ProposalInspection)
def inspect_proposals(req: ProposalInspectRequest) -> proposals.ProposalInspection:
    return proposals.inspect(req.project, req.workspace, req.comparison_target)


@router.post("/review", response_model=proposals.ProposalInspection)
def review_proposals(req: ProposalReviewRequest) -> proposals.ProposalInspection:
    return proposals.review(
        req.project,
        req.workspace,
        req.events,
        req.expected_review_digest,
        req.expected_workspace_digest,
        req.bulk,
        req.comparison_target,
    )


@router.post("/compile", response_model=proposals.ProposalCompilation)
def compile_proposals(req: ProposalCompileRequest) -> proposals.ProposalCompilation:
    return proposals.compile_bundle(
        req.project,
        req.workspace,
        req.expected_review_digest,
        req.expected_workspace_digest,
        req.comparison_target,
    )


@router.post("/verify", response_model=proposals.ProposalCompilation)
def verify_proposals(bundle: proposals.ProposalCompilation) -> proposals.ProposalCompilation:
    return proposals.verify(bundle)


class ProposalBodyLimit:
    """Bound the encoded transport before JSON allocation, including chunked requests.

    File contents are independently limited to 8 MB. JSON escaping and the project/registry
    wrapper need additional room; this transport bound is 24 MB and applies only to new routes.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/proposals/"):
            await self.app(scope, receive, send)
            return
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > 24_000_000:
                response = JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "PROPOSAL_BODY_LIMIT",
                            "message": "Proposal request exceeds 24 MB",
                            "details": [],
                        }
                    },
                )
                await response(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, replay, send)
