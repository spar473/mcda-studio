"""The invented method exemplars against independent oracles (docs/design/method-exemplars.md).

Each study is checked four ways:

- the shipped ``project.json`` and gallery starter are exactly what ``build.py`` writes, and the
  project says that it is invented;
- every stated method's numbers equal an independent recomputation (``ahp_oracle`` for AHP; a
  plain-Python recomputation of the additive value, written here, for MAVT);
- a table of headline facts, recorded from those oracles at build time on 18 November 2026, is
  pinned, so a changed input cannot move the engine and the oracle together unnoticed;
- the shared registration rules hold.

The inputs are the author's invented judgements, so the headline facts are properties of this data,
not claims about any real decision.
"""

import hashlib
import importlib.util
import json
import math
import random
import re
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import ahp_oracle as oracle
import comparison_oracle
import feasibility_oracle
import numpy as np
import promethee_oracle
import pytest
import smaa_sampling_oracle
import sorting_oracle as values_oracle
from fastapi.testclient import TestClient

from mcda_studio.api import create_app
from mcda_studio.domain.errors import McdaError
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import (
    AhpResult,
    MavtResult,
    MavtSortingResult,
    PrometheeResult,
    SmaaResult,
)
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import comparison_service as cs
from mcda_studio.services import feasibility_service as fs
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository

ROOT = Path(__file__).parents[2]
repo = JsonProjectRepository()
TOL = 1e-10


def load_build(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"{name}_build", ROOT / "examples" / name / "build.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project_of(name: str) -> Project:
    return repo.load(ROOT / "examples" / name / "project.json")


#: Every shipped exemplar; each development appends its study here.
STUDIES = ["clinic_site_selection", "flood_defence_options", "engineering_trade_study"]


@pytest.mark.parametrize("study", STUDIES)
def test_the_project_and_starter_are_exactly_what_the_script_writes(
    study: str, tmp_path: Path
) -> None:
    build = load_build(study)
    repo.save(build.build_project(), tmp_path / "project.json")
    shipped = (ROOT / "examples" / study / "project.json").read_bytes()
    assert (tmp_path / "project.json").read_bytes() == shipped
    starter = ROOT / "examples" / "starter_templates" / study
    assert (starter / "project.json").read_bytes() == shipped
    manifest = json.loads((starter / "manifest.json").read_text())
    assert manifest["artifacts"][0]["sha256"] == hashlib.sha256(shipped).hexdigest()
    assert manifest["source_example"] == f"examples/{study}"


@pytest.mark.parametrize("study", STUDIES)
def test_each_study_says_that_it_is_invented(study: str) -> None:
    assert "invented" in project_of(study).description.lower()
    readme = (ROOT / "examples" / study / "README.md").read_text()
    assert "invented" in readme[:300].lower()


# ---- independent recomputation ---------------------------------------------------------------
def lapack(items: list[str], judgements: list[dict[str, Any]]) -> tuple[list[float], float]:
    """Priorities and λmax of one matrix by LAPACK, from the stored judgements."""
    m = np.array([[float(x) for x in row] for row in oracle.matrix(items, judgements)])
    values, vectors = np.linalg.eig(m)
    k = int(np.argmax(values.real))
    w = np.abs(vectors[:, k].real)
    return list(w / w.sum()), float(values[k].real)


def mavt_values(raw: dict[str, Any], profile_id: str) -> dict[str, float]:
    """Additive value written out by hand: shares within sibling groups, multiplied down each
    path, times each leaf's partial value. Linear and qualitative functions only."""
    ratings = next(p for p in raw["weight_profiles"] if p["id"] == profile_id)["judgements"]
    nodes = {n["id"]: n for n in raw["criteria"]}
    kids: dict[str | None, list[str]] = {}
    for n in sorted(raw["criteria"], key=lambda n: n["order"]):
        kids.setdefault(n.get("parent_id"), []).append(n["id"])

    def weight(node: str) -> float:
        siblings = kids[nodes[node].get("parent_id")]
        local = (
            1.0 if len(siblings) == 1 else ratings[node] / math.fsum(ratings[s] for s in siblings)
        )
        parent = nodes[node].get("parent_id")
        return local if parent is None else local * weight(parent)

    def partial(leaf: str, x: float | str) -> float:
        node = nodes[leaf]
        function, scale = node["value_function"], node["scale"]
        if function["kind"] == "qualitative":
            return float(function["mapping"][x])
        low, high = scale["lower"], scale["upper"]
        share = (float(x) - low) / (high - low)
        return share if function["direction"] == "increasing" else 1.0 - share

    leaves = [n for n in nodes if n not in kids]
    measured = {(p["alternative_id"], p["criterion_id"]): p["value"] for p in raw["performances"]}
    return {
        a["id"]: math.fsum(weight(leaf) * partial(leaf, measured[a["id"], leaf]) for leaf in leaves)
        for a in raw["alternatives"]
    }


def ahp(project: Project, synthesis: str) -> AhpResult:
    cfg = project.analysis.model_copy(
        update={"method": "ahp", "parameters": {"synthesis": synthesis}}
    )
    result = svc.evaluate_project(project, cfg)
    assert isinstance(result, AhpResult)
    return result


def mavt(project: Project, profile_id: str) -> MavtResult:
    cfg = project.analysis.model_copy(
        update={"method": "mavt", "weight_profile_id": profile_id, "parameters": {}}
    )
    result = svc.evaluate_project(project, cfg)
    assert isinstance(result, MavtResult)
    return result


# ---- clinic site selection ---------------------------------------------------------------------
CLINIC = "clinic_site_selection"
SITES = ["town_centre", "school_site", "hospital_grounds", "edge_of_town"]

#: Headline facts, read from the oracle-checked run on 18 November 2026. They are put to the owner
#: for review in docs/development/clinic-site-selection-verification.md; none is a claim about a
#: real decision.
CLINIC_AHP_ORDER = {
    "distributive": SITES,
    "ideal": SITES,
}
CLINIC_AHP_PRIORITY = {
    "town_centre": 0.3370,
    "school_site": 0.2728,
    "hospital_grounds": 0.2058,
    "edge_of_town": 0.1844,
}
CLINIC_GLOBAL = {
    "travel_time": 0.3597,
    "bus_service": 0.1799,
    "build_cost": 0.1980,
    "running_cost": 0.0990,
    "expansion": 0.0545,
    "support": 0.1089,
}
CLINIC_MAVT = {
    "default": {  # Access-led
        "order": ["school_site", "town_centre", "hospital_grounds", "edge_of_town"],
        "value": {
            "school_site": 0.6643,
            "town_centre": 0.6455,
            "hospital_grounds": 0.6107,
            "edge_of_town": 0.3925,
        },
    },
    "cost_led": {
        "order": ["school_site", "hospital_grounds", "town_centre", "edge_of_town"],
        "value": {
            "school_site": 0.6940,
            "hospital_grounds": 0.6201,
            "town_centre": 0.5309,
            "edge_of_town": 0.5125,
        },
    },
}
CLINIC_UNITS = {
    "travel_time": "min",
    "bus_service": "services/h",
    "build_cost": "NZD m",
    "running_cost": "NZD k/year",
}


def test_the_clinic_study_states_exactly_mavt_and_ahp() -> None:
    project = project_of(CLINIC)
    assert project.ahp is not None
    assert project.sorting is None and project.smaa is None and project.promethee is None
    assert project.requirements is None
    assert project.analysis.method == "ahp"
    assert [p.id for p in project.weight_profiles] == ["default", "cost_led"]
    assert len(project.alternatives) == 4 and len(project.tree().leaves()) == 6
    units = {n.id: n.scale.unit for n in project.criteria if n.scale and n.scale.is_numeric}
    assert units == CLINIC_UNITS
    judged = sum(len(g.judgements) for g in project.ahp.criteria) + sum(
        len(g.judgements) for g in project.ahp.alternatives
    )
    assert judged == 42


def check_ahp_against_the_oracle(project: Project, synthesis: str) -> None:
    raw = project.model_dump(mode="json")
    expected = oracle.evaluate(raw, lambda items, js: lapack(items, js)[0], synthesis)  # type: ignore[arg-type]
    result = ahp(project, synthesis)
    for node, value in expected["local"].items():
        assert result.local_priorities[node] == pytest.approx(float(value), abs=TOL)
    for leaf, value in expected["global"].items():
        assert result.global_priorities[leaf] == pytest.approx(float(value), abs=TOL)
    by_id = {a.alternative_id: a for a in result.alternatives}
    for alt, value in expected["overall"].items():
        assert by_id[alt].priority == pytest.approx(float(value), abs=TOL)
        if synthesis == "ideal":
            assert by_id[alt].ideal_score == pytest.approx(float(expected["ideal"][alt]), abs=TOL)
    assert {a: by_id[a].rank for a in by_id} == oracle.ranks(expected["overall"])
    assert math.fsum(result.global_priorities.values()) == pytest.approx(1.0, abs=TOL)


def check_every_matrix_against_the_oracle(project: Project, matrices: int) -> None:
    result = ahp(project, "distributive")
    assert result.consistency_threshold == 0.10
    assert len(result.matrices) == matrices
    for m in result.matrices:
        judgements = [j.model_dump() for j in m.judgements]
        weights, lam = lapack(m.items, judgements)
        for item, w in zip(m.items, weights, strict=True):
            assert m.priorities[item] == pytest.approx(w, abs=1e-9)
        ci, ri, cr = oracle.consistency(lam, len(m.items))
        assert m.lambda_max == pytest.approx(lam, abs=1e-9)
        assert m.consistency_index == pytest.approx(float(ci), abs=1e-9)
        assert m.random_index == pytest.approx(float(ri), abs=1e-12)
        assert m.consistency_ratio == pytest.approx(float(cr), abs=1e-9)
        assert m.inconsistent == (float(cr) > 0.10)
        if len(m.items) >= 3:
            entries = [[float(x) for x in row] for row in oracle.matrix(m.items, judgements)]
            triad = oracle.most_inconsistent_triad(entries, m.items)
            assert triad is not None and m.most_inconsistent_triad is not None
            assert m.most_inconsistent_triad.items == triad[0]
            assert m.most_inconsistent_triad.index == pytest.approx(float(triad[1]), abs=1e-9)
            assert m.most_inconsistent_triad.consistent_value == pytest.approx(
                float(triad[2]), abs=1e-9
            )


@pytest.mark.parametrize("synthesis", ["distributive", "ideal"])
def test_the_clinic_ahp_numbers_equal_the_independent_oracle(synthesis: str) -> None:
    check_ahp_against_the_oracle(project_of(CLINIC), synthesis)


def test_every_clinic_matrix_equals_the_oracle_on_consistency_and_triads() -> None:
    check_every_matrix_against_the_oracle(project_of(CLINIC), 4 + 6)


@pytest.mark.parametrize("profile_id", ["default", "cost_led"])
def test_the_clinic_mavt_values_equal_the_hand_written_recomputation(profile_id: str) -> None:
    project = project_of(CLINIC)
    expected = mavt_values(project.model_dump(mode="json"), profile_id)
    result = mavt(project, profile_id)
    got = {row.alternative_id: row.value for row in result.ranking}
    for alt, value in expected.items():
        assert got[alt] == pytest.approx(value, abs=1e-12)


@pytest.mark.parametrize("synthesis", ["distributive", "ideal"])
def test_the_clinic_ahp_headline_order(synthesis: str) -> None:
    result = ahp(project_of(CLINIC), synthesis)
    assert [a.alternative_id for a in result.alternatives] == CLINIC_AHP_ORDER[synthesis]
    assert [a.rank for a in result.alternatives] == [1, 2, 3, 4]


def test_the_clinic_ahp_headline_priorities_and_the_one_flagged_matrix() -> None:
    result = ahp(project_of(CLINIC), "distributive")
    for a in result.alternatives:
        assert a.priority == pytest.approx(CLINIC_AHP_PRIORITY[a.alternative_id], abs=5e-5)
    for leaf, value in CLINIC_GLOBAL.items():
        assert result.global_priorities[leaf] == pytest.approx(value, abs=5e-5)
    flagged = [m for m in result.matrices if m.inconsistent]
    assert [(m.kind, m.group_id) for m in flagged] == [("alternatives", "support")]
    assert flagged[0].consistency_ratio == pytest.approx(0.1640, abs=5e-4)
    assert flagged[0].most_inconsistent_triad is not None
    assert flagged[0].most_inconsistent_triad.items == (
        "hospital_grounds",
        "edge_of_town",
        "school_site",
    )
    assert max(m.consistency_ratio for m in result.matrices if not m.inconsistent) < 0.035


@pytest.mark.parametrize("profile_id", ["default", "cost_led"])
def test_the_clinic_mavt_headline_order_and_leaders(profile_id: str) -> None:
    result = mavt(project_of(CLINIC), profile_id)
    expected = CLINIC_MAVT[profile_id]
    assert [row.alternative_id for row in result.ranking] == expected["order"]
    got = {row.alternative_id: row.value for row in result.ranking}
    for alt, value in expected["value"].items():
        assert got[alt] == pytest.approx(value, abs=5e-5)


def test_the_two_methods_name_different_leaders_and_share_no_weights() -> None:
    """The design intent is a readable difference, not agreement; neither reads the other."""
    project = project_of(CLINIC)
    assert ahp(project, "distributive").alternatives[0].alternative_id == "town_centre"
    assert mavt(project, "default").ranking[0].alternative_id == "school_site"
    assert mavt(project, "cost_led").ranking[0].alternative_id == "school_site"
    result = ahp(project, "distributive")
    assert result.weight_profile_id is None and result.scenario_id is None


@pytest.mark.parametrize("method", ["mavt_sorting", "smaa2", "promethee2"])
def test_unstated_methods_fail_with_their_usual_typed_errors(method: str) -> None:
    project = project_of(CLINIC)
    cfg = project.analysis.model_copy(update={"method": method, "parameters": {}})
    with pytest.raises(McdaError):
        svc.evaluate_project(project, cfg)


# ---- flood defence options ---------------------------------------------------------------------
FLOOD = "flood_defence_options"
FLOOD_ALTS = ["sea_wall", "dune_pumping", "gates_road", "managed_retreat", "maintain_existing"]

REASON_CLASSES = (
    ("missing", r"^no measurement$"),
    ("below_minimum", r" is below the minimum "),
    ("not_above_minimum", r" is not above the exclusive minimum "),
    ("within", r" is within the limits$"),
    ("allowed", r" is allowed$"),
    ("not_allowed", r" is not one of the allowed labels "),
)


def reason_class(reason: str) -> str:
    found = [name for name, pattern in REASON_CLASSES if re.search(pattern, reason)]
    assert len(found) == 1, reason
    return found[0]


#: Headline facts, read from the oracle-checked run on 18 November 2026 (put to the owner for review
#: in docs/development/flood-defence-options-verification.md; none is a claim about real flooding).
#: Per option: (protection standard status and reason class, consent status and class, overall).
FLOOD_FEASIBILITY = {
    "sea_wall": (("pass", "within"), ("pass", "allowed"), "pass"),
    "dune_pumping": (("pass", "within"), ("pass", "allowed"), "pass"),
    "gates_road": (("pass", "within"), ("pass", "allowed"), "pass"),
    "managed_retreat": (("pass", "within"), ("fail", "not_allowed"), "fail"),
    "maintain_existing": (("fail", "below_minimum"), ("pass", "allowed"), "fail"),
}
FLOOD_MAVT = {
    "default": {  # Safety-first
        "order": ["gates_road", "managed_retreat", "sea_wall", "dune_pumping", "maintain_existing"],
        "value": {
            "gates_road": 0.6639,
            "managed_retreat": 0.6482,
            "sea_wall": 0.5516,
            "dune_pumping": 0.4949,
            "maintain_existing": 0.3444,
        },
    },
    "cost_conscious": {
        "order": ["managed_retreat", "gates_road", "dune_pumping", "maintain_existing", "sea_wall"],
        "value": {
            "managed_retreat": 0.6713,
            "gates_road": 0.5871,
            "dune_pumping": 0.5039,
            "maintain_existing": 0.5010,
            "sea_wall": 0.4844,
        },
    },
}
#: PROMETHEE II: (positive, negative, net) flow per option, in rank order.
FLOOD_PROMETHEE = {
    "managed_retreat": (0.3877, 0.3075, 0.0802),
    "gates_road": (0.3702, 0.3008, 0.0694),
    "maintain_existing": (0.4763, 0.4375, 0.0388),
    "dune_pumping": (0.3063, 0.3481, -0.0419),
    "sea_wall": (0.3438, 0.4902, -0.1465),
}
#: PROMETHEE I relation for each pair, as (preferred, other) or "incomparable".
FLOOD_RELATIONS = {
    frozenset(("sea_wall", "dune_pumping")): "incomparable",
    frozenset(("gates_road", "sea_wall")): ("gates_road", "sea_wall"),
    frozenset(("managed_retreat", "sea_wall")): ("managed_retreat", "sea_wall"),
    frozenset(("maintain_existing", "sea_wall")): ("maintain_existing", "sea_wall"),
    frozenset(("gates_road", "dune_pumping")): ("gates_road", "dune_pumping"),
    frozenset(("managed_retreat", "dune_pumping")): ("managed_retreat", "dune_pumping"),
    frozenset(("dune_pumping", "maintain_existing")): "incomparable",
    frozenset(("gates_road", "managed_retreat")): "incomparable",
    frozenset(("gates_road", "maintain_existing")): "incomparable",
    frozenset(("managed_retreat", "maintain_existing")): "incomparable",
}
#: The pairs that MAVT (Safety-first) and PROMETHEE II order differently.
FLOOD_DIFFERING_PAIRS = {
    frozenset(("sea_wall", "dune_pumping")),
    frozenset(("sea_wall", "maintain_existing")),
    frozenset(("dune_pumping", "maintain_existing")),
    frozenset(("gates_road", "managed_retreat")),
}
FLOOD_UNITS = {
    "protection_standard": "years",
    "capital_cost": "NZD m",
    "maintenance_cost": "NZD m",
    "habitat": "ha",
    "disruption": "months",
}


def promethee(project: Project) -> PrometheeResult:
    cfg = project.analysis.model_copy(update={"method": "promethee2", "parameters": {}})
    result = svc.evaluate_project(project, cfg)
    assert isinstance(result, PrometheeResult)
    return result


def test_the_flood_study_states_exactly_mavt_requirements_and_promethee() -> None:
    project = project_of(FLOOD)
    assert project.promethee is not None and project.requirements is not None
    assert project.sorting is None and project.smaa is None and project.ahp is None
    assert project.analysis.method == "mavt"
    assert [p.id for p in project.weight_profiles] == ["default", "cost_conscious"]
    assert [a.id for a in project.alternatives] == FLOOD_ALTS
    assert len(project.tree().leaves()) == 7 and project.scenarios == []
    assert [(r.kind, r.criterion_id) for r in project.requirements] == [
        ("bound", "protection_standard"),
        ("labels", "consent"),
    ]
    units = {n.id: n.scale.unit for n in project.criteria if n.scale and n.scale.is_numeric}
    assert units == FLOOD_UNITS
    assert len(project.promethee.criteria) == 7


def test_the_flood_feasibility_statuses_equal_the_independent_oracle() -> None:
    project = project_of(FLOOD)
    raw = project.model_dump(mode="json")
    result = fs.check_feasibility(project)
    expected = feasibility_oracle.evaluate(raw)
    assert [a.alternative_id for a in result.alternatives] == FLOOD_ALTS
    for a in result.alternatives:
        mine = [(c.status, reason_class(c.reason)) for c in a.checks]
        assert mine == expected[a.alternative_id]["checks"], a.alternative_id
        assert a.status == expected[a.alternative_id]["status"]
    for k, s in enumerate(result.summary):
        statuses = [expected[a]["checks"][k][0] for a in expected]
        assert (s.passed, s.failed, s.unknown) == tuple(
            statuses.count(v) for v in ("pass", "fail", "unknown")
        )


def test_the_flood_feasibility_headline_grid_and_the_exact_limit() -> None:
    project = project_of(FLOOD)
    result = fs.check_feasibility(project)
    for a in result.alternatives:
        first, second, overall = FLOOD_FEASIBILITY[a.alternative_id]
        assert [(c.status, reason_class(c.reason)) for c in a.checks] == [first, second]
        assert a.status == overall
    assert [(s.passed, s.failed, s.unknown) for s in result.summary] == [(4, 1, 0), (4, 1, 0)]
    # One option sits exactly on the inclusive 100-year limit and passes.
    requirement = project.requirements[0]  # type: ignore[index]
    assert requirement.minimum == 100.0 and requirement.minimum_inclusive  # type: ignore[union-attr]
    measured = {
        p.alternative_id: p.value
        for p in project.performances
        if p.criterion_id == "protection_standard"
    }
    assert [a for a, v in measured.items() if v == 100.0] == ["dune_pumping"]


@pytest.mark.parametrize("profile_id", ["default", "cost_conscious"])
def test_the_flood_mavt_values_equal_the_hand_written_recomputation(profile_id: str) -> None:
    project = project_of(FLOOD)
    expected = mavt_values(project.model_dump(mode="json"), profile_id)
    got = {row.alternative_id: row.value for row in mavt(project, profile_id).ranking}
    for alt, value in expected.items():
        assert got[alt] == pytest.approx(value, abs=1e-12)


@pytest.mark.parametrize("profile_id", ["default", "cost_conscious"])
def test_the_flood_mavt_headline_order_and_values(profile_id: str) -> None:
    result = mavt(project_of(FLOOD), profile_id)
    expected = FLOOD_MAVT[profile_id]
    assert [row.alternative_id for row in result.ranking] == expected["order"]
    got = {row.alternative_id: row.value for row in result.ranking}
    for alt, value in expected["value"].items():
        assert got[alt] == pytest.approx(value, abs=5e-5)


def test_the_flood_promethee_numbers_equal_the_independent_oracle() -> None:
    project = project_of(FLOOD)
    exact = promethee_oracle.flows(project.model_dump(mode="json"))
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
    assert {f.alternative_id: f.rank for f in result.flows} == promethee_oracle.ranks(exact["net"])
    for pair in result.partial_order:
        expected = promethee_oracle.relation(exact, pair.alternative_a, pair.alternative_b)
        assert expected == ("a" if pair.relation == "preferred" else pair.relation)
    assert len(result.partial_order) == len(FLOOD_ALTS) * (len(FLOOD_ALTS) - 1) // 2


def test_the_flood_promethee_explanation_split_equals_the_oracle() -> None:
    project = project_of(FLOOD)
    exact = promethee_oracle.flows(project.model_dump(mode="json"))
    explanation = promethee(project).explanation
    assert explanation.available, explanation.unavailable_reason
    n = len(exact["alternatives"])
    for pair in explanation.pairs:
        a, b = pair.alternative_a, pair.alternative_b
        gap, head, via = promethee_oracle.split(exact, a, b)
        assert gap == head + via
        assert abs(pair.flow_gap - float(gap)) <= TOL
        assert abs(pair.head_to_head - float(head)) <= TOL
        assert abs(pair.via_others - float(via)) <= TOL
        for row in pair.criteria:
            leaf = row.criterion_id
            contribution = exact["weights"][leaf] * (
                exact["criterion"][leaf][a] - exact["criterion"][leaf][b]
            )
            assert abs(row.promethee_contribution - float(contribution)) <= TOL
        assert abs(sum(r.promethee_contribution for r in pair.criteria) - pair.flow_gap) <= 1e-9
        assert n == 5


def test_the_flood_promethee_headline_flows_relations_and_differing_pairs() -> None:
    result = promethee(project_of(FLOOD))
    assert [f.alternative_id for f in result.flows] == list(FLOOD_PROMETHEE)
    for f in result.flows:
        positive, negative, net = FLOOD_PROMETHEE[f.alternative_id]
        assert f.positive_flow == pytest.approx(positive, abs=5e-5)
        assert f.negative_flow == pytest.approx(negative, abs=5e-5)
        assert f.net_flow == pytest.approx(net, abs=5e-5)
    relations = {
        frozenset((p.alternative_a, p.alternative_b)): (
            (p.alternative_a, p.alternative_b) if p.relation == "preferred" else p.relation
        )
        for p in result.partial_order
    }
    assert relations == FLOOD_RELATIONS
    assert result.explanation.available
    assert {
        frozenset((p.alternative_a, p.alternative_b)) for p in result.explanation.pairs
    } == FLOOD_DIFFERING_PAIRS


def test_a_difference_exactly_at_a_threshold_counts_no_preference() -> None:
    """Managed retreat disturbs 0.8 ha and dune restoration 0.4 ha: the difference is exactly the
    0.4 ha indifference threshold, so neither is preferred on habitat."""
    project = project_of(FLOOD)
    raw = project.model_dump(mode="json")
    exact = promethee_oracle.flows(raw)
    habitat = promethee_oracle.measurements(raw)["habitat"]
    threshold = promethee_oracle.exact(
        next(c for c in raw["promethee"]["criteria"] if c["criterion_id"] == "habitat")["function"][
            "q"
        ]
    )
    assert habitat["managed_retreat"] - habitat["dune_pumping"] == threshold
    assert exact["degrees"]["habitat"]["dune_pumping", "managed_retreat"] == 0
    assert exact["degrees"]["habitat"]["managed_retreat", "dune_pumping"] == 0
    engine = promethee(project).preference_matrix
    assert engine["dune_pumping"]["managed_retreat"] == pytest.approx(
        float(exact["preference"]["dune_pumping", "managed_retreat"]), abs=TOL
    )


def test_requirements_never_filter_or_reorder_a_ranking() -> None:
    """A failed option stays in every ranking, and removing the requirements changes no value."""
    project = project_of(FLOOD)
    bare = ps.set_requirements(project, [])
    for profile_id in ("default", "cost_conscious"):
        with_req = mavt(project, profile_id)
        without = mavt(bare, profile_id)
        assert [(r.alternative_id, r.value) for r in with_req.ranking] == [
            (r.alternative_id, r.value) for r in without.ranking
        ]
        assert len(with_req.ranking) == 5
    assert [(f.alternative_id, f.net_flow) for f in promethee(project).flows] == [
        (f.alternative_id, f.net_flow) for f in promethee(bare).flows
    ]
    # Both failed options are ranked: one leads two readings, the other is third in PROMETHEE II.
    assert mavt(project, "cost_conscious").ranking[0].alternative_id == "managed_retreat"
    assert promethee(project).flows[0].alternative_id == "managed_retreat"
    assert [f.alternative_id for f in promethee(project).flows].index("maintain_existing") == 2


@pytest.mark.parametrize("method", ["mavt_sorting", "smaa2", "ahp"])
def test_the_flood_study_unstated_methods_fail_with_their_usual_typed_errors(method: str) -> None:
    project = project_of(FLOOD)
    cfg = project.analysis.model_copy(update={"method": method, "parameters": {}})
    with pytest.raises(McdaError):
        svc.evaluate_project(project, cfg)


# ---- the comparison view, for every study --------------------------------------------------------
@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    with TestClient(create_app(tmp_path_factory.mktemp("store"), frontend_dir=False)) as c:
        yield c


#: (study, the context the comparison is run in, the methods that run for it).
COMPARISON_CASES = [
    ("clinic_site_selection", {}, ["ahp", "mavt"]),
    ("flood_defence_options", {}, ["mavt", "promethee2"]),
    ("flood_defence_options", {"weight_profile_id": "cost_conscious"}, ["mavt", "promethee2"]),
    ("engineering_trade_study", {}, ["ahp", "mavt", "mavt_sorting", "promethee2", "smaa2"]),
    (
        "engineering_trade_study",
        {"weight_profile_id": "cost_led"},
        ["ahp", "mavt", "mavt_sorting", "promethee2", "smaa2"],
    ),
    (
        "engineering_trade_study",
        {"scenario_id": "diminishing_endurance"},
        ["ahp", "mavt", "mavt_sorting", "promethee2", "smaa2"],
    ),
]


@pytest.mark.parametrize(
    ("study", "context", "running"),
    COMPARISON_CASES,
    ids=[f"{s}-{'-'.join(c.values()) or 'saved'}" for s, c, _ in COMPARISON_CASES],
)
def test_the_comparison_equals_the_independent_oracle(
    client: TestClient, study: str, context: dict[str, str], running: list[str]
) -> None:
    project = project_of(study)
    cfg = project.analysis.model_copy(update={"parameters": {}, **context})
    comparison = cs.compare_methods(project, cfg)
    assert [c.method for c in comparison.columns] == [
        "mavt",
        "mavt_sorting",
        "smaa2",
        "promethee2",
        "ahp",
    ]
    bodies: dict[str, Any] = {}
    for column in comparison.columns:
        response = client.post(
            "/api/evaluate",
            json={
                "project": project.model_dump(mode="json"),
                "configuration": column.configuration.model_dump(mode="json"),
            },
        )
        if column.status == "failed":
            assert response.status_code == column.error.status  # type: ignore[union-attr]
            error = response.json()["error"]
            assert error["code"] == column.error.code  # type: ignore[union-attr]
            assert column.cells == [] and column.leaders == []
            continue
        assert response.status_code == 200
        body = response.json()
        bodies[column.method] = body
        expected = comparison_oracle.cells(column.method, body)
        assert [c.alternative_id for c in column.cells] == comparison.alternative_order
        for cell in column.cells:
            own = expected[cell.alternative_id]
            assert (cell.rank, cell.quantity, cell.class_id) == (
                own["rank"],
                own["quantity"],
                own["class"],
            )
        assert column.leaders == comparison_oracle.leaders(column.method, body)
    # Exactly the methods the study states run; every other column is a typed error.
    assert sorted(bodies) == running
    expected_agreement = comparison_oracle.agreement(bodies)
    agreement = comparison.agreement
    assert agreement.leaders_agree == expected_agreement["agree"]
    assert {tuple(g.leaders): g.methods for g in agreement.leader_groups} == expected_agreement[
        "groups"
    ]
    assert [(c.alternative_id, c.sorting_class_id, c.smaa_class_id) for c in agreement.classes] == (
        expected_agreement["classes"]
    )
    assert [r.method for r in agreement.reasons] == expected_agreement["reasons"]
    assert all(r.reasons for r in agreement.reasons)


# ---- engineering trade study ---------------------------------------------------------------------
TRADE = "engineering_trade_study"
W, K, L, T, A = (
    "wheeled_rover",
    "tracked_crawler",
    "legged_walker",
    "tethered_crawler",
    "small_drone",
)
TRADE_ALTS = [W, K, L, T, A]
TRADE_CONTEXTS = [
    ("default", None),
    ("default", "diminishing_endurance"),
    ("cost_led", None),
    ("cost_led", "diminishing_endurance"),
]

#: Headline facts, read from the oracle-checked run on 19 November 2026 (put to the owner for review
#: in docs/development/engineering-trade-study-verification.md; none is a claim about a real
#: vehicle). Per context: the MAVT order, each value, and each concept's sorting class.
TRADE_MAVT = {
    ("default", None): {
        "order": [K, W, T, A, L],
        "value": {K: 0.6845, W: 0.6219, T: 0.5859, A: 0.4615, L: 0.3322},
        "class": {K: "shortlist", W: "reserve", T: "reserve", A: "drop", L: "drop"},
    },
    ("default", "diminishing_endurance"): {
        "order": [K, W, T, A, L],
        "value": {K: 0.7145, W: 0.6591, T: 0.5943, A: 0.4682, L: 0.3531},
        "class": {K: "shortlist", W: "shortlist", T: "reserve", A: "drop", L: "drop"},
    },
    ("cost_led", None): {
        "order": [W, K, T, A, L],
        "value": {W: 0.7257, K: 0.7164, T: 0.6091, A: 0.5623, L: 0.2779},
        "class": {W: "shortlist", K: "shortlist", T: "reserve", A: "reserve", L: "drop"},
    },
    ("cost_led", "diminishing_endurance"): {
        "order": [W, K, T, A, L],
        "value": {W: 0.7469, K: 0.7335, T: 0.6139, A: 0.5661, L: 0.2898},
        "class": {W: "shortlist", K: "shortlist", T: "reserve", A: "reserve", L: "drop"},
    },
}
#: Per concept: (payload status and reason class, maturity status and class, overall).
TRADE_FEASIBILITY = {
    W: (("pass", "within"), ("pass", "allowed"), "pass"),
    K: (("pass", "within"), ("pass", "allowed"), "pass"),
    L: (("pass", "within"), ("fail", "not_allowed"), "fail"),
    T: (("pass", "within"), ("pass", "allowed"), "pass"),
    A: (("fail", "below_minimum"), ("pass", "allowed"), "fail"),
}
#: PROMETHEE II: (positive, negative, net) per concept, in rank order.
TRADE_PROMETHEE = {
    K: (0.4608, 0.1717, 0.2892),
    W: (0.4460, 0.2000, 0.2460),
    T: (0.3308, 0.2722, 0.0586),
    A: (0.2646, 0.4090, -0.1444),
    L: (0.1570, 0.6063, -0.4493),
}
TRADE_AHP = {K: 0.2625, W: 0.2464, T: 0.2219, A: 0.1527, L: 0.1165}
TRADE_AHP_LEAVES = {
    "endurance": 0.2226,
    "payload": 0.1767,
    "obstacle": 0.1403,
    "unit_cost": 0.1980,
    "maintenance": 0.0990,
    "maturity": 0.1089,
    "operator_skill": 0.0545,
}
#: SMAA-2 at the default seed and 10,000 draws: per concept, the share at each rank and in each
#: class, for each run. A share of draws under the stated uncertainty, not a probability.
TRADE_SMAA = {
    "combined": {
        W: ([0.0, 0.5901, 0.4099, 0.0, 0.0], {"shortlist": 0.3301, "reserve": 0.6699, "drop": 0.0}),
        K: ([0.9976, 0.0024, 0.0, 0.0, 0.0], {"shortlist": 0.9662, "reserve": 0.0338, "drop": 0.0}),
        L: ([0.0, 0.0, 0.0, 0.0, 1.0], {"shortlist": 0.0, "reserve": 0.0, "drop": 1.0}),
        T: (
            [0.0024, 0.4075, 0.5901, 0.0, 0.0],
            {"shortlist": 0.3013, "reserve": 0.6987, "drop": 0.0},
        ),
        A: ([0.0, 0.0, 0.0, 1.0, 0.0], {"shortlist": 0.0, "reserve": 0.0870, "drop": 0.9130}),
    },
    "performance": {
        W: ([0.0, 0.5907, 0.4093, 0.0, 0.0], {"shortlist": 0.0, "reserve": 1.0, "drop": 0.0}),
        K: ([1.0, 0.0, 0.0, 0.0, 0.0], {"shortlist": 1.0, "reserve": 0.0, "drop": 0.0}),
        L: ([0.0, 0.0, 0.0, 0.0, 1.0], {"shortlist": 0.0, "reserve": 0.0, "drop": 1.0}),
        T: ([0.0, 0.4093, 0.5907, 0.0, 0.0], {"shortlist": 0.4093, "reserve": 0.5907, "drop": 0.0}),
        A: ([0.0, 0.0, 0.0, 1.0, 0.0], {"shortlist": 0.0, "reserve": 0.0, "drop": 1.0}),
    },
    "preference": {
        W: ([0.0, 0.9223, 0.0777, 0.0, 0.0], {"shortlist": 0.3128, "reserve": 0.6872, "drop": 0.0}),
        K: ([1.0, 0.0, 0.0, 0.0, 0.0], {"shortlist": 0.9917, "reserve": 0.0083, "drop": 0.0}),
        L: ([0.0, 0.0, 0.0, 0.0, 1.0], {"shortlist": 0.0, "reserve": 0.0, "drop": 1.0}),
        T: ([0.0, 0.0777, 0.9223, 0.0, 0.0], {"shortlist": 0.0, "reserve": 1.0, "drop": 0.0}),
        A: ([0.0, 0.0, 0.0, 1.0, 0.0], {"shortlist": 0.0, "reserve": 0.0914, "drop": 0.9086}),
    },
}
#: The leaders of each method, per context.
TRADE_LEADERS = {
    "saved": {"mavt": K, "mavt_sorting": K, "smaa2": K, "promethee2": K, "ahp": K},
    "cost_led": {"mavt": W, "mavt_sorting": W, "smaa2": K, "promethee2": K, "ahp": K},
    "diminishing_endurance": {"mavt": K, "mavt_sorting": K, "smaa2": K, "promethee2": K, "ahp": K},
}
TRADE_UNITS = {
    "endurance": "min",
    "payload": "kg",
    "unit_cost": "NZD k",
    "maintenance": "NZD k/year",
}
EXPLORATION_DRAWS = 10_000


def evaluate_with(project: Project, method: str, **update: Any) -> Any:
    cfg = project.analysis.model_copy(update={"method": method, "parameters": {}, **update})
    return svc.evaluate_project(project, cfg)


def smaa(project: Project, run: str) -> SmaaResult:
    result = evaluate_with(project, "smaa2", parameters={"uncertainty": run})
    assert isinstance(result, SmaaResult)
    return result


def sampled_classes(
    raw: dict[str, Any], run: str, draws: int, seed: int
) -> dict[str, dict[str, float]]:
    """Class shares from the independent sampler's own draws: the same stream and order as
    ``smaa_sampling_oracle.rank_acceptability``, counting ``sorting_oracle.class_of`` instead."""
    rng = random.Random(seed)
    nodes = {n["id"]: n for n in raw["criteria"]}
    alts = [a["id"] for a in raw["alternatives"]]
    class_ids = [c["id"] for c in raw["sorting"]["classes"]]
    base = values_oracle._profile(raw, None, None)
    measured = {(p["alternative_id"], p["criterion_id"]): p["value"] for p in raw["performances"]}
    cells = raw["smaa"]["cells"] if run in ("performance", "combined") else []
    groups = raw["smaa"]["groups"] if run in ("preference", "combined") else []
    fixed = values_oracle.global_weights(raw, values_oracle.local_weights(raw, base))
    counts = {a: dict.fromkeys(class_ids, 0) for a in alts}
    for _ in range(draws):
        cell_values = dict(measured)
        for cell in cells:
            leaf = nodes[cell["criterion_id"]]
            key = (cell["alternative_id"], cell["criterion_id"])
            cell_values[key] = smaa_sampling_oracle._draw(
                rng, cell["distribution"], leaf["scale"].get("labels", [])
            )
        weights = fixed
        if groups:
            judgements = dict(base)
            for group in groups:
                for child, (lower, upper) in group["intervals"].items():
                    judgements[child] = rng.uniform(lower, upper)
            weights = values_oracle.global_weights(
                raw, values_oracle.local_weights(raw, judgements)
            )
        for alt in alts:
            value = math.fsum(
                weight
                * values_oracle.partial_value(
                    nodes[leaf]["value_function"], nodes[leaf]["scale"], cell_values[(alt, leaf)]
                )
                for leaf, weight in weights.items()
            )
            counts[alt][values_oracle.class_of(value, raw)] += 1
    return {a: {c: n / draws for c, n in row.items()} for a, row in counts.items()}


def within_four_standard_errors(mine: float, engine: float, draws: int) -> bool:
    pooled = (mine + engine) / 2
    bound = 4 * math.sqrt(max(pooled * (1 - pooled), 1e-4) * 2 / draws) + 0.002
    return abs(mine - engine) <= bound


def test_the_trade_study_states_every_section() -> None:
    project = project_of(TRADE)
    assert project.sorting and project.smaa and project.promethee and project.ahp
    assert project.requirements is not None
    assert project.analysis.method == "mavt"
    assert [p.id for p in project.weight_profiles] == ["default", "cost_led"]
    assert [s.id for s in project.scenarios] == ["diminishing_endurance"]
    assert [a.id for a in project.alternatives] == TRADE_ALTS
    assert len(project.tree().leaves()) == 7
    units = {n.id: n.scale.unit for n in project.criteria if n.scale and n.scale.is_numeric}
    assert units == TRADE_UNITS
    assert [c.id for c in project.sorting.classes] == ["shortlist", "reserve", "drop"]
    assert [c.lower_boundary for c in project.sorting.classes] == [0.65, 0.50, None]
    assert [(r.kind, r.criterion_id) for r in project.requirements] == [
        ("bound", "payload"),
        ("labels", "maturity"),
    ]
    judged = sum(len(g.judgements) for g in project.ahp.criteria) + sum(
        len(g.judgements) for g in project.ahp.alternatives
    )
    assert judged == 78 and len(project.promethee.criteria) == 7
    # SMAA-2 uses only what the independent sampler covers: uniform and categorical cells, rating
    # intervals, no shared draw, independent dependence.
    assert len(project.smaa.cells) == 12 and project.smaa.shared_draws == []
    assert {c.distribution.kind for c in project.smaa.cells} == {"uniform", "categorical"}
    assert [g.kind for g in project.smaa.groups] == ["rating_intervals"]
    assert project.smaa.dependence == "independent"


@pytest.mark.parametrize(("profile_id", "scenario_id"), TRADE_CONTEXTS)
def test_the_trade_mavt_values_equal_the_independent_oracle(
    profile_id: str, scenario_id: str | None
) -> None:
    project = project_of(TRADE)
    raw = project.model_dump(mode="json")
    values = values_oracle.overall_values(raw, scenario_id, profile_id)
    result = evaluate_with(project, "mavt", weight_profile_id=profile_id, scenario_id=scenario_id)
    assert isinstance(result, MavtResult)
    for row in result.ranking:
        assert row.value == pytest.approx(values[row.alternative_id], abs=1e-12)
        assert row.rank == 1 + sum(
            1 for v in values.values() if v > values[row.alternative_id] + 1e-12
        )


@pytest.mark.parametrize(("profile_id", "scenario_id"), TRADE_CONTEXTS)
def test_the_trade_classes_equal_the_independent_oracle(
    profile_id: str, scenario_id: str | None
) -> None:
    project = project_of(TRADE)
    raw = project.model_dump(mode="json")
    values = values_oracle.overall_values(raw, scenario_id, profile_id)
    result = evaluate_with(
        project, "mavt_sorting", weight_profile_id=profile_id, scenario_id=scenario_id
    )
    assert isinstance(result, MavtSortingResult)
    for a in result.assignments:
        assert a.class_id == values_oracle.class_of(values[a.alternative_id], raw)
        nearest = values_oracle.nearest_boundary(values[a.alternative_id], raw)
        assert nearest is not None and a.nearest_boundary_class_id == nearest[0]
        assert a.distance_to_nearest_boundary == pytest.approx(nearest[1], abs=1e-12)


@pytest.mark.parametrize(("profile_id", "scenario_id"), TRADE_CONTEXTS)
def test_the_trade_mavt_and_class_headline_facts(profile_id: str, scenario_id: str | None) -> None:
    project = project_of(TRADE)
    expected = TRADE_MAVT[(profile_id, scenario_id)]
    result = evaluate_with(
        project, "mavt_sorting", weight_profile_id=profile_id, scenario_id=scenario_id
    )
    assert [row.alternative_id for row in result.ranking] == expected["order"]
    for row in result.ranking:
        assert row.value == pytest.approx(expected["value"][row.alternative_id], abs=5e-5)
    assert {a.alternative_id: a.class_id for a in result.assignments} == expected["class"]


def test_one_concept_sits_close_to_a_class_boundary_and_a_scenario_moves_it() -> None:
    """The boundaries are illustrative and were chosen after the values were known: the Wheeled
    rover sits just below the Shortlist boundary, and the scenario lifts it across."""
    project = project_of(TRADE)
    base = evaluate_with(project, "mavt_sorting")
    scenario = evaluate_with(project, "mavt_sorting", scenario_id="diminishing_endurance")
    near = next(a for a in base.assignments if a.alternative_id == W)
    assert near.class_id == "reserve" and near.nearest_boundary_class_id == "shortlist"
    assert near.distance_to_nearest_boundary < 0.03
    assert next(a for a in scenario.assignments if a.alternative_id == W).class_id == "shortlist"


def test_the_trade_feasibility_statuses_equal_the_independent_oracle() -> None:
    project = project_of(TRADE)
    result = fs.check_feasibility(project)
    expected = feasibility_oracle.evaluate(project.model_dump(mode="json"))
    assert [a.alternative_id for a in result.alternatives] == TRADE_ALTS
    for a in result.alternatives:
        mine = [(c.status, reason_class(c.reason)) for c in a.checks]
        assert mine == expected[a.alternative_id]["checks"], a.alternative_id
        assert a.status == expected[a.alternative_id]["status"]


def test_the_trade_feasibility_headline_grid_and_the_exact_limit() -> None:
    project = project_of(TRADE)
    for a in fs.check_feasibility(project).alternatives:
        first, second, overall = TRADE_FEASIBILITY[a.alternative_id]
        assert [(c.status, reason_class(c.reason)) for c in a.checks] == [first, second]
        assert a.status == overall
    requirement = project.requirements[0]  # type: ignore[index]
    assert requirement.minimum == 2.0 and requirement.minimum_inclusive  # type: ignore[union-attr]
    payload = {
        p.alternative_id: p.value for p in project.performances if p.criterion_id == "payload"
    }
    assert [a for a, v in payload.items() if v == 2.0] == [T]


def test_feasibility_tests_the_entered_value_not_the_sampled_range() -> None:
    """The Tethered crawler's payload range spans its limit, yet its entered value meets it."""
    project = project_of(TRADE)
    cell = next(
        c
        for c in project.smaa.cells  # type: ignore[union-attr]
        if c.alternative_id == T and c.criterion_id == "payload"
    )
    assert cell.distribution.lower < 2.0 < cell.distribution.upper  # type: ignore[union-attr]
    status = {a.alternative_id: a.status for a in fs.check_feasibility(project).alternatives}
    assert status[T] == "pass"


def test_failed_concepts_stay_in_every_reading_and_requirements_change_nothing() -> None:
    project = project_of(TRADE)
    bare = ps.set_requirements(project, [])
    for method in ("mavt", "mavt_sorting", "promethee2", "ahp"):
        with_req = evaluate_with(project, method)
        without = evaluate_with(bare, method)
        # The result echoes the project's schema version, which removing requirements lowers.
        ignored = {"project_fingerprint", "schema_version"}
        assert with_req.model_dump(exclude=ignored) == without.model_dump(exclude=ignored), method
    assert {r.alternative_id for r in evaluate_with(project, "mavt").ranking} == set(TRADE_ALTS)
    assert {row.alternative_id for row in smaa(project, "combined").acceptability} == set(
        TRADE_ALTS
    )
    # Neither failing concept scores strongly: the Legged walker is last and the drone fourth.
    for ranked in (
        [f.alternative_id for f in evaluate_with(project, "promethee2").flows],
        [a.alternative_id for a in evaluate_with(project, "ahp").alternatives],
        [r.alternative_id for r in evaluate_with(project, "mavt").ranking],
    ):
        assert ranked[-2:] == [A, L]


def test_the_trade_promethee_numbers_equal_the_independent_oracle() -> None:
    project = project_of(TRADE)
    exact = promethee_oracle.flows(project.model_dump(mode="json"))
    result = evaluate_with(project, "promethee2")
    assert isinstance(result, PrometheeResult)
    for f in result.flows:
        a = f.alternative_id
        assert abs(f.positive_flow - float(exact["positive"][a])) <= TOL
        assert abs(f.negative_flow - float(exact["negative"][a])) <= TOL
        assert abs(f.net_flow - float(exact["net"][a])) <= TOL
        for leaf, value in f.criterion_flows.items():
            assert abs(value - float(exact["criterion"][leaf][a])) <= TOL
    for (a, b), value in exact["preference"].items():
        assert abs(result.preference_matrix[a][b] - float(value)) <= TOL
    assert {f.alternative_id: f.rank for f in result.flows} == promethee_oracle.ranks(exact["net"])
    for pair in result.partial_order:
        expected = promethee_oracle.relation(exact, pair.alternative_a, pair.alternative_b)
        assert expected == ("a" if pair.relation == "preferred" else pair.relation)


def test_the_trade_promethee_headline_flows_and_complete_order() -> None:
    result = evaluate_with(project_of(TRADE), "promethee2")
    assert [f.alternative_id for f in result.flows] == list(TRADE_PROMETHEE)
    for f in result.flows:
        positive, negative, net = TRADE_PROMETHEE[f.alternative_id]
        assert f.positive_flow == pytest.approx(positive, abs=5e-5)
        assert f.negative_flow == pytest.approx(negative, abs=5e-5)
        assert f.net_flow == pytest.approx(net, abs=5e-5)
    # Every pair is ordered, none incomparable, and MAVT (Performance-led) disagrees on no pair.
    assert {p.relation for p in result.partial_order} == {"preferred"}
    order = list(TRADE_PROMETHEE)
    for p in result.partial_order:
        assert order.index(p.alternative_a) < order.index(p.alternative_b)
    assert result.explanation.available and result.explanation.pairs == []


@pytest.mark.parametrize("synthesis", ["distributive", "ideal"])
def test_the_trade_ahp_numbers_equal_the_independent_oracle(synthesis: str) -> None:
    check_ahp_against_the_oracle(project_of(TRADE), synthesis)


def test_every_trade_matrix_equals_the_oracle_on_consistency_and_triads() -> None:
    check_every_matrix_against_the_oracle(project_of(TRADE), 4 + 7)


def test_the_trade_ahp_headline_priorities_and_no_flagged_matrix() -> None:
    result = ahp(project_of(TRADE), "distributive")
    assert [a.alternative_id for a in result.alternatives] == list(TRADE_AHP)
    for a in result.alternatives:
        assert a.priority == pytest.approx(TRADE_AHP[a.alternative_id], abs=5e-5)
    for leaf, value in TRADE_AHP_LEAVES.items():
        assert result.global_priorities[leaf] == pytest.approx(value, abs=5e-5)
    assert [m for m in result.matrices if m.inconsistent] == []
    assert max(m.consistency_ratio for m in result.matrices) == pytest.approx(0.0516, abs=5e-4)
    assert [a.alternative_id for a in ahp(project_of(TRADE), "ideal").alternatives] == list(
        TRADE_AHP
    )


@pytest.mark.parametrize("run", ["performance", "preference", "combined"])
def test_sampled_ranks_agree_with_the_independent_sampler(run: str) -> None:
    """A bounded statistical check: two independent estimates of each rank share agree within four
    standard errors of their difference (plus 0.002 for rounding of ties)."""
    project = project_of(TRADE)
    raw = project.model_dump(mode="json")
    independent = smaa_sampling_oracle.rank_acceptability(raw, run, EXPLORATION_DRAWS, seed=7)
    result = smaa(project, run)
    assert result.samples == EXPLORATION_DRAWS and result.evaluation == "sampled"
    for row in result.acceptability:
        for rank, estimate in enumerate(row.ranks):
            assert within_four_standard_errors(
                independent[row.alternative_id][rank], estimate.frequency, EXPLORATION_DRAWS
            ), (run, row.alternative_id, rank)


@pytest.mark.parametrize("run", ["performance", "preference", "combined"])
def test_sampled_class_shares_agree_with_the_independent_sampler(run: str) -> None:
    project = project_of(TRADE)
    independent = sampled_classes(project.model_dump(mode="json"), run, EXPLORATION_DRAWS, seed=7)
    for row in smaa(project, run).acceptability:
        for class_id, estimate in row.classes.items():
            assert within_four_standard_errors(
                independent[row.alternative_id][class_id], estimate.frequency, EXPLORATION_DRAWS
            ), (run, row.alternative_id, class_id)


@pytest.mark.parametrize("run", ["performance", "preference", "combined"])
def test_the_trade_smaa_headline_shares(run: str) -> None:
    result = smaa(project_of(TRADE), run)
    assert result.leader_id == K and result.seed == 0 and result.dependence == "independent"
    for row in result.acceptability:
        ranks, classes = TRADE_SMAA[run][row.alternative_id]
        assert [e.frequency for e in row.ranks] == pytest.approx(ranks, abs=1e-4)
        assert {k: e.frequency for k, e in row.classes.items()} == pytest.approx(classes, abs=1e-4)


def test_a_concept_near_a_boundary_spreads_across_classes_under_smaa() -> None:
    """The design intent, found: three concepts have class shares above 5% in two classes."""
    result = smaa(project_of(TRADE), "combined")
    spread = {
        row.alternative_id
        for row in result.acceptability
        if sum(1 for e in row.classes.values() if e.frequency > 0.05) >= 2
    }
    assert spread == {W, T, A}
    by_id = {row.alternative_id: row for row in result.acceptability}
    assert 0.2 < by_id[W].classes["shortlist"].frequency < 0.8
    assert 0.2 < by_id[T].classes["shortlist"].frequency < 0.8


@pytest.mark.parametrize(
    ("context", "update"),
    [
        ("saved", {}),
        ("cost_led", {"weight_profile_id": "cost_led"}),
        ("diminishing_endurance", {"scenario_id": "diminishing_endurance"}),
    ],
)
def test_the_five_methods_name_these_leaders(context: str, update: dict[str, str]) -> None:
    project = project_of(TRADE)
    comparison = cs.compare_methods(
        project, project.analysis.model_copy(update={"parameters": {}, **update})
    )
    leaders = {c.method: c.leaders for c in comparison.columns if c.status == "ok"}
    assert leaders == {m: [leader] for m, leader in TRADE_LEADERS[context].items()}
    assert comparison.agreement.leaders_agree == (context != "cost_led")
