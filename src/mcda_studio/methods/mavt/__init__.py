"""Additive multi-attribute value theory (MAVT) with swing weighting."""

from mcda_studio.domain.common import Issue
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import MavtResult
from mcda_studio.domain.validation import validate_value_model
from mcda_studio.methods.base import Capability, check_parameters
from mcda_studio.methods.mavt.aggregation import evaluate_mavt
from mcda_studio.methods.mavt.parameters import MavtParameters


class MavtMethod:
    name = "mavt"
    label = "MAVT (additive value)"
    capabilities: frozenset[Capability] = frozenset(
        {
            "value_functions",
            "swing_weights",
            "value_scores",
            "contributions",
            "weight_sensitivity",
            "scenario_comparison",
        }
    )

    def validate(self, project: Project, configuration: AnalysisConfiguration) -> list[Issue]:
        issues = validate_value_model(project, configuration).issues
        return [*issues, *check_parameters(MavtParameters, configuration.parameters)]

    def evaluate(self, project: Project, configuration: AnalysisConfiguration) -> MavtResult:
        return evaluate_mavt(project, configuration)


__all__ = ["MavtMethod", "evaluate_mavt"]
