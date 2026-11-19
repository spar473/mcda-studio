"""AHP: validation, small and hand-derived matrices, synthesis, the triad hint, convergence,
schema version 5 and the section edits (design note ``docs/design/ahp.md``)."""

import json

import pytest

from mcda_studio.domain.errors import ConvergenceError, ProjectLoadError, ValidationFailed
from mcda_studio.domain.pairwise import (
    AhpModel,
    AlternativeJudgements,
    CriteriaJudgements,
    PairwiseJudgement,
)
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import AhpResult
from mcda_studio.methods.ahp import matrix
from mcda_studio.methods.ahp.matrix import analyse
from mcda_studio.methods.base import validate_analysis
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text

from builders import tiny_project

repo = JsonProjectRepository()


def j(row: str, column: str, value: float) -> PairwiseJudgement:
    return PairwiseJudgement(row=row, column=column, value=value)


def config(project: Project, **parameters: object):  # type: ignore[no-untyped-def]
    return project.analysis.model_copy(update={"method": "ahp", "parameters": parameters})


def ahp(project: Project, synthesis: str = "distributive") -> AhpResult:
    result = svc.evaluate_project(project, config(project, synthesis=synthesis))
    assert isinstance(result, AhpResult)
    return result


def codes(project: Project, **parameters: object) -> list[str]:
    return [i.code for i in validate_analysis(project, config(project, **parameters)).issues]


def flat(alternatives: list[str], leaves: dict[str, list[PairwiseJudgement]], top=None) -> Project:  # type: ignore[no-untyped-def]
    """Flat leaves with no scales, values or measurements: AHP needs none of them."""
    p = ps.new_project("Flat").model_copy(update={"id": "flat"})
    for alt in alternatives:
        p = ps.add_alternative(p, alt.title(), alt_id=alt)
    for leaf in leaves:
        p = ps.add_criterion(p, leaf.title(), crit_id=leaf)
    model = AhpModel(
        criteria=[CriteriaJudgements(parent_id=None, judgements=top)] if top is not None else [],
        alternatives=[
            AlternativeJudgements(criterion_id=leaf, judgements=js) for leaf, js in leaves.items()
        ],
    )
    return ps.set_ahp_model(p, model)


# ---- matrices of one, two and three items -----------------------------------------------------
def test_one_and_two_items_are_defined_without_iteration() -> None:
    one = analyse(["a"], [])
    assert (one.priorities, one.lambda_max, one.consistency_index, one.consistency_ratio) == (
        [1.0],
        1.0,
        0.0,
        0.0,
    )
    two = analyse(["a", "b"], [j("b", "a", 3)])
    assert two.priorities == [0.25, 0.75] and two.iterations == 0
    assert (two.lambda_max, two.consistency_index, two.consistency_ratio) == (2.0, 0.0, 0.0)
    assert two.random_index == 0.0 and two.triad is None and not two.inconsistent


def test_a_consistent_matrix_has_exact_priorities_and_no_inconsistency() -> None:
    a = analyse(["a", "b", "c"], [j("a", "b", 2), j("a", "c", 4), j("b", "c", 2)])
    assert a.priorities == pytest.approx([4 / 7, 2 / 7, 1 / 7], abs=1e-15)
    assert a.consistency_index <= 1e-15 and a.triad is not None and a.triad.index <= 1e-15


def test_the_most_inconsistent_triad_names_the_planted_judgement() -> None:
    # Consistent from weights 8:4:2:1, except d over a, which should be 1/8 and is stated as 4.
    items = ["a", "b", "c", "d"]
    js = [j("a", "b", 2), j("a", "c", 4), j("d", "a", 4), j("b", "c", 2), j("b", "d", 4)]
    js.append(j("c", "d", 2))
    a = analyse(items, js)
    assert a.triad is not None and a.triad.items == ("a", "b", "d")
    assert a.triad.judgements == (2.0, 4.0, 0.25)  # M[a][b], M[b][d], M[a][d]
    assert a.triad.consistent_value == 8.0  # a over d should be 2 x 4
    assert a.triad.index == pytest.approx(1 - 0.25 / 8)  # min(|1 - 1/32|, |1 - 32|)
    assert a.inconsistent


def test_the_warning_is_above_the_threshold_not_at_it(monkeypatch: pytest.MonkeyPatch) -> None:
    items = ["a", "b", "c"]
    js = [j("a", "b", 3), j("a", "c", 5), j("b", "c", 4)]
    cr = analyse(items, js).consistency_ratio
    monkeypatch.setattr(matrix, "CR_THRESHOLD", cr)
    assert not analyse(items, js).inconsistent
    monkeypatch.setattr(matrix, "CR_THRESHOLD", cr - 1e-9)
    assert analyse(items, js).inconsistent


def test_non_convergence_is_an_error_never_a_partial_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(matrix, "MAX_ITERATIONS", 2)
    with pytest.raises(ConvergenceError, match="did not converge within 2 iterations"):
        analyse(["a", "b", "c"], [j("a", "b", 3), j("a", "c", 5), j("b", "c", 4)])


# ---- hierarchy and synthesis -----------------------------------------------------------------
def test_global_priorities_multiply_down_the_tree() -> None:
    p = ps.new_project("Tree").model_copy(update={"id": "tree"})
    for alt in ("x", "y"):
        p = ps.add_alternative(p, alt.upper(), alt_id=alt)
    for crit, parent in (("cost", None), ("risk", None), ("price", "cost"), ("fees", "cost")):
        p = ps.add_criterion(p, crit.title(), crit_id=crit, parent_id=parent)
    p = ps.add_criterion(p, "Only", crit_id="only", parent_id="risk")
    model = AhpModel(
        criteria=[
            CriteriaJudgements(parent_id=None, judgements=[j("cost", "risk", 3)]),
            CriteriaJudgements(parent_id="cost", judgements=[j("price", "fees", 4)]),
        ],
        alternatives=[
            AlternativeJudgements(criterion_id=leaf, judgements=[j("x", "y", v)])
            for leaf, v in (("price", 1), ("fees", 2), ("only", 3))
        ],
    )
    result = ahp(ps.set_ahp_model(p, model))
    assert result.local_priorities == pytest.approx(
        {"cost": 0.75, "risk": 0.25, "price": 0.8, "fees": 0.2, "only": 1.0}
    )
    assert result.global_priorities == pytest.approx({"price": 0.6, "fees": 0.15, "only": 0.25})
    assert [m.group_id for m in result.matrices] == [None, "cost", "price", "fees", "only"]
    x = next(a for a in result.alternatives if a.alternative_id == "x")
    assert x.priority == pytest.approx(0.6 * 0.5 + 0.15 * 2 / 3 + 0.25 * 0.75)


def copy_case(with_copy: bool) -> Project:
    """Three equally weighted leaves; d, when present, is a copy of b on every leaf."""
    alternatives = ["a", "b", "c", *(["d"] if with_copy else [])]
    weights = {"one": (1, 9, 1), "two": (9, 1, 1), "three": (8, 1, 9)}

    def leaf(w: tuple[int, int, int]) -> list[PairwiseJudgement]:
        scores = dict(zip("abc", w, strict=True)) | ({"d": w[1]} if with_copy else {})
        out = []
        for i, a in enumerate(alternatives):
            for b in alternatives[i + 1 :]:
                hi, lo = (a, b) if scores[a] >= scores[b] else (b, a)
                out.append(j(hi, lo, scores[hi] / scores[lo]))
        return out

    top = [j("one", "two", 1), j("one", "three", 1), j("two", "three", 1)]
    return flat(alternatives, {name: leaf(w) for name, w in weights.items()}, top)


def test_a_copy_reverses_two_alternatives_under_distributive_synthesis_only() -> None:
    def order(result: AhpResult) -> list[str]:
        return [a.alternative_id for a in result.alternatives if a.alternative_id != "d"]

    assert order(ahp(copy_case(False))) == ["a", "b", "c"]
    assert order(ahp(copy_case(True))) == ["a", "c", "b"]  # d dilutes b's leaf
    before, after = ahp(copy_case(False), "ideal"), ahp(copy_case(True), "ideal")
    assert order(after) == order(before)
    scores = {a.alternative_id: a.ideal_score for a in before.alternatives}
    assert {
        a.alternative_id: a.ideal_score for a in after.alternatives if a.alternative_id != "d"
    } == (pytest.approx(scores))


def test_ideal_synthesis_divides_by_the_best_and_normalises() -> None:
    result = ahp(flat(["a", "b"], {"one": [j("a", "b", 3)], "two": [j("b", "a", 1)]},
                      [j("one", "two", 1)]), "ideal")  # fmt: skip
    a, b = (next(x for x in result.alternatives if x.alternative_id == k) for k in "ab")
    assert a.ideal_score == pytest.approx(0.5 * 1 + 0.5 * 1)
    assert b.ideal_score == pytest.approx(0.5 * (1 / 3) + 0.5 * 1)
    assert a.priority + b.priority == pytest.approx(1.0)
    assert result.synthesis == "ideal" and result.random_index_table == "saaty-tran-2007"


def test_the_result_names_no_profile_or_scenario_and_carries_the_label() -> None:
    result = ahp(flat(["a", "b"], {"one": [j("a", "b", 2)]}))
    assert result.weight_profile_id is None and result.scenario_id is None
    assert result.label.startswith("AHP priorities under these pairwise judgements")
    assert [(r.alternative_id, r.value) for r in result.ranking] == [
        (a.alternative_id, a.priority) for a in result.alternatives
    ]


def test_mavt_inputs_never_change_ahp() -> None:
    project = ps.set_ahp_model(
        tiny_project(),
        AhpModel(
            criteria=[CriteriaJudgements(parent_id=None, judgements=[j("quality", "cost", 2)])],
            alternatives=[
                AlternativeJudgements(criterion_id="cost", judgements=[j("a", "b", 3)]),
                AlternativeJudgements(criterion_id="quality", judgements=[j("b", "a", 5)]),
            ],
        ),
    )
    before = ahp(project)
    changed = ps.set_judgement(project, "quality", 1.0)
    changed = ps.set_performance(changed, "a", "cost", 99.0)
    after = ahp(changed)
    assert after.alternatives == before.alternatives and after.matrices == before.matrices
    assert codes(project.model_copy(update={"weight_profiles": []})) == []


# ---- validation -------------------------------------------------------------------------------
def base() -> Project:
    return flat(["a", "b", "c"], {"one": [j("a", "b", 2), j("a", "c", 4), j("b", "c", 2)]})


def with_leaf(judgements: list[PairwiseJudgement]) -> Project:
    project = base()
    assert project.ahp is not None
    model = project.ahp.model_copy(deep=True)
    model.alternatives[0].judgements = judgements
    return ps.set_ahp_model(project, model)


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda p: ps.clear_ahp_model(p), "AHP_NOT_STATED"),
        (
            lambda p: ps.remove_alternative(ps.remove_alternative(p, "b"), "c"),
            "AHP_TOO_FEW_ALTERNATIVES",
        ),
        (lambda p: ps.add_criterion(p, "Two", crit_id="two"), "AHP_JUDGEMENT_MISSING"),
        (lambda p: ps.add_alternative(p, "D", alt_id="d"), "AHP_JUDGEMENT_MISSING"),
        (lambda p: with_leaf([j("a", "b", 2), j("a", "c", 4), j("b", "z", 2)]), "UNKNOWN_AHP_ITEM"),
        (
            lambda p: with_leaf([j("a", "a", 1), j("a", "b", 2), j("a", "c", 4), j("b", "c", 2)]),
            "SELF_JUDGEMENT",
        ),
        (
            lambda p: with_leaf([j("a", "b", 2), j("b", "a", 2), j("a", "c", 4), j("b", "c", 2)]),
            "DUPLICATE_JUDGEMENT",
        ),
        (
            lambda p: with_leaf([j("a", "b", 0.5), j("a", "c", 4), j("b", "c", 2)]),
            "INVALID_JUDGEMENT",
        ),
        (
            lambda p: with_leaf([j("a", "b", 10), j("a", "c", 4), j("b", "c", 2)]),
            "INVALID_JUDGEMENT",
        ),
    ],
)
def test_every_error_code(change, code: str) -> None:  # type: ignore[no-untyped-def]
    project = change(base())
    assert code in codes(project)
    with pytest.raises(ValidationFailed):
        ahp(project)


def test_unknown_and_duplicate_groups() -> None:
    project = base()
    assert project.ahp is not None
    model = project.ahp.model_copy(deep=True)
    model.criteria.append(CriteriaJudgements(parent_id="one"))  # a leaf has no children to judge
    model.alternatives.append(AlternativeJudgements(criterion_id="nope"))
    model.alternatives.append(model.alternatives[0].model_copy(deep=True))
    found = codes(ps.set_ahp_model(project, model))
    assert found.count("UNKNOWN_AHP_GROUP") == 2 and "DUPLICATE_AHP_GROUP" in found


def test_too_many_items_for_the_random_index_table() -> None:
    alternatives = [f"x{k:02d}" for k in range(16)]
    judgements = [j(a, b, 1) for i, a in enumerate(alternatives) for b in alternatives[i + 1 :]]
    assert "AHP_TOO_MANY_ITEMS" in codes(flat(alternatives, {"one": judgements}))


def test_the_value_hint_says_to_swap_and_parameters_are_checked() -> None:
    project = with_leaf([j("a", "b", 0.5), j("a", "c", 4), j("b", "c", 2)])
    issue = next(i for i in validate_analysis(project, config(project)).issues)
    assert "swap row and column" in issue.message
    assert codes(base(), samples=3) == ["UNKNOWN_PARAMETER"]
    assert codes(base(), synthesis="geometric") == ["INVALID_PARAMETER"]


def test_inconsistency_is_a_warning_in_the_result_not_a_validation_error() -> None:
    project = with_leaf([j("a", "b", 9), j("c", "a", 3), j("b", "c", 5)])
    assert codes(project) == []
    result = ahp(project)
    assert [d.code for d in result.diagnostics] == ["AHP_INCONSISTENT"]
    assert result.matrices[-1].inconsistent


# ---- the read-only preview -------------------------------------------------------------------
def test_the_preview_reports_issues_until_the_matrix_is_complete() -> None:
    partial = svc.preview_ahp_matrix(["a", "b", "c"], [j("a", "b", 2)])
    assert not partial.ready and partial.analysis is None
    assert [i.code for i in partial.issues] == ["AHP_JUDGEMENT_MISSING"]
    assert "a/c, b/c" in partial.issues[0].message
    complete = svc.preview_ahp_matrix(
        ["a", "b", "c"], [j("a", "b", 2), j("a", "c", 4), j("b", "c", 2)]
    )
    assert complete.ready and complete.analysis is not None
    assert complete.analysis.priorities == pytest.approx({"a": 4 / 7, "b": 2 / 7, "c": 1 / 7})
    assert [i.code for i in svc.preview_ahp_matrix(["a", "a"], []).issues][
        0
    ] == "DUPLICATE_AHP_ITEM"
    assert [i.code for i in svc.preview_ahp_matrix([], []).issues] == ["AHP_TOO_FEW_ITEMS"]


# ---- schema version 5 and edits ---------------------------------------------------------------
def test_the_section_needs_version_5_and_clearing_restores_the_bytes() -> None:
    start = tiny_project()
    stated = with_leaf([j("a", "b", 2), j("a", "c", 4), j("b", "c", 2)]).ahp
    assert stated is not None
    project = ps.set_ahp_model(start, stated)
    text = to_json_text(project)
    assert json.loads(text)["schema_version"] == 5 and '"ahp"' in text
    assert '"ahp"' not in to_json_text(start) and start.required_schema_version() == 1
    assert to_json_text(ps.clear_ahp_model(project)) == to_json_text(start)
    raw = json.loads(text)
    raw["schema_version"] = 4
    with pytest.raises(ProjectLoadError, match="schema version 4 cannot contain 'ahp'"):
        repo.from_dict(raw)


def test_removal_prunes_judgements_and_never_adds_any() -> None:
    project = flat(
        ["a", "b", "c"],
        {"one": [j("a", "b", 2), j("a", "c", 4), j("b", "c", 2)], "two": [j("c", "a", 3)]},
        [j("one", "two", 5)],
    )
    without_b = ps.remove_alternative(project, "b")
    assert without_b.ahp is not None
    assert without_b.ahp.alternatives[0].judgements == [j("a", "c", 4)]
    without_two = ps.remove_criterion(project, "two")
    assert without_two.ahp is not None
    assert [a.criterion_id for a in without_two.ahp.alternatives] == ["one"]
    assert without_two.ahp.criteria[0].judgements == []
    grown = ps.add_alternative(project, "D", alt_id="d")
    assert grown.ahp == project.ahp
