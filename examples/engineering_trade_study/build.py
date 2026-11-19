"""Builds examples/engineering_trade_study/project.json and its gallery starter, using only the
public services API.

An invented engineering trade study (docs/design/engineering-trade-study-example.md): a team chooses
a concept for an autonomous inspection vehicle that will survey a long service tunnel. It is the one
study that states every method's section, so the comparison view shows five real columns. The
project states MAVT inputs (two weight profiles and one scenario), value-based sorting classes,
SMAA-2 uncertainty, PROMETHEE II's own inputs, 78 AHP pairwise judgements and two requirements. They
are different questions put to the author, so none is derived from another. Every name and figure
is invented.

    python examples/engineering_trade_study/build.py
"""

import hashlib
import json
from pathlib import Path

from mcda_studio.domain.criteria import (
    ControlPoint,
    Direction,
    LinearValueFunction,
    PiecewiseLinearValueFunction,
    QualitativeValueFunction,
)
from mcda_studio.domain.outranking import (
    LinearPreferenceFunction,
    PrometheeCriterion,
    PrometheeModel,
    UShapeFunction,
    UsualFunction,
    VShapeFunction,
)
from mcda_studio.domain.pairwise import (
    AhpModel,
    AlternativeJudgements,
    CriteriaJudgements,
    PairwiseJudgement,
)
from mcda_studio.domain.preferences import Scenario, WeightProfile
from mcda_studio.domain.project import Project
from mcda_studio.domain.requirements import BoundRequirement, LabelsRequirement
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.domain.sorting import SortingModel
from mcda_studio.domain.starter_templates import StarterArtifact, StarterTemplate
from mcda_studio.domain.uncertainty import (
    CategoricalDistribution,
    CellUncertainty,
    GroupUncertainty,
    SmaaModel,
    UniformDistribution,
)
from mcda_studio.services import project_service as ps
from mcda_studio.services import starter_template_service as starters
from mcda_studio.storage.json_repository import JsonProjectRepository

HERE = Path(__file__).parent
STARTER = HERE.parent / "starter_templates" / "engineering_trade_study"

W, K, L, T, A = (
    "wheeled_rover",
    "tracked_crawler",
    "legged_walker",
    "tethered_crawler",
    "small_drone",
)

#: alternative id -> (name, measurements by leaf id). The test oracles read the project JSON, not
#: this table.
DATA: dict[str, tuple[str, dict[str, float | str]]] = {
    W: (
        "Wheeled rover",
        {
            "endurance": 180.0,
            "payload": 4.2,
            "obstacle": "low",
            "unit_cost": 45.0,
            "maintenance": 6.0,
            "maturity": "proven",
            "operator_skill": "low",
        },
    ),
    K: (
        "Tracked crawler",
        {
            "endurance": 150.0,
            "payload": 8.0,
            "obstacle": "medium",
            "unit_cost": 70.0,
            "maintenance": 11.0,
            "maturity": "proven",
            "operator_skill": "low",
        },
    ),
    L: (
        "Legged walker",
        {
            "endurance": 110.0,
            "payload": 3.5,
            "obstacle": "high",
            "unit_cost": 160.0,
            "maintenance": 28.0,
            "maturity": "concept",
            "operator_skill": "high",
        },
    ),
    T: (
        "Tethered crawler",
        {
            "endurance": 280.0,
            "payload": 2.0,
            "obstacle": "medium",
            "unit_cost": 90.0,
            "maintenance": 9.0,
            "maturity": "prototype",
            "operator_skill": "medium",
        },
    ),
    A: (
        "Small aerial drone",
        {
            "endurance": 35.0,
            "payload": 1.2,
            "obstacle": "high",
            "unit_cost": 30.0,
            "maintenance": 14.0,
            "maturity": "prototype",
            "operator_skill": "high",
        },
    ),
}

#: Raw swing ratings per profile, one per node, relative to its siblings. Judgements of the author.
PERFORMANCE_LED = {
    "performance": 100.0,
    "cost": 50.0,
    "risk": 40.0,
    "endurance": 100.0,
    "payload": 70.0,
    "obstacle": 60.0,
    "unit_cost": 100.0,
    "maintenance": 60.0,
    "maturity": 100.0,
    "operator_skill": 50.0,
}
COST_LED = {
    "performance": 60.0,
    "cost": 100.0,
    "risk": 40.0,
    "endurance": 100.0,
    "payload": 70.0,
    "obstacle": 60.0,
    "unit_cost": 100.0,
    "maintenance": 80.0,
    "maturity": 100.0,
    "operator_skill": 50.0,
}

#: Sorting classes, best first, with illustrative boundaries on the overall value. The boundaries
#: were chosen after the MAVT values were known, so that one concept sits close to one of them; they
#: are judgements of the author, not derived from any method.
CLASSES: list[tuple[str, float | None]] = [
    ("Shortlist", 0.65),
    ("Reserve", 0.50),
    ("Drop", None),
]


def smaa_model() -> SmaaModel:
    """SMAA-2's own uncertainty. Uniform ranges are stated test spreads around the entered values,
    one categorical cell states a maturity that is not settled, and the top-level swing ratings are
    uncertain within stated intervals. Dependence is independent, the only supported kind."""

    def uniform(alt: str, leaf: str, lower: float, upper: float) -> CellUncertainty:
        return CellUncertainty(
            alternative_id=alt,
            criterion_id=leaf,
            distribution=UniformDistribution(lower=lower, upper=upper),
        )

    return SmaaModel(
        cells=[
            uniform(W, "endurance", 165.0, 195.0),
            uniform(K, "endurance", 135.0, 165.0),
            uniform(L, "endurance", 90.0, 130.0),
            uniform(A, "endurance", 28.0, 42.0),
            uniform(W, "payload", 3.9, 4.5),
            uniform(K, "payload", 7.7, 8.3),
            uniform(L, "payload", 3.2, 3.8),
            uniform(T, "payload", 1.8, 2.2),
            uniform(A, "payload", 1.0, 1.4),
            uniform(K, "unit_cost", 60.0, 80.0),
            uniform(L, "unit_cost", 140.0, 180.0),
            CellUncertainty(
                alternative_id=T,
                criterion_id="maturity",
                distribution=CategoricalDistribution(
                    labels=["prototype", "proven"], probabilities=[0.6, 0.4]
                ),
            ),
        ],
        groups=[
            GroupUncertainty(
                parent_id=None,
                kind="rating_intervals",
                intervals={
                    "performance": (80.0, 100.0),
                    "cost": (30.0, 70.0),
                    "risk": (20.0, 60.0),
                },
            )
        ],
    )


def promethee_model() -> PrometheeModel:
    """PROMETHEE II's own inputs. Weights are importances applied to preference degrees, stated
    separately from the swing ratings; thresholds are in each leaf's own units, and the labelled
    leaves carry their own numeric codes."""
    return PrometheeModel(
        criteria=[
            PrometheeCriterion(
                criterion_id="endurance",
                direction="maximise",
                weight=20.0,
                function=LinearPreferenceFunction(q=15.0, p=90.0),
            ),
            PrometheeCriterion(
                criterion_id="payload",
                direction="maximise",
                weight=15.0,
                function=LinearPreferenceFunction(q=0.5, p=3.0),
            ),
            PrometheeCriterion(
                criterion_id="obstacle",
                direction="maximise",
                weight=10.0,
                function=UsualFunction(),
                coding={"low": 1.0, "medium": 2.0, "high": 3.0},
            ),
            PrometheeCriterion(
                criterion_id="unit_cost",
                direction="minimise",
                weight=20.0,
                function=VShapeFunction(p=60.0),
            ),
            PrometheeCriterion(
                criterion_id="maintenance",
                direction="minimise",
                weight=10.0,
                function=LinearPreferenceFunction(q=2.0, p=12.0),
            ),
            PrometheeCriterion(
                criterion_id="maturity",
                direction="maximise",
                weight=15.0,
                function=VShapeFunction(p=2.0),
                coding={"concept": 1.0, "prototype": 2.0, "proven": 3.0},
            ),
            PrometheeCriterion(
                criterion_id="operator_skill",
                direction="minimise",
                weight=10.0,
                function=UShapeFunction(q=1.0),
                coding={"low": 1.0, "medium": 2.0, "high": 3.0},
            ),
        ]
    )


#: AHP judgements, (favoured item, other item, times as important or preferred, 1 to 9). These are
#: the author's separate pairwise answers; they read no measurement and no swing rating. 78 in all:
#: 8 on the criteria and 70 (7 leaves times 10 pairs) on the five concepts.
Judgement = tuple[str, str, float]
CRITERIA_JUDGEMENTS: list[tuple[str | None, list[Judgement]]] = [
    (None, [("performance", "cost", 2.0), ("performance", "risk", 3.0), ("cost", "risk", 2.0)]),
    (
        "performance",
        [
            ("endurance", "payload", 1.0),
            ("endurance", "obstacle", 2.0),
            ("payload", "obstacle", 1.0),
        ],
    ),
    ("cost", [("unit_cost", "maintenance", 2.0)]),
    ("risk", [("maturity", "operator_skill", 2.0)]),
]
CONCEPT_JUDGEMENTS: list[tuple[str, list[Judgement]]] = [
    (
        "endurance",
        [
            (W, K, 1.0), (W, L, 3.0), (T, W, 2.0), (W, A, 5.0), (K, L, 2.0),
            (T, K, 2.0), (K, A, 4.0), (T, L, 5.0), (L, A, 2.0), (T, A, 9.0),
        ],
    ),
    (
        "payload",
        [
            (K, W, 2.0), (W, L, 1.0), (W, T, 2.0), (W, A, 4.0), (K, L, 3.0),
            (K, T, 4.0), (K, A, 8.0), (L, T, 2.0), (L, A, 3.0), (T, A, 2.0),
        ],
    ),
    (
        "obstacle",
        [
            (K, W, 4.0), (L, W, 9.0), (T, W, 4.0), (A, W, 7.0), (L, K, 2.0),
            (K, T, 1.0), (A, K, 2.0), (L, T, 2.0), (L, A, 1.0), (A, T, 2.0),
        ],
    ),
    (
        "unit_cost",
        [
            (W, K, 2.0), (W, L, 8.0), (W, T, 2.0), (W, A, 1.0), (K, L, 5.0),
            (K, T, 1.0), (A, K, 1.0), (T, L, 4.0), (A, L, 7.0), (A, T, 2.0),
        ],
    ),
    (
        "maintenance",
        [
            (W, K, 2.0), (W, L, 8.0), (W, T, 1.0), (W, A, 3.0), (K, L, 5.0),
            (T, K, 1.0), (K, A, 2.0), (T, L, 6.0), (A, L, 3.0), (T, A, 2.0),
        ],
    ),
    (
        "maturity",
        [
            (W, K, 1.0), (W, L, 9.0), (W, T, 2.0), (W, A, 2.0), (K, L, 9.0),
            (K, T, 2.0), (K, A, 2.0), (T, L, 4.0), (A, L, 4.0), (T, A, 1.0),
        ],
    ),
    (
        "operator_skill",
        [
            (W, K, 1.0), (W, L, 8.0), (W, T, 2.0), (W, A, 4.0), (K, L, 8.0),
            (K, T, 2.0), (K, A, 4.0), (T, L, 4.0), (A, L, 2.0), (T, A, 2.0),
        ],
    ),
]  # fmt: skip


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
            for leaf, items in CONCEPT_JUDGEMENTS
        ],
    )


def requirements() -> list[BoundRequirement | LabelsRequirement]:
    return [
        BoundRequirement(
            id="payload_min",
            name="Payload capacity of at least 2 kg",
            criterion_id="payload",
            unit="kg",
            minimum=2.0,
            minimum_inclusive=True,
            rationale="An invented minimum for the survey instrument package.",
        ),
        LabelsRequirement(
            id="maturity_floor",
            name="Technology at least at prototype stage",
            criterion_id="maturity",
            allowed=["prototype", "proven"],
            rationale="A concept-stage technology cannot be fielded within the project's time.",
        ),
    ]


def build_project() -> Project:
    p = ps.new_project(
        "Engineering trade study (example)",
        description=(
            "Invented trade study: five concepts for an autonomous inspection vehicle, read through "
            "MAVT, value-based sorting, SMAA-2, PROMETHEE II and AHP, with two requirements "
            "checked outside every score. All names and figures are invented."
        ),
        decision_maker="Design team",
    )
    p = p.model_copy(update={"id": "engineering_trade_study_example"})  # fixed id: reproducible
    for alt_id, (name, _) in DATA.items():
        p = ps.add_alternative(p, name, alt_id=alt_id)

    ratio = ScaleType.RATIO
    ordinal = ScaleType.ORDINAL
    p = ps.add_criterion(p, "Performance", crit_id="performance")
    p = ps.add_criterion(
        p,
        "Endurance",
        "performance",
        "endurance",
        scale=Scale(type=ratio, unit="min", lower=0.0, upper=300.0),
        value_function=LinearValueFunction(),
    )
    p = ps.add_criterion(
        p,
        "Payload capacity",
        "performance",
        "payload",
        scale=Scale(type=ratio, unit="kg", lower=0.0, upper=12.0),
        value_function=LinearValueFunction(),
    )
    p = ps.add_criterion(
        p,
        "Obstacle capability",
        "performance",
        "obstacle",
        scale=Scale(type=ordinal, labels=["low", "medium", "high"]),
        value_function=QualitativeValueFunction(mapping={"low": 0.0, "medium": 0.5, "high": 1.0}),
    )

    p = ps.add_criterion(p, "Cost", crit_id="cost")
    p = ps.add_criterion(
        p,
        "Unit cost",
        "cost",
        "unit_cost",
        scale=Scale(type=ratio, unit="NZD k", lower=10.0, upper=200.0),
        value_function=LinearValueFunction(direction=Direction.DECREASING),
    )
    p = ps.add_criterion(
        p,
        "Annual maintenance cost",
        "cost",
        "maintenance",
        scale=Scale(type=ratio, unit="NZD k/year", lower=0.0, upper=40.0),
        value_function=LinearValueFunction(direction=Direction.DECREASING),
    )

    p = ps.add_criterion(p, "Risk", crit_id="risk")
    p = ps.add_criterion(
        p,
        "Technology maturity",
        "risk",
        "maturity",
        scale=Scale(type=ordinal, labels=["concept", "prototype", "proven"]),
        value_function=QualitativeValueFunction(
            mapping={"concept": 0.0, "prototype": 0.5, "proven": 1.0}
        ),
    )
    p = ps.add_criterion(
        p,
        "Operator skill needed",
        "risk",
        "operator_skill",
        # Ordinal labels run from the worst to the best, so mapped values never decrease.
        scale=Scale(type=ordinal, labels=["high", "medium", "low"]),
        value_function=QualitativeValueFunction(mapping={"high": 0.0, "medium": 0.5, "low": 1.0}),
    )

    for alt_id, (_, measures) in DATA.items():
        for leaf, value in measures.items():
            p = ps.set_performance(p, alt_id, leaf, value)
    for node, rating in PERFORMANCE_LED.items():
        p = ps.set_judgement(p, node, rating)
    p = ps.rename_weight_profile(p, ps.DEFAULT_PROFILE_ID, "Performance-led")
    p = ps.add_weight_profile(
        p, WeightProfile(id="cost_led", name="Cost-led", judgements=dict(COST_LED))
    )
    p = ps.add_scenario(
        p,
        Scenario(
            id="diminishing_endurance",
            name="Diminishing returns on endurance",
            value_function_overrides={
                "endurance": PiecewiseLinearValueFunction(
                    points=[
                        ControlPoint(x=0.0, value=0.0),
                        ControlPoint(x=120.0, value=0.5),
                        ControlPoint(x=200.0, value=0.85),
                        ControlPoint(x=300.0, value=1.0),
                    ]
                )
            },
        ),
    )
    p = ps.set_requirements(p, requirements())
    p = ps.set_sorting_model(p, SortingModel(classes=ps.sorting_classes(CLASSES)))
    p = ps.set_smaa_model(p, smaa_model())
    p = ps.set_promethee_model(p, promethee_model())
    p = ps.set_ahp_model(p, ahp_model())
    return ps.set_analysis_method(p, "mavt")


def write_starter(project_bytes: bytes) -> None:
    """The gallery card: the project alone, hash-checked by the existing starter loader."""
    STARTER.mkdir(parents=True, exist_ok=True)
    (STARTER / "project.json").write_bytes(project_bytes)
    manifest = StarterTemplate(
        id="engineering_trade_study",
        version="1",
        title="Engineering trade study",
        description=(
            "Invented trade study: five inspection-vehicle concepts, seven criteria, two weight "
            "profiles and a scenario, classes, SMAA-2 uncertainty, PROMETHEE II, 78 AHP judgements "
            "and two requirements, so every method reads one model. All names and figures are "
            "invented."
        ),
        source_example="examples/engineering_trade_study",
        source_version="1",
        tasks=[
            "Read each concept's class and its requirement status",
            "Compare all five methods and read where their leaders differ",
            "Read how a concept near a class boundary spreads across classes under SMAA-2",
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
