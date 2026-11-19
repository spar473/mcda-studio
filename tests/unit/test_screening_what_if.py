"""Trials must equal a separately saved complete profile, with no changed source."""

from pathlib import Path

import pytest

from mcda_studio.domain.errors import ModelStructureError
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.services import results_service
from mcda_studio.services.screening_summary_service import screening_summary
from mcda_studio.services.screening_what_if_service import what_if_weights
from mcda_studio.storage.json_repository import JsonProjectRepository

repo = JsonProjectRepository()
STUDY = Path(__file__).parents[2] / "examples" / "nz_venture_screening"
ROOTS = ("team", "problem_solution", "market", "traction")


def saved_oracle(project, cfg, ratings, path: Path):  # type: ignore[no-untyped-def]
    # Independent path: construct the COMPLETE saved profile directly, without the
    # preview's immutable edit helper, then pass it through repository serialization.
    saved = project.model_copy(deep=True)
    profile_id = project.resolve_profile(cfg).id
    profile = next(profile for profile in saved.weight_profiles if profile.id == profile_id)
    profile.judgements = {**profile.judgements, **ratings}
    repo.save(saved, path)
    return repo.load(path)


@pytest.mark.parametrize("root", ROOTS)
@pytest.mark.parametrize("rating", [0.0, 137.12345678901235])
def test_each_root_equals_an_independently_saved_profile_exactly(
    root: str, rating: float, tmp_path: Path
) -> None:
    project = repo.load(STUDY / "project.json")
    cfg = AnalysisConfiguration(method="mavt_sorting", weight_profile_id="technical_ip")
    before = project.model_dump_json()
    response = what_if_weights(project, cfg, {root: rating})
    saved = saved_oracle(project, cfg, {root: rating}, tmp_path / "saved.json")
    assert (
        response.status == "available"
        and response.summary is not None
        and response.record is not None
    )
    assert response.summary.model_dump_json() == screening_summary(saved, cfg).model_dump_json()
    assert (
        response.record.model_dump_json()
        == results_service.analysis_record(saved, cfg).model_dump_json()
    )
    assert response.project_fingerprint == project.fingerprint()
    assert response.trial_project_fingerprint == saved.fingerprint()
    assert response.configuration == cfg and response.weight_profile_id == "technical_ip"
    assert [control.criterion_id for control in response.controls] == list(ROOTS)
    for control in response.controls:
        assert control.raw_rating == saved.resolve_profile(cfg).judgements[control.criterion_id]
        assert control.local_weight == response.record.result.local_weights[control.criterion_id]
        assert control.global_share == response.record.result.local_weights[control.criterion_id]
        assert control.step == "any" and control.slider_max >= control.raw_rating
    assert project.model_dump_json() == before
    # The oracle's COMPLETE profile retains every leaf judgement and every other profile.
    for source, actual in zip(project.weight_profiles, saved.weight_profiles, strict=True):
        assert actual.judgements == (
            {**source.judgements, root: rating}
            if source.id == "technical_ip"
            else source.judgements
        )


@pytest.mark.parametrize("profile", ["technical_ip", "commercial_traction"])
@pytest.mark.parametrize("scenario", [None, "linear_market_size"])
def test_profile_scenario_and_noninteger_uncapped_source_ratings_remain_exact(
    profile: str, scenario: str | None, tmp_path: Path
) -> None:
    project = repo.load(STUDY / "project.json")
    cfg = AnalysisConfiguration(method="mavt", weight_profile_id=profile, scenario_id=scenario)
    source = next(p for p in project.weight_profiles if p.id == profile)
    source.judgements["team"] = 250.12345678901235
    baseline = what_if_weights(project, cfg, {})
    assert baseline.status == "available"
    assert baseline.controls[0].raw_rating == 250.12345678901235
    assert baseline.controls[0].slider_max >= 250.12345678901235
    ratings = {
        "team": 301.2345678901234,
        "market": 0,
        "problem_solution": 50.75,
        "traction": 80.125,
    }
    trial = what_if_weights(project, cfg, ratings)
    saved = saved_oracle(project, cfg, ratings, tmp_path / "saved.json")
    assert trial.record is not None and trial.summary is not None
    assert (
        trial.record.model_dump_json()
        == results_service.analysis_record(saved, cfg).model_dump_json()
    )
    assert trial.summary.model_dump_json() == screening_summary(saved, cfg).model_dump_json()


def test_all_zero_is_unavailable_and_zero_controls_do_not_disappear() -> None:
    project = repo.load(STUDY / "project.json")
    response = what_if_weights(project, None, dict.fromkeys(ROOTS, 0.0))
    assert response.status == "unavailable" and response.reason
    assert (
        response.record is None
        and response.summary is None
        and response.trial_project_fingerprint is None
    )
    assert [control.criterion_id for control in response.controls] == list(ROOTS)
    assert all(
        control.raw_rating == 0 and control.local_weight is None and control.global_share is None
        for control in response.controls
    )


@pytest.mark.parametrize(
    "ratings",
    [
        {"mandate": 1},
        {"hq_country": 1},
        {"missing": 1},
        {"team": -1},
        {"team": True},
        {"team": float("nan")},
        {"team": float("inf")},
        {"team": "12"},
    ],
)
def test_invalid_or_unscored_rating_is_refused(ratings) -> None:  # type: ignore[no-untyped-def]
    project = repo.load(STUDY / "project.json")
    before = project.model_dump_json()
    with pytest.raises(ModelStructureError):
        what_if_weights(project, None, ratings)
    assert project.model_dump_json() == before


def test_other_methods_are_honestly_unavailable() -> None:
    project = repo.load(STUDY / "project.json")
    for method in ("smaa2", "promethee2", "ahp"):
        response = what_if_weights(project, AnalysisConfiguration(method=method), {})
        assert (
            response.status == "unavailable" and response.controls == [] and response.record is None
        )


def test_evaluable_only_child_without_a_profile_has_no_stated_rating_to_vary() -> None:
    from builders import scored_project

    project = scored_project({"a": 0.2, "b": 0.7})
    assert project.weight_profiles[0].judgements == {}
    before = project.model_dump_json()
    source = results_service.analysis_record(project)
    assert source.result.local_weights == {"score": 1.0}
    response = what_if_weights(project, None, {})
    assert response.status == "unavailable" and response.reason
    assert response.controls == [] and response.record is None and response.summary is None
    with pytest.raises(ModelStructureError, match="Only stated, baseline-weighted"):
        what_if_weights(project, None, {"score": 100})
    assert project.model_dump_json() == before
