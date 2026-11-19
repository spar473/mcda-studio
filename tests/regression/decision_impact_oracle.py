"""Independent plain-Python oracle for decision impact. It never imports mcda_studio.

From the raw project JSON alone, for every qualitative or ordinal cell of every alternative, it
rewrites that one measurement to each other label, recomputes every alternative's overall value from
scratch (through ``sorting_oracle``, itself plain Python), then derives competition ranks, the
leader set and classes with its own code. Nothing is shared with the engine: no numpy, no
incremental update of one row. The service must agree to 1e-12 on values and exactly on ranks,
classes, leaders and the label lists.
"""

import copy
from typing import Any

import sorting_oracle

TOL = 1e-12
Project = dict[str, Any]


def competition_ranks(values: dict[str, float]) -> dict[str, int]:
    return {
        a: 1 + sum(1 for other in values.values() if other > v + TOL) for a, v in values.items()
    }


def leaders(ranks: dict[str, int]) -> set[str]:
    return {a for a, r in ranks.items() if r == 1}


def class_or_none(value: float, project: Project) -> str | None:
    if not project.get("sorting"):
        return None
    return sorting_oracle.class_of(value, project)


def scored_labelled_cells(
    project: Project, scenario_id: str | None, profile_id: str | None
) -> list[tuple[str, str]]:
    """(alternative, leaf) of every entered label on a positive-weight qualitative leaf."""
    local = sorting_oracle.local_weights(
        project, sorting_oracle._profile(project, scenario_id, profile_id)
    )
    weights = sorting_oracle.global_weights(project, local)
    nodes = {n["id"]: n for n in project["criteria"]}
    measured = {
        (p["alternative_id"], p["criterion_id"]): p["value"] for p in project["performances"]
    }
    cells = []
    for leaf, weight in weights.items():
        function = sorting_oracle._function(project, nodes[leaf], scenario_id)
        if weight > 0 and function["kind"] == "qualitative":
            for alt in (a["id"] for a in project["alternatives"]):
                if isinstance(measured.get((alt, leaf)), str):
                    cells.append((alt, leaf))
    return cells


def impacts(
    project: Project, scenario_id: str | None = None, profile_id: str | None = None
) -> dict[tuple[str, str], dict[str, Any]]:
    base = sorting_oracle.overall_values(project, scenario_id, profile_id)
    base_ranks = competition_ranks(base)
    base_leaders = leaders(base_ranks)
    base_class = {a: class_or_none(v, project) for a, v in base.items()}
    nodes = {n["id"]: n for n in project["criteria"]}
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for alt, leaf in scored_labelled_cells(project, scenario_id, profile_id):
        labels = nodes[leaf]["scale"]["labels"]
        current = next(
            p["value"]
            for p in project["performances"]
            if p["alternative_id"] == alt and p["criterion_id"] == leaf
        )
        effects = {}
        for label in labels:
            if label == current:
                continue
            trial = copy.deepcopy(project)
            for p in trial["performances"]:
                if p["alternative_id"] == alt and p["criterion_id"] == leaf:
                    p["value"] = label
            values = sorting_oracle.overall_values(trial, scenario_id, profile_id)
            ranks = competition_ranks(values)
            changes = []
            if ranks[alt] != base_ranks[alt]:
                changes.append("target_rank")
            if any(ranks[a] != base_ranks[a] for a in values if a != alt):
                changes.append("other_rank")
            if leaders(ranks) != base_leaders:
                changes.append("leader")
            if class_or_none(values[alt], trial) != base_class[alt]:
                changes.append("target_class")
            effects[label] = {
                "value": values[alt],
                "target_rank": ranks[alt],
                "target_class": class_or_none(values[alt], trial),
                "leaders": sorted(leaders(ranks)),
                "changes": changes,
                "levels": labels.index(label) - labels.index(current),
            }
        moving = {k: e for k, e in effects.items() if e["changes"]}
        nearest = min((abs(e["levels"]) for e in moving.values()), default=None)
        result[(alt, leaf)] = {
            "effects": effects,
            "smallest": sorted(
                (k for k, e in moving.items() if abs(e["levels"]) == nearest), key=labels.index
            ),
            "decisive": any(
                "leader" in e["changes"] or "target_class" in e["changes"] for e in effects.values()
            ),
            "rank": any(
                "target_rank" in e["changes"] or "other_rank" in e["changes"]
                for e in effects.values()
            ),
        }
    return result
