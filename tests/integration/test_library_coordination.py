"""Real POSIX processes and stopped-library recovery; never use a user's library."""

import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager

import pytest

from mcda_studio.storage.library_lock import LibraryOwnership
from mcda_studio.storage.project_store import ProjectStore

from builders import tiny_project


def request(url, body=None):
    with urllib.request.urlopen(
        urllib.request.Request(
            url,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        ),
        timeout=5,
    ) as response:
        return json.load(response)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def running(root, port=None):
    port = port or free_port()
    command = [
        sys.executable,
        "-m",
        "mcda_studio",
        "serve",
        "--store",
        str(root),
        "--port",
        str(port),
        "--no-open",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(200):
            if process.poll() is not None:
                pytest.fail(process.communicate()[0])
            try:
                request(url + "/api/health")
                break
            except OSError:
                time.sleep(0.025)
        else:
            pytest.fail("Server readiness timed out")
        yield process, url, port
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)


def test_a_stopped_server_restarts_on_the_same_port(tmp_path):
    """Connections the server closed leave TIME_WAIT sockets on its port; a prompt restart on that
    port must still bind instead of reporting the port as occupied."""
    root = tmp_path / "library"
    with running(root) as (_, url, port):
        for _ in range(3):
            request(url + "/api/health")  # urllib asks the server to close each connection
    with running(root, port) as (_, again, _):
        assert request(again + "/api/health")["status"] == "ok"


def test_independent_servers_and_cli_writers_respect_lifetime_owner(tmp_path):
    root = tmp_path / "library"
    gui = tmp_path / "gui"  # --open needs GUI assets; never rely on a built checkout
    gui.mkdir()
    (gui / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    with running(root) as (owner, url, port):
        second = subprocess.run(
            [
                sys.executable,
                "-m",
                "mcda_studio",
                "serve",
                "--store",
                str(root),
                "--port",
                str(free_port()),
                "--frontend",
                str(gui),
                "--open",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert second.returncode == 1
        diagnostic = " ".join((second.stdout + second.stderr).split())
        assert str(owner.pid) in diagnostic and str(port) in diagnostic
        assert "do not delete" in diagnostic
        doc = request(url + "/api/projects", {"title": "Owner writes work"})
        source = root / f"{doc['project']['id']}.json"
        before = source.read_bytes()
        blocked = subprocess.run(
            [sys.executable, "-m", "mcda_studio", "alternative", "add", str(source), "Blocked"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert blocked.returncode == 1 and "owned by another process" in " ".join(
            blocked.stderr.split()
        )
        assert source.read_bytes() == before
        unrelated = tmp_path / "unmanaged/project.json"
        result = subprocess.run(
            [sys.executable, "-m", "mcda_studio", "new", "Unrelated", "-o", str(unrelated)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0 and unrelated.exists()
        assert not (unrelated.parent / ".mcda-studio.lock").exists()
        with running(tmp_path / "other") as (_, other, _):
            request(other + "/api/projects", {"title": "Independent library"})
            assert len(request(url + "/api/projects")["projects"]) == 1
            assert len(request(other + "/api/projects")["projects"]) == 1
    # The same cooperating CLI write now succeeds after shutdown.
    result = subprocess.run(
        [sys.executable, "-m", "mcda_studio", "alternative", "add", str(source), "Allowed"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0 and source.read_bytes() != before


@pytest.mark.parametrize("abrupt", [False, True])
def test_normal_shutdown_and_kill_release_os_ownership(tmp_path, abrupt):
    root = tmp_path / "library"
    with running(root) as (owner, _, _):
        (owner.kill if abrupt else owner.terminate)()
        owner.wait(timeout=10)
    # Diagnostic marker survives, but it cannot prevent reacquisition.
    assert (root / ".mcda-studio.lock").exists()
    with running(root) as (_, url, _):
        assert request(url + "/api/health")["status"] == "ok"


@pytest.mark.parametrize("after_publication", [False, True])
def test_interrupted_restore_retains_recoverable_data_and_releases_owner(
    tmp_path, after_publication
):
    store = ProjectStore(tmp_path / "library")
    project = tiny_project()
    store.create(project)
    entry = store.delete(project.id)
    before = entry.read_bytes()
    code = """
import os,stat,sys
from mcda_studio.storage.project_store import ProjectStore
if sys.argv[3] == 'True':
    original = os.fsync
    def interrupt(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode): os._exit(77)
        return original(fd)
    os.fsync = interrupt
else:
    os.link = lambda *a, **k: os._exit(77)
ProjectStore(sys.argv[1]).restore(sys.argv[2])
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(store.root), entry.name, str(after_publication)],
        timeout=10,
    )
    assert result.returncode == 77 and entry.read_bytes() == before
    if after_publication:
        assert store.get(project.id).project == project
    else:
        assert store.restore(entry.name).project == project
    with LibraryOwnership(store.root):
        pass


def test_stopped_library_backup_and_fresh_location_recovery_drill(tmp_path):
    root = tmp_path / "original"
    store = ProjectStore(root)
    active = tiny_project()
    deleted = active.model_copy(update={"id": "deleted", "title": "Recover later"})
    store.create(active)
    store.create(deleted)
    entry = store.delete(deleted.id)
    fingerprints = {p.project.id: p.fingerprint for p in store.list()[0]}
    backup, recovered = tmp_path / "backup", tmp_path / "recovered"
    with LibraryOwnership(root):  # Refuse the drill if a server/writer is still running.
        shutil.copytree(root, backup, symlinks=True)
    shutil.copytree(backup, recovered, symlinks=True)  # Refuses existing target.
    with pytest.raises(FileExistsError):
        shutil.copytree(backup, recovered, symlinks=True)
    assert (recovered / ".trash" / entry.name).read_bytes() == entry.read_bytes()
    with running(recovered) as (_, url, _):
        reopened = request(url + "/api/projects")["projects"]
        assert {p["id"]: p["fingerprint"] for p in reopened} == fingerprints
        restored = request(url + f"/api/trash/{entry.name}/restore", {})
        assert restored["fingerprint"] == deleted.fingerprint()
        assert request(url + f"/api/projects/{deleted.id}")["fingerprint"] == deleted.fingerprint()


def mcda(*args):
    return subprocess.run(
        [sys.executable, "-m", "mcda_studio", *args], capture_output=True, text=True, timeout=60
    )


def test_library_backup_tool_respects_a_running_server_and_round_trips_through_one(tmp_path):
    root = tmp_path / "original"
    store = ProjectStore(root)
    active = tiny_project()
    deleted = active.model_copy(update={"id": "deleted", "title": "Recover later"})
    store.create(active)
    store.create(deleted)
    entry = store.delete(deleted.id)
    archive, recovered = tmp_path / "library.zip", tmp_path / "recovered"
    with running(root) as (process, _, port):
        refused = mcda("library", "backup", "--store", str(root), "--to", str(archive))
        said = " ".join(refused.stderr.split())  # Rich wraps long paths
        assert refused.returncode == 1 and "owned by another process" in said
        assert str(process.pid) in said and str(port) in said
        assert not archive.exists()
    made = mcda("library", "backup", "--store", str(root), "--to", str(archive))
    assert made.returncode == 0, made.stderr
    assert mcda("library", "verify", str(archive)).returncode == 0
    restored = mcda("library", "restore", str(archive), "--to", str(recovered))
    assert restored.returncode == 0, restored.stderr
    with running(recovered) as (_, url, _):
        listed = request(url + "/api/projects")["projects"]
        assert {p["id"]: p["fingerprint"] for p in listed} == {active.id: active.fingerprint()}
        revived = request(url + f"/api/trash/{entry.name}/restore", {})
        assert revived["fingerprint"] == deleted.fingerprint()
