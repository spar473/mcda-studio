"""An invented venture-style study for the rater kit and the typed-proposal runner tests.

Ten invented companies, six labelled rubric criteria (four with five levels, two with four), one
numeric criterion and one mandate criterion. Every name, rubric, source and rating is invented. The
evidence and project carry canary strings in fields a classifier or rater must never see.
"""

import json
from pathlib import Path

CANARIES = [
    "CANARY-VALUE-7f3a",
    "CANARY-DESCRIPTION-91bc",
    "CANARY-MEASUREMENT-5d20",
    "CANARY-NOTE",
]
FIVE = ["Weak", "Fair", "Good", "Strong", "Excellent"]
FOUR = ["None", "Some", "Most", "All"]
COMPANIES = [(f"co{i}", f"Company {chr(65 + i)}") for i in range(10)]
FIVE_LEAVES = ["f1", "f2", "f3", "f4"]
FOUR_LEAVES = ["g1", "g2"]
STUDY = "invented"


def labels_of(leaf: str) -> list[str]:
    return FIVE if leaf in FIVE_LEAVES else FOUR


def page_url(base: str, company: str, index: int) -> str:
    return f"{base}/{company}/{index}"


def invented_study(directory: Path, base: str = "https://example.org") -> dict[str, Path]:
    """Write project, rubrics and evidence JSON into ``directory``; return their paths.

    ``base`` is the origin of the cited pages (a local test server in the runner's tests).
    """
    leaves = [
        {
            "id": leaf,
            "name": f"Criterion {leaf}",
            "parent_id": "team",
            "parent_name": "Team",
            "scale_type": "ordinal",
            "labels": labels_of(leaf),
            "rubric": f"Rubric text for {leaf}: choose the best-supported level.",
            "numeric": False,
        }
        for leaf in FIVE_LEAVES + FOUR_LEAVES
    ]
    leaves.append(
        {
            "id": "size",
            "name": "Market size",
            "parent_id": "market",
            "parent_name": "Market",
            "scale_type": "ratio",
            "labels": [],
            "rubric": "Billions.",
            "numeric": True,
        }
    )
    rubrics = {
        "version": 1,
        "study": STUDY,
        "as_of": "2026-01-01",
        "scored_leaves": leaves,
        "screened_excluded": [{"id": "hq", "name": "HQ", "parent_id": "mandate"}],
    }
    performances, claims = [], []
    for c, (alt, _) in enumerate(COMPANIES):
        for k, leaf in enumerate(FIVE_LEAVES + FOUR_LEAVES):
            labels = labels_of(leaf)
            performances.append(
                {
                    "alternative_id": alt,
                    "criterion_id": leaf,
                    "value": labels[(c + k) % len(labels)],
                }
            )
            claims.append(
                {
                    "id": f"{alt}__{leaf}",
                    "alternative_id": alt,
                    "criterion_id": leaf,
                    "value": CANARIES[0],
                    "source": {
                        "name": f"Page {k % 2} about {alt}",
                        "reference": page_url(base, alt, k % 2),
                        "description": CANARIES[1],
                        "date": "2026-01-01",
                    },
                    "review": {"note": CANARIES[3]},
                }
            )
        performances.append({"alternative_id": alt, "criterion_id": "size", "value": 3.5})
        claims.append(
            {
                "id": f"{alt}__size",
                "alternative_id": alt,
                "criterion_id": "size",
                "value": 3.5,
                "source": {"name": "Report", "reference": f"{base}/market-report"},
            }
        )
    performances.append(
        {"alternative_id": COMPANIES[0][0], "criterion_id": "hq", "value": CANARIES[2]}
    )
    criteria = [
        {
            "id": leaf,
            "name": f"Criterion {leaf}",
            "parent_id": "team",
            "scale": {"type": "ordinal", "labels": labels_of(leaf)},
        }
        for leaf in FIVE_LEAVES + FOUR_LEAVES
    ]
    project = {
        "alternatives": [{"id": a, "name": n, "metadata": {}} for a, n in COMPANIES],
        "criteria": criteria,
        "performances": performances,
        "description": CANARIES[2],
    }
    paths = {
        "project": directory / "project.json",
        "rubrics": directory / "rubrics.json",
        "evidence": directory / "evidence.json",
    }
    paths["project"].write_text(json.dumps(project), encoding="utf-8")
    paths["rubrics"].write_text(json.dumps(rubrics), encoding="utf-8")
    paths["evidence"].write_text(json.dumps({"claims": claims}), encoding="utf-8")
    return paths
