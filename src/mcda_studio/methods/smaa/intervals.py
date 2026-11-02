"""Exact (Clopper-Pearson) binomial intervals in pure Python; SciPy is not a runtime dependency.

The bounds are quantiles of beta distributions, found by bisection on the regularised incomplete
beta function, which is evaluated by its continued fraction (modified Lentz). Zero and all events
use the closed forms. Tests compare with ``scipy.stats.beta.ppf``.
"""

import math
from functools import lru_cache

_TINY = 1e-300


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    c, d = 1.0, 1.0 - (a + b) * x / (a + 1.0)
    d = 1.0 / (d if abs(d) > _TINY else _TINY)
    h = d
    for m in range(1, 100_000):
        m2 = 2 * m
        for numerator in (
            m * (b - m) * x / ((a - 1.0 + m2) * (a + m2)),
            -(a + m) * (a + b + m) * x / ((a + m2) * (a + 1.0 + m2)),
        ):
            d = 1.0 + numerator * d
            d = 1.0 / (d if abs(d) > _TINY else _TINY)
            c = 1.0 + numerator / c
            c = c if abs(c) > _TINY else _TINY
            step = d * c
            h *= step
        if abs(step - 1.0) < 1e-16:
            return h
    raise ArithmeticError("the incomplete beta continued fraction did not converge")


def regularized_beta(a: float, b: float, x: float) -> float:
    """I_x(a, b) for a, b > 0."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_front = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(log_front) * _beta_continued_fraction(a, b, x) / a
    return 1.0 - math.exp(log_front) * _beta_continued_fraction(b, a, 1.0 - x) / b


def beta_quantile(q: float, a: float, b: float) -> float:
    """The x with I_x(a, b) = q, by bisection to the limit of double precision."""
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if mid in (lo, hi):
            break
        if regularized_beta(a, b, mid) < q:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


@lru_cache(maxsize=65536)
def clopper_pearson(count: int, n: int, confidence: float) -> tuple[float, float]:
    """The exact two-sided interval for ``count`` events in ``n`` independent trials."""
    if n < 1 or not 0 <= count <= n:
        raise ValueError(f"need 0 <= count <= n and n >= 1, got {count} of {n}")
    alpha = 1.0 - confidence
    lower = 0.0 if count == 0 else beta_quantile(alpha / 2, count, n - count + 1)
    upper = 1.0 if count == n else beta_quantile(1 - alpha / 2, count + 1, n - count)
    if count == 0:
        upper = 1.0 - (alpha / 2) ** (1.0 / n)
    if count == n:
        lower = (alpha / 2) ** (1.0 / n)
    return lower, upper
