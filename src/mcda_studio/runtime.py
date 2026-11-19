"""Distribution identity and resource lookup, independent of optional API dependencies."""

import hashlib
import json
import os
from contextlib import ExitStack
from importlib import metadata, resources
from pathlib import Path

from mcda_studio import __version__


def package_version() -> str:
    try:
        return metadata.version("mcda-studio")
    except metadata.PackageNotFoundError:
        return __version__


def source_checkout() -> Path | None:
    package = Path(__file__).resolve().parent
    root = package.parent.parent
    if (root / "pyproject.toml").is_file() and root / "src/mcda_studio" == package:
        return root
    return None


def asset_directory(name: str, explicit: str | Path | None, stack: ExitStack) -> Path | None:
    """Explicit path, env, checkout, then package; extraction lives until stack closes."""
    configured = explicit if explicit is not None else os.environ.get(f"MCDA_STUDIO_{name.upper()}")
    if configured is not None:
        directory = Path(configured).expanduser()
        required = directory / "index.html" if name == "frontend" else directory
        if not required.exists():
            raise ValueError(f"Configured {name} path is missing: {required}")
        return directory
    checkout = source_checkout()
    relative = "frontend/dist" if name == "frontend" else "examples"
    if checkout and (checkout / relative).is_dir():
        return checkout / relative
    bundled = resources.files("mcda_studio").joinpath(f"_{name}")
    if bundled.is_dir():
        return stack.enter_context(resources.as_file(bundled))
    return None


def build_identity(frontend: Path | None = None) -> dict[str, str | bool | None]:
    manifest = resources.files("mcda_studio").joinpath("_build_info.json")
    identity: dict[str, str | bool | None] = {
        "source_revision": None,
        "source_dirty": None,
        "frontend_index_sha256": None,
    }
    if manifest.is_file():
        identity.update(json.loads(manifest.read_text(encoding="utf-8")))
    # Identify the index actually served, including an explicit override.
    if frontend is not None:
        index = frontend / "index.html"
        identity["frontend_index_sha256"] = (
            hashlib.sha256(index.read_bytes()).hexdigest() if index.is_file() else None
        )
    return identity
