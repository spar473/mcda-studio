"""Independent raw-measurement MAVT/sorting oracle. No application imports.

Fractions retain the decimal input algebra; float products and math.fsum reproduce the
specified numerical boundary, rather than moving a case across it with rational rounding.
"""

import math
from fractions import Fraction


def evaluate(raw, ratings, functions, boundaries):
    weights = {
        key: float(Fraction(str(value)) / sum(Fraction(str(v)) for v in ratings.values()))
        for key, value in ratings.items()
    }
    values = {}
    for alternative, measurements in raw.items():
        partials = []
        for leaf in ratings:
            x = float(measurements[leaf])
            kind, details = functions[leaf]
            if kind == "piecewise":
                points = details
                if not points[0][0] <= x <= points[-1][0]:
                    raise ValueError("out of domain")
                for (x0, v0), (x1, v1) in zip(points, points[1:], strict=False):
                    if x <= x1:
                        value = v0 + (v1 - v0) * (x - x0) / (x1 - x0)
                        break
            else:
                lo, hi, decreasing = details
                if not lo <= x <= hi:
                    raise ValueError("out of domain")
                value = (hi - x) / (hi - lo) if decreasing else (x - lo) / (hi - lo)
            partials.append(weights[leaf] * min(1.0, max(0.0, value)))
        values[alternative] = math.fsum(partials)
    ranks = {
        a: 1 + sum(other > score + 1e-12 for other in values.values())
        for a, score in values.items()
    }
    classes = {
        a: sum(score < boundary - 1e-12 for boundary in boundaries) for a, score in values.items()
    }
    return values, ranks, classes


def acceptabilities(outcomes, ratings, functions, boundaries):
    """Exact event probabilities, never a mean of scores or disagreements."""
    ranks, classes = {}, {}
    for probability, raw in outcomes:
        _, rank, cls = evaluate(raw, ratings, functions, boundaries)
        for alternative in raw:
            key = alternative, rank[alternative]
            ranks[key] = ranks.get(key, Fraction(0)) + probability
            key = alternative, cls[alternative]
            classes[key] = classes.get(key, Fraction(0)) + probability
    return ranks, classes
