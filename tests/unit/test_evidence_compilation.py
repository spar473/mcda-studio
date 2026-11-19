"""Evidence compilation bundles replay retained history and reproduce the authoritative copy."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mcda_studio.domain.errors import ModelEditError, StaleRevisionError, ValidationFailed
from mcda_studio.domain.evidence import EvidenceDossier, Review
from mcda_studio.domain.evidence_workspace import ClaimReview
from mcda_studio.services import evidence_compilation_service as svc
from mcda_studio.services import evidence_service, project_service
from mcda_studio.services import evidence_workspace_service as workspaces
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text

ROOT = Path(__file__).parents[2]
PAIRS = [("vc", "nz_deeptech_vc", ("hyades", "market_size")),
         ("supplier", "supplier_qualification", ("apex", "unit_price"))]  # fmt: skip


def inputs(name="supplier", example="supplier_qualification"):
    p = JsonProjectRepository().load(ROOT / f"examples/{example}/project.json")
    d = EvidenceDossier.model_validate_json(
        (ROOT / f"examples/evidence_demo/{name}.json").read_text()
    )
    return p, d


def event(claim_id="unreviewed_example", status="rejected", **kwargs):
    return ClaimReview(
        claim_id=claim_id,
        review=Review(
            status=status,
            reviewer="Local analyst",
            reviewed_at=datetime(2026, 11, 1, tzinfo=UTC),
            note="Checked source",
            **kwargs,
        ),
    )


def reviewed(p, d, *events):
    current = workspaces.inspect(p, d)
    for e in events:
        current = workspaces.propose_review(p, current.workspace, e, current.preview.review_digest)
    return current


def compile_(p, current):
    return svc.compilation_bundle(
        p, current.workspace, current.preview.review_digest, current.workspace.digest
    )


@pytest.mark.parametrize("name,example,cell", PAIRS)
def test_bundle_retains_history_and_reproduces_after_reopening(name, example, cell, tmp_path):
    p, d = inputs(name, example)
    source, original = to_json_text(p), d.model_dump_json()
    before = p.performance_index()[cell]
    current = reviewed(p, d, event())
    bundle = compile_(p, current)
    assert to_json_text(p) == source and d.model_dump_json() == original
    assert bundle.workspace == current.workspace and bundle.workspace.source_project == p
    assert bundle.workspace.original_dossier == d
    assert [r.review.status for r in bundle.workspace.reviews] == ["rejected"]
    assert bundle.preview == current.preview
    [change] = bundle.preview.changes
    assert (change.alternative_id, change.criterion_id) == cell
    assert change.claim_id == "reviewed_example" and change.before == before
    assert bundle.project.performance_index()[cell] == d.claims[0].value
    assert bundle.compiled_fingerprint == bundle.project.fingerprint() != p.fingerprint()
    # Identical to the existing CLI gate fed with the exported reviewed dossier.
    exported = EvidenceDossier.model_validate_json(current.dossier.model_dump_json())
    cli = evidence_service.compile_copy(p, exported, current.preview.review_digest)
    assert cli == bundle.project
    path = tmp_path / "bundle.json"
    path.write_text(bundle.model_dump_json())
    reopened = svc.EvidenceCompilation.model_validate_json(path.read_text())
    assert svc.verify(reopened) == bundle
    opened = svc.inspect(p, reopened)
    assert opened.compilation == bundle and opened.inspection == current
    repo = JsonProjectRepository()
    repo.save(bundle.project, tmp_path / "copy.json")
    assert repo.load(tmp_path / "copy.json").fingerprint() == bundle.compiled_fingerprint


def test_only_accepted_or_corrected_values_compile_and_originals_survive():
    p, d = inputs()
    current = reviewed(p, d, event(), event("reviewed_example", "corrected", corrected_value=43))
    bundle = compile_(p, current)
    assert bundle.project.performance_index()[("apex", "unit_price")] == 43
    assert p.performance_index()[("apex", "unit_price")] == 42
    assert bundle.workspace.original_dossier.claims[0].value == 40
    assert bundle.workspace.original_dossier.claims[0].review.status == "accepted"
    assert [e.review.status for e in bundle.workspace.reviews] == ["rejected", "corrected"]
    rejected = reviewed(p, d, event(), event("reviewed_example"))
    nothing = compile_(p, rejected)
    assert nothing.preview.changes == [] and nothing.project == p
    unreviewed = reviewed(p, d)
    unreviewed.workspace.original_dossier.claims[0].review = None
    unreviewed.workspace.digest = workspaces.workspace_digest(unreviewed.workspace)
    pending = workspaces.inspect(p, unreviewed.workspace)
    assert compile_(p, pending).project == p  # proposals never fill measurements


def test_missing_measurements_stay_missing_not_zero():
    p, d = inputs()
    p = project_service.clear_performance(p, "brightline", "unit_price")
    d.project_fingerprint = p.fingerprint()
    current = reviewed(p, d, event())
    bundle = compile_(p, current)
    assert ("brightline", "unit_price") not in bundle.project.performance_index()
    assert [(c.alternative_id, c.criterion_id) for c in bundle.preview.missing_measurements] == [
        ("brightline", "unit_price")
    ]


def test_conflicting_accepted_claims_duplicate_ids_units_and_references_are_refused():
    p, d = inputs()
    d.claims[1].review = Review(
        status="accepted", reviewer="Second", reviewed_at=datetime(2026, 11, 1, tzinfo=UTC)
    )
    conflict = workspaces.inspect(p, d)
    assert "EVIDENCE_MULTIPLE_ACCEPTED" in [i.code for i in conflict.preview.issues]
    with pytest.raises(ValidationFailed, match="only one claim"):
        compile_(p, conflict)
    for change in ("duplicate", "unit", "alternative", "criterion"):
        p, d = inputs()
        if change == "duplicate":
            d.claims.append(d.claims[0].model_copy(deep=True))
        elif change == "unit":
            d.claims[0].unit = "USD"
        elif change == "alternative":
            d.claims[0].alternative_id = "absent"
        else:
            d.claims[0].criterion_id = "absent"
        with pytest.raises(ValidationFailed):
            compile_(p, workspaces.inspect(p, d))


def test_stale_preview_project_or_history_is_refused():
    p, d = inputs()
    current = reviewed(p, d, event())
    with pytest.raises(StaleRevisionError):
        svc.compilation_bundle(p, current.workspace, "wrong", current.workspace.digest)
    edited = project_service.update_project_details(p, title="Edited after review")
    with pytest.raises(StaleRevisionError):
        compile_(edited, current)
    # Repeating an identical review keeps the effective dossier (and so the preview digest)
    # but changes the history; the acknowledged history must be the one compiled.
    longer = workspaces.propose_review(p, current.workspace, event(), current.preview.review_digest)
    assert longer.preview.review_digest == current.preview.review_digest
    with pytest.raises(StaleRevisionError, match="history"):
        svc.compilation_bundle(
            p, longer.workspace, current.preview.review_digest, current.workspace.digest
        )


@pytest.mark.parametrize(
    "tamper", ["unsigned", "project", "preview", "history", "resigned_history", "source"]
)
def test_tampered_bundles_are_refused(tamper):
    p, d = inputs()
    bundle = compile_(p, reviewed(p, d, event()))
    if tamper == "unsigned":
        bundle.project.title = "Changed without a new digest"
    elif tamper == "project":
        bundle.project.performances[0].value = 99
    elif tamper == "preview":
        bundle.preview.changes[0].after = 99
    elif tamper == "history":
        bundle.workspace.reviews.append(event("reviewed_example"))
    elif tamper == "resigned_history":
        bundle.workspace.reviews.append(event("reviewed_example"))
        bundle.workspace.digest = workspaces.workspace_digest(bundle.workspace)
    else:
        bundle.workspace.source_project.title = "Different original"
        bundle.workspace.digest = workspaces.workspace_digest(bundle.workspace)
    if tamper != "unsigned":
        bundle.digest = svc.bundle_digest(bundle)
    with pytest.raises(ModelEditError):
        svc.verify(bundle)
    with pytest.raises(ModelEditError):
        svc.inspect(p, bundle)


def test_historical_inspection_survives_project_edits_but_review_is_blocked():
    p, d = inputs()
    bundle = compile_(p, reviewed(p, d, event()))
    edited = project_service.set_performance(p, "apex", "unit_price", 41)
    opened = svc.inspect(edited, bundle)
    assert opened.compilation == bundle  # the recorded compilation is unchanged
    assert "EVIDENCE_STALE_PROJECT" in [i.code for i in opened.inspection.preview.issues]
    assert opened.inspection.workspace == bundle.workspace
    with pytest.raises(StaleRevisionError):
        workspaces.propose_review(
            edited,
            opened.inspection.workspace,
            event("reviewed_example"),
            opened.inspection.preview.review_digest,
        )
    # Opening against the compiled copy is equally historical: its dossier binds the source.
    against_copy = svc.inspect(bundle.project, bundle)
    assert "EVIDENCE_STALE_PROJECT" in [i.code for i in against_copy.inspection.preview.issues]
