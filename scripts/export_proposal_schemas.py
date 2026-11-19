"""Publish the local proposal interchange schemas; never fetch schema references."""

import json
import sys
from pathlib import Path

from mcda_studio.domain.external_proposals import ExternalProposals, ProposalIntake
from mcda_studio.services.proposal_service import ProposalCompilation

ROOT = Path(__file__).resolve().parents[1] / "docs/schemas"
MODELS = {
    "external-proposals-v1.schema.json": ProposalIntake,
    "external-proposals-workspace-v1.schema.json": ExternalProposals,
    "proposal-compilation-v1.schema.json": ProposalCompilation,
}


def main():
    for name, model in MODELS.items():
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            **model.model_json_schema(mode="validation"),
        }
        text = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        file = ROOT / name
        if "--check" in sys.argv:
            if not file.is_file() or file.read_text() != text:
                raise SystemExit(f"Proposal schema out of date: {file.name}")
        else:
            file.write_text(text)
    print("Proposal schemas current.")


if __name__ == "__main__":
    main()
