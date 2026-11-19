"""Safe deterministic formulas, review gates, units and dependency integrity."""

import json
from fractions import Fraction
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from typer.testing import CliRunner

from mcda_studio.cli import app
from mcda_studio.domain.derived import DerivedModel
from mcda_studio.domain.errors import StaleRevisionError, ValidationFailed
from mcda_studio.domain.evidence import Origin
from mcda_studio.domain.uncertainty import CellUncertainty, SmaaModel, UniformDistribution
from mcda_studio.methods.formulas import FormulaError, Quantity, calculate, parse
from mcda_studio.services import derived_service as derived
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/derived_measurements"


def example(name="venture"):
    project = JsonProjectRepository().load(EXAMPLE / f"{name}-project.json")
    model = DerivedModel.model_validate_json((EXAMPLE / f"{name}-model.json").read_text())
    return project, model


def codes(report):
    return {issue.code for issue in report.issues}


def test_reviewed_source_formula_and_shared_factor_trace_are_reproducible():
    p, m = example()
    before = to_json_text(p), m.model_dump_json()
    report = derived.preview(p, m)
    assert report.issues == []
    assert [c.value for c in report.calculations] == [600_000, 640_000]
    assert all("addressable_customers" in c.source_ids for c in report.calculations)
    assert all(c.dimension == {"NZD": 1, "year": -1} for c in report.calculations)
    assert derived.preview(p, m).model_dump_json() == report.model_dump_json()
    compiled = derived.compile_copy(p, m, report.review_digest)
    assert compiled.performance_index() == {("a", "result"): 600_000, ("b", "result"): 640_000}
    assert (to_json_text(p), m.model_dump_json()) == before
    # The preview owns a full provenance snapshot, unaffected by a later change.
    m.sources[0].source.description = "Revised"
    assert report.model.sources[0].source.description != "Revised"
    with pytest.raises(StaleRevisionError):
        derived.compile_copy(p, m, report.review_digest)


def test_supplier_tco_against_independent_rational_arithmetic():
    p, m = example("supplier")
    report = derived.preview(p, m)
    assert not report.issues
    values = {c.id: c.value for c in report.calculations}
    assert values == {"purchase_volume": 3000, "tco_a": 155000, "tco_b": 161000}
    assert Fraction(values["tco_a"]) == Fraction(5000) + 3 * (1000 * 40 + 10000)
    tco = next(c for c in report.calculations if c.id == "tco_a")
    assert tco.dependencies == ["maintenance_a", "price_a", "purchase_volume", "setup_a", "years"]
    assert tco.source_ids == ["annual_units", "maintenance_a", "price_a", "setup_a", "years"]
    assert "purchase_volume" not in tco.source_ids
    m.formulas.reverse()
    reversed_report = derived.preview(p, m)
    assert not reversed_report.issues
    assert {c.id: c.value for c in reversed_report.calculations} == values


@pytest.mark.parametrize(
    "expression,code",
    [
        ("__import__('os').system('false')", "FORMULA_UNSUPPORTED"),
        ("(1).__class__", "FORMULA_UNSUPPORTED"),
        ("[x for x in [1]]", "FORMULA_UNSUPPORTED"),
        ("lambda: 1", "FORMULA_UNSUPPORTED"),
        ("2 ** 3", "FORMULA_UNSUPPORTED"),
        ("True + 1", "FORMULA_UNSUPPORTED"),
        ("min(1)", "FORMULA_UNSUPPORTED"),
        ("max(a=1,b=2)", "FORMULA_UNSUPPORTED"),
        ("1/0", "FORMULA_ZERO_DIVISION"),
        ("1e308 * 100", "FORMULA_NONFINITE"),
        ("1e309", "FORMULA_NONFINITE"),
        ("1 +", "FORMULA_SYNTAX"),
        ("+".join(["1"] * 100), "FORMULA_LIMIT"),
    ],
)
def test_unsupported_and_invalid_arithmetic_has_explicit_errors(expression, code):
    with pytest.raises(FormulaError) as caught:
        calculate(parse(expression), lambda key: Quantity(1, {}))
    assert caught.value.code == code


def test_units_min_max_and_unary_operations():
    q = {"cost": Quantity(4, {"NZD": 1}), "other": Quantity(8, {"NZD": 1})}
    assert calculate(
        parse("max(cost, min(other, cost + other)) - -cost / 2"), q.__getitem__
    ) == Quantity(10, {"NZD": 1})
    for expression in ("cost + 1", "min(cost, 1)"):
        with pytest.raises(FormulaError, match="matching dimensions"):
            calculate(parse(expression), q.__getitem__)


def test_unaccepted_sources_and_formulas_never_compile_or_become_zero():
    p, m = example()
    m.sources[0].review = None
    report = derived.preview(p, m)
    assert "DERIVED_UNREVIEWED_SOURCE" in codes(report) and not report.calculations
    with pytest.raises(ValidationFailed):
        derived.compile_copy(p, m, report.review_digest)
    p, m = example()
    m.sources[0].value = None
    assert "DERIVED_MISSING_INPUT" in codes(derived.preview(p, m))
    p, m = example()
    m.formulas[0].review = None
    assert "DERIVED_UNREVIEWED_FORMULA" in codes(derived.preview(p, m))


def test_tool_proposals_need_review_and_corrections_replace_only_the_accepted_input():
    p, m = example()
    source = m.sources[0]
    source.origin = Origin(
        kind="tool", proposed_by="Synthetic extractor", tool_id="demo", tool_version="1"
    )
    original_review = source.review.model_copy(deep=True)
    source.review = None
    assert "DERIVED_UNREVIEWED_SOURCE" in codes(derived.preview(p, m))
    source.review = original_review.model_copy(
        update={"status": "corrected", "corrected_value": 5000.0}
    )
    report = derived.preview(p, m)
    assert not report.issues
    assert [c.value for c in report.calculations] == [300000, 320000]
    assert source.value == 10000  # preserve the original recorded claim


def test_reserved_names_units_and_resource_limits_are_explicit():
    p, m = example()
    m.units["1"] = {"currency": 1}
    assert "DERIVED_UNIT_DEFINITION" in codes(derived.preview(p, m))
    m.units = {}
    m.sources[0].id = "min"
    assert "DERIVED_RESERVED_ID" in codes(derived.preview(p, m))
    with pytest.raises(FormulaError) as exc:
        parse("1" * 2001)
    assert exc.value.code == "FORMULA_LIMIT"
    with pytest.raises(FormulaError) as exc:
        calculate(parse("a * a"), lambda key: Quantity(1, {"x": 16}))
    assert exc.value.code == "FORMULA_DIMENSION_LIMIT"


def test_nested_dependency_limit_is_an_explicit_issue_not_an_interpreter_crash():
    p, m = example()
    template = m.formulas[0]
    m.formulas = [
        template.model_copy(
            update={
                "id": f"f{k}",
                "expression": f"f{k + 1}" + " * 1" * 25,
                "alternative_id": None,
                "criterion_id": None,
            }
        )
        for k in range(65)
    ]
    result = derived.preview(p, m)
    assert codes(result) <= {"DERIVED_DEPTH_LIMIT", "FORMULA_LIMIT", "DERIVED_UNKNOWN_INPUT"}
    assert codes(result) & {"DERIVED_DEPTH_LIMIT", "FORMULA_LIMIT"}


def test_cycles_unknown_references_dimensions_duplicates_and_stale_models():
    p, m = example()
    m.formulas[0].expression = "market_b"
    m.formulas[1].expression = "market_a"
    assert codes(derived.preview(p, m)) == {"DERIVED_CYCLE"}
    m.formulas[0].expression = "unknown"
    assert "DERIVED_UNKNOWN_INPUT" in codes(derived.preview(p, m))
    p, m = example()
    m.formulas[0].unit = "customers"
    assert "DERIVED_OUTPUT_DIMENSION" in codes(derived.preview(p, m))
    p, m = example()
    m.sources[0].unit = "USD"
    assert "DERIVED_UNKNOWN_UNIT" in codes(derived.preview(p, m))
    p, m = example()
    m.sources.append(m.sources[0])
    assert "DERIVED_DUPLICATE_ID" in codes(derived.preview(p, m))
    p, m = example()
    p.title = "Revised"
    assert "DERIVED_STALE_PROJECT" in codes(derived.preview(p, m))


def test_target_integrity_and_existing_uncertainty_are_not_silently_reinterpreted():
    p, m = example()
    m.formulas[1].alternative_id = "a"
    assert "DERIVED_DUPLICATE_TARGET" in codes(derived.preview(p, m))
    p, m = example()
    p.smaa = SmaaModel(
        cells=[
            CellUncertainty(
                alternative_id="a",
                criterion_id="result",
                distribution=UniformDistribution(lower=0, upper=1e6),
            )
        ]
    )
    m.project_fingerprint = p.fingerprint()
    assert "DERIVED_UNCERTAINTY_UNSUPPORTED" in codes(derived.preview(p, m))


@given(st.integers(0, 100000), st.integers(0, 100), st.integers(1, 100000))
def test_bottom_up_arithmetic_against_fraction_oracle(customers, adoption_percent, price):
    variables = {
        "n": Quantity(float(customers), {"customer": 1}),
        "r": Quantity(adoption_percent / 100, {}),
        "p": Quantity(float(price), {"NZD": 1, "customer": -1, "year": -1}),
    }
    actual = calculate(parse("n * r * p"), variables.__getitem__)
    expected = Fraction(customers * adoption_percent * price, 100)
    assert actual.value == pytest.approx(float(expected), rel=5e-16, abs=1e-12)
    assert actual.dimension == {"NZD": 1, "year": -1}


def test_cli_compiles_new_copy_and_never_overwrites(tmp_path):
    p, m = example("supplier")
    runner = CliRunner()
    arguments = [str(EXAMPLE / "supplier-project.json"), str(EXAMPLE / "supplier-model.json")]
    result = runner.invoke(app, ["derived", "preview", *arguments])
    assert result.exit_code == 0
    report = json.loads(result.stdout)
    target = tmp_path / "compiled.json"
    args = [
        "derived",
        "compile",
        *arguments,
        "--review-digest",
        report["review_digest"],
        "-o",
        str(target),
    ]
    assert runner.invoke(app, args).exit_code == 0
    before = target.read_bytes()
    assert JsonProjectRepository().load(target).performance_index()[("a", "result")] == 155000
    assert runner.invoke(app, args).exit_code != 0
    assert target.read_bytes() == before
