"""Publish new local model/check/starter schemas without changing existing sidecar formats."""

import json
import sys
from pathlib import Path

from mcda_studio.domain.model_comparison import ModelChecks, ModelComparison
from mcda_studio.domain.starter_templates import StarterMaterialization, StarterTemplate
from mcda_studio.services.checked_factor_service import CheckedFactorRun
from mcda_studio.services.model_checks_service import ModelOutputRun
from mcda_studio.services.model_comparison_service import ModelComparisonCompilation

ROOT = Path(__file__).resolve().parents[1] / "docs/schemas"
MODELS = {
    "model-checks-v1.schema.json": ModelChecks,
    "model-comparison-v1.schema.json": ModelComparison,
    "model-output-v1.schema.json": ModelOutputRun,
    "model-comparison-compilation-v1.schema.json": ModelComparisonCompilation,
    "checked-factor-run-v1.schema.json": CheckedFactorRun,
    "starter-template-v1.schema.json": StarterTemplate,
    "starter-materialization-v1.schema.json": StarterMaterialization,
}


def main():
    for name, model in MODELS.items():
        value = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            **model.model_json_schema(mode="validation"),
        }
        text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        file = ROOT / name
        if "--check" in sys.argv:
            if not file.is_file() or file.read_text() != text:
                raise SystemExit(f"Out of date model schema: {name}")
        else:
            file.write_text(text)
    print("Model/check/starter schemas are current")


if __name__ == "__main__":
    main()
