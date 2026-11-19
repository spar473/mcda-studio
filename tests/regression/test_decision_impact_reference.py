"""Decision impact for qualitative and ordinal cells, against an independent brute-force oracle.

The oracle (``tests/regression/decision_impact_oracle.py``) never imports the application: it
rewrites one cell at a time in the raw project JSON and recomputes every value, rank, leader and
class from scratch. The service must agree to 1e-12 on values and exactly on everything else, on
the real venture study (both profiles and the scenario), the other bundled examples that apply,
and generated trees full of ties.
"""

import json
import random
from pathlib import Path

import decision_impact_oracle as oracle
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mcda_studio.domain.criteria import QualitativeValueFunction
from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.external_proposals import (
    ExternalProposals,
    LocalModelCard,
    ProposalReview,
    ProposalReviewDetails,
)
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.services import decision_impact_service as impact
from mcda_studio.services import evidence_service, proposal_import_service, proposal_service
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
STUDY = EXAMPLES / "nz_venture_screening"
repo = JsonProjectRepository()


def raw(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def compare(project, project_json, configuration=None):
    cfg = configuration or AnalysisConfiguration(method="mavt")
    result = impact.decision_impact(project, cfg)
    assert result.status == "available"
    expected = oracle.impacts(project_json, cfg.scenario_id, cfg.weight_profile_id)
    got = {(c.alternative_id, c.criterion_id): c for c in result.cells}
    assert set(got) == set(expected)
    for cell, truth in expected.items():
        mine = got[cell]
        assert [e.label for e in mine.effects] == list(truth["effects"])
        for effect in mine.effects:
            want = truth["effects"][effect.label]
            assert abs(effect.value - want["value"]) <= 1e-12
            assert effect.target_rank == want["target_rank"]
            assert effect.target_class_id == want["target_class"]
            assert effect.leaders == want["leaders"]
            assert sorted(effect.changes) == sorted(want["changes"])
            assert effect.levels == want["levels"]
        assert mine.smallest_changes == truth["smallest"]
        assert mine.can_change_decision == truth["decisive"]
        assert mine.tier == (
            "leader_or_class" if truth["decisive"] else ("rank" if truth["rank"] else "none")
        )
    return result


@pytest.mark.parametrize(
    "configuration",
    [
        AnalysisConfiguration(method="mavt"),
        AnalysisConfiguration(method="mavt", weight_profile_id="commercial_traction"),
        AnalysisConfiguration(method="mavt", scenario_id="linear_market_size"),
    ],
)
def test_the_venture_study_agrees_with_the_brute_force_oracle(configuration):
    project = repo.load(STUDY / "project.json")
    result = compare(project, raw(STUDY / "project.json"), configuration)
    assert result.analysed_cells == 8 * 14  # the 14 weighted rubric leaves; mandate leaves carry 0
    assert {c.criterion_id for c in result.cells}.isdisjoint({"hq_country", "stage", "sector"})
    assert result.baseline_leaders and result.baseline_classes


def test_the_qualification_example_agrees_and_local_anchor_examples_are_outside_the_oracle():
    """supplier_qualification has fixed anchors; the other bundled examples use local anchors, which
    the plain-Python oracle (like the sorting oracle it builds on) does not cover."""
    path = EXAMPLES / "supplier_qualification" / "project.json"
    project, project_json = repo.load(path), raw(path)
    result = compare(project, project_json)
    assert result.analysed_cells > 0
    for name in ("supplier_selection", "infrastructure_procurement", "nz_deeptech_vc"):
        other = raw(EXAMPLES / name / "project.json")
        with pytest.raises((ValueError, KeyError)):
            oracle.impacts(other)
        # the service still analyses them, with the engine's own anchors
        assert impact.decision_impact(repo.load(EXAMPLES / name / "project.json")).status in {
            "available",
            "unavailable",
        }


def test_cells_are_ordered_by_decision_then_rank_then_nothing_and_otherwise_by_project_order():
    project = repo.load(STUDY / "project.json")
    result = impact.decision_impact(project)
    order = {"leader_or_class": 0, "rank": 1, "none": 2}
    leaves = project.tree().leaves()
    alternatives = [a.id for a in project.alternatives]
    keys = [
        (order[c.tier], leaves.index(c.criterion_id), alternatives.index(c.alternative_id))
        for c in result.cells
    ]
    assert keys == sorted(keys)
    assert {c.tier for c in result.cells} == set(order)


def test_numeric_unweighted_and_missing_cells_are_not_analysed_and_looking_changes_nothing():
    project = repo.load(STUDY / "project.json")
    before = project.fingerprint()
    result = impact.decision_impact(project)
    assert project.fingerprint() == before
    assert not any(c.criterion_id in {"market_size", "market_growth"} for c in result.cells)
    broken = ps.clear_performance(project, "upstock", "board_advisors")
    unavailable = impact.decision_impact(broken)
    assert unavailable.status == "unavailable" and "missing" in unavailable.reason
    assert unavailable.cells == []


def test_no_classes_means_no_class_effects_and_a_leader_change_is_still_found():
    project = ps.clear_sorting_model(repo.load(STUDY / "project.json"))
    result = impact.decision_impact(project)
    assert result.baseline_classes == {}
    assert all(c.target_class_labels == [] for c in result.cells)
    assert all(e.target_class_id is None for c in result.cells for e in c.effects)
    compare(project, json.loads(json.dumps(raw(STUDY / "project.json"))) | {"sorting": None})


def test_the_label_lists_and_smallest_change_follow_their_definitions():
    result = impact.decision_impact(repo.load(STUDY / "project.json"))
    for cell in result.cells:
        names = [e.label for e in cell.effects]
        assert cell.current_label not in names and len(names) >= 1
        for key, change in (
            ("target_rank_labels", "target_rank"),
            ("target_class_labels", "target_class"),
            ("leader_labels", "leader"),
        ):
            assert getattr(cell, key) == [e.label for e in cell.effects if change in e.changes]
        assert set(cell.any_rank_labels) == {
            e.label for e in cell.effects if {"target_rank", "other_rank"} & set(e.changes)
        }
        moving = [e for e in cell.effects if e.changes]
        if moving:
            nearest = min(abs(e.levels) for e in moving)
            assert cell.smallest_changes == [e.label for e in moving if abs(e.levels) == nearest]
        else:
            assert cell.smallest_changes == []
        assert cell.can_change_decision == bool(cell.leader_labels or cell.target_class_labels)


# --- reasons --------------------------------------------------------------------------------------


def test_dossier_reasons_are_judgement_disputed_outdated_and_missing_and_unreasoned_cells_stay():
    project = repo.load(STUDY / "project.json")
    dossier = EvidenceDossier.model_validate_json((STUDY / "evidence.json").read_text())
    plain = impact.decision_impact(project)
    result = impact.decision_impact(project, dossier=dossier)
    assert [(c.alternative_id, c.criterion_id) for c in result.cells] == [
        (c.alternative_id, c.criterion_id) for c in plain.cells
    ]  # reasons never change the analysis or its order
    assert all(c.reasons == [] for c in plain.cells)
    kinds = {r for c in result.cells for r in c.reasons}
    assert {"judgement_only", "outdated"} <= kinds
    judged = next(c for c in result.cells if "judgement_only" in c.reasons)
    claims = [
        x
        for x in dossier.claims
        if x.alternative_id == judged.alternative_id
        and x.criterion_id == judged.criterion_id
        and x.review
    ]
    assert claims and all(x.source.description.startswith("Judgement") for x in claims)
    assert any(c.reasons == [] for c in result.cells)  # analysed and marked "no open reason"
    # a second, unreviewed claim on a cell makes it disputed
    extra = dossier.claims[0].model_copy(
        update={
            "id": "extra_unreviewed",
            "alternative_id": "hectre",
            "criterion_id": "board_advisors",
            "value": project.tree().node("board_advisors").scale.labels[0],
            "review": None,
        }
    )
    again = impact.decision_impact(
        project, dossier=dossier.model_copy(update={"claims": [*dossier.claims, extra]})
    )
    cell = next(
        c for c in again.cells if (c.alternative_id, c.criterion_id) == ("hectre", "board_advisors")
    )
    assert "disputed" in cell.reasons


def test_a_dossier_for_another_revision_gives_no_reasons():
    project = repo.load(STUDY / "project.json")
    dossier = EvidenceDossier.model_validate_json((STUDY / "evidence.json").read_text())
    stale = dossier.model_copy(update={"project_fingerprint": "0" * 64})
    assert all(c.reasons == [] for c in impact.decision_impact(project, dossier=stale).cells)


def categorical_workspace(project) -> ExternalProposals:
    """Two tools on one cell (different labels), one pending cell and one rejected cell."""
    card = {
        "version": 1,
        "purpose": "Propose labels",
        "limitations": "Invented",
        "model_version": "1",
        "details": {},
    }
    digest = evidence_service._digest(LocalModelCard.model_validate(card).model_dump(mode="json"))
    source = {
        "name": "S",
        "reference": "local:s",
        "location": "",
        "date": "2026-11-01",
        "description": "Invented",
        "classification": "unknown",
    }

    def proposal(pid, tool, alt, leaf, value):
        return {
            "proposal_version": 1,
            "id": pid,
            "subject": {"alternative_id": alt, "criterion_id": leaf},
            "payload": {"kind": "categorical_cell", "value": value, "unit": None},
            "tool_id": tool,
            "tool_version": "1",
            "model_card_id": "card",
            "model_card_digest": digest,
            "run_at": "2026-11-01T00:00:00+00:00",
            "confidence": None,
            "source_ids": ["s"],
            "replaces_proposal_id": None,
        }

    def first(leaf):
        return project.tree().node(leaf).scale.labels[0]

    labels = project.tree().node("board_advisors").scale.labels
    raw_intake = {
        "schema_version": 1,
        "project_fingerprint": project.fingerprint(),
        "sources": {"s": source},
        "model_cards": {"card": card},
        "proposals": [
            proposal("a1", "tool_a", "hectre", "board_advisors", labels[0]),
            proposal("b1", "tool_b", "hectre", "board_advisors", labels[1]),
            proposal("p1", "tool_a", "wych", "team_completeness", first("team_completeness")),
            proposal("r1", "tool_a", "hnry", "track_record", first("track_record")),
        ],
        "human_dossier": None,
    }
    workspace = proposal_import_service.parse(project, json.dumps(raw_intake))
    event = ProposalReview(
        proposal_id="r1",
        review=ProposalReviewDetails(
            status="rejected",
            reviewer="R",
            reviewed_at="2026-11-02T00:00:00+00:00",
            note="no",
            primary_source_id="s",
        ),
    )
    current = proposal_service.inspect(project, workspace)
    reviewed = proposal_service.review(
        project, workspace, [event], current.review_digest, workspace.digest, False, None
    )
    return reviewed.workspace


def test_proposal_reasons_pending_rejected_and_tool_disagreement():
    project = repo.load(STUDY / "project.json")
    workspace = categorical_workspace(project)
    result = impact.decision_impact(project, proposals=workspace)
    by_cell = {(c.alternative_id, c.criterion_id): c.reasons for c in result.cells}
    assert "tool_human_disagreement" in by_cell[("hectre", "board_advisors")]
    assert "proposal_pending" in by_cell[("hectre", "board_advisors")]
    assert by_cell[("wych", "team_completeness")] == ["proposal_pending"]
    assert by_cell[("hnry", "track_record")] == ["proposal_rejected"]
    assert by_cell[("upstock", "problem_severity")] == []
    plain = impact.decision_impact(project)
    assert [c.model_dump(exclude={"reasons"}) for c in plain.cells] == [
        c.model_dump(exclude={"reasons"}) for c in result.cells
    ]


# --- generated trees with ties --------------------------------------------------------------------


def random_project(rng: random.Random, with_classes: bool):
    p = ps.new_project("Generated")
    n_alt = rng.randint(2, 5)
    for i in range(n_alt):
        p = ps.add_alternative(p, f"alt {i}", alt_id=f"a{i}")
    groups = rng.randint(1, 3)
    leaves: list[str] = []
    for g in range(groups):
        group = f"g{g}"
        parent = None
        if groups > 1:
            p = ps.add_criterion(p, f"group {g}", crit_id=group)
            parent = group
        for k in range(rng.randint(1, 3)):
            leaf = f"{group}l{k}"
            levels = rng.randint(2, 4)
            labels = [f"L{n}" for n in range(levels)]
            scale_type = ScaleType.ORDINAL if rng.random() < 0.7 else ScaleType.CATEGORICAL
            middle = [rng.choice([0.0, 0.25, 0.5, 0.75, 1.0]) for _ in labels[1:-1]]
            if scale_type is ScaleType.ORDINAL:
                middle.sort()  # ordinal values never decrease; the ends are always 0 and 1
            mapping = dict(zip(labels, [0.0, *middle, 1.0], strict=True))
            p = ps.add_criterion(
                p,
                f"leaf {leaf}",
                parent,
                leaf,
                scale=Scale(type=scale_type, labels=labels),
                value_function=QualitativeValueFunction(mapping=mapping),
            )
            leaves.append(leaf)
    for i in range(n_alt):
        for leaf in leaves:
            labels = p.tree().node(leaf).scale.labels
            p = ps.set_performance(p, f"a{i}", leaf, rng.choice(labels))
    for node in p.criteria:
        siblings = [n for n in p.criteria if n.parent_id == node.parent_id]
        if len(siblings) > 1:
            p = ps.set_judgement(
                p, node.id, float(rng.choice([0, 10, 20, 30, 50])) if rng.random() < 0.8 else 10.0
            )
    if with_classes:
        cuts = sorted(
            {rng.choice([0.25, 0.375, 0.5, 0.625, 0.75]) for _ in range(rng.randint(1, 2))},
            reverse=True,
        )
        names = [f"C{n}" for n in range(len(cuts) + 1)]
        p = ps.set_sorting_model(p, ps_sorting(names, cuts))
    return p


def ps_sorting(names, cuts):
    from mcda_studio.domain.sorting import SortingModel

    return SortingModel(classes=ps.sorting_classes([*zip(names, [*cuts, None], strict=True)]))


def check_against_oracle(project) -> impact.DecisionImpact:
    result = impact.decision_impact(project, AnalysisConfiguration(method="mavt"))
    if result.status != "available":
        return result  # a generated model that does not validate is not the oracle's business
    expected = oracle.impacts(json.loads(project.model_dump_json()))
    got = {(c.alternative_id, c.criterion_id): c for c in result.cells}
    assert set(got) == set(expected)
    for cell, truth in expected.items():
        assert [e.label for e in got[cell].effects] == list(truth["effects"])
        for effect in got[cell].effects:
            want = truth["effects"][effect.label]
            assert abs(effect.value - want["value"]) <= 1e-12
            assert effect.target_rank == want["target_rank"]
            assert effect.target_class_id == want["target_class"]
            assert effect.leaders == want["leaders"]
            assert sorted(effect.changes) == sorted(want["changes"])
            assert effect.levels == want["levels"]
        assert got[cell].smallest_changes == truth["smallest"]
        assert got[cell].can_change_decision == truth["decisive"]
    return result


@settings(max_examples=60, deadline=None)
@given(st.integers(0, 2**31), st.booleans())
def test_generated_trees_with_ties_agree_with_the_oracle(seed, with_classes):
    check_against_oracle(random_project(random.Random(seed), with_classes))


def test_the_generated_corpus_really_contains_ties_leader_changes_and_class_changes():
    seen = {"tie": 0, "leader": 0, "target_class": 0, "target_rank": 0, "other_rank": 0}
    for seed in range(80):
        result = check_against_oracle(random_project(random.Random(seed), seed % 2 == 0))
        for cell in result.cells:
            for effect in cell.effects:
                seen["tie"] += len(effect.leaders) > 1
                for change in effect.changes:
                    seen[change] += 1
    assert all(count > 0 for count in seen.values()), seen


# --- exact boundaries and mixed claims ---------------------------------------------------------


def boundary_project():
    """One leaf mapped 0, 0.5, 1 with weight 1, and a class boundary at exactly 0.5."""
    from mcda_studio.domain.sorting import SortingModel

    p = ps.new_project("Boundary")
    for alt in ("a", "b", "c"):
        p = ps.add_alternative(p, alt.upper(), alt_id=alt)
    p = ps.add_criterion(
        p,
        "Level",
        crit_id="level",
        scale=Scale(type=ScaleType.ORDINAL, labels=["L0", "L1", "L2"]),
        value_function=QualitativeValueFunction(mapping={"L0": 0.0, "L1": 0.5, "L2": 1.0}),
    )
    for alt, label in (("a", "L2"), ("b", "L0"), ("c", "L1")):
        p = ps.set_performance(p, alt, "level", label)
    return ps.set_sorting_model(
        p, SortingModel(classes=ps.sorting_classes([("High", 0.5), ("Low", None)]))
    )


def test_a_value_exactly_on_a_class_boundary_takes_the_higher_class():
    project = boundary_project()
    result = impact.decision_impact(project)
    cell = next(c for c in result.cells if (c.alternative_id, c.criterion_id) == ("b", "level"))
    middle = next(e for e in cell.effects if e.label == "L1")
    assert middle.value == 0.5 and middle.target_class_id == "high"  # the higher class on the line
    # b is Low at L0 and High at L1 (exactly 0.5): the class changes there, and ties c at rank
    assert "target_class" in middle.changes and "target_rank" in middle.changes
    assert middle.leaders == ["a"]
    compare(project, json.loads(project.model_dump_json()))


def test_a_rejected_claim_leaves_the_cell_without_support():
    project = repo.load(STUDY / "project.json")
    dossier = EvidenceDossier.model_validate_json((STUDY / "evidence.json").read_text())
    plain = impact.decision_impact(project, dossier=dossier)
    judged = next(c for c in plain.cells if "judgement_only" in c.reasons)
    cell_ids = (judged.alternative_id, judged.criterion_id)
    claims = []
    for claim in dossier.claims:
        if (claim.alternative_id, claim.criterion_id) == cell_ids and claim.review:
            claim = claim.model_copy(
                update={"review": claim.review.model_copy(update={"status": "rejected"})}
            )
        claims.append(claim)
    result = impact.decision_impact(project, dossier=dossier.model_copy(update={"claims": claims}))
    cell = next(c for c in result.cells if (c.alternative_id, c.criterion_id) == cell_ids)
    assert "missing" in cell.reasons and "judgement_only" not in cell.reasons


def test_a_dossier_with_two_accepted_claims_on_one_cell_gives_no_reasons():
    project = repo.load(STUDY / "project.json")
    dossier = EvidenceDossier.model_validate_json((STUDY / "evidence.json").read_text())
    first = next(c for c in impact.decision_impact(project, dossier=dossier).cells if c.reasons)
    template = next(
        x
        for x in dossier.claims
        if (x.alternative_id, x.criterion_id) == (first.alternative_id, first.criterion_id)
        and x.review
    )
    twin = template.model_copy(update={"id": "second_accepted_claim"})
    broken = dossier.model_copy(update={"claims": [*dossier.claims, twin]})
    assert all(c.reasons == [] for c in impact.decision_impact(project, dossier=broken).cells)
