"""One AHP matrix: its reciprocal entries, principal eigenvector, consistency and most inconsistent
triad (design note §2).

The eigenvector comes from power iteration in plain Python with ``math.fsum``; a matrix that does
not converge within the cap is an error, never a partial result. Random indices are Saaty and Tran
(2007) for 1 to 15 items, as printed in Nguyen (2020), arXiv:2011.05376, Table 12.
"""

import math
from dataclasses import dataclass
from itertools import combinations

from mcda_studio.domain.common import Issue, Severity
from mcda_studio.domain.errors import ConvergenceError
from mcda_studio.domain.pairwise import PairwiseJudgement

RANDOM_INDEX_TABLE = "saaty-tran-2007"
#: RI for n = 1 to 15 items; RANDOM_INDEX[n - 1] is the index for n items.
RANDOM_INDEX = (
    0.0, 0.0, 0.52, 0.89, 1.11, 1.25, 1.35, 1.40, 1.45, 1.49, 1.52, 1.54, 1.56, 1.58, 1.59
)  # fmt: skip
MAX_ITEMS = len(RANDOM_INDEX)
TOLERANCE = 1e-14
MAX_ITERATIONS = 10_000
CR_THRESHOLD = 0.10


@dataclass(frozen=True)
class Triad:
    items: tuple[str, str, str]
    judgements: tuple[float, float, float]  # M[i][j], M[j][k], M[i][k]
    index: float  # Koczkodaj's triad index
    consistent_value: float  # M[i][j] * M[j][k]: the M[i][k] that would make the triad consistent


@dataclass(frozen=True)
class MatrixAnalysis:
    items: list[str]
    priorities: list[float]  # in item order; sum to 1
    lambda_max: float
    consistency_index: float
    random_index: float
    consistency_ratio: float
    inconsistent: bool
    triad: Triad | None
    iterations: int


def random_index(n: int) -> float:
    return RANDOM_INDEX[n - 1]


def matrix_issues(items: list[str], judgements: list[PairwiseJudgement], where: str) -> list[Issue]:
    """The rules for one matrix: known items, one judgement per pair, values from 1 to 9, and every
    pair judged. Shared by validation and the read-only preview."""
    issues: list[Issue] = []

    def add(code: str, message: str, path: str = where) -> None:
        issues.append(Issue(severity=Severity.ERROR, code=code, message=message, path=path))

    if len(items) > MAX_ITEMS:
        add(
            "AHP_TOO_MANY_ITEMS",
            f"{len(items)} items: a matrix holds at most {MAX_ITEMS}, the limit of the "
            "random-index table",
        )
    known = set(items)
    seen: set[frozenset[str]] = set()
    for j in judgements:
        at = f"{where}.judgements[{j.row},{j.column}]"
        if j.row not in known or j.column not in known:
            add("UNKNOWN_AHP_ITEM", f"{j.row!r} or {j.column!r} is not an item of this matrix", at)
            continue
        if j.row == j.column:
            add("SELF_JUDGEMENT", f"{j.row!r} is compared with itself", at)
            continue
        pair = frozenset((j.row, j.column))
        if pair in seen:
            add("DUPLICATE_JUDGEMENT", "this pair is judged more than once", at)
            continue
        seen.add(pair)
        if not 1.0 <= j.value <= 9.0:
            hint = "; to favour the column, swap row and column" if 0 < j.value < 1 else ""
            add("INVALID_JUDGEMENT", f"the value {j.value!r} must lie from 1 to 9{hint}", at)
    missing = [
        f"{a}/{b}" for a, b in combinations(items, 2) if frozenset((a, b)) not in seen and a != b
    ]
    if missing:
        add("AHP_JUDGEMENT_MISSING", f"pairs not judged: {', '.join(missing)}")
    return issues


def build_matrix(items: list[str], judgements: list[PairwiseJudgement]) -> list[list[float]]:
    """The reciprocal matrix of a validated, complete set of judgements."""
    index = {item: k for k, item in enumerate(items)}
    n = len(items)
    m = [[1.0] * n for _ in range(n)]
    for j in judgements:
        r, c = index[j.row], index[j.column]
        m[r][c] = j.value
        m[c][r] = 1.0 / j.value
    return m


def _multiply(m: list[list[float]], w: list[float]) -> list[float]:
    return [math.fsum(a * b for a, b in zip(row, w, strict=True)) for row in m]


def principal_eigenvector(m: list[list[float]]) -> tuple[list[float], float, int]:
    """Power iteration from the uniform vector, scaled by its largest entry at every step; then
    normalised to sum to 1. Returns the priorities, λmax = Σ (Mw)ᵢ and the iterations."""
    n = len(m)
    w = [1.0] * n
    for iteration in range(1, MAX_ITERATIONS + 1):
        v = _multiply(m, w)
        top = max(v)
        v = [x / top for x in v]
        if max(abs(a - b) for a, b in zip(v, w, strict=True)) <= TOLERANCE:
            total = math.fsum(v)
            w = [x / total for x in v]
            return w, math.fsum(_multiply(m, w)), iteration
        w = v
    raise ConvergenceError(
        f"the principal eigenvector did not converge within {MAX_ITERATIONS} "
        "iterations; no priorities are reported"
    )


def most_inconsistent_triad(m: list[list[float]], items: list[str]) -> Triad | None:
    """Koczkodaj's index over every triple i < j < k; the first largest in item order."""
    best: Triad | None = None
    for i, j, k in combinations(range(len(items)), 3):
        x, y, z = m[i][j], m[j][k], m[i][k]
        index = min(abs(1 - z / (x * y)), abs(1 - x * y / z))
        if best is None or index > best.index:
            best = Triad((items[i], items[j], items[k]), (x, y, z), index, x * y)
    return best


def analyse(items: list[str], judgements: list[PairwiseJudgement]) -> MatrixAnalysis:
    """Priorities and consistency of a validated, complete matrix."""
    n = len(items)
    m = build_matrix(items, judgements)
    if n == 1:
        priorities, lam, iterations = [1.0], 1.0, 0
    elif n == 2:
        v = m[0][1]  # a 2 x 2 reciprocal matrix is always consistent: no iteration, CI = 0
        priorities, lam, iterations = [v / (1 + v), 1 / (1 + v)], 2.0, 0
    else:
        priorities, lam, iterations = principal_eigenvector(m)
    ci = max(0.0, (lam - n) / (n - 1)) if n >= 3 else 0.0
    ri = random_index(n)
    cr = ci / ri if n >= 3 else 0.0
    return MatrixAnalysis(
        items=list(items),
        priorities=priorities,
        lambda_max=lam,
        consistency_index=ci,
        random_index=ri,
        consistency_ratio=cr,
        inconsistent=cr > CR_THRESHOLD,
        triad=most_inconsistent_triad(m, items) if n >= 3 else None,
        iterations=iterations,
    )
