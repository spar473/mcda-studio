"""Independent plain-Python oracle for value-based sorting. It never imports mcda_studio.

It reads a project file as plain JSON and recomputes from the specification alone: additive
values (linear functions on fixed anchors, piecewise-linear, qualitative and direct-rating
functions; hierarchical swing weights; profiles and value-function scenarios), classes, distance to
the nearest boundary, the audit sample, and the exact class-change weights of one-way sensitivity.
No numpy, no tree classes, no shared code with the engine.
"""

import hashlib
import json
import math
from pathlib import Path
from typing import Any

TOL = 1e-12
Project = dict[str, Any]


def load(path: Path) -> Project:
    project: Project = json.loads(path.read_text(encoding="utf-8"))
    return project


def _profile(project: Project, scenario_id: str | None, profile_id: str | None) -> dict[str, float]:
    scenario = next((s for s in project["scenarios"] if s["id"] == scenario_id), None)
    wanted = profile_id or (scenario["weight_profile_id"] if scenario else None)
    profiles = project["weight_profiles"]
    chosen = next(p for p in profiles if p["id"] == wanted) if wanted else profiles[0]
    return dict(chosen["judgements"])


def _function(project: Project, leaf: dict[str, Any], scenario_id: str | None) -> dict[str, Any]:
    scenario = next((s for s in project["scenarios"] if s["id"] == scenario_id), None)
    overrides = scenario["value_function_overrides"] if scenario else {}
    function: dict[str, Any] = overrides.get(leaf["id"], leaf["value_function"])
    return function


def partial_value(function: dict[str, Any], scale: dict[str, Any], x: Any) -> float:
    kind = function["kind"]
    if kind == "qualitative":
        return float(function["mapping"][x])
    if kind == "direct_rating":
        lo, hi = function["min_rating"], function["max_rating"]
        return (x - lo) / (hi - lo)
    if kind == "linear":
        if scale["anchor_mode"] != "fixed":
            raise ValueError("the oracle covers fixed anchors only")
        lo, hi = scale["lower"], scale["upper"]
        rising = (x - lo) / (hi - lo)
        return rising if function["direction"] == "increasing" else 1.0 - rising
    if kind == "piecewise_linear":
        points = sorted((p["x"], p["value"]) for p in function["points"])
        for (x0, v0), (x1, v1) in zip(points, points[1:], strict=False):
            if x0 <= x <= x1:
                return v0 + (v1 - v0) * (x - x0) / (x1 - x0)
        raise ValueError(f"{x} is outside the piecewise domain")
    raise ValueError(f"unknown function kind {kind}")


def local_weights(project: Project, judgements: dict[str, float]) -> dict[str, float]:
    """Swing ratings normalised within each sibling group; an only child has weight 1."""
    out: dict[str, float] = {}
    for node in project["criteria"]:
        siblings = [n["id"] for n in project["criteria"] if n["parent_id"] == node["parent_id"]]
        if len(siblings) == 1:
            out[node["id"]] = 1.0
        else:
            out[node["id"]] = judgements[node["id"]] / sum(judgements[s] for s in siblings)
    return out


def global_weights(project: Project, local: dict[str, float]) -> dict[str, float]:
    parents = {n["id"]: n["parent_id"] for n in project["criteria"]}
    leaves = [n["id"] for n in project["criteria"] if n["id"] not in parents.values()]
    out: dict[str, float] = {}
    for leaf in leaves:
        weight, node = 1.0, leaf
        while node is not None:
            weight *= local[node]
            node = parents[node]
        out[leaf] = weight
    return out


def overall_values(
    project: Project,
    scenario_id: str | None = None,
    profile_id: str | None = None,
    local: dict[str, float] | None = None,
) -> dict[str, float]:
    local = local or local_weights(project, _profile(project, scenario_id, profile_id))
    weights = global_weights(project, local)
    nodes = {n["id"]: n for n in project["criteria"]}
    measured = {
        (p["alternative_id"], p["criterion_id"]): p["value"] for p in project["performances"]
    }
    out: dict[str, float] = {}
    for alt in (a["id"] for a in project["alternatives"]):
        terms = []
        for leaf, weight in weights.items():
            node = nodes[leaf]
            function = _function(project, node, scenario_id)
            terms.append(weight * partial_value(function, node["scale"], measured[(alt, leaf)]))
        out[alt] = math.fsum(terms)
    return out


def boundaries(project: Project) -> list[tuple[str, float]]:
    """(class id, lower boundary) for every class but the lowest, best first."""
    return [(c["id"], c["lower_boundary"]) for c in project["sorting"]["classes"][:-1]]


def class_of(value: float, project: Project) -> str:
    classes = [c["id"] for c in project["sorting"]["classes"]]
    for class_id, boundary in boundaries(project):
        if value >= boundary - TOL:  # on a boundary, within the tolerance: the higher class
            return class_id
    return classes[-1]


def nearest_boundary(value: float, project: Project) -> tuple[str, float] | None:
    best: tuple[str, float] | None = None
    for class_id, boundary in boundaries(project):
        distance = abs(value - boundary)
        if best is None or distance < best[1]:
            best = (class_id, distance)
    return best


def audit_sample(values: dict[str, float], project: Project) -> list[str]:
    audit = project["sorting"]["audit"]
    ids = [c["id"] for c in project["sorting"]["classes"]]
    cutoff = ids.index(audit["below_class_id"])
    pool = [a for a, v in values.items() if ids.index(class_of(v, project)) > cutoff]
    keyed = sorted(
        pool, key=lambda a: (hashlib.sha256(f"{audit['seed']}:{a}".encode()).hexdigest(), a)
    )
    return keyed[: audit["sample_size"]]


def class_change_weights(
    project: Project, node_id: str, scenario_id: str | None = None, profile_id: str | None = None
) -> dict[str, list[tuple[float, str]]]:
    """For each alternative, every (weight, boundary class id) at which its class changes when
    ``node_id``'s local weight is set to t and its siblings keep their proportions."""
    base = local_weights(project, _profile(project, scenario_id, profile_id))
    parent = next(n["parent_id"] for n in project["criteria"] if n["id"] == node_id)
    siblings = [
        n["id"] for n in project["criteria"] if n["parent_id"] == parent and n["id"] != node_id
    ]
    rest = sum(base[s] for s in siblings)

    def at(t: float) -> dict[str, float]:
        local = dict(base)
        local[node_id] = t
        for s in siblings:
            local[s] = (1.0 - t) * base[s] / rest
        return overall_values(project, scenario_id, profile_id, local)

    v0, v1 = at(0.0), at(1.0)
    out: dict[str, list[tuple[float, str]]] = {}
    for alt in v0:
        changes = []
        for class_id, boundary in boundaries(project):
            g0, g1 = v0[alt] - (boundary - TOL), v1[alt] - (boundary - TOL)
            if (g0 >= 0) != (g1 >= 0):
                changes.append((g0 / (g0 - g1), class_id))
        out[alt] = sorted(changes)
    return out
