import json
from pathlib import Path
from typing import Any

import pytest

from mcda_studio.domain.errors import ProjectLoadError
from mcda_studio.domain.project import SCHEMA_VERSION, Project
from mcda_studio.methods.mavt.aggregation import evaluate_mavt
from mcda_studio.storage import json_repository as jr
from mcda_studio.storage.json_repository import JsonProjectRepository, save_model

from builders import tiny_project

repo = JsonProjectRepository()


def test_round_trip_preserves_everything(tmp_path: Path) -> None:
    p = tiny_project()
    path = repo.save(p, tmp_path / "p.json")
    q = repo.load(path)
    assert q == p and q.fingerprint() == p.fingerprint()
    assert evaluate_mavt(q) == evaluate_mavt(p)


def test_saving_is_deterministic_and_leaves_no_temp_files(tmp_path: Path) -> None:
    p = tiny_project()
    repo.save(p, tmp_path / "a.json")
    repo.save(p, tmp_path / "b.json")
    assert (tmp_path / "a.json").read_text() == (tmp_path / "b.json").read_text()
    assert (tmp_path / "a.json").read_text().endswith("}\n")
    assert sorted(f.name for f in tmp_path.iterdir()) == ["a.json", "b.json"]


def test_overwrite_is_atomic_when_serialisation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = repo.save(tiny_project(), tmp_path / "p.json")
    original = path.read_text()

    def boom(_: Any) -> str:
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(jr, "to_json_text", boom)
    with pytest.raises(RuntimeError):
        repo.save(tiny_project(), path)
    assert path.read_text() == original


def test_save_creates_missing_directories(tmp_path: Path) -> None:
    repo.save(tiny_project(), tmp_path / "x" / "y" / "p.json")
    assert (tmp_path / "x" / "y" / "p.json").exists()


def test_result_models_can_be_saved(tmp_path: Path) -> None:
    out = save_model(evaluate_mavt(tiny_project()), tmp_path / "r.json")
    assert json.loads(out.read_text())["method"] == "mavt"


@pytest.mark.parametrize(
    "content,match",
    [
        ("{not json", "not valid JSON"),
        ("[1, 2]", "JSON object"),
        ("{}", "schema_version"),
        ('{"schema_version": "1"}', "schema_version"),
        ('{"schema_version": true}', "schema_version"),
        ('{"schema_version": 0}', "invalid schema version"),
        (f'{{"schema_version": {SCHEMA_VERSION + 1}}}', "newer than this program"),
        (f'{{"schema_version": {SCHEMA_VERSION}, "id": "x"}}', "failed schema validation"),
    ],
)
def test_malformed_files_fail_clearly(tmp_path: Path, content: str, match: str) -> None:
    path = tmp_path / "bad.json"
    path.write_text(content)
    with pytest.raises(ProjectLoadError, match=match):
        repo.load(path)


def test_missing_file_and_directory(tmp_path: Path) -> None:
    with pytest.raises(ProjectLoadError, match="not found"):
        repo.load(tmp_path / "nope.json")
    with pytest.raises(ProjectLoadError):
        repo.load(tmp_path)


def test_unknown_fields_and_wrong_types_are_rejected(tmp_path: Path) -> None:
    d = tiny_project().model_dump(mode="json")
    d["alternatives"][0]["colour"] = "red"
    with pytest.raises(ProjectLoadError, match="schema validation"):
        repo.from_dict(d)
    d = tiny_project().model_dump(mode="json")
    d["performances"][0]["value"] = [1, 2]
    with pytest.raises(ProjectLoadError):
        repo.from_dict(d)


def test_migrations_are_applied_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    d = tiny_project().model_dump(mode="json")
    d["schema_version"] = 1
    d["title"] = "old title"

    def to_v2(raw: dict[str, Any]) -> dict[str, Any]:
        raw = dict(raw)
        raw["title"] = raw["title"].upper()
        return raw

    monkeypatch.setattr(jr, "SCHEMA_VERSION", 2)
    monkeypatch.setitem(jr.MIGRATIONS, 1, to_v2)
    loaded = repo.from_dict(d)
    # migrated, then held at the lowest version that can represent it (no version-2 section)
    assert loaded.title == "OLD TITLE" and loaded.schema_version == 1
    monkeypatch.delitem(jr.MIGRATIONS, 1)
    with pytest.raises(ProjectLoadError, match="no migration"):
        repo.from_dict(d)


def test_json_schema_can_be_generated() -> None:
    schema = Project.model_json_schema()
    assert "alternatives" in schema["properties"]
