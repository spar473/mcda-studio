"""Factor draws through independent MAVT/sorting answers and the ordinary reference engines."""

from datetime import UTC, datetime
from fractions import Fraction

import numpy as np
import pytest
from factor_analysis_oracle import acceptabilities, evaluate
from hypothesis import given, settings
from hypothesis import strategies as st

from mcda_studio.domain.decision import DecisionDetails
from mcda_studio.domain.derived import DerivedFormula, DerivedModel, SourceFactor
from mcda_studio.domain.errors import ModelEditError, ValidationFailed
from mcda_studio.domain.evidence import Origin, Review, Source
from mcda_studio.domain.factor_uncertainty import FactorDistribution, FactorUncertaintyModel
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.uncertainty import (
    CellUncertainty,
    DiscreteDistribution,
    GroupUncertainty,
    SmaaModel,
    UniformDistribution,
)
from mcda_studio.services import analysis_service, derived_service
from mcda_studio.services import factor_analysis_service as service
from mcda_studio.services import factor_uncertainty_service as factors

from builders import flat_project, with_classes

ACCEPTED = Review(
    status="accepted", reviewer="Reviewer", reviewed_at=datetime(2026, 11, 1, tzinfo=UTC)
)
ORIGIN = Origin(kind="human", proposed_by="Analyst")
SOURCE = Source(
    name="Synthetic note",
    reference="local:synthetic",
    date="2026-11-01",
    description="Invented measurements",
)


def case(offset=0.0):
    p = with_classes(
        flat_project([[0.5, 0.5], [0.5, 0.5 + offset]], [100, 70]),
        [("Upper", 0.5), ("Lower", None)],
    )
    model = DerivedModel(
        project_fingerprint=p.fingerprint(),
        sources=[
            SourceFactor(id="x", value=0.5, unit="1", source=SOURCE, origin=ORIGIN, review=ACCEPTED)
        ],
        formulas=[
            DerivedFormula(
                id="first",
                expression="x",
                unit="1",
                alternative_id="a0",
                criterion_id="c0",
                origin=ORIGIN,
                review=ACCEPTED,
            ),
            DerivedFormula(
                id="second",
                expression="x",
                unit="1",
                alternative_id="a1",
                criterion_id="c0",
                origin=ORIGIN,
                review=ACCEPTED,
            ),
        ],
    )
    spec = FactorUncertaintyModel(
        project_fingerprint=p.fingerprint(),
        model_digest=derived_service.preview(p, model).model_digest,
        distributions=[
            FactorDistribution(
                factor_id="x",
                distribution=DiscreteDistribution(
                    values=[0.25, 0.5, 0.75], probabilities=[0.25, 0.5, 0.25]
                ),
                origin=ORIGIN,
                review=ACCEPTED,
            )
        ],
    )
    return p, model, spec


def params(**kw):
    return service.FactorRunParameters(draws=32, seed=13, **kw)


@pytest.mark.parametrize("offset", [0, 0.5e-12, 2e-12, 5e-12, -5e-12])
@pytest.mark.parametrize("run", ["mavt", "mavt_sorting", "smaa2_factors"])
def test_exact_raw_measurements_near_ties_and_class_boundaries(offset, run):
    p, model, spec = case(offset)
    original = p.model_dump_json()
    got = service.run(p, model, spec, params(run=run, evaluation="exact_enumeration"))
    result = got.result
    boundaries = [] if run == "mavt" else [0.5]
    functions = {"c0": ("linear", (0, 1, False)), "c1": ("linear", (0, 1, False))}
    outcomes = [
        (Fraction(1, 4), {"a0": {"c0": 0.25, "c1": 0.5}, "a1": {"c0": 0.25, "c1": 0.5 + offset}}),
        (Fraction(1, 2), {"a0": {"c0": 0.5, "c1": 0.5}, "a1": {"c0": 0.5, "c1": 0.5 + offset}}),
        (Fraction(1, 4), {"a0": {"c0": 0.75, "c1": 0.5}, "a1": {"c0": 0.75, "c1": 0.5 + offset}}),
    ]
    rank_p, class_p = acceptabilities(outcomes, {"c0": 100, "c1": 70}, functions, boundaries)
    for row, (_, raw) in zip(result.trace, outcomes, strict=True):
        values, ranks, classes = evaluate(raw, {"c0": 100, "c1": 70}, functions, boundaries)
        assert row.measurements == raw
        assert row.values == values
        assert row.ranks == ranks
        assert row.classes == (
            {a: ["upper", "lower"][c] for a, c in classes.items()} if boundaries else {}
        )
    for a in result.acceptability:
        assert [e.frequency for e in a.ranks] == [
            float(rank_p.get((a.alternative_id, r), 0)) for r in (1, 2)
        ]
        assert all(e.count is None and e.lower is None and e.upper is None for e in a.ranks)
        if boundaries:
            assert {k: e.frequency for k, e in a.classes.items()} == {
                cid: float(class_p.get((a.alternative_id, i), 0))
                for i, cid in enumerate(["upper", "lower"])
            }
    assert p.model_dump_json() == original
    assert result.draw_count == 3
    assert service.verify(got.model_dump(mode="json"), replay=True) == got


def test_point_mass_reduces_exactly_to_deterministic_values_ranks_and_classes():
    p, model, spec = case()
    spec.distributions[0].distribution = DiscreteDistribution(values=[0.5], probabilities=[1])
    got = service.run(p, model, spec, params()).result
    preview = derived_service.preview(p, model)
    compiled = derived_service.compile_copy(p, model, preview.review_digest)
    expected = analysis_service.evaluate_project(
        compiled, AnalysisConfiguration(method="mavt_sorting")
    )
    assert got.reference == expected
    assert all(
        row.values == {a.alternative_id: a.value for a in expected.ranking} for row in got.trace
    )
    assert all(
        row.ranks == {a.alternative_id: a.rank for a in expected.ranking} for row in got.trace
    )
    assert all(
        row.classes == {a.alternative_id: a.class_id for a in expected.assignments}
        for row in got.trace
    )
    assert all(sum(e.count for e in a.ranks) == 32 for a in got.acceptability)


def test_sampled_counts_reproducibility_metadata_and_shared_identity():
    p, model, spec = case()
    spec.distributions[0].distribution = UniformDistribution(lower=0.25, upper=0.75)
    first = service.run(p, model, spec, params())
    assert service.run(p, model, spec, params()) == first
    r = first.result
    assert (r.algorithm, r.sampler_algorithm, r.seed, r.draw_count) == (
        service.ALGORITHM,
        factors.ALGORITHM,
        13,
        32,
    )
    assert r.model_digest == spec.model_digest and r.uncertainty_digest
    assert set(r.environment) == {"python", "numpy", "system"}
    assert r.dependency_order == ["first", "second"] and r.draw_columns == ["x"]
    expected = np.random.Generator(np.random.PCG64(13)).random((32, 1))[:, 0]
    for i, row in enumerate(r.trace):
        assert row.factors["x"] == 0.25 + expected[i] * 0.5
        assert row.formulas["first"] == row.formulas["second"] == row.factors["x"]
    for a in r.acceptability:
        assert a.tied_first.count == 32 and a.tied_first.lower < 1
        assert a.sole_first.count == 0 and a.sole_first.upper > 0
    assert len(r.trace) == 16
    assert r.questions and all("x" in q.question and "unknown" in q.why for q in r.questions)


@pytest.mark.parametrize("kind", ["cell", "weights", "other_cell"])
def test_double_specification_and_unsupported_combinations_are_refused(kind):
    p, model, spec = case()
    if kind == "weights":
        p.smaa = SmaaModel(groups=[GroupUncertainty(parent_id=None, kind="unknown")])
    else:
        p.smaa = SmaaModel(
            cells=[
                CellUncertainty(
                    alternative_id="a0",
                    criterion_id="c0" if kind == "cell" else "c1",
                    distribution=UniformDistribution(lower=0.1, upper=0.9),
                )
            ]
        )
    model.project_fingerprint = p.fingerprint()
    spec.project_fingerprint = p.fingerprint()
    spec.model_digest = derived_service.preview(p, model).model_digest
    with pytest.raises(ValidationFailed) as refused:
        service.run(p, model, spec, params())
    codes = {i.code for i in refused.value.report.issues}
    assert (
        "DERIVED_UNCERTAINTY_UNSUPPORTED" if kind == "cell" else "FACTOR_COMBINATION_UNSUPPORTED"
    ) in codes


def test_bad_arithmetic_draw_is_not_discarded_by_the_integration(monkeypatch):
    p, model, spec = case()
    model.formulas[0].expression = "1 / x"
    model.sources[0].value = 2
    model.formulas[1].expression = "x / 4"
    spec.distributions[0].distribution = UniformDistribution(lower=2, upper=4)
    spec.model_digest = derived_service.preview(p, model).model_digest
    original = factors._marginal

    def marginal(d):
        m = original(d)

        def quantile(u):
            values = m.quantile(u)
            values[17] = 0
            return values

        return factors._Marginal(quantile, m.support, m.atoms)

    monkeypatch.setattr(factors, "_marginal", marginal)
    with pytest.raises(factors.DrawError) as refused:
        service.run(p, model, spec, params())
    assert (refused.value.draw, refused.value.formula_id) == (17, "first")


def test_bad_value_function_draw_aborts_with_typed_index_and_target(monkeypatch):
    p, model, spec = case()
    spec.distributions[0].distribution = UniformDistribution(lower=0.25, upper=0.75)
    original = factors._marginal

    def marginal(d):
        m = original(d)

        def quantile(u):
            values = m.quantile(u)
            values[17] = 2.0
            return values

        return factors._Marginal(quantile, m.support, m.atoms)

    monkeypatch.setattr(factors, "_marginal", marginal)
    with pytest.raises(factors.DrawError) as refused:
        service.run(p, model, spec, params())
    assert refused.value.code == "UNCERTAINTY_VALUE_DOMAIN" and refused.value.draw == 17
    assert "first" in refused.value.formula_id
    assert refused.value.factor_ids == ["x"]


def test_invalid_target_support_is_refused_before_sampling(monkeypatch):
    p, model, spec = case()
    spec.distributions[0].distribution = DiscreteDistribution(
        values=[0.5, 2], probabilities=[0.5, 0.5]
    )

    def forbidden(*args, **kwargs):
        pytest.fail("sampling must not start")

    monkeypatch.setattr(factors, "sample", forbidden)
    with pytest.raises(ValidationFailed) as refused:
        service.run(p, model, spec, params())
    assert {i.code for i in refused.value.report.issues} == {"UNCERTAINTY_VALUE_DOMAIN_SUPPORT"}


def test_records_retain_decisions_and_refuse_tampering():
    p, model, spec = case()
    details = DecisionDetails(
        owner="Owner",
        date="2026-11-01",
        outcome="selected",
        selected_alternative_id="a0",
        alternatives_considered=["a0", "a1"],
        rationale="Review these assumptions again",
        configurations=[AnalysisConfiguration()],
    )
    got = service.run(p, model, spec, params(), details)
    assert got.decision.decision == details
    assert all(
        t.inputs == (["x"] if t.criterion_id == "c0" else [])
        for t in got.decision.measurement_trace
    )
    assert service.verify(got.model_dump(mode="json"), replay=True) == got
    body = got.model_dump(mode="json")
    body["result"]["draw_count"] -= 1
    with pytest.raises(ModelEditError, match="FACTOR_RECORD_CHANGED"):
        service.verify(body)
    body["digest"] = derived_service._digest({k: v for k, v in body.items() if k != "digest"})
    with pytest.raises(ModelEditError, match="denominator"):
        service.verify(body)
    body["result"]["trace"][0]["factors"]["x"] = float("nan")
    with pytest.raises(ModelEditError, match="FACTOR_RECORD_NONFINITE"):
        service.verify(body)
    body["result"]["trace"][0]["factors"]["x"] = 0.5
    body["version"] = 2
    with pytest.raises(ModelEditError, match="FACTOR_RECORD_INVALID"):
        service.verify(body)
    forged = got.model_dump(mode="json")
    forged["result"]["reference"]["ranking"][0]["value"] += 0.1
    forged["digest"] = derived_service._digest({k: v for k, v in forged.items() if k != "digest"})
    with pytest.raises(ModelEditError, match="deterministic reference"):
        service.verify(forged)


@settings(max_examples=20, deadline=None)
@given(st.integers(0, 2**31 - 1), st.floats(0.1, 0.9, allow_nan=False))
def test_keyed_results_ignore_declaration_and_alternative_order(seed, point):
    p, model, spec = case()
    spec.distributions[0].distribution = DiscreteDistribution(values=[point], probabilities=[1])
    par = service.FactorRunParameters(draws=2, seed=seed)
    before = service.run(p, model, spec, par)
    p.alternatives.reverse()
    model.formulas.reverse()
    model.project_fingerprint = p.fingerprint()
    spec.project_fingerprint = p.fingerprint()
    spec.model_digest = derived_service.preview(p, model).model_digest
    after = service.run(p, model, spec, par)
    assert before.result.trace == after.result.trace
    assert {a.alternative_id: a for a in before.result.acceptability} == {
        a.alternative_id: a for a in after.result.acceptability
    }


def test_local_anchors_recompute_and_explicit_clamp_policy_is_retained():
    from mcda_studio.domain.criteria import LinearValueFunction
    from mcda_studio.domain.scales import AnchorMode

    p, model, spec = case()
    # Distinct second target keeps local anchors non-degenerate on every supported draw.
    model.formulas[1].expression = "1 - x"
    p.criteria[0].value_function = LinearValueFunction()
    p.criteria[0].scale.anchor_mode = AnchorMode.LOCAL
    spec.distributions[0].distribution = DiscreteDistribution(
        values=[0.25, 0.75], probabilities=[0.5, 0.5]
    )
    model.project_fingerprint = p.fingerprint()
    spec.project_fingerprint = p.fingerprint()
    spec.model_digest = derived_service.preview(p, model).model_digest
    # Deterministic x must also avoid a degenerate local reference range.
    model.sources[0].value = 0.25
    spec.model_digest = derived_service.preview(p, model).model_digest
    result = service.run(p, model, spec, params(evaluation="exact_enumeration")).result
    assert result.trace[0].ranks == {"a0": 2, "a1": 1}
    assert result.trace[1].ranks == {"a0": 1, "a1": 2}
    # A stated clamp is ordinary engine policy, not an invented sampler clamp.
    p.criteria[0].scale.anchor_mode = AnchorMode.FIXED
    p.criteria[0].value_function = LinearValueFunction(out_of_domain="clamp")
    model.formulas[1].expression = "x"
    spec.distributions[0].distribution = DiscreteDistribution(
        values=[0.25, 2], probabilities=[0.5, 0.5]
    )
    model.project_fingerprint = p.fingerprint()
    spec.project_fingerprint = p.fingerprint()
    spec.model_digest = derived_service.preview(p, model).model_digest
    result = service.run(p, model, spec, params(evaluation="exact_enumeration")).result
    assert result.trace[1].measurements["a0"]["c0"] == 2
    assert result.trace[1].values["a0"] < 1


def test_work_limit_is_checked_before_sampling(monkeypatch):
    p, model, spec = case()
    monkeypatch.setattr(service, "MAX_WORK", 1)

    def forbidden(*args, **kwargs):
        pytest.fail("sampling started before the work limit")

    monkeypatch.setattr(factors, "sample", forbidden)
    with pytest.raises(ValidationFailed) as refused:
        service.run(p, model, spec, params())
    assert {i.code for i in refused.value.report.issues} == {"UNCERTAINTY_LIMIT"}


def test_one_quantile_transform_per_factor_even_when_reused(monkeypatch):
    p, model, spec = case()
    original = factors._marginal
    calls = []

    def marginal(d):
        m = original(d)

        def quantile(u):
            calls.append(len(u))
            return m.quantile(u)

        return factors._Marginal(quantile, m.support, m.atoms)

    monkeypatch.setattr(factors, "_marginal", marginal)
    service.run(p, model, spec, params())
    assert calls == [32]


@pytest.mark.parametrize("explicit_profile", [None, "default"])
def test_curved_scenario_and_profile_precedence_match_independent_oracle(explicit_profile):
    from mcda_studio.domain.criteria import (
        ControlPoint,
        LinearValueFunction,
        PiecewiseLinearValueFunction,
    )
    from mcda_studio.domain.preferences import Scenario, WeightProfile

    p, model, spec = case(0.1)
    p.criteria[1].value_function = LinearValueFunction(direction="decreasing")
    p.weight_profiles.append(
        WeightProfile(id="other", name="Other preferences", judgements={"c0": 50, "c1": 100})
    )
    points = [(0.0, 0.0), (0.5, 0.2), (1.0, 1.0)]
    p.scenarios.append(
        Scenario(
            id="curved",
            name="Curved",
            weight_profile_id="other",
            value_function_overrides={
                "c0": PiecewiseLinearValueFunction(
                    points=[ControlPoint(x=x, value=v) for x, v in points]
                )
            },
        )
    )
    model.project_fingerprint = p.fingerprint()
    spec.project_fingerprint = p.fingerprint()
    spec.model_digest = derived_service.preview(p, model).model_digest
    cfg = AnalysisConfiguration(scenario_id="curved", weight_profile_id=explicit_profile)
    result = service.run(
        p, model, spec, params(configuration=cfg, evaluation="exact_enumeration")
    ).result
    ratings = {"c0": 100, "c1": 70} if explicit_profile else {"c0": 50, "c1": 100}
    assert result.reference.weight_profile_id == (explicit_profile or "other")
    functions = {"c0": ("piecewise", points), "c1": ("linear", (0, 1, True))}
    for row in result.trace:
        values, ranks, classes = evaluate(row.measurements, ratings, functions, [0.5])
        assert row.values == values and row.ranks == ranks
        assert row.classes == {a: ["upper", "lower"][c] for a, c in classes.items()}


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"review": None}, "DERIVED_UNREVIEWED_SOURCE"),
        ({"value": None}, "DERIVED_MISSING_INPUT"),
        ({"unit": "undeclared"}, "DERIVED_UNKNOWN_UNIT"),
    ],
)
def test_unused_incomplete_factors_return_typed_refusals(change, code):
    p, model, spec = case()
    source = SourceFactor(
        id="unused", value=1, unit="1", source=SOURCE, origin=ORIGIN, review=ACCEPTED
    )
    source = source.model_copy(update=change)
    model.sources.append(source)
    spec.model_digest = derived_service.preview(p, model).model_digest
    with pytest.raises(ValidationFailed) as refused:
        service.run(p, model, spec, params())
    assert code in {i.code for i in refused.value.report.issues}
