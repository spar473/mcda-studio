"""SMAA-2's own parameters and rules for the stated uncertainty (design note §1 and §2)."""

import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from mcda_studio.domain.common import Issue, Severity
from mcda_studio.domain.criteria import CriterionTree, QualitativeValueFunction, ValueFunctionSpec
from mcda_studio.domain.errors import McdaError
from mcda_studio.domain.measurements import effective_domain
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.uncertainty import (
    CategoricalDistribution,
    DiscreteDistribution,
    TriangularDistribution,
    UniformDistribution,
)
from mcda_studio.methods.sorting.classes import check_sorting

PROBABILITY_TOL = 1e-9
_LEAF_IN_PATH = re.compile(r"\[([^\]]+)\]$")


class SmaaParameters(BaseModel):
    # Unknown keys are reported by validation as UNKNOWN_PARAMETER warnings and ignored here.
    model_config = ConfigDict(extra="ignore", frozen=True)

    #: which stated inputs vary in this run
    uncertainty: Literal["performance", "preference", "combined"] = "combined"
    samples: StrictInt = Field(default=10_000, ge=1_000, le=100_000)
    seed: StrictInt = Field(default=0, ge=0)
    confidence: float = Field(default=0.95, ge=0.8, le=0.999)


def smaa_parameters(configuration: AnalysisConfiguration) -> SmaaParameters:
    """Parsed parameters; validation has already refused invalid ones."""
    return SmaaParameters.model_validate(configuration.parameters)


def group_children(tree: CriterionTree, parent_id: str | None) -> list[str]:
    return tree.child_ids(parent_id)


def effective_function(
    project: Project, configuration: AnalysisConfiguration, leaf: str
) -> ValueFunctionSpec | None:
    scenario = project.resolve_scenario(configuration)
    node = project.tree().node(leaf)
    if scenario and leaf in scenario.value_function_overrides:
        return scenario.value_function_overrides[leaf]
    return node.value_function


def _probabilities_issue(probabilities: list[float]) -> str | None:
    if not probabilities:
        return "lists no outcomes"
    if any(p < 0 for p in probabilities):
        return "has a negative probability"
    if abs(math.fsum(probabilities) - 1.0) > PROBABILITY_TOL:
        return f"has probabilities summing to {math.fsum(probabilities)!r}, not 1"
    return None


def check_smaa(
    project: Project, configuration: AnalysisConfiguration, value_model_issues: list[Issue]
) -> list[Issue]:
    """The rules for the stated uncertainty, after MAVT's checks of the deterministic model."""
    issues: list[Issue] = []

    def add(code: str, message: str, path: str, severity: Severity = Severity.ERROR) -> None:
        issues.append(Issue(severity=severity, code=code, message=message, path=path))

    try:
        params: SmaaParameters | None = smaa_parameters(configuration)
    except ValidationError:
        params = None  # reported by the parameter checks
    model = project.smaa
    run = params.uncertainty if params else "combined"
    if model is None:
        add(
            "NOTHING_UNCERTAIN",
            "SMAA-2 needs stated uncertainty; the project states none",
            "smaa",
        )
        return issues
    if model.dependence != "independent":
        add(
            "UNSUPPORTED_DEPENDENCE",
            f"dependence {model.dependence!r} is not supported: inputs are independent, except "
            "cells listed together in a shared draw",
            "smaa.dependence",
        )
    try:
        tree = project.tree()
        project.resolve_scenario(configuration)
    except McdaError:
        return issues  # the value-model checks report a broken tree or scenario
    alternatives = set(project.alternative_ids())
    leaves = set(tree.leaves())
    local_anchored = {
        m.group(1)
        for i in value_model_issues
        if i.code == "LOCAL_ANCHORS" and (m := _LEAF_IN_PATH.search(i.path))
    }

    seen_cells: set[tuple[str, str]] = set()
    for cell in model.cells:
        key = (cell.alternative_id, cell.criterion_id)
        where = f"smaa.cells[{cell.alternative_id},{cell.criterion_id}]"
        if cell.alternative_id not in alternatives or cell.criterion_id not in leaves:
            add(
                "UNKNOWN_UNCERTAIN_CELL",
                f"{cell.alternative_id!r} on {cell.criterion_id!r} is not an alternative and a "
                "leaf criterion of this project",
                where,
            )
            continue
        if key in seen_cells:
            add("DUPLICATE_UNCERTAIN_CELL", "this cell has more than one distribution", where)
            continue
        seen_cells.add(key)
        if cell.criterion_id in local_anchored:
            add(
                "SMAA_LOCAL_ANCHORS_UNCERTAIN",
                f"{cell.criterion_id!r} uses local anchors, which would move with every draw; "
                "use fixed anchors for a criterion with uncertain measurements",
                where,
            )
            continue
        node = tree.node(cell.criterion_id)
        vf = effective_function(project, configuration, cell.criterion_id)
        if node.scale is None or vf is None:
            continue  # the value-model checks report the missing scale or function
        dist = cell.distribution
        labelled = isinstance(vf, QualitativeValueFunction)
        if labelled != isinstance(dist, CategoricalDistribution):
            add(
                "DISTRIBUTION_SCALE_MISMATCH",
                "a labelled scale needs a categorical distribution, and a numeric scale a "
                "uniform, triangular or discrete one",
                where,
            )
            continue
        problem: str | None = None
        support: list[float] = []
        if isinstance(dist, UniformDistribution):
            if not dist.lower < dist.upper:
                problem = "needs lower < upper"
            support = [dist.lower, dist.upper]
        elif isinstance(dist, TriangularDistribution):
            if not (dist.lower <= dist.mode <= dist.upper and dist.lower < dist.upper):
                problem = "needs lower <= mode <= upper and lower < upper"
            support = [dist.lower, dist.upper]
        elif isinstance(dist, DiscreteDistribution):
            if len(dist.values) != len(dist.probabilities):
                problem = "needs one probability per value"
            elif len(set(dist.values)) != len(dist.values):
                problem = "lists a value twice"
            else:
                problem = _probabilities_issue(dist.probabilities)
            support = list(dist.values)
        else:
            if len(dist.labels) != len(dist.probabilities):
                problem = "needs one probability per label"
            elif len(set(dist.labels)) != len(dist.labels):
                problem = "lists a label twice"
            elif unknown := [x for x in dist.labels if x not in node.scale.labels]:
                problem = f"lists labels that are not on the scale: {unknown}"
            else:
                problem = _probabilities_issue(dist.probabilities)
        if problem:
            add("INVALID_DISTRIBUTION", f"the {dist.kind} distribution {problem}", where)
            continue
        domain = effective_domain(node.scale, vf, [])
        if (
            support
            and domain is not None
            and (min(support) < domain.lower or max(support) > domain.upper)
        ):
            add(
                "DISTRIBUTION_OUTSIDE_DOMAIN",
                f"the distribution reaches outside the value-function domain "
                f"[{domain.lower}, {domain.upper}]; it is never clamped",
                where,
            )

    parents = {None, *(i for i in tree.all_ids() if not tree.is_leaf(i))}
    seen_groups: set[str | None] = set()
    for group in model.groups:
        label = "top" if group.parent_id is None else group.parent_id
        where = f"smaa.groups[{label}]"
        if group.parent_id not in parents:
            add(
                "UNKNOWN_UNCERTAIN_GROUP",
                f"{group.parent_id!r} is not a criterion with children",
                where,
            )
            continue
        if group.parent_id in seen_groups:
            add("DUPLICATE_UNCERTAIN_GROUP", "this group has more than one entry", where)
            continue
        seen_groups.add(group.parent_id)
        children = group_children(tree, group.parent_id)
        if len(children) < 2:
            add(
                "INVALID_GROUP_UNCERTAINTY",
                "a group with one child always has local weight 1, so it cannot vary",
                where,
            )
            continue
        if group.kind == "unknown":
            if group.intervals:
                add(
                    "UNEXPECTED_RATING_INTERVALS",
                    "an unknown group draws uniform local weights; it takes no rating intervals",
                    where,
                )
            continue
        for child in children:
            interval = group.intervals.get(child)
            if interval is None:
                add("MISSING_RATING_INTERVAL", f"no rating interval for {child!r}", where)
            elif not 0.0 <= interval[0] <= interval[1]:
                add(
                    "INVALID_RATING_INTERVAL",
                    f"the interval for {child!r} needs 0 <= lower <= upper",
                    f"{where}.intervals.{child}",
                )
        for extra in sorted(set(group.intervals) - set(children)):
            add(
                "UNKNOWN_RATING_INTERVAL",
                f"{extra!r} is not a child of this group",
                f"{where}.intervals.{extra}",
            )
        if group.intervals and all(hi == 0.0 for _, hi in group.intervals.values()):
            add(
                "ZERO_RATING_INTERVALS",
                "every rating interval is zero, so every draw of this group sums to zero",
                where,
            )

    shared_ids: set[str] = set()
    in_shared: set[tuple[str, str]] = set()
    for shared in model.shared_draws:
        where = f"smaa.shared_draws[{shared.id}]"
        if shared.id in shared_ids:
            add("DUPLICATE_SHARED_DRAW", "this shared draw id is used twice", where)
        shared_ids.add(shared.id)
        if len(shared.cells) < 2:
            add("INVALID_SHARED_DRAW", "a shared draw needs at least two cells", where)
        for ref in shared.cells:
            key = (ref.alternative_id, ref.criterion_id)
            if key not in seen_cells:
                add(
                    "UNKNOWN_SHARED_CELL",
                    f"{ref.alternative_id!r} on {ref.criterion_id!r} has no stated distribution",
                    where,
                )
            elif key in in_shared:
                add("DUPLICATE_SHARED_CELL", "a cell can be in one shared draw only", where)
            in_shared.add(key)

    varies_cells = run in {"performance", "combined"} and bool(model.cells)
    varies_groups = run in {"preference", "combined"} and bool(model.groups)
    if not (varies_cells or varies_groups):
        add(
            "NOTHING_UNCERTAIN",
            f"nothing stated varies in a {run} run",
            "configuration.parameters.uncertainty",
        )
    if project.sorting is not None:  # class acceptability needs valid classes
        issues.extend(i for i in check_sorting(project, []) if i.code != "SORTING_LOCAL_ANCHORS")
    return issues
