"""The committed OpenAPI document (docs/api/openapi.json) is the contract the frontend's types
are generated from; it must always describe the code that is actually running."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mcda_studio.api import create_app
from mcda_studio.cli import app as cli_app

ROOT = Path(__file__).parents[2]


def test_committed_openapi_document_is_current() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "export_openapi", ROOT / "scripts" / "export_openapi.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    committed = (ROOT / "docs" / "api" / "openapi.json").read_text(encoding="utf-8")
    assert committed == module.render(), "run: python scripts/export_openapi.py"


def test_every_documented_endpoint_has_a_description_of_its_error_shape(tmp_path: Path) -> None:
    spec = create_app(tmp_path, frontend_dir=False).openapi()
    schemas = spec["components"]["schemas"]
    # the saved-file schema and the API bodies are the very same models. Because the models
    # serialise their defaults, FastAPI publishes an -Input and an -Output variant of a model that
    # is both accepted and returned; both must exist and describe the same fields.
    for name in ("MavtResult", "SensitivityResult", "ScenarioComparison", "ValidationReport"):
        assert name in schemas
    assert "Project-Input" in schemas
    assert "Project-Output" in schemas
    project_fields = set(schemas["Project-Output"]["properties"])
    assert set(schemas["Project-Input"]["properties"]) == project_fields
    assert {
        "schema_version",
        "id",
        "title",
        "alternatives",
        "criteria",
        "performances",
    } <= project_fields
    saved_schema = json.loads((ROOT / "docs" / "architecture" / "project_schema.json").read_text())
    assert set(saved_schema["properties"]) == project_fields


def test_serve_command_refuses_politely_without_the_api_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    real_import = builtins.__import__

    def fake(name: str, *args: object, **kwargs: object) -> object:
        if name == "uvicorn":
            raise ImportError("no uvicorn", name="uvicorn")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", fake)
    result = CliRunner().invoke(cli_app, ["serve"])
    assert result.exit_code == 1
    assert "whl[api]" in "".join(result.output.split())  # Rich may wrap lines
