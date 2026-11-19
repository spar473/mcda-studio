"""Calculation workspace: append-only authoring history, explicit review and exact applications."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mcda_studio.domain.calculation_workspace import (
    ApplyCalculation,
    CalculationWorkspace,
    DefineFormula,
    DefineSource,
    DefineUnit,
    Rebind,
    RemoveEntry,
    ReviewEntry,
)
from mcda_studio.domain.derived import DerivedFormula, DerivedModel, SourceFactor
from mcda_studio.domain.errors import ModelEditError, StaleRevisionError, ValidationFailed
from mcda_studio.domain.evidence import Origin, Review, Source
from mcda_studio.services import calculation_workspace_service as cw
from mcda_studio.services import derived_service as derived
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository

EXAMPLE = Path(__file__).parents[2] / "examples/derived_measurements"
WHEN = datetime(2026, 11, 1, 9, tzinfo=UTC)
HUMAN = Origin(kind="human", proposed_by="Analyst")
SOURCE = Source(name="Note", reference="local:note", date="2026-11-01", description="Synthetic")


def venture():
    p = JsonProjectRepository().load(EXAMPLE / "venture-project.json")
    return p, DerivedModel.model_validate_json((EXAMPLE / "venture-model.json").read_text())


def blank(p):
    return cw.inspect(p, DerivedModel(project_fingerprint=p.fingerprint()))


def review(status="accepted", corrected=None, reviewer="Analyst"):
    return Review(status=status, reviewer=reviewer, reviewed_at=WHEN, corrected_value=corrected)


def factor(fid, value, unit="1", origin=HUMAN):
    return SourceFactor(id=fid, value=value, unit=unit, source=SOURCE, origin=origin)


def formula(fid, expression, unit="1", alternative=None, criterion=None):
    return DerivedFormula(
        id=fid,
        expression=expression,
        unit=unit,
        origin=HUMAN,
        alternative_id=alternative,
        criterion_id=criterion,
    )


def step(p, current, event):
    return cw.propose(p, current.workspace, event, current.preview.review_digest)


def run(p, current, *events):
    for event in events:
        current = step(p, current, event)
    return current


def build_market(p):
    """The venture market model authored from blank, through the interface's events only."""
    units = [
        DefineUnit(unit="customers", dimension={"customer": 1}, recorded_by="A", recorded_at=WHEN),
        DefineUnit(
            unit="NZD/customer/year",
            dimension={"NZD": 1, "customer": -1, "year": -1},
            recorded_by="A",
            recorded_at=WHEN,
        ),
        DefineUnit(
            unit="NZD/year", dimension={"NZD": 1, "year": -1}, recorded_by="A", recorded_at=WHEN
        ),
    ]
    factors = [
        factor("customers", 10000, "customers"),
        factor("adoption_a", 0.05),
        factor("adoption_b", 0.08),
        factor("price_a", 1200, "NZD/customer/year"),
        factor("price_b", 800, "NZD/customer/year"),
    ]
    events = [*units, *(DefineSource(factor=f, recorded_at=WHEN) for f in factors)]
    events += [ReviewEntry(entry="source", id=f.id, review=review()) for f in factors]
    formulas = [
        formula(f"m_{alt}", f"customers * adoption_{alt} * price_{alt}", "NZD/year", alt, "result")
        for alt in ("a", "b")
    ]
    events += [DefineFormula(formula=f, recorded_at=WHEN) for f in formulas]
    events += [ReviewEntry(entry="formula", id=f.id, review=review()) for f in formulas]
    return run(p, blank(p), *events)


def test_authoring_from_blank_matches_the_example_calculation():
    p, model = venture()
    authored = build_market(p)
    example = derived.preview(p, model)
    assert authored.relationship == "bound" and authored.applicable
    assert [(c.formula_id, c.after) for c in authored.changes] == [
        ("m_a", example.calculations[0].value),
        ("m_b", example.calculations[1].value),
    ]
    assert [c.status for c in authored.checks] == ["calculates", "calculates"]
    uses = {u.factor_id: u for u in authored.factor_uses}
    assert uses["customers"].shared and uses["customers"].alternative_ids == ["a", "b"]
    assert not uses["adoption_a"].shared and uses["adoption_a"].formula_ids == ["m_a"]


def test_revising_a_factor_leaves_it_pending_and_keeps_history():
    p, model = venture()
    current = cw.inspect(p, model)
    revised = factor("adoption_a", 0.06)
    revised.unit, revised.source = "1", model.sources[1].source
    pending = step(p, current, DefineSource(factor=revised, recorded_at=WHEN))
    assert [i.code for i in pending.preview.issues] == ["DERIVED_UNREVIEWED_SOURCE"]
    assert not pending.applicable and [c.formula_id for c in pending.changes] == ["market_b"]
    # Formula reviews are about expressions, not values: they are kept.
    assert all(f.review and f.review.status == "accepted" for f in pending.model.formulas)
    # The earlier accepted definition remains in the original model, the new one is an event.
    assert pending.workspace.original_model.sources[1].value == 0.05
    assert pending.workspace.original_model.sources[1].review.status == "accepted"
    assert pending.model.sources[1].value == 0.06 and pending.model.sources[1].review is None
    accepted = step(p, pending, ReviewEntry(entry="source", id="adoption_a", review=review()))
    assert [(c.formula_id, c.changed) for c in accepted.changes] == [
        ("market_a", True),
        ("market_b", True),
    ]
    # Usage is static, so it is known even while the factor is pending.
    assert {u.factor_id: u.formula_ids for u in pending.factor_uses}["adoption_a"] == ["market_a"]


def test_applying_reproduces_compilation_and_survives_reopening():
    p, model = venture()
    current = cw.inspect(p, model)
    applied = cw.apply(p, current.workspace, current.preview.review_digest, "Analyst", WHEN)
    compiled = derived.compile_copy(p, model, current.preview.review_digest)
    assert applied.bundle.project == compiled
    assert applied.project_fingerprint == compiled.fingerprint()
    assert [(a.alternative_id, a.value) for a in applied.assignments] == [
        ("a", 600000.0),
        ("b", 640000.0),
    ]
    edited = p
    for a in applied.assignments:
        edited = ps.set_performance(edited, a.alternative_id, a.criterion_id, a.value)
    assert edited.fingerprint() == applied.project_fingerprint  # the editor's batch is exact
    workspace = applied.inspection.workspace
    assert isinstance(workspace.events[-1], ApplyCalculation)
    reopened = cw.inspect(
        edited, CalculationWorkspace.model_validate_json(workspace.model_dump_json())
    )
    assert reopened.relationship == "bound" and not reopened.applicable
    assert reopened.bindings == [p.fingerprint(), edited.fingerprint()]
    assert derived.verify_bundle(applied.bundle) == applied.bundle


def test_undo_redo_and_explicit_rebinding():
    p, model = venture()
    current = cw.inspect(p, model)
    applied = cw.apply(p, current.workspace, current.preview.review_digest, "Analyst", WHEN)
    workspace = applied.inspection.workspace
    undone = cw.inspect(p, workspace)  # the editor undid the application
    assert undone.relationship == "earlier" and not undone.applicable and not undone.checks
    with pytest.raises(StaleRevisionError):
        step(p, undone, ReviewEntry(entry="source", id="adoption_a", review=review()))
    assert cw.inspect(applied.bundle.project, workspace).relationship == "bound"  # redo
    renamed = ps.rename_project(applied.bundle.project, "Renamed")
    different = cw.inspect(renamed, workspace)
    assert different.relationship == "different"
    with pytest.raises(ModelEditError, match="CALCULATION_REBIND_PROJECT"):
        step(renamed, different, Rebind(project=p, recorded_by="A", recorded_at=WHEN))
    rebound = step(renamed, different, Rebind(project=renamed, recorded_by="A", recorded_at=WHEN))
    assert rebound.relationship == "bound" and len(rebound.bindings) == 3
    with pytest.raises(ModelEditError, match="CALCULATION_REBIND_SAME"):
        step(renamed, rebound, Rebind(project=renamed, recorded_by="A", recorded_at=WHEN))
    other = renamed.model_copy(update={"id": "other"})
    crafted = rebound.workspace.model_copy(deep=True)
    crafted.events[-1] = Rebind(project=other, recorded_by="A", recorded_at=WHEN)
    crafted.digest = cw.workspace_digest(crafted)
    with pytest.raises(ModelEditError, match="CALCULATION_REBIND_PROJECT"):
        cw.inspect(other, crafted)


def test_formula_acceptance_requires_a_valid_calculation_with_explanations():
    p, _ = venture()
    current = build_market(p)
    wrong_unit = formula("wrong", "customers * adoption_a", "NZD/year")
    mixed = formula("mixed", "customers + adoption_a", "customers")
    upstream = formula("upstream", "wrong * 2", "NZD/year")
    current = run(
        p,
        current,
        *(DefineFormula(formula=f, recorded_at=WHEN) for f in (wrong_unit, mixed, upstream)),
    )
    checks = {c.formula_id: c for c in current.checks}
    assert checks["wrong"].issue.code == "DERIVED_OUTPUT_DIMENSION"
    assert checks["wrong"].explanation == (
        "The expression gives customer, but the declared unit is NZD × year^-1."
    )
    assert checks["mixed"].explanation == (
        "Only quantities with the same dimensions can be added, subtracted or compared: "
        "customer and dimensionless."
    )
    assert checks["upstream"].explanation.startswith("Accept its inputs first")
    assert checks["m_a"].explanation == (
        "Calculates 600000 NZD/year; its dimensions (NZD × year^-1) match the declared unit."
    )
    assert checks["upstream"].references == ["wrong"]
    for fid in ("wrong", "mixed"):
        with pytest.raises(ModelEditError, match="CALCULATION_ACCEPT_INVALID"):
            step(p, current, ReviewEntry(entry="formula", id=fid, review=review()))
    rejected = step(p, current, ReviewEntry(entry="formula", id="wrong", review=review("rejected")))
    assert rejected.model.formulas[2].review.status == "rejected"
    # Unreviewed draft formulas are errors in the authoritative preview, so nothing is applicable.
    assert not current.applicable
    # Dimension explanations never alter the digested preview issues.
    issue = next(i for i in current.preview.issues if i.path == "formulas[wrong]")
    assert issue.message == "formula 'wrong' requires acceptance"


def test_errors_inside_a_dependency_name_that_dependency():
    p, _ = venture()
    current = build_market(p)
    current = run(
        p,
        current,
        DefineFormula(formula=formula("inner", "customers + adoption_a", "1"), recorded_at=WHEN),
    )
    current = run(
        p,
        current,
        DefineFormula(formula=formula("outer", "inner * 2", "1"), recorded_at=WHEN),
    )
    crafted = current.workspace.model_copy(deep=True)
    crafted.events.append(ReviewEntry(entry="formula", id="inner", review=review()))
    crafted.digest = cw.workspace_digest(crafted)
    # A crafted acceptance replays (acceptance checks guard proposals), but never calculates.
    opened = cw.inspect(p, crafted)
    outer = next(c for c in opened.checks if c.formula_id == "outer")
    assert outer.explanation.startswith("In inner: only quantities with the same dimensions")
    assert "formulas[inner]" in {i.path for i in opened.preview.issues}


@pytest.mark.parametrize(
    ("event", "code"),
    [
        (DefineUnit(unit="1", dimension={}, recorded_by="A", recorded_at=WHEN), "UNIT_RESERVED"),
        (
            DefineUnit(unit="customers", dimension={"x": 1}, recorded_by="A", recorded_at=WHEN),
            "UNIT_EXISTS",
        ),
        (DefineSource(factor=factor("market_a", 1), recorded_at=WHEN), "ID_IN_USE"),
        (DefineFormula(formula=formula("adoption_a", "1"), recorded_at=WHEN), "ID_IN_USE"),
        (ReviewEntry(entry="source", id="absent", review=review()), "REVIEW_ENTRY"),
        (
            ReviewEntry(entry="formula", id="market_a", review=review("corrected", 1.0)),
            "FORMULA_CORRECTION",
        ),
        (
            ReviewEntry(entry="source", id="adoption_a", review=review("corrected", "high")),
            "CORRECTION_VALUE",
        ),
        (RemoveEntry(entry="formula", id="absent", recorded_by="A", recorded_at=WHEN), "REMOVE"),
    ],
)
def test_invalid_events_are_refused_on_proposal_and_on_replay(event, code):
    p, model = venture()
    current = cw.inspect(p, model)
    with pytest.raises(ModelEditError, match=f"CALCULATION_{code}"):
        step(p, current, event)
    crafted = current.workspace.model_copy(deep=True)
    crafted.events.append(event)
    crafted.digest = cw.workspace_digest(crafted)
    with pytest.raises(ModelEditError, match=f"CALCULATION_{code}.*event 0"):
        cw.inspect(p, crafted)


def test_definitions_never_carry_their_own_review():
    p, model = venture()
    current = cw.inspect(p, model)
    reviewed = factor("adoption_a", 0.9)
    reviewed.review = review()
    with pytest.raises(ModelEditError, match="CALCULATION_DEFINITION_REVIEWED"):
        step(p, current, DefineSource(factor=reviewed, recorded_at=WHEN))
    blank_value = factor("unknown", None)
    pending = step(p, current, DefineSource(factor=blank_value, recorded_at=WHEN))
    with pytest.raises(ModelEditError, match="CALCULATION_ACCEPT_MISSING"):
        step(p, pending, ReviewEntry(entry="source", id="unknown", review=review()))
    corrected = step(
        p, pending, ReviewEntry(entry="source", id="unknown", review=review("corrected", 0.0))
    )
    assert corrected.model.sources[-1].review.corrected_value == 0.0
    with pytest.raises(ModelEditError, match="CALCULATION_PERSON"):
        step(p, pending, ReviewEntry(entry="source", id="unknown", review=review(reviewer=" ")))


def test_tampered_and_resigned_histories_are_refused():
    p, model = venture()
    current = cw.inspect(p, model)
    applied = cw.apply(p, current.workspace, current.preview.review_digest, "Analyst", WHEN)
    workspace = applied.inspection.workspace
    unsigned = workspace.model_copy(deep=True)
    unsigned.events[-1].recorded_by = "Someone else"
    with pytest.raises(ModelEditError, match="CALCULATION_HISTORY_CHANGED"):
        cw.inspect(applied.bundle.project, unsigned)
    for field, value, code in [
        ("review_digest", "0" * 64, "APPLY_DIGEST"),
        ("project_fingerprint", "0" * 64, "APPLY_RESULT"),
    ]:
        crafted = workspace.model_copy(deep=True)
        setattr(crafted.events[-1], field, value)
        crafted.digest = cw.workspace_digest(crafted)
        with pytest.raises(ModelEditError, match=f"CALCULATION_{code}"):
            cw.inspect(applied.bundle.project, crafted)
    mismatched = workspace.model_copy(deep=True)
    mismatched.source_project = ps.rename_project(p, "Other")
    mismatched.digest = cw.workspace_digest(mismatched)
    with pytest.raises(ModelEditError, match="CALCULATION_HISTORY_PROJECT"):
        cw.inspect(p, mismatched)


def test_applying_requires_a_current_error_free_change():
    p, model = venture()
    current = cw.inspect(p, model)
    with pytest.raises(StaleRevisionError):
        cw.apply(p, current.workspace, "0" * 64, "Analyst", WHEN)
    with pytest.raises(ModelEditError, match="CALCULATION_PERSON"):
        cw.apply(p, current.workspace, current.preview.review_digest, " ", WHEN)
    applied = cw.apply(p, current.workspace, current.preview.review_digest, "Analyst", WHEN)
    after = applied.inspection
    with pytest.raises(ModelEditError, match="already equals its measurement"):
        cw.apply(applied.bundle.project, after.workspace, after.preview.review_digest, "A", WHEN)
    with pytest.raises(StaleRevisionError):  # the editor undid the application
        cw.apply(
            p, after.workspace, cw.inspect(p, after.workspace).preview.review_digest, "A", WHEN
        )
    pending = step(
        applied.bundle.project,
        after,
        DefineSource(factor=factor("adoption_a", 0.07), recorded_at=WHEN),
    )
    with pytest.raises(ValidationFailed):
        cw.apply(
            applied.bundle.project, pending.workspace, pending.preview.review_digest, "A", WHEN
        )


def test_raw_models_for_another_revision_are_read_only():
    p, model = venture()
    edited = ps.rename_project(p, "Edited")
    opened = cw.inspect(edited, model)
    assert opened.relationship == "different" and not opened.workspace_exportable
    assert [i.code for i in opened.preview.issues] == ["DERIVED_STALE_PROJECT"]
    with pytest.raises(ModelEditError, match="CALCULATION_HISTORY_PROJECT"):
        step(edited, opened, Rebind(project=edited, recorded_by="A", recorded_at=WHEN))


def test_removal_and_redefinition_keep_formula_order():
    p, model = venture()
    current = cw.inspect(p, model)
    retargeted = model.formulas[0].model_copy(update={"review": None})
    current = run(
        p,
        current,
        DefineFormula(formula=retargeted, recorded_at=WHEN),
        RemoveEntry(entry="formula", id="market_b", recorded_by="A", recorded_at=WHEN),
    )
    assert [f.id for f in current.model.formulas] == ["market_a"]
    assert {u.factor_id: u.shared for u in current.factor_uses}["addressable_customers"] is False


def test_limits_are_typed_refusals():
    p, model = venture()
    current = cw.inspect(p, model)
    full = current.workspace.model_copy(deep=True)
    full.events = [
        DefineUnit(unit=f"u{i}", dimension={"x": 1}, recorded_by="A", recorded_at=WHEN)
        for i in range(125)
    ]
    full.digest = cw.workspace_digest(full)
    crowded = cw.inspect(p, full)
    with pytest.raises(ModelEditError, match="CALCULATION_EVENT_INVALID"):
        step(
            p,
            crowded,
            DefineUnit(unit="u_last", dimension={"x": 1}, recorded_by="A", recorded_at=WHEN),
        )
    long = current.workspace.model_copy(deep=True)
    long.events = [ReviewEntry(entry="source", id="adoption_a", review=review())] * 2000
    long.digest = cw.workspace_digest(long)
    with pytest.raises(ModelEditError, match="CALCULATION_HISTORY_LIMIT"):
        step(p, cw.inspect(p, long), ReviewEntry(entry="source", id="adoption_a", review=review()))


def test_naive_times_are_refused():
    with pytest.raises(ValueError, match="timezone"):
        DefineUnit(unit="u", dimension={}, recorded_by="A", recorded_at=datetime(2026, 11, 1))


def test_usage_follows_intermediates_and_tiny_changes_still_count():
    p = JsonProjectRepository().load(EXAMPLE / "supplier-project.json")
    model = DerivedModel.model_validate_json((EXAMPLE / "supplier-model.json").read_text())
    current = cw.inspect(p, model)
    uses = {u.factor_id: u for u in current.factor_uses}
    # annual_units reaches both targets only through the intermediate purchase_volume.
    assert uses["annual_units"].formula_ids == ["purchase_volume", "tco_a", "tco_b"]
    assert uses["annual_units"].shared and uses["annual_units"].alternative_ids == ["a", "b"]
    applied = cw.apply(p, current.workspace, current.preview.review_digest, "Analyst", WHEN)
    after = applied.inspection
    price = next(s for s in after.model.sources if s.id == "price_a")
    nudged = step(
        applied.bundle.project,
        after,
        DefineSource(
            factor=price.model_copy(update={"value": 40.0001, "review": None}), recorded_at=WHEN
        ),
    )
    nudged = step(
        applied.bundle.project, nudged, ReviewEntry(entry="source", id="price_a", review=review())
    )
    tco_a = next(c for c in nudged.changes if c.formula_id == "tco_a")
    assert 0 < tco_a.after - tco_a.before < 1 and tco_a.changed and nudged.applicable
