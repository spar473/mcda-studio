"""PROMETHEE II: net outranking flows and the PROMETHEE I partial order (``promethee2``)."""

from mcda_studio.domain.common import Issue
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import PrometheeResult
from mcda_studio.domain.validation import validate_measurements
from mcda_studio.methods.base import Capability, check_parameters
from mcda_studio.methods.promethee.engine import run_promethee
from mcda_studio.methods.promethee.validation import PrometheeParameters, check_promethee


class PrometheeMethod:
    name = "promethee2"
    label = "PROMETHEE II (outranking flows)"
    capabilities: frozenset[Capability] = frozenset({"flows"})

    def validate(self, project: Project, configuration: AnalysisConfiguration) -> list[Issue]:
        # The method-independent measurement checks, then the section, then parameters. MAVT's
        # value functions and swing profiles are not PROMETHEE inputs, so their checks do not run.
        return [
            *validate_measurements(project).issues,
            *check_promethee(project),
            *check_parameters(PrometheeParameters, configuration.parameters),
        ]

    def evaluate(self, project: Project, configuration: AnalysisConfiguration) -> PrometheeResult:
        return run_promethee(project, configuration)


__all__ = ["PrometheeMethod"]
