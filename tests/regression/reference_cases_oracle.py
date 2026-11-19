"""An independent oracle for reference cases. It never imports the application.

It reads the raw project JSON and the raw reference-set JSON, derives global leaf weights from the
raw swing ratings with its own code (local weight = rating / sum of its siblings' ratings, a missing
rating counting as 1, global = product along the root path), and computes every similarity, shared
count, ordering and grouping from scratch with exact fractions.
"""

import math
from fractions import Fraction
from typing import Any


def _children(criteria: list[dict[str, Any]]) -> dict[str | None, list[str]]:
    out: dict[str | None, list[str]] = {}
    for node in criteria:
        out.setdefault(node.get("parent_id"), []).append(node["id"])
    return out


def global_weights(project: dict[str, Any], profile_id: str | None) -> dict[str, float]:
    profiles = project["weight_profiles"]
    profile = next(p for p in profiles if p["id"] == profile_id) if profile_id else profiles[0]
    ratings = profile["judgements"]
    kids = _children(project["criteria"])
    parent = {node["id"]: node.get("parent_id") for node in project["criteria"]}
    local: dict[str, float] = {}
    for group in kids.values():
        values = [float(ratings.get(k, 1.0)) for k in group]
        total = math.fsum(values)
        for k, value in zip(group, values, strict=True):
            local[k] = value / total
    leaves = [n["id"] for n in project["criteria"] if n["id"] not in kids]
    out: dict[str, float] = {}
    for leaf in leaves:
        path = []
        node: str | None = leaf
        while node is not None:
            path.append(node)
            node = parent[node]
        weight = 1.0
        for step in reversed(path):  # root first, like the engine
            weight *= local[step]
        out[leaf] = weight
    return out


def compare(
    project: dict[str, Any],
    reference_set: dict[str, Any],
    alternative_id: str,
    *,
    profile_id: str | None = None,
    k: int = 3,
    weighting: str = "equal",
    min_shared: Fraction = Fraction(1, 2),
    exclude_same_id: bool = False,
) -> dict[str, Any]:
    nodes = {n["id"]: n for n in project["criteria"]}
    kids = _children(project["criteria"])
    order = [n["id"] for n in project["criteria"]]
    weights = global_weights(project, profile_id)

    def labelled(leaf: str) -> bool:
        scale = nodes[leaf].get("scale") or {}
        return scale.get("type") in ("ordinal", "categorical")

    # Leaves in depth-first tree order; siblings by their stated order, then as listed.
    def walk(parent: str | None) -> list[str]:
        out: list[str] = []
        siblings = [c for c in order if nodes[c].get("parent_id") == parent]
        siblings.sort(key=lambda c: (nodes[c].get("order", 0), order.index(c)))
        for child in siblings:
            out.extend([child] if child not in kids else walk(child))
        return out

    compared = [leaf for leaf in walk(None) if labelled(leaf) and weights[leaf] > 0]
    mine = {
        p["criterion_id"]: p["value"]
        for p in project["performances"]
        if p["alternative_id"] == alternative_id
    }
    ranked = []
    not_comparable = []
    excluded = []
    for case in reference_set["cases"]:
        if exclude_same_id and case["id"] == alternative_id:
            excluded.append(case["id"])
            continue
        theirs = {r["criterion_id"]: r["label"] for r in case["ratings"]}
        gaps: list[tuple[str, Fraction, int | None]] = []
        for leaf in compared:
            if leaf not in mine or leaf not in theirs:
                continue
            scale = nodes[leaf]["scale"]
            labels = scale["labels"]
            a, b = labels.index(mine[leaf]), labels.index(theirs[leaf])
            if scale["type"] == "ordinal":
                gap = Fraction(abs(a - b), len(labels) - 1) if len(labels) > 1 else Fraction(0)
                gaps.append((leaf, gap, abs(a - b)))
            else:
                gaps.append((leaf, Fraction(int(a != b)), None))
        shared = len(gaps)
        if shared == 0 or Fraction(shared, len(compared)) < min_shared:
            not_comparable.append((case["id"], shared, len(compared)))
            continue
        if weighting == "equal":
            distance = sum((g for _, g, _ in gaps), Fraction(0)) / shared
        else:
            w = {leaf: Fraction(weights[leaf]) for leaf, _, _ in gaps}
            total = sum(w.values(), Fraction(0))
            distance = sum((w[leaf] * g for leaf, g, _ in gaps), Fraction(0)) / total
        same = [leaf for leaf, g, _ in gaps if g == 0]
        one = [leaf for leaf, g, steps in gaps if g != 0 and steps == 1]
        further = [leaf for leaf, g, steps in gaps if g != 0 and steps != 1]
        ranked.append((1 - distance, shared, case["id"], same, one, further))
    ranked.sort(key=lambda r: (-r[0], -r[1], r[2]))
    return {
        "compared": compared,
        "top": [
            {
                "case_id": r[2],
                "similarity": r[0],
                "shared": r[1],
                "same": r[3],
                "one_step": r[4],
                "further": r[5],
            }
            for r in ranked[:k]
        ],
        "remaining": max(0, len(ranked) - k),
        "not_comparable": not_comparable,
        "excluded": excluded,
    }
