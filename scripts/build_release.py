"""Build and inspect a GUI wheel and a wheel rebuilt from the sdist; never publish."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = (
    "nz_deeptech_vc",
    "supplier_selection",
    "supplier_qualification",
    "infrastructure_procurement",
)


def run(*command: str, cwd: Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def inspect_wheel(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        for asset in ("_frontend/index.html", "_build_info.json"):
            assert f"mcda_studio/{asset}" in names, asset
        for name in EXAMPLES:
            for filename in ("README.md", "project.json"):
                assert f"mcda_studio/_examples/{name}/{filename}" in names
        manifests = [
            name
            for name in names
            if name.startswith("mcda_studio/_examples/starter_templates/")
            and name.endswith("/manifest.json")
        ]
        assert len(manifests) == 4, "All four starter manifests must ship"
        assert "mcda_studio/_examples/starter_templates/legacy.json" in names
        for manifest in manifests:
            data = json.loads(archive.read(manifest))
            for artifact in data["artifacts"]:
                target = str(Path(manifest).parent / artifact["path"])
                assert target in names, target
                assert hashlib.sha256(archive.read(target)).hexdigest() == artifact["sha256"]
        assert any(
            n.startswith("mcda_studio/_frontend/assets/") and n.endswith(".js") for n in names
        )
        assert not any(
            part in n.split("/")
            for n in names
            for part in ("node_modules", ".venv", ".git", "private", "test-results", "__pycache__")
        )
        metadata = next(n for n in names if n.endswith(".dist-info/METADATA"))
        text = archive.read(metadata).decode()
        requirements = [line for line in text.splitlines() if line.startswith("Requires-Dist:")]
        for dependency in ("fastapi", "uvicorn"):
            assert all("extra ==" in line for line in requirements if dependency in line)
        return json.loads(archive.read("mcda_studio/_build_info.json"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-frontend", action="store_true", help="Use an already built frontend"
    )
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not args.skip_frontend:
        run("npm", "ci", cwd=ROOT / "frontend")
        run("npm", "run", "build", cwd=ROOT / "frontend")
    direct, rebuilt = out / "direct", out / "from-sdist"
    direct.mkdir(exist_ok=True)
    rebuilt.mkdir(exist_ok=True)
    run(sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(direct))
    run(sys.executable, "-m", "build", "--sdist", "--no-isolation", "--outdir", str(out))
    sdists = sorted(out.glob("*.tar.gz"))
    assert len(sdists) == 1, "Use an output directory containing only this release's sdist"
    with tempfile.TemporaryDirectory(prefix="mcda-sdist-") as tmp:
        with tarfile.open(sdists[0]) as archive:
            names = archive.getnames()
            assert any(n.endswith("/frontend/dist/index.html") for n in names)
            assert any(n.endswith("/frontend/src/main.tsx") for n in names)
            assert not any("node_modules" in n or "/private/" in n for n in names)
            archive.extractall(tmp, filter="data")
        source = next(p for p in Path(tmp).iterdir() if p.is_dir())
        env = dict(os.environ, PIP_NO_INDEX="1")
        env.pop("PYTHONPATH", None)
        subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(rebuilt)],
            cwd=source,
            env=env,
            check=True,
        )
    wheels = [*direct.glob("*.whl"), *rebuilt.glob("*.whl")]
    assert len(wheels) == 2
    identities = [inspect_wheel(w) for w in wheels]
    assert identities[0] == identities[1], "sdist rebuild changed provenance"
    # Negative gate: release builds must not silently omit the GUI.
    with tempfile.TemporaryDirectory(prefix="mcda-missing-assets-") as tmp:
        with tarfile.open(sdists[0]) as archive:
            archive.extractall(tmp, filter="data")
        source = next(p for p in Path(tmp).iterdir() if p.is_dir())
        (source / "frontend/dist/index.html").unlink()
        result = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--no-isolation"],
            cwd=source,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0 and "GUI assets missing" in result.stdout + result.stderr
    files = [sdists[0], *wheels]
    manifest = "".join(
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out).as_posix()}\n"
        for p in files
    )
    (out / "MANIFEST.sha256").write_text(manifest)
    print(manifest, end="")


if __name__ == "__main__":
    main()
