"""Versioned JSON project files.

* Saving is atomic (write to a temp file in the same directory, then ``os.replace``).
* Output is deterministic (stable key order from the models, 2-space indent, trailing newline),
  so project files diff cleanly under Git.
* Loading checks ``schema_version``, applies registered migrations, then validates the schema.
"""

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from mcda_studio.domain.errors import ProjectLoadError
from mcda_studio.domain.project import SCHEMA_VERSION, Project


def _v1_to_v2(raw: dict[str, Any]) -> dict[str, Any]:
    """Version 2 only adds the optional ``sorting`` section, which a version-1 file cannot hold."""
    if "sorting" in raw:
        raise ProjectLoadError("schema version 1 cannot contain 'sorting'")
    return raw


def _v2_to_v3(raw: dict[str, Any]) -> dict[str, Any]:
    """Version 3 only adds the optional ``smaa`` section, which an older file cannot hold."""
    if "smaa" in raw:
        raise ProjectLoadError("schema version 2 cannot contain 'smaa'")
    return raw


def _v3_to_v4(raw: dict[str, Any]) -> dict[str, Any]:
    """Version 4 only adds the optional ``promethee`` section, which an older file cannot hold."""
    if "promethee" in raw:
        raise ProjectLoadError("schema version 3 cannot contain 'promethee'")
    return raw


def _v4_to_v5(raw: dict[str, Any]) -> dict[str, Any]:
    """Version 5 only adds the optional ``ahp`` section, which an older file cannot hold."""
    if "ahp" in raw:
        raise ProjectLoadError("schema version 4 cannot contain 'ahp'")
    return raw


def _v5_to_v6(raw: dict[str, Any]) -> dict[str, Any]:
    """Version 6 only adds the optional ``requirements`` list, which an older file cannot hold."""
    if "requirements" in raw:
        raise ProjectLoadError("schema version 5 cannot contain 'requirements'")
    return raw


#: ``MIGRATIONS[n]`` upgrades a raw dict from schema version n to n + 1.
MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    1: _v1_to_v2,
    2: _v2_to_v3,
    3: _v3_to_v4,
    4: _v4_to_v5,
    5: _v5_to_v6,
}


def to_json_text(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class JsonProjectRepository:
    def save(self, project: Project, path: str | Path) -> Path:
        target = Path(path)
        _atomic_write(target, to_json_text(project))
        return target

    def load(self, path: str | Path) -> Project:
        source = Path(path)
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ProjectLoadError(f"project file not found: {source}") from None
        except (OSError, UnicodeDecodeError) as exc:
            raise ProjectLoadError(f"cannot read {source}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ProjectLoadError(f"{source} is not valid JSON: {exc}") from exc
        return self.from_dict(raw)

    def from_dict(self, raw: Any) -> Project:
        if not isinstance(raw, dict):
            raise ProjectLoadError("project file must contain a JSON object")
        version = raw.get("schema_version")
        if not isinstance(version, int) or isinstance(version, bool):
            raise ProjectLoadError("project file has no integer 'schema_version'")
        if version > SCHEMA_VERSION:
            raise ProjectLoadError(
                f"project schema version {version} is newer than this program supports "
                f"({SCHEMA_VERSION}); upgrade MCDA Studio"
            )
        if version < 1:
            raise ProjectLoadError(f"invalid schema version {version}")
        while version < SCHEMA_VERSION:
            migrate = MIGRATIONS.get(version)
            if migrate is None:
                raise ProjectLoadError(f"no migration from schema version {version}")
            raw = migrate(raw)
            version += 1
            raw["schema_version"] = version
        try:
            project = Project.model_validate(raw)
        except ValidationError as exc:
            raise ProjectLoadError(f"project file failed schema validation:\n{exc}") from exc
        return project.model_copy(update={"schema_version": project.required_schema_version()})


def save_model(model: BaseModel, path: str | Path) -> Path:
    """Write any result/report model as deterministic JSON (atomic)."""
    target = Path(path)
    _atomic_write(target, to_json_text(model))
    return target
