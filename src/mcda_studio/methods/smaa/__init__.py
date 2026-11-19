"""SMAA-2: sampled rank and class acceptability under stated uncertainty (``smaa2``)."""

from mcda_studio.domain.common import Issue
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import SmaaResult
from mcda_studio.domain.validation import validate_value_model
from mcda_studio.methods.base import Capability, check_parameters
from mcda_studio.methods.smaa.engine import run_smaa
from mcda_studio.methods.smaa.validation import SmaaParameters, check_smaa


class SmaaMethod:
    name = "smaa2"
    label = "SMAA-2 (sampled acceptability)"
    capabilities: frozenset[Capability] = frozenset(
        {"value_functions", "swing_weights", "acceptability"}
    )

    def validate(self, project: Project, configuration: AnalysisConfiguration) -> list[Issue]:
        # MAVT's checks of the deterministic model first, then the stated uncertainty, then
        # parameters. A missing measurement still blocks: a distribution never fills it.
        issues = validate_value_model(project, configuration).issues
        return [
            *issues,
            *check_smaa(project, configuration, issues),
            *check_parameters(SmaaParameters, configuration.parameters),
        ]

    def evaluate(self, project: Project, configuration: AnalysisConfiguration) -> SmaaResult:
        return run_smaa(project, configuration)


__all__ = ["SmaaMethod"]
