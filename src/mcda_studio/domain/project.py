"""The Project aggregate: everything needed to define, save and re-run a decision analysis."""

import hashlib
import json

from pydantic import Field, field_serializer

from mcda_studio.domain.alternatives import Alternative
from mcda_studio.domain.common import DomainModel, Id
from mcda_studio.domain.criteria import CriterionNode, CriterionTree
from mcda_studio.domain.errors import UnknownReferenceError
from mcda_studio.domain.measurements import Measurement, Performance
from mcda_studio.domain.outranking import PrometheeModel
from mcda_studio.domain.pairwise import AhpModel
from mcda_studio.domain.preferences import (
    AnalysisConfiguration,
    Scenario,
    WeightProfile,
)
from mcda_studio.domain.requirements import Requirement
from mcda_studio.domain.sorting import SortingModel
from mcda_studio.domain.uncertainty import SmaaModel

#: The newest schema this program reads and writes. A file is written with the *lowest* version
#: that can represent it (``Project.required_schema_version``), so a project that uses no newer
#: section keeps its bytes, its fingerprint and older installations' ability to open it.
SCHEMA_VERSION = 6

#: The first schema version of each optional method section.
SECTION_VERSIONS = {"sorting": 2, "smaa": 3, "promethee": 4, "ahp": 5, "requirements": 6}


class Project(DomainModel):
    # The version this project needs: loading and the section edits keep it equal to
    # ``required_schema_version()``, and what is written is always that, whatever is stored here.
    schema_version: int = 1
    id: Id
    title: str = Field(min_length=1)
    description: str = ""
    decision_maker: str = ""
    alternatives: list[Alternative] = Field(default_factory=list)
    criteria: list[CriterionNode] = Field(default_factory=list)
    performances: list[Performance] = Field(default_factory=list)
    weight_profiles: list[WeightProfile] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(default_factory=list)
    analysis: AnalysisConfiguration = Field(default_factory=AnalysisConfiguration)
    # Absent method sections are omitted from files and fingerprints, never written as null.
    sorting: SortingModel | None = Field(default=None, exclude_if=lambda v: v is None)
    smaa: SmaaModel | None = Field(default=None, exclude_if=lambda v: v is None)
    promethee: PrometheeModel | None = Field(default=None, exclude_if=lambda v: v is None)
    ahp: AhpModel | None = Field(default=None, exclude_if=lambda v: v is None)
    # Feasibility requirements: method-independent, never empty when present.
    requirements: list[Requirement] | None = Field(default=None, exclude_if=lambda v: v is None)

    @field_serializer("schema_version")
    def _lowest_sufficient_version(self, _stored: int) -> int:
        return self.required_schema_version()

    def required_schema_version(self) -> int:
        """The lowest schema version that can represent this project."""
        used = [v for name, v in SECTION_VERSIONS.items() if getattr(self, name) is not None]
        return max([1, *used])

    # ---- read-only helpers (never mutate) -------------------------------------------------
    def tree(self) -> CriterionTree:
        return CriterionTree(self.criteria)

    def alternative_ids(self) -> list[str]:
        return [a.id for a in self.alternatives]

    def performance_index(self) -> dict[tuple[str, str], Measurement]:
        return {(p.alternative_id, p.criterion_id): p.value for p in self.performances}

    def fingerprint(self) -> str:
        """sha256 over canonical JSON: identical models give identical fingerprints."""
        canonical = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def resolve_scenario(self, configuration: AnalysisConfiguration) -> Scenario | None:
        if configuration.scenario_id is None:
            return None
        for s in self.scenarios:
            if s.id == configuration.scenario_id:
                return s
        raise UnknownReferenceError(f"unknown scenario id {configuration.scenario_id!r}")

    def resolve_profile(self, configuration: AnalysisConfiguration) -> WeightProfile | None:
        """Profile precedence: configuration > scenario > first profile in the project."""
        wanted = configuration.weight_profile_id
        if wanted is None:
            scenario = self.resolve_scenario(configuration)
            wanted = scenario.weight_profile_id if scenario else None
        if wanted is None:
            return self.weight_profiles[0] if self.weight_profiles else None
        for p in self.weight_profiles:
            if p.id == wanted:
                return p
        raise UnknownReferenceError(f"unknown weight profile id {wanted!r}")
