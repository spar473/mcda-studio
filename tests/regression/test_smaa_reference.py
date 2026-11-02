"""SMAA-2 against independent references: exact enumeration and intervals from ``smaa_oracle``
(plain Python, checked in a clean interpreter to load no ``mcda_studio`` module), SciPy's beta
quantiles, and the analytic two-weight case whose order switches at 3/7."""

import subprocess
import sys
from pathlib import Path

import pytest
import smaa_oracle as oracle
from scipy.stats import beta

from mcda_studio.domain.project import Project
from mcda_studio.domain.results import SmaaResult
from mcda_studio.domain.uncertainty import (
    CategoricalDistribution,
    CellRef,
    CellUncertainty,
    DiscreteDistribution,
    GroupUncertainty,
    SharedDraw,
    SmaaModel,
    UniformDistribution,
)
from mcda_studio.methods.smaa.intervals import clopper_pearson
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository

from builders import scored_project, tiny_project

ROOT = Path(__file__).parents[2]
QUALIFICATION = ROOT / "examples" / "supplier_qualification" / "project.json"


def smaa(project: Project, **parameters: object) -> SmaaResult:
    cfg = project.analysis.model_copy(update={"method": "smaa2", "parameters": parameters})
    result = svc.evaluate_project(project, cfg)
    assert isinstance(result, SmaaResult)
    return result


def cell(alt: str, crit: str, dist: object) -> CellUncertainty:
    return CellUncertainty(alternative_id=alt, criterion_id=crit, distribution=dist)  # type: ignore[arg-type]


def qualification_with_discrete_uncertainty() -> Project:
    model = SmaaModel(
        cells=[
            cell(
                "apex",
                "certification",
                CategoricalDistribution(
                    labels=["iso9001", "iso9001_14001"], probabilities=[0.3, 0.7]
                ),
            ),
            cell(
                "delta",
                "defect_rate",
                DiscreteDistribution(values=[0.8, 2.5, 4.0], probabilities=[0.5, 0.3, 0.2]),
            ),
            cell(
                "brightline",
                "on_time",
                DiscreteDistribution(values=[91, 99], probabilities=[0.6, 0.4]),
            ),
            cell(
                "evergreen",
                "on_time",
                DiscreteDistribution(values=[80, 95], probabilities=[0.5, 0.5]),
            ),
        ],
        shared_draws=[
            SharedDraw(
                id="carrier",
                cells=[
                    CellRef(alternative_id="brightline", criterion_id="on_time"),
                    CellRef(alternative_id="evergreen", criterion_id="on_time"),
                ],
            )
        ],
    )
    return ps.set_smaa_model(JsonProjectRepository().load(QUALIFICATION), model)


def tie_case() -> Project:
    """b equals a with probability one half, so a is only ever first in a tie."""
    project = scored_project({"a": 0.5, "b": 0.6, "c": 0.1})
    return ps.set_smaa_model(
        project,
        SmaaModel(
            cells=[
                cell(
                    "b", "score", DiscreteDistribution(values=[0.5, 0.7], probabilities=[0.5, 0.5])
                )
            ]
        ),
    )


def test_the_oracle_imports_nothing_from_mcda_studio() -> None:
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import smaa_oracle; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] == 'mcda_studio'))"
    )
    run = subprocess.run(
        [sys.executable, "-I", "-c", code, str(Path(__file__).parent)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert run.stdout.strip() == "[]"


@pytest.mark.parametrize("build", [qualification_with_discrete_uncertainty, tie_case])
def test_exact_enumeration_matches_the_oracle_exactly(build) -> None:  # type: ignore[no-untyped-def]
    project = build()
    raw = project.model_dump(mode="json")
    ranks, sole, tied, classes = oracle.exact_acceptability(raw)
    result = smaa(project)
    assert result.evaluation == "exact_enumeration" and result.samples is None
    for row in result.acceptability:
        a = row.alternative_id
        assert [e.frequency for e in row.ranks] == [float(p) for p in ranks[a]]
        assert row.sole_first.frequency == float(sole[a])
        assert row.tied_first.frequency == float(tied[a])
        assert {k: e.frequency for k, e in row.classes.items()} == {
            k: float(p) for k, p in classes[a].items()
        }
        assert all(e.count is None and e.lower is None and e.upper is None for e in row.ranks)


def test_ties_share_rank_one_and_are_reported_apart_from_sole_first() -> None:
    by = {row.alternative_id: row for row in smaa(tie_case()).acceptability}
    assert by["a"].ranks[0].frequency == 0.5 and by["a"].sole_first.frequency == 0.0
    assert by["a"].tied_first.frequency == 0.5
    assert by["b"].ranks[0].frequency == 1.0 and by["b"].sole_first.frequency == 0.5
    assert sum(row.ranks[0].frequency for row in by.values()) == 1.5  # ties share the rank


def test_sampled_ties_take_competition_ranks_through_the_fsum_path() -> None:
    """With a continuous input elsewhere the run is sampled; b still equals a in half the draws."""
    project = tie_case()
    assert project.smaa is not None
    model = project.smaa.model_copy(
        update={
            "cells": [
                *project.smaa.cells,
                cell("c", "score", UniformDistribution(lower=0.0, upper=0.2)),
            ]
        }
    )
    result = smaa(ps.set_smaa_model(project, model), samples=4000, seed=5)
    by = {row.alternative_id: row for row in result.acceptability}
    assert result.evaluation == "sampled"
    assert by["a"].ranks[0].count == by["a"].tied_first.count == by["b"].tied_first.count
    assert by["a"].sole_first.count == 0 and 0 < by["a"].tied_first.frequency < 1
    assert "NEAR_TIE_DRAWS" in [d.code for d in result.diagnostics]


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_the_two_weight_case_switches_at_three_sevenths(seed: int) -> None:
    """V_a(t) = 0.6 + 0.2 t, V_b(t) = 0.9 - 0.5 t: with t uniform, a leads with probability 4/7."""
    project = ps.set_smaa_model(
        tiny_project(), SmaaModel(groups=[GroupUncertainty(parent_id=None, kind="unknown")])
    )
    result = smaa(project, samples=20000, seed=seed, confidence=0.999)
    a = next(row for row in result.acceptability if row.alternative_id == "a")
    assert a.ranks[0].lower is not None and a.ranks[0].upper is not None
    assert a.ranks[0].lower <= 4 / 7 <= a.ranks[0].upper


@pytest.mark.parametrize(("k", "n"), [(k, n) for n in (1, 2, 7, 20) for k in range(n + 1)])
def test_intervals_match_exact_binomial_tails_and_scipy(k: int, n: int) -> None:
    lower, upper = clopper_pearson(k, n, 0.95)
    o_lower, o_upper = oracle.clopper_pearson(k, n, 0.95)
    s_lower = 0.0 if k == 0 else float(beta.ppf(0.025, k, n - k + 1))
    s_upper = 1.0 if k == n else float(beta.ppf(0.975, k + 1, n - k))
    assert lower == pytest.approx(o_lower, abs=1e-12) and upper == pytest.approx(o_upper, abs=1e-12)
    assert lower == pytest.approx(s_lower, abs=1e-12) and upper == pytest.approx(s_upper, abs=1e-12)


def test_zero_events_give_a_nonzero_upper_bound() -> None:
    for n in (1, 10, 1000, 100_000):
        lower, upper = clopper_pearson(0, n, 0.95)
        assert lower == 0.0 and upper > 0.0
        lower, upper = clopper_pearson(n, n, 0.95)
        assert upper == 1.0 and lower < 1.0
    # c (0.1) can never beat a (0.5) or b (uniform on 0.5 to 0.7): its rank-1 count is zero
    project = ps.set_smaa_model(
        scored_project({"a": 0.5, "b": 0.6, "c": 0.1}),
        SmaaModel(cells=[cell("b", "score", UniformDistribution(lower=0.5, upper=0.7))]),
    )
    sampled = smaa(project, samples=1000)
    never = [e for row in sampled.acceptability for e in row.ranks if e.count == 0]
    assert never and all(e.upper is not None and e.upper > 0 for e in never)
