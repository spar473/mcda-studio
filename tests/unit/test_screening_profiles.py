"""Independent existing summaries remain exact under a two-profile comparison."""

from pathlib import Path

import pytest

from mcda_studio.domain.errors import ModelStructureError
from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.services.screening_profiles_service import compare_profiles
from mcda_studio.services.screening_summary_service import screening_summary
from mcda_studio.storage.json_repository import JsonProjectRepository

repo = JsonProjectRepository()
STUDY = Path(__file__).parents[2] / "examples" / "nz_venture_screening"


def test_profile_comparison_preserves_each_existing_summary_and_source_exactly() -> None:
    project = repo.load(STUDY / "project.json")
    dossier = EvidenceDossier.model_validate_json((STUDY / "evidence.json").read_text())
    before, evidence_before = project.model_dump_json(), dossier.model_dump_json()
    for scenario in (None, "linear_market_size"):
        cfg = AnalysisConfiguration(method="mavt_sorting", scenario_id=scenario)
        for ids in (
            ["technical_ip", "commercial_traction"],
            ["commercial_traction", "technical_ip"],
        ):
            comparison = compare_profiles(project, cfg, ids, dossier)
            assert comparison.project_fingerprint == project.fingerprint()
            assert comparison.configuration == cfg and comparison.scenario_id == scenario
            assert [reading.profile_id for reading in comparison.profiles] == ids
            for reading in comparison.profiles:
                assert reading.name == next(
                    profile.name
                    for profile in project.weight_profiles
                    if profile.id == reading.profile_id
                )
                expected = screening_summary(
                    project,
                    cfg.model_copy(update={"weight_profile_id": reading.profile_id}),
                    dossier,
                )
                assert reading.summary.model_dump_json() == expected.model_dump_json()
            left, right = comparison.profiles
            by_right = {row.alternative_id: row for row in right.summary.rows}
            assert [movement.alternative_id for movement in comparison.movements] == [
                row.alternative_id for row in left.summary.rows
            ]
            for row, movement in zip(left.summary.rows, comparison.movements, strict=True):
                other = by_right[row.alternative_id]
                assert (movement.from_profile_id, movement.to_profile_id) == tuple(ids)
                assert (movement.from_rank, movement.to_rank) == (row.rank, other.rank)
                assert movement.places_changed == row.rank - other.rank
                assert movement.emphasize == (abs(row.rank - other.rank) >= 2)
                assert movement.line_class_id == row.class_id
    assert project.model_dump_json() == before
    assert dossier.model_dump_json() == evidence_before


def test_any_two_profiles_and_explicit_scenario_override_keep_requested_order() -> None:
    project = repo.load(STUDY / "project.json")
    extra = project.weight_profiles[0].model_copy(
        deep=True, update={"id": "third", "name": "A third partner"}
    )
    project.weight_profiles.append(extra)
    project.scenarios[0].weight_profile_id = "technical_ip"
    cfg = AnalysisConfiguration(method="mavt", scenario_id="linear_market_size")
    result = compare_profiles(project, cfg, ["third", "commercial_traction"])
    assert [reading.profile_id for reading in result.profiles] == ["third", "commercial_traction"]
    assert [reading.summary.weight_profile_id for reading in result.profiles] == [
        "third",
        "commercial_traction",
    ]
    assert all(reading.summary.scenario_id == "linear_market_size" for reading in result.profiles)


def test_unavailable_readings_have_no_movements_or_substituted_ranking() -> None:
    project = repo.load(STUDY / "project.json")
    project.performances.pop()
    before = project.model_dump_json()
    result = compare_profiles(project, None, ["technical_ip", "commercial_traction"])
    assert result.movements == []
    for reading in result.profiles:
        assert reading.summary.status == "unavailable" and reading.summary.reason
        assert reading.summary.rows == []
    assert project.model_dump_json() == before


def test_tied_engine_competition_ranks_are_not_replaced_by_display_positions() -> None:
    project = repo.load(STUDY / "project.json")
    first = project.alternatives[0].id
    values = {
        performance.criterion_id: performance.value
        for performance in project.performances
        if performance.alternative_id == first
    }
    for performance in project.performances:
        performance.value = values[performance.criterion_id]
    result = compare_profiles(project, None, ["technical_ip", "commercial_traction"])
    assert all(
        [row.rank for row in reading.summary.rows] == [1] * len(project.alternatives)
        for reading in result.profiles
    )
    assert all(
        movement.places_changed == 0 and not movement.emphasize for movement in result.movements
    )


@pytest.mark.parametrize(
    "ids",
    [
        [],
        ["technical_ip"],
        ["technical_ip", "technical_ip"],
        ["technical_ip", "missing"],
        ["technical_ip", "commercial_traction", "technical_ip"],
    ],
)
def test_invalid_profile_pair_is_refused(ids: list[str]) -> None:
    project = repo.load(STUDY / "project.json")
    with pytest.raises(ModelStructureError):
        compare_profiles(project, None, ids)
