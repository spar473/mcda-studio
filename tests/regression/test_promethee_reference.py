"""PROMETHEE II against published examples and an independent oracle.

Published examples, used as data under CC BY 4.0 with their citations:

- V. Podvezko and A. Podviezko, "Dependence of multi-criteria evaluation result on choice of
  preference functions and their parameters", Technological and Economic Development of Economy
  16(1), 143-158, 2010, doi:10.3846/tede.2010.09. Table 3, variants 2 (usual), 3 (U-shape),
  4 (V-shape) and 6 (linear). The paper sums preference indices without dividing by n - 1, so its
  flows are 3 times ours (n = 4).
- A. Flachs and Y. De Smet, "From outranking flow scores to linear programs: group decision making
  in PROMETHEE II", arXiv:2610.34481v1, 2026, Appendix A.

``promethee_oracle`` is plain Python in exact fractions, checked in a clean interpreter to load no
``mcda_studio`` module; it is checked against both examples, then against the engine.
"""

import random
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import promethee_oracle as oracle
import pytest

from mcda_studio.domain.outranking import (
    AnyPreferenceFunction,
    LinearPreferenceFunction,
    PrometheeCriterion,
    PrometheeModel,
    UShapeFunction,
    UsualFunction,
    VShapeFunction,
)
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import PrometheeResult
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps

TOL = 1e-12


def promethee(project: Project) -> PrometheeResult:
    cfg = project.analysis.model_copy(update={"method": "promethee2", "parameters": {}})
    result = svc.evaluate_project(project, cfg)
    assert isinstance(result, PrometheeResult)
    return result


def build(
    alternatives: dict[str, list[float | str]],
    criteria: list[tuple[str, str, float, AnyPreferenceFunction]],
    scales: dict[int, Scale] | None = None,
    codings: dict[int, dict[str, float]] | None = None,
) -> Project:
    """Flat leaves c1.. with (name, direction, weight, function); interval scales by default."""
    p = ps.new_project("Reference").model_copy(update={"id": "reference"})
    for alt in alternatives:
        p = ps.add_alternative(p, alt.title(), alt_id=alt)
    for j, (name, _, _, _) in enumerate(criteria):
        scale = (scales or {}).get(j, Scale(type=ScaleType.INTERVAL))
        p = ps.add_criterion(p, name, crit_id=f"c{j + 1}", scale=scale)
    for alt, row in alternatives.items():
        for j, value in enumerate(row):
            p = ps.set_performance(p, alt, f"c{j + 1}", value)
    model = PrometheeModel(
        criteria=[
            PrometheeCriterion(
                criterion_id=f"c{j + 1}",
                direction=direction,  # type: ignore[arg-type]
                weight=weight,
                function=function,
                coding=(codings or {}).get(j),
            )
            for j, (_, direction, weight, function) in enumerate(criteria)
        ]
    )
    return ps.set_promethee_model(p, model)


# ---- Podvezko and Podviezko (2010) ----------------------------------------------------------
COUNTRIES = ["estonia", "latvia", "lithuania", "poland"]
BALTIC = {
    "estonia": [5.1, 9.8, 430.0, 9.3, 0.70],
    "latvia": [7.5, 6.5, 298.0, 10.3, 0.55],
    "lithuania": [9.7, 16.1, 306.0, 11.6, 0.73],
    "poland": [3.8, 8.4, 501.0, 19.3, 0.79],
}
BALTIC_WEIGHTS = [0.28, 0.19, 0.15, 0.18, 0.20]
BALTIC_DIRECTIONS = ["maximise", "maximise", "maximise", "minimise", "maximise"]
VARIANTS: dict[str, list[AnyPreferenceFunction]] = {
    "2 usual": [UsualFunction()] * 5,
    "3 U-shape": [UShapeFunction(q=q) for q in (2.5, 2.0, 150.0, 2.2, 0.1)],
    "4 V-shape": [VShapeFunction(p=p) for p in (5.0, 8.0, 100.0, 10.0, 0.1)],
    "6 linear": [
        LinearPreferenceFunction(q=q, p=p)
        for q, p in ((2.5, 5.0), (2.0, 8.0), (130.0, 195.0), (2.3, 10.0), (0.06, 0.15))
    ],
}
#: Table 3 as printed, Estonia, Latvia, Lithuania, Poland: (3 F+, 3 F-, 3 F, decimals, ranks).
PRINTED: dict[str, tuple[list[float], list[float], list[float], int, list[int]]] = {
    "2 usual": (
        [1.70, 0.92, 2.14, 1.24],
        [1.30, 2.08, 0.86, 1.76],
        [0.40, -1.16, 1.28, -0.52],
        2,
        [2, 4, 1, 3],
    ),
    "3 U-shape": (
        [0.75, 0.46, 1.51, 0.50],
        [0.47, 1.13, 0.33, 1.29],
        [0.28, -0.67, 1.18, -0.79],
        2,
        [2, 3, 1, 4],
    ),
    "4 V-shape": (
        [0.924, 0.527, 1.594, 0.952],
        [0.888, 1.367, 0.485, 1.257],
        [0.036, -0.840, 1.109, -0.305],
        3,
        [2, 4, 1, 3],
    ),
    "6 linear": (
        [0.426, 0.291, 1.348, 0.567],
        [0.438, 0.986, 0.150, 1.058],
        [-0.012, -0.695, 1.198, -0.491],
        3,
        [2, 4, 1, 3],
    ),
}


def baltic(variant: str) -> Project:
    functions = VARIANTS[variant]
    return build(
        BALTIC,  # type: ignore[arg-type]
        [
            (f"criterion {j + 1}", BALTIC_DIRECTIONS[j], BALTIC_WEIGHTS[j], functions[j])
            for j in range(5)
        ],
        scales={j: Scale(type=ScaleType.RATIO) for j in range(5)},
    )


def flachs_de_smet() -> Project:
    return build(
        {"a": [-2.0, 2.0], "b": [0.0, 0.0], "c": [1.0, -2.0], "d": [2.0, 1.0]},
        [
            ("g1", "maximise", 0.2, UsualFunction()),
            ("g2", "maximise", 0.8, LinearPreferenceFunction(q=1.0, p=3.0)),
        ],
    )


@pytest.mark.parametrize("variant", list(VARIANTS))
def test_podvezko_variants_reproduce_the_printed_flows_and_ranks(variant: str) -> None:
    plus, minus, net, decimals, printed_ranks = PRINTED[variant]
    half = 0.5 * 10**-decimals
    result = promethee(baltic(variant))
    by_id = {f.alternative_id: f for f in result.flows}
    for k, country in enumerate(COUNTRIES):
        f = by_id[country]
        assert abs(3 * f.positive_flow - plus[k]) <= half
        assert abs(3 * f.negative_flow - minus[k]) <= half
        assert abs(3 * f.net_flow - net[k]) <= half
        assert f.rank == printed_ranks[k]


@pytest.mark.parametrize("variant", list(VARIANTS))
def test_the_oracle_reproduces_the_printed_values_before_it_checks_the_engine(
    variant: str,
) -> None:
    plus, minus, net, decimals, printed_ranks = PRINTED[variant]
    exact = oracle.flows(baltic(variant).model_dump(mode="json"))
    half = Fraction(1, 2 * 10**decimals)
    for k, country in enumerate(COUNTRIES):
        assert abs(3 * exact["positive"][country] - Fraction(str(plus[k]))) <= half
        assert abs(3 * exact["negative"][country] - Fraction(str(minus[k]))) <= half
        assert abs(3 * exact["net"][country] - Fraction(str(net[k]))) <= half
    assert [oracle.ranks(exact["net"])[c] for c in COUNTRIES] == printed_ranks


def test_variant_6_hits_its_threshold_exactly_and_counts_no_preference() -> None:
    """Poland and Lithuania differ by exactly q5 = 0.06 on criterion 5; in binary floating point
    0.79 - 0.73 is 0.06000000000000005, and without the tolerance this would be a preference."""
    assert 0.79 - 0.73 > 0.06
    result = promethee(baltic("6 linear"))
    exact = oracle.flows(baltic("6 linear").model_dump(mode="json"))
    assert exact["degrees"]["c5"]["poland", "lithuania"] == 0
    poland = next(f for f in result.flows if f.alternative_id == "poland")
    assert abs(poland.positive_flow - float(exact["positive"]["poland"])) <= TOL


def test_flachs_de_smet_net_flows_exactly() -> None:
    printed = {"a": 0.2, "b": -0.067, "c": -0.6, "d": 0.467}
    exact = oracle.flows(flachs_de_smet().model_dump(mode="json"))
    assert exact["net"] == {
        "a": Fraction(1, 5),
        "b": Fraction(-1, 15),
        "c": Fraction(-3, 5),
        "d": Fraction(7, 15),
    }
    result = promethee(flachs_de_smet())
    for f in result.flows:
        assert round(f.net_flow, 3) == printed[f.alternative_id]
        assert abs(f.net_flow - float(exact["net"][f.alternative_id])) <= TOL
    assert [f.alternative_id for f in result.flows] == ["d", "a", "b", "c"]


def test_the_oracle_imports_nothing_from_mcda_studio() -> None:
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import promethee_oracle; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] == 'mcda_studio'))"
    )
    run = subprocess.run(
        [sys.executable, "-I", "-c", code, str(Path(__file__).parent)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert run.stdout.strip() == "[]"


# ---- the engine against the oracle on generated cases -----------------------------------------
LABELS = ["low", "medium", "high", "top"]


def generated(seed: int) -> Project:
    """Values and thresholds on a 0.1 grid, so ties and differences equal to q or p are common."""
    rng = random.Random(seed)
    n = rng.randint(2, 7)
    leaves = rng.randint(1, 5)
    alts = [f"x{i}" for i in range(n)]
    criteria: list[tuple[str, str, float, AnyPreferenceFunction]] = []
    scales: dict[int, Scale] = {}
    codings: dict[int, dict[str, float]] = {}
    rows: dict[str, list[float | str]] = {a: [] for a in alts}
    for j in range(leaves):
        labelled = rng.random() < 0.3
        if labelled:
            kind = rng.choice([ScaleType.ORDINAL, ScaleType.CATEGORICAL])
            scales[j] = Scale(type=kind, labels=LABELS)
            codings[j] = {label: round(rng.randint(0, 30) / 10, 1) for label in LABELS}
            for a in alts:
                rows[a].append(rng.choice(LABELS))
        else:
            for a in alts:
                rows[a].append(round(rng.randint(-20, 40) / 10, 1))
        q = round(rng.randint(0, 15) / 10, 1)
        p = round(q + rng.randint(1, 15) / 10, 1)
        function = rng.choice(
            [
                UsualFunction(),
                UShapeFunction(q=q),
                VShapeFunction(p=p),
                LinearPreferenceFunction(q=q, p=p),
            ]
        )
        direction = rng.choice(["maximise", "minimise"])
        weight = float(rng.randint(0, 5)) if j else float(rng.randint(1, 5))
        criteria.append((f"criterion {j}", direction, weight, function))
    return build(rows, criteria, scales, codings)


@pytest.mark.parametrize("seed", range(60))
def test_the_engine_agrees_with_the_oracle(seed: int) -> None:
    project = generated(seed)
    exact = oracle.flows(project.model_dump(mode="json"))
    result = promethee(project)
    for f in result.flows:
        a = f.alternative_id
        assert abs(f.positive_flow - float(exact["positive"][a])) <= TOL
        assert abs(f.negative_flow - float(exact["negative"][a])) <= TOL
        assert abs(f.net_flow - float(exact["net"][a])) <= TOL
        for leaf, value in f.criterion_flows.items():
            assert abs(value - float(exact["criterion"][leaf][a])) <= TOL
    for (a, b), value in exact["preference"].items():
        assert abs(result.preference_matrix[a][b] - float(value)) <= TOL
    ranks = oracle.ranks(exact["net"])
    assert {f.alternative_id: f.rank for f in result.flows} == ranks
    assert [r.alternative_id for r in result.ranking] == [f.alternative_id for f in result.flows]
    for pair in result.partial_order:
        expected = oracle.relation(exact, pair.alternative_a, pair.alternative_b)
        assert expected == ("a" if pair.relation == "preferred" else pair.relation)
    assert (
        len(result.partial_order)
        == len(exact["alternatives"]) * (len(exact["alternatives"]) - 1) // 2
    )


@pytest.mark.parametrize("seed", range(60))
def test_invariants_hold_on_every_generated_case(seed: int) -> None:
    result = promethee(generated(seed))
    weights = {c.criterion_id: c.normalised_weight for c in result.criteria}
    assert abs(sum(f.net_flow for f in result.flows)) <= len(result.flows) * TOL
    for f in result.flows:
        assert 0 <= f.positive_flow <= 1 and 0 <= f.negative_flow <= 1 and -1 <= f.net_flow <= 1
        assert f.net_flow == f.positive_flow - f.negative_flow
        by_criterion = sum(weights[j] * v for j, v in f.criterion_flows.items())
        assert abs(f.net_flow - by_criterion) <= TOL


def mavt_disagreeing(seed: int) -> Project:
    """A generated case with MAVT weights and value functions of its own, so pairs can differ."""
    from mcda_studio.domain.criteria import (
        DirectRatingValueFunction,
        QualitativeValueFunction,
    )

    project = generated(seed)
    rng = random.Random(seed + 1000)
    for node in project.tree().leaves():
        scale = project.tree().node(node).scale
        assert scale is not None
        if scale.is_labelled:
            values = sorted(rng.sample(range(1, 10), len(LABELS) - 2))
            mapping = dict(zip(LABELS, [0.0, *(v / 10 for v in values), 1.0], strict=True))
            function = QualitativeValueFunction(mapping=mapping)
        else:
            function = DirectRatingValueFunction(min_rating=-2.0, max_rating=4.0)
        project = ps.set_value_function(project, node, function)  # type: ignore[arg-type]
        project = ps.set_judgement(project, node, float(rng.randint(1, 100)))
    return project


@pytest.mark.parametrize("seed", range(40))
def test_the_explanation_split_agrees_with_the_oracle(seed: int) -> None:
    project = mavt_disagreeing(seed)
    exact = oracle.flows(project.model_dump(mode="json"))
    result = promethee(project)
    explanation = result.explanation
    assert explanation.available, explanation.unavailable_reason
    mavt = {r.alternative_id: r.mavt_rank for r in explanation.ranks}
    prom = {r.alternative_id: r.promethee_rank for r in explanation.ranks}
    expected = {
        frozenset((a, b))
        for a in mavt
        for b in mavt
        if a < b
        and (mavt[a] > mavt[b]) - (mavt[a] < mavt[b]) != (prom[a] > prom[b]) - (prom[a] < prom[b])
    }
    assert {frozenset((p.alternative_a, p.alternative_b)) for p in explanation.pairs} == expected
    for pair in explanation.pairs:
        gap, head, via = oracle.split(exact, pair.alternative_a, pair.alternative_b)
        assert gap == head + via
        assert abs(pair.flow_gap - float(gap)) <= TOL
        assert abs(pair.head_to_head - float(head)) <= TOL
        assert abs(pair.via_others - float(via)) <= TOL
        rows = {r.criterion_id: r for r in pair.criteria}
        weights = exact["weights"]
        n = len(exact["alternatives"])
        for leaf, row in rows.items():
            a, b = pair.alternative_a, pair.alternative_b
            contribution = weights[leaf] * (
                exact["criterion"][leaf][a] - exact["criterion"][leaf][b]
            )
            head_to_head = (
                weights[leaf]
                * 2
                * (exact["degrees"][leaf][a, b] - exact["degrees"][leaf][b, a])
                / (n - 1)
            )
            assert abs(row.promethee_contribution - float(contribution)) <= TOL
            assert abs(row.promethee_head_to_head - float(head_to_head)) <= TOL
        assert abs(sum(r.promethee_contribution for r in pair.criteria) - pair.flow_gap) <= 1e-9
