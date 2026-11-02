"""Portable calculation artifacts retain assumptions and revalidate the existing compile gate."""

from pathlib import Path

import pytest

from mcda_studio.domain.derived import DerivedModel
from mcda_studio.domain.errors import ModelEditError, StaleRevisionError, ValidationFailed
from mcda_studio.services import derived_service as svc
from mcda_studio.services import project_service
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text

EXAMPLES = Path(__file__).parents[2] / "examples/derived_measurements"


def inputs(name="supplier"):
    p = JsonProjectRepository().load(EXAMPLES / f"{name}-project.json")
    model = DerivedModel.model_validate_json((EXAMPLES / f"{name}-model.json").read_text())
    return p, model


@pytest.mark.parametrize("name", ["venture", "supplier"])
def test_bundle_preserves_original_inputs_and_reproduces_after_reopening(name, tmp_path):
    p, model = inputs(name)
    source, original_model = to_json_text(p), model.model_dump_json()
    report = svc.preview(p, model)
    bundle = svc.compilation_bundle(p, model, report.review_digest)
    assert bundle.preview == report and bundle.source_project == p
    assert bundle.project == svc.compile_copy(p, model, report.review_digest)
    assert bundle.compiled_fingerprint == bundle.project.fingerprint()
    assert to_json_text(p) == source and model.model_dump_json() == original_model
    assert bundle.digest
    path = tmp_path / "bundle.json"
    path.write_text(bundle.model_dump_json())
    reopened = svc.DerivedCompilation.model_validate_json(path.read_text())
    assert svc.preview_document(p, reopened) == report
    # Static output is a normal project and survives the existing persistence path.
    output = tmp_path / "static.json"
    repo = JsonProjectRepository()
    repo.save(bundle.project, output)
    assert repo.load(output).fingerprint() == bundle.compiled_fingerprint


def test_compilation_requires_exact_review_and_accepted_factors():
    p, model = inputs()
    report = svc.preview(p, model)
    with pytest.raises(StaleRevisionError):
        svc.compilation_bundle(p, model, "wrong")
    model.sources[0].review = None
    with pytest.raises(StaleRevisionError):
        svc.compilation_bundle(p, model, report.review_digest)
    invalid = svc.preview(p, model)
    with pytest.raises(ValidationFailed):
        svc.compilation_bundle(p, model, invalid.review_digest)


@pytest.mark.parametrize("resign", [False, True])
def test_changed_bundle_output_is_refused_even_if_digest_is_recomputed(resign):
    p, model = inputs()
    bundle = svc.compilation_bundle(p, model, svc.preview(p, model).review_digest)
    bundle.project.title = "Modified compiled result"
    if resign:
        bundle.digest = svc._digest(bundle.model_dump(mode="json", exclude={"digest"}))
    with pytest.raises(ModelEditError):
        svc.preview_document(p, bundle)


def test_reopened_bundle_never_rebinds_to_an_edited_project():
    p, model = inputs()
    bundle = svc.compilation_bundle(p, model, svc.preview(p, model).review_digest)
    p.title = "Different project revision"
    report = svc.preview_document(p, bundle)
    assert [i.code for i in report.issues] == ["DERIVED_STALE_PROJECT"]


def test_existing_manual_values_are_visible_and_changed_only_in_the_compiled_copy():
    p, model = inputs()
    p = project_service.set_performance(p, "a", "result", 123456)
    model.project_fingerprint = p.fingerprint()
    report = svc.preview(p, model)
    target = next(c for c in report.calculations if c.alternative_id == "a")
    assert target.before == 123456 and target.value == 155000
    bundle = svc.compilation_bundle(p, model, report.review_digest)
    assert bundle.source_project.performance_index()[("a", "result")] == 123456
    assert p.performance_index()[("a", "result")] == 123456
    assert bundle.project.performance_index()[("a", "result")] == 155000
