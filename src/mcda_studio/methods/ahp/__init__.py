"""AHP: priorities from pairwise judgements on criteria and alternatives (``ahp``)."""

from mcda_studio.domain.common import Issue
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import AhpResult
from mcda_studio.domain.validation import validate_structure
from mcda_studio.methods.ahp.engine import run_ahp
from mcda_studio.methods.ahp.validation import AhpParameters, check_ahp
from mcda_studio.methods.base import Capability, check_parameters


class AhpMethod:
    name = "ahp"
    label = "AHP (pairwise priorities)"
    capabilities: frozenset[Capability] = frozenset({"consistency"})

    def validate(self, project: Project, configuration: AnalysisConfiguration) -> list[Issue]:
        # The structural checks, then the section, then parameters. Measurements, value
        # functions, swing profiles and scenarios are not AHP inputs, so their checks do not run.
        return [
            *validate_structure(project).issues,
            *check_ahp(project),
            *check_parameters(AhpParameters, configuration.parameters),
        ]

    def evaluate(self, project: Project, configuration: AnalysisConfiguration) -> AhpResult:
        return run_ahp(project, configuration)


__all__ = ["AhpMethod"]
