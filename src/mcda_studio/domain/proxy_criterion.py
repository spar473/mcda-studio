"""An optional, disclosed criterion plan with explicit, replayable local review actions."""

from datetime import date
from typing import Literal

from pydantic import Field, field_validator

from mcda_studio.domain.common import FiniteFloat, Id
from mcda_studio.domain.criteria import CriterionNode
from mcda_studio.domain.evidence import Review
from mcda_studio.domain.sidecar_common import SidecarModel


class ProxyCardFact(SidecarModel):
    value: str = Field(min_length=1, max_length=2000)
    unknown: bool = False
    reason: str = Field(default="", max_length=2000)
    source_ids: list[Id] = Field(default_factory=list, max_length=64)
    review: Review | None = None


class ProxyFeature(SidecarModel):
    id: Id
    description: str = Field(min_length=1, max_length=2000)
    source_ids: list[Id] = Field(min_length=1, max_length=64)
    observed_at: date = Field(strict=False)
    criterion_ids: list[Id] = Field(default_factory=list, max_length=128)
    factor_ids: list[Id] = Field(default_factory=list, max_length=256)
    review: Review | None = None

    @field_validator("observed_at", mode="before")
    @classmethod
    def calendar_date(cls, value: object) -> object:
        if type(value) is date or (
            isinstance(value, str) and len(value) == 10 and value[4] == "-" and value[7] == "-"
        ):
            return value
        raise ValueError("feature observation date must be an explicit ISO calendar date")


class ProxyOverlap(SidecarModel):
    feature_id: Id
    relation: Literal["same_concept", "shared_evidence", "possible_overlap", "reviewed_distinct"]
    resolution: Literal["baseline_only", "retain_with_rationale", "remove_criterion"]
    remove_criterion_ids: list[Id] = Field(default_factory=list, max_length=128)
    rationale: str = Field(min_length=1, max_length=2000)
    review: Review | None = None


class ProxyPlanState(SidecarModel):
    project_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    criterion: CriterionNode
    score_meaning: str = Field(min_length=1, max_length=2000)
    compared_profile_ids: list[Id] = Field(default_factory=list, max_length=64)
    swing_ratings: dict[Id, FiniteFloat | None] = Field(default_factory=dict, max_length=64)
    card_id: Id | None = None
    card_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    card_facts: dict[Id, ProxyCardFact] = Field(default_factory=dict, max_length=64)
    licence_compatible: bool | None = None
    licence_review: Review | None = None
    features: list[ProxyFeature] = Field(default_factory=list, max_length=128)
    overlaps: list[ProxyOverlap] = Field(default_factory=list, max_length=128)
    score_workspace_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    enabled: bool = False
    plan_review: Review | None = None


class ProxyOperation(SidecarModel):
    kind: Literal[
        "edit",
        "review_card_fact",
        "review_feature",
        "review_overlap",
        "review_licence",
        "review_plan",
        "set_enabled",
        "bind_scores",
    ]
    review: Review
    state: ProxyPlanState | None = None
    id: Id | None = None
    enabled: bool | None = None
    licence_compatible: bool | None = None
    workspace_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class ProxyRevision(SidecarModel):
    previous_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    operation: ProxyOperation


class ProxyCriterionPlan(SidecarModel):
    version: Literal[1] = 1
    initial: ProxyPlanState
    revisions: list[ProxyRevision] = Field(default_factory=list, max_length=2000)
    digest: str


class ProxyAcknowledgements(SidecarModel):
    card: bool = False
    overlap: bool = False
    weight_changes: bool = False
    unknown_facts: bool = False
