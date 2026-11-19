"""Generate component contracts from actual Python model/starter services, without network."""

import argparse
import json
import math
import platform
from pathlib import Path
from unittest.mock import patch

import numpy as np

from mcda_studio.domain.evidence import Review
from mcda_studio.domain.model_comparison import ModelComparison
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.starter_templates import StarterInstantiationRequest
from mcda_studio.services import model_comparison_service as comparisons
from mcda_studio.services import screening_summary_service as screening
from mcda_studio.services import starter_template_service as starters

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "frontend/tests/fixtures"

# Owner-approved component-snapshot exceptions only. Numerical guarantees remain
# in the unchanged same-runtime engine checks and independent summary oracles.
SCREENING_SUMMARY_FLOAT_PATHS = frozenset(
    {
        "rows.*.value",
        "rows.*.margin",
        "rows.*.drivers.*.contribution",
        "rows.*.fragility.base_local_weight",
        "rows.*.fragility.local_weight",
        "rows.*.fragility.weight_change",
    }
)


def assert_fixture_matches(name, committed, generated):
    """Exact fixture contract, with six named screening-summary float exceptions.

    No whole object or numeric type is ignored. Keys, list order/length, scalar
    types, nullability, all other values and unknown future float fields stay exact.
    """
    if name != "screening-summary.json":
        assert committed == generated, f"{name}: component fixture differs"
        return

    def compare(left, right, path):
        location = name + ": " + ".".join(map(str, path))
        assert type(left) is type(right), f"{location}: scalar/container type differs"
        if isinstance(left, dict):
            assert left.keys() == right.keys(), f"{location}: keys differ"
            for key in left:
                compare(left[key], right[key], (*path, key))
        elif isinstance(left, list):
            assert len(left) == len(right), f"{location}: list length differs"
            for index, (old, new) in enumerate(zip(left, right, strict=True)):
                compare(old, new, (*path, index))
        else:
            pattern = ".".join("*" if isinstance(key, int) else key for key in path)
            if pattern in SCREENING_SUMMARY_FLOAT_PATHS and isinstance(left, float):
                assert math.isfinite(left) and math.isfinite(right), f"{location}: non-finite float"
            else:
                assert left == right, f"{location}: {left!r} != {right!r}"

    compare(committed, generated, ())


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
    study = Project.model_validate_json(
        (ROOT / "examples/nz_venture_screening/project.json").read_text()
    )
    commercial = AnalysisConfiguration(
        method="mavt_sorting", weight_profile_id="commercial_traction"
    )
    summary = screening.screening_summary(study, commercial).model_dump(mode="json")
    return {
        "screening-summary.json": summary,
        "screening-study-project.json": study.model_dump(mode="json"),
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


def write_fixtures(target, *, check=False):
    if not check:
        target.mkdir(parents=True, exist_ok=True)
    for name, value in fixtures().items():
        text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        file = target / name
        if check:
            if not file.is_file():
                raise SystemExit(f"Out of date component fixture: {name}")
            if name != "screening-summary.json" and file.read_text() != text:
                raise SystemExit(f"Out of date component fixture: {name}")
            try:
                assert_fixture_matches(name, json.loads(file.read_text()), value)
            except AssertionError as exc:
                raise SystemExit(f"Out of date component fixture: {exc}") from exc
        else:
            file.write_text(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=TARGET)
    args = parser.parse_args(argv)
    write_fixtures(args.output_dir, check=args.check)
    print("Model/starter component contracts are current")


if __name__ == "__main__":
    main()
