"""Exact market medians from raw decimal strings; standard library only, no app imports."""

from collections.abc import Sequence
from fractions import Fraction


def medians(
    estimates: Sequence[tuple[str, str, str, int, str, str, str, str]],
) -> tuple[Fraction, Fraction]:
    def centre(column: int) -> Fraction:
        values = sorted(Fraction(row[column]) for row in estimates)
        n = len(values)
        return (values[(n - 1) // 2] + values[n // 2]) / 2

    return centre(4), centre(5)
