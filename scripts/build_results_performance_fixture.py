"""Generic B6 benchmark: 50 alternatives, 40 leaves, depth three, two profiles/scenarios."""

import json
import sys
from pathlib import Path

from mcda_studio.domain.project import Project


def build_project() -> Project:
    criteria = []
    ratings = {}
    leaves = []
    for group in range(4):
        group_id = f"objective_{group}"
        criteria.append({"id": group_id, "name": f"Performance objective {group}", "order": group})
        ratings[group_id] = 100 - group * 20
        for branch in range(2):
            branch_id = f"{group_id}_branch_{branch}"
            criteria.append(
                {
                    "id": branch_id,
                    "name": f"Nested performance branch {group}.{branch}",
                    "parent_id": group_id,
                    "order": branch,
                }
            )
            ratings[branch_id] = 100 - branch * 25
            for leaf in range(5):
                leaf_id = f"metric_{group}_{branch}_{leaf}"
                leaves.append(leaf_id)
                criteria.append(
                    {
                        "id": leaf_id,
                        "name": (
                            f"Performance metric {group}.{branch}.{leaf} "
                            "with a deliberately descriptive label"
                        ),
                        "description": (
                            "A generic dimensionless performance judgement "
                            "over a fixed 0–100 range. Benchmark inputs are synthetic; "
                            "this is not an empirical decision recommendation."
                        ),
                        "parent_id": branch_id,
                        "order": leaf,
                        "scale": {
                            "type": "interval",
                            "unit": "index points",
                            "lower": 0,
                            "upper": 100,
                        },
                        "value_function": {
                            "kind": "direct_rating",
                            "min_rating": 0,
                            "max_rating": 100,
                        },
                    }
                )
                ratings[leaf_id] = 100 - leaf * 10
    alternatives = [
        {
            "id": f"option_{i:03d}",
            "name": (
                f"Generic alternative {i:03d} — a long descriptive label "
                "for layout and interaction checks"
            ),
        }
        for i in range(50)
    ]
    other = {**ratings, **{f"objective_{i}": 40 + i * 20 for i in range(4)}}
    return Project.model_validate(
        {
            "schema_version": 1,
            "id": "results_performance",
            "title": "B6 results performance fixture — 50 alternatives / 40 leaf criteria",
            "description": (
                "Deterministic synthetic benchmark; 52 nodes, three hierarchy levels, "
                "2000 measurements. No domain-specific assumptions."
            ),
            "criteria": criteria,
            "alternatives": alternatives,
            "performances": [
                {
                    "alternative_id": alternative["id"],
                    "criterion_id": leaf,
                    "value": float((i * 17 + j * 7) % 101),
                }
                for i, alternative in enumerate(alternatives)
                for j, leaf in enumerate(leaves)
            ],
            "weight_profiles": [
                {"id": "balanced", "name": "Balanced benchmark preferences", "judgements": ratings},
                {
                    "id": "alternative",
                    "name": "Alternative benchmark preferences",
                    "judgements": other,
                },
            ],
            "scenarios": [
                {
                    "id": "reverse_first",
                    "name": "Reverse first metric",
                    "value_function_overrides": {
                        leaves[0]: {"kind": "linear", "direction": "decreasing"}
                    },
                },
                {
                    "id": "different_profile",
                    "name": "Different profile",
                    "weight_profile_id": "alternative",
                },
            ],
        }
    )


def main() -> None:
    path = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parents[1] / "tests/fixtures/performance_project.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_project().model_dump(mode="json"), sort_keys=True, indent=2) + "\n"
    )
    print(path)


if __name__ == "__main__":
    main()
