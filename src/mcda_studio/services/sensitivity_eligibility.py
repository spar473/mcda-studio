"""Shared scored-node eligibility for summary fragility and weight questions.

The sensitivity engine itself still allows probing zero-weight criteria. These
read-only summaries exclude them so a screening-only branch never becomes a score.
"""

from mcda_studio.domain.criteria import CriterionTree
from mcda_studio.methods.mavt.aggregation import TIE_TOL


def node_global_weight(tree: CriterionTree, local: dict[str, float], node_id: str) -> float:
    """The product of local weights from ``node_id`` up to the root."""
    weight = 1.0
    node: str | None = node_id
    while node is not None:
        weight *= local[node]
        node = tree.node(node).parent_id
    return weight


def eligible_nodes(tree: CriterionTree, local: dict[str, float]) -> tuple[list[str], list[str]]:
    """Nodes one-way sensitivity accepts and that carry weight, and those excluded for zero
    weight. Nodes without a sibling or already at local weight 1 cannot be varied at all."""
    varied: list[str] = []
    excluded: list[str] = []
    for node_id in tree.all_ids():
        parent = tree.node(node_id).parent_id
        if len(tree.child_ids(parent)) < 2 or local[node_id] >= 1.0 - TIE_TOL:
            continue
        (varied if node_global_weight(tree, local, node_id) > 0.0 else excluded).append(node_id)
    return varied, excluded
