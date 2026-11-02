"""Second, independent regression fixture (verifies reusability, not fidelity to DECERNS).

The expected numbers below are produced by a plain-Python oracle written *separately* from the
engine: no shared code beyond reading the raw data, no numpy, no bisect, no tree classes.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from mcda_studio.methods.mavt.sensitivity import weight_sensitivity
from mcda_studio.services import analysis_service as svc
from mcda_studio.storage.json_repository import JsonProjectRepository

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples" / "supplier_selection"


def _build_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("supplier_build", EXAMPLE / "build.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build = _build_module()


# ---- the oracle --------------------------------------------------------------------------
def oracle_values(ratings: dict[str, float], defect: str = "piecewise") -> dict[str, float]:
    data = {alt: m for alt, (_, m) in build.DATA.items()}

    def share(r: dict[str, float], names: list[str]) -> dict[str, float]:
        total = sum(r[n] for n in names)
        return {n: r[n] / total for n in names}

    top = share(ratings, ["cost", "performance", "risk"])
    cost = share(ratings, ["unit_price", "logistics_cost"])
    quality = share(ratings, ["quality", "delivery"])
    q = share(ratings, ["defect_rate", "certification"])
    d = share(ratings, ["on_time", "lead_time"])
    risk = share(ratings, ["financial_stability", "region"])
    w = {
        "unit_price": top["cost"] * cost["unit_price"],
        "logistics_cost": top["cost"] * cost["logistics_cost"],
        "defect_rate": top["performance"] * quality["quality"] * q["defect_rate"],
        "certification": top["performance"] * quality["quality"] * q["certification"],
        "on_time": top["performance"] * quality["delivery"] * d["on_time"],
        "lead_time": top["performance"] * quality["delivery"] * d["lead_time"],
        "financial_stability": top["risk"] * risk["financial_stability"],
        "region": top["risk"] * risk["region"],
    }
    assert abs(sum(w.values()) - 1) < 1e-12

    logistics = [m["logistics_cost"] for m in data.values()]
    lo, hi = min(logistics), max(logistics)
    cert = {"none": 0.0, "iso9001": 0.55, "iso9001_14001": 1.0}
    region = {"overseas": 0.0, "regional": 0.5, "domestic": 1.0}
    pts = [(0.0, 1.0), (1.0, 0.9), (3.0, 0.5), (8.0, 0.0)]

    def interp(x: float) -> float:
        for (x0, v0), (x1, v1) in zip(pts, pts[1:], strict=False):
            if x0 <= x <= x1:
                return v0 + (v1 - v0) * (x - x0) / (x1 - x0)
        raise AssertionError(x)

    out = {}
    for alt, m in data.items():
        v = {
            "unit_price": (60 - m["unit_price"]) / 40,
            "logistics_cost": (hi - m["logistics_cost"]) / (hi - lo),
            "defect_rate": interp(m["defect_rate"])
            if defect == "piecewise"
            else (10 - m["defect_rate"]) / 10,
            "certification": cert[m["certification"]],
            "on_time": (m["on_time"] - 70) / 30,
            "lead_time": (30 - m["lead_time"]) / 27,
            "financial_stability": m["financial_stability"] / 100,
            "region": region[m["region"]],
        }
        out[alt] = sum(w[k] * v[k] for k in w)
    return out


# ---- tests -------------------------------------------------------------------------------
def test_shipped_project_file_matches_the_build_script() -> None:
    assert JsonProjectRepository().load(EXAMPLE / "project.json") == build.build_project()


def test_engine_matches_the_independent_oracle() -> None:
    p = JsonProjectRepository().load(EXAMPLE / "project.json")
    expected = oracle_values({k: float(v) for k, v in build.BASE_RATINGS.items()})
    result = svc.evaluate_project(p)
    for r in result.ranking:
        assert r.value == pytest.approx(expected[r.alternative_id], abs=1e-12)
    assert [r.alternative_id for r in result.ranking] == sorted(
        expected, key=lambda k: -expected[k]
    )


def test_cost_focus_profile_matches_oracle() -> None:
    p = JsonProjectRepository().load(EXAMPLE / "project.json")
    ratings = {
        **{k: float(v) for k, v in build.BASE_RATINGS.items()},
        "cost": 100.0,
        "performance": 40.0,
        "risk": 20.0,
    }
    expected = oracle_values(ratings)
    result = svc.evaluate_project(
        p, p.analysis.model_copy(update={"weight_profile_id": "cost_focus"})
    )
    for r in result.ranking:
        assert r.value == pytest.approx(expected[r.alternative_id], abs=1e-12)


def test_linear_defect_scenario_matches_oracle() -> None:
    p = JsonProjectRepository().load(EXAMPLE / "project.json")
    expected = oracle_values({k: float(v) for k, v in build.BASE_RATINGS.items()}, defect="linear")
    result = svc.evaluate_project(
        p, p.analysis.model_copy(update={"scenario_id": "linear_defects"})
    )
    for r in result.ranking:
        assert r.value == pytest.approx(expected[r.alternative_id], abs=1e-12)


def test_sensitivity_crossover_matches_oracle_root() -> None:
    """Oracle: vary the 'performance' parent weight t by hand and solve for the winner flip."""
    p = JsonProjectRepository().load(EXAMPLE / "project.json")
    res = weight_sensitivity(p, None, "performance")
    base = {k: float(v) for k, v in build.BASE_RATINGS.items()}
    lam = base["performance"] / (base["cost"] + base["performance"] + base["risk"])

    others = base["cost"] + base["risk"]

    def values_at(t: float) -> dict[str, float]:
        # ratings that normalise to: performance = t, cost and risk share (1 - t) in their
        # original ratio (the ratings sum to 1, so they ARE the local weights)
        r = dict(base)
        r["performance"] = t
        r["cost"] = (1 - t) * base["cost"] / others
        r["risk"] = (1 - t) * base["risk"] / others
        return oracle_values(r)

    assert 0 < lam < 1

    assert res.first_winner_change_up is not None
    t_star = res.first_winner_change_up.weight
    v = values_at(t_star)
    assert v[res.first_winner_change_up.from_winner] == pytest.approx(
        v[res.first_winner_change_up.to_winner], abs=1e-9
    )
