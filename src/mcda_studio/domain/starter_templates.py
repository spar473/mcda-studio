"""Data-only starter manifests and explicit lineage receipts; no template-name dispatch."""

from typing import Any, Literal

from pydantic import Field

from mcda_studio.domain.common import Id
from mcda_studio.domain.project import Project
from mcda_studio.domain.sidecar_common import SidecarModel


class StarterArtifact(SidecarModel):
    id: Id
    path: str = Field(min_length=1, max_length=256)
    kind: str = Field(min_length=1, max_length=64)
    schema_version: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    optional: bool = False
    reset_policy: Literal["draft", "omit"] = "draft"
    for_model: Id | None = None
    label: str = Field(min_length=1, max_length=200)


class StarterTemplate(SidecarModel):
    schema_version: Literal[1] = 1
    id: Id
    version: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    source_example: str = Field(min_length=1, max_length=200)
    source_version: str = Field(min_length=1, max_length=200)
    tasks: list[str] = Field(min_length=1, max_length=30)
    artifacts: list[StarterArtifact] = Field(min_length=1, max_length=100)
    digest: str


class StarterInstantiationRequest(SidecarModel):
    template_id: Id
    mode: Literal["fresh", "worked_example"] = "fresh"
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=4000)
    decision_maker: str = Field(default="", max_length=200)
    project_id: Id | None = None
    optional_artifact_ids: list[Id] = Field(default_factory=list, max_length=30)


class StarterArtifactData(SidecarModel):
    kind: str
    schema_version: int
    label: str
    value: dict[str, Any]


class StarterLineageReceipt(SidecarModel):
    version: Literal[1] = 1
    template_id: str
    template_version: str
    template_digest: str
    request: StarterInstantiationRequest
    original_project_fingerprint: str
    project_fingerprint: str
    artifact_digests: dict[str, str]
    cleared_fields: list[str]
    omitted_artifact_ids: list[str]
    limitations: list[str]
    digest: str


class StarterMaterialization(SidecarModel):
    artifact_kind: Literal["starter_materialization"] = "starter_materialization"
    version: Literal[1] = 1
    template: StarterTemplate
    project: Project
    artifacts: dict[str, StarterArtifactData]
    receipt: StarterLineageReceipt
    digest: str
