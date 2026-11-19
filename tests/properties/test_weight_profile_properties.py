"""Independent hierarchical products and randomized profile/reference isolation checks."""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mcda_studio.domain.criteria import CriterionNode
from mcda_studio.domain.preferences import Scenario
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps

from builders import tiny_project


@settings(max_examples=70, deadline=None)
@given(
    depth=st.integers(1, 9),
    ratings=st.lists(st.tuples(st.integers(0, 1000), st.integers(0, 1000)), min_size=9, max_size=9),
)
def test_arbitrary_depth_weights_match_independent_chain_products_with_missing_measurements(
    depth, ratings
):
    p = ps.new_project("Deep tree")
    p.criteria = [CriterionNode(id="g0", name="G0")]
    judgements = {}
    expected = {}
    survival = 1.0
    invalid = False
    for i in range(depth):
        a, b = ratings[i]
        group = f"g{i}"
        leaf = f"l{i}"
        next_id = f"g{i + 1}" if i + 1 < depth else "tail"
        p.criteria.extend(
            [
                CriterionNode(id=leaf, name=leaf, parent_id=group, order=0),
                CriterionNode(id=next_id, name=next_id, parent_id=group, order=1),
            ]
        )
        judgements.update({leaf: a, next_id: b})
        if a + b == 0:
            invalid = True
        else:
            expected[leaf] = survival * a / (a + b)
            survival *= b / (a + b)
    expected["tail"] = survival
    p.weight_profiles[0].judgements = judgements
    before = p.model_dump_json()
    result = svc.preview_weights(p)
    assert p.model_dump_json() == before and p.performances == []
    if invalid:
        assert not result.weights_ready and result.local_weights == result.global_weights == {}
        assert result.path_shares == {}
    else:
        assert result.weights_ready and result.global_weights == pytest.approx(expected, abs=1e-12)
        assert math.fsum(result.global_weights.values()) == pytest.approx(1, abs=1e-12)
        assert result.local_weights["g0"] == 1 and "g0" not in p.weight_profiles[0].judgements
        assert all(r.readiness == "incomplete" for r in result.swing_ranges.values())
        # Branch shares explain the same arithmetic: leaves repeat the global weights, and every
        # group divides its own parent's share rather than the whole goal.
        shares = result.path_shares
        assert {k: shares[k] for k in result.global_weights} == result.global_weights
        assert shares["g0"] == pytest.approx(1, abs=1e-12)
        for i in range(depth):
            kids = [f"l{i}", f"g{i + 1}" if i + 1 < depth else "tail"]
            assert math.fsum(shares[k] for k in kids) == pytest.approx(shares[f"g{i}"], abs=1e-12)


@settings(max_examples=70, deadline=None)
@given(
    rating=st.integers(0, 10000),
    saved=st.sampled_from([None, "default", "other"]),
    refs=st.lists(st.sampled_from([None, "default", "other"]), min_size=0, max_size=8),
)
def test_duplicate_edit_and_delete_preserve_independent_profiles_and_reference_closure(
    rating, saved, refs
):
    p = ps.duplicate_weight_profile(tiny_project(), "default", "Other", "other")
    p.analysis.weight_profile_id = saved
    for i, profile in enumerate(refs):
        p = ps.add_scenario(p, Scenario(id=f"s{i}", name=f"S{i}", weight_profile_id=profile))
    before = p.fingerprint()
    q = ps.set_judgement(p, "cost", rating, "other")
    assert p.weight_profiles[0].judgements == q.weight_profiles[0].judgements
    assert p.fingerprint() == before
    r = ps.remove_weight_profile(q, "default", "other")
    assert all(s.weight_profile_id == "other" for s in r.scenarios)
    assert r.analysis.weight_profile_id == "other"
    assert len(r.weight_profiles) == 1 and r.weight_profiles[0].judgements["cost"] == rating
    assert (
        q.weight_profiles[0].id == "default"
        and q.weight_profiles[0].judgements == p.weight_profiles[0].judgements
    )
