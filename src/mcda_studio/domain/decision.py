"""Local decision snapshots; each revision is a separate record."""

from datetime import date
from typing import Literal, Self

from pydantic import Field, model_validator

from mcda_studio.domain.analysis_record import AnyAnalysisRecord
from mcda_studio.domain.common import DomainModel, Id
from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project


class DecisionDraft(DomainModel):
    owner: str = Field(min_length=1)
    date: date
    chosen_alternative_id: Id
    rationale: str = Field(min_length=1)
    configurations: list[AnalysisConfiguration] = Field(min_length=1)
    unresolved_assumptions: list[str] = Field(default_factory=list)
    review_triggers: list[str] = Field(default_factory=list)


class EvidenceSnapshot(DomainModel):
    source_project: Project
    dossier: EvidenceDossier
    review_digest: str
    evidence_digest: str


class DecisionRecord(DomainModel):
    version: Literal[1] = 1
    digest: str
    previous_digest: str | None = None
    decision: DecisionDraft
    project: Project
    project_fingerprint: str
    analyses: list[AnyAnalysisRecord]
    evidence: EvidenceSnapshot | None = None


class DecisionDetails(DomainModel):
    """What the decision owner states for a version-2 record. ``alternatives_considered`` is a
    declaration only: every recorded analysis still uses all of the project's alternatives."""

    owner: str = Field(min_length=1)
    date: date
    outcome: Literal["selected", "deferred"]
    selected_alternative_id: Id | None = None
    alternatives_considered: list[Id] = Field(min_length=1, max_length=100)
    rationale: str = Field(min_length=1)
    # A bounded, explicit selection: never every method/profile/scenario combination.
    configurations: list[AnalysisConfiguration] = Field(min_length=1, max_length=6)
    unresolved_assumptions: list[str] = Field(default_factory=list, max_length=100)
    review_triggers: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def consistent_outcome(self) -> Self:
        if (self.outcome == "selected") != (self.selected_alternative_id is not None):
            raise ValueError("a selected outcome names one alternative; a deferred one names none")
        if len(set(self.alternatives_considered)) != len(self.alternatives_considered):
            raise ValueError("alternatives considered must not repeat")
        if (
            self.selected_alternative_id is not None
            and self.selected_alternative_id not in self.alternatives_considered
        ):
            raise ValueError("the selected alternative must be among those considered")
        seen = [c.model_dump_json() for c in self.configurations]
        if len(set(seen)) != len(seen):
            raise ValueError("each analysis configuration may be recorded once")
        return self
