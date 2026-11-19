"""Reference cases against an independent oracle.

The oracle (``tests/regression/reference_cases_oracle.py``) never imports the application. The
service agrees with it exactly (fractions, not floats) on hand-built cases under both weightings
and both profiles, and on generated reference sets full of ties and missing ratings.
"""

import json
import random
from fractions import Fraction
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from reference_cases_oracle import compare as oracle

import reference_case_builders as b
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.services import reference_case_service as svc

HAND = {"o4": "D", "o5": "v5", "cat": "red"}
FULL = {"o4": "A", "o5": "v1", "cat": "green", "o4b": "B", "o5b": "v4"}
PARTIAL = {"o5": "v1", "cat": "red", "o4b": "C", "o5b": "v5"}
LABELS = {"o4": b.FOUR, "o5": b.FIVE, "cat": b.COLOURS, "o4b": b.FOUR, "o5b": b.FIVE}


def _agree(
    raw: dict[str, Any],
    alternative: str,
    weighting: str,
    profile: str | None,
    k: int,
    threshold: str = "1/2",
    exclude_same_id: bool = False,
) -> None:
    project = b.project()
    cfg = AnalysisConfiguration(method="mavt", weight_profile_id=profile)
    result = svc.reference_cases(
        project,
        b.load(raw),
        cfg,
        alternative,
        k=k,
        weighting=weighting,  # type: ignore[arg-type]
        min_shared_fraction=threshold,
        exclude_same_id=exclude_same_id,
    )
    expected = oracle(
        json.loads(project.model_dump_json()),
        raw,
        alternative,
        profile_id=profile,
        k=k,
        weighting=weighting,
        min_shared=Fraction(threshold),
        exclude_same_id=exclude_same_id,
    )
    got = result.alternatives[0]
    assert got.excluded_case_ids == expected["excluded"]
    assert result.compared_criteria == expected["compared"]
    assert [
        {
            "case_id": c.case_id,
            "similarity": Fraction(c.similarity_exact),
            "shared": c.shared_count,
            "same": [r.criterion_id for r in c.same],
            "one_step": [r.criterion_id for r in c.one_step],
            "further": [r.criterion_id for r in c.further],
        }
        for c in got.cases
    ] == expected["top"]
    assert all(c.similarity == float(Fraction(c.similarity_exact)) for c in got.cases)
    assert got.remaining_count == expected["remaining"]
    assert [(n.case_id, n.shared_count, n.compared_count) for n in got.not_comparable] == expected[
        "not_comparable"
    ]


@pytest.mark.parametrize("weighting", ["equal", "profile"])
@pytest.mark.parametrize("profile", [None, "four"])
@pytest.mark.parametrize("alternative", ["x", "y"])
def test_the_service_agrees_with_the_oracle_on_hand_built_cases(
    weighting: str, profile: str | None, alternative: str
) -> None:
    raw = b.reference_set(
        b.case("hand", HAND),
        b.case("zz_full", FULL),
        b.case("aa_partial", PARTIAL),
        b.case("c1", {"o4": "B", "o5": "v3", "cat": "blue", "o4b": "D"}),
        b.case("c2", {"o4": "C", "cat": "green", "o5b": "v2"}),
        b.case("c3", {"o5": "v5"}),
    )
    _agree(raw, alternative, weighting, profile, k=4)


def _random_set(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    cases = []
    for i in range(rng.randint(1, 9)):
        labels = {
            leaf: rng.choice(options) for leaf, options in LABELS.items() if rng.random() < 0.7
        }
        # repeat an earlier case's ratings sometimes, so exact ties are common
        if cases and rng.random() < 0.3:
            labels = {r["criterion_id"]: r["label"] for r in rng.choice(cases)["ratings"]}
        cases.append(b.case(f"case{rng.randint(0, 99):02d}_{i}", labels))
    return b.reference_set(*cases)


@settings(max_examples=80, deadline=None)
@given(
    st.integers(0, 2**31),
    st.sampled_from(["equal", "profile"]),
    st.sampled_from([None, "four"]),
    st.sampled_from(["x", "y"]),
    st.integers(1, 20),
    st.sampled_from(["1/2", "1/4", "3/5", "1/1"]),
)
def test_generated_sets_agree_with_the_oracle(
    seed: int, weighting: str, profile: str | None, alternative: str, k: int, threshold: str
) -> None:
    _agree(_random_set(seed), alternative, weighting, profile, k, threshold)


@pytest.mark.parametrize("exclude", [False, True])
@pytest.mark.parametrize("alternative", ["x", "y"])
def test_leaving_out_the_own_case_agrees_with_the_oracle(alternative: str, exclude: bool) -> None:
    raw = b.reference_set(
        b.case("x", FULL),
        b.case("y", PARTIAL),
        b.case("hand", HAND),
        b.case("c1", {"o4": "B", "o5": "v3", "cat": "blue", "o4b": "D"}),
    )
    _agree(raw, alternative, "equal", None, k=4, exclude_same_id=exclude)


@settings(max_examples=60, deadline=None)
@given(
    st.integers(0, 2**31),
    st.sampled_from(["equal", "profile"]),
    st.sampled_from(["x", "y"]),
    st.integers(1, 20),
    st.booleans(),
)
def test_generated_sets_with_own_cases_agree_with_the_oracle(
    seed: int, weighting: str, alternative: str, k: int, exclude: bool
) -> None:
    rng = random.Random(seed)
    raw = _random_set(seed)
    for own in ("x", "y"):
        labels = {
            leaf: rng.choice(options) for leaf, options in LABELS.items() if rng.random() < 0.7
        }
        raw["cases"].append(b.case(own, labels))
    _agree(raw, alternative, weighting, None, k, exclude_same_id=exclude)


def test_the_generated_corpus_contains_ties_and_not_comparable_cases() -> None:
    ties = not_comparable = 0
    for seed in range(60):
        raw = _random_set(seed)
        result = svc.reference_cases(b.project(), b.load(raw), alternative_id="x", k=20)
        similarities = [c.similarity_exact for c in result.alternatives[0].cases]
        ties += len(similarities) - len(set(similarities))
        not_comparable += len(result.alternatives[0].not_comparable)
    assert ties > 10 and not_comparable > 10
