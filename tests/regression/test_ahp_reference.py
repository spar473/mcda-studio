"""AHP against a published example, an independent eigensolver and an exact oracle.

Published sources, used as data under CC BY 4.0 with their citations:

- V. Kampourakis, G. Kavallieratos, G. Spathoulas, V. Gkioulos and S. Katsikas, "LLM-Assisted AHP
  for Explainable Cyber Range Evaluation", arXiv:2512.10487, 2025: the 10 x 10 matrix of
  Equation 7 and the weights of Table 2. Its table prints 0.317 for C1, while its text gives
  "approximately 0.316"; the eigenvector gives 0.31573.
- S. D. Nguyen, "Evaluating and Ranking Criteria for Mathematics Graduate Education Admissions
  through the Analytic Hierarchy Process", arXiv:2011.05376, 2020: Table 12, the random indices of
  Saaty and Tran (2007).

The independent eigensolver is LAPACK's QR algorithm (``numpy.linalg.eig``), a different
algorithm from the engine's power iteration. ``ahp_oracle`` is plain Python in exact fractions,
checked in a clean interpreter to load no ``mcda_studio`` module.
"""

import itertools
import math
import random
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

import ahp_oracle as oracle
import numpy as np
import pytest

from mcda_studio.domain.pairwise import (
    AhpModel,
    AlternativeJudgements,
    CriteriaJudgements,
    PairwiseJudgement,
)
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import AhpResult
from mcda_studio.methods.ahp.matrix import RANDOM_INDEX, RANDOM_INDEX_TABLE, analyse
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps

TOL = 1e-10

# ---- the published sources ---------------------------------------------------------------------
CYBER = [
    "1 2 7 5 7 7 7 5 9 7",
    "1/2 1 7 5 7 7 7 3 9 7",
    "1/7 1/7 1 1/3 1/3 2 3 1/3 3 3",
    "1/5 1/5 3 1 2 3 3 1/3 5 3",
    "1/7 1/7 3 1/2 1 3 3 1/3 5 3",
    "1/7 1/7 1/2 1/3 1/3 1 3 1/5 3 3",
    "1/7 1/7 1/3 1/3 1/3 1/3 1 1/5 3 2",
    "1/5 1/3 3 3 3 5 5 1 7 5",
    "1/9 1/9 1/3 1/5 1/5 1/3 1/3 1/7 1 1/3",
    "1/7 1/7 1/3 1/3 1/3 1/3 1/2 1/5 3 1",
]
#: Table 2 as printed, by criterion number; C1 is checked against the text's 0.316 instead.
CYBER_TABLE = {
    2: 0.254,
    8: 0.130,
    4: 0.079,
    5: 0.066,
    3: 0.046,
    6: 0.039,
    7: 0.028,
    10: 0.025,
    9: 0.016,
}
#: Table 12 as printed, n = 1 to 15.
NGUYEN_RI = [0, 0, 0.52, 0.89, 1.11, 1.25, 1.35, 1.40, 1.45, 1.49, 1.52, 1.54, 1.56, 1.58, 1.59]


def judgements_of(entries: list[list[Fraction]], items: list[str]) -> list[PairwiseJudgement]:
    """Each pair once, as the entry that is at least 1."""
    out = []
    for i, j in itertools.combinations(range(len(items)), 2):
        v = entries[i][j]
        row, column, value = (items[i], items[j], v) if v >= 1 else (items[j], items[i], 1 / v)
        out.append(PairwiseJudgement(row=row, column=column, value=float(value)))
    return out


def lapack(items: list[str], judgements: list[Any]) -> tuple[list[float], float]:
    """Priorities and λmax by LAPACK, from the same stored judgements."""
    rows = [dict(j) if isinstance(j, dict) else j.model_dump() for j in judgements]
    m = np.array([[float(x) for x in row] for row in oracle.matrix(items, rows)])
    values, vectors = np.linalg.eig(m)
    k = int(np.argmax(values.real))
    w = np.abs(vectors[:, k].real)
    return list(w / w.sum()), float(values[k].real)


def test_the_published_cyber_range_weights() -> None:
    entries = [[Fraction(x) for x in row.split()] for row in CYBER]
    items = [f"c{i + 1}" for i in range(10)]
    judgements = judgements_of(entries, items)
    a = analyse(items, judgements)
    for k, printed in CYBER_TABLE.items():
        assert abs(a.priorities[k - 1] - printed) <= 0.0005
    assert round(a.priorities[0], 3) == 0.316  # the text's value; the table's 0.317 is rounded up
    w, lam = lapack(items, judgements)
    assert abs(a.lambda_max - lam) <= TOL
    assert max(abs(x - y) for x, y in zip(a.priorities, w, strict=True)) <= TOL
    assert a.consistency_ratio == pytest.approx((lam - 10) / 9 / 1.49, abs=TOL)
    assert a.consistency_ratio < 0.10 and not a.inconsistent  # "well below 0.10", as printed
    assert a.triad is not None and a.triad.items == ("c1", "c5", "c9")


def test_the_random_index_table_is_the_printed_one() -> None:
    assert RANDOM_INDEX_TABLE == "saaty-tran-2007"
    assert list(RANDOM_INDEX) == NGUYEN_RI
    assert [float(Fraction(oracle.RANDOM_INDEX[n])) for n in range(1, 16)] == NGUYEN_RI


def test_the_oracle_imports_nothing_from_mcda_studio() -> None:
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import ahp_oracle; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] in ('mcda_studio', 'numpy')))"
    )
    run = subprocess.run(
        [sys.executable, "-I", "-c", code, str(Path(__file__).parent)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert run.stdout.strip() == "[]"


# ---- the engine against LAPACK -----------------------------------------------------------------
SCALE = [Fraction(v) for v in (1, 2, 3, 4, 5, 6, 7, 8, 9)]


def random_matrix(rng: random.Random, n: int) -> list[list[Fraction]]:
    m = [[Fraction(1)] * n for _ in range(n)]
    for i, j in itertools.combinations(range(n), 2):
        v = rng.choice(SCALE)
        m[i][j], m[j][i] = (v, 1 / v) if rng.random() < 0.5 else (1 / v, v)
    return m


@pytest.mark.parametrize("seed", range(120))
def test_the_engine_agrees_with_lapack(seed: int) -> None:
    rng = random.Random(seed)
    n = 3 + seed % 13
    items = [f"i{k}" for k in range(n)]
    judgements = judgements_of(random_matrix(rng, n), items)
    a = analyse(items, judgements)
    w, lam = lapack(items, judgements)
    assert abs(a.lambda_max - lam) <= TOL * n
    assert max(abs(x - y) for x, y in zip(a.priorities, w, strict=True)) <= TOL
    assert math.fsum(a.priorities) == pytest.approx(1.0, abs=1e-15)
    ci, ri, cr = oracle.consistency(lam, n)
    assert a.random_index == float(ri)
    assert a.consistency_index == pytest.approx(ci, abs=TOL)
    assert a.consistency_ratio == pytest.approx(cr, abs=TOL)
    assert a.inconsistent == (cr > 0.10)
    exact = oracle.matrix(items, [j.model_dump() for j in judgements])
    triad = oracle.most_inconsistent_triad(exact, items)
    assert triad is not None and a.triad is not None
    assert a.triad.items == triad[0]
    assert a.triad.index == pytest.approx(float(triad[1]), abs=1e-12)
    assert a.triad.consistent_value == pytest.approx(float(triad[2]), rel=1e-12)


@pytest.mark.parametrize(
    ("a", "b", "c"), [("3", "5", "4"), ("2", "9", "7"), ("9", "1/9", "9"), ("1", "1", "1")]
)
def test_the_closed_form_of_a_3_by_3_matrix(a: str, b: str, c: str) -> None:
    """λmax = 1 + t + 1/t with t = (ac/b)^(1/3) for entries a = M12, b = M13, c = M23."""
    x, y, z = Fraction(a), Fraction(b), Fraction(c)
    m = [[Fraction(1), x, y], [1 / x, Fraction(1), z], [1 / y, 1 / z, Fraction(1)]]
    items = ["x", "y", "z"]
    analysis = analyse(items, judgements_of(m, items))
    t = float(x * z / y) ** (1 / 3)
    assert analysis.lambda_max == pytest.approx(1 + t + 1 / t, abs=1e-12)


# ---- consistent hierarchies against the exact oracle -----------------------------------------
def consistent(rng: random.Random, items: list[str]) -> list[PairwiseJudgement]:
    """Judgements w_i / w_j from weights whose ratios are exact in binary floating point."""
    pool = rng.choice([(1, 2, 3, 6), (1, 2, 4, 8)])
    w = [Fraction(rng.choice(pool)) for _ in items]
    m = [[w[i] / w[j] for j in range(len(items))] for i in range(len(items))]
    return judgements_of(m, items)


def hierarchy(seed: int) -> Project:
    rng = random.Random(seed)
    p = ps.new_project("Hierarchy").model_copy(update={"id": "hierarchy"})
    alternatives = [f"a{k}" for k in range(rng.randint(2, 6))]
    for alt in alternatives:
        p = ps.add_alternative(p, alt.upper(), alt_id=alt)
    tops = [f"t{k}" for k in range(rng.randint(1, 4))]
    for t in tops:
        p = ps.add_criterion(p, t.upper(), crit_id=t)
    leaves_under: dict[str, list[str]] = {}
    for t in tops:
        count = rng.choice([0, 1, 2, 3])
        leaves_under[t] = [f"{t}_{k}" for k in range(count)]
        for leaf in leaves_under[t]:
            p = ps.add_criterion(p, leaf.upper(), crit_id=leaf, parent_id=t)
    tree = p.tree()
    groups = [None, *(i for i in tree.all_ids() if not tree.is_leaf(i))]
    criteria = [
        CriteriaJudgements(parent_id=g, judgements=consistent(rng, tree.child_ids(g)))
        for g in groups
        if len(tree.child_ids(g)) >= 2
    ]
    leaves = [
        AlternativeJudgements(criterion_id=leaf, judgements=consistent(rng, alternatives))
        for leaf in tree.leaves()
    ]
    return ps.set_ahp_model(p, AhpModel(criteria=criteria, alternatives=leaves))


def ahp(project: Project, synthesis: str = "distributive") -> AhpResult:
    cfg = project.analysis.model_copy(
        update={"method": "ahp", "parameters": {"synthesis": synthesis}}
    )
    result = svc.evaluate_project(project, cfg)
    assert isinstance(result, AhpResult)
    return result


def exact_priorities(items: list[str], judgements: list[dict[str, Any]]) -> list[Fraction]:
    return oracle.consistent_priorities(oracle.matrix(items, judgements))


@pytest.mark.parametrize("synthesis", ["distributive", "ideal"])
@pytest.mark.parametrize("seed", range(40))
def test_consistent_hierarchies_agree_with_the_exact_oracle(seed: int, synthesis: str) -> None:
    project = hierarchy(seed)
    raw = project.model_dump(mode="json")
    exact = oracle.evaluate(raw, exact_priorities, synthesis)  # type: ignore[arg-type]
    result = ahp(project, synthesis)
    for node, value in exact["local"].items():
        assert result.local_priorities[node] == pytest.approx(float(value), abs=1e-12)
    for leaf, value in exact["global"].items():
        assert result.global_priorities[leaf] == pytest.approx(float(value), abs=1e-12)
    by_id = {a.alternative_id: a for a in result.alternatives}
    for alt, value in exact["overall"].items():
        assert by_id[alt].priority == pytest.approx(float(value), abs=1e-12)
        if synthesis == "ideal":
            assert by_id[alt].ideal_score == pytest.approx(float(exact["ideal"][alt]), abs=1e-12)
        else:
            assert by_id[alt].ideal_score is None
    assert {a: by_id[a].rank for a in by_id} == oracle.ranks(exact["overall"])
    for m in result.matrices:
        assert m.consistency_index <= 1e-12 and m.consistency_ratio <= 1e-12 and not m.inconsistent
    assert math.fsum(result.global_priorities.values()) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("seed", range(20))
def test_inconsistent_hierarchies_agree_with_the_oracle_on_lapack_priorities(seed: int) -> None:
    project = hierarchy(seed)
    rng = random.Random(seed + 500)
    alternatives = project.alternative_ids()
    section = project.ahp
    assert section is not None
    for entry in section.alternatives:
        entry.judgements = judgements_of(random_matrix(rng, len(alternatives)), alternatives)
    project = ps.set_ahp_model(project, section)
    raw = project.model_dump(mode="json")
    for synthesis in ("distributive", "ideal"):
        expected = oracle.evaluate(raw, lambda i, j: lapack(i, j)[0], synthesis)
        result = ahp(project, synthesis)
        for a in result.alternatives:
            assert a.priority == pytest.approx(
                float(expected["overall"][a.alternative_id]), abs=TOL
            )
