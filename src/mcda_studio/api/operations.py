"""Editing operations accepted by ``POST /api/edit``.

Each operation maps one-to-one onto a function in ``mcda_studio.services.project_service``;
nothing here re-implements an editing rule. Operations in one request are applied in order,
all-or-nothing, to the project *in the request body* (the stored project is not touched), so a
client can keep its own unsaved working copy and an undo history.
"""

from typing import Annotated, Literal

from pydantic import Field

from mcda_studio.domain.common import DomainModel, FiniteFloat, Id
from mcda_studio.domain.criteria import ValueFunctionSpec
from mcda_studio.domain.measurements import Measurement
from mcda_studio.domain.outranking import PrometheeModel
from mcda_studio.domain.pairwise import AhpModel
from mcda_studio.domain.project import Project
from mcda_studio.domain.requirements import Requirement
from mcda_studio.domain.scales import Scale
from mcda_studio.domain.sorting import SortingModel
from mcda_studio.domain.uncertainty import SmaaModel
from mcda_studio.services import project_service as ps

_Name = Annotated[str, Field(min_length=1)]


class UpdateProject(DomainModel):
    op: Literal["update_project"] = "update_project"
    title: _Name | None = None
    description: str | None = None
    decision_maker: str | None = None


class AddAlternative(DomainModel):
    op: Literal["add_alternative"] = "add_alternative"
    name: _Name
    alternative_id: Id | None = None


class RenameAlternative(DomainModel):
    op: Literal["rename_alternative"] = "rename_alternative"
    alternative_id: Id
    name: _Name


class RemoveAlternative(DomainModel):
    op: Literal["remove_alternative"] = "remove_alternative"
    alternative_id: Id


class AddCriterion(DomainModel):
    op: Literal["add_criterion"] = "add_criterion"
    name: _Name
    parent_id: Id | None = None
    criterion_id: Id | None = None
    position: int | None = Field(default=None, ge=0)
    scale: Scale | None = None
    value_function: ValueFunctionSpec | None = None
    #: required to turn a measured leaf into a parent (its data would be discarded)
    discard_leaf_data: bool = False


class UpdateCriterion(DomainModel):
    op: Literal["update_criterion"] = "update_criterion"
    criterion_id: Id
    name: _Name | None = None
    description: str | None = None


class MoveCriterion(DomainModel):
    op: Literal["move_criterion"] = "move_criterion"
    criterion_id: Id
    new_parent_id: Id | None = None  # null = top level
    position: int | None = Field(default=None, ge=0)
    discard_leaf_data: bool = False


class RemoveCriterion(DomainModel):
    op: Literal["remove_criterion"] = "remove_criterion"
    criterion_id: Id


class SetScale(DomainModel):
    op: Literal["set_scale"] = "set_scale"
    criterion_id: Id
    scale: Scale


class SetValueFunction(DomainModel):
    op: Literal["set_value_function"] = "set_value_function"
    criterion_id: Id
    value_function: ValueFunctionSpec


class SetPerformance(DomainModel):
    op: Literal["set_performance"] = "set_performance"
    alternative_id: Id
    criterion_id: Id
    value: FiniteFloat | str


class ClearPerformance(DomainModel):
    op: Literal["clear_performance"] = "clear_performance"
    alternative_id: Id
    criterion_id: Id


class ClearCriterionPerformances(DomainModel):
    op: Literal["clear_criterion_performances"] = "clear_criterion_performances"
    criterion_id: Id


class SetJudgement(DomainModel):
    op: Literal["set_judgement"] = "set_judgement"
    node_id: Id
    rating: FiniteFloat
    profile_id: Id | None = None


class ClearJudgement(DomainModel):
    op: Literal["clear_judgement"] = "clear_judgement"
    node_id: Id
    profile_id: Id | None = None


class CreateWeightProfile(DomainModel):
    op: Literal["create_weight_profile"] = "create_weight_profile"
    name: _Name
    profile_id: Id | None = None


class DuplicateWeightProfile(DomainModel):
    op: Literal["duplicate_weight_profile"] = "duplicate_weight_profile"
    profile_id: Id
    name: _Name
    new_profile_id: Id | None = None


class RenameWeightProfile(DomainModel):
    op: Literal["rename_weight_profile"] = "rename_weight_profile"
    profile_id: Id
    name: _Name


class RemoveWeightProfile(DomainModel):
    op: Literal["remove_weight_profile"] = "remove_weight_profile"
    profile_id: Id
    replacement_profile_id: Id | None = None


class SetDefaultWeightProfile(DomainModel):
    op: Literal["set_default_weight_profile"] = "set_default_weight_profile"
    profile_id: Id | None


class CreateScenario(DomainModel):
    op: Literal["create_scenario"] = "create_scenario"
    name: _Name
    scenario_id: Id | None = None


class DuplicateScenario(DomainModel):
    op: Literal["duplicate_scenario"] = "duplicate_scenario"
    scenario_id: Id
    name: _Name
    new_scenario_id: Id | None = None


class RenameScenario(DomainModel):
    op: Literal["rename_scenario"] = "rename_scenario"
    scenario_id: Id
    name: _Name


class RemoveScenario(DomainModel):
    op: Literal["remove_scenario"] = "remove_scenario"
    scenario_id: Id
    repair_default: bool = False
    replacement_scenario_id: Id | None = None


class SetScenarioProfile(DomainModel):
    op: Literal["set_scenario_profile"] = "set_scenario_profile"
    scenario_id: Id
    profile_id: Id | None


class SetScenarioOverride(DomainModel):
    op: Literal["set_scenario_override"] = "set_scenario_override"
    scenario_id: Id
    criterion_id: Id
    value_function: ValueFunctionSpec


class ClearScenarioOverride(DomainModel):
    op: Literal["clear_scenario_override"] = "clear_scenario_override"
    scenario_id: Id
    criterion_id: Id


class SetDefaultScenario(DomainModel):
    op: Literal["set_default_scenario"] = "set_default_scenario"
    scenario_id: Id | None


class SetSortingModel(DomainModel):
    op: Literal["set_sorting_model"] = "set_sorting_model"
    sorting: SortingModel


class ClearSortingModel(DomainModel):
    op: Literal["clear_sorting_model"] = "clear_sorting_model"


class SetSmaaModel(DomainModel):
    op: Literal["set_smaa_model"] = "set_smaa_model"
    smaa: SmaaModel


class ClearSmaaModel(DomainModel):
    op: Literal["clear_smaa_model"] = "clear_smaa_model"


class SetPrometheeModel(DomainModel):
    op: Literal["set_promethee_model"] = "set_promethee_model"
    promethee: PrometheeModel


class ClearPrometheeModel(DomainModel):
    op: Literal["clear_promethee_model"] = "clear_promethee_model"


class SetAhpModel(DomainModel):
    op: Literal["set_ahp_model"] = "set_ahp_model"
    ahp: AhpModel


class ClearAhpModel(DomainModel):
    op: Literal["clear_ahp_model"] = "clear_ahp_model"


class SetRequirements(DomainModel):
    op: Literal["set_requirements"] = "set_requirements"
    requirements: list[Requirement]


class ClearRequirements(DomainModel):
    op: Literal["clear_requirements"] = "clear_requirements"


class SetAnalysisMethod(DomainModel):
    op: Literal["set_analysis_method"] = "set_analysis_method"
    method: _Name


Operation = Annotated[
    UpdateProject
    | AddAlternative
    | RenameAlternative
    | RemoveAlternative
    | AddCriterion
    | UpdateCriterion
    | MoveCriterion
    | RemoveCriterion
    | SetScale
    | SetValueFunction
    | SetPerformance
    | ClearPerformance
    | ClearCriterionPerformances
    | SetJudgement
    | ClearJudgement
    | CreateWeightProfile
    | DuplicateWeightProfile
    | RenameWeightProfile
    | RemoveWeightProfile
    | SetDefaultWeightProfile
    | CreateScenario
    | DuplicateScenario
    | RenameScenario
    | RemoveScenario
    | SetScenarioProfile
    | SetScenarioOverride
    | ClearScenarioOverride
    | SetDefaultScenario
    | SetSortingModel
    | ClearSortingModel
    | SetSmaaModel
    | ClearSmaaModel
    | SetPrometheeModel
    | ClearPrometheeModel
    | SetAhpModel
    | ClearAhpModel
    | SetRequirements
    | ClearRequirements
    | SetAnalysisMethod,
    Field(discriminator="op"),
]


def apply_operation(project: Project, op: Operation) -> Project:
    """Apply one operation through the services layer; returns a new Project."""
    match op:
        case UpdateProject():
            return ps.update_project_details(project, op.title, op.description, op.decision_maker)
        case AddAlternative():
            return ps.add_alternative(project, op.name, alt_id=op.alternative_id)
        case RenameAlternative():
            return ps.rename_alternative(project, op.alternative_id, op.name)
        case RemoveAlternative():
            return ps.remove_alternative(project, op.alternative_id)
        case AddCriterion():
            return ps.add_criterion(
                project,
                op.name,
                parent_id=op.parent_id,
                crit_id=op.criterion_id,
                scale=op.scale,
                value_function=op.value_function,
                position=op.position,
                discard_leaf_data=op.discard_leaf_data,
            )
        case UpdateCriterion():
            return ps.update_criterion(project, op.criterion_id, op.name, op.description)
        case MoveCriterion():
            return ps.move_criterion(
                project,
                op.criterion_id,
                op.new_parent_id,
                position=op.position,
                discard_leaf_data=op.discard_leaf_data,
            )
        case RemoveCriterion():
            return ps.remove_criterion(project, op.criterion_id)
        case SetScale():
            return ps.set_scale(project, op.criterion_id, op.scale)
        case SetValueFunction():
            return ps.set_value_function(project, op.criterion_id, op.value_function)
        case SetPerformance():
            value: Measurement = op.value
            return ps.set_performance(project, op.alternative_id, op.criterion_id, value)
        case ClearPerformance():
            return ps.clear_performance(project, op.alternative_id, op.criterion_id)
        case ClearCriterionPerformances():
            return ps.clear_criterion_performances(project, op.criterion_id)
        case SetJudgement():
            return ps.set_judgement(project, op.node_id, op.rating, op.profile_id)
        case ClearJudgement():
            return ps.clear_judgement(project, op.node_id, op.profile_id)

        case CreateWeightProfile():
            return ps.create_weight_profile(project, op.name, op.profile_id)
        case DuplicateWeightProfile():
            return ps.duplicate_weight_profile(project, op.profile_id, op.name, op.new_profile_id)
        case RenameWeightProfile():
            return ps.rename_weight_profile(project, op.profile_id, op.name)
        case RemoveWeightProfile():
            return ps.remove_weight_profile(project, op.profile_id, op.replacement_profile_id)
        case SetDefaultWeightProfile():
            return ps.set_default_weight_profile(project, op.profile_id)

        case CreateScenario():
            return ps.create_scenario(project, op.name, op.scenario_id)
        case DuplicateScenario():
            return ps.duplicate_scenario(project, op.scenario_id, op.name, op.new_scenario_id)
        case RenameScenario():
            return ps.rename_scenario(project, op.scenario_id, op.name)
        case RemoveScenario():
            return ps.remove_scenario(
                project,
                op.scenario_id,
                repair_default=op.repair_default,
                replacement_scenario_id=op.replacement_scenario_id,
            )
        case SetScenarioProfile():
            return ps.set_scenario_profile(project, op.scenario_id, op.profile_id)
        case SetScenarioOverride():
            return ps.set_scenario_override(
                project, op.scenario_id, op.criterion_id, op.value_function
            )
        case ClearScenarioOverride():
            return ps.clear_scenario_override(project, op.scenario_id, op.criterion_id)
        case SetDefaultScenario():
            return ps.set_default_scenario(project, op.scenario_id)

        case SetSortingModel():
            return ps.set_sorting_model(project, op.sorting)
        case ClearSortingModel():
            return ps.clear_sorting_model(project)
        case SetSmaaModel():
            return ps.set_smaa_model(project, op.smaa)
        case ClearSmaaModel():
            return ps.clear_smaa_model(project)
        case SetPrometheeModel():
            return ps.set_promethee_model(project, op.promethee)
        case ClearPrometheeModel():
            return ps.clear_promethee_model(project)
        case SetAhpModel():
            return ps.set_ahp_model(project, op.ahp)
        case ClearAhpModel():
            return ps.clear_ahp_model(project)
        case SetRequirements():
            return ps.set_requirements(project, list(op.requirements))
        case ClearRequirements():
            return ps.clear_requirements(project)
        case SetAnalysisMethod():
            return ps.set_analysis_method(project, op.method)
