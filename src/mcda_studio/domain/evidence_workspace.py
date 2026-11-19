"""Portable review history around unchanged version-1 evidence dossiers."""

from typing import Literal

from pydantic import Field

from mcda_studio.domain.common import DomainModel, Id
from mcda_studio.domain.evidence import EvidenceDossier, Review
from mcda_studio.domain.project import Project


class ClaimReview(DomainModel):
    claim_id: Id
    review: Review


class EvidenceWorkspace(DomainModel):
    workspace_version: Literal[1] = 1
    source_project: Project
    original_dossier: EvidenceDossier
    # Original proposals and original reviews remain in original_dossier; every later review
    # is appended. Reopening replays these events, rather than trusting a cached current state.
    reviews: list[ClaimReview] = Field(default_factory=list, max_length=2000)
    digest: str
