"""Builds examples/infrastructure_procurement/project.json using only the public services API.

The B3 acceptance case for hierarchical swing weighting and preference profiles. It is
deliberately unrelated to the NZ deep-tech venture study and differs from the supplier example in
the ways B3 has to handle:

* four parent objectives with *different* numbers of children (3, 2, 2 and 1),
* an only child, whose local weight is one without any invented rating,
* a three-level branch (Service performance -> Reliability -> leaves),
* mixed quantitative (ratio, interval) and qualitative (ordinal, categorical) scales,
* a zero-rated criterion inside an otherwise valid sibling group,
* two independent preference profiles,
* a scenario that references a profile *and* overrides a value function.

    python examples/infrastructure_procurement/build.py
"""

from pathlib import Path

from mcda_studio.domain.criteria import (
    ControlPoint,
    Direction,
    DirectRatingValueFunction,
    LinearValueFunction,
    PiecewiseLinearValueFunction,
    QualitativeValueFunction,
)
from mcda_studio.domain.preferences import Scenario, WeightProfile
from mcda_studio.domain.project import Project
from mcda_studio.domain.scales import AnchorMode, Scale, ScaleType
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository

#: alternative id -> (name, measurements by leaf id). Also used by the independent test oracle.
DATA: dict[str, tuple[str, dict[str, float | str]]] = {
    "alliance": (
        "Alliance upgrade of existing plant",
        {
            "capital_cost": 48.0,
            "operating_cost": 3.9,
            "funding_premium": 0.8,
            "capacity_margin": 18.0,
            "outage_hours": 26.0,
            "compliance": "compliant",
            "community": "supportive",
            "footprint": "existing_site",
            "track_record": 85.0,
        },
    ),
    "designbuild": (
        "Design-build greenfield plant",
        {
            "capital_cost": 95.0,
            "operating_cost": 2.6,
            "funding_premium": 2.4,
            "capacity_margin": 45.0,
            "outage_hours": 9.0,
            "compliance": "exceeds",
            "community": "divided",
            "footprint": "greenfield",
            "track_record": 65.0,
        },
    ),
    "modular": (
        "Modular staged build",
        {
            "capital_cost": 66.0,
            "operating_cost": 3.2,
            "funding_premium": 1.5,
            "capacity_margin": 30.0,
            "outage_hours": 15.0,
            "compliance": "exceeds",
            "community": "neutral",
            "footprint": "brownfield",
            "track_record": 88.0,
        },
    ),
    "regional": (
        "Regional shared scheme",
        {
            "capital_cost": 58.0,
            "operating_cost": 4.6,
            "funding_premium": 3.1,
            "capacity_margin": 24.0,
            "outage_hours": 34.0,
            "compliance": "marginal",
            "community": "supportive",
            "footprint": "brownfield",
            "track_record": 45.0,
        },
    ),
}

#: The "Balanced" profile. ``footprint`` is a deliberate zero inside a valid group: the decision
#: maker sees no value in that particular swing, which is not the same as having no judgement.
BASE_RATINGS = {
    "lifecycle_cost": 100,
    "service": 95,
    "consent": 60,
    "delivery": 45,
    "capital_cost": 100,
    "operating_cost": 70,
    "funding_premium": 30,
    "reliability": 100,
    "compliance": 85,
    "capacity_margin": 60,
    "outage_hours": 100,
    "community": 100,
    "footprint": 0,
}

#: The "Consent led" profile: the same tree, a different decision maker's swings.
CONSENT_RATINGS = {
    **BASE_RATINGS,
    "lifecycle_cost": 40,
    "service": 70,
    "consent": 100,
    "delivery": 35,
    "footprint": 55,
}


def build_project() -> Project:
    p = ps.new_project(
        "Infrastructure procurement (example)",
        description=(
            "Independent B3 acceptance case: four objectives, a three-level branch, an only "
            "child, a zero-rated criterion and two preference profiles."
        ),
        decision_maker="Capital planning group",
    )
    p = p.model_copy(update={"id": "infrastructure_procurement_example"})  # fixed, reproducible id
    for alt_id, (name, _) in DATA.items():
        p = ps.add_alternative(p, name, alt_id=alt_id)

    ratio = ScaleType.RATIO

    # --- Lifecycle cost: three children, all quantitative and all decreasing ------------------
    p = ps.add_criterion(p, "Lifecycle cost", crit_id="lifecycle_cost")
    p = ps.add_criterion(
        p,
        "Capital cost",
        "lifecycle_cost",
        "capital_cost",
        scale=Scale(type=ratio, unit="NZD m", lower=40.0, upper=100.0),
        value_function=LinearValueFunction(direction=Direction.DECREASING),
    )
    p = ps.add_criterion(
        p,
        "Operating cost",
        "lifecycle_cost",
        "operating_cost",
        scale=Scale(type=ratio, unit="NZD m/yr", anchor_mode=AnchorMode.LOCAL),
        value_function=LinearValueFunction(direction=Direction.DECREASING),
    )
    p = ps.add_criterion(
        p,
        "Funding risk premium",
        "lifecycle_cost",
        "funding_premium",
        scale=Scale(type=ratio, unit="%", lower=0.0, upper=4.0),
        value_function=LinearValueFunction(direction=Direction.DECREASING),
    )

    # --- Service performance: two children, one of which is itself a parent (depth 3) ---------
    p = ps.add_criterion(p, "Service performance", crit_id="service")
    p = ps.add_criterion(p, "Reliability", "service", "reliability")
    p = ps.add_criterion(
        p,
        "Design capacity margin",
        "reliability",
        "capacity_margin",
        scale=Scale(type=ratio, unit="%", lower=10.0, upper=50.0),
        value_function=LinearValueFunction(),
    )
    p = ps.add_criterion(
        p,
        "Unplanned outage hours",
        "reliability",
        "outage_hours",
        scale=Scale(type=ratio, unit="h/yr", lower=0.0, upper=40.0),
        value_function=PiecewiseLinearValueFunction(
            points=[
                ControlPoint(x=0.0, value=1.0),
                ControlPoint(x=8.0, value=0.85),
                ControlPoint(x=20.0, value=0.4),
                ControlPoint(x=40.0, value=0.0),
            ]
        ),
    )
    p = ps.add_criterion(
        p,
        "Water quality compliance",
        "service",
        "compliance",
        scale=Scale(type=ScaleType.ORDINAL, labels=["marginal", "compliant", "exceeds"]),
        value_function=QualitativeValueFunction(
            mapping={"marginal": 0.0, "compliant": 0.6, "exceeds": 1.0}
        ),
    )

    # --- Consent and community: two children, one qualitative and one unordered category ------
    p = ps.add_criterion(p, "Consent and community", crit_id="consent")
    p = ps.add_criterion(
        p,
        "Community acceptance",
        "consent",
        "community",
        scale=Scale(type=ScaleType.ORDINAL, labels=["divided", "neutral", "supportive"]),
        value_function=QualitativeValueFunction(
            mapping={"divided": 0.0, "neutral": 0.5, "supportive": 1.0}
        ),
    )
    p = ps.add_criterion(
        p,
        "Ecological footprint",
        "consent",
        "footprint",
        scale=Scale(
            type=ScaleType.CATEGORICAL, labels=["greenfield", "brownfield", "existing_site"]
        ),
        value_function=QualitativeValueFunction(
            mapping={"greenfield": 0.0, "brownfield": 0.45, "existing_site": 1.0}
        ),
    )

    # --- Delivery capability: a single child, whose local weight is necessarily one ------------
    p = ps.add_criterion(p, "Delivery capability", crit_id="delivery")
    p = ps.add_criterion(
        p,
        "Contractor track record",
        "delivery",
        "track_record",
        # Directly rated 0-100 by the review panel, not a measured physical quantity.
        scale=Scale(type=ScaleType.INTERVAL, lower=0.0, upper=100.0),
        value_function=DirectRatingValueFunction(min_rating=0.0, max_rating=100.0),
    )

    for alt_id, (_, measures) in DATA.items():
        for leaf, value in measures.items():
            p = ps.set_performance(p, alt_id, leaf, value)
    for node, rating in BASE_RATINGS.items():
        p = ps.set_judgement(p, node, float(rating))

    p = ps.rename_weight_profile(p, "default", "Balanced")
    p = ps.add_weight_profile(
        p,
        WeightProfile(
            id="consent_led",
            name="Consent led",
            judgements={k: float(v) for k, v in CONSENT_RATINGS.items()},
        ),
    )
    # A scenario that both names a profile and overrides a value function, so profile resolution
    # through a scenario is exercised alongside scenario value functions.
    p = ps.add_scenario(
        p,
        Scenario(
            id="consent_review",
            name="Consent review (linear outage hours)",
            weight_profile_id="consent_led",
            value_function_overrides={
                "outage_hours": LinearValueFunction(direction=Direction.DECREASING)
            },
        ),
    )
    return p


def main() -> None:
    here = Path(__file__).parent
    project = build_project()
    JsonProjectRepository().save(project, here / "project.json")
    print(f"wrote {here / 'project.json'}")


if __name__ == "__main__":
    main()
