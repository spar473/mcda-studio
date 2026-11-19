"""Builds examples/flood_defence_options/project.json and its gallery starter, using only the
public services API.

An invented feasibility and PROMETHEE II study (docs/design/flood-defence-options-example.md): a
small coastal town compares five ways of reducing flood risk. One measurement is a hard requirement
that no score may offset. The project states MAVT inputs (two weight profiles), two requirements
and, separately, PROMETHEE II's own weights, directions and preference functions. They are different
questions put to the author, so none is derived from another. Every name and figure is invented.

    python examples/flood_defence_options/build.py
"""

import hashlib
import json
from pathlib import Path

from mcda_studio.domain.criteria import Direction, LinearValueFunction, QualitativeValueFunction
from mcda_studio.domain.outranking import (
    LinearPreferenceFunction,
    PrometheeCriterion,
    PrometheeModel,
    UShapeFunction,
    UsualFunction,
    VShapeFunction,
)
from mcda_studio.domain.preferences import WeightProfile
from mcda_studio.domain.project import Project
from mcda_studio.domain.requirements import BoundRequirement, LabelsRequirement
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.domain.starter_templates import StarterArtifact, StarterTemplate
from mcda_studio.services import project_service as ps
from mcda_studio.services import starter_template_service as starters
from mcda_studio.storage.json_repository import JsonProjectRepository

HERE = Path(__file__).parent
STARTER = HERE.parent / "starter_templates" / "flood_defence_options"

#: alternative id -> (name, measurements by leaf id). The test oracles read the project JSON, not
#: this table.
DATA: dict[str, tuple[str, dict[str, float | str]]] = {
    "sea_wall": (
        "Raised sea wall",
        {
            "protection_standard": 200.0,
            "residual_risk": "medium",
            "capital_cost": 42.0,
            "maintenance_cost": 9.0,
            "habitat": 3.2,
            "consent": "contested",
            "disruption": 18.0,
        },
    ),
    "dune_pumping": (
        "Dune restoration with pumping",
        {
            "protection_standard": 100.0,
            "residual_risk": "medium",
            "capital_cost": 24.0,
            "maintenance_cost": 22.0,
            "habitat": 0.4,
            "consent": "notified",
            "disruption": 9.0,
        },
    ),
    "gates_road": (
        "Flood gates and raised road",
        {
            "protection_standard": 150.0,
            "residual_risk": "low",
            "capital_cost": 31.0,
            "maintenance_cost": 15.0,
            "habitat": 1.1,
            "consent": "notified",
            "disruption": 14.0,
        },
    ),
    "managed_retreat": (
        "Managed retreat of the lowest street",
        {
            "protection_standard": 120.0,
            "residual_risk": "low",
            "capital_cost": 18.5,
            "maintenance_cost": 4.0,
            "habitat": 0.8,
            "consent": "not consentable",
            "disruption": 10.0,
        },
    ),
    "maintain_existing": (
        "Maintain the existing defences",
        {
            "protection_standard": 25.0,
            "residual_risk": "high",
            "capital_cost": 3.0,
            "maintenance_cost": 28.0,
            "habitat": 0.2,
            "consent": "routine",
            "disruption": 1.0,
        },
    ),
}

#: Raw swing ratings per profile, one per node, relative to its siblings. Judgements of the author.
SAFETY_FIRST = {
    "protection": 100.0,
    "cost": 40.0,
    "environment": 30.0,
    "protection_standard": 100.0,
    "residual_risk": 60.0,
    "capital_cost": 100.0,
    "maintenance_cost": 70.0,
    "habitat": 100.0,
    "consent": 80.0,
    "disruption": 40.0,
}
COST_CONSCIOUS = {
    "protection": 60.0,
    "cost": 100.0,
    "environment": 40.0,
    "protection_standard": 100.0,
    "residual_risk": 60.0,
    "capital_cost": 100.0,
    "maintenance_cost": 90.0,
    "habitat": 80.0,
    "consent": 70.0,
    "disruption": 60.0,
}


def promethee_model() -> PrometheeModel:
    """PROMETHEE II's own inputs. Weights are importances applied to preference degrees, stated
    separately from the swing ratings above; thresholds are in each leaf's own units, and the
    labelled leaves carry their own numeric codes."""
    return PrometheeModel(
        criteria=[
            PrometheeCriterion(
                criterion_id="protection_standard",
                direction="maximise",
                weight=25.0,
                function=LinearPreferenceFunction(q=10.0, p=60.0),
            ),
            PrometheeCriterion(
                criterion_id="residual_risk",
                direction="minimise",
                weight=10.0,
                function=UsualFunction(),
                coding={"low": 1.0, "medium": 2.0, "high": 3.0},
            ),
            PrometheeCriterion(
                criterion_id="capital_cost",
                direction="minimise",
                weight=20.0,
                function=VShapeFunction(p=20.0),
            ),
            PrometheeCriterion(
                criterion_id="maintenance_cost",
                direction="minimise",
                weight=10.0,
                function=LinearPreferenceFunction(q=2.0, p=10.0),
            ),
            PrometheeCriterion(
                criterion_id="habitat",
                direction="minimise",
                weight=10.0,
                function=UShapeFunction(q=0.4),
            ),
            PrometheeCriterion(
                criterion_id="consent",
                direction="minimise",
                weight=15.0,
                function=VShapeFunction(p=2.0),
                coding={"routine": 1.0, "notified": 2.0, "contested": 3.0, "not consentable": 4.0},
            ),
            PrometheeCriterion(
                criterion_id="disruption",
                direction="minimise",
                weight=10.0,
                function=LinearPreferenceFunction(q=2.0, p=8.0),
            ),
        ]
    )


def requirements() -> list[BoundRequirement | LabelsRequirement]:
    return [
        BoundRequirement(
            id="protection_standard_min",
            name="Protection standard of at least 100 years",
            criterion_id="protection_standard",
            unit="years",
            minimum=100.0,
            minimum_inclusive=True,
            rationale="An invented design standard for the town's planning rules.",
        ),
        LabelsRequirement(
            id="consent_possible",
            name="A consent pathway exists",
            criterion_id="consent",
            allowed=["routine", "notified", "contested"],
            rationale="An option that cannot be consented cannot be built.",
        ),
    ]


def build_project() -> Project:
    p = ps.new_project(
        "Flood defence options (example)",
        description=(
            "Invented feasibility and PROMETHEE II example: five ways for a small coastal town to "
            "reduce flood risk, with a hard protection standard that no score can offset. All "
            "names and figures are invented."
        ),
        decision_maker="Planning team",
    )
    p = p.model_copy(update={"id": "flood_defence_options_example"})  # fixed id: reproducible file
    for alt_id, (name, _) in DATA.items():
        p = ps.add_alternative(p, name, alt_id=alt_id)

    ratio = ScaleType.RATIO
    ordinal = ScaleType.ORDINAL
    p = ps.add_criterion(p, "Protection", crit_id="protection")
    p = ps.add_criterion(
        p,
        "Flood protection standard",
        "protection",
        "protection_standard",
        scale=Scale(type=ratio, unit="years", lower=10.0, upper=250.0),
        value_function=LinearValueFunction(),
    )
    p = ps.add_criterion(
        p,
        "Residual risk if overtopped",
        "protection",
        "residual_risk",
        # Ordinal labels run from the worst to the best, so mapped values never decrease.
        scale=Scale(type=ordinal, labels=["high", "medium", "low"]),
        value_function=QualitativeValueFunction(mapping={"high": 0.0, "medium": 0.5, "low": 1.0}),
    )

    p = ps.add_criterion(p, "Cost", crit_id="cost")
    p = ps.add_criterion(
        p,
        "Capital cost",
        "cost",
        "capital_cost",
        scale=Scale(type=ratio, unit="NZD m", lower=0.0, upper=50.0),
        value_function=LinearValueFunction(direction=Direction.DECREASING),
    )
    p = ps.add_criterion(
        p,
        "50-year maintenance cost",
        "cost",
        "maintenance_cost",
        scale=Scale(type=ratio, unit="NZD m", lower=0.0, upper=35.0),
        value_function=LinearValueFunction(direction=Direction.DECREASING),
    )

    p = ps.add_criterion(p, "Environment and community", crit_id="environment")
    p = ps.add_criterion(
        p,
        "Habitat disturbed",
        "environment",
        "habitat",
        scale=Scale(type=ratio, unit="ha", lower=0.0, upper=5.0),
        value_function=LinearValueFunction(direction=Direction.DECREASING),
    )
    p = ps.add_criterion(
        p,
        "Consent pathway",
        "environment",
        "consent",
        scale=Scale(type=ordinal, labels=["not consentable", "contested", "notified", "routine"]),
        value_function=QualitativeValueFunction(
            mapping={"not consentable": 0.0, "contested": 0.3, "notified": 0.7, "routine": 1.0}
        ),
    )
    p = ps.add_criterion(
        p,
        "Construction disruption",
        "environment",
        "disruption",
        scale=Scale(type=ratio, unit="months", lower=0.0, upper=24.0),
        value_function=LinearValueFunction(direction=Direction.DECREASING),
    )

    for alt_id, (_, measures) in DATA.items():
        for leaf, value in measures.items():
            p = ps.set_performance(p, alt_id, leaf, value)
    for node, rating in SAFETY_FIRST.items():
        p = ps.set_judgement(p, node, rating)
    p = ps.rename_weight_profile(p, ps.DEFAULT_PROFILE_ID, "Safety-first")
    p = ps.add_weight_profile(
        p,
        WeightProfile(id="cost_conscious", name="Cost-conscious", judgements=dict(COST_CONSCIOUS)),
    )
    p = ps.set_requirements(p, requirements())
    p = ps.set_promethee_model(p, promethee_model())
    return ps.set_analysis_method(p, "mavt")


def write_starter(project_bytes: bytes) -> None:
    """The gallery card: the project alone, hash-checked by the existing starter loader."""
    STARTER.mkdir(parents=True, exist_ok=True)
    (STARTER / "project.json").write_bytes(project_bytes)
    manifest = StarterTemplate(
        id="flood_defence_options",
        version="1",
        title="Flood defence options",
        description=(
            "Invented feasibility and PROMETHEE II example: five flood defence options, seven "
            "criteria, a hard protection standard and a consent requirement checked beside every "
            "ranking, PROMETHEE II's own weights and thresholds, and two MAVT weight profiles. "
            "All names and figures are invented."
        ),
        source_example="examples/flood_defence_options",
        source_version="1",
        tasks=[
            "Read each option's requirement status beside its ranking",
            "Compare MAVT with PROMETHEE II and read why any pair differs",
            "Check how a large cost advantage is capped by its preference threshold",
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
