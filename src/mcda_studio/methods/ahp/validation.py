"""AHP's own parameters and rules for its section (design note §5). MAVT's checks do not apply."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from mcda_studio.domain.common import Issue, Severity
from mcda_studio.domain.criteria import CriterionTree
from mcda_studio.domain.errors import ModelStructureError
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.methods.ahp.matrix import matrix_issues


class AhpParameters(BaseModel):
    # Unknown keys are reported by validation as UNKNOWN_PARAMETER warnings and ignored here.
    model_config = ConfigDict(extra="ignore", frozen=True)

    synthesis: Literal["distributive", "ideal"] = "distributive"


def ahp_parameters(configuration: AnalysisConfiguration) -> AhpParameters:
    """Parsed parameters; validation has already refused invalid ones."""
    return AhpParameters.model_validate(configuration.parameters)


def criteria_groups(tree: CriterionTree) -> list[str | None]:
    """The sibling groups that are judged: the top level and every node, in tree order, with two
    or more children. A single child always has local priority 1 and takes no judgements."""
    parents: list[str | None] = [None, *(i for i in tree.all_ids() if not tree.is_leaf(i))]
    return [p for p in parents if len(tree.child_ids(p)) >= 2]


def group_label(parent_id: str | None) -> str:
    return "top" if parent_id is None else parent_id


def check_ahp(project: Project) -> list[Issue]:
    """The rules for the section, after the method-independent structural checks."""
    issues: list[Issue] = []

    def add(code: str, message: str, path: str) -> None:
        issues.append(Issue(severity=Severity.ERROR, code=code, message=message, path=path))

    model = project.ahp
    if model is None:
        add(
            "AHP_NOT_STATED",
            "AHP needs pairwise judgements for the criteria and, on every leaf, for the "
            "alternatives; the project states none",
            "ahp",
        )
        return issues
    alternatives = project.alternative_ids()
    if len(alternatives) < 2:
        add(
            "AHP_TOO_FEW_ALTERNATIVES",
            "AHP compares alternatives in pairs: it needs at least two",
            "alternatives",
        )
    try:
        tree = project.tree()
    except ModelStructureError:
        return issues  # the structural checks report the broken tree
    groups = criteria_groups(tree)
    stated_groups: set[str | None] = set()
    for entry in model.criteria:
        where = f"ahp.criteria[{group_label(entry.parent_id)}]"
        if entry.parent_id not in groups:
            add(
                "UNKNOWN_AHP_GROUP",
                f"{entry.parent_id!r} is not a criterion with two or more children",
                where,
            )
            continue
        if entry.parent_id in stated_groups:
            add("DUPLICATE_AHP_GROUP", "this group has more than one entry", where)
            continue
        stated_groups.add(entry.parent_id)
        issues.extend(matrix_issues(tree.child_ids(entry.parent_id), entry.judgements, where))
    for parent in groups:
        if parent not in stated_groups:
            add(
                "AHP_JUDGEMENT_MISSING",
                "the children of this group are not judged against each other",
                f"ahp.criteria[{group_label(parent)}]",
            )
    leaves = tree.leaves()
    stated_leaves: set[str] = set()
    for alt_entry in model.alternatives:
        where = f"ahp.alternatives[{alt_entry.criterion_id}]"
        if alt_entry.criterion_id not in leaves:
            add("UNKNOWN_AHP_GROUP", f"{alt_entry.criterion_id!r} is not a leaf criterion", where)
            continue
        if alt_entry.criterion_id in stated_leaves:
            add("DUPLICATE_AHP_GROUP", "this leaf has more than one entry", where)
            continue
        stated_leaves.add(alt_entry.criterion_id)
        issues.extend(matrix_issues(alternatives, alt_entry.judgements, where))
    for leaf in leaves:
        if leaf not in stated_leaves:
            add(
                "AHP_JUDGEMENT_MISSING",
                "the alternatives are not judged against each other on this leaf",
                f"ahp.alternatives[{leaf}]",
            )
    return issues
