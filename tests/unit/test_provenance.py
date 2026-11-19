"""Separate-copy receipts relate fingerprints explicitly; nothing is rebound or made equal."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mcda_studio.domain.derived import DerivedModel
from mcda_studio.domain.errors import ModelEditError
from mcda_studio.domain.evidence import EvidenceDossier, Review
from mcda_studio.domain.evidence_workspace import ClaimReview
from mcda_studio.services import derived_service, project_service
from mcda_studio.services import evidence_compilation_service as evidence_compilation
from mcda_studio.services import evidence_workspace_service as workspaces
from mcda_studio.services import provenance_service as svc
from mcda_studio.storage.json_repository import JsonProjectRepository

ROOT = Path(__file__).parents[2]


def evidence_bundle():
    p = JsonProjectRepository().load(ROOT / "examples/supplier_qualification/project.json")
    d = EvidenceDossier.model_validate_json(
        (ROOT / "examples/evidence_demo/supplier.json").read_text()
    )
    current = workspaces.inspect(p, d)
    review = Review(status="rejected", reviewer="Analyst", reviewed_at=datetime.now(UTC))
    current = workspaces.propose_review(
        p,
        current.workspace,
        ClaimReview(claim_id="unreviewed_example", review=review),
        current.preview.review_digest,
    )
    bundle = evidence_compilation.compilation_bundle(
        p, current.workspace, current.preview.review_digest, current.workspace.digest
    )
    return p, bundle


def calculation_bundle():
    folder = ROOT / "examples/derived_measurements"
    p = JsonProjectRepository().load(folder / "venture-project.json")
    model = DerivedModel.model_validate_json((folder / "venture-model.json").read_text())
    return p, derived_service.compilation_bundle(
        p, model, derived_service.preview(p, model).review_digest
    )


def imported_copy(project):
    """What the import endpoint does when the project ID already exists."""
    copy = project_service.duplicate_project(project, title=project.title)
    return copy, svc.copy_receipt(project, copy)


def resign(receipt):
    receipt.digest = svc.receipt_digest(receipt)
    return receipt


@pytest.mark.parametrize("make", [evidence_bundle, calculation_bundle])
def test_exact_relationships_and_verified_copy(make):
    source, bundle = make()
    copy, receipt = imported_copy(bundle.project)
    assert receipt.transformation == "new_project_id"
    assert receipt.original_fingerprint == bundle.compiled_fingerprint
    assert receipt.copy_fingerprint == copy.fingerprint() != bundle.compiled_fingerprint
    assert svc.bind(bundle.project, bundle).relationship == "compiled"
    assert svc.bind(source, bundle).relationship == "source"
    # Without the explicit receipt the copy is different, however similar its numbers are.
    assert svc.bind(copy, bundle).relationship == "different"
    binding = svc.bind(copy, bundle, receipt)
    assert binding.relationship == "verified_copy" and binding.copy_receipt == receipt
    assert binding.current_fingerprint == copy.fingerprint()
    assert binding.compiled_fingerprint == bundle.compiled_fingerprint
    assert binding.current_fingerprint != binding.compiled_fingerprint
    assert binding.source_fingerprint == source.fingerprint()
    assert binding.artifact_digest == bundle.digest


@pytest.mark.parametrize("make", [evidence_bundle, calculation_bundle])
def test_later_edits_to_the_copy_or_other_projects_never_bind(make):
    _, bundle = make()
    copy, receipt = imported_copy(bundle.project)
    edited = project_service.update_project_details(copy, description="Edited after import")
    with pytest.raises(ModelEditError, match="PROVENANCE_RECEIPT_PROJECT"):
        svc.bind(edited, bundle, receipt)
    assert svc.bind(edited, bundle).relationship == "different"
    other = JsonProjectRepository().load(ROOT / "examples/nz_deeptech_vc/project.json")
    other_copy, other_receipt = imported_copy(other)
    with pytest.raises(ModelEditError, match="PROVENANCE_RECEIPT_ARTIFACT"):
        svc.bind(other_copy, bundle, other_receipt)


def test_receipts_record_only_an_id_change():
    _, bundle = evidence_bundle()
    retitled = project_service.duplicate_project(bundle.project)  # also changes the title
    with pytest.raises(ModelEditError, match="TRANSFORMATION"):
        svc.copy_receipt(bundle.project, retitled)
    with pytest.raises(ModelEditError, match="IDENTITY"):
        svc.copy_receipt(bundle.project, bundle.project.model_copy(deep=True))


@pytest.mark.parametrize("field", ["digest", "copy_id", "original_id", "original_fp", "same_ids"])
def test_tampered_receipts_are_refused(field):
    _, bundle = evidence_bundle()
    copy, receipt = imported_copy(bundle.project)
    if field == "digest":
        receipt.original_project_id = "elsewhere"
    elif field == "copy_id":
        resign(receipt).copy_project_id = "elsewhere"
        resign(receipt)
    elif field == "original_id":
        receipt.original_project_id = "elsewhere"
        resign(receipt)
    elif field == "original_fp":
        receipt.original_fingerprint = "0" * 64
        resign(receipt)
    else:
        receipt.original_project_id = receipt.copy_project_id
        resign(receipt)
    with pytest.raises(ModelEditError, match="PROVENANCE_RECEIPT"):
        svc.verify_receipt(copy, receipt)
    with pytest.raises(ModelEditError):
        svc.bind(copy, bundle, receipt)


@pytest.mark.parametrize("make", [evidence_bundle, calculation_bundle])
def test_binding_verifies_the_artifact_first(make):
    source, bundle = make()
    bundle.project.title = "Tampered compiled result"
    with pytest.raises(ModelEditError):
        svc.bind(source, bundle)
