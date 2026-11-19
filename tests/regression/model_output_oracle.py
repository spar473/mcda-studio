"""Independent exact calculations and declared-range checks. No application imports."""

from fractions import Fraction
from itertools import product


def bottom_up(customers, adoption, price):
    return Fraction(str(customers)) * Fraction(str(adoption)) * Fraction(str(price))


def top_down(total, share):
    return Fraction(str(total)) * Fraction(str(share))


def segment_sum(segments, overlap=0):
    return sum((Fraction(str(v)) for v in segments), Fraction()) - Fraction(str(overlap))


def convert(value, rate):
    return Fraction(str(value)) * Fraction(str(rate))


def exact_values(customers, adoption, prices):
    return sorted({bottom_up(c, a, p) for c, a, p in product(customers, adoption, prices)})


def linear_quantile(values, numerator, denominator):
    ordered = sorted(Fraction(str(v)) for v in values)
    position = Fraction(numerator, denominator) * (len(ordered) - 1)
    index = position.numerator // position.denominator
    fraction = position - index
    return (
        ordered[index]
        if not fraction
        else ordered[index] + fraction * (ordered[index + 1] - ordered[index])
    )


def allowed(value, lower, upper, lower_inclusive=True, upper_inclusive=True):
    v = Fraction.from_float(float(value))
    lo = Fraction.from_float(float(lower)) if lower is not None else None
    hi = Fraction.from_float(float(upper)) if upper is not None else None
    return (lo is None or (v >= lo if lower_inclusive else v > lo)) and (
        hi is None or (v <= hi if upper_inclusive else v < hi)
    )


def bottom_up_bound(customers, adoption, price):
    from regression.rounding_oracle import evaluate

    return evaluate(
        "customers * adoption * price", dict(customers=customers, adoption=adoption, price=price)
    )


def linear_quantile_bound(values, numerator, denominator):
    from regression.rounding_oracle import Bounded

    q = Bounded.input(str(float(Fraction(numerator, denominator))))
    position = q * Bounded.input(len(values) - 1)
    exact_position = Fraction(numerator, denominator) * (len(values) - 1)
    index = exact_position.numerator // exact_position.denominator
    if not index <= position.exact - position.error <= position.exact + position.error < index + 1:
        raise ValueError("quantile position uncertainty crosses an order-statistic boundary")
    ordered = sorted(values)
    lower, upper = Bounded.input(ordered[index]), Bounded.input(ordered[index + 1])
    fraction = position - Bounded.input(index)
    # Both algebraic interpolation branches have this exact decimal target. Bound either
    # possible branch's rounding without assuming reassociation or fused operations.
    left = lower + (upper - lower) * fraction
    right = upper - (upper - lower) * (Bounded.input(1) - fraction)
    exact = linear_quantile(values, numerator, denominator)
    error = max(left.error + abs(left.exact - exact), right.error + abs(right.exact - exact))
    return Bounded(exact, error)
