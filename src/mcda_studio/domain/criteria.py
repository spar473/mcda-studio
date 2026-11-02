"""Criteria hierarchy and value-function specifications.

The hierarchy is an arbitrary-depth forest: nodes with ``parent_id=None`` are the children of an
implicit root. A node is a *leaf* iff nothing names it as parent. Only leaves carry a scale and a
value function. The tree can have any depth; nothing assumes three levels.
"""

from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from mcda_studio.domain.common import DomainModel, FiniteFloat, Id
from mcda_studio.domain.errors import ModelStructureError, UnknownReferenceError
from mcda_studio.domain.scales import Scale, ScaleType


class Direction(StrEnum):
    INCREASING = "increasing"  # higher measurement = more preferred
    DECREASING = "decreasing"  # lower measurement = more preferred


class _NumericValueFunction(DomainModel):
    #: "error": a measurement outside the domain is a validation error (default).
    #: "clamp": it is clamped to the nearest end and reported as a diagnostic - never silent.
    out_of_domain: Literal["error", "clamp"] = "error"


class LinearValueFunction(_NumericValueFunction):
    """v(x) = (x-L)/(U-L) (increasing) or (U-x)/(U-L) (decreasing); L, U come from the scale."""

    kind: Literal["linear"] = "linear"
    direction: Direction = Direction.INCREASING


class ControlPoint(DomainModel):
    x: FiniteFloat
    value: FiniteFloat


class PiecewiseLinearValueFunction(_NumericValueFunction):
    """Interpolates linearly between ordered (x, value) points; domain = [x_first, x_last]."""

    kind: Literal["piecewise_linear"] = "piecewise_linear"
    points: list[ControlPoint]


class QualitativeValueFunction(DomainModel):
    """Explicit label -> preference value mapping. Spacing is a judgement, never assumed."""

    kind: Literal["qualitative"] = "qualitative"
    mapping: dict[str, FiniteFloat]


class DirectRatingValueFunction(_NumericValueFunction):
    """The measurement *is* a rating on [min_rating, max_rating], rescaled linearly to [0, 1]."""

    kind: Literal["direct_rating"] = "direct_rating"
    min_rating: FiniteFloat = 0.0
    max_rating: FiniteFloat = 100.0


ValueFunctionSpec = Annotated[
    LinearValueFunction
    | PiecewiseLinearValueFunction
    | QualitativeValueFunction
    | DirectRatingValueFunction,
    Field(discriminator="kind"),
]

#: Which value-function kinds are admissible for which scale type. Anything else is rejected
#: because the transformation would not be meaningful for that measurement level.
ALLOWED_VALUE_FUNCTIONS: dict[ScaleType, frozenset[str]] = {
    ScaleType.CATEGORICAL: frozenset({"qualitative"}),
    ScaleType.ORDINAL: frozenset({"qualitative"}),
    ScaleType.INTERVAL: frozenset({"linear", "piecewise_linear", "direct_rating"}),
    ScaleType.RATIO: frozenset({"linear", "piecewise_linear"}),
}


class CriterionNode(DomainModel):
    id: Id
    name: str = Field(min_length=1)
    parent_id: Id | None = None
    order: int = 0  # position among siblings (ties broken by list position)
    description: str = ""
    # Leaf-only fields (must be None on non-leaf nodes; enforced by validation):
    scale: Scale | None = None
    value_function: ValueFunctionSpec | None = None


class CriterionTree:
    """Read-only view over a list of nodes. Raises ModelStructureError on malformed input."""

    def __init__(self, nodes: Sequence[CriterionNode]) -> None:
        self._nodes: dict[str, CriterionNode] = {}
        for n in nodes:
            if n.id in self._nodes:
                raise ModelStructureError(f"duplicate criterion id {n.id!r}")
            self._nodes[n.id] = n
        for n in nodes:
            if n.parent_id is not None and n.parent_id not in self._nodes:
                raise ModelStructureError(f"criterion {n.id!r} has unknown parent {n.parent_id!r}")
            if n.parent_id == n.id:
                raise ModelStructureError(f"criterion {n.id!r} is its own parent")
        position = {n.id: i for i, n in enumerate(nodes)}
        self._children: dict[str | None, list[str]] = {None: []}
        for n in nodes:
            self._children.setdefault(n.id, [])
            self._children.setdefault(n.parent_id, []).append(n.id)
        for kids in self._children.values():
            kids.sort(key=lambda i: (self._nodes[i].order, position[i]))
        reachable = set(self._descend(None))
        if len(reachable) != len(self._nodes):
            cyclic = sorted(set(self._nodes) - reachable)
            raise ModelStructureError(f"criteria hierarchy contains a cycle involving {cyclic}")

    def _descend(self, start: str | None) -> list[str]:
        out: list[str] = []
        stack = list(reversed(self._children.get(start, [])))
        while stack:
            cur = stack.pop()
            out.append(cur)
            stack.extend(reversed(self._children[cur]))
        return out

    def __contains__(self, node_id: object) -> bool:
        return node_id in self._nodes

    def __len__(self) -> int:
        return len(self._nodes)

    def node(self, node_id: str) -> CriterionNode:
        try:
            return self._nodes[node_id]
        except KeyError:
            raise UnknownReferenceError(f"unknown criterion id {node_id!r}") from None

    def child_ids(self, parent_id: str | None) -> list[str]:
        return list(self._children.get(parent_id, []))

    def is_leaf(self, node_id: str) -> bool:
        return not self._children[node_id]

    def all_ids(self) -> list[str]:
        """All node ids, depth-first in sibling order."""
        return self._descend(None)

    def leaves(self) -> list[str]:
        return [i for i in self._descend(None) if self.is_leaf(i)]

    def path(self, node_id: str) -> list[str]:
        """Ids from the top-level ancestor down to ``node_id`` inclusive."""
        out = [node_id]
        cur = self.node(node_id).parent_id
        while cur is not None:
            out.append(cur)
            cur = self._nodes[cur].parent_id
        return list(reversed(out))

    def depth(self, node_id: str) -> int:
        return len(self.path(node_id))

    def subtree_ids(self, node_id: str) -> list[str]:
        """``node_id`` and all its descendants."""
        return [node_id, *self._descend(node_id)]
