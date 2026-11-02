"""Owner-approved bound derivation and exact engine-to-engine/boundary contracts."""

from fractions import Fraction

import pytest

from mcda_studio.domain.derived import DerivedFormula, DerivedModel, SourceFactor
from mcda_studio.domain.errors import ValidationFailed
from mcda_studio.domain.model_comparison import ModelChecks, QuantityCheck
from mcda_studio.services import derived_service as derived
from mcda_studio.services import model_checks_service as checks
from model_builders import ORIGIN, REVIEW, inputs
from regression.rounding_oracle import Bounded, U, evaluate


def test_forward_bound_covers_binary64_rounding_but_excludes_one_percent_error():
    result = evaluate("x * y * z", {"x": "1", "y": "0.05", "z": "3"})
    assert result.exact == Fraction(3, 20)
    assert result.contains(0.15000000000000002)
    assert not result.contains(0.1515)
    assert Bounded.input("0.05").error == Fraction("0.05") * U
    assert Bounded.input("0.25").error == 0


@pytest.mark.parametrize("expression", ["x + y", "x - y", "x * y", "x / y"])
def test_dyadic_formula_shapes_retain_exact_equality_through_deterministic_path(expression):
    p, original, _, _, _ = inputs()
    model = DerivedModel(
        project_fingerprint=p.fingerprint(),
        sources=[
            SourceFactor(
                id=id,
                value=value,
                unit="1",
                source=original.sources[0].source,
                origin=ORIGIN,
                review=REVIEW,
            )
            for id, value in (("x", 0.5), ("y", 0.25))
        ],
        formulas=[
            DerivedFormula(
                id="result", expression=expression, unit="1", origin=ORIGIN, review=REVIEW
            )
        ],
    )
    preview = derived.preview(p, model)
    bundle = derived.compilation_bundle(p, model, preview.review_digest)
    actual = bundle.preview.calculations[0].value
    oracle = evaluate(expression, {"x": "0.5", "y": "0.25"})
    assert Fraction.from_float(actual) == oracle.exact
    assert oracle.contains(actual)


def test_addition_subtraction_product_and_denominator_errors_are_propagated():
    for expression, actual in (
        ("x + y", 0.1 + 0.2),
        ("x - y", 0.1 - 0.2),
        ("x * y", 0.1 * 0.2),
        ("x / y", 0.1 / 0.2),
    ):
        assert evaluate(expression, {"x": "0.1", "y": "0.2"}).contains(actual)
    with pytest.raises(ValueError, match="contains zero"):
        Bounded.input("1") / Bounded(Fraction(1), Fraction(1))
    with pytest.raises(ValueError, match="arithmetic model"):
        Bounded.input("1e-320")


def test_computed_binary64_rounding_crosses_inclusive_decimal_boundary_without_tolerance():
    p, original, _, _, _ = inputs()
    model = DerivedModel(
        project_fingerprint=p.fingerprint(),
        sources=[
            SourceFactor(
                id=id,
                value=value,
                unit="1",
                source=original.sources[0].source,
                origin=ORIGIN,
                review=REVIEW,
            )
            for id, value in (("x", 0.1), ("y", 0.2))
        ],
        formulas=[
            DerivedFormula(id="sum", expression="x + y", unit="1", origin=ORIGIN, review=REVIEW)
        ],
    )
    value = derived.preview(p, model).calculations[0].value
    assert value == 0.30000000000000004
    declaration = ModelChecks(
        project_fingerprint=p.fingerprint(),
        model_digest=derived._digest(model.model_dump(mode="json")),
        checks=[
            QuantityCheck(
                id="upper_limit", quantity_kind="formula", quantity_id="sum", unit="1", upper=0.3
            )
        ],
        origin=ORIGIN,
        review=REVIEW,
        digest="",
    )
    declaration.digest = checks.checks_digest(declaration)
    with pytest.raises(ValidationFailed, match="upper_limit"):
        checks.check_values(declaration, {"sum": value})
    assert not checks._contains(declaration.checks[0], value)
