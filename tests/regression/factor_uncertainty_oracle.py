"""Independent exact answers for fundamental-factor uncertainty; no application imports.

Joint discrete outcomes are built with exact fractions. A quantile group is coupled here by a
two-pointer merge of the members' sorted cumulative probabilities (the comonotone construction),
not by the production cut-point search. Formulas are plain Python functions in each test, so no
expression parser or interpreter is shared."""

from collections import defaultdict
from collections.abc import Callable
from fractions import Fraction
from itertools import product

Atoms = list[tuple[Fraction, Fraction]]  # (value, probability)


def comonotone(members: dict[str, Atoms]) -> list[tuple[Fraction, dict[str, Fraction]]]:
    """One shared uniform through every member's quantile: merge the cumulative steps."""
    sorted_atoms = {name: sorted(atoms) for name, atoms in members.items()}
    position = dict.fromkeys(sorted_atoms, 0)
    left = dict.fromkeys(sorted_atoms, Fraction(0))  # probability left in the current atom
    for name, atoms in sorted_atoms.items():
        left[name] = atoms[0][1]
    out = []
    while True:
        # Skip exhausted zero-probability atoms.
        for name, atoms in sorted_atoms.items():
            while left[name] == 0 and position[name] + 1 < len(atoms):
                position[name] += 1
                left[name] = atoms[position[name]][1]
        step = min(left.values())
        if step == 0:
            break
        out.append((step, {name: sorted_atoms[name][position[name]][0] for name in sorted_atoms}))
        for name in left:
            left[name] -= step
    return out


def joint(
    independent: dict[str, Atoms], groups: list[dict[str, Atoms]]
) -> list[tuple[Fraction, dict[str, Fraction]]]:
    blocks = [[(p, {name: v}) for v, p in atoms if p > 0] for name, atoms in independent.items()]
    blocks += [comonotone(group) for group in groups]
    out = []
    for combination in product(*blocks):
        probability = Fraction(1)
        values: dict[str, Fraction] = {}
        for p, chosen in combination:
            probability *= p
            values.update(chosen)
        out.append((probability, values))
    return out


def distribution(
    outcomes: list[tuple[Fraction, dict[str, Fraction]]],
    formula: Callable[[dict[str, Fraction]], Fraction],
) -> dict[Fraction, Fraction]:
    out: dict[Fraction, Fraction] = defaultdict(Fraction)
    for p, values in outcomes:
        out[formula(values)] += p
    return dict(out)


def moments(dist: dict[Fraction, Fraction]) -> tuple[Fraction, Fraction]:
    mean = sum((v * p for v, p in dist.items()), Fraction(0))
    variance = sum(((v - mean) ** 2 * p for v, p in dist.items()), Fraction(0))
    return mean, variance


def uniform_raw_moment(a: Fraction, b: Fraction, k: int) -> Fraction:
    return (b ** (k + 1) - a ** (k + 1)) / ((k + 1) * (b - a))


def product_central_moments(
    x: tuple[Fraction, Fraction], y: tuple[Fraction, Fraction]
) -> tuple[Fraction, Fraction, Fraction]:
    """Mean, variance and fourth central moment of XY for independent uniforms X and Y."""
    raw = [uniform_raw_moment(*x, k) * uniform_raw_moment(*y, k) for k in range(5)]
    mean = raw[1]
    variance = raw[2] - mean**2
    fourth = raw[4] - 4 * mean * raw[3] + 6 * mean**2 * raw[2] - 3 * mean**4
    return mean, variance, fourth


def triangular_cdf(x: float, a: float, m: float, b: float) -> float:
    if x <= a:
        return 0.0
    if x <= m:
        return (x - a) ** 2 / ((b - a) * (m - a))
    if x < b:
        return 1 - (b - x) ** 2 / ((b - a) * (b - m))
    return 1.0


def triangular_moments(a: Fraction, m: Fraction, b: Fraction) -> tuple[Fraction, Fraction]:
    return (a + m + b) / 3, (a * a + m * m + b * b - a * m - a * b - m * b) / 18
