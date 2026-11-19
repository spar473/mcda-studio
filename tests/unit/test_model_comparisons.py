"""Checks, range meanings, dependency scope and explicit model selection boundaries."""

import math

import pytest

from mcda_studio.domain.derived import DerivedFormula, SourceFactor
from mcda_studio.domain.errors import ModelEditError, StaleRevisionError, ValidationFailed
from mcda_studio.domain.model_comparison import ExactRange, SampledRange
from mcda_studio.services import checked_factor_service
from mcda_studio.services import derived_service as derived
from mcda_studio.services import factor_analysis_service as analysis
from mcda_studio.services import model_checks_service as checks
from mcda_studio.services import model_comparison_service as comparisons
from model_builders import ORIGIN, REVIEW, inputs
from regression.model_output_oracle import (
    allowed,
    bottom_up,
    bottom_up_bound,
    exact_values,
    linear_quantile,
    linear_quantile_bound,
    top_down,
)


def test_two_model_ranges_overlap_but_disagreement_is_not_erased_or_averaged():
    p, _, _, _, comparison = inputs()
    original = p.model_dump_json()
    result = comparisons.inspect(p, comparison)
    assert result.comparable and not result.stale
    left, right = result.left.run, result.right.run
    assert bottom_up_bound(10000, 0.05, 1200).contains(left.value)
    assert left.value == float(bottom_up(10000, 0.05, 1200)) == 600000
    assert right.value == float(top_down(100000000, 0.01)) == 1000000
    assert (left.range.lower, left.range.upper) == (320000, 1008000)
    assert (right.range.lower, right.range.upper) == (800000, 1200000)
    assert left.range.kind == "support_enclosure" and right.range.kind == "source_interval"
    assert left.range.upper > right.range.lower
    assert [q.code for q in result.questions] == ["MODEL_DISAGREEMENT"]
    assert p.model_dump_json() == original
    assert set(left.source_classifications.values()) == {"independent", "self_reported", "unknown"}
    assert checks.verify_output(left) == left


def test_exact_discrete_support_and_sample_quantile_match_independent_oracle():
    p, _, _, _, comparison = inputs(discrete=True)
    output = comparison.left.model_copy(deep=True)
    output.range = ExactRange()
    result = checks.run_output(p, output)
    values = exact_values([8000, 10000, 12000], [0.04, 0.05, 0.06], [1200])
    assert (result.range.lower, result.range.upper) == (float(values[0]), float(values[-1]))
    assert result.draw_count == 9 and result.seed is None
    output.range = SampledRange(draws=16, seed=17)
    sampled = checks.run_output(p, output)
    assert all(row in result.first_draws for row in sampled.first_draws)
    observed = [r["bottom_a"] for r in sampled.first_draws]
    assert linear_quantile_bound(observed, 1, 40).contains(sampled.range.lower)
    assert linear_quantile_bound(observed, 39, 40).contains(sampled.range.upper)
    assert sampled.range.lower == float(linear_quantile(observed, 1, 40))
    assert sampled.range.upper == float(linear_quantile(observed, 39, 40))
    assert sampled.range.quantile_algorithm == "linear.v1" and sampled.draw_count == 16
    assert checks.verify_output(sampled) == sampled


def test_source_bounds_never_become_a_uniform_distribution():
    p, _, _, _, comparison = inputs()
    output = comparison.right.model_copy(deep=True)
    original = output.model_dump_json()
    result = checks.run_output(p, output)
    assert (
        result.draw_count == 0
        and result.seed is None
        and result.scoped_uncertainty.distributions == []
    )
    assert output.model_dump_json() == original
    output.range = SampledRange(draws=20)
    with pytest.raises(ValidationFailed, match="explicit factor distributions"):
        checks.run_output(p, output)


@pytest.mark.parametrize("field", ["population", "geography", "period", "currency_basis", "unit"])
def test_unknown_or_incompatible_scope_produces_question_not_difference(field):
    p, _, _, _, comparison = inputs()
    setattr(comparison.right.scope, field, None)
    comparison.digest = comparisons.comparison_digest(comparison)
    result = comparisons.inspect(p, comparison)
    assert not result.comparable and result.questions[0].code == "MODEL_SCOPE_INCOMPARABLE"
    assert result.left.run.value == 600000 and result.right.run.value == 1000000


def test_missing_unused_draft_blocks_only_affected_outputs():
    p, model, spec, declaration, comparison = inputs()
    extra = SourceFactor(
        id="unfinished", value=None, unit="1", source=model.sources[0].source, origin=ORIGIN
    )
    model.sources.append(extra)
    model.formulas.append(
        DerivedFormula(id="draft", expression="unfinished * 2", unit="1", origin=ORIGIN)
    )
    digest = derived._digest(model.model_dump(mode="json"))
    spec.model_digest = digest
    declaration.model_digest = digest
    declaration.digest = checks.checks_digest(declaration)
    output = comparison.left.model_copy(deep=True)
    output.model = model
    output.uncertainty = spec
    output.checks = declaration
    run = checks.run_output(p, output)
    assert run.value == 600000 and {"unfinished", "draft"} <= set(run.omitted_quantity_ids)
    assert any(s.value is None for s in run.specification.model.sources)
    output.formula_id = "draft"
    with pytest.raises(ValidationFailed):
        checks.run_output(p, output)


def test_changed_quantity_checks_model_binding_review_units_and_unknown_ids_refuse():
    for change in ("digest", "model", "review", "quantity", "unit", "kind"):
        p, _, _, _, comparison = inputs()
        output = comparison.left
        if change == "digest":
            output.checks.digest = "0" * 64
        if change == "model":
            output.model.sources[0].value = 12000
        if change == "review":
            output.checks.review = None
            output.checks.digest = checks.checks_digest(output.checks)
        if change == "quantity":
            output.checks.checks[0].quantity_id = "unknown"
            output.checks.digest = checks.checks_digest(output.checks)
        if change == "unit":
            output.checks.checks[0].unit = "other"
            output.checks.digest = checks.checks_digest(output.checks)
        if change == "kind":
            output.checks.checks[0].quantity_kind = "formula"
            output.checks.digest = checks.checks_digest(output.checks)
        with pytest.raises(ValidationFailed):
            checks.run_output(p, output)


@pytest.mark.parametrize(
    "value,inclusive,expected",
    [(0, True, True), (0, False, False), (-1, True, False), (math.nextafter(0, 1), False, True)],
)
def test_bounds_use_exact_declared_inclusivity_without_tolerance(value, inclusive, expected):
    _, _, _, declaration, _ = inputs()
    check = declaration.checks[0].model_copy(deep=True)
    check.lower = 0.0
    check.upper = None
    check.lower_inclusive = inclusive
    assert checks._contains(check, value) == allowed(value, 0, None, inclusive) == expected


def test_support_violations_refuse_before_sampling_and_every_draw_is_checked():
    p, _, _, declaration, comparison = inputs()
    declaration.checks[0].lower = 0.05
    declaration.digest = checks.checks_digest(declaration)
    comparison.left.checks = declaration
    with pytest.raises(ValidationFailed, match="declared support"):
        checks.run_output(p, comparison.left)
    from mcda_studio.services.factor_uncertainty_service import DrawError

    values = {"adoption": 0.04, "customers": 10000.0, "price": 1200.0, "bottom_a": 480000.0}
    with pytest.raises(DrawError) as error:
        checks.check_values(declaration, values, 17)
    assert error.value.draw == 17 and error.value.formula_id == "adoption"


def test_explicit_selection_changes_only_one_cell_and_preserves_both_model_inputs():
    p, _, _, _, comparison = inputs()
    original = p.model_dump_json()
    before = comparison.model_dump_json()
    current = comparisons.inspect(p, comparison)
    selection = comparisons.ModelTargetSelection(
        side="right",
        alternative_id="a",
        criterion_id="annual",
        target_scope=comparison.right.scope.model_copy(deep=True),
        review=REVIEW,
    )
    bundle = comparisons.compile_selection(p, comparison, selection, current.review_digest)
    assert bundle.calculation.project.performance_index()["a", "annual"] == 1000000
    assert bundle.calculation.project.performance_index()["b", "annual"] == 480000
    assert p.model_dump_json() == original and comparison.model_dump_json() == before
    assert len(bundle.calculation.preview.calculations) >= 1
    assert comparisons.verify(bundle) == bundle
    with pytest.raises(StaleRevisionError):
        comparisons.compile_selection(p, comparison, selection, "wrong")
    selection.target_scope.population = "other"
    with pytest.raises(ValidationFailed, match="exact known reviewed scope"):
        comparisons.compile_selection(p, comparison, selection, current.review_digest)


def test_checked_factor_run_uses_shared_realizations_and_preserves_old_record_format():
    p, model, spec, declaration, _ = inputs(discrete=True)
    result = checked_factor_service.run(
        p, model, spec, declaration, analysis.FactorRunParameters(draws=16, seed=17)
    )
    assert result.record.version == 1 and result.checks == declaration
    for row in result.record.result.trace:
        a = row.measurements["a"]["annual"]
        b = row.measurements["b"]["annual"]
        assert a == row.factors["customers"] * row.factors["adoption"] * row.factors["price"]
        assert b == row.factors["other_customers"] * row.factors["adoption"] * row.factors["price"]
    assert checked_factor_service.verify(result) == result
    changed = result.model_copy(deep=True)
    changed.checks_digest = "0" * 64
    with pytest.raises(ModelEditError):
        checked_factor_service.verify(changed)


@pytest.mark.parametrize(
    "factor,value", [("customers", 0), ("price", 0), ("adoption", 0), ("adoption", 1)]
)
def test_zero_and_adoption_endpoints_are_values_not_missing_inputs(factor, value):
    p, model, _, _, comparison = inputs()
    source = next(s for s in model.sources if s.id == factor)
    source.value = value
    output = comparison.left
    output.model = model
    output.uncertainty = None
    output.checks = None
    result = checks.run_output(p, output)
    expected = bottom_up(
        *[
            next(s.value for s in model.sources if s.id == name)
            for name in ("customers", "adoption", "price")
        ]
    )
    assert result.value == float(expected)
    assert result.range.lower == result.range.upper == float(expected)


def test_reviewed_input_change_clears_comparison_distribution_and_check_acceptance():
    p, _, _, _, comparison = inputs()
    old = comparisons.inspect(p, comparison)
    changed = comparisons.review_input(
        p,
        comparison,
        "left",
        "source",
        "customers",
        REVIEW.model_copy(update={"note": "Reviewed displayed customer factor"}),
        old.review_digest,
    )
    assert changed.comparison.review is None
    assert changed.comparison.left.checks.review is None
    assert all(d.review is None for d in changed.comparison.left.uncertainty.distributions)
    assert changed.comparison.right == comparison.right
    assert changed.left.status == "unavailable" and changed.right.status == "completed"
    assert comparison.review == REVIEW
    with pytest.raises(StaleRevisionError):
        comparisons.review_input(
            p, changed.comparison, "left", "checks", "checks", REVIEW, old.review_digest
        )


def test_disjoint_segment_sum_explicit_overlap_and_unit_conversion_match_oracle():
    from mcda_studio.domain.model_comparison import PopulationSegment, SegmentAggregation
    from regression.model_output_oracle import convert, segment_sum

    p, model, _, _, comparison = inputs()
    model.formulas.append(
        DerivedFormula(
            id="sum_segments",
            expression="bottom_a + bottom_b",
            unit="money/year",
            origin=ORIGIN,
            review=REVIEW,
        )
    )
    output = comparison.left
    output.model = model
    output.uncertainty = None
    output.checks = None
    output.formula_id = "sum_segments"
    output.aggregation = SegmentAggregation(
        segments=[
            PopulationSegment(formula_id=id, population_key=key, definition=f"Invented {key}")
            for id, key in (("bottom_a", "population_a"), ("bottom_b", "population_b"))
        ],
        disjoint_populations=True,
        rationale="Explicitly disjoint invented populations",
        review=REVIEW,
    )
    comparisons.validate_segments(output)
    assert checks.run_output(p, output).value == float(segment_sum([600000, 480000]))
    output.aggregation.segments[1].population_key = "population_a"
    with pytest.raises(ValidationFailed, match="overlap"):
        comparisons.validate_segments(output)
    output.aggregation.disjoint_populations = False
    output.aggregation.overlap_model_formula_id = "sum_segments"
    output.aggregation.overlap_quantity_ids = ["overlap"]
    model.sources.append(
        SourceFactor(
            id="overlap",
            value=80000,
            unit="money/year",
            source=model.sources[0].source,
            origin=ORIGIN,
            review=REVIEW,
        )
    )
    model.formulas[-1].expression = "bottom_a + bottom_b - overlap"
    comparisons.validate_segments(output)
    assert checks.run_output(p, output).value == float(segment_sum([600000, 480000], 80000))
    model.units["other_money/year"] = {"other_money": 1, "time": -1}
    model.units["other_money/money"] = {"other_money": 1, "money": -1}
    model.sources.append(
        SourceFactor(
            id="conversion",
            value=1.25,
            unit="other_money/money",
            source=model.sources[0].source,
            origin=ORIGIN,
            review=REVIEW,
        )
    )
    model.formulas.append(
        DerivedFormula(
            id="converted",
            expression="sum_segments * conversion",
            unit="other_money/year",
            origin=ORIGIN,
            review=REVIEW,
        )
    )
    output.formula_id = "converted"
    output.aggregation = None
    assert checks.run_output(p, output).value == float(convert(1000000, 1.25))
    model.sources[-1].unit = "1"
    with pytest.raises(ValidationFailed):
        checks.run_output(p, output)


def test_simple_ratio_denominator_and_negative_factor_domains_are_explicit_checks():
    from mcda_studio.domain.derived import DerivedModel
    from mcda_studio.domain.model_comparison import (
        EnclosureRange,
        ModelChecks,
        ModelOutputSpec,
        ModelScope,
    )
    from mcda_studio.domain.starter_templates import StarterInstantiationRequest
    from mcda_studio.services import starter_template_service

    material = starter_template_service.instantiate(
        StarterInstantiationRequest(
            template_id="venture_screening",
            mode="worked_example",
            optional_artifact_ids=["ownership_model", "ownership_checks"],
        )
    )
    model = DerivedModel.model_validate(material.artifacts["ownership_model"].value)
    declaration = ModelChecks.model_validate_json(
        __import__("json").dumps(material.artifacts["ownership_checks"].value)
    )
    spec = ModelOutputSpec(
        id="ratio",
        label="Unattached illustrative ratio",
        model=model,
        formula_id="new_share",
        scope=ModelScope(unit="1"),
        range=EnclosureRange(),
        checks=declaration,
    )
    assert checks.run_output(material.project, spec).value == 0.2
    for value in (0, -1):
        for source in model.sources:
            if source.id in {"pre_money", "new_cash"}:
                source.value = value
        declaration.model_digest = derived._digest(model.model_dump(mode="json"))
        declaration.digest = checks.checks_digest(declaration)
        with pytest.raises(ValidationFailed):
            checks.run_output(material.project, spec)


def test_check_support_failure_precedes_sampler_and_bad_draw_aborts_without_thinning(monkeypatch):
    from types import SimpleNamespace

    import numpy as np

    from mcda_studio.services import factor_uncertainty_service as factors

    p, _, _, declaration, comparison = inputs()
    output = comparison.left
    output.range = SampledRange(draws=1, seed=7)
    declaration.checks[0].lower = 0.05
    declaration.digest = checks.checks_digest(declaration)
    output.checks = declaration

    def must_not_sample(*args, **kwargs):
        raise AssertionError("sampling ran before quantity-check preflight")

    monkeypatch.setattr(factors, "sample", must_not_sample)
    with pytest.raises(ValidationFailed, match="declared support"):
        checks.run_output(p, output)
    declaration.checks[0].lower = 0.0
    declaration.digest = checks.checks_digest(declaration)
    monkeypatch.setattr(
        factors,
        "sample",
        lambda *args, **kwargs: SimpleNamespace(
            draws=1,
            values={
                name: np.array([value])
                for name, value in {
                    "customers": 10000.0,
                    "adoption": 1.1,
                    "price": 1200.0,
                    "bottom_a": 13200000.0,
                }.items()
            },
        ),
    )
    with pytest.raises(factors.DrawError) as error:
        checks.run_output(p, output)
    assert error.value.draw == 0 and error.value.formula_id == "adoption"


def test_unreviewed_comparison_cannot_supply_an_available_reviewed_output():
    p, _, _, _, comparison = inputs()
    comparison.review = None
    comparison.digest = comparisons.comparison_digest(comparison)
    current = comparisons.inspect(p, comparison)
    assert current.right.status == "completed"
    selection = comparisons.ModelTargetSelection(
        side="right",
        alternative_id="a",
        criterion_id="annual",
        target_scope=comparison.right.scope,
        review=REVIEW,
    )
    with pytest.raises(ValidationFailed, match="review the comparison"):
        comparisons.compile_selection(p, comparison, selection, current.review_digest)


def test_source_bounds_do_not_require_unused_probability_group_members():
    from mcda_studio.domain.factor_uncertainty import QuantileGroup
    from mcda_studio.domain.model_comparison import SourceInterval, SourceRange

    p, model, spec, declaration, comparison = inputs()
    model.sources.append(
        SourceFactor(
            id="unneeded_group_member",
            value=None,
            unit="1",
            source=model.sources[0].source,
            origin=ORIGIN,
        )
    )
    spec.model_digest = derived._digest(model.model_dump(mode="json"))
    spec.groups = [
        QuantileGroup(
            id="unused_coupling",
            factor_ids=["customers", "unneeded_group_member"],
            rationale="Retained probability declaration, unused by source-bound propagation",
            origin=ORIGIN,
            review=REVIEW,
        )
    ]
    declaration.model_digest = spec.model_digest
    declaration.digest = checks.checks_digest(declaration)
    output = comparison.left
    output.model, output.uncertainty, output.checks = model, spec, declaration
    output.range = SourceRange(
        intervals=[
            SourceInterval(
                factor_id="customers",
                unit="customer",
                lower=8000,
                upper=12000,
                origin=ORIGIN,
                review=REVIEW,
            )
        ]
    )
    result = checks.run_output(p, output)
    assert result.value == 600000
    assert (result.range.lower, result.range.upper) == (480000, 720000)
    assert result.draw_count == 0 and result.scoped_uncertainty.groups == []
    assert "unneeded_group_member" in result.omitted_quantity_ids
    assert result.specification.uncertainty.groups == spec.groups
