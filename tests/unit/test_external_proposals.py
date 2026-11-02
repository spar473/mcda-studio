"""Review, provenance, refusal and round-trip tests for local external proposals."""

import copy
import json

import pytest

from mcda_studio.domain.errors import ModelEditError, StaleRevisionError, ValidationFailed
from mcda_studio.domain.external_proposals import (
    AlternativeTag,
    CategoricalProposal,
    NumericProposal,
    SuggestedSourceClaim,
)
from mcda_studio.services import evidence_service
from mcda_studio.services import proposal_import_service as imports
from mcda_studio.services import proposal_service as svc
from mcda_studio.storage.json_repository import to_json_text
from proposal_builders import apply, compile_, event, inputs
from regression.proposal_oracle import canonical_digest, compiled_cells, csv_payloads


def test_pending_corrected_rejected_and_compilation_preserve_all_originals():
    p, intake = inputs()
    workspace = svc.start(p, intake)
    original = workspace.model_dump_json()
    assert compile_(p, workspace).evidence.project == p
    accepted = apply(p, workspace, event()).workspace
    assert compile_(p, accepted).evidence.project.performance_index()["a", "cost"] == 30
    corrected = apply(
        p, accepted, event(status="corrected", payload=NumericProposal(value=44, unit=None))
    ).workspace
    bundle = compile_(p, corrected)
    assert bundle.workspace.intake == intake
    assert bundle.workspace.intake.proposals[0].payload.value == 30
    assert [r.review.status for r in bundle.workspace.reviews] == ["accepted", "corrected"]
    assert bundle.evidence.project.performance_index() == compiled_cells(
        corrected.model_dump(mode="json")
    )
    assert bundle.evidence.project.performance_index()["a", "cost"] == 44
    assert p.performance_index()["a", "cost"] == 20
    assert workspace.model_dump_json() == original
    ordinary = evidence_service.compile_copy(
        p, bundle.evidence.workspace.original_dossier, bundle.evidence.preview.review_digest
    )
    assert to_json_text(ordinary) == to_json_text(bundle.evidence.project)
    assert (
        svc.verify(svc.ProposalCompilation.model_validate_json(bundle.model_dump_json())) == bundle
    )
    rejected = apply(p, corrected, event(status="rejected")).workspace
    assert compile_(p, rejected).evidence.project == p
    assert [e.review.status for e in rejected.reviews] == ["accepted", "corrected", "rejected"]


def test_json_csv_parity_and_independent_canonical_digest():
    p, intake = inputs()
    text, registry = imports.csv_files(intake)
    a = imports.parse(p, intake.model_dump_json())
    b = imports.parse(p, text, "csv", registry)
    assert a.model_dump_json() == b.model_dump_json()
    assert csv_payloads(text)["quote_a"]["payload"] == intake.proposals[0].payload.model_dump()
    assert svc.workspace_digest(a) == canonical_digest(
        a.model_dump(mode="json", exclude={"digest"})
    )
    assert imports.parse(p, a.model_dump_json()) == a


@pytest.mark.parametrize(
    "change,code",
    [
        ("alternative", "PROPOSAL_ALTERNATIVE"),
        ("criterion", "PROPOSAL_CRITERION"),
        ("unit", "PROPOSAL_UNIT"),
        ("source", "PROPOSAL_SOURCES"),
        ("source_reference", "PROPOSAL_SOURCES"),
        ("card", "PROPOSAL_MODEL_CARD"),
        ("card_digest", "PROPOSAL_MODEL_CARD"),
        ("value", "PROPOSAL_VALUE"),
    ],
)
def test_semantic_issues_retained_but_acceptance_refused(change, code):
    p, intake = inputs()
    proposal = intake.proposals[0]
    if change == "alternative":
        proposal.subject.alternative_id = "missing"
    if change == "criterion":
        proposal.subject.criterion_id = "missing"
    if change == "unit":
        proposal.payload.unit = "other"
    if change == "source":
        intake.sources.clear()
    if change == "source_reference":
        proposal.source_ids = ["missing"]
    if change == "card":
        intake.model_cards.clear()
    if change == "card_digest":
        proposal.model_card_digest = "0" * 64
    if change == "value":
        proposal.payload.value = -1.0
    workspace = imports.parse(p, intake.model_dump_json())
    checked = svc.inspect(p, workspace)
    assert code in [i.code for i in checked.rows[0].issues]
    assert not checked.rows[0].bulk_eligible
    assert checked.questions[0].code == "PROPOSAL_PENDING"
    assert workspace.intake == intake
    with pytest.raises(ValidationFailed):
        apply(p, workspace, event())
    assert compile_(p, workspace).evidence.project == p
    # Individual rejection can resolve a blocked proposal; bulk must never include it.
    rejected = apply(p, workspace, event(status="rejected"))
    assert rejected.rows[0].review.status == "rejected"
    with pytest.raises(ModelEditError, match="PROPOSAL_BULK_BLOCKED"):
        apply(p, workspace, event(status="rejected"), bulk=True)


def test_unknown_label_can_be_corrected_without_rewriting_original():
    from mcda_studio.domain.criteria import QualitativeValueFunction
    from mcda_studio.domain.scales import Scale, ScaleType

    p, intake = inputs()
    criterion = p.tree().node("cost")
    criterion.value_function = None
    criterion.scale = Scale(type=ScaleType.CATEGORICAL, labels=["low", "high"])
    criterion.value_function = QualitativeValueFunction(mapping={"low": 0, "high": 1})
    intake.project_fingerprint = p.fingerprint()
    intake.proposals[0].payload = CategoricalProposal(value="unknown", unit=None)
    workspace = svc.start(p, intake)
    assert "PROPOSAL_LABEL" in [i.code for i in svc.inspect(p, workspace).rows[0].issues]
    fixed = apply(
        p,
        workspace,
        event(status="corrected", payload=CategoricalProposal(value="high", unit=None)),
    ).workspace
    assert compile_(p, fixed).evidence.project.performance_index()["a", "cost"] == "high"
    assert fixed.intake.proposals[0].payload.value == "unknown"


def test_two_tools_and_human_comparisons_keep_original_and_effective_disagreements():
    from mcda_studio.domain.evidence import Claim, EvidenceDossier, Origin

    p, intake = inputs()
    second = intake.proposals[0].model_copy(deep=True)
    second.id, second.tool_id, second.payload.value = "quote_b", "external_b", 40.0
    intake.proposals.append(second)
    intake.human_dossier = EvidenceDossier(
        project_fingerprint=p.fingerprint(),
        claims=[
            Claim(
                id="human",
                alternative_id="a",
                criterion_id="cost",
                value=40,
                unit=None,
                source=intake.sources["brief"],
                origin=Origin(kind="human", proposed_by="Illustrative reviewer"),
            )
        ],
    )
    workspace = svc.start(p, intake)
    checked = svc.inspect(p, workspace, "tool:external_b")
    assert checked.rows[0].original_relation == "disagreement"
    assert svc.inspect(p, workspace, "human").rows[0].original_relation == "disagreement"
    fixed = apply(
        p,
        workspace,
        event(status="corrected", payload=NumericProposal(value=40, unit=None)),
        comparison_target="tool:external_b",
    )
    assert (
        fixed.rows[0].original_relation == "disagreement"
        and fixed.rows[0].effective_relation == "agreement"
    )
    columns = fixed.comparisons[0].columns
    assert [c.original_value for c in columns] == [30, 40, 40]
    assert [c.effective_value for c in columns] == [40, 40, 40]
    assert all(c.sources == ["local:invented-brief"] for c in columns)
    assert "PROPOSAL_DISAGREEMENT" in [q.code for q in fixed.questions]
    with pytest.raises(ValidationFailed, match="earlier active"):
        apply(p, fixed.workspace, event("quote_b"))
    removed = apply(p, fixed.workspace, event(status="rejected")).workspace
    selected = apply(p, removed, event("quote_b")).workspace
    assert len(compile_(p, selected).evidence.preview.changes) == 1


def test_tags_and_source_assertions_never_invent_measurements():
    p, intake = inputs()
    intake.proposals[0].subject.criterion_id = None
    intake.proposals[0].payload = AlternativeTag(namespace="risk", label="check", text="Follow up")
    other = intake.proposals[0].model_copy(deep=True)
    other.id = "assertion"
    other.payload = SuggestedSourceClaim(
        source_id="brief",
        assertion="A delivery is reported",
        excerpt="Illustrative quote",
        location="p1",
    )
    intake.proposals.append(other)
    workspace = svc.start(p, intake)
    reviewed = apply(p, workspace, event(), event("assertion"), bulk=True).workspace
    bundle = compile_(p, reviewed)
    assert bundle.evidence.project == p and bundle.evidence.preview.changes == []
    assert len(bundle.annotations) == 2
    assert bundle.workspace.intake == intake
    assert svc.verify(bundle) == bundle


def test_confidence_does_not_change_compiled_project_or_analytical_outputs():
    from mcda_studio.services import analysis_service

    p, intake = inputs()
    copies = []
    for confidence in (None, 0.01, 1.0):
        candidate = intake.model_copy(deep=True)
        if confidence is None:
            candidate.proposals[0].confidence = None
        else:
            candidate.proposals[0].confidence.value = confidence
        workspace = apply(p, svc.start(p, candidate), event()).workspace
        copies.append(compile_(p, workspace).evidence.project)
    assert all(to_json_text(c) == to_json_text(copies[0]) for c in copies)
    assert all(
        analysis_service.evaluate_project(c) == analysis_service.evaluate_project(copies[0])
        for c in copies
    )


def test_stale_project_and_acknowledgements_block_reviews_and_compilation():
    p, intake = inputs()
    workspace = svc.start(p, intake)
    current = svc.inspect(p, workspace)
    edited = p.model_copy(deep=True)
    edited.title = "Changed"
    assert svc.inspect(edited, workspace).stale
    assert svc.inspect(edited, workspace).workspace == workspace
    with pytest.raises(StaleRevisionError):
        apply(edited, workspace, event())
    unbound = imports.parse(edited, intake.model_dump_json())
    assert unbound.source_project is None and svc.inspect(edited, unbound).stale
    assert unbound.intake == intake
    with pytest.raises(StaleRevisionError):
        apply(edited, unbound, event())
    for review_digest, workspace_digest in (
        ("wrong", workspace.digest),
        (current.review_digest, "wrong"),
    ):
        with pytest.raises(StaleRevisionError):
            svc.review(p, workspace, [event()], review_digest, workspace_digest)
        with pytest.raises(StaleRevisionError):
            svc.compile_bundle(p, workspace, review_digest, workspace_digest)
    with pytest.raises(StaleRevisionError):
        svc.compile_bundle(edited, workspace, current.review_digest, workspace.digest)
    assert imports.parse(edited, workspace.model_dump_json()) == workspace


@pytest.mark.parametrize(
    "change", ["unsigned", "source", "history", "compiled", "annotations", "original"]
)
def test_tampered_resigned_bundles_and_history_are_refused(change):
    p, intake = inputs()
    bundle = compile_(p, apply(p, svc.start(p, intake), event()).workspace)
    if change == "unsigned":
        bundle.workspace.reviews[0].review.note = "Changed"
    elif change == "source":
        bundle.workspace.source_project.title = "Changed"
    elif change == "history":
        bundle.workspace.reviews[0].proposal_id = "unknown"
    elif change == "compiled":
        bundle.evidence.project.title = "Changed"
    elif change == "annotations":
        bundle.annotations = []  # next mutation alters an existing result instead
    elif change == "original":
        bundle.workspace.intake.proposals[0].payload.value = -2.0
    if change == "annotations":
        bundle.evidence.compiled_fingerprint = "0" * 64
    if change != "unsigned":
        bundle.workspace.digest = svc.workspace_digest(bundle.workspace)
        bundle.digest = evidence_service._digest(bundle.model_dump(mode="json", exclude={"digest"}))
    with pytest.raises((ModelEditError, ValidationFailed)):
        svc.verify(bundle)


@pytest.mark.parametrize(
    "change",
    [
        "version",
        "bool_version",
        "extra",
        "duplicate",
        "nonfinite",
        "bool_number",
        "numeric_string",
        "naive_time",
        "source_date",
        "numeric_time",
        "confidence",
        "missing_cell_subject",
    ],
)
def test_structural_import_is_atomic(change):
    p, intake = inputs()
    raw = intake.model_dump(mode="json")
    if change == "version":
        raw["schema_version"] = 2
    if change == "bool_version":
        raw["schema_version"] = True
    if change == "extra":
        raw["extra"] = "not allowed"
    if change == "duplicate":
        raw["proposals"] *= 2
    if change == "nonfinite":
        raw["proposals"][0]["payload"]["value"] = float("nan")
    if change == "bool_number":
        raw["proposals"][0]["payload"]["value"] = True
    if change == "numeric_string":
        raw["proposals"][0]["payload"]["value"] = "30"
    if change == "numeric_time":
        raw["proposals"][0]["run_at"] = 0
    if change == "source_date":
        raw["sources"]["brief"]["date"] = 0
    if change == "naive_time":
        raw["proposals"][0]["run_at"] = "2026-11-01T00:00:00"
    if change == "confidence":
        raw["proposals"][0]["confidence"]["value"] = 1.1
    if change == "missing_cell_subject":
        raw["proposals"][0]["subject"]["criterion_id"] = None
    before = copy.deepcopy(raw)
    with pytest.raises(ModelEditError):
        imports.parse(p, json.dumps(raw))
    if change != "nonfinite":
        assert raw == before


def test_csv_headers_lines_bad_fields_and_json_duplicates_are_refused():
    p, intake = inputs()
    text, registry = imports.csv_files(intake)
    for bad in (
        text.replace("schema_version,", "schema_version,schema_version,"),
        text.replace(",", ";"),
        text.replace("numeric_cell", "other_kind"),
    ):
        with pytest.raises(ModelEditError):
            imports.parse(p, bad, "csv", registry)
    with pytest.raises(ModelEditError, match="CSV line 2"):
        imports.parse(p, text.replace("external_a", ""), "csv", registry)
    with pytest.raises(ModelEditError, match="duplicate JSON"):
        imports.parse(p, '{"schema_version":1,"schema_version":1}')
    with pytest.raises(ModelEditError, match="registry"):
        imports.parse(p, text, "csv")


def test_file_string_proposal_and_history_limits_are_atomic(tmp_path):
    p, intake = inputs()
    with pytest.raises(ModelEditError, match="8 MB"):
        imports.parse(p, " " * 8_000_001)
    file = tmp_path / "large.json"
    file.write_bytes(b" " * 8_000_001)
    with pytest.raises(ModelEditError, match="8 MB"):
        imports.read_local(file)
    with pytest.raises(ModelEditError, match="10000"):
        imports.strict_json(json.dumps("a" * 10001))
    with pytest.raises(ModelEditError):
        imports.strict_json("[" * 40 + "0" + "]" * 40)
    raw = intake.model_dump(mode="json")
    raw["proposals"] = [dict(raw["proposals"][0], id=f"p{i}") for i in range(2001)]
    with pytest.raises(ModelEditError):
        imports.parse(p, json.dumps(raw))
    workspace = svc.start(p, intake)
    workspace.reviews = [event(status="rejected")] * 2000
    workspace.digest = svc.workspace_digest(workspace)
    before = workspace.model_dump_json()
    with pytest.raises(ModelEditError, match="2000"):
        apply(p, workspace, event())
    assert workspace.model_dump_json() == before


def test_review_selection_kind_primary_source_and_common_bulk_metadata():
    p, intake = inputs()
    workspace = svc.start(p, intake)
    with pytest.raises(ValidationFailed, match="primary"):
        e = event()
        e.review.primary_source_id = None
        apply(p, workspace, e)
    with pytest.raises(ModelEditError, match="CORRECTION_KIND"):
        apply(
            p,
            workspace,
            event(status="corrected", payload=CategoricalProposal(value="high", unit=None)),
        )
    for events in ([], [event(), event()], [event("missing")]):
        current = svc.inspect(p, workspace)
        with pytest.raises(ModelEditError):
            svc.review(p, workspace, events, current.review_digest, workspace.digest)
    other = intake.proposals[0].model_copy(deep=True)
    other.id, other.subject.alternative_id = "quote_b", "b"
    intake.proposals.append(other)
    workspace = svc.start(p, intake)
    e = event("quote_b")
    e.review.note = "Different"
    with pytest.raises(ModelEditError, match="BULK_METADATA"):
        apply(p, workspace, event(), e, bulk=True)
    assert workspace.reviews == []


def test_missing_local_registries_can_be_supplied_without_rewriting_intake_or_reviews():
    from mcda_studio.domain.external_proposals import ProposalRegistrySupply
    from proposal_builders import TIME

    p, intake = inputs()
    card = intake.model_cards.pop("card")
    source = intake.sources.pop("brief")
    workspace = svc.start(p, intake)
    rejected = apply(p, workspace, event(status="rejected")).workspace
    supply = ProposalRegistrySupply(
        sources={"brief": source},
        model_cards={"card": card},
        recorded_by="Illustrative reviewer",
        recorded_at=TIME,
    )
    supplemented = svc.supply_registries(p, rejected, supply, rejected.digest).workspace
    assert supplemented.intake == intake and supplemented.reviews == rejected.reviews
    assert svc.resolved_intake(supplemented).sources["brief"] == source
    accepted = apply(p, supplemented, event()).workspace
    assert compile_(p, accepted).evidence.project.performance_index()["a", "cost"] == 30
    assert svc.verify(compile_(p, accepted)).workspace == accepted
    changed = source.model_copy(deep=True)
    changed.description = "Replacement"
    with pytest.raises(ModelEditError, match="REGISTRY_REPLACE"):
        svc.supply_registries(
            p,
            accepted,
            ProposalRegistrySupply(
                sources={"brief": changed}, recorded_by="Illustrative reviewer", recorded_at=TIME
            ),
            accepted.digest,
        )


def test_unit_correction_and_explicit_source_measurement_preserve_original_inputs():
    from mcda_studio.domain.external_proposals import ProposedMeasurement

    p, intake = inputs()
    intake.proposals[0].payload.unit = "wrong"
    fixed = apply(
        p,
        svc.start(p, intake),
        event(status="corrected", payload=NumericProposal(value=31, unit=None)),
    ).workspace
    assert compile_(p, fixed).evidence.project.performance_index()["a", "cost"] == 31
    assert fixed.intake.proposals[0].payload.unit == "wrong"
    p, intake = inputs()
    intake.proposals[0].payload = SuggestedSourceClaim(
        source_id="brief",
        assertion="Reported measurement",
        excerpt="Invented value 39",
        location="table 1",
        measurement=ProposedMeasurement(value=39, unit=None),
    )
    workspace = apply(p, svc.start(p, intake), event()).workspace
    bundle = compile_(p, workspace)
    assert bundle.evidence.project.performance_index()["a", "cost"] == 39
    assert bundle.annotations[0].payload.assertion == "Reported measurement"


def test_partially_valid_csv_never_imports_the_valid_subset():
    p, intake = inputs()
    second = intake.proposals[0].model_copy(deep=True)
    second.id = "quote_b"
    intake.proposals.append(second)
    text, registry = imports.csv_files(intake)
    lines = text.splitlines(keepends=True)
    lines[2] = lines[2].replace("external_a", "")
    with pytest.raises(ModelEditError, match="CSV line 3"):
        imports.parse(p, "".join(lines), "csv", registry)
    assert len(intake.proposals) == 2


def test_bulk_history_limit_refuses_every_selected_event_atomically():
    p, intake = inputs()
    other = intake.proposals[0].model_copy(deep=True)
    other.id, other.subject.alternative_id = "quote_b", "b"
    intake.proposals.append(other)
    workspace = svc.start(p, intake)
    workspace.reviews = [event(status="rejected")] * 1999
    workspace.digest = svc.workspace_digest(workspace)
    before = workspace.model_dump_json()
    with pytest.raises(ModelEditError, match="2000"):
        apply(p, workspace, event(), event("quote_b"), bulk=True)
    assert workspace.model_dump_json() == before


def test_mixed_comparison_keeps_agreement_separate_from_incomparability():
    p, intake = inputs()
    same = intake.proposals[0].model_copy(deep=True)
    same.id, same.tool_id = "same", "external_b"
    incompatible = same.model_copy(deep=True)
    incompatible.id, incompatible.payload.unit = "different_unit", "other"
    intake.proposals.extend([same, incompatible])
    current = svc.inspect(p, svc.start(p, intake), "tool:external_b")
    first = next(r for r in current.rows if r.original.id == "quote_a")
    assert first.original_relation == "mixed"
    assert first.original_relations == ["agreement", "incomparable"]
    assert "disagreement" not in first.original_relations


def test_corrected_source_assertion_with_new_measurement_keeps_absence_distinct():
    from mcda_studio.domain.external_proposals import ProposedMeasurement

    p, intake = inputs()
    intake.proposals[0].payload = SuggestedSourceClaim(
        source_id="brief",
        assertion="Reported value",
        excerpt="Unquantified original",
        location="p1",
    )
    other = intake.proposals[0].model_copy(deep=True)
    other.id, other.tool_id = "numeric", "external_b"
    other.payload = NumericProposal(value=39, unit=None)
    intake.proposals.append(other)
    workspace = svc.start(p, intake)
    corrected = SuggestedSourceClaim(
        source_id="brief",
        assertion="Reported value",
        excerpt="Reviewed explicit 39",
        location="p1",
        measurement=ProposedMeasurement(value=39, unit=None),
    )
    current = apply(
        p,
        workspace,
        event(status="corrected", payload=corrected),
        comparison_target="tool:external_b",
    )
    row = next(r for r in current.rows if r.original.id == "quote_a")
    assert row.original_relations == ["incomparable"] and row.effective_relations == ["agreement"]
    column = next(c for c in current.comparisons[0].columns if c.id == "quote_a")
    assert column.original_value is None and column.effective_value == 39
    assert "PROPOSAL_INCOMPARABLE" in [q.code for q in current.questions]
    assert "PROPOSAL_DISAGREEMENT" not in [q.code for q in current.questions]
    assert compile_(p, current.workspace).evidence.project.performance_index()["a", "cost"] == 39
