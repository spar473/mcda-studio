"""Relate a current project to a retained compilation artifact; never rebind or merge identities.

Different fingerprints never compare equal. A separate copy is accepted only through an explicit
receipt whose single recorded transformation reproduces both fingerprints exactly.
"""

from typing import Literal

from mcda_studio.domain.common import DomainModel
from mcda_studio.domain.errors import ModelEditError
from mcda_studio.domain.project import Project
from mcda_studio.domain.provenance import ProjectCopyReceipt
from mcda_studio.services import derived_service as derived
from mcda_studio.services import evidence_compilation_service as evidence_compilation
from mcda_studio.services import evidence_service as evidence

Artifact = evidence_compilation.EvidenceCompilation | derived.DerivedCompilation
Relationship = Literal["compiled", "source", "verified_copy", "different"]


class ArtifactBinding(DomainModel):
    """How the current project relates to a verified artifact. ``different`` is not an error:
    the artifact stays inspectable, but nothing may act on it in the current context."""

    artifact_kind: Literal["evidence_compilation", "calculation_bundle"]
    artifact_digest: str
    source_fingerprint: str
    compiled_fingerprint: str
    current_fingerprint: str
    relationship: Relationship
    copy_receipt: ProjectCopyReceipt | None


def receipt_digest(receipt: ProjectCopyReceipt) -> str:
    return evidence._digest(receipt.model_dump(mode="json", exclude={"digest"}))


def _with_id(project: Project, project_id: str) -> Project:
    result = project.model_copy(deep=True)
    result.id = project_id
    return result


def verify_receipt(copy: Project, receipt: ProjectCopyReceipt) -> ProjectCopyReceipt:
    """The receipt must describe this exact copy, and restoring the ID must give the original."""
    if receipt.digest != receipt_digest(receipt):
        raise ModelEditError("PROVENANCE_RECEIPT_CHANGED: copy receipt digest does not match")
    if receipt.original_project_id == receipt.copy_project_id:
        raise ModelEditError("PROVENANCE_RECEIPT_IDENTITY: a copy receipt must change the ID")
    if copy.id != receipt.copy_project_id or copy.fingerprint() != receipt.copy_fingerprint:
        raise ModelEditError(
            "PROVENANCE_RECEIPT_PROJECT: copy receipt does not describe this project revision"
        )
    if _with_id(copy, receipt.original_project_id).fingerprint() != receipt.original_fingerprint:
        raise ModelEditError(
            "PROVENANCE_RECEIPT_TRANSFORMATION: the copy differs by more than its project ID"
        )
    return receipt


def copy_receipt(original: Project, copy: Project) -> ProjectCopyReceipt:
    """Record an import that replaced only the project ID; refuse any other difference."""
    receipt = ProjectCopyReceipt(
        original_project_id=original.id,
        original_fingerprint=original.fingerprint(),
        copy_project_id=copy.id,
        copy_fingerprint=copy.fingerprint(),
        digest="",
    )
    receipt.digest = receipt_digest(receipt)
    return verify_receipt(copy, receipt)


def bind(
    project: Project, artifact: Artifact, receipt: ProjectCopyReceipt | None = None
) -> ArtifactBinding:
    """Verify the artifact in full, then classify the current project by exact fingerprints."""
    if isinstance(artifact, evidence_compilation.EvidenceCompilation):
        evidence_compilation.verify(artifact)
        kind: Literal["evidence_compilation", "calculation_bundle"] = "evidence_compilation"
        source = artifact.workspace.source_project
    else:
        derived.verify_bundle(artifact)
        kind = "calculation_bundle"
        source = artifact.source_project
    current = project.fingerprint()
    relationship: Relationship
    if receipt is not None:
        verify_receipt(project, receipt)
        if receipt.original_fingerprint != artifact.compiled_fingerprint:
            raise ModelEditError(
                "PROVENANCE_RECEIPT_ARTIFACT: receipt does not start from this compiled project"
            )
        relationship = "verified_copy"
    elif current == artifact.compiled_fingerprint:
        relationship = "compiled"
    elif current == source.fingerprint():
        relationship = "source"
    else:
        relationship = "different"
    return ArtifactBinding(
        artifact_kind=kind,
        artifact_digest=artifact.digest,
        source_fingerprint=source.fingerprint(),
        compiled_fingerprint=artifact.compiled_fingerprint,
        current_fingerprint=current,
        relationship=relationship,
        copy_receipt=receipt.model_copy(deep=True) if receipt is not None else None,
    )
