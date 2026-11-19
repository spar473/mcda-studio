"""Reviewed evidence compilation bundles: replayable history plus a reproducible static copy."""

from typing import Literal

from mcda_studio.domain.common import DomainModel
from mcda_studio.domain.errors import ModelEditError, StaleRevisionError, ValidationFailed
from mcda_studio.domain.evidence_workspace import EvidenceWorkspace
from mcda_studio.domain.project import Project
from mcda_studio.services import evidence_service as evidence
from mcda_studio.services import evidence_workspace_service as workspaces


class EvidenceCompilation(DomainModel):
    """The exact review history, the preview compiled from it and the separate project copy.

    The effective dossier is not stored: replaying ``workspace`` derives it from the original
    proposals and appended reviews, so no independently editable current state can drift.
    """

    compilation_version: Literal[1] = 1
    workspace: EvidenceWorkspace
    preview: evidence.EvidencePreview
    project: Project
    compiled_fingerprint: str
    digest: str


class EvidenceCompilationInspection(DomainModel):
    """A verified bundle plus its history inspected against the current project."""

    compilation: EvidenceCompilation
    inspection: workspaces.EvidenceInspection


def bundle_digest(bundle: EvidenceCompilation) -> str:
    return evidence._digest(bundle.model_dump(mode="json", exclude={"digest"}))


def compilation_bundle(
    project: Project, workspace: EvidenceWorkspace, review_digest: str, workspace_digest: str
) -> EvidenceCompilation:
    """Compile the replayed dossier through the authoritative gate; nothing is written."""
    dossier = workspaces._replay(workspace)
    # The review digest binds the effective dossier; this binds the exact history behind it.
    if workspace.digest != workspace_digest:
        raise StaleRevisionError("Review history changed; review the compilation again.")
    compiled = evidence.compile_copy(project, dossier, review_digest)
    bundle = EvidenceCompilation(
        workspace=workspace.model_copy(deep=True),
        preview=evidence.preview(project, dossier),
        project=compiled,
        compiled_fingerprint=compiled.fingerprint(),
        digest="",
    )
    bundle.digest = bundle_digest(bundle)
    return bundle


def verify(bundle: EvidenceCompilation) -> EvidenceCompilation:
    """Check the digest, replay the history and reproduce the whole compilation in Python."""
    if bundle.digest != bundle_digest(bundle):
        raise ModelEditError("EVIDENCE_BUNDLE_CHANGED: compilation bundle digest does not match")
    try:
        expected = compilation_bundle(
            bundle.workspace.source_project,
            bundle.workspace,
            bundle.preview.review_digest,
            bundle.workspace.digest,
        )
    except (StaleRevisionError, ValidationFailed) as exc:
        raise ModelEditError(
            "EVIDENCE_BUNDLE_MISMATCH: recorded preview does not reproduce"
        ) from exc
    if expected != bundle:
        raise ModelEditError("EVIDENCE_BUNDLE_MISMATCH: compilation bundle does not reproduce")
    return bundle


def inspect(project: Project, bundle: EvidenceCompilation) -> EvidenceCompilationInspection:
    """Historical inspection never rebinds: the history is checked against the current project."""
    verified = verify(bundle)
    return EvidenceCompilationInspection(
        compilation=verified.model_copy(deep=True),
        inspection=workspaces.inspect(project, verified.workspace),
    )
