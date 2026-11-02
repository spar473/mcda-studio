"""Generic factor identity, declaration order, point masses and classification invariants."""

from hypothesis import given, settings
from hypothesis import strategies as st

from mcda_studio.domain.model_comparison import SampledRange
from mcda_studio.domain.uncertainty import DiscreteDistribution
from mcda_studio.services import checked_factor_service as checked
from mcda_studio.services import derived_service as derived
from mcda_studio.services import factor_analysis_service as analysis
from mcda_studio.services import model_checks_service as checks
from model_builders import inputs
from regression.rounding_oracle import evaluate as exact_formula


@settings(max_examples=20, deadline=None)
@given(st.integers(0, 100000), st.booleans())
def test_declaration_order_preserves_each_seeded_factor_draw_and_source_relationship(seed, reverse):
    p, model, spec, declaration, comparison = inputs()
    output = comparison.left.model_copy(deep=True)
    output.range = SampledRange(draws=12, seed=seed)
    before = checks.run_output(p, output)
    if reverse:
        model.sources.reverse()
        model.formulas.reverse()
        spec.distributions.reverse()
        p.alternatives.reverse()
        model.project_fingerprint = p.fingerprint()
        spec.project_fingerprint = p.fingerprint()
        declaration.project_fingerprint = p.fingerprint()
        spec.model_digest = derived._digest(model.model_dump(mode="json"))
        declaration.model_digest = spec.model_digest
        declaration.digest = checks.checks_digest(declaration)
    output.model, output.uncertainty, output.checks = model, spec, declaration
    after = checks.run_output(p, output)
    assert after.first_draws == before.first_draws
    assert after.value == before.value and after.range == before.range
    assert after.source_classifications == before.source_classifications


@settings(max_examples=15, deadline=None)
@given(st.integers(1, 16), st.integers(0, 100000))
def test_shared_factor_has_one_realization_in_every_formula_and_checked_analysis(draws, seed):
    p, model, spec, declaration, _ = inputs()
    run = checked.run(
        p,
        model,
        spec,
        declaration,
        analysis.FactorRunParameters(run="mavt", draws=draws, seed=seed),
    )
    assert run.record.result.draw_count == draws
    for row in run.record.result.trace:
        f = row.factors
        temporary = model.model_copy(deep=True)
        for source in temporary.sources:
            if source.id in f:
                source.value = f[source.id]
        preview = derived.preview(p, temporary)
        compiled = derived.compilation_bundle(p, temporary, preview.review_digest)
        deterministic = {c.id: c.value for c in compiled.preview.calculations}
        assert row.formulas["bottom_a"] == deterministic["bottom_a"]
        assert row.formulas["bottom_b"] == deterministic["bottom_b"]
        assert exact_formula("customers * adoption * price", f).contains(row.formulas["bottom_a"])
        assert exact_formula("other_customers * adoption * price", f).contains(
            row.formulas["bottom_b"]
        )
        assert row.measurements["a"]["annual"] == row.formulas["bottom_a"]
        assert row.measurements["b"]["annual"] == row.formulas["bottom_b"]


@settings(max_examples=15, deadline=None)
@given(st.integers(0, 12000), st.integers(0, 1200))
def test_explicit_point_mass_reduces_to_the_same_deterministic_formula(customers, price):
    p, model, spec, _, comparison = inputs()
    source_values = {"customers": customers, "price": price}
    for source in model.sources:
        if source.id in source_values:
            source.value = source_values[source.id]
    for marginal in spec.distributions:
        value = next(source.value for source in model.sources if source.id == marginal.factor_id)
        marginal.distribution = DiscreteDistribution(values=[value], probabilities=[1])
    spec.model_digest = derived._digest(model.model_dump(mode="json"))
    output = comparison.left
    output.model, output.uncertainty, output.checks = model, spec, None
    output.range = SampledRange(draws=8, seed=7)
    run = checks.run_output(p, output)
    deterministic = derived.preview(p, model)
    compiled = derived.compilation_bundle(p, model, deterministic.review_digest)
    expected = next(c.value for c in compiled.preview.calculations if c.id == "bottom_a")
    assert run.value == run.range.lower == run.range.upper == expected
