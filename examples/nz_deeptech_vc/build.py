"""Builds examples/nz_deeptech_vc/project.json from the original study report (September 2026).

"Prioritising New Zealand Deep-Tech Startups for Venture Capital Due Diligence": 4 alternatives,
4 parent objectives, 8 leaf criteria, additive MAVT with hierarchical swing weights. Everything
below is transcribed from the report; nothing is invented. Section numbers refer to the report.

    python examples/nz_deeptech_vc/build.py

The model is built with the same public services API any user would use, so the file is also a
test that the generic schema can express a real study without VC-specific code.
"""

import json
from pathlib import Path

from mcda_studio.domain.criteria import (
    ControlPoint,
    Direction,
    LinearValueFunction,
    PiecewiseLinearValueFunction,
    QualitativeValueFunction,
)
from mcda_studio.domain.preferences import Scenario
from mcda_studio.domain.project import Project
from mcda_studio.domain.scales import AnchorMode, Scale, ScaleType
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository

#: Section e(i): global qualitative scale, DECERNS codes 1-5 = VL..VH (ordinal, not equally spaced
#: until a preference mapping is adopted). Section f(iii): the mapping is 0/25/50/75/100.
LEVELS = ["Very Low", "Low", "Moderate", "High", "Very High"]
LEVEL_VALUES = {"Very Low": 0.0, "Low": 0.25, "Moderate": 0.5, "High": 0.75, "Very High": 1.0}
CODE = {1: "Very Low", 2: "Low", 3: "Moderate", 4: "High", 5: "Very High"}

#: Section e(ii) performance matrix; DECERNS codes (Figure 2) shown as labels. Outlier's Market Size
#: is the UNROUNDED 1.7129 (the report prints 1.71 but states DECERNS "retains the unrounded
#: input").
#: alternative id -> (name, {leaf id: measurement})
DATA: dict[str, tuple[str, dict[str, float | str]]] = {
    "hyades": (
        "Hyades",
        {
            "founder_expertise": CODE[3],
            "team_coverage": CODE[4],
            "problem_significance": CODE[4],
            "solution_viability": CODE[3],
            "market_size": 26.45,
            "market_growth": 8.71,
            "customer_validation": CODE[3],
            "execution_maturity": CODE[3],
        },
    ),
    "forever_harvest": (
        "Forever Harvest",
        {
            "founder_expertise": CODE[5],
            "team_coverage": CODE[4],
            "problem_significance": CODE[4],
            "solution_viability": CODE[4],
            "market_size": 1.38,
            "market_growth": 23.10,
            "customer_validation": CODE[4],
            "execution_maturity": CODE[4],
        },
    ),
    "kura_dynamics": (
        "Kura Dynamics",
        {
            "founder_expertise": CODE[5],
            "team_coverage": CODE[4],
            "problem_significance": CODE[5],
            "solution_viability": CODE[3],
            "market_size": 4.60,
            "market_growth": 9.60,
            "customer_validation": CODE[2],
            "execution_maturity": CODE[3],
        },
    ),
    "outlier_space": (
        "Outlier Space",
        {
            "founder_expertise": CODE[5],
            "team_coverage": CODE[5],
            "problem_significance": CODE[4],
            "solution_viability": CODE[3],
            "market_size": 1.7129,
            "market_growth": 16.90,
            "customer_validation": CODE[4],
            "execution_maturity": CODE[3],
        },
    ),
}

#: Section f(ii): Market Size control points *as printed* (rounded to 3 dp). The report says the
#: implemented points were "lightly adjusted when entered in DECERNS"; the unrounded entries are not
#: published, so the printed ones are used. They reproduce the report's partial values to ~5e-5 and
#: the final scores to ~5e-6; see tests/regression/test_nz_deeptech_vc_reference.py.
MARKET_SIZE_POINTS = [
    (1.380, 0.000),
    (2.552, 0.252),
    (5.077, 0.500),
    (10.037, 0.748),
    (26.450, 1.000),
]

#: Section h(i): swing ratings. Parents: Team 100, Problem & Solution 90, Market 80, Traction 70.
#: Within each parent the most valuable swing is 100 and the others are relative to it.
SWING_RATINGS: dict[str, float] = {
    "team": 100,
    "problem_solution": 90,
    "market": 80,
    "traction": 70,
    "founder_expertise": 100,
    "team_coverage": 65,
    "problem_significance": 90,
    "solution_viability": 100,
    "market_size": 100,
    "market_growth": 80,
    "customer_validation": 100,
    "execution_maturity": 70,
}

QUALITATIVE_LEAVES = {
    "founder_expertise": ("Founder Expertise", "team"),
    "team_coverage": ("Team Coverage", "team"),
    "problem_significance": ("Problem Significance", "problem_solution"),
    "solution_viability": ("Solution Viability", "problem_solution"),
    "customer_validation": ("Customer Validation", "traction"),
    "execution_maturity": ("Execution Maturity", "traction"),
}


def _qualitative_scale() -> Scale:
    return Scale(type=ScaleType.ORDINAL, labels=list(LEVELS))


def build_project() -> Project:
    p = ps.new_project(
        "NZ deep-tech startups for VC due diligence",
        description=(
            "Public-information screening model for prioritising four early-stage New Zealand "
            "deep-tech startups for further due diligence (not an investment recommendation). "
            "Transcribed from the original study report, September 2026."
        ),
        decision_maker="Seed-stage venture capital analyst or partner (hypothetical)",
    )
    p = p.model_copy(update={"id": "nz_deeptech_vc_study"})  # fixed id: reproducible file
    for alt_id, (name, _) in DATA.items():
        p = ps.add_alternative(p, name, alt_id=alt_id)

    # Section d: four objectives, eight leaf criteria.
    for crit_id, name in [
        ("team", "Team"),
        ("problem_solution", "Problem & Solution"),
        ("market", "Market"),
        ("traction", "Traction"),
    ]:
        p = ps.add_criterion(p, name, crit_id=crit_id)

    # Order within each parent follows Figure 1 / the weight table.
    p = ps.add_criterion(p, *_q("founder_expertise"), **_qual_kwargs())
    p = ps.add_criterion(p, *_q("team_coverage"), **_qual_kwargs())
    p = ps.add_criterion(p, *_q("problem_significance"), **_qual_kwargs())
    p = ps.add_criterion(p, *_q("solution_viability"), **_qual_kwargs())

    # Section f(ii): local scale, maximising, concave piecewise-linear partial value function.
    p = ps.add_criterion(
        p,
        "Market Size",
        "market",
        "market_size",
        scale=Scale(type=ScaleType.RATIO, unit="US$ bn", anchor_mode=AnchorMode.LOCAL),
        value_function=PiecewiseLinearValueFunction(
            points=[ControlPoint(x=x, value=v) for x, v in MARKET_SIZE_POINTS]
        ),
    )
    # Section h(i): local scale, maximising, linear: v = (g - 8.71) / (23.10 - 8.71).
    p = ps.add_criterion(
        p,
        "Market Growth",
        "market",
        "market_growth",
        scale=Scale(type=ScaleType.RATIO, unit="% CAGR", anchor_mode=AnchorMode.LOCAL),
        value_function=LinearValueFunction(direction=Direction.INCREASING),
    )

    p = ps.add_criterion(p, *_q("customer_validation"), **_qual_kwargs())
    p = ps.add_criterion(p, *_q("execution_maturity"), **_qual_kwargs())

    for alt_id, (_, measures) in DATA.items():
        for leaf, value in measures.items():
            p = ps.set_performance(p, alt_id, leaf, value)
    for node, rating in SWING_RATINGS.items():
        p = ps.set_judgement(p, node, float(rating))

    # Section i: the "linear Market Size" sensitivity model. Only Market Size changes.
    p = ps.add_scenario(
        p,
        Scenario(
            id="linear_market_size",
            name="Linear Market Size (local range)",
            value_function_overrides={
                "market_size": LinearValueFunction(direction=Direction.INCREASING)
            },
        ),
    )
    return p


def _q(leaf: str) -> tuple[str, str, str]:
    name, parent = QUALITATIVE_LEAVES[leaf]
    return name, parent, leaf


def _qual_kwargs() -> dict[str, object]:
    return {
        "scale": _qualitative_scale(),
        "value_function": QualitativeValueFunction(mapping=dict(LEVEL_VALUES)),
    }


#: Printed in the report (rounded) - used by the regression tests, kept next to the data.
EXPECTED_WEIGHTS = {
    "founder_expertise": 0.1783,
    "team_coverage": 0.1159,
    "problem_significance": 0.1254,
    "solution_viability": 0.1393,
    "market_size": 0.1307,
    "market_growth": 0.1046,
    "customer_validation": 0.1211,
    "execution_maturity": 0.0848,
}


def main() -> None:
    here = Path(__file__).parent
    JsonProjectRepository().save(build_project(), here / "project.json")
    (here / "expected_weights.json").write_text(
        json.dumps(EXPECTED_WEIGHTS, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {here / 'project.json'} and expected_weights.json")


if __name__ == "__main__":
    main()
