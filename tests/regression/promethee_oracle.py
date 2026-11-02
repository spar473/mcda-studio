"""Independent plain-Python oracle for PROMETHEE II. It never imports mcda_studio.

It reads a project file's JSON and computes, in exact rational arithmetic, the preference degrees,
the flows (normalised by n - 1), the single-criterion net flows, the PROMETHEE I relations and the
split of a flow gap into its head-to-head and via-others parts. Every input number becomes a
fraction through its decimal string, so a difference that equals a threshold in decimal equals it
here exactly: no tolerance is needed or used.

Definitions follow Brans and Mareschal, "PROMETHEE methods", in Figueira, Greco and Ehrgott (eds.),
Multiple Criteria Decision Analysis: State of the Art Surveys, Springer, 2005.
"""

from fractions import Fraction
from typing import Any

Project = dict[str, Any]


def exact(x: float | int | str) -> Fraction:
    """A JSON number as the decimal it was written as."""
    return Fraction(str(x))


def degree(function: dict[str, Any], d: Fraction) -> Fraction:
    if d <= 0:
        return Fraction(0)
    kind = function["kind"]
    if kind == "usual":
        return Fraction(1)
    if kind == "u_shape":
        return Fraction(0) if d <= exact(function["q"]) else Fraction(1)
    if kind == "v_shape":
        p = exact(function["p"])
        return d / p if d < p else Fraction(1)
    q, p = exact(function["q"]), exact(function["p"])
    if d <= q:
        return Fraction(0)
    if d >= p:
        return Fraction(1)
    return (d - q) / (p - q)


def leaves(project: Project) -> list[str]:
    parents = {n["parent_id"] for n in project["criteria"] if n.get("parent_id")}
    return [n["id"] for n in project["criteria"] if n["id"] not in parents]


def measurements(project: Project) -> dict[str, dict[str, Fraction]]:
    """Per leaf, each alternative's measurement as a fraction (its code on a labelled leaf)."""
    entries = {e["criterion_id"]: e for e in project["promethee"]["criteria"]}
    out: dict[str, dict[str, Fraction]] = {leaf: {} for leaf in leaves(project)}
    for cell in project["performances"]:
        value = cell["value"]
        coding = entries[cell["criterion_id"]].get("coding")
        out[cell["criterion_id"]][cell["alternative_id"]] = (
            exact(coding[value]) if isinstance(value, str) else exact(value)
        )
    return out


def flows(project: Project) -> dict[str, Any]:
    """Everything PROMETHEE II and I compute, exactly."""
    alts = [a["id"] for a in project["alternatives"]]
    n = len(alts)
    entries = {e["criterion_id"]: e for e in project["promethee"]["criteria"]}
    xs = measurements(project)
    total = sum((exact(e["weight"]) for e in entries.values()), Fraction(0))
    weights = {leaf: exact(e["weight"]) / total for leaf, e in entries.items()}
    degrees: dict[str, dict[tuple[str, str], Fraction]] = {}
    for leaf, e in entries.items():
        sign = 1 if e["direction"] == "maximise" else -1
        x = xs[leaf]
        degrees[leaf] = {
            (a, b): degree(e["function"], sign * (x[a] - x[b])) for a in alts for b in alts
        }
    pi = {
        (a, b): sum((weights[j] * degrees[j][a, b] for j in entries), Fraction(0))
        for a in alts
        for b in alts
        if a != b
    }
    positive = {a: sum((pi[a, b] for b in alts if b != a), Fraction(0)) / (n - 1) for a in alts}
    negative = {a: sum((pi[b, a] for b in alts if b != a), Fraction(0)) / (n - 1) for a in alts}
    net = {a: positive[a] - negative[a] for a in alts}
    criterion = {
        j: {
            a: sum((degrees[j][a, b] - degrees[j][b, a] for b in alts if b != a), Fraction(0))
            / (n - 1)
            for a in alts
        }
        for j in entries
    }
    return {
        "alternatives": alts,
        "weights": weights,
        "degrees": degrees,
        "preference": pi,
        "positive": positive,
        "negative": negative,
        "net": net,
        "criterion": criterion,
    }


def ranks(values: dict[str, Fraction]) -> dict[str, int]:
    """Competition ranks: equal values share a rank."""
    return {a: 1 + sum(1 for v in values.values() if v > values[a]) for a in values}


def relation(result: dict[str, Any], a: str, b: str) -> str:
    """PROMETHEE I for the ordered pair: 'a', 'b', 'indifferent' or 'incomparable'."""
    plus, minus = result["positive"], result["negative"]
    if plus[a] == plus[b] and minus[a] == minus[b]:
        return "indifferent"
    if plus[a] >= plus[b] and minus[a] <= minus[b]:
        return "a"
    if plus[b] >= plus[a] and minus[b] <= minus[a]:
        return "b"
    return "incomparable"


def split(result: dict[str, Any], a: str, b: str) -> tuple[Fraction, Fraction, Fraction]:
    """The flow gap, its head-to-head part and its via-others part, each computed on its own."""
    alts, pi, n = result["alternatives"], result["preference"], len(result["alternatives"])
    gap = result["net"][a] - result["net"][b]
    head = 2 * (pi[a, b] - pi[b, a]) / (n - 1)
    via = sum(
        ((pi[a, c] - pi[c, a]) - (pi[b, c] - pi[c, b]) for c in alts if c not in (a, b)),
        Fraction(0),
    ) / (n - 1)
    return gap, head, via
