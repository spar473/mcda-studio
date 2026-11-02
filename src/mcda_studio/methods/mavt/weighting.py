"""Hierarchical swing weighting.

Local weight:   lambda_i = r_i / sum_k r_k          (within a sibling group)
Global weight:  w_j = product of lambda_e over e in path(root -> leaf j)

Global leaf weights are *always derived* from the raw swing ratings; nobody enters them by hand.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass

from mcda_studio.domain.criteria import CriterionTree
from mcda_studio.domain.errors import WeightError
from mcda_studio.domain.preferences import check_judgements

WEIGHT_BASIS = (
    "Swing weights: each rating expresses the importance of the swing from the worst to the best "
    "level of that criterion over the stated scale range, not abstract importance. Changing a "
    "scale range changes the meaning of its weight."
)


@dataclass(frozen=True)
class WeightSet:
    local: dict[str, float]  # every node, relative to its siblings
    global_: dict[str, float]  # leaves only


def local_weights(tree: CriterionTree, judgements: Mapping[str, float]) -> dict[str, float]:
    """Normalise raw ratings within every sibling group. Raises WeightError if invalid."""
    problems = check_judgements(tree, judgements)
    if problems:
        raise WeightError("; ".join(f"{p.path}: {p.message}" for p in problems))
    out: dict[str, float] = {}
    parents: list[str | None] = [None, *[i for i in tree.all_ids() if not tree.is_leaf(i)]]
    for pid in parents:
        kids = tree.child_ids(pid)
        if not kids:
            continue
        ratings = [float(judgements.get(k, 1.0)) for k in kids]
        total = math.fsum(ratings)
        for kid, r in zip(kids, ratings, strict=True):
            out[kid] = r / total
    return out


def global_weights(tree: CriterionTree, local: Mapping[str, float]) -> dict[str, float]:
    """Product of local weights along each leaf's root path."""
    out: dict[str, float] = {}
    for leaf in tree.leaves():
        w = 1.0
        for node_id in tree.path(leaf):
            w *= local[node_id]
        out[leaf] = w
    return out


def path_shares(tree: CriterionTree, local: Mapping[str, float]) -> dict[str, float]:
    """Product of local weights along every node's root path, leaves and objectives alike.

    A leaf's share is its global weight; an objective's share is the fraction of the overall
    goal its branch carries. Nothing here is an independent preference input: the numbers are
    derived from the same local weights, so the GUI never multiplies weights of its own.
    """
    out: dict[str, float] = {}
    for node_id in tree.all_ids():
        w = 1.0
        for step in tree.path(node_id):
            w *= local[step]
        out[node_id] = w
    return out


def compute_weights(tree: CriterionTree, judgements: Mapping[str, float]) -> WeightSet:
    local = local_weights(tree, judgements)
    return WeightSet(local=local, global_=global_weights(tree, local))
