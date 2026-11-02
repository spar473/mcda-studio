"""Manifest integrity, fresh-review resets, intact demonstrations and portable lineage."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from mcda_studio.domain.errors import ModelEditError
from mcda_studio.domain.starter_templates import StarterInstantiationRequest
from mcda_studio.services import analysis_service
from mcda_studio.services import derived_service as derived
from mcda_studio.services import starter_template_service as starters

ROOT = Path(__file__).resolve().parents[2] / "examples"


def request(id, mode="fresh", **kwargs):
    return StarterInstantiationRequest(template_id=id, mode=mode, **kwargs)


def reviews(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "review":
                yield item
            yield from reviews(item)
    elif isinstance(value, list):
        for item in value:
            yield from reviews(item)


@pytest.mark.parametrize(
    "id", ["blank", "supplier_selection", "infrastructure_procurement", "venture_screening"]
)
def test_fresh_inputs_clear_reviews_and_snapshots_while_worked_example_is_intact(id):
    worked = starters.instantiate(request(id, "worked_example"))
    fresh = starters.instantiate(request(id, project_id="new_project", title="My project"))
    assert worked.project.fingerprint() == worked.receipt.original_project_fingerprint
    assert fresh.project.id == "new_project" and fresh.project.title == "My project"
    assert fresh.project.fingerprint() != worked.project.fingerprint()
    assert fresh.project.alternatives == worked.project.alternatives
    assert fresh.project.performances == worked.project.performances
    assert fresh.project.weight_profiles == worked.project.weight_profiles
    assert fresh.project.decision_maker == "" and starters.WARNING in fresh.project.description
    assert all(value is None for a in fresh.artifacts.values() for value in reviews(a.value))
    assert not any(a.kind in starters.SNAPSHOTS for a in fresh.artifacts.values())
    if id == "venture_screening":
        assert worked.artifacts["external_proposals"].value["reviews"]
        assert fresh.artifacts["external_proposals"].value["reviews"] == []
        assert "model_output" in fresh.receipt.omitted_artifact_ids
        assert any(value for a in worked.artifacts.values() for value in reviews(a.value))
        assert "ownership_model" not in fresh.artifacts
        assert fresh.artifacts["market_checks"].value["model_digest"] == derived._digest(
            fresh.artifacts["market_model"].value
        )
    assert starters.verify(worked) == worked
    assert starters.verify(fresh) == fresh
    assert starters.archive(fresh) == starters.archive(fresh)
    if fresh.project.alternatives:
        expected = analysis_service.evaluate_project(worked.project).model_copy(
            update={
                "project_id": fresh.project.id,
                "project_fingerprint": fresh.project.fingerprint(),
            }
        )
        assert analysis_service.evaluate_project(fresh.project) == expected


def test_optional_arithmetic_is_unattached_off_by_default_and_requires_explicit_dependencies():
    default = starters.instantiate(request("venture_screening", "worked_example"))
    optional = starters.instantiate(
        request(
            "venture_screening",
            "worked_example",
            optional_artifact_ids=["ownership_model", "ownership_checks"],
        )
    )
    assert default.project == optional.project
    assert "ownership_model" not in default.artifacts
    model = optional.artifacts["ownership_model"].value
    assert all(f["alternative_id"] is None and f["criterion_id"] is None for f in model["formulas"])
    assert "excludes option pools" in model["sources"][0]["source"]["description"]
    with pytest.raises(ModelEditError, match="requires its model"):
        starters.instantiate(
            request("venture_screening", optional_artifact_ids=["ownership_checks"])
        )
    with pytest.raises(ModelEditError, match="optional artifact IDs"):
        starters.instantiate(request("venture_screening", optional_artifact_ids=["not_declared"]))


def test_manifest_and_artifact_hashes_versions_and_paths_are_verified_before_materialization(
    tmp_path,
):
    shutil.copytree(ROOT / "starter_templates", tmp_path / "starter_templates")
    file = tmp_path / "starter_templates/blank/manifest.json"
    original = file.read_text()
    template = json.loads(original)
    template["description"] = "Changed without its digest"
    file.write_text(json.dumps(template))
    with pytest.raises(ModelEditError, match="STARTER_DIGEST"):
        starters.list_templates(tmp_path)
    file.write_text(original)
    project = file.parent / "project.json"
    original_project = project.read_text()
    project.write_text(original_project + " ")
    with pytest.raises(ModelEditError, match="STARTER_ARTIFACT_CHANGED"):
        starters.list_templates(tmp_path)
    project.write_text(original_project)
    for path in ("../project.json", "/outside.json", "bad\\path.json"):
        template = json.loads(original)
        template["artifacts"][0]["path"] = path
        template["digest"] = derived._digest({k: v for k, v in template.items() if k != "digest"})
        file.write_text(json.dumps(template))
        with pytest.raises(ModelEditError, match="STARTER_PATH"):
            starters.list_templates(tmp_path)
    file.write_text(original)
    raw = json.loads(original_project)
    raw["schema_version"] = 999
    project.write_text(json.dumps(raw))
    template = json.loads(original)
    template["artifacts"][0].update(
        schema_version=999, sha256=hashlib.sha256(project.read_bytes()).hexdigest()
    )
    template["digest"] = derived._digest({k: v for k, v in template.items() if k != "digest"})
    file.write_text(json.dumps(template))
    with pytest.raises(ModelEditError, match="STARTER_VERSION"):
        starters.list_templates(tmp_path)


def test_worked_example_overrides_and_changed_receipts_are_refused():
    with pytest.raises(ModelEditError, match="retains its exact project"):
        starters.instantiate(request("blank", "worked_example", title="Different"))
    materials = starters.instantiate(request("blank", project_id="fresh_blank"))
    materials.receipt.cleared_fields = []
    materials.digest = derived._digest(materials.model_dump(mode="json", exclude={"digest"}))
    with pytest.raises(ModelEditError, match="STARTER_MISMATCH"):
        starters.verify(materials)


def test_loader_never_dispatches_on_template_id_or_description(tmp_path):
    shutil.copytree(ROOT / "starter_templates/blank", tmp_path / "starter_templates/arbitrary")
    manifest = tmp_path / "starter_templates/arbitrary/manifest.json"
    raw = json.loads(manifest.read_text())
    raw.update(
        id="arbitrary", title="Wholly different task", description="No engine vocabulary needed"
    )
    raw["digest"] = derived._digest({k: v for k, v in raw.items() if k != "digest"})
    manifest.write_text(json.dumps(raw))
    output = starters.instantiate(request("arbitrary", project_id="new_id"), tmp_path)
    assert output.project.title == "Wholly different task"
    assert output.project.criteria == [] and output.receipt.template_id == "arbitrary"


def test_browser_integer_rendering_round_trip_keeps_typed_sidecar_digests_and_detects_changes():
    material = starters.instantiate(request("venture_screening", project_id="browser_roundtrip"))

    def browser(value):
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, list):
            return [browser(item) for item in value]
        if isinstance(value, dict):
            return {key: browser(item) for key, item in value.items()}
        return value

    from mcda_studio.domain.starter_templates import StarterMaterialization

    returned = StarterMaterialization.model_validate_json(
        json.dumps(browser(material.model_dump(mode="json")))
    )
    assert starters.verify(returned) == material
    returned.artifacts["market_model"].value["sources"][0]["value"] += 1
    with pytest.raises(ModelEditError, match="STARTER_CHANGED"):
        starters.verify(returned)


def test_configured_examples_directory_does_not_redirect_legacy_structure_definitions(tmp_path):
    import os
    import subprocess
    import sys

    from mcda_studio.services.templates import from_template

    code = """import json
from mcda_studio.services.templates import from_template
project = from_template('supplier-selection', 'Configured')
print(json.dumps(project.model_dump(mode='json', exclude={'id'}), sort_keys=True))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={
            **os.environ,
            "MCDA_STUDIO_EXAMPLES": str(tmp_path),
            "PYTHONPATH": str(ROOT.parent / "src"),
        },
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == from_template(
        "supplier-selection", "Configured"
    ).model_dump(mode="json", exclude={"id"})
