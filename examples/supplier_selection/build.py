"""Builds examples/supplier_selection/project.json using only the public services API.

A deliberately different problem from the NZ deep-tech venture-capital study: 5 alternatives,
8 leaf criteria, mixed tree depth (2 and 3 levels), and every scale / value-function kind.

    python examples/supplier_selection/build.py
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
    "apex": (
        "Apex Components",
        {
            "unit_price": 42.0,
            "logistics_cost": 1.8,
            "defect_rate": 1.2,
            "certification": "iso9001_14001",
            "on_time": 96.0,
            "lead_time": 7.0,
            "financial_stability": 80.0,
            "region": "domestic",
        },
    ),
    "brightline": (
        "Brightline Supply",
        {
            "unit_price": 35.0,
            "logistics_cost": 3.5,
            "defect_rate": 3.1,
            "certification": "iso9001",
            "on_time": 91.0,
            "lead_time": 12.0,
            "financial_stability": 65.0,
            "region": "regional",
        },
    ),
    "cobalt": (
        "Cobalt Industrial",
        {
            "unit_price": 28.0,
            "logistics_cost": 5.9,
            "defect_rate": 6.4,
            "certification": "none",
            "on_time": 82.0,
            "lead_time": 21.0,
            "financial_stability": 45.0,
            "region": "overseas",
        },
    ),
    "delta": (
        "Delta Parts",
        {
            "unit_price": 51.0,
            "logistics_cost": 1.1,
            "defect_rate": 0.8,
            "certification": "iso9001_14001",
            "on_time": 99.0,
            "lead_time": 4.0,
            "financial_stability": 90.0,
            "region": "domestic",
        },
    ),
    "evergreen": (
        "Evergreen Materials",
        {
            "unit_price": 38.0,
            "logistics_cost": 2.7,
            "defect_rate": 2.2,
            "certification": "iso9001",
            "on_time": 88.0,
            "lead_time": 9.0,
            "financial_stability": 70.0,
            "region": "regional",
        },
    ),
}

BASE_RATINGS = {
    "cost": 100,
    "performance": 90,
    "risk": 50,
    "unit_price": 100,
    "logistics_cost": 40,
    "quality": 100,
    "delivery": 80,
    "defect_rate": 100,
    "certification": 30,
    "on_time": 100,
    "lead_time": 60,
    "financial_stability": 100,
    "region": 25,
}


def build_project() -> Project:
    p = ps.new_project(
        "Supplier selection (example)",
        description="Independent reusability example: cost, performance and risk of 5 suppliers.",
        decision_maker="Procurement team",
    )
    p = p.model_copy(update={"id": "supplier_selection_example"})  # fixed id: reproducible file
    for alt_id, (name, _) in DATA.items():
        p = ps.add_alternative(p, name, alt_id=alt_id)

    ratio = ScaleType.RATIO
    p = ps.add_criterion(p, "Cost", crit_id="cost")
    p = ps.add_criterion(
        p,
        "Unit price",
        "cost",
        "unit_price",
        scale=Scale(type=ratio, unit="NZD", lower=20.0, upper=60.0),
        value_function=LinearValueFunction(direction=Direction.DECREASING),
    )
    p = ps.add_criterion(
        p,
        "Logistics cost",
        "cost",
        "logistics_cost",
        scale=Scale(type=ratio, unit="NZD/unit", anchor_mode=AnchorMode.LOCAL),
        value_function=LinearValueFunction(direction=Direction.DECREASING),
    )

    p = ps.add_criterion(p, "Performance", crit_id="performance")
    p = ps.add_criterion(p, "Quality", "performance", "quality")
    p = ps.add_criterion(
        p,
        "Defect rate",
        "quality",
        "defect_rate",
        scale=Scale(type=ratio, unit="%", lower=0.0, upper=10.0),
        value_function=PiecewiseLinearValueFunction(
            points=[
                ControlPoint(x=0.0, value=1.0),
                ControlPoint(x=1.0, value=0.9),
                ControlPoint(x=3.0, value=0.5),
                ControlPoint(x=8.0, value=0.0),
            ]
        ),
    )
    p = ps.add_criterion(
        p,
        "Certification",
        "quality",
        "certification",
        scale=Scale(type=ScaleType.ORDINAL, labels=["none", "iso9001", "iso9001_14001"]),
        value_function=QualitativeValueFunction(
            mapping={"none": 0.0, "iso9001": 0.55, "iso9001_14001": 1.0}
        ),
    )
    p = ps.add_criterion(p, "Delivery", "performance", "delivery")
    p = ps.add_criterion(
        p,
        "On-time delivery",
        "delivery",
        "on_time",
        scale=Scale(type=ratio, unit="%", lower=70.0, upper=100.0),
        value_function=LinearValueFunction(),
    )
    p = ps.add_criterion(
        p,
        "Lead time",
        "delivery",
        "lead_time",
        scale=Scale(type=ratio, unit="days", lower=3.0, upper=30.0),
        value_function=LinearValueFunction(direction=Direction.DECREASING),
    )

    p = ps.add_criterion(p, "Risk", crit_id="risk")
    p = ps.add_criterion(
        p,
        "Financial stability",
        "risk",
        "financial_stability",
        scale=Scale(type=ScaleType.INTERVAL, lower=0.0, upper=100.0),
        value_function=DirectRatingValueFunction(min_rating=0.0, max_rating=100.0),
    )
    p = ps.add_criterion(
        p,
        "Sourcing region",
        "risk",
        "region",
        scale=Scale(type=ScaleType.CATEGORICAL, labels=["overseas", "regional", "domestic"]),
        value_function=QualitativeValueFunction(
            mapping={"overseas": 0.0, "regional": 0.5, "domestic": 1.0}
        ),
    )

    for alt_id, (_, measures) in DATA.items():
        for leaf, value in measures.items():
            p = ps.set_performance(p, alt_id, leaf, value)
    for node, rating in BASE_RATINGS.items():
        p = ps.set_judgement(p, node, float(rating))

    p = ps.add_weight_profile(
        p,
        WeightProfile(
            id="cost_focus",
            name="Cost focus",
            judgements={
                **{k: float(v) for k, v in BASE_RATINGS.items()},
                "cost": 100.0,
                "performance": 40.0,
                "risk": 20.0,
            },
        ),
    )
    p = ps.add_scenario(
        p,
        Scenario(
            id="linear_defects",
            name="Defect rate as linear (0-10 %)",
            value_function_overrides={
                "defect_rate": LinearValueFunction(direction=Direction.DECREASING)
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
