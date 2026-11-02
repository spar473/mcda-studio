"""The feasibility check's result: pass, fail or unknown per alternative and requirement.

It does not depend on any method, weight, profile, value function or scenario, and it changes no
ranking. See ``docs/design/feasibility-check.md``.
"""

from typing import Literal

from pydantic import Field

from mcda_studio.domain.common import DomainModel, Id, Issue
from mcda_studio.domain.measurements import Measurement
from mcda_studio.domain.requirements import Requirement

FeasibilityStatus = Literal["pass", "fail", "unknown"]
FeasibilityLabel = Literal[
    "feasibility: each requirement is tested on its own measurement; no score offsets a failure"
]
FEASIBILITY_LABEL: FeasibilityLabel = (
    "feasibility: each requirement is tested on its own measurement; no score offsets a failure"
)


class RequirementCheck(DomainModel):
    requirement_id: Id
    status: FeasibilityStatus
    measurement: Measurement | None
    reason: str


class AlternativeFeasibility(DomainModel):
    alternative_id: Id
    name: str
    status: FeasibilityStatus  # fail if any requirement fails, else unknown if any is unknown
    checks: list[RequirementCheck]  # in requirement order
    failed: list[Id]
    unknown: list[Id]


class RequirementSummary(DomainModel):
    requirement_id: Id
    name: str
    criterion_id: Id
    passed: int
    failed: int
    unknown: int


class FeasibilityResult(DomainModel):
    label: FeasibilityLabel = FEASIBILITY_LABEL
    project_id: Id
    project_fingerprint: str
    requirements: list[Requirement]
    alternatives: list[AlternativeFeasibility]  # in the project's alternative order
    summary: list[RequirementSummary]  # in requirement order
    diagnostics: list[Issue] = Field(default_factory=list)
