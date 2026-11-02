"""Publish synthetic UI contracts from the real proxy services; never inference."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from mcda_studio.domain.requirements import BoundRequirement  # noqa: E402
from mcda_studio.services import proxy_criterion_service as proxy  # noqa: E402
from proxy_builders import inputs, request  # noqa: E402


def fixtures():
    value = inputs()

    def requirement(project):
        project.id = "proxy_requirements_fixture"
        project.title = "Illustrative proxy and mandatory requirements"
        project.performances[0].value = 1.0
        project.requirements = [
            BoundRequirement(
                id="minimum_quality",
                name="Minimum quality",
                criterion_id="quality",
                minimum=0.5,
                maximum=1.0,
                unit=None,
            )
        ]

    feasible = inputs(project_change=requirement)
    return {
        "proxy-feasibility-inputs.json": feasible.model_dump(mode="json"),
        "proxy-feasibility-pair.json": proxy.run_pair(request(feasible)).model_dump(mode="json"),
        "proxy-inputs.json": value.model_dump(mode="json"),
        "proxy-inspection.json": proxy.inspect(value).model_dump(mode="json"),
        "proxy-pair.json": proxy.run_pair(request(value)).model_dump(mode="json"),
    }


if __name__ == "__main__":
    for name, value in fixtures().items():
        (ROOT / "frontend/tests/fixtures" / name).write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n"
        )
