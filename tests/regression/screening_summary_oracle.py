"""Independent plain-Python oracle for the screening summary. It never imports mcda_studio.

From the project file alone (through ``sorting_oracle`` and ``feasibility_oracle``, themselves
plain Python): values, competition ranks, the two largest weighted contributions, classes and
boundary distances, requirement status, and fragility by brute force. Fragility varies every
eligible criterion node's local weight with its siblings in proportion, evaluates values at the
two endpoints, finds every rank crossover and class change with its own root formula, and keeps
the smallest change of the node's global weight. No numpy, no shared code with the engine.
"""

from typing import Any

import feasibility_oracle
import sorting_oracle as values_oracle

TOL = 1e-12
Project = dict[str, Any]


def _parents(project: Project) -> dict[str, str | None]:
    return {n["id"]: n["parent_id"] for n in project["criteria"]}


def node_global(project: Project, local: dict[str, float], node: str | None) -> float:
    parents, weight = _parents(project), 1.0
    while node is not None:
        weight *= local[node]
        node = parents[node]
    return weight


def contributions(
    project: Project, profile_id: str | None, scenario_id: str | None
) -> dict[str, dict[str, float]]:
    local = values_oracle.local_weights(
        project, values_oracle._profile(project, scenario_id, profile_id)
    )
    weights = values_oracle.global_weights(project, local)
    nodes = {n["id"]: n for n in project["criteria"]}
    measured = {
        (p["alternative_id"], p["criterion_id"]): p["value"] for p in project["performances"]
    }
    out: dict[str, dict[str, float]] = {}
    for alt in (a["id"] for a in project["alternatives"]):
        out[alt] = {}
        for leaf, weight in weights.items():
            function = values_oracle._function(project, nodes[leaf], scenario_id)
            value = values_oracle.partial_value(
                function, nodes[leaf]["scale"], measured[(alt, leaf)]
            )
            out[alt][leaf] = weight * value
    return out


def eligible_nodes(project: Project, local: dict[str, float]) -> tuple[list[str], list[str]]:
    parents = _parents(project)
    varied, excluded = [], []
    for node in project["criteria"]:
        siblings = [n for n, p in parents.items() if p == node["parent_id"]]
        if len(siblings) < 2 or local[node["id"]] >= 1.0 - TOL:
            continue
        target = varied if node_global(project, local, node["id"]) > 0.0 else excluded
        target.append(node["id"])
    return varied, excluded


def fragility(
    project: Project, profile_id: str | None = None, scenario_id: str | None = None
) -> tuple[dict[str, Any], list[str]]:
    """{alt: ("tied", [others]) | ("none",) | ("change", amount, [(kind, node, detail), ...])}"""
    base = values_oracle.local_weights(
        project, values_oracle._profile(project, scenario_id, profile_id)
    )
    parents = _parents(project)
    values = values_oracle.overall_values(project, scenario_id, profile_id)
    varied, excluded = eligible_nodes(project, base)
    candidates: dict[str, list[tuple[float, str, str, str]]] = {a: [] for a in values}
    for node in varied:
        siblings = [n for n, p in parents.items() if p == parents[node] and n != node]
        rest = sum(base[s] for s in siblings)

        def at(
            t: float, node: str = node, siblings: list[str] = siblings, rest: float = rest
        ) -> dict[str, float]:
            local = dict(base)
            local[node] = t
            for s in siblings:
                local[s] = (1.0 - t) * base[s] / rest
            return values_oracle.overall_values(project, scenario_id, profile_id, local)

        v0, v1 = at(0.0), at(1.0)
        scale = node_global(project, base, parents[node])
        for a in values:
            for b in values:
                if a == b:
                    continue
                d0, d1 = v0[a] - v0[b], v1[a] - v1[b]
                if (d0 > TOL and d1 < -TOL) or (d0 < -TOL and d1 > TOL):
                    t = d0 / (d0 - d1)
                    if TOL < t < 1.0 - TOL:
                        candidates[a].append((abs(t - base[node]) * scale, "rank", node, b))
            if project.get("sorting") and project["sorting"]["classes"]:
                for class_id, boundary in values_oracle.boundaries(project):
                    g0, g1 = v0[a] - (boundary - TOL), v1[a] - (boundary - TOL)
                    if (g0 >= 0) != (g1 >= 0):
                        t = g0 / (g0 - g1)
                        candidates[a].append((abs(t - base[node]) * scale, "class", node, class_id))
    out: dict[str, Any] = {}
    for a, v in values.items():
        tied = [b for b, w in values.items() if b != a and abs(w - v) <= TOL]
        if tied:
            out[a] = ("tied", tied)
        elif not candidates[a]:
            out[a] = ("none",)
        else:
            smallest = min(c[0] for c in candidates[a])
            out[a] = ("change", smallest, [c[1:] for c in candidates[a] if c[0] <= smallest + TOL])
    return out, excluded


def summary(
    project: Project, profile_id: str | None = None, scenario_id: str | None = None
) -> dict[str, Any]:
    values = values_oracle.overall_values(project, scenario_id, profile_id)
    parts = contributions(project, profile_id, scenario_id)
    feasible = feasibility_oracle.evaluate(project) if project.get("requirements") else None
    sorting = project.get("sorting")
    frag, excluded = fragility(project, profile_id, scenario_id)
    rows: dict[str, Any] = {}
    for a, v in values.items():
        positive = sorted((c for c in parts[a].values() if c > 0.0), reverse=True)
        rows[a] = {
            "value": v,
            "rank": 1 + sum(1 for w in values.values() if w > v + TOL),
            "drivers": positive[:2],
            "class": values_oracle.class_of(v, project) if sorting and sorting["classes"] else None,
            "margin": (values_oracle.nearest_boundary(v, project) or (None, None))[1]
            if sorting and sorting["classes"]
            else None,
            "requirements": feasible[a]["status"] if feasible else None,
            "fragility": frag[a],
        }
    return {"rows": rows, "excluded": excluded}
