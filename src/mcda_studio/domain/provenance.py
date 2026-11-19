"""Versioned records of identity changes between project copies; never an equality rule."""

from typing import Annotated, Literal

from pydantic import StringConstraints

from mcda_studio.domain.common import DomainModel, Id

Fingerprint = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class ProjectCopyReceipt(DomainModel):
    """Issued when an import stores a project under a new ID because the original ID exists.

    ``new_project_id`` means exactly one change: ``id`` was replaced. Every other field, and
    therefore every measurement and judgement, is byte-identical in canonical JSON.
    """

    receipt_version: Literal[1] = 1
    transformation: Literal["new_project_id"] = "new_project_id"
    original_project_id: Id
    original_fingerprint: Fingerprint
    copy_project_id: Id
    copy_fingerprint: Fingerprint
    digest: str
