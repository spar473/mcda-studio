"""Version-2 decision records cite verified artifacts, trace measurements and link revisions."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from mcda_studio.domain.decision import DecisionDetails, DecisionDraft
from mcda_studio.domain.derived import DerivedFormula, DerivedModel, SourceFactor
from mcda_studio.domain.errors import ModelEditError, ValidationFailed
from mcda_studio.domain.evidence import EvidenceDossier, Origin, Review, Source
from mcda_studio.domain.evidence_workspace import ClaimReview
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.requirements import BoundRequirement
from mcda_studio.services import decision_record_service as svc
from mcda_studio.services import decision_service, derived_service, project_service
from mcda_studio.services import evidence_compilation_service as evidence_compilation
from mcda_studio.services import evidence_workspace_service as workspaces
from mcda_studio.services import provenance_service as provenance
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text

ROOT = Path(__file__).parents[2]
WHEN = datetime(2026, 11, 1, tzinfo=UTC)


def supplier():
    return JsonProjectRepository().load(ROOT / "examples/supplier_qualification/project.json")


def evidence_bundle(p=None):
    p = p or supplier()
    d = EvidenceDossier.model_validate_json(
        (ROOT / "examples/evidence_demo/supplier.json").read_text()
    )
    current = workspaces.inspect(p, d)
    review = Review(status="rejected", reviewer="Analyst", reviewed_at=WHEN)
    current = workspaces.propose_review(
        p,
        current.workspace,
        ClaimReview(claim_id="unreviewed_example", review=review),
        current.preview.review_digest,
    )
    return evidence_compilation.compilation_bundle(
        p, current.workspace, current.preview.review_digest, current.workspace.digest
    )


def calculation_on(project):
    """A synthetic, explicitly reviewed model bound to ``project`` (test setup, not a rebind)."""
    accepted = Review(status="accepted", reviewer="Analyst", reviewed_at=WHEN)
    origin = Origin(kind="human", proposed_by="Analyst")
    source = Source(name="Quote", reference="local:q", date=date(2026, 10, 31), description="x")
    model = DerivedModel(
        project_fingerprint=project.fingerprint(),
        units={"NZD": {"NZD": 1}},
        sources=[
            SourceFactor(
                id="quote", value=39, unit="NZD", source=source, origin=origin, review=accepted
            )
        ],
        formulas=[
            DerivedFormula(
                id="brightline_price",
                expression="quote",
                unit="NZD",
                origin=origin,
                review=accepted,
                alternative_id="brightline",
                criterion_id="unit_price",
            )
        ],
    )
    preview = derived_service.preview(project, model)
    return derived_service.compilation_bundle(project, model, preview.review_digest)


def details(**changes):
    base = DecisionDetails(
        owner="Decision owner",
        date=date(2026, 11, 1),
        outcome="selected",
        selected_alternative_id="apex",
        alternatives_considered=["apex", "brightline", "cobalt", "delta", "evergreen"],
        rationale="Best value within the qualification classes",
        configurations=[
            AnalysisConfiguration(method="mavt"),
            AnalysisConfiguration(method="smaa2"),
        ],
        unresolved_assumptions=["Freight costs stay flat"],
        review_triggers=["New quotation"],
    )
    return base.model_copy(update=changes)


def cite(artifact, receipt=None):
    return svc.SupportingArtifact(artifact=artifact, copy_receipt=receipt)


def test_record_traces_evidence_and_reopens(tmp_path):
    bundle = evidence_bundle()
    project = bundle.project
    before = to_json_text(project)
    record = svc.create(project, details(), [cite(bundle)])
    assert to_json_text(project) == before
    assert record.project == project and record.project_fingerprint == project.fingerprint()
    [anchor] = record.anchors
    assert (anchor.relationship, anchor.anchored_to) == ("compiled", "record_project")
    traced = {(t.alternative_id, t.criterion_id): t for t in record.measurement_trace}
    apex = traced[("apex", "unit_price")]
    assert (apex.origin, apex.reference_id, apex.value, apex.original_value) == (
        "evidence",
        "reviewed_example",
        40,
        42,
    )
    assert apex.artifact_digest == bundle.digest
    assert traced[("brightline", "unit_price")].origin == "entered"
    path = tmp_path / "record.json"
    path.write_text(record.model_dump_json())
    reopened = svc.DecisionRecordV2.model_validate_json(path.read_text())
    assert svc.verify(reopened) == record
    assert svc.inspect(project, reopened).current_project_matches


def test_unavailable_analyses_are_recorded_not_dropped():
    bundle = evidence_bundle()
    record = svc.create(bundle.project, details(), [cite(bundle)])
    mavt, smaa = record.analyses
    assert mavt.status == "completed" and mavt.record is not None
    assert mavt.record.result.project_fingerprint == record.project_fingerprint
    assert smaa.status == "unavailable" and smaa.record is None and smaa.issues
    assert smaa.reason.startswith("[")
    codes = [n.code for n in record.notices]
    assert "DECISION_ANALYSIS_UNAVAILABLE" in codes
    assert "DECISION_MEASUREMENTS_WITHOUT_ARTIFACT" in codes


def test_considered_alternatives_do_not_change_the_analysis_universe():
    p = supplier()
    record = svc.create(
        p,
        details(alternatives_considered=["apex", "cobalt"], configurations=[
            AnalysisConfiguration(method="mavt")
        ]),
    )  # fmt: skip
    ranked = record.analyses[0].record.result.ranking
    assert {r.alternative_id for r in ranked} == set(p.alternative_ids())
    assert "DECISION_ANALYSIS_UNIVERSE" in [n.code for n in record.notices]
    with pytest.raises(ValidationFailed, match="DECISION_UNKNOWN_ALTERNATIVE"):
        svc.create(p, details(alternatives_considered=["apex", "absent"]))


def test_outcome_rules_and_deferral():
    deferred = svc.create(supplier(), details(outcome="deferred", selected_alternative_id=None))
    assert deferred.decision.selected_alternative_id is None
    with pytest.raises(ValueError):
        DecisionDetails.model_validate({**details().model_dump(), "outcome": "deferred"})
    with pytest.raises(ValueError):
        DecisionDetails.model_validate(
            {**details().model_dump(), "alternatives_considered": ["cobalt"]}
        )
    with pytest.raises(ValueError):
        DecisionDetails.model_validate(
            {**details().model_dump(), "configurations": [{"method": "mavt"}] * 2}
        )


def test_failed_and_unresolved_requirements_are_surfaced_beside_the_choice():
    p = supplier()
    p.requirements = [
        BoundRequirement(id="price_cap", name="Price cap", criterion_id="unit_price",
                         unit="NZD", maximum=41),
    ]  # fmt: skip
    record = svc.create(p, details(configurations=[AnalysisConfiguration(method="mavt")]))
    assert record.feasibility.status == "checked"
    apex = next(a for a in record.feasibility.result.alternatives if a.alternative_id == "apex")
    assert apex.status == "fail"  # 42 > 41: shown, never overridden
    assert "DECISION_SELECTED_FAILS_REQUIREMENT" in [n.code for n in record.notices]
    p = project_service.clear_performance(p, "apex", "unit_price")
    unresolved = svc.create(p, details(configurations=[AnalysisConfiguration(method="mavt")]))
    assert "DECISION_SELECTED_UNRESOLVED_REQUIREMENT" in [n.code for n in unresolved.notices]
    assert unresolved.analyses[0].status == "unavailable"  # missing is not zero


def test_imported_copy_needs_its_receipt():
    bundle = evidence_bundle()
    copy = project_service.duplicate_project(bundle.project, title=bundle.project.title)
    receipt = provenance.copy_receipt(bundle.project, copy)
    with pytest.raises(ModelEditError, match="DECISION_ARTIFACT_UNRELATED"):
        svc.create(copy, details(), [cite(bundle)])
    record = svc.create(copy, details(), [cite(bundle, receipt)])
    assert record.anchors[0].relationship == "verified_copy"
    assert record.project_fingerprint != bundle.compiled_fingerprint
    edited = project_service.update_project_details(copy, description="changed")
    with pytest.raises(ModelEditError, match="DECISION_RECEIPT_UNMATCHED"):
        svc.create(edited, details(), [cite(bundle, receipt)])


@pytest.mark.parametrize("order", ["evidence_first", "calculation_first"])
def test_calculation_on_compiled_evidence_traces_both_artifacts(order):
    evidence = evidence_bundle()
    calculation = calculation_on(evidence.project)
    cited = [cite(evidence), cite(calculation)]
    if order == "calculation_first":
        cited.reverse()
    record = svc.create(calculation.project, details(), cited)
    assert [(a.artifact_digest, a.anchored_to) for a in record.anchors] == [
        (calculation.digest, "record_project"),
        (evidence.digest, "artifact_source"),
    ]
    assert record.anchors[1].anchor_artifact_digest == calculation.digest
    traced = {(t.alternative_id, t.criterion_id): t for t in record.measurement_trace}
    assert traced[("apex", "unit_price")].origin == "evidence"
    calc = traced[("brightline", "unit_price")]
    assert (calc.origin, calc.reference_id, calc.inputs, calc.value) == (
        "calculation",
        "brightline_price",
        ["quote"],
        39,
    )
    assert calc.original_value == supplier().performance_index()[("brightline", "unit_price")]
    # Evidence alone does not compile the calculated project.
    with pytest.raises(ModelEditError, match="DECISION_ARTIFACT_UNRELATED"):
        svc.create(calculation.project, details(), [cite(evidence)])
    with pytest.raises(ModelEditError, match="DECISION_DUPLICATE_ARTIFACT"):
        svc.create(calculation.project, details(), [cite(calculation), cite(calculation)])


def test_revisions_link_predecessors_and_leave_them_unchanged():
    p = supplier()
    first = svc.create(p, details())
    original = first.model_dump_json()
    changed = details(unresolved_assumptions=["Freight costs rise 10%"])
    second = svc.create(p, changed, previous=first)
    assert second.previous_digest == first.digest and second.predecessor.digest == first.digest
    assert second.predecessor.rationale == first.decision.rationale
    assert first.model_dump_json() == original
    assert svc.inspect(p, second, first).predecessor_verified is True
    with pytest.raises(ModelEditError, match="DECISION_PREDECESSOR_MISMATCH"):
        svc.inspect(p, second, svc.create(p, details(rationale="Unrelated")))
    rewritten = second.model_copy(deep=True)
    rewritten.predecessor.rationale = "A different history"
    rewritten.digest = svc.digest(rewritten)
    assert svc.verify(rewritten)  # a consistent re-signed summary needs the predecessor file
    with pytest.raises(ModelEditError, match="DECISION_PREDECESSOR_MISMATCH"):
        svc.inspect(p, rewritten, first)
    tampered = first.model_copy(deep=True)
    tampered.decision.rationale = "Rewritten"
    with pytest.raises(ModelEditError, match="DECISION_INVALID_PREDECESSOR"):
        svc.create(p, changed, previous=tampered)
    other = project_service.duplicate_project(p)
    with pytest.raises(ModelEditError, match="DECISION_DIFFERENT_PROJECT"):
        svc.create(other, changed, previous=first)


def test_version_one_records_remain_readable_and_revisable():
    p = supplier()
    draft = DecisionDraft(
        owner="Analyst",
        date=date(2026, 10, 31),
        chosen_alternative_id="apex",
        rationale="Earlier CLI record",
        configurations=[AnalysisConfiguration(method="mavt")],
    )
    v1 = decision_service.create(p, draft)
    assert svc.inspect(p, v1).record == v1
    revision = svc.create(p, details(), previous=v1)
    assert revision.predecessor.version == 1 and revision.previous_digest == v1.digest
    assert svc.inspect(p, revision, v1).predecessor_verified is True
    v1.decision.rationale = "tampered"
    with pytest.raises(ModelEditError, match="DECISION_RECORD_CHANGED"):
        svc.inspect(p, v1)


def test_historical_record_survives_later_project_edits():
    bundle = evidence_bundle()
    record = svc.create(bundle.project, details(), [cite(bundle)])
    edited = project_service.set_performance(bundle.project, "apex", "unit_price", 39)
    opened = svc.inspect(edited, record)
    assert not opened.current_project_matches and opened.record == record
    assert opened.record.project.performance_index()[("apex", "unit_price")] == 40


@pytest.mark.parametrize(
    "tamper", ["unsigned", "trace", "notice", "analysis", "artifact", "link", "anchor"]
)
def test_tampered_records_are_refused_even_when_resigned(tamper):
    p = supplier()
    bundle = evidence_bundle(p)
    first = svc.create(bundle.project, details())
    record = svc.create(bundle.project, details(), [cite(bundle)], first)
    if tamper == "unsigned":
        record.decision.rationale = "Changed afterwards"
    elif tamper == "trace":
        record.measurement_trace[0].original_value = 1
    elif tamper == "notice":
        record.notices = []
    elif tamper == "analysis":
        record.analyses[0].record.result.ranking[0].value = 0.99
    elif tamper == "artifact":
        record.supporting_artifacts[0].artifact.project.title = "Other"
    elif tamper == "link":
        record.previous_digest = "0" * 64
    else:
        record.anchors[0].relationship = "verified_copy"
    if tamper != "unsigned":
        record.digest = svc.digest(record)
    with pytest.raises(ValidationFailed if tamper == "analysis" else ModelEditError):
        svc.verify(record)


def codes(exc):
    return {i.code for i in exc.value.report.issues}


def with_requirement(p):
    p.requirements = [
        BoundRequirement(id="price_cap", name="Price cap", criterion_id="unit_price",
                         unit="NZD", maximum=50),
    ]  # fmt: skip
    return p


def unknown(record, field):
    d = record.decision.model_dump()
    if field == "considered":
        d["alternatives_considered"] = [*d["alternatives_considered"], "ghost"]
    else:
        d["alternatives_considered"] = [*d["alternatives_considered"], "ghost"]
        d["selected_alternative_id"] = "ghost"
    record.decision = DecisionDetails.model_validate(d)
    record.digest = svc.digest(record)
    return record


@pytest.mark.parametrize("requirements", [False, True])
@pytest.mark.parametrize("field", ["considered", "selected"])
def test_unknown_alternatives_are_validation_errors_on_create_and_reopen(field, requirements):
    p = with_requirement(supplier()) if requirements else supplier()
    expected = {"DECISION_UNKNOWN_ALTERNATIVE"} | (
        {"DECISION_UNKNOWN_SELECTION"} if field == "selected" else set()
    )
    bad = unknown(svc.create(p, details()), field).decision
    with pytest.raises(ValidationFailed) as created:
        svc.create(p, bad)
    assert codes(created) == expected
    record = unknown(svc.create(p, details()), field)
    with pytest.raises(ValidationFailed) as reopened:
        svc.verify(record)
    assert codes(reopened) == expected
    with pytest.raises(ValidationFailed):
        svc.inspect(p, record)
    with pytest.raises(ValidationFailed):  # a predecessor must verify fully
        svc.create(p, details(), previous=record)


@pytest.mark.parametrize(
    "tamper,code",
    [
        ("missing", "DECISION_ANALYSIS_RECORD_MISSING"),
        ("unavailable_with_record", "DECISION_ANALYSIS_STATUS"),
        ("unavailable_without_reason", "DECISION_ANALYSIS_STATUS"),
        ("completed_with_reason", "DECISION_ANALYSIS_STATUS"),
        ("swapped_records", "DECISION_ANALYSIS_SUBSTITUTED"),
        ("other_method", "DECISION_ANALYSIS_SUBSTITUTED"),
        ("snapshot_configuration", "DECISION_ANALYSIS_CONFIGURATION"),
        ("declared_configuration", "DECISION_ANALYSIS_CONFIGURATION"),
        ("dropped", "DECISION_ANALYSIS_COUNT"),
    ],
)
def test_snapshots_must_match_status_and_declared_configuration(tamper, code):
    p = supplier()
    configurations = [
        AnalysisConfiguration(method="mavt"),
        AnalysisConfiguration(method="mavt", weight_profile_id=p.weight_profiles[1].id),
        AnalysisConfiguration(method="smaa2"),
    ]
    record = svc.create(p, details(configurations=configurations))
    first, second, third = record.analyses
    assert (first.status, second.status, third.status) == ("completed", "completed", "unavailable")
    if tamper == "missing":
        first.record = None
    elif tamper == "unavailable_with_record":
        third.record = first.record
    elif tamper == "unavailable_without_reason":
        third.reason = ""
    elif tamper == "completed_with_reason":
        first.reason = "invented"
    elif tamper == "swapped_records":
        # Each sealed record still verifies by its own digest; only the pairing is wrong.
        first.record, second.record = second.record, first.record
    elif tamper == "other_method":
        first.record = (
            svc.create(p, details(configurations=[AnalysisConfiguration(method="mavt_sorting")]))
            .analyses[0]
            .record
        )
    elif tamper == "snapshot_configuration":
        first.configuration = AnalysisConfiguration(method="mavt", scenario_id="unknown")
    elif tamper == "declared_configuration":
        d = record.decision.model_dump()
        d["configurations"][0]["weight_profile_id"] = p.weight_profiles[1].id
        d["configurations"][1]["weight_profile_id"] = None
        record.decision = DecisionDetails.model_validate(d)
    else:
        record.analyses = record.analyses[:2]
    record.digest = svc.digest(record)
    with pytest.raises(ValidationFailed) as refused:
        svc.verify(record)
    assert code in codes(refused)


def test_version_one_records_with_unknown_choices_are_refused():
    p = supplier()
    draft = DecisionDraft(
        owner="Analyst",
        date=date(2026, 10, 31),
        chosen_alternative_id="apex",
        rationale="Earlier CLI record",
        configurations=[AnalysisConfiguration(method="mavt")],
    )
    v1 = decision_service.create(p, draft)
    v1.decision.chosen_alternative_id = "ghost"
    v1.digest = decision_service.digest(v1)
    with pytest.raises(ValidationFailed) as refused:
        svc.inspect(p, v1)
    assert codes(refused) == {"DECISION_UNKNOWN_SELECTION"}
    with pytest.raises(ValidationFailed):
        svc.create(p, details(), previous=v1)
