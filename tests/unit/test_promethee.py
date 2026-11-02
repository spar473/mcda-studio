"""PROMETHEE II: validation, hand-derived cases, the explanation against MAVT, schema version 4
and the section edits (design note ``docs/design/promethee-ii.md``)."""

import json
from fractions import Fraction

import pytest

from mcda_studio.domain.criteria import Direction, LinearValueFunction
from mcda_studio.domain.errors import AnalysisLimitError, ProjectLoadError, ValidationFailed
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
from mcda_studio.methods.base import validate_analysis
from mcda_studio.methods.promethee import flows as promethee_flows
from mcda_studio.methods.promethee.explanation import DETAIL_LIMIT
from mcda_studio.methods.promethee.flows import preference_degree
from mcda_studio.methods.promethee.validation import threshold_tolerance
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text

from builders import tiny_project

repo = JsonProjectRepository()


def config(project: Project, **parameters: object):  # type: ignore[no-untyped-def]
    return project.analysis.model_copy(update={"method": "promethee2", "parameters": parameters})


def promethee(project: Project) -> PrometheeResult:
    result = svc.evaluate_project(project, config(project))
    assert isinstance(result, PrometheeResult)
    return result


def codes(project: Project, **parameters: object) -> list[str]:
    return [i.code for i in validate_analysis(project, config(project, **parameters)).issues]


def entry(
    criterion: str,
    direction: str = "maximise",
    weight: float = 1.0,
    function: AnyPreferenceFunction | None = None,
    coding: dict[str, float] | None = None,
) -> PrometheeCriterion:
    return PrometheeCriterion(
        criterion_id=criterion,
        direction=direction,  # type: ignore[arg-type]
        weight=weight,
        function=function or UsualFunction(),
        coding=coding,
    )


def flat(
    rows: dict[str, list[float]],
    entries: list[PrometheeCriterion],
    *,
    value_functions: bool = False,
) -> Project:
    """Alternatives on flat interval leaves c1..; optionally with MAVT value functions too."""
    p = ps.new_project("Flat").model_copy(update={"id": "flat"})
    for alt in rows:
        p = ps.add_alternative(p, alt.upper(), alt_id=alt)
    width = len(next(iter(rows.values())))
    for j in range(width):
        p = ps.add_criterion(
            p,
            f"Criterion {j + 1}",
            crit_id=f"c{j + 1}",
            scale=Scale(type=ScaleType.INTERVAL, lower=-100.0, upper=100.0),
            value_function=LinearValueFunction() if value_functions else None,
        )
        if value_functions:
            p = ps.set_judgement(p, f"c{j + 1}", 50.0)
    for alt, row in rows.items():
        for j, value in enumerate(row):
            p = ps.set_performance(p, alt, f"c{j + 1}", value)
    return ps.set_promethee_model(p, PrometheeModel(criteria=entries))


def tiny_promethee(**overrides: AnyPreferenceFunction) -> Project:
    """``tiny_project`` (MAVT valid) with a PROMETHEE section on cost and quality."""
    return ps.set_promethee_model(
        tiny_project(),
        PrometheeModel(
            criteria=[
                entry("cost", "minimise", 2.0, overrides.get("cost")),
                entry("quality", "maximise", 1.0, overrides.get("quality")),
            ]
        ),
    )


# ---- preference functions ------------------------------------------------------------------
@pytest.mark.parametrize(
    ("function", "d", "expected"),
    [
        (UsualFunction(), 0.0, 0.0),
        (UsualFunction(), -3.0, 0.0),
        (UsualFunction(), 1e-6, 1.0),
        (UShapeFunction(q=2.0), 2.0, 0.0),  # d = q is no preference
        (UShapeFunction(q=2.0), 2.000001, 1.0),
        (VShapeFunction(p=4.0), 2.0, 0.5),
        (VShapeFunction(p=4.0), 4.0, 1.0),
        (VShapeFunction(p=4.0), 9.0, 1.0),
        (LinearPreferenceFunction(q=1.0, p=3.0), 1.0, 0.0),  # at q
        (LinearPreferenceFunction(q=1.0, p=3.0), 2.0, 0.5),
        (LinearPreferenceFunction(q=1.0, p=3.0), 3.0, 1.0),  # at p
        (LinearPreferenceFunction(q=1.0, p=3.0), 30.0, 1.0),
    ],
)
def test_preference_degrees_by_hand(
    function: AnyPreferenceFunction, d: float, expected: float
) -> None:
    assert preference_degree(function, d, threshold_tolerance(d, 0.0)) == expected


def test_a_difference_equal_to_q_in_decimal_counts_as_q() -> None:
    d = 0.79 - 0.73  # 0.06000000000000005 in binary floating point
    tol = threshold_tolerance(0.79, 0.73)
    assert preference_degree(UShapeFunction(q=0.06), d, tol) == 0.0
    assert preference_degree(LinearPreferenceFunction(q=0.06, p=0.15), d, tol) == 0.0
    assert preference_degree(UShapeFunction(q=0.06), d, 0.0) == 1.0  # what no tolerance gives


# ---- hand-derived flows -----------------------------------------------------------------------
def test_minimise_prefers_the_lower_measurement() -> None:
    result = promethee(flat({"a": [10.0], "b": [20.0]}, [entry("c1", "minimise")]))
    assert [f.alternative_id for f in result.flows] == ["a", "b"]
    a = result.flows[0]
    assert (a.positive_flow, a.negative_flow, a.net_flow) == (1.0, 0.0, 1.0)


def test_two_alternatives_have_no_via_others_part() -> None:
    project = tiny_promethee(cost=VShapeFunction(p=80.0))
    result = promethee(project)
    # cost: a is 40 cheaper, 40/80 = 0.5 of full preference, weight 2/3; quality: b is 3 better
    pi_ab, pi_ba = Fraction(2, 3) * Fraction(1, 2), Fraction(1, 3)
    a = next(f for f in result.flows if f.alternative_id == "a")
    assert a.net_flow == pytest.approx(float(pi_ab - pi_ba), abs=1e-15)
    assert result.preference_matrix["a"]["b"] == pytest.approx(float(pi_ab), abs=1e-15)
    assert len(result.explanation.pairs) == 1  # MAVT puts a first; PROMETHEE II ties them
    for pair in result.explanation.pairs:
        assert pair.via_others == pytest.approx(0.0, abs=1e-15)


def test_all_weight_on_one_criterion_makes_the_net_flow_that_criterion_flow() -> None:
    rows = {"a": [1.0, 5.0], "b": [3.0, 1.0], "c": [2.0, 9.0]}
    result = promethee(
        flat(
            rows, [entry("c1", weight=1.0, function=VShapeFunction(p=2.0)), entry("c2", weight=0.0)]
        )
    )
    for f in result.flows:
        assert f.net_flow == pytest.approx(f.criterion_flows["c1"], abs=1e-15)
    assert "PROMETHEE_CRITERION_INERT" in [d.code for d in result.diagnostics]


def test_codings_compare_labels_by_their_codes() -> None:
    p = flat({"a": [0.0], "b": [0.0], "c": [0.0]}, [entry("c1", weight=0.0)])
    p = ps.add_criterion(
        p,
        "Maturity",
        crit_id="maturity",
        scale=Scale(type=ScaleType.ORDINAL, labels=["low", "medium", "high"]),
    )
    for alt, label in (("a", "low"), ("b", "medium"), ("c", "high")):
        p = ps.set_performance(p, alt, "maturity", label)
    coding = {"low": 1.0, "medium": 2.0, "high": 5.0}
    section = PrometheeModel(
        criteria=[
            entry("c1", weight=0.0),
            entry("maturity", weight=1.0, function=VShapeFunction(p=4.0), coding=coding),
        ]
    )
    result = promethee(ps.set_promethee_model(p, section))
    # coded differences: b-a 1 (0.25), c-a 4 (1), c-b 3 (0.75)
    pi = result.preference_matrix
    assert (pi["b"]["a"], pi["c"]["a"], pi["c"]["b"]) == (0.25, 1.0, 0.75)
    assert result.criteria[1].coding == coding and result.criteria[1].unit is None


def test_promethee_i_finds_an_incomparability_the_net_flow_hides() -> None:
    # weights 3:2, usual functions. pi(a,b) = pi(a,c) = 2/5, pi(b,a) = pi(c,a) = pi(c,b) = 3/5,
    # pi(b,c) = 0: a has F+ 2/5 and F- 3/5, b has F+ 3/10 and F- 1/2. Both net flows are -1/5.
    rows = {"a": [0.0, 1.0], "b": [1.0, 0.0], "c": [2.0, 0.0]}
    result = promethee(flat(rows, [entry("c1", weight=3.0), entry("c2", weight=2.0)]))
    by_id = {f.alternative_id: f for f in result.flows}
    a, b = by_id["a"], by_id["b"]
    assert (a.positive_flow, a.negative_flow) == pytest.approx((0.4, 0.6))
    assert (b.positive_flow, b.negative_flow) == pytest.approx((0.3, 0.5))
    assert a.net_flow == pytest.approx(b.net_flow) and a.rank == b.rank == 2
    relations = {frozenset((p.alternative_a, p.alternative_b)): p for p in result.partial_order}
    assert relations[frozenset(("a", "b"))].relation == "incomparable"
    c_over_a = relations[frozenset(("a", "c"))]
    assert (c_over_a.alternative_a, c_over_a.relation) == ("c", "preferred")
    assert "INCOMPARABLE_PAIRS" in [d.code for d in result.diagnostics]


def test_an_added_alternative_reverses_two_others_through_the_via_others_part() -> None:
    entries = [entry("c1", weight=0.6), entry("c2", weight=0.2), entry("c3", weight=0.2)]
    two = promethee(flat({"a": [1.0, 0.0, 0.0], "b": [0.0, 1.0, 1.0]}, entries))
    assert [f.alternative_id for f in two.flows] == ["a", "b"]
    three = flat(
        {"a": [1.0, 0.0, 0.0], "b": [0.0, 1.0, 1.0], "c": [2.0, 0.5, 0.5]},
        entries,
        value_functions=True,
    )
    three = ps.set_judgement(three, "c1", 100.0)  # MAVT keeps a ahead of b
    three = ps.set_judgement(three, "c2", 10.0)
    three = ps.set_judgement(three, "c3", 10.0)
    result = promethee(three)
    by_id = {f.alternative_id: f for f in result.flows}
    assert by_id["b"].net_flow > by_id["a"].net_flow  # c reversed a and b
    pair = next(
        p for p in result.explanation.pairs if {p.alternative_a, p.alternative_b} == {"a", "b"}
    )
    a_first = pair.alternative_a == "a"
    head, via = (pair.head_to_head, pair.via_others)
    if not a_first:
        head, via = -head, -via
    assert head == pytest.approx(0.2) and via == pytest.approx(-0.4)


def test_swing_weights_and_value_functions_are_never_read() -> None:
    project = tiny_promethee(cost=LinearPreferenceFunction(q=5.0, p=50.0))
    before = promethee(project)
    changed = ps.set_judgement(project, "quality", 100.0)
    changed = ps.set_value_function(
        changed, "cost", LinearValueFunction(direction=Direction.INCREASING)
    )
    after = promethee(changed)
    assert after.flows == before.flows and after.partial_order == before.partial_order
    assert after.explanation != before.explanation  # only MAVT's side moved


def test_the_label_and_the_ranking_hold_flows_not_values() -> None:
    result = promethee(tiny_promethee())
    assert (
        result.label.startswith("net outranking flows") and "not preference values" in result.label
    )
    assert [(r.alternative_id, r.value) for r in result.ranking] == [
        (f.alternative_id, f.net_flow) for f in result.flows
    ]


# ---- validation -------------------------------------------------------------------------------
def test_mavt_inputs_are_not_required() -> None:
    project = flat({"a": [1.0], "b": [2.0]}, [entry("c1")])
    project = project.model_copy(update={"weight_profiles": []})
    assert codes(project) == []
    assert promethee(project).explanation.available is False


def test_measurement_checks_still_block() -> None:
    project = flat({"a": [1.0], "b": [2.0]}, [entry("c1")])
    missing = ps.clear_performance(project, "b", "c1")
    assert "MISSING_MEASUREMENT" in codes(missing)
    with pytest.raises(ValidationFailed):
        promethee(missing)


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda p: ps.clear_promethee_model(p), "PROMETHEE_NOT_STATED"),
        (lambda p: ps.remove_alternative(p, "b"), "PROMETHEE_TOO_FEW_ALTERNATIVES"),
        (lambda p: section(p, []), "PROMETHEE_CRITERION_MISSING"),
        (lambda p: section(p, [entry("c1"), entry("nope")]), "UNKNOWN_PROMETHEE_CRITERION"),
        (lambda p: section(p, [entry("c1"), entry("c1")]), "DUPLICATE_PROMETHEE_CRITERION"),
        (
            lambda p: section(p, [entry("c1", function=UShapeFunction(q=-1))]),
            "INVALID_PREFERENCE_FUNCTION",
        ),
        (
            lambda p: section(p, [entry("c1", function=VShapeFunction(p=0))]),
            "INVALID_PREFERENCE_FUNCTION",
        ),
        (
            lambda p: section(p, [entry("c1", function=LinearPreferenceFunction(q=2, p=2))]),
            "INVALID_PREFERENCE_FUNCTION",
        ),
        (lambda p: section(p, [entry("c1", weight=-1.0)]), "INVALID_PROMETHEE_WEIGHT"),
        (lambda p: section(p, [entry("c1", weight=0.0)]), "ZERO_PROMETHEE_WEIGHTS"),
        (lambda p: section(p, [entry("c1", coding={"x": 1.0})]), "UNEXPECTED_CODING"),
    ],
)
def test_every_numeric_error_code(change, code: str) -> None:  # type: ignore[no-untyped-def]
    project = change(flat({"a": [1.0], "b": [2.0]}, [entry("c1")]))
    assert code in codes(project)
    with pytest.raises(ValidationFailed):
        promethee(project)


def section(project: Project, entries: list[PrometheeCriterion]) -> Project:
    return ps.set_promethee_model(project, PrometheeModel(criteria=entries))


def labelled(kind: ScaleType, coding: dict[str, float] | None) -> Project:
    p = flat({"a": [1.0], "b": [2.0]}, [entry("c1")])
    p = ps.add_criterion(
        p, "Grade", crit_id="grade", scale=Scale(type=kind, labels=["low", "mid", "high"])
    )
    p = ps.set_performance(p, "a", "grade", "low")
    p = ps.set_performance(p, "b", "grade", "high")
    return section(p, [entry("c1"), entry("grade", coding=coding)])


def test_labelled_leaves_need_a_code_for_each_label() -> None:
    assert "CODING_MISSING" in codes(labelled(ScaleType.CATEGORICAL, None))
    assert "CODING_MISSING" in codes(labelled(ScaleType.CATEGORICAL, {"low": 0.0, "high": 1.0}))
    extra = {"low": 0.0, "mid": 1.0, "high": 2.0, "top": 3.0}
    assert "UNKNOWN_CODED_LABEL" in codes(labelled(ScaleType.CATEGORICAL, extra))
    assert codes(labelled(ScaleType.CATEGORICAL, {"low": 2.0, "mid": 0.0, "high": 1.0})) == []


def test_ordinal_codes_against_the_label_order_warn() -> None:
    unordered = labelled(ScaleType.ORDINAL, {"low": 2.0, "mid": 0.0, "high": 1.0})
    assert codes(unordered) == ["ORDINAL_CODING_UNORDERED"]
    promethee(unordered)  # a warning only
    assert codes(labelled(ScaleType.ORDINAL, {"low": 0.0, "mid": 1.0, "high": 3.0})) == []


def test_a_criterion_that_can_never_contribute_warns() -> None:
    wide_q = flat({"a": [1.0], "b": [2.5]}, [entry("c1", function=UShapeFunction(q=1.5))])
    assert codes(wide_q) == ["PROMETHEE_CRITERION_INERT"]
    spread = flat({"a": [1.0], "b": [1.0], "c": [2.0]}, [entry("c1")])
    assert codes(spread) == []
    same = flat({"a": [1.0, 3.0], "b": [2.0, 3.0]}, [entry("c1"), entry("c2")])
    assert codes(same) == ["PROMETHEE_CRITERION_INERT"]


def test_unknown_parameters_warn_and_are_ignored() -> None:
    project = flat({"a": [1.0], "b": [2.0]}, [entry("c1")])
    assert codes(project, samples=10) == ["UNKNOWN_PARAMETER"]


def test_a_leaf_that_gains_children_is_reported_not_repaired() -> None:
    project = flat({"a": [1.0, 2.0], "b": [2.0, 1.0]}, [entry("c1"), entry("c2")])
    grown = ps.add_criterion(project, "Part", parent_id="c2", discard_leaf_data=True)
    assert grown.promethee == project.promethee
    assert "UNKNOWN_PROMETHEE_CRITERION" in codes(grown)


def test_the_work_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    project = flat({"a": [1.0], "b": [2.0]}, [entry("c1")])
    monkeypatch.setattr(promethee_flows, "MAX_DEGREES", 2**2 * 1 - 1)
    with pytest.raises(AnalysisLimitError, match="10\\^6 preference degrees"):
        promethee(project)


# ---- the explanation against MAVT ---------------------------------------------------------
def capped_case() -> Project:
    """MAVT puts most weight on cost, where A is far ahead; PROMETHEE weighs the three equally
    and caps A's cost advantage at p = 10, so B, ahead on quality and delivery, comes first."""
    p = ps.new_project("Capped").model_copy(update={"id": "capped"})
    p = ps.add_alternative(p, "Alpha", alt_id="a")
    p = ps.add_alternative(p, "Beta", alt_id="b")
    specs = [
        ("cost", "Cost", 100.0, Direction.DECREASING, "NZD"),
        ("quality", "Quality", 10.0, Direction.INCREASING, None),
        ("delivery", "Delivery", 10.0, Direction.INCREASING, None),
    ]
    for crit, name, upper, direction, unit in specs:
        p = ps.add_criterion(
            p,
            name,
            crit_id=crit,
            scale=Scale(type=ScaleType.RATIO, lower=0.0, upper=upper, unit=unit),
            value_function=LinearValueFunction(direction=direction),
        )
    for alt, row in (("a", (20.0, 6.0, 5.0)), ("b", (60.0, 7.0, 6.0))):
        for (crit, *_), value in zip(specs, row, strict=True):
            p = ps.set_performance(p, alt, crit, value)
    for crit, rating in (("cost", 100.0), ("quality", 20.0), ("delivery", 20.0)):
        p = ps.set_judgement(p, crit, rating)
    return section(
        p,
        [
            entry("cost", "minimise", 1.0, VShapeFunction(p=10.0)),
            entry("quality", "maximise", 1.0),
            entry("delivery", "maximise", 1.0),
        ],
    )


def test_a_capped_advantage_that_flips_the_order_is_named() -> None:
    result = promethee(capped_case())
    explanation = result.explanation
    assert explanation.available
    assert [(r.alternative_id, r.mavt_rank, r.promethee_rank) for r in explanation.ranks] == [
        ("b", 2, 1),
        ("a", 1, 2),
    ]
    (pair,) = explanation.pairs
    assert (pair.alternative_a, pair.alternative_b) == ("a", "b")
    assert pair.value_gap == pytest.approx((80 + 12 + 10 - 40 - 14 - 12) / 140)
    assert pair.flow_gap == pytest.approx(-2 / 3) and pair.head_to_head == pytest.approx(-2 / 3)
    rows = {r.criterion_id: r for r in pair.criteria}
    cost = rows["cost"]
    assert (cost.difference, cost.favours, cost.zone, cost.capped, cost.p) == (
        40.0,
        "a",
        "full",
        True,
        10.0,
    )
    assert cost.promethee_contribution == pytest.approx(2 / 3)
    assert cost.mavt_contribution == pytest.approx(40 / 140)
    assert rows["quality"].favours == "b" and rows["quality"].zone == "full"
    assert pair.reasons == [
        "Quality: favours Beta in PROMETHEE (-0.667 of the flow gap); Beta is 1 higher, and the "
        "usual function counts any difference as full preference.",
        "Cost: MAVT's advantage for Alpha (+0.286 value) is reduced; Alpha is 40 NZD lower, "
        "beyond p = 10, so PROMETHEE counts full preference and no more.",
        "Delivery: favours Beta in PROMETHEE (-0.667 of the flow gap); Beta is 1 higher, and the "
        "usual function counts any difference as full preference.",
    ]


def test_zones_name_their_thresholds() -> None:
    # MAVT puts a first. PROMETHEE: a's 40 lower cost lies within q = 50 (no preference); b's 3
    # higher quality lies between q = 1 and p = 5 (half of full preference), so b comes first.
    project = tiny_promethee(
        cost=LinearPreferenceFunction(q=50.0, p=60.0),
        quality=LinearPreferenceFunction(q=1.0, p=5.0),
    )
    (pair,) = promethee(project).explanation.pairs
    rows = {r.criterion_id: r for r in pair.criteria}
    assert (rows["cost"].zone, rows["cost"].capped, rows["cost"].q) == ("no_preference", False, 50)
    assert (rows["quality"].zone, rows["quality"].preference_degree) == ("partial", 0.5)
    assert pair.reasons == [
        "Quality: favours B in PROMETHEE (-0.333 of the flow gap); B is 3 higher, between q = 1 "
        "and p = 5, so PROMETHEE counts 0.5 of full preference.",
        "Cost: MAVT's advantage for A (+0.267 value) is reduced; A is 40 lower, within q = 50, so "
        "PROMETHEE counts no preference.",
    ]


def test_the_explanation_is_omitted_with_the_reason_when_mavt_is_invalid() -> None:
    project = flat({"a": [1.0], "b": [2.0]}, [entry("c1")])
    result = promethee(project)
    assert not result.explanation.available
    assert "MISSING_VALUE_FUNCTION" in result.explanation.unavailable_codes
    assert result.explanation.unavailable_reason and result.explanation.pairs == []
    assert "EXPLANATION_UNAVAILABLE" in [d.code for d in result.diagnostics]
    assert [f.alternative_id for f in result.flows] == ["b", "a"]


def test_detail_is_limited_to_fifty_pairs_with_a_diagnostic() -> None:
    # MAVT reads c1 (rising); PROMETHEE reads c2 (falling): every one of 66 pairs is reversed.
    rows = {f"x{i:02d}": [float(i), float(-i)] for i in range(12)}
    project = flat(rows, [entry("c1", weight=0.0), entry("c2")], value_functions=True)
    project = ps.set_judgement(project, "c1", 100.0)
    project = ps.set_judgement(project, "c2", 1.0)
    result = promethee(project)
    pairs = result.explanation.pairs
    assert len(pairs) == 66 and DETAIL_LIMIT == 50
    assert [p.detailed for p in pairs] == [True] * 50 + [False] * 16
    assert all(p.criteria and p.reasons for p in pairs[:50])
    assert all(not p.criteria and not p.reasons for p in pairs[50:])
    change = {
        r.alternative_id: abs(r.mavt_rank - r.promethee_rank) for r in result.explanation.ranks
    }
    keys = [max(change[p.alternative_a], change[p.alternative_b]) for p in pairs]
    assert keys == sorted(keys, reverse=True)
    assert "EXPLANATION_LIMITED" in [d.code for d in result.diagnostics]


def test_agreeing_methods_list_no_pairs() -> None:
    result = promethee(tiny_promethee())
    assert result.explanation.available and result.explanation.pairs == []
    assert [r.mavt_rank for r in result.explanation.ranks] == [1, 2]


# ---- schema version 4 and edits ---------------------------------------------------------
def test_the_section_needs_version_4_and_clearing_restores_the_bytes() -> None:
    start = tiny_project()
    stated = tiny_promethee().promethee
    assert stated is not None
    with_section = ps.set_promethee_model(start, stated)
    assert start.required_schema_version() == 1
    assert with_section.required_schema_version() == 4
    text = to_json_text(with_section)
    assert json.loads(text)["schema_version"] == 4 and '"coding"' not in text
    assert '"promethee"' not in to_json_text(start)
    assert to_json_text(ps.clear_promethee_model(with_section)) == to_json_text(start)
    assert repo.from_dict(json.loads(text)) == with_section


def test_a_version_3_file_cannot_hold_the_section() -> None:
    raw = json.loads(to_json_text(tiny_promethee()))
    raw["schema_version"] = 3
    with pytest.raises(ProjectLoadError, match="schema version 3 cannot contain 'promethee'"):
        repo.from_dict(raw)


def test_removing_a_criterion_removes_its_entry() -> None:
    project = ps.remove_criterion(tiny_promethee(), "quality")
    assert project.promethee is not None
    assert [c.criterion_id for c in project.promethee.criteria] == ["cost"]
    kept = ps.remove_alternative(tiny_promethee(), "b")
    assert kept.promethee == tiny_promethee().promethee
