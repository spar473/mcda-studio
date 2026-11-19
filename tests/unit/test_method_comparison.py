"""The method comparison: subsets, unknown methods, typed errors per column, limits, leader
agreement with ties, and each method's own reason (``docs/design/method-comparison.md``)."""

from pathlib import Path

import pytest

from mcda_studio.domain.errors import UnknownReferenceError
from mcda_studio.domain.outranking import (
    LinearPreferenceFunction,
    PrometheeCriterion,
    PrometheeModel,
)
from mcda_studio.domain.pairwise import PairwiseJudgement
from mcda_studio.domain.uncertainty import (
    CellUncertainty,
    GroupUncertainty,
    SmaaModel,
    UniformDistribution,
)
from mcda_studio.services import comparison_service as cs
from mcda_studio.services import project_service as ps
from mcda_studio.services import results_service as results
from mcda_studio.storage.json_repository import JsonProjectRepository

from builders import every_section, flat_project, scored_project, tiny_project, with_classes

ROOT = Path(__file__).parents[2]
QUALIFICATION = ROOT / "examples" / "supplier_qualification" / "project.json"


def column(comparison, method):  # type: ignore[no-untyped-def]
    return next(c for c in comparison.columns if c.method == method)


def test_a_subset_keeps_registry_order_and_an_unknown_method_is_refused() -> None:
    project = tiny_project()
    comparison = cs.compare_methods(project, methods=["ahp", "mavt"])
    assert comparison.methods == ["mavt", "ahp"] and [c.method for c in comparison.columns] == [
        "mavt",
        "ahp",
    ]
    with pytest.raises(UnknownReferenceError, match="unknown MCDA method 'electre'"):
        cs.compare_methods(project, methods=["mavt", "electre"])


def test_a_method_that_cannot_read_the_model_is_a_failed_column() -> None:
    comparison = cs.compare_methods(tiny_project())
    ahp = column(comparison, "ahp")
    assert ahp.status == "failed" and ahp.cells == [] and ahp.leaders == []
    assert ahp.error is not None and (ahp.error.status, ahp.error.code) == (
        422,
        "VALIDATION_FAILED",
    )
    assert ahp.error.issue_codes == ["AHP_NOT_STATED"]
    assert ahp.inputs == ["pairwise judgements (ahp)"]
    assert comparison.agreement.leaders_agree is None  # only MAVT ran


def test_a_method_over_its_limit_shows_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(results, "MAX_ALTERNATIVES", 1)
    comparison = cs.compare_methods(tiny_project())
    # The results limits apply before validation, so every method reports the limit.
    assert {c.error.code for c in comparison.columns if c.error} == {"ANALYSIS_LIMIT"}
    assert all(c.status == "failed" for c in comparison.columns)
    assert column(comparison, "mavt").error.status == 413  # type: ignore[union-attr]


def test_columns_name_inputs_parameters_and_their_own_labels() -> None:
    project = every_section(JsonProjectRepository().load(QUALIFICATION))
    comparison = cs.compare_methods(project)
    smaa = column(comparison, "smaa2")
    assert smaa.label == "sampled acceptability under these assumptions"
    assert smaa.quantity_name == "rank-1 acceptability" and smaa.configuration.parameters == {}
    assert "stated uncertainty (smaa)" in smaa.inputs and "classes (sorting)" in smaa.inputs
    assert column(comparison, "promethee2").quantity_range == "-1 to 1"
    assert column(comparison, "mavt").label is None
    assert all(c.record_digest and c.calculation_path for c in comparison.columns)
    labels = {c.method: c.method_label for c in comparison.columns}
    assert (
        labels["ahp"] == "AHP (pairwise priorities)" and labels["mavt"] == "MAVT (additive value)"
    )


def test_the_saved_method_keeps_its_parameters_and_others_use_defaults() -> None:
    project = ps.set_analysis_method(tiny_project(), "mavt")
    project.analysis.parameters = {"dominance_check": False}
    comparison = cs.compare_methods(project)
    assert column(comparison, "mavt").configuration.parameters == {"dominance_check": False}
    assert column(comparison, "ahp").configuration.parameters == {}


def test_a_tied_leader_is_not_agreement() -> None:
    project = flat_project([[1.0, 0.0], [0.0, 1.0]], [50.0, 50.0])  # MAVT ties a0 and a1
    model = PrometheeModel(
        criteria=[
            PrometheeCriterion(
                criterion_id=c,
                direction="maximise",
                weight=w,
                function=LinearPreferenceFunction(q=0, p=1),
            )
            for c, w in (("c0", 2.0), ("c1", 1.0))
        ]
    )
    comparison = cs.compare_methods(ps.set_promethee_model(project, model))
    assert column(comparison, "mavt").leaders == ["a0", "a1"]
    assert column(comparison, "promethee2").leaders == ["a0"]
    assert comparison.agreement.leaders_agree is False
    reason = comparison.agreement.reasons[0]
    assert reason.method == "promethee2" and "first place is" in reason.reasons[0]


def test_promethee_reasons_come_from_its_explanation_of_the_two_leaders() -> None:
    project = ps.set_promethee_model(
        tiny_project(),
        PrometheeModel(
            criteria=[
                PrometheeCriterion(
                    criterion_id="cost",
                    direction="minimise",
                    weight=2.0,
                    function=LinearPreferenceFunction(q=50.0, p=60.0),
                ),
                PrometheeCriterion(
                    criterion_id="quality",
                    direction="maximise",
                    weight=1.0,
                    function=LinearPreferenceFunction(q=1.0, p=5.0),
                ),
            ]
        ),
    )
    comparison = cs.compare_methods(project, methods=["mavt", "promethee2"])
    (reason,) = comparison.agreement.reasons
    assert (reason.leaders, reason.mavt_leaders) == (["b"], ["a"])
    own = column(comparison, "promethee2")
    record = results.analysis_record(project, own.configuration)
    pair = record.result.explanation.pairs[0]  # type: ignore[union-attr]
    assert reason.reasons == pair.reasons and any("within q = 50" in r for r in reason.reasons)


def test_smaa_reason_says_when_no_alternative_leads_in_half_the_draws() -> None:
    project = flat_project([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], [1.0, 1.0, 1.0])
    project = ps.set_smaa_model(
        project, SmaaModel(groups=[GroupUncertainty(parent_id=None, kind="unknown")])
    )
    comparison = cs.compare_methods(project, methods=["mavt", "smaa2"])
    (reason,) = comparison.agreement.reasons
    assert reason.reasons[-1] == "no alternative takes rank 1 in half of the draws"
    assert "takes rank 1 in" in reason.reasons[0] and "% to " in reason.reasons[0]


def test_ahp_reasons_name_its_inconsistent_matrices() -> None:
    project = every_section(JsonProjectRepository().load(QUALIFICATION))
    assert project.ahp is not None
    model = project.ahp.model_copy(deep=True)
    model.alternatives[0].judgements = [
        PairwiseJudgement(row=j.column, column=j.row, value=9.0) if k % 2 else j
        for k, j in enumerate(model.alternatives[0].judgements)
    ]
    comparison = cs.compare_methods(ps.set_ahp_model(project, model), methods=["mavt", "ahp"])
    (reason,) = comparison.agreement.reasons
    leaf = model.alternatives[0].criterion_id
    assert reason.reasons[0].startswith("AHP reads its own pairwise judgements")
    assert any(
        r.startswith(f"the alternatives on {leaf}: consistency ratio") for r in reason.reasons
    )


def test_sorting_and_smaa_classes_can_disagree() -> None:
    project = with_classes(scored_project({"a": 0.9, "b": 0.52}), [("Go", 0.5), ("Stop", None)])
    project = ps.set_smaa_model(
        project,
        SmaaModel(
            cells=[
                CellUncertainty(
                    alternative_id="b",
                    criterion_id="score",
                    distribution=UniformDistribution(lower=0.2, upper=0.6),
                )
            ]
        ),
    )
    comparison = cs.compare_methods(project, methods=["mavt_sorting", "smaa2"])
    rows = {c.alternative_id: c for c in comparison.agreement.classes}
    assert rows["a"].agree and not rows["b"].agree
    assert (rows["b"].sorting_class_id, rows["b"].smaa_class_id) == ("go", "stop")
    assert rows["b"].smaa_class_share == pytest.approx(0.75, abs=0.02)
    assert comparison.agreement.leaders_agree is True and comparison.agreement.reasons == []


def test_without_mavt_there_are_no_reasons() -> None:
    project = every_section(JsonProjectRepository().load(QUALIFICATION))
    comparison = cs.compare_methods(project, methods=["promethee2", "ahp"])
    assert comparison.agreement.leaders_agree is not None and comparison.agreement.reasons == []


def test_a_shared_tie_for_first_is_still_not_agreement() -> None:
    project = with_classes(
        flat_project([[1.0, 0.0], [0.0, 1.0]], [50.0, 50.0]), [("Go", 0.4), ("Stop", None)]
    )
    comparison = cs.compare_methods(project, methods=["mavt", "mavt_sorting"])
    assert [c.leaders for c in comparison.columns] == [["a0", "a1"], ["a0", "a1"]]
    assert comparison.agreement.leaders_agree is False  # one leader each is needed to agree
    assert [g.methods for g in comparison.agreement.leader_groups] == [["mavt", "mavt_sorting"]]
