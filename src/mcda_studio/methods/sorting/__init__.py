"""Value-based sorting into ordered classes on the overall MAVT value (``mavt_sorting``)."""

from mcda_studio.domain.common import Issue
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import MavtSortingResult
from mcda_studio.domain.validation import validate_value_model
from mcda_studio.methods.base import Capability, check_parameters
from mcda_studio.methods.mavt.aggregation import evaluate_mavt
from mcda_studio.methods.mavt.parameters import MavtParameters
from mcda_studio.methods.sorting.classes import build_sorting_result, check_sorting


class MavtSortingMethod:
    name = "mavt_sorting"
    label = "Value-based sorting (MAVT)"
    capabilities: frozenset[Capability] = frozenset(
        {
            "value_functions",
            "swing_weights",
            "value_scores",
            "contributions",
            "weight_sensitivity",
            "scenario_comparison",
            "classes",
        }
    )

    def validate(self, project: Project, configuration: AnalysisConfiguration) -> list[Issue]:
        # MAVT's checks unchanged and in order, then the sorting section, then parameters.
        issues = validate_value_model(project, configuration).issues
        return [
            *issues,
            *check_sorting(project, issues),
            *check_parameters(MavtParameters, configuration.parameters),
        ]

    def evaluate(self, project: Project, configuration: AnalysisConfiguration) -> MavtSortingResult:
        base = evaluate_mavt(project, configuration)  # validates through this method
        assert project.sorting is not None  # guaranteed by validation (NO_SORTING_MODEL)
        return build_sorting_result(base, project.sorting)


__all__ = ["MavtSortingMethod"]
