"""Builds examples/clinic_site_selection/project.json and its gallery starter, using only the
public services API.

An invented AHP study (docs/design/clinic-site-selection-example.md): a small authority chooses a
site for a community health clinic from four candidate sites. The project states MAVT inputs
(two weight profiles) and, separately, AHP pairwise judgements. The two are different questions put
to the author, so neither is derived from the other and nothing is reconciled. Every name and
figure is invented. The 42 judgements are literal values below, each pair stored once as the entry
that is at least 1 (the favoured item first).

    python examples/clinic_site_selection/build.py
"""

import hashlib
import json
from pathlib import Path

from mcda_studio.domain.criteria import Direction, LinearValueFunction, QualitativeValueFunction
from mcda_studio.domain.pairwise import (
    AhpModel,
    AlternativeJudgements,
    CriteriaJudgements,
    PairwiseJudgement,
)
from mcda_studio.domain.preferences import WeightProfile
from mcda_studio.domain.project import Project
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.domain.starter_templates import StarterArtifact, StarterTemplate
from mcda_studio.services import project_service as ps
from mcda_studio.services import starter_template_service as starters
from mcda_studio.storage.json_repository import JsonProjectRepository

HERE = Path(__file__).parent
STARTER = HERE.parent / "starter_templates" / "clinic_site_selection"

#: alternative id -> (name, measurements by leaf id). The test oracle reads the project JSON, not
#: this table.
DATA: dict[str, tuple[str, dict[str, float | str]]] = {
    "town_centre": (
        "Town centre site",
        {
            "travel_time": 12.0,
            "bus_service": 8.0,
            "build_cost": 11.5,
            "running_cost": 520.0,
            "expansion": "none",
            "support": "high",
        },
    ),
    "hospital_grounds": (
        "Beside the hospital",
        {
            "travel_time": 18.0,
            "bus_service": 6.0,
            "build_cost": 9.0,
            "running_cost": 410.0,
            "expansion": "limited",
            "support": "medium",
        },
    ),
    "edge_of_town": (
        "Edge-of-town site",
        {
            "travel_time": 31.0,
            "bus_service": 2.0,
            "build_cost": 6.5,
            "running_cost": 480.0,
            "expansion": "ample",
            "support": "low",
        },
    ),
    "school_site": (
        "Shared school site",
        {
            "travel_time": 15.0,
            "bus_service": 4.0,
            "build_cost": 8.0,
            "running_cost": 390.0,
            "expansion": "limited",
            "support": "high",
        },
    ),
}

#: Raw swing ratings per profile, one per node, relative to its siblings. Judgements of the author.
ACCESS_LED = {
    "access": 100.0,
    "cost": 50.0,
    "fit": 30.0,
    "travel_time": 100.0,
    "bus_service": 60.0,
    "build_cost": 100.0,
    "running_cost": 70.0,
    "expansion": 60.0,
    "support": 100.0,
}
COST_LED = {
    "access": 55.0,
    "cost": 100.0,
    "fit": 25.0,
    "travel_time": 100.0,
    "bus_service": 60.0,
    "build_cost": 100.0,
    "running_cost": 90.0,
    "expansion": 60.0,
    "support": 100.0,
}

#: AHP judgements, (favoured item, other item, times as important or preferred, 1 to 9). These are
#: the author's separate pairwise answers; they read no measurement and no swing rating.
Judgement = tuple[str, str, float]
CRITERIA_JUDGEMENTS: list[tuple[str | None, list[Judgement]]] = [
    (None, [("access", "cost", 2.0), ("access", "fit", 3.0), ("cost", "fit", 2.0)]),
    ("access", [("travel_time", "bus_service", 2.0)]),
    ("cost", [("build_cost", "running_cost", 2.0)]),
    ("fit", [("support", "expansion", 2.0)]),
]
T, H, E, S = "town_centre", "hospital_grounds", "edge_of_town", "school_site"
SITE_JUDGEMENTS: list[tuple[str, list[Judgement]]] = [
    (
        "travel_time",
        [(T, S, 2.0), (T, H, 3.0), (T, E, 7.0), (S, H, 2.0), (S, E, 5.0), (H, E, 3.0)],
    ),
    (
        "bus_service",
        [(T, H, 2.0), (T, S, 3.0), (T, E, 7.0), (H, S, 2.0), (H, E, 5.0), (S, E, 3.0)],
    ),
    (
        "build_cost",
        [(E, S, 2.0), (E, H, 3.0), (E, T, 5.0), (S, H, 2.0), (S, T, 4.0), (H, T, 3.0)],
    ),
    (
        "running_cost",
        [(S, H, 1.0), (S, E, 3.0), (S, T, 5.0), (H, E, 2.0), (H, T, 4.0), (E, T, 2.0)],
    ),
    (
        "expansion",
        [(E, H, 5.0), (E, S, 5.0), (E, T, 9.0), (H, S, 1.0), (H, T, 4.0), (S, T, 4.0)],
    ),
    # The panel's answers on community support disagree with themselves: the town centre is judged
    # 3 times the hospital site and the hospital site 5 times the edge, yet the town centre only 9
    # times the edge, and the school site only 2 times the edge. This is the one matrix whose
    # consistency ratio is meant to exceed 0.10.
    (
        "support",
        [(T, S, 1.0), (T, H, 3.0), (T, E, 9.0), (S, H, 3.0), (S, E, 2.0), (H, E, 5.0)],
    ),
]


def _judgements(items: list[Judgement]) -> list[PairwiseJudgement]:
    return [PairwiseJudgement(row=r, column=c, value=v) for r, c, v in items]


def ahp_model() -> AhpModel:
    return AhpModel(
        criteria=[
            CriteriaJudgements(parent_id=parent, judgements=_judgements(items))
            for parent, items in CRITERIA_JUDGEMENTS
        ],
        alternatives=[
            AlternativeJudgements(criterion_id=leaf, judgements=_judgements(items))
            for leaf, items in SITE_JUDGEMENTS
        ],
    )


def build_project() -> Project:
    p = ps.new_project(
        "Clinic site selection (example)",
        description=(
            "Invented AHP example: four candidate sites for a community health clinic, read "
            "through AHP pairwise judgements and, separately, MAVT swing weights. All names and "
            "figures are invented."
        ),
        decision_maker="Planning team",
    )
    p = p.model_copy(update={"id": "clinic_site_selection_example"})  # fixed id: reproducible file
    for alt_id, (name, _) in DATA.items():
        p = ps.add_alternative(p, name, alt_id=alt_id)

    ratio = ScaleType.RATIO
    ordinal = ScaleType.ORDINAL
    p = ps.add_criterion(p, "Access", crit_id="access")
    p = ps.add_criterion(
        p,
        "Median travel time for the people served",
        "access",
        "travel_time",
        scale=Scale(type=ratio, unit="min", lower=5.0, upper=40.0),
        value_function=LinearValueFunction(direction=Direction.DECREASING),
    )
    p = ps.add_criterion(
        p,
        "Bus services per hour at the site",
        "access",
        "bus_service",
        scale=Scale(type=ratio, unit="services/h", lower=0.0, upper=10.0),
        value_function=LinearValueFunction(),
    )

    p = ps.add_criterion(p, "Cost", crit_id="cost")
    p = ps.add_criterion(
        p,
        "Land and build cost",
        "cost",
        "build_cost",
        scale=Scale(type=ratio, unit="NZD m", lower=5.0, upper=14.0),
        value_function=LinearValueFunction(direction=Direction.DECREASING),
    )
    p = ps.add_criterion(
        p,
        "Annual running cost",
        "cost",
        "running_cost",
        scale=Scale(type=ratio, unit="NZD k/year", lower=300.0, upper=700.0),
        value_function=LinearValueFunction(direction=Direction.DECREASING),
    )

    p = ps.add_criterion(p, "Fit", crit_id="fit")
    p = ps.add_criterion(
        p,
        "Room to expand",
        "fit",
        "expansion",
        scale=Scale(type=ordinal, labels=["none", "limited", "ample"]),
        value_function=QualitativeValueFunction(
            mapping={"none": 0.0, "limited": 0.5, "ample": 1.0}
        ),
    )
    p = ps.add_criterion(
        p,
        "Community support",
        "fit",
        "support",
        scale=Scale(type=ordinal, labels=["low", "medium", "high"]),
        value_function=QualitativeValueFunction(mapping={"low": 0.0, "medium": 0.6, "high": 1.0}),
    )

    for alt_id, (_, measures) in DATA.items():
        for leaf, value in measures.items():
            p = ps.set_performance(p, alt_id, leaf, value)
    for node, rating in ACCESS_LED.items():
        p = ps.set_judgement(p, node, rating)
    p = ps.rename_weight_profile(p, ps.DEFAULT_PROFILE_ID, "Access-led")
    p = ps.add_weight_profile(
        p, WeightProfile(id="cost_led", name="Cost-led", judgements=dict(COST_LED))
    )
    p = ps.set_ahp_model(p, ahp_model())
    return ps.set_analysis_method(p, "ahp")


def write_starter(project_bytes: bytes) -> None:
    """The gallery card: the project alone, hash-checked by the existing starter loader."""
    STARTER.mkdir(parents=True, exist_ok=True)
    (STARTER / "project.json").write_bytes(project_bytes)
    manifest = StarterTemplate(
        id="clinic_site_selection",
        version="1",
        title="Clinic site selection",
        description=(
            "Invented AHP example: four candidate clinic sites, six criteria, 42 pairwise "
            "judgements (one matrix deliberately a little inconsistent) and, separately, two MAVT "
            "weight profiles. All names and figures are invented."
        ),
        source_example="examples/clinic_site_selection",
        source_version="1",
        tasks=[
            "Read each site's AHP priority and the consistency of every matrix",
            "Open the one inconsistent matrix and its most inconsistent triad",
            "Compare AHP priorities with the MAVT ranking under each profile",
        ],
        artifacts=[
            StarterArtifact(
                id="project",
                path="project.json",
                kind="project",
                schema_version=json.loads(project_bytes)["schema_version"],
                sha256=hashlib.sha256(project_bytes).hexdigest(),
                optional=False,
                reset_policy="draft",
                for_model=None,
                label="Project",
            )
        ],
        digest="",
    )
    manifest.digest = starters.template_digest(manifest)
    (STARTER / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    project = build_project()
    JsonProjectRepository().save(project, HERE / "project.json")
    write_starter((HERE / "project.json").read_bytes())
    print(f"wrote {HERE / 'project.json'} and the starter in {STARTER}")


if __name__ == "__main__":
    main()
