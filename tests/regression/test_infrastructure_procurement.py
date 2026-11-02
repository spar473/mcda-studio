"""B3 acceptance fixture: hierarchical weights and preference profiles on an unrelated problem.

The expected numbers come from a plain-Python oracle written *separately* from the engine: no
shared code beyond reading the raw data, no numpy, no tree classes, and the weight products are
spelled out by hand so a wrong hierarchy or a wrong profile cannot pass unnoticed.
"""

import importlib.util
import math
from pathlib import Path
from types import ModuleType

import pytest

from mcda_studio.domain.errors import ModelEditError
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples" / "infrastructure_procurement"


def _build_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("infrastructure_build", EXAMPLE / "build.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build = _build_module()


def project():
    return JsonProjectRepository().load(EXAMPLE / "project.json")


# ---- the oracle --------------------------------------------------------------------------
def oracle_weights(ratings: dict[str, float]) -> dict[str, float]:
    """Local shares written out group by group, then multiplied down each path by hand."""

    def share(names: list[str]) -> dict[str, float]:
        total = sum(ratings[n] for n in names)
        return {n: ratings[n] / total for n in names}

    top = share(["lifecycle_cost", "service", "consent", "delivery"])
    cost = share(["capital_cost", "operating_cost", "funding_premium"])
    service = share(["reliability", "compliance"])
    reliability = share(["capacity_margin", "outage_hours"])
    consent = share(["community", "footprint"])
    # "Contractor track record" is an only child: its local weight is one, and the build script
    # supplies no rating for it, so the oracle must not read one either.
    assert "track_record" not in ratings

    w = {
        "capital_cost": top["lifecycle_cost"] * cost["capital_cost"],
        "operating_cost": top["lifecycle_cost"] * cost["operating_cost"],
        "funding_premium": top["lifecycle_cost"] * cost["funding_premium"],
        "capacity_margin": top["service"] * service["reliability"] * reliability["capacity_margin"],
        "outage_hours": top["service"] * service["reliability"] * reliability["outage_hours"],
        "compliance": top["service"] * service["compliance"],
        "community": top["consent"] * consent["community"],
        "footprint": top["consent"] * consent["footprint"],
        "track_record": top["delivery"] * 1.0,
    }
    assert abs(sum(w.values()) - 1) < 1e-12
    return w


def oracle_values(ratings: dict[str, float], outage: str = "piecewise") -> dict[str, float]:
    data = {alt: m for alt, (_, m) in build.DATA.items()}
    w = oracle_weights(ratings)

    operating = [m["operating_cost"] for m in data.values()]
    lo, hi = min(operating), max(operating)
    compliance = {"marginal": 0.0, "compliant": 0.6, "exceeds": 1.0}
    community = {"divided": 0.0, "neutral": 0.5, "supportive": 1.0}
    footprint = {"greenfield": 0.0, "brownfield": 0.45, "existing_site": 1.0}
    pts = [(0.0, 1.0), (8.0, 0.85), (20.0, 0.4), (40.0, 0.0)]

    def interp(x: float) -> float:
        for (x0, v0), (x1, v1) in zip(pts, pts[1:], strict=False):
            if x0 <= x <= x1:
                return v0 + (v1 - v0) * (x - x0) / (x1 - x0)
        raise AssertionError(x)

    out = {}
    for alt, m in data.items():
        v = {
            "capital_cost": (100 - m["capital_cost"]) / 60,
            "operating_cost": (hi - m["operating_cost"]) / (hi - lo),
            "funding_premium": (4 - m["funding_premium"]) / 4,
            "capacity_margin": (m["capacity_margin"] - 10) / 40,
            "outage_hours": interp(m["outage_hours"])
            if outage == "piecewise"
            else (40 - m["outage_hours"]) / 40,
            "compliance": compliance[m["compliance"]],
            "community": community[m["community"]],
            "footprint": footprint[m["footprint"]],
            "track_record": m["track_record"] / 100,
        }
        out[alt] = sum(w[k] * v[k] for k in w)
    return out


def ratings(name: str) -> dict[str, float]:
    source = build.BASE_RATINGS if name == "default" else build.CONSENT_RATINGS
    return {k: float(v) for k, v in source.items()}


# ---- structural acceptance ---------------------------------------------------------------
def test_shipped_project_file_matches_the_build_script() -> None:
    assert project() == build.build_project()


def test_the_fixture_actually_exercises_the_b3_acceptance_shape() -> None:
    """Guards the acceptance case itself: a later edit must not quietly simplify it away."""
    p = project()
    tree = p.tree()
    objectives = [i for i in tree.all_ids() if not tree.is_leaf(i)]
    child_counts = {i: len(tree.child_ids(i)) for i in objectives}
    assert len(tree.child_ids(None)) == 4  # four parent objectives
    assert {3, 2, 1}.issubset(set(child_counts.values()))  # different numbers of children
    assert child_counts["delivery"] == 1  # an only child
    assert max(len(tree.path(leaf)) for leaf in tree.leaves()) == 3  # a deeper nested branch
    scales = {c.scale.type.value for c in p.criteria if c.scale}
    assert {"ratio", "interval"} & scales and {"ordinal", "categorical"} <= scales
    assert p.weight_profiles[0].judgements["footprint"] == 0  # zero inside a valid group
    assert len(p.weight_profiles) >= 2
    assert any(s.weight_profile_id for s in p.scenarios)  # a scenario profile reference


# ---- weights ------------------------------------------------------------------------------
@pytest.mark.parametrize("profile_id", ["default", "consent_led"])
def test_hierarchical_weights_match_the_hand_written_products(profile_id: str) -> None:
    p = project()
    preview = svc.preview_weights(
        p, p.analysis.model_copy(update={"weight_profile_id": profile_id})
    )
    expected = oracle_weights(ratings(profile_id))
    assert preview.weights_ready
    assert preview.global_weights == pytest.approx(expected, abs=1e-12)
    assert math.fsum(preview.global_weights.values()) == pytest.approx(1.0, abs=1e-12)
    # The only child's local weight is one, and no rating was invented for it.
    assert preview.local_weights["track_record"] == 1.0
    assert "track_record" not in p.weight_profiles[0].judgements
    assert preview.sibling_rating_totals["delivery"] is None
    # Branch shares explain the same arithmetic without being extra weight.
    assert preview.path_shares["reliability"] == pytest.approx(
        preview.global_weights["capacity_margin"] + preview.global_weights["outage_hours"],
        abs=1e-12,
    )
    assert {k: preview.path_shares[k] for k in expected} == preview.global_weights


def test_a_zero_rating_is_a_valid_zero_weight_not_a_missing_judgement() -> None:
    p = project()
    preview = svc.preview_weights(p)
    assert preview.weights_ready  # the sibling group is still valid
    assert preview.local_weights["footprint"] == 0.0
    assert preview.global_weights["footprint"] == 0.0
    assert preview.global_weights["community"] == pytest.approx(preview.path_shares["consent"])
    # Clearing the same rating is a different state: the group becomes incomplete.
    cleared = svc.preview_weights(ps.clear_judgement(p, "footprint"))
    assert not cleared.weights_ready and cleared.global_weights == {}
    assert "MISSING_JUDGEMENT" in {i.code for i in cleared.diagnostics}


# ---- results and profile resolution -------------------------------------------------------
def test_engine_matches_the_independent_oracle_for_each_profile() -> None:
    p = project()
    for profile_id in ["default", "consent_led"]:
        expected = oracle_values(ratings(profile_id))
        cfg = p.analysis.model_copy(update={"weight_profile_id": profile_id})
        result = svc.evaluate_project(p, cfg)
        for r in result.ranking:
            assert r.value == pytest.approx(expected[r.alternative_id], abs=1e-12)
        assert [r.alternative_id for r in result.ranking] == sorted(
            expected, key=lambda k: -expected[k]
        )


def test_the_two_profiles_genuinely_disagree() -> None:
    """A fixture whose profiles ranked alike would not prove profile isolation at all."""
    p = project()
    order = {
        profile_id: [
            r.alternative_id
            for r in svc.evaluate_project(
                p, p.analysis.model_copy(update={"weight_profile_id": profile_id})
            ).ranking
        ]
        for profile_id in ["default", "consent_led"]
    }
    assert order["default"] != order["consent_led"]


def test_scenario_reference_selects_its_profile_and_its_value_function() -> None:
    p = project()
    cfg = p.analysis.model_copy(update={"scenario_id": "consent_review"})
    assert p.resolve_profile(cfg).id == "consent_led"
    expected = oracle_values(ratings("consent_led"), outage="linear")
    for r in svc.evaluate_project(p, cfg).ranking:
        assert r.value == pytest.approx(expected[r.alternative_id], abs=1e-12)
    # An explicit profile still beats the scenario's own reference.
    explicit = cfg.model_copy(update={"weight_profile_id": "default"})
    assert p.resolve_profile(explicit).id == "default"
    override = oracle_values(ratings("default"), outage="linear")
    for r in svc.evaluate_project(p, explicit).ranking:
        assert r.value == pytest.approx(override[r.alternative_id], abs=1e-12)


def test_the_referenced_profile_cannot_be_deleted_without_an_explicit_replacement() -> None:
    p = project()
    assert ps.weight_profile_references(p, "consent_led") == [
        "scenarios[consent_review].weight_profile_id"
    ]
    with pytest.raises(ModelEditError, match="explicit replacement"):
        ps.remove_weight_profile(p, "consent_led")
    replaced = ps.remove_weight_profile(p, "consent_led", "default")
    assert [x.id for x in replaced.weight_profiles] == ["default"]
    assert replaced.scenarios[0].weight_profile_id == "default"
    # The replacement is a real reference update, not a silent fallback: results now follow it.
    cfg = replaced.analysis.model_copy(update={"scenario_id": "consent_review"})
    assert replaced.resolve_profile(cfg).id == "default"
    expected = oracle_values(ratings("default"), outage="linear")
    for r in svc.evaluate_project(replaced, cfg).ranking:
        assert r.value == pytest.approx(expected[r.alternative_id], abs=1e-12)


def test_duplicating_a_profile_reproduces_results_then_diverges_independently() -> None:
    p = project()
    duplicated = ps.duplicate_weight_profile(p, "default", "Balanced (copy)", "copy")
    base = svc.evaluate_project(p)
    for r in svc.evaluate_project(
        duplicated, duplicated.analysis.model_copy(update={"weight_profile_id": "copy"})
    ).ranking:
        assert r.value == pytest.approx(
            next(x.value for x in base.ranking if x.alternative_id == r.alternative_id), abs=1e-15
        )
    edited = ps.set_judgement(duplicated, "lifecycle_cost", 10.0, "copy")
    changed = oracle_values({**ratings("default"), "lifecycle_cost": 10.0})
    for r in svc.evaluate_project(
        edited, edited.analysis.model_copy(update={"weight_profile_id": "copy"})
    ).ranking:
        assert r.value == pytest.approx(changed[r.alternative_id], abs=1e-12)
    # The source profile and every other profile are untouched.
    for r in svc.evaluate_project(edited).ranking:
        assert r.value == pytest.approx(
            next(x.value for x in base.ranking if x.alternative_id == r.alternative_id), abs=1e-15
        )
    assert edited.weight_profiles[0].judgements == p.weight_profiles[0].judgements
