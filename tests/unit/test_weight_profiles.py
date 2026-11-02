"""Profile lifecycle, explicit/automatic reference protection, isolation and non-mutation."""

import pytest

from mcda_studio.domain.errors import ModelEditError, UnknownReferenceError
from mcda_studio.domain.preferences import Scenario, WeightProfile
from mcda_studio.services import project_service as ps

from builders import tiny_project


def two_profiles():
    return ps.duplicate_weight_profile(tiny_project(), "default", "Other", "other")


def test_create_has_no_imputed_ratings_and_deterministic_collision_safe_ids():
    p = tiny_project()
    before = p.fingerprint()
    q = ps.create_weight_profile(p, "  New analyst  ")
    assert q.weight_profiles[-1].id == "new_analyst"
    assert q.weight_profiles[-1].name == "New analyst" and q.weight_profiles[-1].judgements == {}
    assert ps.create_weight_profile(q, "New analyst").weight_profiles[-1].id == "new_analyst_2"
    assert ps.create_weight_profile(p, "New analyst").fingerprint() == q.fingerprint()
    assert q.analysis == p.analysis and p.fingerprint() == before
    assert q.schema_version == p.schema_version


def test_duplicate_and_rename_keep_original_profile_isolated_and_ids_stable():
    p = tiny_project()
    before = p.model_dump_json()
    q = ps.duplicate_weight_profile(p, "default", "Second analyst", "second")
    assert q.weight_profiles[0].judgements == q.weight_profiles[1].judgements
    q = ps.set_judgement(q, "cost", 240, "second")
    assert q.weight_profiles[0].judgements == p.weight_profiles[0].judgements
    renamed = ps.rename_weight_profile(q, "second", "New display name")
    assert renamed.weight_profiles[1].id == "second"
    assert renamed.weight_profiles[1].judgements == q.weight_profiles[1].judgements
    renamed.weight_profiles[1].judgements["cost"] = 999
    assert q.weight_profiles[1].judgements["cost"] == 240
    assert p.model_dump_json() == before


@pytest.mark.parametrize("name", ["", " ", "\t\n"])
def test_blank_names_are_refused_without_mutation(name):
    p = two_profiles()
    before = p.fingerprint()
    for operation in [
        lambda: ps.create_weight_profile(p, name),
        lambda: ps.duplicate_weight_profile(p, "default", name),
        lambda: ps.rename_weight_profile(p, "other", name),
    ]:
        with pytest.raises(ModelEditError):
            operation()
        assert p.fingerprint() == before


def test_last_profile_and_unknown_or_same_replacements_are_refused():
    with pytest.raises(ModelEditError, match="last"):
        ps.remove_weight_profile(tiny_project(), "default")
    p = two_profiles()
    before = p.fingerprint()
    with pytest.raises(ModelEditError, match="different"):
        ps.remove_weight_profile(p, "default", "default")
    with pytest.raises(UnknownReferenceError):
        ps.remove_weight_profile(p, "default", "absent")
    with pytest.raises(UnknownReferenceError):
        ps.remove_weight_profile(p, "absent", "other")
    assert p.fingerprint() == before


def test_referenced_profile_requires_replacement_for_explicit_and_automatic_references():
    p = ps.add_scenario(two_profiles(), Scenario(id="auto", name="Automatic"))
    p = ps.add_scenario(p, Scenario(id="explicit", name="Explicit", weight_profile_id="default"))
    p.analysis.parameters = {"nested": {"unchanged": [1, 2]}}
    assert set(ps.weight_profile_references(p, "default")) == {
        "analysis.weight_profile_id",
        "scenarios[auto].weight_profile_id",
        "scenarios[explicit].weight_profile_id",
    }
    before = p.fingerprint()
    with pytest.raises(ModelEditError, match="explicit replacement"):
        ps.remove_weight_profile(p, "default")
    q = ps.remove_weight_profile(p, "default", "other")
    assert [x.id for x in q.weight_profiles] == ["other"]
    assert q.analysis.weight_profile_id == "other"
    assert all(s.weight_profile_id == "other" for s in q.scenarios)
    assert q.analysis.parameters == p.analysis.parameters and p.fingerprint() == before
    assert q.criteria == p.criteria and q.performances == p.performances


def test_saved_scenario_resolution_and_unreferenced_deletion_do_not_change_other_references():
    p = ps.add_scenario(two_profiles(), Scenario(id="s", name="S", weight_profile_id="other"))
    p.analysis.scenario_id = "s"
    assert ps.weight_profile_references(p, "other") == [
        "scenarios[s].weight_profile_id",
        "analysis.weight_profile_id",
    ]
    q = ps.remove_weight_profile(p, "default")
    assert q.analysis == p.analysis and q.scenarios == p.scenarios
    assert q.weight_profiles[0].id == "other"
    r = ps.remove_weight_profile(p, "other", "default")
    assert r.analysis.scenario_id == "s" and r.analysis.weight_profile_id == "default"
    assert r.scenarios[0].weight_profile_id == "default"


def test_explicit_saved_default_is_an_isolated_targeted_change():
    p = two_profiles()
    p.analysis.parameters = {"nested": {"p": True}}
    q = ps.set_default_weight_profile(p, "other")
    assert q.analysis.weight_profile_id == "other" and p.analysis.weight_profile_id is None
    assert q.analysis.parameters == p.analysis.parameters
    assert ps.set_default_weight_profile(q, None).fingerprint() == p.fingerprint()
    with pytest.raises(UnknownReferenceError):
        ps.set_default_weight_profile(p, "missing")


def test_collision_and_ambiguous_profile_edits_are_refused():
    p = two_profiles()
    with pytest.raises(ModelEditError):
        ps.create_weight_profile(p, "Collision", "default")
    with pytest.raises(ModelEditError):
        ps.duplicate_weight_profile(p, "default", "Collision", "default")
    p.weight_profiles.append(WeightProfile(id="default", name="Duplicate"))
    with pytest.raises(ModelEditError, match="ambiguous"):
        ps.remove_weight_profile(p, "default", "other")
    with pytest.raises(ModelEditError, match="ambiguous"):
        ps.create_weight_profile(p, "new")


def test_a_duplicate_shares_no_mutable_state_with_its_source_or_the_input():
    """Pin the isolation *invariant*, not the mechanism that currently provides it.

    Three independent barriers make a duplicate independent today: the deep copy in
    `duplicate_weight_profile`, a second deep copy in `add_weight_profile`, and the
    `model_validate(model_dump())` round trip in `_rebuild`. Any one of them is enough, which is
    why mutating a single barrier is an equivalent mutant. This test holds the property itself, so
    it still fails if all of them are removed.
    """
    p = tiny_project()
    before = p.model_dump_json()
    q = ps.duplicate_weight_profile(p, "default", "Copy", "copy")
    source = next(x for x in q.weight_profiles if x.id == "default")
    clone = next(x for x in q.weight_profiles if x.id == "copy")
    assert clone.judgements == source.judgements
    # No shared containers, inside the result or back to the caller's project.
    assert clone.judgements is not source.judgements
    assert clone.judgements is not p.weight_profiles[0].judgements
    assert source.judgements is not p.weight_profiles[0].judgements
    # Writing straight into the returned model moves nothing else.
    clone.judgements["cost"] = 12345.0
    assert source.judgements["cost"] == 100.0
    assert p.weight_profiles[0].judgements["cost"] == 100.0
    assert p.model_dump_json() == before
