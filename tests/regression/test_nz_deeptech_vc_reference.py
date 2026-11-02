"""NZ deep-tech venture-capital study as the canonical mathematical regression.

Reference: the completed report "Prioritising New Zealand Deep-Tech Startups for Venture Capital
Due Diligence" (September 2026). Every ``REPORT_*`` constant below is a number *printed in that
report*, with the section it comes from. The fixture ``examples/nz_deeptech_vc/project.json`` is
built from the report's inputs only (``examples/nz_deeptech_vc/build.py``).

How the printed numbers are compared (no tolerance was widened to make anything pass):

* a quantity printed to *n* decimals must **round** to the printed digits (``rounds_to``): this is
  strictly tighter than an absolute tolerance of half a unit;
* the one place where the report's own inputs are rounded (Market Size control points, printed to
  3 d.p.) is tested by an interval derived from that rounding, see
  ``test_market_size_partials_are_consistent_with_the_rounding_of_the_printed_control_points``;
* an independent plain-Python oracle (no ``mcda_studio`` imports) recomputes everything from the
  report's inputs and must agree with the engine to 1e-12 (scores) / 1e-9 (crossovers).

A missing fixture is a test FAILURE, not a skip.
"""

import importlib.util
import itertools
import json
from pathlib import Path
from types import ModuleType

import pytest

from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import MavtResult
from mcda_studio.methods.mavt.sensitivity import weight_sensitivity
from mcda_studio.methods.mavt.value_functions import piecewise_linear
from mcda_studio.services import analysis_service as svc
from mcda_studio.storage.json_repository import JsonProjectRepository

pytestmark = pytest.mark.regression

EXAMPLE_DIR = Path(__file__).parents[2] / "examples" / "nz_deeptech_vc"
FIXTURE = EXAMPLE_DIR / "project.json"

# ---- numbers printed in the report ------------------------------------------------------------
# Section h(ii), table "Overall results": base piecewise model and linear Market Size model (3 dp).
REPORT_BASE = {
    "forever_harvest": 0.723,
    "outlier_space": 0.660,
    "kura_dynamics": 0.599,
    "hyades": 0.573,
}
REPORT_LINEAR = {
    "forever_harvest": 0.723,
    "outlier_space": 0.652,
    "kura_dynamics": 0.556,
    "hyades": 0.573,
}
# Section h(i) weight table (4 dp): parent W_p, local lambda_j|p, global w_j.
REPORT_PARENT_WEIGHTS = {
    "team": 0.2941,
    "problem_solution": 0.2647,
    "market": 0.2353,
    "traction": 0.2059,
}
REPORT_LOCAL = {
    "founder_expertise": 0.6061,
    "team_coverage": 0.3939,
    "problem_significance": 0.4737,
    "solution_viability": 0.5263,
    "market_size": 0.5556,
    "market_growth": 0.4444,
    "customer_validation": 0.5882,
    "execution_maturity": 0.4118,
}
REPORT_GLOBAL = {
    "founder_expertise": 0.1783,
    "team_coverage": 0.1159,
    "problem_significance": 0.1254,
    "solution_viability": 0.1393,
    "market_size": 0.1307,
    "market_growth": 0.1046,
    "customer_validation": 0.1211,
    "execution_maturity": 0.0848,
}
# Section h(i): Market Growth partials (3 dp). Section i: linear Market Size partials (6 dp).
REPORT_GROWTH_PARTIALS = {
    "hyades": 0.000,
    "forever_harvest": 1.000,
    "kura_dynamics": 0.062,
    "outlier_space": 0.569,
}
REPORT_LINEAR_SIZE_PARTIALS = {
    "forever_harvest": 0.000000,
    "outlier_space": 0.013279,
    "kura_dynamics": 0.128440,
    "hyades": 1.000000,
}
# Section f(ii): base-model Market Size partials (printed with 6 d.p. for the two interior ones).
REPORT_PW_SIZE_PARTIALS = {
    "forever_harvest": 0.0,
    "outlier_space": 0.071541,
    "kura_dynamics": 0.453102,
    "hyades": 1.0,
}
# Section f(i): Founder Expertise values under the adopted qualitative mapping.
REPORT_FOUNDER_PARTIALS = {
    "hyades": 0.50,
    "forever_harvest": 1.00,
    "kura_dynamics": 1.00,
    "outlier_space": 1.00,
}
# Section i table: first winner change when the parent weight is raised (None = none over [0, 1]).
REPORT_FIRST_CHANGE = {
    "team": ("outlier_space", 0.569),
    "problem_solution": None,
    "market": ("hyades", 0.674),
    "traction": None,
    "market_size": ("hyades", 0.873),  # local weight; Market parent fixed, Growth complements
}
# Section i text: at the Market Size crossover FH and Hyades tie near 0.648; global size weight
# rises from 0.131 to approximately 0.205.
REPORT_TIE_VALUE = 0.648
REPORT_SIZE_GLOBAL_WEIGHT_AT_CROSSOVER = 0.205

ALTS = ["forever_harvest", "outlier_space", "kura_dynamics", "hyades"]


def rounds_to(value: float, printed: float, decimals: int) -> bool:
    """True iff ``value`` rounds to the digits the report printed."""
    return round(value, decimals) == pytest.approx(printed, abs=10 ** -(decimals + 3))


# ---- fixtures ------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def project() -> Project:
    assert FIXTURE.exists(), (
        f"missing reference project {FIXTURE}; run examples/nz_deeptech_vc/build.py"
    )
    return JsonProjectRepository().load(FIXTURE)


@pytest.fixture(scope="module")
def base_result(project: Project) -> MavtResult:
    result = svc.evaluate_project(project)
    assert isinstance(result, MavtResult)
    return result


@pytest.fixture(scope="module")
def linear_result(project: Project) -> MavtResult:
    result = svc.evaluate_project(project, AnalysisConfiguration(scenario_id="linear_market_size"))
    assert isinstance(result, MavtResult)
    return result


def _builder_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("nz_deeptech_vc_build", EXAMPLE_DIR / "build.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---- plain-Python oracle: shares no code with the engine --------------------------------------
class Oracle:
    """Recomputes the study from the report's inputs with nothing but ``dict`` and ``float``."""

    levels = {1: 0.0, 2: 0.25, 3: 0.5, 4: 0.75, 5: 1.0}
    codes = {
        "founder_expertise": dict(hyades=3, forever_harvest=5, kura_dynamics=5, outlier_space=5),
        "team_coverage": dict(hyades=4, forever_harvest=4, kura_dynamics=4, outlier_space=5),
        "problem_significance": dict(hyades=4, forever_harvest=4, kura_dynamics=5, outlier_space=4),
        "solution_viability": dict(hyades=3, forever_harvest=4, kura_dynamics=3, outlier_space=3),
        "customer_validation": dict(hyades=3, forever_harvest=4, kura_dynamics=2, outlier_space=4),
        "execution_maturity": dict(hyades=3, forever_harvest=4, kura_dynamics=3, outlier_space=3),
    }
    size = dict(hyades=26.45, forever_harvest=1.38, kura_dynamics=4.60, outlier_space=1.7129)
    growth = dict(hyades=8.71, forever_harvest=23.10, kura_dynamics=9.60, outlier_space=16.90)
    cp_x = [1.380, 2.552, 5.077, 10.037, 26.450]
    cp_v = [0.0, 0.252, 0.5, 0.748, 1.0]
    tree = {
        "team": ["founder_expertise", "team_coverage"],
        "problem_solution": ["problem_significance", "solution_viability"],
        "market": ["market_size", "market_growth"],
        "traction": ["customer_validation", "execution_maturity"],
    }
    parent_rating = {"team": 100.0, "problem_solution": 90.0, "market": 80.0, "traction": 70.0}
    leaf_rating = {
        "founder_expertise": 100.0,
        "team_coverage": 65.0,
        "problem_significance": 90.0,
        "solution_viability": 100.0,
        "market_size": 100.0,
        "market_growth": 80.0,
        "customer_validation": 100.0,
        "execution_maturity": 70.0,
    }

    def pw(self, x: float) -> float:
        for i in range(len(self.cp_x) - 1):
            if self.cp_x[i] <= x <= self.cp_x[i + 1]:
                span = self.cp_x[i + 1] - self.cp_x[i]
                return self.cp_v[i] + (x - self.cp_x[i]) / span * (self.cp_v[i + 1] - self.cp_v[i])
        raise ValueError(x)

    def size_partial(self, alt: str, linear: bool) -> float:
        x = self.size[alt]
        if linear:
            return (x - 1.38) / (26.45 - 1.38)
        return self.pw(x)

    def partials(self, linear: bool = False) -> dict[str, dict[str, float]]:
        lo, hi = min(self.growth.values()), max(self.growth.values())
        out: dict[str, dict[str, float]] = {}
        for a in ALTS:
            row = {k: self.levels[v[a]] for k, v in self.codes.items()}
            row["market_size"] = self.size_partial(a, linear)
            row["market_growth"] = (self.growth[a] - lo) / (hi - lo)
            out[a] = row
        return out

    def parent_weights(self) -> dict[str, float]:
        total = sum(self.parent_rating.values())
        return {p: r / total for p, r in self.parent_rating.items()}

    def local(self) -> dict[str, float]:
        out = {}
        for kids in self.tree.values():
            s = sum(self.leaf_rating[k] for k in kids)
            out.update({k: self.leaf_rating[k] / s for k in kids})
        return out

    def global_weights(self, parents: dict[str, float] | None = None) -> dict[str, float]:
        parents = parents or self.parent_weights()
        loc = self.local()
        return {k: parents[p] * loc[k] for p, kids in self.tree.items() for k in kids}

    def overall(self, linear: bool = False) -> dict[str, float]:
        w, parts = self.global_weights(), self.partials(linear)
        return {a: sum(w[k] * parts[a][k] for k in w) for a in ALTS}

    def affine_parent(self, parent: str) -> dict[str, tuple[float, float]]:
        """V_a(t) = A + B t: ``parent`` weight is t, the other parents scale proportionally."""
        lam = self.parent_weights()
        parts = self.partials()
        loc = self.local()
        res = {}
        for a in ALTS:
            a0 = b = 0.0
            for p, kids in self.tree.items():
                inner = sum(loc[k] * parts[a][k] for k in kids)
                if p == parent:
                    b += inner
                else:
                    scale = lam[p] / (1 - lam[parent])
                    a0 += scale * inner
                    b -= scale * inner
            res[a] = (a0, b)
        return res

    def affine_size(self) -> dict[str, tuple[float, float]]:
        """V_a(t) with the Market Size local weight = t (Market parent weight fixed)."""
        parts, w = self.partials(), self.global_weights()
        wm = self.parent_weights()["market"]
        res = {}
        for a in ALTS:
            rest = sum(w[k] * parts[a][k] for k in w if k not in ("market_size", "market_growth"))
            res[a] = (
                rest + wm * parts[a]["market_growth"],
                wm * (parts[a]["market_size"] - parts[a]["market_growth"]),
            )
        return res

    @staticmethod
    def first_crossover_up(
        lines: dict[str, tuple[float, float]], base_t: float
    ) -> tuple[str, float] | None:
        value = lambda a, t: lines[a][0] + lines[a][1] * t  # noqa: E731
        leader = max(lines, key=lambda a: value(a, base_t))
        best: tuple[str, float] | None = None
        for other in lines:
            if other == leader:
                continue
            slope = lines[other][1] - lines[leader][1]
            if slope <= 0:
                continue
            t = (lines[leader][0] - lines[other][0]) / slope
            if base_t < t <= 1 and (best is None or t < best[1]):
                best = (other, t)
        return best


ORACLE = Oracle()


# ---- the generic fixture is exactly the report's inputs ----------------------------------------
def test_fixture_file_is_exactly_what_build_py_generates(project: Project) -> None:
    built = _builder_module().build_project()
    assert project.fingerprint() == built.fingerprint()


def test_fixture_has_the_reports_structure(project: Project) -> None:
    assert [a.id for a in project.alternatives] == [
        "hyades",
        "forever_harvest",
        "kura_dynamics",
        "outlier_space",
    ]
    tree = project.tree()
    assert tree.child_ids(None) == list(Oracle.tree)
    for parent, kids in Oracle.tree.items():
        assert tree.child_ids(parent) == kids
    assert len(project.performances) == 4 * 8
    assert [s.id for s in project.scenarios] == ["linear_market_size"]
    assert project.id == "nz_deeptech_vc_study"


def test_fixture_validates_with_only_the_documented_local_anchor_warnings(project: Project) -> None:
    """Market Growth is a local linear scale in the base model; the linear Market Size scenario
    makes Market Size local too. Nothing else is reported."""
    report = svc.validate(project)
    assert report.ok
    assert sorted((i.code, i.path) for i in report.issues) == [
        ("LOCAL_ANCHORS", "criteria[market_growth]"),
        ("LOCAL_ANCHORS", "scenarios[linear_market_size].value_function_overrides[market_size]"),
    ]


def test_outlier_market_size_is_the_unrounded_input(project: Project) -> None:
    """Section e(ii): displayed 1.71, but 'DECERNS retains the unrounded input 1.7129'."""
    perf = project.performance_index()
    assert perf[("outlier_space", "market_size")] == 1.7129


# ---- Priority 1: original results ------------------------------------------------------------
def test_base_case_ranking_and_scores_round_to_the_report(base_result: MavtResult) -> None:
    assert [r.alternative_id for r in base_result.ranking] == [
        "forever_harvest",
        "outlier_space",
        "kura_dynamics",
        "hyades",
    ]
    for r in base_result.ranking:
        assert rounds_to(r.value, REPORT_BASE[r.alternative_id], 3), (r.alternative_id, r.value)


def test_base_case_matches_the_independent_oracle(base_result: MavtResult) -> None:
    oracle = ORACLE.overall()
    for r in base_result.ranking:
        assert r.value == pytest.approx(oracle[r.alternative_id], abs=1e-12)


def test_weights_round_to_the_report_at_every_level(
    base_result: MavtResult, project: Project
) -> None:
    for leaf, printed in REPORT_GLOBAL.items():
        assert rounds_to(base_result.global_weights[leaf], printed, 4), leaf
        assert rounds_to(base_result.local_weights[leaf], REPORT_LOCAL[leaf], 4), leaf
    for parent, printed in REPORT_PARENT_WEIGHTS.items():
        assert rounds_to(base_result.local_weights[parent], printed, 4), parent
    assert sum(base_result.global_weights.values()) == pytest.approx(1.0, abs=1e-12)
    expected_file = json.loads((EXAMPLE_DIR / "expected_weights.json").read_text())
    assert expected_file == REPORT_GLOBAL


def test_global_weights_match_the_independent_oracle(base_result: MavtResult) -> None:
    for leaf, w in ORACLE.global_weights().items():
        assert base_result.global_weights[leaf] == pytest.approx(w, abs=1e-12)


def test_market_growth_and_founder_expertise_partials_match_the_report(
    base_result: MavtResult,
) -> None:
    detail = {d.alternative_id: d.partial_values for d in base_result.alternatives}
    for alt, printed in REPORT_GROWTH_PARTIALS.items():
        assert rounds_to(detail[alt]["market_growth"], printed, 3), alt
    for alt, printed in REPORT_FOUNDER_PARTIALS.items():
        assert detail[alt]["founder_expertise"] == pytest.approx(printed, abs=1e-12), alt
    # Section f(iii): all six qualitative criteria map VL..VH to 0/.25/.5/.75/1.
    for alt, row in ORACLE.partials().items():
        for leaf in Oracle.codes:
            assert detail[alt][leaf] == pytest.approx(row[leaf], abs=1e-12), (alt, leaf)


def test_overall_value_is_the_weighted_sum_of_partial_values(base_result: MavtResult) -> None:
    for d in base_result.alternatives:
        recomputed = sum(base_result.global_weights[k] * v for k, v in d.partial_values.items())
        assert d.overall_value == pytest.approx(recomputed, abs=1e-12)
        assert sum(d.weighted_contributions.values()) == pytest.approx(d.overall_value, abs=1e-12)


# ---- the one place the report's own inputs are rounded ------------------------------------------
def test_market_size_control_points_are_the_printed_ones(project: Project) -> None:
    vf = next(n for n in project.criteria if n.id == "market_size").value_function
    assert vf is not None
    points = [(p.x, p.value) for p in vf.points]  # type: ignore[union-attr]
    assert points == list(zip(Oracle.cp_x, Oracle.cp_v, strict=True))
    for x, v in points:
        assert piecewise_linear(x, Oracle.cp_x, Oracle.cp_v) == pytest.approx(v, abs=1e-12)


def _market_size_partial_bounds(alt: str) -> tuple[float, float]:
    """Range of the partial value over every control-point set that rounds to the printed table.

    x1, v1, x2, v2 are varied inside +-0.0005 (the report prints 3 d.p.). The end points are held:
    1.380 and 26.450 are the observed range (the linear model's six-decimal partials in section i
    reproduce exactly with them), 0.000 and 1.000 are the endpoint convention. x3 and v3 do not
    affect Outlier (segment 1) or Kura (segment 2).
    """
    half = 5e-4
    grid = [-half, -half / 2, 0.0, half / 2, half]
    values = []
    for dx1, dv1, dx2, dv2 in itertools.product(grid, repeat=4):
        xs = [1.380, 2.552 + dx1, 5.077 + dx2, 10.037, 26.450]
        vs = [0.0, 0.252 + dv1, 0.5 + dv2, 0.748, 1.0]
        values.append(piecewise_linear(Oracle.size[alt], xs, vs))
    return min(values), max(values)


@pytest.mark.parametrize("alt", ["outlier_space", "kura_dynamics"])
def test_market_size_partials_are_consistent_with_the_rounding_of_the_printed_control_points(
    alt: str, base_result: MavtResult
) -> None:
    """INVESTIGATED DISCREPANCY (not a tolerance change).

    Using the printed control points the engine gives Outlier 0.071579 and Kura 0.453150 while the
    report prints 0.071541 and 0.453102 (differences 3.8e-5 and 4.8e-5). The report says its
    DECERNS control points were entered "lightly adjusted" and are "shown rounded", so the engine
    cannot be expected to match six decimals from 3-dp inputs. This test checks that (a) the
    report's six-decimal value lies inside the range implied by that rounding, and (b) so does the
    engine's value. Both must hold, and the interval is a few 1e-4 wide, far narrower than the
    3-dp rounding of the final scores.
    """
    lo, hi = _market_size_partial_bounds(alt)
    printed = REPORT_PW_SIZE_PARTIALS[alt]
    engine = next(d for d in base_result.alternatives if d.alternative_id == alt).partial_values[
        "market_size"
    ]
    assert lo <= printed <= hi, (alt, lo, printed, hi)
    assert lo <= engine <= hi, (alt, lo, engine, hi)
    assert hi - lo < 2e-3  # the rounding window is tight, so this test is not vacuous


def test_the_unresolved_control_point_rounding_cannot_change_a_printed_score(
    base_result: MavtResult,
) -> None:
    """Replacing the engine's Market Size partials by the report's six-decimal ones moves every
    overall value by well under the 5e-4 that 3-dp rounding allows (and does not change a digit)."""
    w = base_result.global_weights["market_size"]
    detail = {d.alternative_id: d for d in base_result.alternatives}
    for alt, printed in REPORT_PW_SIZE_PARTIALS.items():
        swapped = detail[alt].overall_value + w * (
            printed - detail[alt].partial_values["market_size"]
        )
        assert abs(swapped - detail[alt].overall_value) < 1e-5
        assert rounds_to(swapped, REPORT_BASE[alt], 3)


# ---- Priority 1: the alternate linear Market Size scenario --------------------------------------
def test_linear_scenario_ranking_and_scores_round_to_the_report(linear_result: MavtResult) -> None:
    assert [r.alternative_id for r in linear_result.ranking] == [
        "forever_harvest",
        "outlier_space",
        "hyades",
        "kura_dynamics",
    ]
    for r in linear_result.ranking:
        assert rounds_to(r.value, REPORT_LINEAR[r.alternative_id], 3), (r.alternative_id, r.value)
    oracle = ORACLE.overall(linear=True)
    for r in linear_result.ranking:
        assert r.value == pytest.approx(oracle[r.alternative_id], abs=1e-12)


def test_linear_scenario_market_size_partials_match_the_report_to_six_decimals(
    linear_result: MavtResult,
) -> None:
    for d in linear_result.alternatives:
        assert d.partial_values["market_size"] == pytest.approx(
            REPORT_LINEAR_SIZE_PARTIALS[d.alternative_id], abs=5e-7
        )


def test_linear_scenario_changes_only_market_size(
    base_result: MavtResult, linear_result: MavtResult
) -> None:
    """Section i: 'All raw data, other scores, swing judgements and weights are unchanged.'"""
    assert linear_result.global_weights == base_result.global_weights
    base = {d.alternative_id: d for d in base_result.alternatives}
    for d in linear_result.alternatives:
        assert d.raw_measurements == base[d.alternative_id].raw_measurements
        for leaf, v in d.partial_values.items():
            if leaf != "market_size":
                assert v == base[d.alternative_id].partial_values[leaf]


def test_linear_scenario_swaps_hyades_and_kura_only(project: Project) -> None:
    cmp = svc.compare_scenarios(project, ["linear_market_size"])
    s = cmp.scenarios[0]
    assert cmp.baseline.ranking == ["forever_harvest", "outlier_space", "kura_dynamics", "hyades"]
    assert s.ranking[:2] == cmp.baseline.ranking[:2] == ["forever_harvest", "outlier_space"]
    assert s.ranking[2:] == ["hyades", "kura_dynamics"]
    assert s.ranking_differs_from_baseline and not s.winner_differs_from_baseline


# ---- Priority 1: sensitivity crossover values ---------------------------------------------------
@pytest.mark.parametrize("node", list(REPORT_FIRST_CHANGE))
def test_first_winner_change_rounds_to_the_report(node: str, project: Project) -> None:
    res = weight_sensitivity(project, None, node)
    expected = REPORT_FIRST_CHANGE[node]
    if expected is None:
        assert res.first_winner_change_up is None, f"{node}: report says no winner change"
        assert res.first_winner_change_down is None
        assert res.winner_stable_range == (0.0, 1.0)
        return
    winner, printed = expected
    change = res.first_winner_change_up
    assert change is not None, f"no winner change found when raising the {node} weight"
    assert change.from_winner == "forever_harvest"
    assert change.to_winner == winner
    assert rounds_to(change.weight, printed, 3), (node, change.weight)


def test_sensitivity_base_weights_match_the_report(project: Project) -> None:
    for node, printed in [
        ("team", 0.294),
        ("problem_solution", 0.265),
        ("market", 0.235),
        ("traction", 0.206),
    ]:
        assert rounds_to(weight_sensitivity(project, None, node).base_weight, printed, 3), node
    assert rounds_to(weight_sensitivity(project, None, "market_size").base_weight, 0.556, 3)


@pytest.mark.parametrize("node", ["team", "market"])
def test_parent_crossovers_agree_with_the_independent_affine_oracle(
    node: str, project: Project
) -> None:
    lines = ORACLE.affine_parent(node)
    expected = ORACLE.first_crossover_up(lines, ORACLE.parent_weights()[node])
    assert expected is not None
    change = weight_sensitivity(project, None, node).first_winner_change_up
    assert change is not None
    assert change.to_winner == expected[0]
    assert change.weight == pytest.approx(expected[1], abs=1e-9)


def test_market_size_crossover_agrees_with_the_oracle_and_reproduces_the_reported_tie(
    project: Project,
) -> None:
    lines = ORACLE.affine_size()
    expected = ORACLE.first_crossover_up(lines, 100.0 / 180.0)
    assert expected is not None
    change = weight_sensitivity(project, None, "market_size").first_winner_change_up
    assert change is not None
    assert change.to_winner == expected[0] == "hyades"
    assert change.weight == pytest.approx(expected[1], abs=1e-9)
    t = change.weight
    fh = lines["forever_harvest"][0] + lines["forever_harvest"][1] * t
    hy = lines["hyades"][0] + lines["hyades"][1] * t
    assert fh == pytest.approx(hy, abs=1e-9)  # a genuine tie at the crossover
    assert rounds_to(fh, REPORT_TIE_VALUE, 3)
    assert rounds_to(
        ORACLE.parent_weights()["market"] * t, REPORT_SIZE_GLOBAL_WEIGHT_AT_CROSSOVER, 3
    )


def test_market_weight_0_680_is_beyond_the_calculated_crossover(project: Project) -> None:
    """Figure 5 (right): Market = 0.680 is 'beyond the calculated crossover 0.674'; Hyades leads."""
    lines = ORACLE.affine_parent("market")
    at = {a: lines[a][0] + lines[a][1] * 0.680 for a in ALTS}
    assert max(at, key=lambda a: at[a]) == "hyades"
    change = weight_sensitivity(project, None, "market").first_winner_change_up
    assert change is not None and change.weight < 0.680
