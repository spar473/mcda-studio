"""Verify both installed wheels and a consumer pipx install outside the checkout."""

import argparse
import contextlib
import hashlib
import json
import os
import platform
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import venv
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = {
    "nz_deeptech_vc",
    "supplier_selection",
    "supplier_qualification",
    "infrastructure_procurement",
}
EXPECTED = [0.7226678550207962, 0.6599105426568632, 0.5985654393128845, 0.5733847765581512]


def playwright_browsers() -> Path:
    """Playwright's default browser cache for the calling user, read before HOME is isolated.
    This smoke workflow is POSIX-only (it uses the bin/ venv layout)."""
    if sys.platform == "darwin":
        return Path.home() / "Library/Caches/ms-playwright"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "ms-playwright"


def run(*command: str, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(
            f"{command[0]} failed ({result.returncode}):\n{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def request(url: str, body: Any = None) -> Any:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def verify_ranking(result: Any) -> None:
    assert [r["alternative_id"] for r in result["ranking"]] == [
        "forever_harvest",
        "outlier_space",
        "kura_dynamics",
        "hyades",
    ]
    assert all(
        abs(row["value"] - value) <= 1e-12
        for row, value in zip(result["ranking"], EXPECTED, strict=True)
    )


@contextlib.contextmanager
def server(command: Path, work: Path, env: dict[str, str]):
    # Startup binds the candidate port before opening a browser; a rare race fails safely.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    log = work / "server.log"
    with log.open("w") as output:
        process = subprocess.Popen(
            [
                str(command),
                "serve",
                "--no-open",
                "--port",
                str(port),
                "--store",
                str(work / "projects"),
            ],
            cwd=work,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            for _ in range(200):
                if process.poll() is not None:
                    raise RuntimeError(log.read_text())
                try:
                    request(url + "/api/health")
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                raise RuntimeError(f"Server not ready: {log.read_text()}")
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def exercise(command: Path, python: Path, work: Path, env: dict[str, str], browser: bool) -> None:
    work.mkdir()
    location = run(
        str(python), "-c", "import mcda_studio; print(mcda_studio.__file__)", cwd=work, env=env
    )
    assert ROOT not in Path(location.strip()).parents, location
    assert "mcda-studio" in run(str(command), "--version", cwd=work, env=env)
    run(str(command), "--help", cwd=work, env=env)
    run(str(python), "-m", "pip", "check", cwd=work, env=env)
    # The browser imports VC itself; the API imports the other two and verifies all three names.
    with server(command, work, env) as url:
        with urllib.request.urlopen(url) as response:
            html = response.read().decode()
        assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)
        assert any(a.endswith(".js") for a in assets) and any(a.endswith(".css") for a in assets)
        for asset in assets:
            with urllib.request.urlopen(url + asset) as response:
                assert response.status == 200 and response.read()
        # Installed startup must refuse an independent owner, before any browser is opened.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            second_port = probe.getsockname()[1]
        blocked = subprocess.run(
            [
                str(command),
                "serve",
                "--no-open",
                "--store",
                str(work / "projects"),
                "--port",
                str(second_port),
            ],
            cwd=work,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert blocked.returncode == 1 and "owned by another process" in " ".join(
            blocked.stderr.split()
        )
        health = request(url + "/api/health")
        assert health["build"]["frontend_index_sha256"]
        starters = request(url + "/api/starter-templates")
        assert len(starters) == 4
        for starter in starters:
            body = {
                "template_id": starter["id"],
                "project_id": "installed_" + starter["id"],
                "title": "Installed illustrative draft",
            }
            material = request(url + "/api/starter-templates/instantiate", body)
            assert material["receipt"]["template_digest"] == starter["digest"]
            assert request(url + "/api/starter-templates/verify", material) == material
            assert "require your review" in material["project"]["description"]
            input_file = work / (starter["id"] + "-starter-request.json")
            output_file = work / (starter["id"] + "-starter-materials.json")
            input_file.write_text(json.dumps(body))
            run(
                str(command),
                "starter-templates",
                "instantiate",
                str(input_file),
                "-o",
                str(output_file),
                cwd=work,
                env=env,
            )
            assert json.loads(output_file.read_text()) == material
        examples = request(url + "/api/examples")
        assert {e["name"] for e in examples} == EXAMPLES
        if browser:
            run("node", str(ROOT / "scripts/smoke_browser.mjs"), url, str(work), cwd=work, env=env)
        for example in sorted(EXAMPLES - ({"nz_deeptech_vc"} if browser else set())):
            request(url + f"/api/examples/{example}/import", {})
        projects = request(url + "/api/projects")["projects"]
        assert len(projects) == len(EXAMPLES)
        vc = next(e for e in examples if e["name"] == "nz_deeptech_vc")["project_id"]
        record = request(url + f"/api/projects/{vc}/analysis/record", {})
        verify_ranking(record["result"])
        exported = request(
            url + f"/api/projects/{vc}/analysis/export",
            {
                "format": "json",
                "expected_project_fingerprint": record["result"]["project_fingerprint"],
                "expected_record_digest": record["record_digest"],
            },
        )
        source = work / "exported-project.json"
        source.write_text(json.dumps(exported["source_project"]))
        run(str(command), "validate", str(source), cwd=work, env=env)
        repeated = json.loads(
            run(str(command), "evaluate", str(source), "--json", cwd=work, env=env)
        )
        assert repeated == exported["record"]["result"]
        if browser:
            document = json.loads((work / "browser-analysis.json").read_text())
            assert document["record"]["result"] == repeated
    # A fresh process reopens the actual saved library.
    with server(command, work, env) as url:
        reopened = request(url + f"/api/projects/{vc}/analysis/record", {})
        assert reopened == record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument(
        "--wheelhouse", type=Path, help="Verified dependency wheels for offline installs"
    )
    parser.add_argument(
        "--browser", action="store_true", help="Drive the installed GUI in Chromium"
    )
    args = parser.parse_args()
    dist = args.dist.resolve()
    wheels = [next((dist / route).glob("*.whl")) for route in ("direct", "from-sdist")]
    output = dist / "smoke-evidence"
    output.mkdir(exist_ok=True)
    pip_args = (
        ["--no-index", "--find-links", str(args.wheelhouse.resolve())] if args.wheelhouse else []
    )
    with tempfile.TemporaryDirectory(prefix="mcda-installed-") as tmp:
        work = Path(tmp)
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("MCDA_STUDIO_") and k not in ("PYTHONPATH", "PYTHONHOME")
        }
        # Isolating HOME/XDG_CACHE_HOME must not hide browsers Playwright already installed.
        env.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(playwright_browsers()))
        env.update(
            HOME=str(work / "home"),
            XDG_CACHE_HOME=str(work / "cache"),
            PIP_CACHE_DIR=str(work / "pip-cache"),
            PIP_CONFIG_FILE=os.devnull,
        )
        if args.wheelhouse:
            env.update(PIP_NO_INDEX="1", PIP_FIND_LINKS=str(args.wheelhouse.resolve()))
        for index, wheel in enumerate(wheels):
            target = work / f"venv-{index}"
            venv.EnvBuilder(with_pip=True).create(target)
            python = target / "bin/python"
            run(
                str(python),
                "-m",
                "pip",
                "install",
                *pip_args,
                "--require-hashes",
                "-r",
                str(ROOT / "requirements/runtime-py312.txt"),
                cwd=work,
                env=env,
            )
            run(
                str(python), "-m", "pip", "install", "--no-deps", f"{wheel}[api]", cwd=work, env=env
            )
            scenario = work / f"wheel-{index}"
            exercise(target / "bin/mcda", python, scenario, env, args.browser)
            if args.browser:
                import shutil

                for name in (
                    "installed-gui.png",
                    "browser-analysis.json",
                    "browser-project.json",
                    "installed-recovery.png",
                    "installed-visible-model.png",
                    "installed-visible-model.json",
                ):
                    shutil.copy2(scenario / name, output / f"{index}-{name}")
        # Plain wheel really resolves only base dependencies; no preinstalled API environment.
        target = work / "engine-only"
        venv.EnvBuilder(with_pip=True).create(target)
        python = target / "bin/python"
        run(str(python), "-m", "pip", "install", *pip_args, str(wheels[0]), cwd=work, env=env)
        run(str(target / "bin/mcda"), "--help", cwd=work, env=env)
        result = subprocess.run(
            [str(target / "bin/mcda"), "serve"], cwd=work, env=env, capture_output=True, text=True
        )
        assert result.returncode == 1 and "whl[api]" in result.stderr.replace("\n", "")
        run(
            str(python),
            "-c",
            "import importlib.util; assert importlib.util.find_spec('uvicorn') is None",
            cwd=work,
            env=env,
        )
        # Consumer resolution with the exact documented wheel[api] command, not --no-deps.
        env.update(
            PIPX_HOME=str(work / "pipx"),
            PIPX_BIN_DIR=str(work / "bin"),
            PIPX_MAN_DIR=str(work / "man"),
        )
        command = [
            sys.executable,
            "-m",
            "pipx",
            "install",
            f"{wheels[0]}[api]",
            "--python",
            sys.executable,
        ]
        if pip_args:
            import shlex

            command += ["--pip-args", shlex.join(pip_args)]
        run(*command, cwd=work, env=env)
        pipx_python = work / "pipx/venvs/mcda-studio/bin/python"
        exercise(work / "bin/mcda", pipx_python, work / "pipx-check", env, args.browser)
    (output / "result.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "wheel_routes": [str(p) for p in wheels],
                "wheel_sha256": {
                    str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in wheels
                },
                "environment": {"platform": platform.platform(), "python": sys.version},
                "plain_wheel": "engine only; api-extra diagnostic passed",
                "pipx": "passed",
                "browser": args.browser,
                "outside_checkout": True,
                "checks": "GUI, oracle, export/reopen, ownership, restore, D1 visible model",
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Installed smoke passed; evidence: {output}")


if __name__ == "__main__":
    main()
