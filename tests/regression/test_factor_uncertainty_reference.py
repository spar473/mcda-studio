"""Fundamental-factor uncertainty against independent exact answers and analytic moments.

Statistical bounds are fixed in advance as five standard errors from the exact variance (or
fourth moment) and the draw count; the seeds are fixed, so each run is reproducible."""

import math
from collections import defaultdict
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest
from factor_uncertainty_oracle import (
    distribution,
    joint,
    moments,
    product_central_moments,
    triangular_cdf,
    triangular_moments,
)

from mcda_studio.domain.derived import DerivedFormula, DerivedModel, SourceFactor
from mcda_studio.domain.errors import ValidationFailed
from mcda_studio.domain.evidence import Origin, Review, Source
from mcda_studio.domain.factor_uncertainty import (
    FactorDistribution,
    FactorUncertaintyModel,
    QuantileGroup,
)
from mcda_studio.domain.uncertainty import (
    DiscreteDistribution,
    TriangularDistribution,
    UniformDistribution,
)
from mcda_studio.services import derived_service as derived
from mcda_studio.services import factor_uncertainty_service as fu
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository

EXAMPLE = Path(__file__).parents[2] / "examples/derived_measurements"
WHEN = datetime(2026, 11, 1, tzinfo=UTC)
ACCEPTED = Review(status="accepted", reviewer="Reviewer", reviewed_at=WHEN)
HUMAN = Origin(kind="human", proposed_by="Analyst")
SOURCE = Source(name="Note", reference="local:note", date="2026-11-01", description="Synthetic")
UNIT = "NZD/year"
F = Fraction


def project():
    return JsonProjectRepository().load(EXAMPLE / "venture-project.json")


def build(p, sources, formulas):
    """sources: {id: (value, unit)}; formulas: [(id, expression, alternative or None)]."""
    model = DerivedModel(
        project_fingerprint=p.fingerprint(),
        units={UNIT: {"NZD": 1, "year": -1}},
        sources=[
            SourceFactor(id=i, value=v, unit=u, source=SOURCE, origin=HUMAN, review=ACCEPTED)
            for i, (v, u) in sources.items()
        ],
        formulas=[
            DerivedFormula(
                id=i,
                expression=e,
                unit=UNIT,
                origin=HUMAN,
                review=ACCEPTED,
                alternative_id=alt,
                criterion_id="result" if alt else None,
            )
            for i, e, alt in formulas
        ],
    )
    return model


def uncertain(p, model, dists, groups=(), review=ACCEPTED):
    return FactorUncertaintyModel(
        project_fingerprint=p.fingerprint(),
        model_digest=derived.preview(p, model).model_digest,
        distributions=[
            FactorDistribution(factor_id=i, distribution=d, origin=HUMAN, review=review)
            for i, d in dists.items()
        ],
        groups=[
            QuantileGroup(id=g, factor_ids=m, rationale="Same source", origin=HUMAN, review=review)
            for g, m in groups
        ],
    )


def discrete(*pairs):
    return DiscreteDistribution(values=[v for v, _ in pairs], probabilities=[q for _, q in pairs])


def exact(values):
    return [(F(v), F(q)) for v, q in values]


def produced(enumeration, formula_id):
    out = defaultdict(Fraction)
    for outcome in enumeration.outcomes:
        out[F(outcome.values[formula_id])] += outcome.probability
    return dict(out)


def product_case(groups=()):
    p = project()
    model = build(p, {"x": (1.0, UNIT), "y": (2.0, "1")}, [("market_a", "x * y", "a")])
    dists = {"x": discrete((1.0, 0.5), (3.0, 0.5)), "y": discrete((2.0, 0.5), (4.0, 0.5))}
    return p, model, uncertain(p, model, dists, groups)


def test_independent_discrete_product_matches_exact_enumeration():
    p, model, spec = product_case()
    got = produced(fu.enumerate_outcomes(fu.plan(p, model, spec)), "market_a")
    oracle = joint({"x": exact([(1, "1/2"), (3, "1/2")]), "y": exact([(2, "1/2"), (4, "1/2")])}, [])
    expected = distribution(oracle, lambda v: v["x"] * v["y"])
    assert got == expected == {2: F(1, 4), 4: F(1, 4), 6: F(1, 4), 12: F(1, 4)}
    assert moments(got) == (6, 14)
    # The nonlinear range fallacy: four atoms, not a distribution on [2, 12].
    assert moments(got) != (7, F(25, 3))


def test_explicit_quantile_coupling_differs_from_independence():
    p, model, spec = product_case([("same_source", ["x", "y"])])
    got = produced(fu.enumerate_outcomes(fu.plan(p, model, spec)), "market_a")
    oracle = joint(
        {}, [{"x": exact([(1, "1/2"), (3, "1/2")]), "y": exact([(2, "1/2"), (4, "1/2")])}]
    )
    assert got == distribution(oracle, lambda v: v["x"] * v["y"]) == {2: F(1, 2), 12: F(1, 2)}
    assert moments(got) == (7, 25)


def test_unequal_coupled_steps_follow_the_comonotone_merge():
    p = project()
    model = build(p, {"x": (1.0, UNIT), "y": (2.0, "1")}, [("market_a", "x * y", "a")])
    dists = {"x": discrete((3.0, 0.75), (1.0, 0.25)), "y": discrete((2.0, 0.5), (4.0, 0.5))}
    spec = uncertain(p, model, dists, [("g", ["y", "x"])])
    got = produced(fu.enumerate_outcomes(fu.plan(p, model, spec)), "market_a")
    oracle = joint(
        {}, [{"x": exact([(1, "1/4"), (3, "3/4")]), "y": exact([(2, "1/2"), (4, "1/2")])}]
    )
    assert (
        got
        == distribution(oracle, lambda v: v["x"] * v["y"])
        == {2: F(1, 4), 6: F(1, 4), 12: F(1, 2)}
    )


def shared_case():
    p = project()
    model = build(p, {"x": (1.0, UNIT)}, [("market_a", "2 * x", "a"), ("market_b", "3 * x", "b")])
    return p, model


def test_a_shared_factor_is_one_value_across_alternatives():
    p, model = shared_case()
    spec = uncertain(p, model, {"x": discrete((1.0, 0.5), (3.0, 0.5))})
    enumeration = fu.enumerate_outcomes(fu.plan(p, model, spec))
    assert all(o.values["market_b"] > o.values["market_a"] for o in enumeration.outcomes)
    # Independently resampling x per alternative would let A exceed B with probability 1/4.
    resampled = joint(
        {"xa": exact([(1, "1/2"), (3, "1/2")]), "xb": exact([(1, "1/2"), (3, "1/2")])}, []
    )
    wrong = sum((q for q, v in resampled if 2 * v["xa"] > 3 * v["xb"]), F(0))
    assert wrong == F(1, 4)
    sample = fu.sample(fu.plan(p, model, spec), seed=7, draws=2000)
    assert np.all(sample.values["market_b"] > sample.values["market_a"])
    assert np.array_equal(sample.values["market_b"] / 3, sample.values["x"])


def test_identities_hold_exactly_on_every_draw():
    p = project()
    model = build(
        p,
        {"x": (1.5, UNIT), "y": (2.0, "1")},
        [
            ("zero", "x - x", None),
            ("intermediate", "x * y", None),
            ("market_a", "intermediate + x / x * x", "a"),
            ("market_b", "intermediate * 2", "b"),
        ],
    )
    model.formulas[0].unit = UNIT
    spec = uncertain(
        p,
        model,
        {
            "x": UniformDistribution(lower=1, upper=2),
            "y": TriangularDistribution(lower=1, mode=2, upper=4),
        },
    )
    sample = fu.sample(fu.plan(p, model, spec), seed=11, draws=3000)
    v = sample.values
    assert np.all(v["zero"] == 0)
    assert np.array_equal(v["market_b"], v["intermediate"] * 2)
    # One realised intermediate per draw feeds both targets.
    assert np.array_equal(v["market_a"], v["intermediate"] + v["x"] / v["x"] * v["x"])
    assert np.array_equal(v["intermediate"], v["x"] * v["y"])


def test_zero_uncertainty_reproduces_the_deterministic_calculation():
    p, model = shared_case()
    report = derived.preview(p, model)
    for spec in (
        uncertain(p, model, {}),
        uncertain(p, model, {"x": discrete((1.0, 1.0))}),
    ):
        plan = fu.plan(p, model, spec)
        sample = fu.sample(plan, seed=3, draws=50)
        for c in report.calculations:
            assert np.all(sample.values[c.id] == c.value)
        (outcome,) = fu.enumerate_outcomes(plan).outcomes
        assert outcome.probability == 1
        assert {c.id: c.value for c in report.calculations} == {
            k: outcome.values[k] for k in ("market_a", "market_b")
        }


def test_continuous_product_moments_within_preregistered_bounds():
    p, model, _ = product_case()
    spec = uncertain(
        p,
        model,
        {"x": UniformDistribution(lower=1, upper=3), "y": UniformDistribution(lower=2, upper=4)},
    )
    n = 40_000
    sample = fu.sample(fu.plan(p, model, spec), seed=20261101, draws=n)
    mean, variance, fourth = product_central_moments((F(1), F(3)), (F(2), F(4)))
    assert (mean, variance) == (6, F(40, 9))  # E[X]E[Y]; Var = VxVy + VxEy^2 + VyEx^2
    values = sample.values["market_a"]
    assert abs(values.mean() - float(mean)) <= 5 * math.sqrt(float(variance) / n)
    assert abs(values.var() - float(variance)) <= 5 * math.sqrt(float(fourth - variance**2) / n)


def test_triangular_quantiles_and_moments():
    a, m, b = 0.0, 1.0, 4.0
    p, model, _ = product_case()
    spec = uncertain(
        p, model, {"x": TriangularDistribution(lower=a, mode=m, upper=b), "y": discrete((2.0, 1.0))}
    )
    plan = fu.plan(p, model, spec)
    grid = np.linspace(0, 1, 1001, endpoint=False)
    quantiles = plan.marginals["x"].quantile(grid)
    # Square roots and products round at about 1e-16; 1e-12 is a margin fixed in advance.
    assert (
        max(
            abs(triangular_cdf(float(q), a, m, b) - u) for q, u in zip(quantiles, grid, strict=True)
        )
        < 1e-12
    )
    n = 40_000
    sample = fu.sample(plan, seed=5, draws=n)
    mean, variance = triangular_moments(F(0), F(1), F(4))
    assert abs(sample.values["x"].mean() - float(mean)) <= 5 * math.sqrt(float(variance) / n)
    assert np.array_equal(sample.values["market_a"], sample.values["x"] * 2.0)


def test_discrete_sampling_frequencies_within_preregistered_bounds():
    for groups, expected in (((), {12: 0.25, 6: 0.25}), ([("g", ["x", "y"])], {12: 0.5, 6: 0.0})):
        p, model, spec = product_case(groups)
        n = 20_000
        values = fu.sample(fu.plan(p, model, spec), seed=13, draws=n).values["market_a"]
        for atom, probability in expected.items():
            observed = float(np.mean(values == atom))
            assert abs(observed - probability) <= 5 * math.sqrt(probability * (1 - probability) / n)


def test_reproducibility_chunk_and_order_invariance(monkeypatch):
    p, model, spec = product_case([("g", ["x", "y"])])
    model.sources.append(
        SourceFactor(id="z", value=1.0, unit="1", source=SOURCE, origin=HUMAN, review=ACCEPTED)
    )
    model.formulas.append(
        DerivedFormula(
            id="market_b",
            expression="x * z",
            unit=UNIT,
            origin=HUMAN,
            review=ACCEPTED,
            alternative_id="b",
            criterion_id="result",
        )
    )
    dists = {
        "x": discrete((1.0, 0.5), (3.0, 0.5)),
        "y": discrete((2.0, 0.5), (4.0, 0.5)),
        "z": UniformDistribution(lower=0.5, upper=1.5),
    }
    spec = uncertain(p, model, dists, [("g", ["x", "y"])])
    first = fu.sample(fu.plan(p, model, spec), seed=99, draws=5000)
    again = fu.sample(fu.plan(p, model, spec), seed=99, draws=5000)
    assert all(np.array_equal(first.values[k], again.values[k]) for k in first.values)
    assert not np.array_equal(
        first.values["z"], fu.sample(fu.plan(p, model, spec), seed=100, draws=5000).values["z"]
    )
    monkeypatch.setattr(fu, "CHUNK_ROWS", 7)
    chunked = fu.sample(fu.plan(p, model, spec), seed=99, draws=5000)
    assert all(np.array_equal(first.values[k], chunked.values[k]) for k in first.values)
    # Reordered declarations and alternatives keep keyed realisations; digests record the order.
    reordered = model.model_copy(deep=True)
    reordered.sources.reverse()
    reordered.formulas.reverse()
    reordered_project = p.model_copy(deep=True)
    reordered_project.alternatives.reverse()
    reordered.project_fingerprint = reordered_project.fingerprint()
    respec = uncertain(
        reordered_project, reordered, dict(reversed(dists.items())), [("g", ["y", "x"])]
    )
    other = fu.sample(fu.plan(reordered_project, reordered, respec), seed=99, draws=5000)
    assert all(np.array_equal(first.values[k], other.values[k]) for k in first.values)
    assert other.uncertainty_digest != first.uncertainty_digest
    assert first.columns == ["z", "g"]
    # Independent factors take columns by sorted ID, never declaration order.
    p2, model2, spec2 = product_case()
    swapped = spec2.model_copy(deep=True)
    swapped.distributions.reverse()
    one = fu.sample(fu.plan(p2, model2, spec2), seed=21, draws=500)
    two = fu.sample(fu.plan(p2, model2, swapped), seed=21, draws=500)
    assert one.columns == two.columns == ["x", "y"]
    assert all(np.array_equal(one.values[k], two.values[k]) for k in one.values)
    assert (first.algorithm, first.draws, first.seed) == (fu.ALGORITHM, 5000, 99)
    assert set(first.environment) == {"python", "numpy", "system"}


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (
            {"dists": {"market_a": UniformDistribution(lower=1, upper=2)}},
            "UNCERTAINTY_DERIVED_OUTPUT",
        ),
        (
            {"dists": {"absent": UniformDistribution(lower=1, upper=2)}},
            "UNCERTAINTY_UNKNOWN_FACTOR",
        ),
        (
            {"dists": {"x": UniformDistribution(lower=2, upper=2)}},
            "UNCERTAINTY_INVALID_DISTRIBUTION",
        ),
        ({"dists": {"x": discrete((1.0, 0.5), (3.0, 0.4))}}, "UNCERTAINTY_INVALID_DISTRIBUTION"),
        ({"review": None}, "UNCERTAINTY_UNREVIEWED"),
        ({"groups": [("g", ["x", "y"])], "group_review": None}, "UNCERTAINTY_UNREVIEWED"),
        ({"groups": [("g", ["x", "w"])]}, "UNCERTAINTY_GROUP_MEMBER"),
        ({"groups": [("g", ["x", "y"]), ("h", ["y", "x"])]}, "UNCERTAINTY_GROUP_OVERLAP"),
        ({"groups": [("x", ["x", "y"])]}, "UNCERTAINTY_DUPLICATE_GROUP"),
        ({"duplicate": True}, "UNCERTAINTY_DUPLICATE"),
        ({"stale_model": True}, "UNCERTAINTY_STALE_MODEL"),
        ({"stale_project": True}, "UNCERTAINTY_STALE_PROJECT"),
    ],
)
def test_unsupported_or_ambiguous_specifications_are_refused_before_sampling(change, code):
    p = project()
    model = build(
        p, {"x": (1.0, UNIT), "y": (2.0, "1"), "w": (1.0, "1")}, [("market_a", "x * y * w", "a")]
    )
    dists = change.get("dists", {"x": discrete((1.0, 0.5), (3.0, 0.5)), "y": discrete((2.0, 1.0))})
    spec = uncertain(p, model, dists, change.get("groups", ()), change.get("review", ACCEPTED))
    if "group_review" in change:
        for group in spec.groups:
            group.review = change["group_review"]
        assert all(d.review == ACCEPTED for d in spec.distributions)
    if change.get("duplicate"):
        spec.distributions.append(spec.distributions[0].model_copy())
    if change.get("stale_model"):
        spec.model_digest = "0" * 64
    if change.get("stale_project"):
        p = ps.rename_project(p, "Changed")
        model.project_fingerprint = p.fingerprint()
        spec.model_digest = derived.preview(p, model).model_digest
    with pytest.raises(ValidationFailed) as refused:
        fu.plan(p, model, spec)
    assert code in {i.code for i in refused.value.report.issues}


@pytest.mark.parametrize(
    ("expression", "support", "code"),
    [
        ("y / x", (-1.0, 1.0), "UNCERTAINTY_DENOMINATOR"),
        ("y / (x - x + 1)", (0.5, 7.0), "UNCERTAINTY_DENOMINATOR"),  # conservative, disclosed
        ("x * y - 5 * y", (0.0, 10.0), "UNCERTAINTY_TARGET_NEGATIVE"),
        ("x * x * x * y / 216", (1e200, 1e300), "UNCERTAINTY_NONFINITE"),
    ],
)
def test_unsupported_arithmetic_domains_are_refused_in_preflight(expression, support, code):
    p = project()
    # The accepted value 6 is valid deterministically; only the stated support reaches the edge.
    model = build(p, {"x": (6.0, "1"), "y": (2.0, UNIT)}, [("market_a", expression, "a")])
    assert not derived.preview(p, model).issues
    spec = uncertain(p, model, {"x": UniformDistribution(lower=support[0], upper=support[1])})
    with pytest.raises(ValidationFailed) as refused:
        fu.plan(p, model, spec)
    assert code in {i.code for i in refused.value.report.issues}


def test_an_invalid_draw_is_refused_with_its_index_and_never_dropped(monkeypatch):
    p = project()
    model = build(p, {"x": (1.0, "1"), "y": (2.0, UNIT)}, [("market_a", "y / x", "a")])
    plan = fu.plan(p, model, uncertain(p, model, {"x": UniformDistribution(lower=1, upper=2)}))
    original = plan.marginals["x"].quantile

    def injected(u):
        values = original(u)
        values[17] = 0.0  # bypasses the preflight, as a defect in a marginal would
        return values

    monkeypatch.setitem(plan.marginals, "x", fu._Marginal(injected, (1.0, 2.0), None))
    with pytest.raises(fu.DrawError) as refused:
        fu.sample(plan, seed=1, draws=40)
    assert (refused.value.code, refused.value.draw, refused.value.formula_id) == (
        "FORMULA_ZERO_DIVISION",
        17,
        "market_a",
    )


def test_limits_warnings_and_enumerability():
    p, model, spec = product_case()
    plan = fu.plan(p, model, spec)
    for draws in (0, fu.MAX_DRAWS + 1):
        with pytest.raises(ValidationFailed, match="UNCERTAINTY_LIMIT|validation"):
            fu.sample(plan, seed=1, draws=draws)
    continuous = uncertain(p, model, {"x": UniformDistribution(lower=2, upper=4)})
    planned = fu.plan(p, model, continuous)
    assert [i.code for i in planned.warnings] == ["UNCERTAINTY_VALUE_OUTSIDE_SUPPORT"]
    with pytest.raises(ValidationFailed) as refused:
        fu.enumerate_outcomes(planned)
    assert refused.value.report.issues[0].code == "UNCERTAINTY_NOT_ENUMERABLE"
