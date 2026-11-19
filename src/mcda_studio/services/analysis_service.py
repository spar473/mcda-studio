"""Coordinates validation and calculation: the single entry point for the CLI and later the API."""

import mcda_studio.methods  # noqa: F401  (registers built-in methods)
from mcda_studio.domain.pairwise import PairwiseJudgement
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.previews import (
    AnalysisValidation,
    SensitivityProbe,
    ValueFunctionCandidate,
    ValueFunctionPreview,
    WeightPreview,
)
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import (
    AhpMatrixPreview,
    AnalysisResult,
    ScenarioComparison,
    SensitivityResult,
)
from mcda_studio.domain.validation import ValidationReport, validate_project
from mcda_studio.methods.ahp.engine import preview_matrix
from mcda_studio.methods.base import (
    Capability,
    available_methods,
    get_method,
    require_capability,
    validate_analysis,
)
from mcda_studio.methods.mavt import sensitivity as _sens
from mcda_studio.methods.mavt.previews import preview_value_function as _preview_value_function
from mcda_studio.methods.mavt.previews import preview_weights as _preview_weights
from mcda_studio.methods.sorting import sensitivity as _sorting


def validate(
    project: Project, configuration: AnalysisConfiguration | None = None
) -> ValidationReport:
    return validate_project(project, configuration)


def _require(
    project: Project, configuration: AnalysisConfiguration | None, capability: Capability
) -> None:
    require_capability(configuration or project.analysis, capability)


def _sorts(project: Project, configuration: AnalysisConfiguration | None) -> bool:
    """Sensitivity of a method that assigns classes also reports exact class changes."""
    name = (configuration or project.analysis).method
    return name in available_methods() and "classes" in get_method(name).capabilities


def evaluate_project(
    project: Project, configuration: AnalysisConfiguration | None = None
) -> AnalysisResult:
    cfg = configuration or project.analysis
    return get_method(cfg.method).evaluate(project, cfg)


def sensitivity(
    project: Project,
    node_id: str,
    configuration: AnalysisConfiguration | None = None,
    steps: int = 101,
) -> SensitivityResult:
    _require(project, configuration, "weight_sensitivity")
    result = _sens.weight_sensitivity(project, configuration, node_id, steps)
    if _sorts(project, configuration):
        return _sorting.sorting_sensitivity(project, configuration or project.analysis, result)
    return result


def sensitivity_probe(
    project: Project,
    node_id: str,
    weight: float,
    configuration: AnalysisConfiguration | None = None,
) -> SensitivityProbe:
    """Read-only scores at one hypothetical local weight; never persists anything."""
    _require(project, configuration, "weight_sensitivity")
    probe = _sens.sensitivity_probe(project, configuration, node_id, weight)
    return _sorting.sorting_probe(project, probe) if _sorts(project, configuration) else probe


def sensitivity_all(
    project: Project, configuration: AnalysisConfiguration | None = None, steps: int = 101
) -> list[SensitivityResult]:
    _require(project, configuration, "weight_sensitivity")
    results = _sens.sensitivity_all(project, configuration, steps)
    if _sorts(project, configuration):
        cfg = configuration or project.analysis
        return [_sorting.sorting_sensitivity(project, cfg, r) for r in results]
    return results


def compare_scenarios(
    project: Project,
    scenario_ids: list[str] | None = None,
    configuration: AnalysisConfiguration | None = None,
) -> ScenarioComparison:
    _require(project, configuration, "scenario_comparison")
    return _sens.compare_scenarios(project, scenario_ids, configuration)


def preview_value_function(
    project: Project,
    criterion_id: str,
    configuration: AnalysisConfiguration | None = None,
    candidate: ValueFunctionCandidate | None = None,
    sample_count: int = 101,
) -> ValueFunctionPreview:
    _require(project, configuration, "value_functions")
    return _preview_value_function(project, criterion_id, configuration, candidate, sample_count)


def preview_weights(
    project: Project, configuration: AnalysisConfiguration | None = None
) -> WeightPreview:
    _require(project, configuration, "swing_weights")
    return _preview_weights(project, configuration)


def validate_effective(
    project: Project, configuration: AnalysisConfiguration | None = None
) -> AnalysisValidation:
    cfg = (configuration or project.analysis).model_copy(deep=True)
    project.resolve_scenario(cfg)
    profile = project.resolve_profile(cfg)
    return AnalysisValidation(
        project_fingerprint=project.fingerprint(),
        configuration=cfg,
        scenario_id=cfg.scenario_id,
        weight_profile_id=profile.id if profile else None,
        validation=validate_analysis(project, cfg),
    )


def preview_ahp_matrix(items: list[str], judgements: list[PairwiseJudgement]) -> AhpMatrixPreview:
    """Read-only priorities and consistency of one drafted AHP matrix; needs no project."""
    return preview_matrix(items, judgements)
