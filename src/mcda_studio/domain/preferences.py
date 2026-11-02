"""Preference information: swing-weight judgements, scenarios and analysis configuration."""

import math
from collections.abc import Mapping
from typing import Any

from pydantic import Field

from mcda_studio.domain.common import DomainModel, FiniteFloat, Id, Issue, Severity
from mcda_studio.domain.criteria import CriterionTree, ValueFunctionSpec


class WeightProfile(DomainModel):
    """Raw swing ratings, one per criterion node, relative to that node's siblings.

    A rating expresses the importance of the swing from worst to best *over the scale range
    in use* - not abstract importance. Ratings need not sum to anything; they are normalised
    within each sibling group. An only child needs no rating (its local weight is 1).
    """

    id: Id
    name: str = Field(min_length=1)
    method: str = "swing"
    judgements: dict[Id, FiniteFloat] = Field(default_factory=dict)


class Scenario(DomainModel):
    """A named variation of the base model: another weight profile and/or other value functions."""

    id: Id
    name: str = Field(min_length=1)
    weight_profile_id: Id | None = None
    value_function_overrides: dict[Id, ValueFunctionSpec] = Field(default_factory=dict)


class AnalysisConfiguration(DomainModel):
    method: str = "mavt"
    weight_profile_id: Id | None = None  # None -> scenario's profile, else the first profile
    scenario_id: Id | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


def check_judgements(
    tree: CriterionTree, judgements: Mapping[str, float], path: str = ""
) -> list[Issue]:
    """Sibling-group rules shared by validation and weighting."""
    issues: list[Issue] = []
    prefix = f"{path}." if path else ""

    def err(code: str, message: str, where: str) -> None:
        issues.append(Issue(severity=Severity.ERROR, code=code, message=message, path=where))

    for key in judgements:
        if key not in tree:
            err(
                "UNKNOWN_JUDGEMENT_NODE",
                f"judgement refers to unknown criterion {key!r}",
                f"{prefix}judgements.{key}",
            )
    parents: list[str | None] = [None, *[i for i in tree.all_ids() if not tree.is_leaf(i)]]
    for pid in parents:
        kids = tree.child_ids(pid)
        if not kids:
            continue
        group = "<top level>" if pid is None else repr(pid)
        ratings: list[float] = []
        group_ok = True
        for kid in kids:
            raw = judgements.get(kid)
            where = f"{prefix}judgements.{kid}"
            if raw is None:
                if len(kids) == 1:
                    ratings.append(1.0)  # only child: weight is necessarily 1
                    continue
                err(
                    "MISSING_JUDGEMENT",
                    f"no swing rating for {kid!r} among siblings of {group}",
                    where,
                )
                group_ok = False
                continue
            if not math.isfinite(raw) or raw < 0:
                err("INVALID_JUDGEMENT", f"swing rating {raw!r} must be finite and >= 0", where)
                group_ok = False
                continue
            ratings.append(float(raw))
        if group_ok and math.fsum(ratings) <= 0.0:
            err(
                "ZERO_SUM_JUDGEMENTS",
                f"all swing ratings under {group} are zero",
                f"{prefix}judgements",
            )
    return issues
