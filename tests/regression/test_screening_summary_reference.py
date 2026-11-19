"""The screening summary against its independent oracle, hand-checked cases and properties.

``screening_summary_oracle`` reads the project file as JSON and never imports ``mcda_studio``
(checked below in a clean interpreter); only this module calls the engine.
"""

import math
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest
import screening_summary_oracle as oracle
from hypothesis import given, settings
from hypothesis import strategies as st

from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.services import project_service as ps
from mcda_studio.services import questions_service as questions
from mcda_studio.services import screening_summary_service as summary
from mcda_studio.storage.json_repository import JsonProjectRepository

from builders import flat_project, tiny_project, with_classes

ROOT = Path(__file__).parents[2]
STUDY = ROOT / "examples" / "nz_venture_screening" / "project.json"
QUALIFICATION = ROOT / "examples" / "supplier_qualification" / "project.json"
CONTEXTS = [
    (STUDY, profile, scenario)
    for profile in ("technical_ip", "commercial_traction")
    for scenario in (None, "linear_market_size")
] + [
    (QUALIFICATION, None, None),
    (QUALIFICATION, "cost_focus", None),
    (QUALIFICATION, None, "linear_defects"),
]


def _engine(
    project: Project, profile: str | None, scenario: str | None
) -> summary.ScreeningSummary:
    cfg = AnalysisConfiguration(method="mavt", weight_profile_id=profile, scenario_id=scenario)
    return summary.screening_summary(project, cfg)


def _compare(project: Project, profile: str | None, scenario: str | None) -> None:
    raw = project.model_dump(mode="json")
    expected = oracle.summary(raw, profile, scenario)
    got = _engine(project, profile, scenario)
    assert got.status == "available"
    assert set(got.excluded_criteria) == set(expected["excluded"])
    for row in got.rows:
        want = expected["rows"][row.alternative_id]
        assert row.value == pytest.approx(want["value"], abs=1e-12)
        assert row.rank == want["rank"]
        assert [d.contribution for d in row.drivers] == pytest.approx(want["drivers"], abs=1e-12)
        assert row.class_id == want["class"]
        if want["margin"] is None:
            assert row.margin is None
        else:
            assert row.margin == pytest.approx(want["margin"], abs=1e-12)
        assert (row.requirements.status if row.requirements else None) == want["requirements"]
        f, w = row.fragility, want["fragility"]
        assert f is not None and f.status == w[0], (row.alternative_id, f, w)
        if w[0] == "change":
            assert f.weight_change == pytest.approx(w[1], abs=1e-12)
            detail = f.other_alternative_id if f.kind == "rank" else f.class_after_id
            kinds = {(k, node) for k, node, _ in w[2]}
            assert (f.kind, f.criterion_id) in kinds
            if f.kind == "rank":
                assert (f.kind, f.criterion_id, detail) in w[2]
        if w[0] == "tied":
            assert sorted(f.tied_with) == sorted(w[1])


def test_the_oracle_imports_nothing_from_mcda_studio() -> None:
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import screening_summary_oracle; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] == 'mcda_studio'))"
    )
    run = subprocess.run(
        [sys.executable, "-I", "-c", code, str(Path(__file__).parent)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert run.stdout.strip() == "[]"


@pytest.mark.parametrize(("path", "profile", "scenario"), CONTEXTS)
def test_every_column_matches_the_oracle(
    path: Path, profile: str | None, scenario: str | None
) -> None:
    _compare(JsonProjectRepository().load(path), profile, scenario)


def test_the_tiny_crossover_is_the_closest_change_by_hand() -> None:
    """Cost weight 2/3; the two alternatives cross at t = 3/7, a change of 5/21 of the weight."""
    got = _engine(tiny_project(), None, None)
    for row in got.rows:
        f = row.fragility
        assert f is not None and f.status == "change" and f.kind == "rank"
        assert f.direction == ("lower" if f.criterion_id == "cost" else "raise")
        assert Fraction(f.weight_change).limit_denominator(1000) == Fraction(5, 21)  # type: ignore[arg-type]
        assert f.other_alternative_id == ({"a", "b"} - {row.alternative_id}).pop()
    assert [r.alternative_id for r in got.rows] == ["a", "b"]
    assert [d.criterion_id for d in got.rows[0].drivers] == ["cost", "quality"]


def test_a_class_change_closer_than_any_crossover_wins() -> None:
    project = with_classes(tiny_project(), [("Top", 0.72), ("Rest", None)])
    a = next(r for r in _engine(project, None, None).rows if r.alternative_id == "a")
    # V_a(t) = 0.6 + 0.2 t reaches the boundary less its tie tolerance, 0.72 - 1e-12, at
    # t = 0.6 - 5e-12: a change of 2/3 - 0.6 + 5e-12 = 1/15 + 5e-12.
    assert a.fragility is not None and a.fragility.kind == "class"
    assert a.fragility.weight_change == pytest.approx(1 / 15 + 5e-12, abs=1e-15)
    assert a.fragility.class_after_id == "rest" and a.fragility.direction == "lower"
    assert a.class_id == "top" and a.margin == pytest.approx(0.73333333333 - 0.72, abs=1e-9)


def test_tied_alternatives_report_the_tie_not_a_positive_change() -> None:
    project = flat_project([[0.5, 0.5], [0.5, 0.5], [0.9, 0.3]], [1.0, 1.0])
    rows = {r.alternative_id: r for r in _engine(project, None, None).rows}
    assert rows["a0"].rank == rows["a1"].rank == 2
    assert rows["a0"].fragility is not None and rows["a0"].fragility.status == "tied"
    assert rows["a0"].fragility.tied_with == ["a1"]


def test_zero_weight_nodes_are_excluded_and_never_reported() -> None:
    project = ps.set_judgement(flat_project([[0.2, 0.9], [0.8, 0.1]], [1.0, 1.0]), "c1", 0.0)
    got = _engine(project, None, None)
    assert got.excluded_criteria == ["c1"]
    assert all(r.fragility and r.fragility.criterion_id != "c1" for r in got.rows)


def test_the_selected_profile_is_the_one_summarised() -> None:
    project = JsonProjectRepository().load(STUDY)
    technical = _engine(project, "technical_ip", None)
    commercial = _engine(project, "commercial_traction", None)
    assert technical.weight_profile_id == "technical_ip"
    assert commercial.weight_profile_id == "commercial_traction"
    assert [r.alternative_id for r in technical.rows] != [r.alternative_id for r in commercial.rows]


def test_a_missing_measurement_makes_the_summary_unavailable_never_zero() -> None:
    project = ps.clear_performance(tiny_project(), "a", "cost")
    got = _engine(project, None, None)
    assert got.status == "unavailable" and got.rows == []
    assert got.reason == "Ranking unavailable: 1 measurement(s) are missing."
    assert "MISSING_MEASUREMENT" in got.issue_codes


def test_absent_sections_are_noted_per_column() -> None:
    got = _engine(tiny_project(), None, None)
    notes = {c.column: c for c in got.columns}
    assert not notes["classes"].available and notes["classes"].reason == "No classes are set up."
    assert not notes["requirements"].available
    assert notes["fragility"].available and notes["open_questions"].available
    assert all(r.class_id is None and r.requirements is None for r in got.rows)


def test_more_than_fifty_nodes_skips_only_fragility() -> None:
    n = summary.MAX_FRAGILITY_NODES + 1
    project = flat_project([[i / n for i in range(n)], [1 - i / n for i in range(n)]], [1.0] * n)
    got = _engine(project, None, None)
    notes = {c.column: c for c in got.columns}
    assert not notes["fragility"].available
    assert notes["fragility"].reason == "Not computed: more than 50 criterion nodes."
    assert all(r.fragility is None for r in got.rows) and len(got.rows) == 2


def test_open_question_counts_add_up_to_the_open_questions_total() -> None:
    project = JsonProjectRepository().load(STUDY)
    cfg = AnalysisConfiguration(method="mavt_sorting")
    got = summary.screening_summary(project, cfg)
    total = len(questions.open_questions(project, cfg).questions)
    assert sum(r.open_questions or 0 for r in got.rows) + (got.project_open_questions or 0) == total


def test_looking_never_changes_the_project() -> None:
    project = JsonProjectRepository().load(STUDY)
    before = project.model_dump(mode="json"), project.fingerprint()
    summary.screening_summary(project, AnalysisConfiguration(method="mavt_sorting"))
    assert (project.model_dump(mode="json"), project.fingerprint()) == before


def test_the_wording_says_preference_not_probability() -> None:
    got = _engine(tiny_project(), None, None)
    assert "not a probability" in got.label
    assert "share of the total weight" in got.fragility_definition


@settings(max_examples=40, deadline=None)
@given(
    st.integers(2, 5).flatmap(
        lambda n: st.tuples(
            st.lists(st.lists(st.integers(0, 20), min_size=3, max_size=3), min_size=n, max_size=n),
            st.lists(st.integers(1, 9), min_size=3, max_size=3),
        )
    ),
    st.booleans(),
)
def test_random_models_match_the_oracle(
    data: tuple[list[list[int]], list[int]], classes: bool
) -> None:
    values, ratings = data
    project = flat_project([[v / 20 for v in row] for row in values], [float(r) for r in ratings])
    if classes:
        project = with_classes(project, [("High", 0.6), ("Mid", 0.35), ("Low", None)])
    _compare(project, None, None)


@settings(max_examples=40, deadline=None)
@given(
    st.lists(st.lists(st.integers(0, 20), min_size=3, max_size=3), min_size=2, max_size=5),
    st.lists(st.integers(1, 9), min_size=3, max_size=3),
)
def test_moving_the_reported_weight_past_the_closest_change_changes_rank_or_class(
    values: list[list[int]], ratings: list[int]
) -> None:
    """Just short of the reported weight nothing changes; just past it, the rank or class does."""
    project = with_classes(
        flat_project([[v / 20 for v in row] for row in values], [float(r) for r in ratings]),
        [("High", 0.6), ("Low", None)],
    )
    raw = project.model_dump(mode="json")
    base_local = oracle.values_oracle.local_weights(
        raw, oracle.values_oracle._profile(raw, None, None)
    )
    base_values = oracle.values_oracle.overall_values(raw)
    for row in _engine(project, None, None).rows:
        f = row.fragility
        if f is None or f.status != "change":
            continue
        assert f.local_weight is not None and f.base_local_weight is not None and f.criterion_id
        siblings = [c for c in base_local if c != f.criterion_id]
        rest = math.fsum(base_local[s] for s in siblings)
        step = 1e-7 if f.local_weight > f.base_local_weight else -1e-7

        def reading(
            t: float,
            node: str = f.criterion_id,
            alt: str = row.alternative_id,
            siblings: list[str] = siblings,
            rest: float = rest,
        ) -> tuple[frozenset[str], str]:
            local = {node: t, **{s: (1 - t) * base_local[s] / rest for s in siblings}}
            vals = oracle.values_oracle.overall_values(raw, local=local)
            above = frozenset(b for b, v in vals.items() if v > vals[alt] + 1e-12)
            return above, oracle.values_oracle.class_of(vals[alt], raw)

        mine = base_values[row.alternative_id]
        here = (
            frozenset(b for b, v in base_values.items() if v > mine + 1e-12),
            oracle.values_oracle.class_of(mine, raw),
        )
        if abs(f.local_weight - f.base_local_weight) > 1e-6:
            assert reading(f.local_weight - step) == here
        if 0.0 <= f.local_weight + step <= 1.0:
            assert reading(f.local_weight + step) != here


@pytest.mark.parametrize(("path", "profile", "scenario"), CONTEXTS)
def test_equal_closest_changes_go_to_the_first_criterion_in_tree_order(
    path: Path, profile: str | None, scenario: str | None
) -> None:
    """Lowering one of two siblings is raising the other, so one change can be offered twice,
    differing only in its last bits. Changes within the tolerance are equal and the criterion met
    first in tree order is reported, so rounding never chooses (it once differed Mac to Linux)."""
    project = JsonProjectRepository().load(path)
    order = {node: k for k, node in enumerate(project.tree().all_ids())}
    expected = oracle.summary(project.model_dump(mode="json"), profile, scenario)
    for row in _engine(project, profile, scenario).rows:
        want = expected["rows"][row.alternative_id]["fragility"]
        if want[0] != "change":
            continue
        nodes = {node for _, node, _ in want[2]}
        assert row.fragility is not None
        assert row.fragility.criterion_id == min(nodes, key=order.__getitem__)


def test_the_supplier_example_has_such_ties() -> None:
    """The rule above is exercised: Apex and Delta can swap by lowering Unit price or by raising
    Logistics cost, its only sibling, by the same amount."""
    project = JsonProjectRepository().load(QUALIFICATION)
    expected = oracle.summary(project.model_dump(mode="json"), None, None)
    rows = {r.alternative_id: r for r in _engine(project, None, None).rows}
    for alt in ("apex", "delta"):
        nodes = {node for _, node, _ in expected["rows"][alt]["fragility"][2]}
        assert nodes == {"unit_price", "logistics_cost"}
        fragility = rows[alt].fragility
        assert fragility is not None
        assert (fragility.criterion_id, fragility.direction) == ("unit_price", "lower")
