"""Independent plain-Python oracle for AHP. It never imports mcda_studio, and uses no numpy.

It reads a project file's JSON and computes, in exact rational arithmetic where the inputs allow:

- the reciprocal matrix of each group's or leaf's judgements;
- exact priorities of a consistent matrix (any column, normalised), refusing an inconsistent one;
- CI and CR from a given λmax, against its own copy of the random-index table;
- Koczkodaj's triad index and the most inconsistent triad;
- global criterion priorities down the tree, both syntheses and competition ranks, from local
  priorities supplied by the caller (exact here, or from LAPACK for an inconsistent matrix).

Random indices: Saaty and Tran (2007) for 1 to 15 items, as printed in S. D. Nguyen, "Evaluating
and Ranking Criteria for Mathematics Graduate Education Admissions through the Analytic Hierarchy
Process", arXiv:2011.05376 (CC BY 4.0), Table 12. Definitions follow Saaty (1980) and Koczkodaj
(1993).
"""

from collections.abc import Callable, Sequence
from fractions import Fraction
from itertools import combinations
from typing import Any

Project = dict[str, Any]
Number = Fraction | float
RANDOM_INDEX = {
    1: "0", 2: "0", 3: "0.52", 4: "0.89", 5: "1.11", 6: "1.25", 7: "1.35", 8: "1.40",
    9: "1.45", 10: "1.49", 11: "1.52", 12: "1.54", 13: "1.56", 14: "1.58", 15: "1.59",
}  # fmt: skip


def matrix(items: Sequence[str], judgements: list[dict[str, Any]]) -> list[list[Fraction]]:
    """Exact entries from the stored floats; the other orientation is the exact reciprocal."""
    index = {item: k for k, item in enumerate(items)}
    n = len(items)
    m = [[Fraction(1)] * n for _ in range(n)]
    for j in judgements:
        r, c = index[j["row"]], index[j["column"]]
        m[r][c] = Fraction(j["value"])
        m[c][r] = 1 / Fraction(j["value"])
    return m


def is_consistent(m: list[list[Fraction]]) -> bool:
    n = len(m)
    return all(m[i][k] == m[i][j] * m[j][k] for i in range(n) for j in range(n) for k in range(n))


def consistent_priorities(m: list[list[Fraction]]) -> list[Fraction]:
    """For a consistent matrix every column is proportional to the priorities, and λmax = n."""
    if not is_consistent(m):
        raise ValueError("the matrix is not consistent; use an eigensolver")
    column = [row[0] for row in m]
    total = sum(column, Fraction(0))
    return [x / total for x in column]


def consistency(lambda_max: Number, n: int) -> tuple[Number, Number, Number]:
    """(CI, RI, CR); CI and CR are 0 for one or two items by definition."""
    ri = Fraction(RANDOM_INDEX[n])
    if n < 3:
        return Fraction(0), ri, Fraction(0)
    ci = (lambda_max - n) / (n - 1)
    ci = max(ci, 0 * ci)
    return ci, ri, ci / (ri if isinstance(ci, Fraction) else float(ri))


def triad_index(x: Number, y: Number, z: Number) -> Number:
    return min(abs(1 - z / (x * y)), abs(1 - x * y / z))


def most_inconsistent_triad(
    m: Sequence[Sequence[Number]], items: Sequence[str]
) -> tuple[tuple[str, str, str], Number, Number] | None:
    """(items, index, consistent value of the third judgement); the first largest in order."""
    best = None
    for i, j, k in combinations(range(len(items)), 3):
        index = triad_index(m[i][j], m[j][k], m[i][k])
        if best is None or index > best[1]:
            best = ((items[i], items[j], items[k]), index, m[i][j] * m[j][k])
    return best


def _tree(project: Project) -> tuple[dict[str | None, list[str]], list[str]]:
    children: dict[str | None, list[str]] = {}
    for n in sorted(project["criteria"], key=lambda n: n["order"]):
        children.setdefault(n.get("parent_id"), []).append(n["id"])

    def walk(parent: str | None) -> list[str]:
        out = []
        for c in children.get(parent, []):
            out.append(c)
            out.extend(walk(c))
        return out

    nodes = walk(None)
    return children, [n for n in nodes if not children.get(n)]


def evaluate(
    project: Project,
    priorities: Callable[[list[str], list[dict[str, Any]]], list[Number]],
    synthesis: str = "distributive",
) -> dict[str, Any]:
    """Global criterion priorities, overall priorities and ranks from the supplied local
    priorities of every matrix."""
    children, leaves = _tree(project)
    section = project["ahp"]
    stated = {g["parent_id"]: g["judgements"] for g in section["criteria"]}
    local: dict[str, Number] = {}
    for parent, kids in children.items():
        if len(kids) == 1:
            local[kids[0]] = Fraction(1)
        elif kids:
            local.update(zip(kids, priorities(kids, stated[parent]), strict=True))
    parent_of = {n["id"]: n.get("parent_id") for n in project["criteria"]}

    def global_priority(node: str) -> Number:
        value = local[node]
        up = parent_of[node]
        while up is not None:
            value = value * local[up]
            up = parent_of[up]
        return value

    g = {leaf: global_priority(leaf) for leaf in leaves}
    alternatives = [a["id"] for a in project["alternatives"]]
    on_leaf = {e["criterion_id"]: e["judgements"] for e in section["alternatives"]}
    p = {leaf: priorities(alternatives, on_leaf[leaf]) for leaf in leaves}
    if synthesis == "ideal":
        score = {
            a: sum((g[leaf] * p[leaf][k] / max(p[leaf]) for leaf in leaves), 0 * g[leaves[0]])
            for k, a in enumerate(alternatives)
        }
        total = sum(score.values(), 0 * g[leaves[0]])
        overall = {a: s / total for a, s in score.items()}
    else:
        score = {}
        overall = {
            a: sum((g[leaf] * p[leaf][k] for leaf in leaves), 0 * g[leaves[0]])
            for k, a in enumerate(alternatives)
        }
    return {"local": local, "global": g, "leaf": p, "overall": overall, "ideal": score}


def ranks(values: dict[str, Number]) -> dict[str, int]:
    """Competition ranks: equal values share a rank."""
    return {a: 1 + sum(1 for v in values.values() if v > values[a]) for a in values}
