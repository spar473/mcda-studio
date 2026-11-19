"""Editing operations on projects.

Every function takes a Project and returns a *new* Project; the argument is never mutated, so a
saved baseline (or a template shared by several projects) cannot be altered by accident. Results
are re-validated by pydantic on construction; semantic completeness is checked by
``validate_project``.
"""

import re
import uuid
from collections.abc import Set as AbstractSet

from mcda_studio.domain.alternatives import Alternative
from mcda_studio.domain.criteria import CriterionNode, CriterionTree, ValueFunctionSpec
from mcda_studio.domain.errors import ModelEditError, UnknownReferenceError
from mcda_studio.domain.measurements import Measurement, Performance
from mcda_studio.domain.outranking import PrometheeModel
from mcda_studio.domain.pairwise import AhpModel, PairwiseJudgement
from mcda_studio.domain.preferences import AnalysisConfiguration, Scenario, WeightProfile
from mcda_studio.domain.project import Project
from mcda_studio.domain.requirements import AnyRequirement
from mcda_studio.domain.scales import Scale
from mcda_studio.domain.sorting import SortingClass, SortingModel
from mcda_studio.domain.uncertainty import CellRef, CellUncertainty, SmaaModel
from mcda_studio.methods import get_method

DEFAULT_PROFILE_ID = "default"


def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", name.strip()).strip("_").lower()
    return (s or "item")[:48]


def _unique_id(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    n = 2
    while f"{base}_{n}" in taken:
        n += 1
    return f"{base}_{n}"


def _copy(project: Project) -> Project:
    return project.model_copy(deep=True)


def _rebuild(project: Project) -> Project:
    """Re-run pydantic validation on a mutated copy."""
    return Project.model_validate(project.model_dump())


# ---- project level ----------------------------------------------------------------------
def new_project(
    title: str, description: str = "", decision_maker: str = "", method: str = "mavt"
) -> Project:
    return Project(
        id=uuid.uuid4().hex[:16],
        title=title,
        description=description,
        decision_maker=decision_maker,
        weight_profiles=[WeightProfile(id=DEFAULT_PROFILE_ID, name="Default")],
        analysis=AnalysisConfiguration(method=method),
    )


def duplicate_project(project: Project, title: str | None = None) -> Project:
    """Independent deep copy with a fresh id; the original is untouched."""
    clone = _copy(project)
    clone.id = uuid.uuid4().hex[:16]
    clone.title = title or f"{project.title} (copy)"
    return clone


def rename_project(project: Project, title: str) -> Project:
    out = _copy(project)
    out.title = title
    return out


def update_project_details(
    project: Project,
    title: str | None = None,
    description: str | None = None,
    decision_maker: str | None = None,
) -> Project:
    """Change the descriptive fields; ``None`` leaves a field as it is."""
    out = _copy(project)
    if title is not None:
        out.title = title
    if description is not None:
        out.description = description
    if decision_maker is not None:
        out.decision_maker = decision_maker
    return out


# ---- alternatives -----------------------------------------------------------------------
def add_alternative(
    project: Project,
    name: str,
    alt_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> Project:
    out = _copy(project)
    taken = {a.id for a in out.alternatives}
    new_id = alt_id or _unique_id(_slug(name), taken)
    if new_id in taken:
        raise ModelEditError(f"alternative id {new_id!r} already exists")
    out.alternatives.append(Alternative(id=new_id, name=name, metadata=dict(metadata or {})))
    return _rebuild(out)


def rename_alternative(project: Project, alt_id: str, name: str) -> Project:
    out = _copy(project)
    for a in out.alternatives:
        if a.id == alt_id:
            a.name = name
            return out
    raise UnknownReferenceError(f"unknown alternative {alt_id!r}")


def remove_alternative(project: Project, alt_id: str) -> Project:
    if alt_id not in project.alternative_ids():
        raise UnknownReferenceError(f"unknown alternative {alt_id!r}")
    out = _copy(project)
    out.alternatives = [a for a in out.alternatives if a.id != alt_id]
    out.performances = [p for p in out.performances if p.alternative_id != alt_id]
    _prune_uncertainty(out, alternatives={alt_id})
    _prune_judgements(out, items={alt_id})
    return out


def _prune_uncertainty(
    out: Project,
    alternatives: AbstractSet[str] = frozenset(),
    criteria: AbstractSet[str] = frozenset(),
) -> None:
    """Stated uncertainty goes with the alternatives and criteria it describes."""
    if out.smaa is None:
        return

    def kept(cell: CellRef | CellUncertainty) -> bool:
        return cell.alternative_id not in alternatives and cell.criterion_id not in criteria

    out.smaa.cells = [c for c in out.smaa.cells if kept(c)]
    for shared in out.smaa.shared_draws:
        shared.cells = [c for c in shared.cells if kept(c)]
    out.smaa.groups = [g for g in out.smaa.groups if g.parent_id not in criteria]
    for group in out.smaa.groups:
        group.intervals = {k: v for k, v in group.intervals.items() if k not in criteria}


def _prune_judgements(
    out: Project, items: AbstractSet[str], groups: AbstractSet[str] = frozenset()
) -> None:
    """AHP judgements go with the alternatives and criteria they name; a removed criterion's own
    group or leaf entry goes too. Nothing is ever added: validation asks for new judgements."""
    if out.ahp is None:
        return

    def kept(judgements: list[PairwiseJudgement]) -> list[PairwiseJudgement]:
        return [j for j in judgements if j.row not in items and j.column not in items]

    out.ahp.criteria = [g for g in out.ahp.criteria if g.parent_id not in groups]
    for group in out.ahp.criteria:
        group.judgements = kept(group.judgements)
    out.ahp.alternatives = [a for a in out.ahp.alternatives if a.criterion_id not in groups]
    for leaf in out.ahp.alternatives:
        leaf.judgements = kept(leaf.judgements)


# ---- criteria ---------------------------------------------------------------------------
def _renumber(out: Project, parent_id: str | None) -> None:
    kids = [n for n in out.criteria if n.parent_id == parent_id]
    kids.sort(key=lambda n: (n.order, out.criteria.index(n)))
    for i, n in enumerate(kids):
        n.order = i


def _clear_leaf_data(out: Project, node_id: str) -> None:
    for n in out.criteria:
        if n.id == node_id:
            n.scale = None
            n.value_function = None
    out.performances = [p for p in out.performances if p.criterion_id != node_id]
    for s in out.scenarios:
        s.value_function_overrides.pop(node_id, None)


def _leaf_has_data(project: Project, node_id: str) -> bool:
    node = next(n for n in project.criteria if n.id == node_id)
    return bool(
        node.scale
        or node.value_function
        or any(p.criterion_id == node_id for p in project.performances)
    )


def add_criterion(
    project: Project,
    name: str,
    parent_id: str | None = None,
    crit_id: str | None = None,
    scale: Scale | None = None,
    value_function: ValueFunctionSpec | None = None,
    position: int | None = None,
    discard_leaf_data: bool = False,
) -> Project:
    """Add a node. Adding a child to a leaf turns it into a parent, which removes the leaf's
    scale, value function and measurements - refused unless ``discard_leaf_data=True``."""
    out = _copy(project)
    taken = {n.id for n in out.criteria}
    if parent_id is not None:
        if parent_id not in taken:
            raise UnknownReferenceError(f"unknown parent criterion {parent_id!r}")
        has_children = any(n.parent_id == parent_id for n in out.criteria)
        if not has_children and _leaf_has_data(out, parent_id):
            if not discard_leaf_data:
                raise ModelEditError(
                    f"{parent_id!r} is a measured leaf; adding a child would discard its scale, "
                    "value function and measurements. Pass discard_leaf_data=True to confirm."
                )
            _clear_leaf_data(out, parent_id)
    new_id = crit_id or _unique_id(_slug(name), taken)
    if new_id in taken:
        raise ModelEditError(f"criterion id {new_id!r} already exists")
    siblings = [n for n in out.criteria if n.parent_id == parent_id]
    order = len(siblings) if position is None else position
    for n in siblings:
        if n.order >= order:
            n.order += 1
    out.criteria.append(
        CriterionNode(
            id=new_id,
            name=name,
            parent_id=parent_id,
            order=order,
            scale=scale,
            value_function=value_function,
        )
    )
    _renumber(out, parent_id)
    return _rebuild(out)


def rename_criterion(project: Project, crit_id: str, name: str) -> Project:
    out = _copy(project)
    for n in out.criteria:
        if n.id == crit_id:
            n.name = name
            return out
    raise UnknownReferenceError(f"unknown criterion {crit_id!r}")


def update_criterion(
    project: Project,
    crit_id: str,
    name: str | None = None,
    description: str | None = None,
) -> Project:
    """Change a criterion's display name and/or description; its id never changes."""
    project.tree().node(crit_id)
    out = _copy(project)
    node = next(n for n in out.criteria if n.id == crit_id)
    if name is not None:
        node.name = name
    if description is not None:
        node.description = description
    return out


def move_criterion(
    project: Project,
    crit_id: str,
    new_parent_id: str | None,
    position: int | None = None,
    discard_leaf_data: bool = False,
) -> Project:
    """Re-parent a criterion (and its subtree) or reorder it among its siblings.

    Swing ratings are relative to siblings, so when the parent changes the moved node's rating
    is dropped from every weight profile; validation then asks for a new one explicitly.
    """
    tree: CriterionTree = project.tree()
    node = tree.node(crit_id)
    if new_parent_id is not None:
        tree.node(new_parent_id)
        if new_parent_id in tree.subtree_ids(crit_id):
            raise ModelEditError("cannot move a criterion into itself or its own subtree")
    out = _copy(project)
    changed_parent = node.parent_id != new_parent_id
    if changed_parent and new_parent_id is not None:
        has_children = any(n.parent_id == new_parent_id for n in out.criteria)
        if not has_children and _leaf_has_data(out, new_parent_id):
            if not discard_leaf_data:
                raise ModelEditError(
                    f"{new_parent_id!r} is a measured leaf; moving a criterion under it would "
                    "discard its data. Pass discard_leaf_data=True to confirm."
                )
            _clear_leaf_data(out, new_parent_id)
    target = next(n for n in out.criteria if n.id == crit_id)
    old_parent = target.parent_id
    siblings = [n for n in out.criteria if n.parent_id == new_parent_id and n.id != crit_id]
    siblings.sort(key=lambda n: (n.order, out.criteria.index(n)))
    index = len(siblings) if position is None else max(0, min(position, len(siblings)))
    target.parent_id = new_parent_id
    ordered = [*siblings[:index], target, *siblings[index:]]
    for i, n in enumerate(ordered):
        n.order = i
    if changed_parent:
        _renumber(out, old_parent)
        for prof in out.weight_profiles:
            prof.judgements.pop(crit_id, None)
    return _rebuild(out)


def remove_criterion(project: Project, crit_id: str) -> Project:
    """Remove a criterion and its whole subtree, with their measurements, ratings and overrides.
    Remaining siblings are re-normalised automatically (weights are always derived)."""
    tree = project.tree()
    doomed = set(tree.subtree_ids(crit_id))
    parent = tree.node(crit_id).parent_id
    out = _copy(project)
    out.criteria = [n for n in out.criteria if n.id not in doomed]
    out.performances = [p for p in out.performances if p.criterion_id not in doomed]
    for prof in out.weight_profiles:
        prof.judgements = {k: v for k, v in prof.judgements.items() if k not in doomed}
    for s in out.scenarios:
        s.value_function_overrides = {
            k: v for k, v in s.value_function_overrides.items() if k not in doomed
        }
    _prune_uncertainty(out, criteria=doomed)
    _prune_judgements(out, items=doomed, groups=doomed)
    if out.requirements is not None:  # requirements go with the leaves they test
        kept = [r for r in out.requirements if r.criterion_id not in doomed]
        out.requirements = kept or None
    if out.promethee is not None:  # PROMETHEE's entries go with the leaves they describe
        out.promethee.criteria = [c for c in out.promethee.criteria if c.criterion_id not in doomed]
    _renumber(out, parent)
    return _rebuild(out)


def _require_leaf(project: Project, crit_id: str) -> None:
    tree = project.tree()
    tree.node(crit_id)
    if not tree.is_leaf(crit_id):
        raise ModelEditError(f"{crit_id!r} has children; only leaf criteria are measured")


def set_scale(project: Project, crit_id: str, scale: Scale) -> Project:
    _require_leaf(project, crit_id)
    out = _copy(project)
    next(n for n in out.criteria if n.id == crit_id).scale = scale
    return out


def set_value_function(project: Project, crit_id: str, vf: ValueFunctionSpec) -> Project:
    _require_leaf(project, crit_id)
    out = _copy(project)
    next(n for n in out.criteria if n.id == crit_id).value_function = vf
    return out


# ---- measurements and weights -----------------------------------------------------------
def set_performance(project: Project, alt_id: str, crit_id: str, value: Measurement) -> Project:
    if alt_id not in project.alternative_ids():
        raise UnknownReferenceError(f"unknown alternative {alt_id!r}")
    _require_leaf(project, crit_id)
    out = _copy(project)
    out.performances = [
        p
        for p in out.performances
        if not (p.alternative_id == alt_id and p.criterion_id == crit_id)
    ]
    out.performances.append(Performance(alternative_id=alt_id, criterion_id=crit_id, value=value))
    return out


def clear_performance(project: Project, alt_id: str, crit_id: str) -> Project:
    """Remove one entered measurement (the cell becomes missing again). Idempotent."""
    if alt_id not in project.alternative_ids():
        raise UnknownReferenceError(f"unknown alternative {alt_id!r}")
    project.tree().node(crit_id)
    out = _copy(project)
    out.performances = [
        p
        for p in out.performances
        if not (p.alternative_id == alt_id and p.criterion_id == crit_id)
    ]
    return out


def clear_criterion_performances(project: Project, crit_id: str) -> Project:
    """Remove every entered measurement of one criterion (e.g. after its scale type changed)."""
    project.tree().node(crit_id)
    out = _copy(project)
    out.performances = [p for p in out.performances if p.criterion_id != crit_id]
    return out


def clear_judgement(project: Project, node_id: str, profile_id: str | None = None) -> Project:
    """Remove a swing rating (it becomes missing again). Idempotent."""
    project.tree().node(node_id)
    out = _copy(project)
    _profile(out, profile_id).judgements.pop(node_id, None)
    return out


def set_judgement(
    project: Project, node_id: str, rating: float, profile_id: str | None = None
) -> Project:
    project.tree().node(node_id)
    out = _copy(project)
    prof = _profile(out, profile_id)
    prof.judgements[node_id] = rating
    return _rebuild(out)


def _profile(project: Project, profile_id: str | None) -> WeightProfile:
    if profile_id is None:
        if not project.weight_profiles:
            raise UnknownReferenceError("the project has no weight profile")
        return project.weight_profiles[0]
    for p in project.weight_profiles:
        if p.id == profile_id:
            return p
    raise UnknownReferenceError(f"unknown weight profile {profile_id!r}")


def add_weight_profile(project: Project, profile: WeightProfile) -> Project:
    if any(p.id == profile.id for p in project.weight_profiles):
        raise ModelEditError(f"weight profile {profile.id!r} already exists")
    out = _copy(project)
    out.weight_profiles.append(profile.model_copy(deep=True))
    return _rebuild(out)


def _managed_profile_ids(project: Project) -> set[str]:
    ids = {p.id for p in project.weight_profiles}
    if len(ids) != len(project.weight_profiles):
        raise ModelEditError("weight-profile ids are ambiguous; repair duplicate ids first")
    return ids


def _profile_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ModelEditError("a weight-profile name cannot be blank")
    return name


def create_weight_profile(project: Project, name: str, profile_id: str | None = None) -> Project:
    """Create an incomplete profile; never impute another decision maker's ratings."""
    name = _profile_name(name)
    taken = _managed_profile_ids(project)
    new_id = profile_id or _unique_id(_slug(name), taken)
    return add_weight_profile(project, WeightProfile(id=new_id, name=name))


def duplicate_weight_profile(
    project: Project, profile_id: str, name: str, new_profile_id: str | None = None
) -> Project:
    _managed_profile_ids(project)
    source = _profile(project, profile_id)
    name = _profile_name(name)
    new_id = new_profile_id or _unique_id(_slug(name), _managed_profile_ids(project))
    clone = source.model_copy(deep=True, update={"id": new_id, "name": name})
    return add_weight_profile(project, clone)


def rename_weight_profile(project: Project, profile_id: str, name: str) -> Project:
    _managed_profile_ids(project)
    _profile(project, profile_id)
    out = _copy(project)
    _profile(out, profile_id).name = _profile_name(name)
    return _rebuild(out)


def weight_profile_references(project: Project, profile_id: str) -> list[str]:
    """Include effective automatic references, so deleting the first profile cannot silently
    change saved analyses/scenarios. This inspects references only, never evaluates a model.
    """
    _managed_profile_ids(project)
    _profile(project, profile_id)
    first = project.weight_profiles[0].id
    refs = [
        f"scenarios[{s.id}].weight_profile_id"
        for s in project.scenarios
        if (s.weight_profile_id or first) == profile_id
    ]
    scenario = next((s for s in project.scenarios if s.id == project.analysis.scenario_id), None)
    resolved = project.analysis.weight_profile_id or (
        scenario.weight_profile_id if scenario and scenario.weight_profile_id else first
    )
    if resolved == profile_id:
        refs.append("analysis.weight_profile_id")
    return refs


def remove_weight_profile(
    project: Project, profile_id: str, replacement_profile_id: str | None = None
) -> Project:
    _managed_profile_ids(project)
    _profile(project, profile_id)
    if len(project.weight_profiles) <= 1:
        raise ModelEditError("the last weight profile cannot be removed")
    if replacement_profile_id is not None:
        if replacement_profile_id == profile_id:
            raise ModelEditError("a replacement must be a different weight profile")
        _profile(project, replacement_profile_id)
    refs = weight_profile_references(project, profile_id)
    if refs and replacement_profile_id is None:
        raise ModelEditError(
            "choose an explicit replacement for referenced weight profile: " + ", ".join(refs)
        )
    out = _copy(project)
    for scenario in out.scenarios:
        if f"scenarios[{scenario.id}].weight_profile_id" in refs:
            scenario.weight_profile_id = replacement_profile_id
    if "analysis.weight_profile_id" in refs:
        out.analysis.weight_profile_id = replacement_profile_id
    out.weight_profiles = [p for p in out.weight_profiles if p.id != profile_id]
    return _rebuild(out)


def set_default_weight_profile(project: Project, profile_id: str | None) -> Project:
    _managed_profile_ids(project)
    if profile_id is not None:
        _profile(project, profile_id)
    out = _copy(project)
    out.analysis.weight_profile_id = profile_id
    return _rebuild(out)


def add_scenario(project: Project, scenario: Scenario) -> Project:
    if any(s.id == scenario.id for s in project.scenarios):
        raise ModelEditError(f"scenario {scenario.id!r} already exists")
    out = _copy(project)
    out.scenarios.append(scenario.model_copy(deep=True))
    return _rebuild(out)


# ---- scenario differences (shared scales and measurements always remain in the base) --------
def _scenario(project: Project, scenario_id: str) -> Scenario:
    ids = [s.id for s in project.scenarios]
    if len(set(ids)) != len(ids):
        raise ModelEditError("scenario ids are ambiguous; repair duplicates first")
    for scenario in project.scenarios:
        if scenario.id == scenario_id:
            return scenario
    raise UnknownReferenceError(f"unknown scenario {scenario_id!r}")


def create_scenario(project: Project, name: str, scenario_id: str | None = None) -> Project:
    name = _profile_name(name)
    new_id = scenario_id or _unique_id(_slug(name), {s.id for s in project.scenarios})
    return add_scenario(project, Scenario(id=new_id, name=name))


def duplicate_scenario(
    project: Project, scenario_id: str, name: str, new_scenario_id: str | None = None
) -> Project:
    source = _scenario(project, scenario_id)
    new_id = new_scenario_id or _unique_id(_slug(name), {s.id for s in project.scenarios})
    return add_scenario(
        project, source.model_copy(deep=True, update={"id": new_id, "name": _profile_name(name)})
    )


def rename_scenario(project: Project, scenario_id: str, name: str) -> Project:
    _scenario(project, scenario_id)
    out = _copy(project)
    _scenario(out, scenario_id).name = _profile_name(name)
    return _rebuild(out)


def remove_scenario(
    project: Project,
    scenario_id: str,
    *,
    repair_default: bool = False,
    replacement_scenario_id: str | None = None,
) -> Project:
    _scenario(project, scenario_id)
    if replacement_scenario_id is not None:
        if replacement_scenario_id == scenario_id:
            raise ModelEditError("replacement must be a different scenario or Base model")
        _scenario(project, replacement_scenario_id)
    if project.analysis.scenario_id == scenario_id and not repair_default:
        raise ModelEditError("explicitly repair the saved default before deleting this scenario")
    out = _copy(project)
    if out.analysis.scenario_id == scenario_id:
        out.analysis.scenario_id = replacement_scenario_id
    out.scenarios = [s for s in out.scenarios if s.id != scenario_id]
    return _rebuild(out)


def set_scenario_profile(project: Project, scenario_id: str, profile_id: str | None) -> Project:
    _scenario(project, scenario_id)
    if profile_id is not None:
        _managed_profile_ids(project)
        profile = _profile(project, profile_id)
        if profile.method != "swing":
            raise ModelEditError("scenario profiles must use supported swing weighting")
    out = _copy(project)
    _scenario(out, scenario_id).weight_profile_id = profile_id
    return _rebuild(out)


def set_scenario_override(
    project: Project, scenario_id: str, criterion_id: str, value_function: ValueFunctionSpec
) -> Project:
    from mcda_studio.domain.validation import validate_leaf_model

    _scenario(project, scenario_id)
    _require_leaf(project, criterion_id)
    node = project.tree().node(criterion_id)
    report = validate_leaf_model(node, value_function, [], {})
    # Definition validation does not require missing local readings; analysis resolves those later.
    if not report.ok:
        raise ModelEditError("; ".join(f"{i.code}: {i.message}" for i in report.errors))
    out = _copy(project)
    _scenario(out, scenario_id).value_function_overrides[criterion_id] = value_function.model_copy(
        deep=True
    )
    return _rebuild(out)


def clear_scenario_override(project: Project, scenario_id: str, criterion_id: str) -> Project:
    _scenario(project, scenario_id)
    _require_leaf(project, criterion_id)
    out = _copy(project)
    _scenario(out, scenario_id).value_function_overrides.pop(criterion_id, None)
    return _rebuild(out)


def set_default_scenario(project: Project, scenario_id: str | None) -> Project:
    if scenario_id is not None:
        _scenario(project, scenario_id)
    out = _copy(project)
    out.analysis.scenario_id = scenario_id
    return _rebuild(out)


# ---- value-based sorting and the saved method ------------------------------------------------
def set_sorting_model(project: Project, model: SortingModel) -> Project:
    """Replace the whole sorting section; its rules are validation issues, so drafts save."""
    out = _copy(project)
    out.sorting = model.model_copy(deep=True)
    return _rebuild(out)


def clear_sorting_model(project: Project) -> Project:
    """Remove the sorting section; a project without other sections is version 1 again."""
    out = _copy(project)
    out.sorting = None
    return _rebuild(out)


def sorting_classes(names_and_boundaries: list[tuple[str, float | None]]) -> list[SortingClass]:
    """Classes best first, with IDs derived from their names as for alternatives."""
    taken: set[str] = set()
    out: list[SortingClass] = []
    for name, boundary in names_and_boundaries:
        class_id = _unique_id(_slug(name), taken)
        taken.add(class_id)
        out.append(SortingClass(id=class_id, name=name.strip(), lower_boundary=boundary))
    return out


def set_analysis_method(project: Project, method: str) -> Project:
    """Make ``method`` the saved default. The saved parameters belonged to the previous method, so
    changing the method clears them: one method's parameters are never applied to another."""
    get_method(method)  # an unknown method is an error, never a silent default
    out = _copy(project)
    if out.analysis.method != method:
        out.analysis.method = method
        out.analysis.parameters = {}
    return _rebuild(out)


# ---- stated uncertainty (SMAA-2) -------------------------------------------------------------
def set_smaa_model(project: Project, model: SmaaModel) -> Project:
    """Replace the whole uncertainty section; its rules are validation issues, so drafts save."""
    out = _copy(project)
    out.smaa = model.model_copy(deep=True)
    return _rebuild(out)


def clear_smaa_model(project: Project) -> Project:
    """Remove the uncertainty section; the project returns to the lowest version it needs."""
    out = _copy(project)
    out.smaa = None
    return _rebuild(out)


# ---- PROMETHEE II inputs ---------------------------------------------------------------------
def set_promethee_model(project: Project, model: PrometheeModel) -> Project:
    """Replace the whole PROMETHEE section; its rules are validation issues, so drafts save."""
    out = _copy(project)
    out.promethee = model.model_copy(deep=True)
    return _rebuild(out)


def clear_promethee_model(project: Project) -> Project:
    """Remove the PROMETHEE section; the project returns to the lowest version it needs."""
    out = _copy(project)
    out.promethee = None
    return _rebuild(out)


# ---- AHP judgements ------------------------------------------------------------------------
def set_ahp_model(project: Project, model: AhpModel) -> Project:
    """Replace the whole AHP section; its rules are validation issues, so drafts save."""
    out = _copy(project)
    out.ahp = model.model_copy(deep=True)
    return _rebuild(out)


def clear_ahp_model(project: Project) -> Project:
    """Remove the AHP section; the project returns to the lowest version it needs."""
    out = _copy(project)
    out.ahp = None
    return _rebuild(out)


# ---- feasibility requirements ------------------------------------------------------------------
def set_requirements(project: Project, requirements: list[AnyRequirement]) -> Project:
    """Replace the whole requirements list; an empty list removes it. Its rules are validation
    issues, so drafts save."""
    out = _copy(project)
    out.requirements = [r.model_copy(deep=True) for r in requirements] or None
    return _rebuild(out)


def clear_requirements(project: Project) -> Project:
    """Remove every requirement; the project returns to the lowest version it needs."""
    out = _copy(project)
    out.requirements = None
    return _rebuild(out)
