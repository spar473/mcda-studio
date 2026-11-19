"""New proxy sidecars; no existing project, sidecar or result schema is altered."""

import json
import sys
from pathlib import Path

from mcda_studio.domain.proxy_criterion import ProxyCriterionPlan
from mcda_studio.services.proxy_criterion_service import ProxyComparisonBundle, ProxyInputs

MODELS = {
    "proxy-plan-v1.schema.json": ProxyCriterionPlan,
    "proxy-inputs-v1.schema.json": ProxyInputs,
    "proxy-comparison-v1.schema.json": ProxyComparisonBundle,
}
ROOT = Path(__file__).resolve().parents[1] / "docs/schemas"


def main():
    for name, model in MODELS.items():
        text = (
            json.dumps(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    **model.model_json_schema(mode="validation"),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        file = ROOT / name
        if "--check" in sys.argv:
            if not file.is_file() or file.read_text() != text:
                raise SystemExit(f"Out of date proxy schema: {name}")
        else:
            file.write_text(text)
    print("Proxy schemas are current")


if __name__ == "__main__":
    main()
