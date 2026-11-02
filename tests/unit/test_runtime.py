"""Installation lookup and startup diagnostics without changing decision-model semantics."""

from contextlib import ExitStack
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from mcda_studio import runtime
from mcda_studio.api import create_app
from mcda_studio.cli import app
from mcda_studio.storage.project_store import ProjectStore


def frontend(path: Path, title: str) -> Path:
    path.mkdir(parents=True)
    (path / "index.html").write_text(f"<!doctype html><title>{title}</title>")
    return path


def test_explicit_and_environment_frontends_override_checkout(monkeypatch, tmp_path):
    explicit = frontend(tmp_path / "explicit", "explicit")
    environment = frontend(tmp_path / "environment", "environment")
    monkeypatch.setenv("MCDA_STUDIO_FRONTEND", str(environment))
    with TestClient(create_app(tmp_path / "projects", frontend_dir=explicit)) as client:
        assert "<title>explicit" in client.get("/").text
        assert client.get("/api/health").json()["build"]["frontend_index_sha256"]
    with TestClient(create_app(tmp_path / "projects")) as client:
        assert "<title>environment" in client.get("/").text
    with TestClient(create_app(tmp_path / "projects", frontend_dir=False)) as client:
        assert client.get("/").status_code == 404
        assert client.get("/api/health").status_code == 200


def test_missing_checkout_falls_back_to_bundled_assets(monkeypatch, tmp_path):
    package = tmp_path / "package"
    frontend(package / "_frontend", "bundled")
    examples = package / "_examples"
    examples.mkdir()
    monkeypatch.delenv("MCDA_STUDIO_FRONTEND", raising=False)
    monkeypatch.delenv("MCDA_STUDIO_EXAMPLES", raising=False)
    monkeypatch.setattr(runtime, "source_checkout", lambda: None)
    monkeypatch.setattr(runtime.resources, "files", lambda name: package)
    with TestClient(create_app(tmp_path / "projects")) as client:
        assert "<title>bundled" in client.get("/").text
        assert client.get("/api/examples").json() == []


def test_checkout_assets_precede_bundle_and_explicit_examples_precede_environment(
    monkeypatch, tmp_path
):
    checkout = tmp_path / "checkout"
    frontend(checkout / "frontend/dist", "checkout")
    monkeypatch.setattr(runtime, "source_checkout", lambda: checkout)
    monkeypatch.delenv("MCDA_STUDIO_FRONTEND", raising=False)
    with ExitStack() as stack:
        assert runtime.asset_directory("frontend", None, stack) == checkout / "frontend/dist"
        monkeypatch.setenv("MCDA_STUDIO_EXAMPLES", str(tmp_path / "missing"))
        explicit = tmp_path / "examples"
        explicit.mkdir()
        assert runtime.asset_directory("examples", explicit, stack) == explicit


def test_startup_errors_are_actionable_and_version_needs_no_server(tmp_path):
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0 and "mcda-studio" in result.stdout
    result = runner.invoke(app, ["serve", "--frontend", str(tmp_path / "missing"), "--open"])
    assert result.exit_code == 1
    assert "Configured frontend path is missing" in " ".join(result.stderr.split())
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("keep me")
    result = runner.invoke(app, ["serve", "--store", str(blocking_file)])
    assert result.exit_code == 1
    assert "Cannot write project library" in " ".join(result.stderr.split())
    assert blocking_file.read_text() == "keep me"


def test_configured_missing_assets_do_not_silently_use_checkout(monkeypatch, tmp_path):
    monkeypatch.setenv("MCDA_STUDIO_FRONTEND", str(tmp_path / "absent"))
    with pytest.raises(ValueError, match="Configured frontend path is missing"):
        create_app(tmp_path / "projects")


def test_browser_opens_only_after_server_readiness(monkeypatch, tmp_path):
    import threading
    from types import SimpleNamespace

    import uvicorn

    from mcda_studio import startup

    opened = threading.Event()

    class Socket:
        def setsockopt(self, *option):
            pass

        def bind(self, address):
            pass

        def listen(self, count):
            pass

        def getsockname(self):
            return ("127.0.0.1", 8765)

        def close(self):
            pass

    class Server:
        started = False

        def __init__(self, config):
            pass

        def run(self, sockets):
            assert not opened.is_set()
            self.started = True
            assert opened.wait(2)

    monkeypatch.setattr(startup.socket, "socket", lambda *args: Socket())
    monkeypatch.setattr(uvicorn, "Server", Server)
    monkeypatch.setattr(startup.webbrowser, "open", lambda url: opened.set())
    startup.run_server(
        SimpleNamespace(state=SimpleNamespace(store=ProjectStore(tmp_path))),
        "127.0.0.1",
        8765,
        True,
    )
    assert opened.is_set()


def test_port_reuse_never_shares_a_port_with_a_live_listener(tmp_path):
    import socket
    from types import SimpleNamespace

    from mcda_studio import startup

    with socket.socket() as other:
        other.bind(("127.0.0.1", 0))
        other.listen()
        app_state = SimpleNamespace(state=SimpleNamespace(store=ProjectStore(tmp_path)))
        with pytest.raises(ValueError, match="Choose another --port"):
            startup.run_server(app_state, "127.0.0.1", other.getsockname()[1], False)


def test_occupied_port_never_opens_browser(monkeypatch, tmp_path):
    from mcda_studio import startup

    class OccupiedSocket:
        def setsockopt(self, *option):
            pass

        def bind(self, address):
            raise OSError("Address already in use")

        def close(self):
            pass

    opened = []
    gui = tmp_path / "gui"  # --open needs GUI assets; never rely on a built checkout
    gui.mkdir()
    (gui / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    monkeypatch.setattr(startup.socket, "socket", lambda *args: OccupiedSocket())
    monkeypatch.setattr(startup.webbrowser, "open", opened.append)
    result = CliRunner().invoke(
        app, ["serve", "--store", str(tmp_path / "library"), "--frontend", str(gui), "--open"]
    )
    assert result.exit_code == 1
    assert "Choose another --port" in " ".join(result.stderr.split())
    assert opened == []
