"""Bundle only release assets; editable engine installs do not require a frontend build."""

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

EXAMPLES = (
    "nz_deeptech_vc",
    "supplier_selection",
    "supplier_qualification",
    "infrastructure_procurement",
)


def starter_assets(root):
    directory = root / "examples/starter_templates"
    legacy = directory / "legacy.json"
    if not legacy.is_file():
        raise RuntimeError("Starter legacy definitions missing")
    paths = {legacy}
    manifests = list(directory.glob("*/manifest.json"))
    if not manifests:
        raise RuntimeError("Starter manifests missing")
    for manifest in manifests:
        data = json.loads(manifest.read_bytes())
        content = {key: value for key, value in data.items() if key != "digest"}
        digest = hashlib.sha256(
            json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        if data["digest"] != digest:
            raise RuntimeError("Starter manifest digest mismatch")
        paths.add(manifest)
        for artifact in data["artifacts"]:
            path = manifest.parent / artifact["path"]
            if not path.resolve().is_relative_to(manifest.parent.resolve()) or not path.is_file():
                raise RuntimeError("Starter artifact path missing or outside manifest directory")
            if hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
                raise RuntimeError("Starter artifact hash mismatch")
            paths.add(path)
    return sorted(paths)


class ReleaseAssetsHook(BuildHookInterface):
    def initialize(self, version, build_data):
        if version == "editable":
            return
        root = Path(self.root)
        frontend = root / "frontend/dist"
        index = frontend / "index.html"
        if not index.is_file() or not any((frontend / "assets").glob("*.js")):
            raise RuntimeError("GUI assets missing: run npm ci and npm run build in frontend first")
        for name in EXAMPLES:
            for filename in ("project.json", "README.md"):
                if not (root / "examples" / name / filename).is_file():
                    raise RuntimeError(f"Bundled example missing: {name}/{filename}")
        starters = starter_assets(root)
        archived = root / "src/mcda_studio/_build_info.json"
        if archived.is_file():
            identity = json.loads(archived.read_text())
            if identity["frontend_index_sha256"] != hashlib.sha256(index.read_bytes()).hexdigest():
                raise RuntimeError("Archived frontend does not match its build identity")
        else:
            revision, dirty = None, None
            if (root / ".git").exists():
                revision = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=root, text=True
                ).strip()
                dirty = bool(
                    subprocess.check_output(
                        ["git", "status", "--porcelain"], cwd=root, text=True
                    ).strip()
                )
            identity = {
                "source_revision": revision,
                "source_dirty": dirty,
                "frontend_index_sha256": hashlib.sha256(index.read_bytes()).hexdigest(),
            }
        self._staging = tempfile.TemporaryDirectory(prefix="mcda-build-")
        manifest = Path(self._staging.name) / "build-info.json"
        manifest.write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n")
        included = build_data.setdefault("force_include", {})
        if self.target_name == "wheel":
            included[str(frontend)] = "mcda_studio/_frontend"
            included[str(manifest)] = "mcda_studio/_build_info.json"
            for name in EXAMPLES:
                for filename in ("project.json", "README.md"):
                    included[str(root / "examples" / name / filename)] = (
                        f"mcda_studio/_examples/{name}/{filename}"
                    )
            for path in starters:
                included[str(path)] = (
                    "mcda_studio/_examples/" + path.relative_to(root / "examples").as_posix()
                )
        else:
            for path in starters:
                included[str(path)] = path.relative_to(root).as_posix()
            included[str(frontend)] = "frontend/dist"
            included[str(manifest)] = "src/mcda_studio/_build_info.json"

    def finalize(self, version, build_data, artifact_path):
        if hasattr(self, "_staging"):
            self._staging.cleanup()
