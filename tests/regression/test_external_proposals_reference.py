"""Both invented domains use the same independent intake/selection oracle."""

import json
import runpy
from pathlib import Path

import pytest

from mcda_studio.domain.external_proposals import ExternalProposals, ProposalIntake
from mcda_studio.services import proposal_import_service as imports
from mcda_studio.services import proposal_service as svc
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text
from regression.proposal_oracle import compiled_cells, reviewed_cells

ROOT = Path(__file__).parents[2]
DEMO = ROOT / "examples/external_proposals"


@pytest.mark.parametrize("name", ["screening", "supplier"])
def test_invented_demos_match_oracle_interchange_and_reproducible_history(name, tmp_path):
    project = JsonProjectRepository().load(DEMO / f"{name}-project.json")
    intake = ProposalIntake.model_validate_json((DEMO / f"{name}-intake.json").read_text())
    workspace = ExternalProposals.model_validate_json((DEMO / f"{name}-workspace.json").read_text())
    bundle = svc.ProposalCompilation.model_validate_json(
        (DEMO / f"{name}-compilation.json").read_text()
    )
    raw = workspace.model_dump(mode="json")
    assert len(reviewed_cells(raw)) == 2
    assert bundle.evidence.project.performance_index() == compiled_cells(raw)
    assert workspace.intake == intake and len(bundle.annotations) == 1
    assert svc.verify(bundle) == bundle
    assert {r.review.status for r in workspace.reviews} == {"accepted", "corrected", "rejected"}
    inspected = svc.inspect(project, workspace, "human")
    assert {q.code for q in inspected.questions} == {"PROPOSAL_PENDING", "PROPOSAL_DISAGREEMENT"}
    assert len([r for r in inspected.rows if r.review is None]) == 2
    assert imports.parse(project, intake.model_dump_json()) == imports.parse(
        project,
        (DEMO / f"{name}-proposals.csv").read_text(),
        "csv",
        (DEMO / f"{name}-registries.json").read_text(),
    )
    original = {f.name: f.read_bytes() for f in DEMO.iterdir() if f.suffix in {".json", ".csv"}}
    script = runpy.run_path(str(DEMO / "build.py"))
    script["build"].__globals__["ROOT"] = tmp_path
    script["build"](name)
    assert all(
        (tmp_path / filename).read_bytes() == data
        for filename, data in original.items()
        if filename.startswith(name + "-")
    )
    assert to_json_text(project) == (DEMO / f"{name}-project.json").read_text()


def test_published_proposal_schemas_match_models_and_old_contract_is_not_rewritten():
    script = runpy.run_path(str(ROOT / "scripts/export_proposal_schemas.py"))
    for name, model in script["MODELS"].items():
        actual = json.loads((ROOT / "docs/schemas" / name).read_text())
        assert actual == {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            **model.model_json_schema(mode="validation"),
        }


def test_component_contract_snapshots_match_python():
    script = runpy.run_path(str(ROOT / "scripts/export_proposal_test_fixtures.py"))
    for name, text in script["texts"]().items():
        assert (ROOT / "frontend/tests/fixtures" / name).read_text() == text
