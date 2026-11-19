"""The portable elementary functions: accuracy against a decimal oracle, refusals, the scalar and
array paths agreeing bit for bit, and pinned digests of the bits.

The digests are the cross-platform check: they were computed once, and every platform that runs
this file must reproduce them exactly. A platform whose arithmetic differs fails here first.
"""

import hashlib
import math
import random
import struct
from decimal import Decimal, localcontext

import numpy as np
import pytest

from mcda_studio.methods import portable
from mcda_studio.methods.smaa.intervals import clopper_pearson

# sqrt(pi) to 40 digits, for Gamma(n + 1/2) = (2n)! sqrt(pi) / (4**n n!).
SQRT_PI = Decimal("1.772453850905516027298167483341145182798")


def ulps(value: float, reference: Decimal) -> float:
    """Distance from the exact value in units in the last place of the correctly rounded one."""
    nearest = float(reference)
    return float(abs(Decimal(value) - reference) / Decimal(math.ulp(nearest)))


def grid(seed: int) -> dict[str, list[float]]:
    rng = random.Random(seed)
    return {
        "log": [rng.uniform(1e-3, 10.0) for _ in range(1500)]
        + [10.0 ** rng.uniform(-300, 300) for _ in range(1500)]
        + [1.0 + rng.uniform(-1e-6, 1e-6) for _ in range(300)]
        + [5e-324, 2.2250738585072014e-308, 1.7976931348623157e308, 1.0, 2.0, 0.5],
        "log1p": [rng.uniform(-0.999999, 5.0) for _ in range(1500)]
        + [rng.uniform(-1e-9, 1e-9) for _ in range(500)]
        + [-1.0 + 2.0**-52, 1e-300, -1e-300, 5e-324, 2.0**-53, -(2.0**-54), 0.0],
        "exp": [rng.uniform(-708.0, 709.7) for _ in range(2000)]
        + [rng.uniform(-1.0, 1.0) for _ in range(1000)]
        + [0.0, 1e-20, -1e-20, 709.78, -745.0],
    }


@pytest.mark.parametrize("seed", [1, 2])
def test_log_log1p_and_exp_are_within_two_ulps_of_the_exact_value(seed: int) -> None:
    points = grid(seed)
    with localcontext() as context:
        context.prec = 700  # enough that 1 + 1e-300 is exact
        worst_log = max(ulps(portable.log(x), Decimal(x).ln()) for x in points["log"])
        worst_log1p = max(
            ulps(portable.log1p(x), (Decimal(1) + Decimal(x)).ln()) if x else 0.0
            for x in points["log1p"]
        )
        context.prec = 60
        worst_exp = max(ulps(portable.exp(x), Decimal(x).exp()) for x in points["exp"])
    assert worst_log <= 1.0
    assert worst_log1p <= 2.0
    assert worst_exp <= 1.0


def test_exact_cases() -> None:
    assert portable.log(1.0) == 0.0
    assert portable.log1p(0.0) == 0.0
    assert portable.log1p(1e-300) == 1e-300  # 1 + x rounds to 1, so ln(1 + x) rounds to x
    assert portable.exp(0.0) == 1.0
    assert portable.exp(-746.0) == 0.0
    assert portable.lgamma(1.0) == 0.0 and portable.lgamma(2.0) == 0.0
    assert portable.power(0.25, 0.5) == pytest.approx(0.5, abs=1e-16)


def test_lgamma_at_integers_and_half_integers_against_exact_factorials() -> None:
    with localcontext() as context:
        context.prec = 60
        for n in [*range(1, 400), 1000, 12345, 99_999, 100_000, 100_001]:
            exact = Decimal(math.factorial(n - 1)).ln()
            error = abs(Decimal(portable.lgamma(float(n))) - exact)
            assert error <= Decimal("2e-15") * max(Decimal(1), abs(exact)), n
            if n <= 171:  # computed from the exact factorial: within an ulp or two
                assert ulps(portable.lgamma(float(n)), exact) <= 2.0 or exact == 0, n
        for n in range(0, 200):
            exact = (
                Decimal(math.factorial(2 * n)) * SQRT_PI / (Decimal(4) ** n * math.factorial(n))
            ).ln()
            error = abs(Decimal(portable.lgamma(n + 0.5)) - exact)
            assert error <= Decimal("1e-14") * max(Decimal(1), abs(exact)), n


def test_lgamma_agrees_with_the_platform_library_away_from_integers() -> None:
    rng = random.Random(3)
    for x in [rng.uniform(1e-6, 300.0) for _ in range(3000)] + [1e-300, 5e-324, 1e6 + 0.25]:
        expected = math.lgamma(x)
        assert abs(portable.lgamma(x) - expected) <= 1e-14 * max(1.0, abs(expected)), x


@pytest.mark.parametrize(
    ("call", "argument", "error"),
    [
        (portable.log, 0.0, ValueError),
        (portable.log, -1.0, ValueError),
        (portable.log, math.inf, ValueError),
        (portable.log, math.nan, ValueError),
        (portable.log1p, -1.0, ValueError),
        (portable.log1p, -2.0, ValueError),
        (portable.log1p, math.nan, ValueError),
        (portable.exp, 709.79, OverflowError),
        (portable.exp, math.inf, ValueError),
        (portable.exp, -math.inf, ValueError),
        (portable.lgamma, 0.0, ValueError),
        (portable.lgamma, -0.5, ValueError),
        (portable.lgamma, math.inf, ValueError),
    ],
)
def test_refusals(call, argument: float, error: type[Exception]) -> None:
    with pytest.raises(error):
        call(argument)


def test_log1p_array_refuses_values_outside_its_domain() -> None:
    for bad in ([-1.0], [0.5, math.nan], [math.inf]):
        with pytest.raises(ValueError):
            portable.log1p_array(np.array(bad))


def test_the_array_path_has_the_bits_of_the_scalar_path() -> None:
    rng = np.random.Generator(np.random.PCG64(11))
    u = np.concatenate([rng.random(20_000), [0.0, 1e-300, 2.0**-53, 0.5, 1.0 - 2.0**-53]])
    array = portable.log1p_array(-u)
    scalar = np.array([portable.log1p(-x) for x in u.tolist()])
    assert np.array_equal(array.view(np.uint64), scalar.view(np.uint64))
    two_d = portable.log1p_array(-u[:20_000].reshape(100, 200))
    assert np.array_equal(two_d.ravel().view(np.uint64), array[:20_000].view(np.uint64))


def _digest(values: list[float]) -> str:
    return hashlib.sha256(struct.pack(f"<{len(values)}d", *values)).hexdigest()


def pinned_values() -> dict[str, list[float]]:
    points = grid(7)
    lgamma_points = (
        [float(n) for n in range(1, 300)]
        + [x * 0.37 for x in range(1, 2000)]
        + [12345.0, 99_999.0, 100_001.0]
    )
    powers = [(a / 1000.0, 1.0 / n) for a in range(1, 200) for n in (1, 7, 1000, 100_000)]
    rng = np.random.Generator(np.random.PCG64(5))
    return {
        "log": [portable.log(x) for x in points["log"]],
        "log1p": [portable.log1p(x) for x in points["log1p"]],
        "exp": [portable.exp(x) for x in points["exp"]],
        "lgamma": [portable.lgamma(x) for x in lgamma_points],
        "power": [portable.power(a, e) for a, e in powers],
        "log1p_array": portable.log1p_array(-rng.random(50_000)).tolist(),
    }


#: Computed on 16 November 2026 (Linux x86_64 and native Windows x86_64 agree). Never update a
#: digest to make a platform pass: a mismatch means that platform's arithmetic differs.
PINNED = {
    "log": "793713ca0ba7e4c972a8a588eaec1e0ed5bbb01d82014264fdb47806b2e2eb4c",
    "log1p": "d77b829836181ab5bc9b2a8407bfe6ae594365c51a3bf792090e3ddf95872753",
    "exp": "a10875b3a5a46d083569a2eebf7da71debfde264c9de47ea0d5644229147318e",
    "lgamma": "66224d6b141010c4ee295073bd8ad38655af30f627b86cd6cd3844a413d20edd",
    "power": "c4d1b58ce5cb77c8bd6dbaaa686fc83c59f33e3fb78ee8d591ba4d9a521b92f4",
    "log1p_array": "4875793e9269b7f03a3c76e396d06badde31126c847f670651f5add435bd3001",
}


@pytest.mark.parametrize("name", sorted(PINNED))
def test_the_bits_match_the_pinned_digests(name: str) -> None:
    assert _digest(pinned_values()[name]) == PINNED[name]


def test_the_intervals_call_no_platform_maths_function(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clopper-Pearson bounds use only ``portable``: the C library's functions round differently
    on different platforms, even where this platform's happen to agree."""

    def refused(*args: object) -> float:
        raise AssertionError("a platform maths function was called")

    for name in ("exp", "expm1", "log", "log1p", "log2", "log10", "lgamma", "gamma", "pow"):
        monkeypatch.setattr(math, name, refused)
    clopper_pearson.cache_clear()
    try:
        for k, n in [(0, 10), (3, 10), (10, 10), (5, 10_000), (5_000, 10_000), (1, 100_000)]:
            lower, upper = clopper_pearson(k, n, 0.95)
            assert 0.0 <= lower <= upper <= 1.0
    finally:
        clopper_pearson.cache_clear()  # no bound computed under the patch is kept
