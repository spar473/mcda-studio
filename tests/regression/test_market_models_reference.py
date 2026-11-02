"""New sidecar contracts, deterministic invented fixtures and independent formula bounds."""

import json
import runpy
from pathlib import Path

from mcda_studio.services import (
    checked_factor_service,
    factor_analysis_service,
    model_checks_service,
)
from model_builders import inputs
from regression.rounding_oracle import evaluate

ROOT = Path(__file__).resolve().parents[2]


def test_new_model_schemas_and_component_contracts_are_current():
    script = runpy.run_path(str(ROOT / "scripts/export_model_schemas.py"))
    for name, model in script["MODELS"].items():
        assert json.loads((ROOT / "docs/schemas" / name).read_text()) == {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            **model.model_json_schema(mode="validation"),
        }
    fixtures = runpy.run_path(str(ROOT / "scripts/export_model_test_fixtures.py"))["fixtures"]()
    for name, value in fixtures.items():
        assert json.loads((ROOT / "frontend/tests/fixtures" / name).read_text()) == value


def test_starter_builder_is_deterministic_and_never_rewrites_original_fixtures(tmp_path):
    files = [
        file
        for folder in (
            "starter_templates",
            "external_proposals",
            "nz_deeptech_vc",
            "market_research",
        )
        for file in (ROOT / "examples" / folder).rglob("*")
        if file.is_file() and file.suffix in {".json", ".csv", ".md"}
    ]
    original = {file: file.read_bytes() for file in files}
    build = runpy.run_path(str(ROOT / "examples/market_research/build.py"))["build"]
    for directory in ("first", "second"):
        build(tmp_path / directory / "templates", tmp_path / directory / "demo")
    generated = {
        file.relative_to(tmp_path / "first"): file.read_bytes()
        for file in (tmp_path / "first").rglob("*")
        if file.is_file()
    }
    assert generated
    assert generated == {
        file.relative_to(tmp_path / "second"): file.read_bytes()
        for file in (tmp_path / "second").rglob("*")
        if file.is_file()
    }
    assert all(file.read_bytes() == data for file, data in original.items())


def test_exact_decimal_market_formulas_and_shared_draws_satisfy_independent_forward_bounds():
    p, model, spec, declaration, comparison = inputs()
    result = checked_factor_service.run(
        p,
        model,
        spec,
        declaration,
        factor_analysis_service.FactorRunParameters(run="mavt", draws=16, seed=73),
    )
    expressions = {formula.id: formula.expression for formula in model.formulas}
    for trace in result.record.result.trace:
        row = {**trace.factors, **trace.formulas}
        for name in ("bottom_a", "bottom_b"):
            assert name in row
            assert evaluate(expressions[name], row).contains(row[name])
    assert evaluate("total * share", {"total": "100000000", "share": "0.01"}).contains(
        model_checks_service.run_output(p, comparison.right).value
    )


def test_ui_fixture_reference_metadata_is_portable_without_leaking_into_live_runs():
    import platform
    from unittest.mock import patch

    import numpy as np

    render = runpy.run_path(str(ROOT / "scripts/export_model_test_fixtures.py"))["fixtures"]
    expected = render()
    original = (platform.python_version(), platform.system(), platform.machine(), np.__version__)
    with (
        patch.object(platform, "system", return_value="Different system"),
        patch.object(np, "__version__", "different-version"),
    ):
        assert render() == expected
        assert platform.system() == "Different system" and np.__version__ == "different-version"
    assert (
        platform.python_version(),
        platform.system(),
        platform.machine(),
        np.__version__,
    ) == original
