"""Reference cases: the sidecar's validation and snapshot guard, label gaps, missing ratings,
the shared-fraction threshold, both weightings, exact ordering, ``k``, outcomes on request and
read-only behaviour. Hand-computed numbers use the fixture in ``reference_case_builders``."""

import json
from datetime import timedelta
from fractions import Fraction
from typing import Any

import pytest
from pydantic import ValidationError

import reference_case_builders as b
from mcda_studio.domain.errors import McdaError, UnknownReferenceError
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.reference_cases import ReferenceCasesInvalid
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.services import reference_case_service as svc

HAND = {"o4": "D", "o5": "v5", "cat": "red"}
FULL = {"o4": "A", "o5": "v1", "cat": "green", "o4b": "B", "o5b": "v4"}
PARTIAL = {"o5": "v1", "cat": "red", "o4b": "C", "o5b": "v5"}


def run(raw: dict[str, Any], **kwargs: Any) -> svc.ReferenceCasesResult:
    kwargs.setdefault("alternative_id", "x")
    return svc.reference_cases(b.project(), b.load(raw), **kwargs)


def issues(raw: dict[str, Any]) -> list[tuple[str, str]]:
    report = svc.validate(b.project(), b.load(raw))
    return [(i.code, i.path) for i in report.issues]


# ---- validation and the snapshot guard ----------------------------------------------------------


def test_a_valid_set_has_no_issues_and_counts_cases_and_ratings() -> None:
    report = svc.validate(b.project(), b.load(b.reference_set(b.case("a", HAND))))
    assert report.valid and report.issues == []
    assert (report.case_count, report.rating_count) == (1, 3)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (
            lambda r: r["cases"][0]["ratings"][1].update(criterion_id="nope"),
            ("REFERENCE_UNKNOWN_CRITERION", "cases[0].ratings[1].criterion_id"),
        ),
        (
            lambda r: r["cases"][0]["ratings"][0].update(label="E"),
            ("REFERENCE_UNKNOWN_LABEL", "cases[0].ratings[0].label"),
        ),
        (
            lambda r: r["cases"][0]["ratings"].append(
                {"criterion_id": "num", "label": "5", "claim_ids": ["c1"]}
            ),
            ("REFERENCE_NUMERIC_CRITERION", "cases[0].ratings[3].criterion_id"),
        ),
        (
            lambda r: r["cases"][0]["outcome"].update(as_of="2021-10-26"),
            ("REFERENCE_OUTCOME_BEFORE_SNAPSHOT", "cases[0].outcome.as_of"),
        ),
        (
            lambda r: r["cases"][0]["ratings"][2].update(claim_ids=["c1", "c9"]),
            ("REFERENCE_UNKNOWN_CLAIM", "cases[0].ratings[2].claim_ids[1]"),
        ),
        (
            lambda r: r["cases"][0]["outcome"].update(claim_ids=["c9"]),
            ("REFERENCE_UNKNOWN_CLAIM", "cases[0].outcome.claim_ids[0]"),
        ),
        (
            lambda r: r["cases"].append(json.loads(json.dumps(r["cases"][0]))),
            ("REFERENCE_DUPLICATE_CASE", "cases[1].id"),
        ),
        (
            lambda r: (
                r["cases"][0]["claims"][1].update(id="c1"),
                r["cases"][0]["outcome"].update(claim_ids=["c1"]),
            ),
            ("REFERENCE_DUPLICATE_CLAIM", "cases[0].claims[1].id"),
        ),
        (
            lambda r: r["cases"][0]["claims"][0].update(source="missing"),
            ("REFERENCE_UNKNOWN_SOURCE", "cases[0].claims[0].source"),
        ),
        (
            lambda r: r["cases"][0]["ratings"].append(r["cases"][0]["ratings"][0]),
            ("REFERENCE_DUPLICATE_RATING", "cases[0].ratings[3].criterion_id"),
        ),
        (
            lambda r: r.update(criteria_from="other"),
            ("REFERENCE_PROJECT_MISMATCH", "criteria_from"),
        ),
    ],
)
def test_each_validation_error_names_its_path(change: Any, expected: tuple[str, str]) -> None:
    raw = b.reference_set(b.case("a", HAND))
    change(raw)
    assert issues(raw) == [expected]


def test_a_rating_on_a_parent_criterion_is_refused() -> None:
    from mcda_studio.services import project_service as ps

    project = ps.add_criterion(b.project(), "Group", crit_id="group")
    project = ps.add_criterion(project, "Sub", "group", "sub", **b._ordinal(b.FOUR))
    raw = b.reference_set(b.case("a", HAND))
    raw["cases"][0]["ratings"][0]["criterion_id"] = "group"
    report = svc.validate(project, b.load(raw))
    assert [(i.code, i.path) for i in report.issues] == [
        ("REFERENCE_UNKNOWN_CRITERION", "cases[0].ratings[0].criterion_id")
    ]
    assert "not a leaf" in report.issues[0].message


def test_the_numeric_refusal_says_version_one_does_not_support_it() -> None:
    raw = b.reference_set(b.case("a", {**HAND}))
    raw["cases"][0]["ratings"].append({"criterion_id": "num", "label": "5", "claim_ids": ["c1"]})
    report = svc.validate(b.project(), b.load(raw))
    assert "version 1" in report.issues[0].message


def test_a_source_one_day_after_the_snapshot_cannot_support_a_rating() -> None:
    late = b.source(b.SNAPSHOT + timedelta(days=1))
    raw = b.reference_set(b.case("a", HAND, source_key="late"), late=late)
    assert issues(raw) == [
        ("REFERENCE_SOURCE_AFTER_SNAPSHOT", f"cases[0].ratings[{i}].claim_ids[0]") for i in range(3)
    ]
    with pytest.raises(ReferenceCasesInvalid) as caught:
        run(raw)
    assert "reference set has 3 validation error(s)" in str(caught.value)


def test_a_source_on_the_snapshot_day_can_support_a_rating() -> None:
    same_day = b.source(b.SNAPSHOT)
    raw = b.reference_set(b.case("a", HAND, source_key="same"), same=same_day)
    assert issues(raw) == []


def test_an_undated_source_supports_an_outcome_but_never_a_rating() -> None:
    outcome_only = b.reference_set(b.case("a", HAND, outcome_source="undated"))
    assert issues(outcome_only) == []
    rating = b.reference_set(b.case("a", HAND, source_key="undated"))
    assert issues(rating) == [
        ("REFERENCE_UNDATED_SOURCE", f"cases[0].ratings[{i}].claim_ids[0]") for i in range(3)
    ]


def test_an_outcome_on_the_snapshot_day_is_accepted() -> None:
    raw = b.reference_set(b.case("a", HAND, as_of=b.SNAPSHOT))
    assert issues(raw) == []


def test_unknown_versions_kinds_and_loose_dates_are_refused_by_the_format() -> None:
    raw = b.reference_set(b.case("a", HAND))
    with pytest.raises(ValidationError, match="version 2 is not supported"):
        b.load({**raw, "version": 2})
    with pytest.raises(ValidationError, match="not a reference set"):
        b.load({**raw, "kind": "external-proposals"})
    with pytest.raises(ValidationError, match="explicit integers"):
        b.load({**raw, "version": "1"})
    loose = json.loads(json.dumps(raw))
    loose["cases"][0]["snapshot_date"] = "27/10/2021"
    with pytest.raises(ValidationError, match="ISO calendar dates"):
        b.load(loose)
    stamp = json.loads(json.dumps(raw))
    stamp["sources"]["before"]["date"] = 1633046400
    with pytest.raises(ValidationError, match="ISO calendar dates"):
        b.load(stamp)
    extra = json.loads(json.dumps(raw))
    extra["cases"][0]["score"] = 1
    with pytest.raises(ValidationError):
        b.load(extra)
    no_claims = json.loads(json.dumps(raw))
    no_claims["cases"][0]["ratings"][0]["claim_ids"] = []
    with pytest.raises(ValidationError):
        b.load(no_claims)


# ---- label gaps ---------------------------------------------------------------------------------


def test_ordinal_gaps_at_both_ends_of_four_and_five_label_scales() -> None:
    four = Scale(type=ScaleType.ORDINAL, labels=b.FOUR)
    five = Scale(type=ScaleType.ORDINAL, labels=b.FIVE)
    assert svc.label_gap(four, "A", "D") == (Fraction(1), 3)
    assert svc.label_gap(four, "D", "A") == (Fraction(1), 3)
    assert svc.label_gap(four, "A", "B") == (Fraction(1, 3), 1)
    assert svc.label_gap(four, "D", "C") == (Fraction(1, 3), 1)
    assert svc.label_gap(four, "A", "A") == (Fraction(0), 0)
    assert svc.label_gap(five, "v1", "v5") == (Fraction(1), 4)
    assert svc.label_gap(five, "v1", "v2") == (Fraction(1, 4), 1)
    assert svc.label_gap(five, "v5", "v4") == (Fraction(1, 4), 1)
    assert svc.label_gap(five, "v5", "v5") == (Fraction(0), 0)
    one = Scale(type=ScaleType.ORDINAL, labels=["only"])
    assert svc.label_gap(one, "only", "only") == (Fraction(0), 0)


def test_a_categorical_mismatch_is_a_full_gap_without_steps() -> None:
    colours = Scale(type=ScaleType.CATEGORICAL, labels=b.COLOURS)
    assert svc.label_gap(colours, "red", "blue") == (Fraction(1), None)
    assert svc.label_gap(colours, "red", "green") == (Fraction(1), None)
    assert svc.label_gap(colours, "green", "green") == (Fraction(0), None)
    result = run(b.reference_set(b.case("a", {"cat": "blue", "o4": "A", "o5": "v1"})))
    match = result.alternatives[0].cases[0]
    further = {row.criterion_id: row for row in match.further}
    assert set(further) == {"cat"} and further["cat"].steps is None
    assert further["cat"].gap == "1/1" and not further["cat"].ordered


# ---- missing, threshold, weighting --------------------------------------------------------------


def test_the_hand_example_under_equal_and_profile_weighting() -> None:
    raw = b.reference_set(b.case("hand", HAND))
    equal = run(raw).alternatives[0].cases[0]
    # gaps o4 A..D = 1, o5 v1..v5 = 1, cat red = red 0; mean 2/3, similarity 1/3
    assert equal.similarity_exact == "1/3" and equal.similarity == pytest.approx(1 / 3)
    assert (equal.shared_count, equal.compared_count) == (3, 5)
    profile = run(raw, weighting="profile").alternatives[0].cases[0]
    # weights 1/8, 1/8, 2/8 renormalised over the three shared leaves: 1/4, 1/4, 1/2
    assert profile.similarity_exact == "1/2"


def test_missing_on_either_side_is_left_out_not_counted_as_zero_or_one() -> None:
    raw = b.reference_set(b.case("hand", HAND))
    match = run(raw).alternatives[0].cases[0]
    assert [(r.criterion_id, r.missing) for r in match.not_compared] == [
        ("o4b", "reference_case"),
        ("o5b", "reference_case"),
    ]
    assert all(r.gap is None and r.steps is None for r in match.not_compared)
    # y has no o4b, o5b or o4b/o5b ratings either: both sides missing, and o4 is the alternative's
    full = run(b.reference_set(b.case("full", FULL)), alternative_id="y").alternatives[0]
    rows = {r.criterion_id: r.missing for r in full.cases[0].not_compared}
    assert rows == {"o4b": "alternative", "o5b": "alternative"}
    both = run(b.reference_set(b.case("hand", HAND)), alternative_id="y").alternatives[0]
    assert {r.criterion_id: r.missing for r in both.cases[0].not_compared} == {
        "o4b": "both",
        "o5b": "both",
    }


def test_exactly_half_shared_is_comparable_and_just_under_is_not() -> None:
    four = AnalysisConfiguration(method="mavt", weight_profile_id="four")
    half = b.case("half", {"o4": "A", "o5": "v2"})  # 2 of the 4 compared leaves
    quarter = b.case("quarter", {"o4": "A"})  # 1 of 4
    result = run(b.reference_set(half, quarter), configuration=four).alternatives[0]
    assert [c.case_id for c in result.cases] == ["half"]
    assert [
        (n.case_id, n.shared_count, n.compared_count, n.shared_fraction)
        for n in result.not_comparable
    ] == [("quarter", 1, 4, "1/4")]
    # with five compared leaves (default profile), two shared is 2/5: below one half
    five = run(b.reference_set(half)).alternatives[0]
    assert five.cases == [] and five.not_comparable[0].shared_fraction == "2/5"
    # a stricter threshold, given as a fraction string
    strict = run(b.reference_set(half), configuration=four, min_shared_fraction="3/4")
    assert strict.alternatives[0].cases == [] and strict.min_shared_fraction == "3/4"


def test_nothing_shared_is_never_comparable_whatever_the_threshold() -> None:
    raw = b.reference_set(b.case("none", {}))
    result = run(raw, min_shared_fraction="1/1000").alternatives[0]
    assert result.cases == [] and result.not_comparable[0].shared_count == 0


def test_zero_weight_and_numeric_leaves_are_not_compared() -> None:
    raw = b.reference_set(b.case("z", {**HAND, "zero": "high"}))
    result = run(raw)
    assert result.compared_criteria == ["o4", "o5", "cat", "o4b", "o5b"]
    match = result.alternatives[0].cases[0]
    shown = {
        r.criterion_id
        for g in (match.same, match.one_step, match.further, match.not_compared)
        for r in g
    }
    assert "zero" not in shown and "num" not in shown
    assert match.similarity_exact == "1/3"  # unchanged by the zero-weight disagreement
    four = run(raw, configuration=AnalysisConfiguration(method="mavt", weight_profile_id="four"))
    assert four.compared_criteria == ["o4", "o5", "cat", "o4b"]


# ---- ordering and k -----------------------------------------------------------------------------


def test_an_exact_tie_breaks_on_shared_count_where_floats_would_reverse_it() -> None:
    # Both distances are exactly 5/12. Summed in floats, the five-leaf case comes out a hair
    # further (0.41666666666666674 against 0.41666666666666663), which would put it second.
    gaps_full = [Fraction(0), Fraction(0), Fraction(1), Fraction(1, 3), Fraction(3, 4)]
    gaps_part = [Fraction(0), Fraction(0), Fraction(2, 3), Fraction(1)]
    assert sum(gaps_full) / 5 == sum(gaps_part) / 4 == Fraction(5, 12)
    assert sum(float(g) for g in gaps_full) / 5 > sum(float(g) for g in gaps_part) / 4
    raw = b.reference_set(b.case("aa_partial", PARTIAL), b.case("zz_full", FULL))
    cases = run(raw).alternatives[0].cases
    assert [(c.case_id, c.similarity_exact, c.shared_count) for c in cases] == [
        ("zz_full", "7/12", 5),
        ("aa_partial", "7/12", 4),
    ]


def test_equal_similarity_and_shared_count_break_on_case_id() -> None:
    raw = b.reference_set(b.case("c2", HAND), b.case("c1", HAND), b.case("c3", HAND))
    assert [c.case_id for c in run(raw).alternatives[0].cases] == ["c1", "c2", "c3"]


def test_similarity_orders_first() -> None:
    raw = b.reference_set(
        b.case("far", HAND), b.case("near", {"o4": "A", "o5": "v2", "cat": "red"})
    )
    cases = run(raw).alternatives[0].cases
    assert [c.case_id for c in cases] == ["near", "far"]
    assert cases[0].similarity_exact == "11/12"  # gaps 0, 1/4, 0


def test_k_bounds_and_the_count_of_the_rest() -> None:
    raw = b.reference_set(*[b.case(f"c{i:02d}", HAND) for i in range(22)])
    assert len(run(raw, k=1).alternatives[0].cases) == 1
    assert run(raw, k=1).alternatives[0].remaining_count == 21
    top = run(raw, k=20).alternatives[0]
    assert len(top.cases) == 20 and top.remaining_count == 2
    default = run(raw).alternatives[0]
    assert len(default.cases) == 3 and default.remaining_count == 19
    for bad in (0, 21, -1):
        with pytest.raises(McdaError, match="k must be"):
            run(raw, k=bad)
    with pytest.raises(McdaError, match="weighting"):
        run(raw, weighting="weighted")
    for bad_fraction in ("0", "3/2", "half", "1/0"):
        with pytest.raises(McdaError, match="min_shared_fraction"):
            run(raw, min_shared_fraction=bad_fraction)


def test_groups_give_both_labels_and_steps() -> None:
    raw = b.reference_set(b.case("full", FULL))
    match = run(raw).alternatives[0].cases[0]
    assert [(r.criterion_id, r.alternative_label, r.case_label, r.steps) for r in match.same] == [
        ("o4", "A", "A", 0),
        ("o5", "v1", "v1", 0),
    ]
    assert [(r.criterion_id, r.steps, r.gap) for r in match.one_step] == [("o4b", 1, "1/3")]
    assert [(r.criterion_id, r.steps, r.gap) for r in match.further] == [
        ("cat", None, "1/1"),
        ("o5b", 3, "3/4"),
    ]
    assert match.same[0].case_note == "o4 note"
    assert match.context[0].value == "Context for full"


# ---- outcomes, scope and read-only behaviour ----------------------------------------------------


def test_outcomes_are_absent_by_default_and_present_on_request() -> None:
    raw = b.reference_set(b.case("a", HAND))
    project, reference = b.project(), b.load(raw)
    plain = svc.reference_cases(project, reference)
    assert plain.include_outcomes is False
    assert all(c.outcome is None for a in plain.alternatives for c in a.cases)
    assert "An outcome" not in plain.model_dump_json()
    shown = svc.reference_cases(project, reference, include_outcomes=True)
    outcome = shown.alternatives[0].cases[0].outcome
    assert outcome is not None and outcome.label == "An outcome" and outcome.claim_ids == ["c2"]


def test_every_alternative_by_default_and_an_unknown_one_is_refused() -> None:
    raw = b.reference_set(b.case("a", HAND))
    everyone = svc.reference_cases(b.project(), b.load(raw))
    assert [a.alternative_id for a in everyone.alternatives] == ["x", "y"]
    with pytest.raises(UnknownReferenceError):
        run(raw, alternative_id="nobody")


def test_the_fixed_label_and_limitations_are_in_every_result() -> None:
    result = run(b.reference_set(b.case("a", HAND)))
    assert "says nothing about how this alternative will turn out" in result.label
    assert "not representative" in result.label and "under-report" in result.label
    assert any("Numeric criteria are not compared" in x for x in result.limitations)
    assert any("knew the outcomes" in x for x in result.limitations)
    words = (result.label + " ".join(result.limitations)).lower()
    for word in ("startup", "round", "investor", "success", "failure", "pre-seed"):
        assert word not in words


def test_an_unknown_profile_is_unavailable_with_its_reason() -> None:
    raw = b.reference_set(b.case("a", HAND))
    bad = AnalysisConfiguration(method="mavt", weight_profile_id="nope")
    result = run(raw, configuration=bad)
    assert result.status == "unavailable" and "nope" in result.reason
    assert result.alternatives == []


def test_calling_the_analysis_changes_no_project_byte_fingerprint_or_etag() -> None:
    project = b.project()
    before_bytes = project.model_dump_json()
    before_fingerprint = project.fingerprint()
    raw = b.reference_set(b.case("a", HAND), b.case("b", FULL))
    reference = b.load(raw)
    reference_before = reference.model_dump_json()
    for kwargs in ({}, {"include_outcomes": True}, {"weighting": "profile"}):
        svc.reference_cases(project, reference, **kwargs)  # type: ignore[arg-type]
    svc.validate(project, reference)
    assert project.model_dump_json() == before_bytes
    assert project.fingerprint() == before_fingerprint  # the ETag is this fingerprint
    assert reference.model_dump_json() == reference_before


# ---- leaving out a case with the alternative's own id ------------------------------------------


def _ids(row: svc.AlternativeReferenceCases) -> list[str]:
    return [c.case_id for c in row.cases] + [c.case_id for c in row.not_comparable]


def test_a_case_sharing_the_alternatives_id_is_kept_by_default() -> None:
    raw = b.reference_set(b.case("x", FULL), b.case("a", HAND))
    result = svc.reference_cases(b.project(), b.load(raw))
    assert result.exclude_same_id is False
    assert all(row.excluded_case_ids == [] for row in result.alternatives)
    assert "x" in _ids(result.alternatives[0])


def test_exclude_same_id_leaves_out_only_that_alternatives_own_case() -> None:
    raw = b.reference_set(b.case("x", FULL), b.case("a", HAND), b.case("y", PARTIAL))
    project, reference = b.project(), b.load(raw)
    kept = svc.reference_cases(project, reference)
    left = svc.reference_cases(project, reference, exclude_same_id=True)
    assert left.exclude_same_id is True
    by_id = {row.alternative_id: row for row in left.alternatives}
    assert by_id["x"].excluded_case_ids == ["x"] and by_id["y"].excluded_case_ids == ["y"]
    assert "x" not in _ids(by_id["x"]) and "y" in _ids(by_id["x"])
    assert "y" not in _ids(by_id["y"]) and "x" in _ids(by_id["y"])
    # The remaining cases keep their exact similarity and relative order.
    for row_kept, row_left in zip(kept.alternatives, left.alternatives, strict=True):
        own = row_kept.alternative_id
        expected = [(c.case_id, c.similarity_exact) for c in row_kept.cases if c.case_id != own]
        assert [(c.case_id, c.similarity_exact) for c in row_left.cases] == expected


def test_an_own_case_too_thin_to_compare_is_excluded_not_listed_as_not_comparable() -> None:
    raw = b.reference_set(b.case("x", {"o4": "A"}), b.case("a", HAND))
    result = run(raw, exclude_same_id=True)
    row = result.alternatives[0]
    assert row.excluded_case_ids == ["x"]
    assert [c.case_id for c in row.not_comparable] == []
    assert row.remaining_count == 0


def test_exclude_same_id_changes_nothing_when_no_case_shares_an_id() -> None:
    raw = b.reference_set(b.case("a", HAND), b.case("b", FULL))
    project, reference = b.project(), b.load(raw)
    plain = svc.reference_cases(project, reference).model_dump()
    left = svc.reference_cases(project, reference, exclude_same_id=True).model_dump()
    assert left.pop("exclude_same_id") is True and plain.pop("exclude_same_id") is False
    assert left == plain
