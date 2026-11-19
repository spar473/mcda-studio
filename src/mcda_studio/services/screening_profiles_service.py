"""Two existing MAVT screening readings, with engine ranks kept separate."""

from mcda_studio.domain.common import DomainModel, Id
from mcda_studio.domain.errors import ModelStructureError
from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.services.screening_summary_service import ScreeningSummary, screening_summary


class ProfileScreening(DomainModel):
    profile_id: Id
    name: str
    summary: ScreeningSummary


class ProfileMovement(DomainModel):
    alternative_id: Id
    from_profile_id: Id
    to_profile_id: Id
    from_rank: int
    to_rank: int
    places_changed: int
    emphasize: bool
    line_class_id: Id | None


class ProfileComparison(DomainModel):
    project_fingerprint: str
    configuration: AnalysisConfiguration
    scenario_id: Id | None
    profiles: list[ProfileScreening]
    movements: list[ProfileMovement]


def compare_profiles(
    project: Project,
    configuration: AnalysisConfiguration | None,
    profile_ids: list[str],
    dossier: EvidenceDossier | None = None,
) -> ProfileComparison:
    # The comparison is between any two profiles in the project. Keeping the request to
    # exactly two bounds it to the two existing-summary computations shown by this view.
    if len(profile_ids) != 2 or len(set(profile_ids)) != 2:
        raise ModelStructureError("Choose two distinct weight profiles.")
    profiles = {profile.id: profile for profile in project.weight_profiles}
    if any(profile_id not in profiles for profile_id in profile_ids):
        raise ModelStructureError("A requested weight profile does not exist.")
    requested = (configuration or project.analysis).model_copy(deep=True)
    readings = [
        ProfileScreening(
            profile_id=profile_id,
            name=profiles[profile_id].name,
            summary=screening_summary(
                project,
                requested.model_copy(update={"weight_profile_id": profile_id}),
                dossier,
            ),
        )
        for profile_id in profile_ids
    ]
    left, right = readings
    movements = []
    if left.summary.status == right.summary.status == "available":
        right_rows = {row.alternative_id: row for row in right.summary.rows}
        for row in left.summary.rows:
            other = right_rows[row.alternative_id]
            change = row.rank - other.rank  # positive means moving up in the right profile
            movements.append(
                ProfileMovement(
                    alternative_id=row.alternative_id,
                    from_profile_id=left.profile_id,
                    to_profile_id=right.profile_id,
                    from_rank=row.rank,
                    to_rank=other.rank,
                    places_changed=change,
                    emphasize=abs(change) >= 2,
                    line_class_id=row.class_id,
                )
            )
    return ProfileComparison(
        project_fingerprint=project.fingerprint(),
        configuration=requested,
        scenario_id=requested.scenario_id,
        profiles=readings,
        movements=movements,
    )
