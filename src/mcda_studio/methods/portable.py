"""Portable elementary functions: the same bits on every IEEE 754 platform.

The platform's C maths library (Apple libm, glibc, the Microsoft runtime) may round ``log``,
``exp`` and ``lgamma`` differently in the last bit, and that difference reaches results through a
bisection or a sum. These functions use only operations IEEE 754 rounds identically everywhere:
``+``, ``-``, ``*``, ``/``, comparisons and exact scaling by powers of two (``frexp``, ``ldexp``),
each applied one at a time in a fixed order. So the result has one bit pattern on every platform.

The algorithms are the classic ones: fdlibm's reductions and minimax polynomials for ``log`` and
``exp`` (Sun Microsystems, freely distributable), Goldberg's identity for ``log1p``, and Stirling's
series with an upward shift for ``lgamma`` (exact factorials for small integers). Measured against
a ``decimal`` oracle: ``log`` and ``exp`` within one unit in the last place, ``log1p`` within two,
``lgamma`` within 1e-14 of max(1, |value|). Tests check that and pin a digest of the bits.

One algorithm serves floats and NumPy arrays: a backend supplies ``frexp``, ``ldexp``, ``trunc``
and a branch-free ``select``, so the scalar and the array paths cannot drift apart.
"""

import math
from typing import Any

import numpy as np
from numpy.typing import NDArray

# fdlibm e_log.c: log(1 + f) = f - hfsq + s * (hfsq + R(z)), s = f / (2 + f), z = s * s.
_LN2_HI = 6.93147180369123816490e-01  # the upper bits of ln 2; k * _LN2_HI is exact for |k| < 2**20
_LN2_LO = 1.90821492927058770002e-10
_LG1 = 6.666666666666735130e-01
_LG2 = 3.999999999940941908e-01
_LG3 = 2.857142874366239149e-01
_LG4 = 2.222219843214978396e-01
_LG5 = 1.818357216161805012e-01
_LG6 = 1.531383769920937332e-01
_LG7 = 1.479819860511658591e-01
_SQRT_HALF = 0.7071067811865476

# fdlibm e_exp.c: exp(r) = 1 + r + r * c / (2 - c), c = r - r**2 * P(r**2), |r| <= ln(2) / 2.
_INV_LN2 = 1.44269504088896338700e00
_P1 = 1.66666666666666019037e-01
_P2 = -2.77777777770155933842e-03
_P3 = 6.61375632143793436117e-05
_P4 = -1.65339022054652515390e-06
_P5 = 4.13813679705723846039e-08
EXP_MAX = 709.78  # exp is refused above this (e**709.78 is just below the largest double)
EXP_MIN = -745.2  # and is 0.0 below this (e**-745.2 is under half the smallest subnormal)

# lgamma: exact factorials for small integers (170! is the largest finite double factorial), then
# Stirling's series for x >= _STIRLING_FROM with the Bernoulli terms B2k / (2k (2k - 1)).
_EXACT_FACTORIAL_UP_TO = 171.0
_STIRLING_FROM = 10.0
_HALF_LOG_2PI = 0.91893853320467274178
_STIRLING = (
    1.0 / 12.0,
    -1.0 / 360.0,
    1.0 / 1260.0,
    -1.0 / 1680.0,
    1.0 / 1188.0,
    -691.0 / 360360.0,
    1.0 / 156.0,
)


class _Floats:
    """Python floats: every operation is one correctly rounded IEEE 754 double operation."""

    frexp = staticmethod(math.frexp)

    @staticmethod
    def ldexp(mantissa: float, exponent: float) -> float:
        return math.ldexp(mantissa, int(exponent))

    @staticmethod
    def select(condition: bool, when_true: Any, when_false: Any) -> Any:
        return when_true if condition else when_false

    @staticmethod
    def trunc(x: float) -> float:
        return float(int(x))


class _Arrays:
    """NumPy float64 arrays: one elementwise ufunc per operation, each correctly rounded."""

    frexp = staticmethod(np.frexp)
    select = staticmethod(np.where)
    trunc = staticmethod(np.trunc)

    @staticmethod
    def ldexp(mantissa: NDArray[np.float64], exponent: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.ldexp(mantissa, exponent.astype(np.int32))


def _log(x: Any, b: Any) -> Any:
    """ln x for positive, finite x (already checked)."""
    m, e = b.frexp(x)  # x = m * 2**e with 0.5 <= m < 1
    low = m < _SQRT_HALF
    m = b.select(low, m * 2.0, m)  # now sqrt(1/2) <= m < sqrt(2)
    k = b.select(low, e - 1, e) * 1.0
    f = m - 1.0  # exact (Sterbenz)
    s = f / (2.0 + f)
    z = s * s
    r = z * (_LG1 + z * (_LG2 + z * (_LG3 + z * (_LG4 + z * (_LG5 + z * (_LG6 + z * _LG7))))))
    hfsq = 0.5 * f * f
    return k * _LN2_HI - ((hfsq - (s * (hfsq + r) + k * _LN2_LO)) - f)


def _log1p(x: Any, b: Any) -> Any:
    """ln(1 + x) for x > -1 (already checked): Goldberg's log(u) * x / (u - 1), u = 1 + x."""
    u = 1.0 + x
    d = u - 1.0
    exact = d == 0.0  # 1 + x rounded to 1, so ln(1 + x) rounds to x
    ratio = x / b.select(exact, 1.0, d)
    return b.select(exact, x, _log(b.select(exact, 1.0, u), b) * ratio)


def _exp(x: Any, b: Any) -> Any:
    """e**x for EXP_MIN <= x <= EXP_MAX (already checked)."""
    k = b.trunc(x * _INV_LN2 + b.select(x < 0.0, -0.5, 0.5))  # the nearest integer to x / ln 2
    hi = x - k * _LN2_HI
    lo = k * _LN2_LO
    r = hi - lo
    t = r * r
    c = r - t * (_P1 + t * (_P2 + t * (_P3 + t * (_P4 + t * _P5))))
    return b.ldexp(1.0 - ((lo - (r * c) / (2.0 - c)) - hi), k)


def _finite(x: float, name: str) -> float:
    if not isinstance(x, int | float) or not math.isfinite(x):
        raise ValueError(f"{name} needs a finite number, got {x!r}")
    return float(x)


def log(x: float) -> float:
    """The natural logarithm of a positive, finite number."""
    if _finite(x, "log") <= 0.0:
        raise ValueError(f"log needs a positive number, got {x!r}")
    return float(_log(float(x), _Floats))


def log1p(x: float) -> float:
    """ln(1 + x), accurate for small x, for finite x > -1."""
    if _finite(x, "log1p") <= -1.0:
        raise ValueError(f"log1p needs a number above -1, got {x!r}")
    return float(_log1p(float(x), _Floats))


def log1p_array(x: NDArray[np.float64]) -> NDArray[np.float64]:
    """Elementwise ln(1 + x) for a float64 array of finite values above -1; the bits of log1p."""
    values = np.asarray(x, dtype=np.float64)
    if not np.all(np.isfinite(values)) or np.any(values <= -1.0):
        raise ValueError("log1p_array needs finite numbers above -1")
    result: NDArray[np.float64] = _log1p(values, _Arrays)
    return result


def exp(x: float) -> float:
    """e**x for finite x; refused above EXP_MAX, 0.0 below EXP_MIN."""
    value = _finite(x, "exp")
    if value > EXP_MAX:
        raise OverflowError(f"exp({x!r}) is too large for a double")
    if value < EXP_MIN:
        return 0.0
    return float(_exp(value, _Floats))


def power(base: float, exponent: float) -> float:
    """base**exponent for a positive base, as exp(exponent * log(base))."""
    return exp(_finite(exponent, "power") * log(base))


def lgamma(x: float) -> float:
    """ln Gamma(x) for finite x > 0."""
    value = _finite(x, "lgamma")
    if value <= 0.0:
        raise ValueError(f"lgamma needs a positive number, got {x!r}")
    if value.is_integer() and value <= _EXACT_FACTORIAL_UP_TO:  # Gamma(n) = (n - 1)!, exactly
        return log(float(math.factorial(int(value) - 1)))
    product = 1.0
    while value < _STIRLING_FROM:  # Gamma(x) = Gamma(x + n) / (x (x + 1) ... (x + n - 1))
        product *= value
        value += 1.0
    z = 1.0 / value
    z2 = z * z
    series = 0.0
    for term in reversed(_STIRLING):
        series = term + z2 * series
    stirling = (value - 0.5) * log(value) - value + _HALF_LOG_2PI + z * series
    return stirling - log(product) if product != 1.0 else stirling
