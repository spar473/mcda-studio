"""Independent plain-Python oracle for SMAA-2. It never imports mcda_studio.

- **Exact enumeration** of discrete stated uncertainty: every joint outcome of the project file's
  ``smaa`` section, its probability as an exact fraction, and the competition ranks and classes of
  that outcome from ``sorting_oracle`` (itself plain Python, reading the same JSON).
- **Clopper-Pearson intervals** found from exact binomial tail sums in rational arithmetic, a
  different route from the engine's continued fraction.

No numpy, no random numbers, no shared code with the engine.
"""

import copy
import itertools
import math
from fractions import Fraction
from typing import Any

import sorting_oracle as values_oracle

TOL = 1e-12
Project = dict[str, Any]


def _exact(probabilities: list[float]) -> list[Fraction]:
    raw = [Fraction(p) for p in probabilities]
    total = sum(raw, Fraction(0))
    return [p / total for p in raw]


def _outcomes(project: Project, cell: dict[str, Any]) -> list[tuple[Fraction, Any]]:
    """A discrete or categorical cell's outcomes in quantile order: numbers ascending, labels in
    scale order."""
    dist = cell["distribution"]
    if dist["kind"] == "discrete":
        pairs = sorted(zip(dist["values"], dist["probabilities"], strict=True))
    else:
        leaf = next(n for n in project["criteria"] if n["id"] == cell["criterion_id"])
        given = dict(zip(dist["labels"], dist["probabilities"], strict=True))
        pairs = [(x, given[x]) for x in leaf["scale"]["labels"] if x in given]
    return list(zip(_exact([p for _, p in pairs]), [v for v, _ in pairs], strict=True))


def _segments(tables: list[list[tuple[Fraction, Any]]]) -> list[tuple[Fraction, list[Any]]]:
    cuts = {Fraction(0), Fraction(1)}
    for table in tables:
        cuts |= set(itertools.accumulate(p for p, _ in table))
    out = []
    for start, end in itertools.pairwise(sorted(cuts)):
        chosen = [
            next(
                v
                for c, (_, v) in zip(itertools.accumulate(p for p, _ in t), t, strict=True)
                if c > start
            )
            for t in tables
        ]
        out.append((end - start, chosen))
    return out


def competition_ranks(values: dict[str, float]) -> dict[str, int]:
    return {a: 1 + sum(1 for o in values.values() if o > v + TOL) for a, v in values.items()}


def exact_acceptability(
    project: Project,
) -> tuple[
    dict[str, list[Fraction]],
    dict[str, Fraction],
    dict[str, Fraction],
    dict[str, dict[str, Fraction]],
]:
    """Rank, sole-first, tied-first and class probabilities over every joint outcome."""
    smaa = project["smaa"]
    cells = {(c["alternative_id"], c["criterion_id"]): c for c in smaa["cells"]}
    shared_cells = {
        (r["alternative_id"], r["criterion_id"]) for s in smaa["shared_draws"] for r in s["cells"]
    }
    variables: list[tuple[list[tuple[str, str]], list[tuple[Fraction, list[Any]]]]] = []
    for key in sorted(cells):
        if key not in shared_cells:
            variables.append(([key], [(p, [v]) for p, v in _outcomes(project, cells[key])]))
    for s in smaa["shared_draws"]:
        keys = [(r["alternative_id"], r["criterion_id"]) for r in s["cells"]]
        variables.append((keys, _segments([_outcomes(project, cells[k]) for k in keys])))
    alternatives = [a["id"] for a in project["alternatives"]]
    class_ids = [c["id"] for c in project["sorting"]["classes"]] if "sorting" in project else []
    ranks = {a: [Fraction(0)] * len(alternatives) for a in alternatives}
    sole = dict.fromkeys(alternatives, Fraction(0))
    tied = dict.fromkeys(alternatives, Fraction(0))
    classes = {a: dict.fromkeys(class_ids, Fraction(0)) for a in alternatives}
    for combo in itertools.product(*(outcomes for _, outcomes in variables)):
        probability = math.prod((o[0] for o in combo), start=Fraction(1))
        drawn = copy.deepcopy(project)
        measured = {(p["alternative_id"], p["criterion_id"]): p for p in drawn["performances"]}
        for (keys, _), (_, chosen) in zip(variables, combo, strict=True):
            for key, value in zip(keys, chosen, strict=True):
                measured[key]["value"] = value
        values = values_oracle.overall_values(drawn)
        rank = competition_ranks(values)
        firsts = sum(1 for r in rank.values() if r == 1)
        for a in alternatives:
            ranks[a][rank[a] - 1] += probability
            if rank[a] == 1:
                (sole if firsts == 1 else tied)[a] += probability
            if class_ids:
                classes[a][values_oracle.class_of(values[a], drawn)] += probability
    return ranks, sole, tied, classes


def _binomial_cdf(k: int, n: int, p: Fraction) -> Fraction:
    return sum((math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1)), Fraction(0))


def clopper_pearson(k: int, n: int, confidence: float) -> tuple[float, float]:
    """Exact interval by bisection on rational binomial tails (small n only)."""
    alpha = Fraction(1) - Fraction(confidence)

    def solve(tail: Any, target: Fraction, increasing: bool) -> float:
        lo, hi = Fraction(0), Fraction(1)
        for _ in range(60):
            mid = (lo + hi) / 2
            if (tail(mid) < target) == increasing:
                lo = mid
            else:
                hi = mid
        return float((lo + hi) / 2)

    lower = 0.0 if k == 0 else solve(lambda p: 1 - _binomial_cdf(k - 1, n, p), alpha / 2, True)
    upper = 1.0 if k == n else solve(lambda p: _binomial_cdf(k, n, p), alpha / 2, False)
    return lower, upper
