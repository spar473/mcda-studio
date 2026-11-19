"""A small synthetic project and reference sets for the reference-cases tests (not the NZ example).

Leaves, all top-level, with swing ratings that give exact binary global weights (sum 8):

    o4    ordinal A < B < C < D                 rating 1 -> 1/8
    o5    ordinal v1 < ... < v5                  rating 1 -> 1/8
    cat   categorical red, green, blue           rating 2 -> 2/8
    o4b   ordinal A < B < C < D                  rating 2 -> 2/8
    o5b   ordinal v1 < ... < v5                  rating 1 -> 1/8
    num   ratio 0..10                            rating 1 -> 1/8 (numeric: never compared)
    zero  ordinal low < high                     rating 0 -> 0   (zero weight: never compared)

Profile ``four`` sets o5b to 0 so that four leaves are compared (to test the 1/2 threshold).
Alternative ``x`` sits at the bottom of every ordinal scale, ``red``, 5 and ``low``.
"""

import json
from datetime import date, timedelta
from typing import Any

from mcda_studio.domain.criteria import (
    Direction,
    LinearValueFunction,
    QualitativeValueFunction,
)
from mcda_studio.domain.preferences import WeightProfile
from mcda_studio.domain.project import Project
from mcda_studio.domain.reference_cases import ReferenceCases
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.services import project_service as ps

FOUR = ["A", "B", "C", "D"]
FIVE = ["v1", "v2", "v3", "v4", "v5"]
COLOURS = ["red", "green", "blue"]
SNAPSHOT = date(2021, 10, 27)
RATINGS = {"o4": 1, "o5": 1, "cat": 2, "o4b": 2, "o5b": 1, "num": 1, "zero": 0}


def _ordinal(labels: list[str]) -> dict[str, Any]:
    step = 1 / (len(labels) - 1)
    return {
        "scale": Scale(type=ScaleType.ORDINAL, labels=list(labels)),
        "value_function": QualitativeValueFunction(
            mapping={label: i * step for i, label in enumerate(labels)}
        ),
    }


def project() -> Project:
    p = ps.new_project("Reference cases fixture")
    p = p.model_copy(update={"id": "fixture_project"})
    p = ps.add_alternative(p, "X", alt_id="x")
    p = ps.add_alternative(p, "Y", alt_id="y")
    p = ps.add_criterion(p, "O4", crit_id="o4", **_ordinal(FOUR))
    p = ps.add_criterion(p, "O5", crit_id="o5", **_ordinal(FIVE))
    p = ps.add_criterion(
        p,
        "Colour",
        crit_id="cat",
        scale=Scale(type=ScaleType.CATEGORICAL, labels=list(COLOURS)),
        value_function=QualitativeValueFunction(mapping={"red": 0.0, "green": 0.5, "blue": 1.0}),
    )
    p = ps.add_criterion(p, "O4b", crit_id="o4b", **_ordinal(FOUR))
    p = ps.add_criterion(p, "O5b", crit_id="o5b", **_ordinal(FIVE))
    p = ps.add_criterion(
        p,
        "Number",
        crit_id="num",
        scale=Scale(type=ScaleType.RATIO, lower=0.0, upper=10.0),
        value_function=LinearValueFunction(direction=Direction.INCREASING),
    )
    p = ps.add_criterion(p, "Zero", crit_id="zero", **_ordinal(["low", "high"]))
    for leaf, value in {
        "o4": "A",
        "o5": "v1",
        "cat": "red",
        "o4b": "A",
        "o5b": "v1",
        "num": 5.0,
        "zero": "low",
    }.items():
        p = ps.set_performance(p, "x", leaf, value)
    for leaf, value in {"o4": "D", "o5": "v5", "cat": "blue", "num": 1.0}.items():
        p = ps.set_performance(p, "y", leaf, value)
    for leaf, rating in RATINGS.items():
        p = ps.set_judgement(p, leaf, float(rating))
    p = ps.add_weight_profile(p, WeightProfile(id="four", name="Four leaves"))
    for leaf, rating in {**RATINGS, "o5b": 0}.items():
        p = ps.set_judgement(p, leaf, float(rating), "four")
    return p


def source(day: date | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": "A source",
        "reference": "https://example.org/a",
        "description": "Observed: a dated public page.",
        "classification": "independent",
    }
    if day is not None:
        out["date"] = day.isoformat()
    return out


ORIGIN = {"kind": "human", "proposed_by": "Test author"}


def case(
    case_id: str,
    labels: dict[str, str],
    *,
    snapshot: date = SNAPSHOT,
    source_key: str = "before",
    outcome_source: str = "after",
    as_of: date | None = None,
) -> dict[str, Any]:
    """One case whose every rating cites one claim on ``source_key``."""
    return {
        "id": case_id,
        "name": f"Case {case_id}",
        "snapshot_date": snapshot.isoformat(),
        "context": [{"label": "First row", "value": f"Context for {case_id}"}],
        "claims": [
            {"id": "c1", "text": "A claim.", "source": source_key, "origin": ORIGIN},
            {"id": "c2", "text": "An outcome claim.", "source": outcome_source, "origin": ORIGIN},
        ],
        "ratings": [
            {"criterion_id": leaf, "label": label, "claim_ids": ["c1"], "note": f"{leaf} note"}
            for leaf, label in labels.items()
        ],
        "outcome": {
            "label": "An outcome",
            "as_of": (as_of or snapshot + timedelta(days=400)).isoformat(),
            "note": "Recorded later.",
            "claim_ids": ["c2"],
        },
    }


def reference_set(*cases: dict[str, Any], **sources: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "reference-cases",
        "version": 1,
        "id": "fixture_set",
        "title": "Fixture reference set",
        "description": "Synthetic cases for tests.",
        "criteria_from": "fixture_project",
        "cases": list(cases),
        "sources": {
            "before": source(SNAPSHOT - timedelta(days=30)),
            "after": source(SNAPSHOT + timedelta(days=400)),
            "undated": source(None),
            **sources,
        },
    }


def load(raw: dict[str, Any]) -> ReferenceCases:
    return ReferenceCases.model_validate_json(json.dumps(raw))
