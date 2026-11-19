"""Shared fixtures for the API tests: a real app over a temporary project directory."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mcda_studio.api import create_app
from mcda_studio.domain.project import Project
from mcda_studio.storage.json_repository import JsonProjectRepository

ROOT = Path(__file__).parents[2]
EXAMPLES = ROOT / "examples"
VC_FILE = EXAMPLES / "nz_deeptech_vc" / "project.json"
SUPPLIER_FILE = EXAMPLES / "supplier_selection" / "project.json"
repo = JsonProjectRepository()


@pytest.fixture
def store_dir(tmp_path: Path) -> Path:
    return tmp_path / "projects"


@pytest.fixture
def client(store_dir: Path) -> Iterator[TestClient]:
    with TestClient(create_app(store_dir, examples_dir=EXAMPLES, frontend_dir=False)) as c:
        yield c


def dump(project: Project) -> dict[str, Any]:
    return project.model_dump(mode="json")


def import_file(client: TestClient, path: Path, **params: str) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    import json

    resp = client.post("/api/projects/import", json=json.loads(raw), params=params)
    assert resp.status_code == 201, resp.text
    body: dict[str, Any] = resp.json()
    return body


def errors(resp: Any) -> dict[str, Any]:
    """The standard error body, asserting its shape."""
    body = resp.json()
    assert set(body) == {"error"}, body
    err: dict[str, Any] = body["error"]
    assert set(err) == {"code", "message", "details"}
    assert isinstance(err["details"], list)
    return err
