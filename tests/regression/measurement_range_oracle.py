"""Independent numerical oracle for a one-criterion piecewise-linear model.

No application imports. NumPy interpolates values; SciPy locates the tolerance
threshold numerically, independently of the engine's rational segment inversion.
"""

import numpy as np
from scipy.optimize import brentq


def rank(x: float, other: float, xs: list[float], values: list[float]) -> int:
    return 1 + int(float(np.interp(other, xs, values)) > float(np.interp(x, xs, values)) + 1e-12)


def contact(other: float, xs: list[float], values: list[float]) -> float | None:
    threshold = float(np.interp(other, xs, values)) - 1e-12

    def gap(x: float) -> float:
        return float(np.interp(x, xs, values)) - threshold

    if gap(xs[0]) * gap(xs[-1]) > 0:
        return None
    return float(brentq(gap, xs[0], xs[-1], xtol=5e-15, rtol=1e-15))
