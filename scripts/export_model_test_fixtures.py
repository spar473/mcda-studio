"""Generate component contracts from actual Python model/starter services, without network."""

import json
import platform
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np

from mcda_studio.domain.evidence import Review
from mcda_studio.domain.model_comparison import ModelComparison
from mcda_studio.domain.project import Project
from mcda_studio.domain.starter_templates import StarterInstantiationRequest
from mcda_studio.services import model_comparison_service as comparisons
from mcda_studio.services import starter_template_service as starters

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "frontend/tests/fixtures"


def _render():
    base = ROOT / "examples/starter_templates/venture_screening"
    project = Project.model_validate_json((base / "project.json").read_text())
    comparison = ModelComparison.model_validate_json((base / "model_comparison.json").read_text())
    current = comparisons.inspect(project, comparison)
    selection = comparisons.ModelTargetSelection(
        side="right",
        alternative_id="a",
        criterion_id="annual",
        target_scope=comparison.right.scope,
        review=Review(
            status="accepted",
            reviewer="Illustrative reviewer",
            reviewed_at="2026-11-01T00:00:00Z",
            note="Reviewed target scope",
        ),
    )
    bundle = comparisons.compile_selection(project, comparison, selection, current.review_digest)
    return {
        "model-inspection.json": current.model_dump(mode="json"),
        "model-bundle.json": bundle.model_dump(mode="json"),
        "starter-catalog.json": [t.model_dump(mode="json") for t in starters.list_templates()],
        "starter-fresh.json": starters.instantiate(
            StarterInstantiationRequest(
                template_id="venture_screening",
                project_id="fresh_component",
                title="My illustrative decision",
            )
        ).model_dump(mode="json"),
    }


def fixtures():
    """Replay UI fixture contracts using their actual historical environment labels.

    Numerical execution is live and every generated numeric field/digest remains exact.
    These are captured UI examples, not a claim about the machine generating the fixture.
    Production run metadata and production replay are not overridden.
    """
    reference = json.loads(
        (ROOT / "examples/starter_templates/venture_screening/model_output.json").read_text()
    )
    environment = reference["environment"]
    system, machine = environment["system"].split(" ", 1)
    with (
        patch.object(platform, "python_version", return_value=environment["python"]),
        patch.object(platform, "system", return_value=system),
        patch.object(platform, "machine", return_value=machine),
        patch.object(np, "__version__", environment["numpy"]),
    ):
        return _render()


def main():
    for name, value in fixtures().items():
        text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        file = TARGET / name
        if "--check" in sys.argv:
            if not file.is_file() or file.read_text() != text:
                raise SystemExit(f"Out of date component fixture: {name}")
        else:
            file.write_text(text)
    print("Model/starter component contracts are current")


if __name__ == "__main__":
    main()
