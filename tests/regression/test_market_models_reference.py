"""New sidecar contracts, deterministic invented fixtures and independent formula bounds."""

import json
import math
import runpy
from copy import deepcopy
from pathlib import Path

import pytest

from mcda_studio.services import (
    checked_factor_service,
    factor_analysis_service,
    model_checks_service,
)
from model_builders import inputs
from regression.rounding_oracle import evaluate

ROOT = Path(__file__).resolve().parents[2]


def test_new_model_schemas_and_component_contracts_are_current(tmp_path):
    script = runpy.run_path(str(ROOT / "scripts/export_model_schemas.py"))
    for name, model in script["MODELS"].items():
        assert json.loads((ROOT / "docs/schemas" / name).read_text()) == {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            **model.model_json_schema(mode="validation"),
        }
    script = runpy.run_path(str(ROOT / "scripts/export_model_test_fixtures.py"))
    committed = ROOT / "frontend/tests/fixtures"
    before = {file: file.read_bytes() for file in committed.glob("*.json")}
    script["main"](["--output-dir", str(tmp_path)])
    assert {file.name for file in tmp_path.glob("*.json")} == {
        "screening-summary.json",
        "screening-study-project.json",
        "model-inspection.json",
        "model-bundle.json",
        "starter-catalog.json",
        "starter-fresh.json",
    }
    for file in tmp_path.glob("*.json"):
        script["assert_fixture_matches"](
            file.name, json.loads((committed / file.name).read_text()), json.loads(file.read_text())
        )
    assert all(file.read_bytes() == value for file, value in before.items())


def test_screening_snapshot_names_only_the_six_approved_float_exceptions():
    script = runpy.run_path(str(ROOT / "scripts/export_model_test_fixtures.py"))
    assert script["SCREENING_SUMMARY_FLOAT_PATHS"] == {
        "rows.*.value",
        "rows.*.margin",
        "rows.*.drivers.*.contribution",
        "rows.*.fragility.base_local_weight",
        "rows.*.fragility.local_weight",
        "rows.*.fragility.weight_change",
    }


@pytest.mark.parametrize(
    "path",
    [
        ("value",),
        ("margin",),
        ("drivers", 0, "contribution"),
        ("fragility", "base_local_weight"),
        ("fragility", "local_weight"),
        ("fragility", "weight_change"),
    ],
)
def test_screening_snapshot_accepts_platform_floats_but_preserves_types_and_nullability(path):
    script = runpy.run_path(str(ROOT / "scripts/export_model_test_fixtures.py"))
    committed = json.loads((ROOT / "frontend/tests/fixtures/screening-summary.json").read_text())
    changed = deepcopy(committed)
    target = changed["rows"][0]
    for key in path[:-1]:
        target = target[key]
    value = target[path[-1]]
    assert isinstance(value, float)
    target[path[-1]] = math.nextafter(value, math.inf)
    script["assert_fixture_matches"]("screening-summary.json", committed, changed)
    for invalid in (None, 0, True, "0.5", math.inf, math.nan):
        target[path[-1]] = invalid
        with pytest.raises(AssertionError):
            script["assert_fixture_matches"]("screening-summary.json", committed, changed)
    target[path[-1]] = None
    missing = deepcopy(changed)
    target[path[-1]] = value
    with pytest.raises(AssertionError):
        script["assert_fixture_matches"]("screening-summary.json", missing, changed)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("rows", 0, "rank"), 2),
        (("rows", 0, "rank"), True),
        (("rows", 0, "class_id"), "monitor"),
        (("rows", 0, "open_questions"), 999),
        (("rows", 0, "requirements", "status"), "fail"),
        (("rows", 0, "alternative_id"), "other"),
        (("rows", 0, "name"), "Different name"),
        (("rows", 0, "fragility", "direction"), "lower"),
        (("status",), "unavailable"),
        (("label",), "Different explanation"),
        (("project_fingerprint",), "other"),
        (("configuration", "weight_profile_id"), "technical_ip"),
        (("rows",), []),
        (("excluded_criteria",), []),
    ],
)
def test_screening_snapshot_keeps_every_non_float_field_exact(path, value):
    script = runpy.run_path(str(ROOT / "scripts/export_model_test_fixtures.py"))
    committed = json.loads((ROOT / "frontend/tests/fixtures/screening-summary.json").read_text())
    changed = deepcopy(committed)
    target = changed
    for key in path[:-1]:
        target = target[key]
    assert target[path[-1]] != value or type(target[path[-1]]) is not type(value)
    target[path[-1]] = value
    with pytest.raises(AssertionError):
        script["assert_fixture_matches"]("screening-summary.json", committed, changed)


def test_screening_snapshot_keeps_keys_and_unknown_float_fields_exact():
    script = runpy.run_path(str(ROOT / "scripts/export_model_test_fixtures.py"))
    committed = json.loads((ROOT / "frontend/tests/fixtures/screening-summary.json").read_text())
    missing = deepcopy(committed)
    del missing["rows"][0]["margin"]
    with pytest.raises(AssertionError, match="keys differ"):
        script["assert_fixture_matches"]("screening-summary.json", committed, missing)
    committed["new_float"] = 0.5
    changed = deepcopy(committed)
    changed["new_float"] = math.nextafter(0.5, math.inf)
    with pytest.raises(AssertionError, match="new_float"):
        script["assert_fixture_matches"]("screening-summary.json", committed, changed)
    with pytest.raises(AssertionError):
        script["assert_fixture_matches"]("other.json", {"value": 0.5}, {"value": 0.6})


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
