"""Library backup archives: round trips, hostile archives, limits, failures and the server guard.

Every archive here is built in a temporary directory; no user library is touched.
"""

import json
import os
import stat
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from mcda_studio.api import create_app
from mcda_studio.cli import app as cli
from mcda_studio.services import project_service as ps
from mcda_studio.storage import library_backup as lb
from mcda_studio.storage.library_backup import BackupError, IncompleteRestoreError
from mcda_studio.storage.library_lock import LOCK_FILE, LibraryBusyError, LibraryOwnership
from mcda_studio.storage.project_store import ProjectStore

from builders import tiny_project


# ---- helpers ----------------------------------------------------------------------------------
def make_library(tmp_path: Path) -> tuple[ProjectStore, str, str]:
    """Two projects; the second is deleted, so the library has one active and one trash entry."""
    store = ProjectStore(tmp_path / "library")
    kept = tiny_project()
    store.create(kept)
    gone = ps.duplicate_project(kept, "Gone")
    store.create(gone)
    entry = store.delete(gone.id)
    os.utime(store.root / f"{kept.id}.json", ns=(1_700_000_000_123_456_789,) * 2)
    return store, kept.id, entry.name


def files(root: Path) -> dict[str, tuple[bytes, int]]:
    """Every regular file under root (bytes, mtime_ns), except the ownership marker."""
    found = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink() and path.name != LOCK_FILE:
            found[str(path.relative_to(root))] = (path.read_bytes(), path.stat().st_mtime_ns)
    return found


def backup(tmp_path: Path, name: str = "backup.zip") -> tuple[ProjectStore, Path]:
    store, _, _ = make_library(tmp_path)
    archive = tmp_path / name
    lb.create_backup(store.root, archive)
    return store, archive


def members(archive: Path) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(archive) as zf:
        return [(i.filename, zf.read(i)) for i in zf.infolist()]


def write_zip(path: Path, items: list[tuple[str | zipfile.ZipInfo, bytes]]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in items:
            zf.writestr(name, data)
    return path


def rewrite(archive: Path, out: Path, *, manifest=None, data=None, extra=()) -> Path:
    """Copy an archive, optionally editing the manifest dict or one member's bytes."""
    items: list[tuple[str | zipfile.ZipInfo, bytes]] = []
    for name, content in members(archive):
        if name == lb.MANIFEST and manifest:
            raw = json.loads(content)
            manifest(raw)
            content = json.dumps(raw).encode()
        if data and name in data:
            content = data[name](content)
        items.append((name, content))
    return write_zip(out, items + list(extra))


def first_active(archive: Path) -> str:
    return next(n for n, _ in members(archive) if n.startswith("projects/"))


# ---- round trip -------------------------------------------------------------------------------
def test_round_trip_preserves_bytes_fingerprints_times_and_recently_deleted(tmp_path):
    store, kept_id, entry = make_library(tmp_path)
    before = files(store.root)
    archive = tmp_path / "backup.zip"
    report = lb.create_backup(store.root, archive)
    assert (report.active, report.deleted, report.warnings) == (1, 1, False)
    target = tmp_path / "restored"
    restored = lb.restore_backup(archive, target)
    assert (restored.active, restored.deleted) == (1, 1)
    assert files(target) == before  # bytes and modification times, .trash included
    assert not (target / lb.INCOMPLETE_MARKER).exists()
    again = ProjectStore(target)
    assert again.get(kept_id).fingerprint == store.get(kept_id).fingerprint
    # Recently deleted works in the restored library and gives back the original revision.
    original = ProjectStore(store.root).list_trash()[0]
    assert again.list_trash()[0].entry == entry == original.entry
    revived = again.restore(entry)
    assert revived.fingerprint == store.restore(entry).fingerprint


def test_lock_marker_is_never_archived_and_a_clean_library_has_no_warnings(tmp_path):
    store, archive = backup(tmp_path)
    assert (store.root / LOCK_FILE).exists()
    names = [n for n, _ in members(archive)]
    assert names[0] == lb.MANIFEST and LOCK_FILE not in "".join(names)
    manifest = json.loads(dict(members(archive))[lb.MANIFEST])
    assert manifest["format"] == lb.FORMAT and manifest["skipped"] == []
    assert all(e["readable"] and len(e["fingerprint"]) == 64 for e in manifest["entries"])


def test_backup_skips_and_reports_files_it_must_not_follow_or_adopt(tmp_path):
    store, _, _ = make_library(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text('{"secret": true}')
    (store.root / "link.json").symlink_to(outside)
    (store.root / ".restore-abc.tmp").write_text("stage")
    (store.root / ".hidden.json").write_text("{}")
    (store.root / "notes.txt").write_text("x")
    (store.root / "sub").mkdir()
    (store.root / "bad name.json").write_text("{}")
    (store.root / lb.TRASH_DIR / "stray.json").write_text("{}")
    archive = tmp_path / "backup.zip"
    report = lb.create_backup(store.root, archive)
    skipped = dict(report.skipped)
    assert skipped["link.json"] == "symlink, not followed"
    assert skipped[".restore-abc.tmp"].startswith("temporary stage file")
    assert skipped[".hidden.json"] == "hidden file"
    assert skipped["sub"] == "subdirectory"
    assert skipped["notes.txt"] == skipped["bad name.json"] == "name is not a project file name"
    assert skipped[".trash/stray.json"] == "name is not a project file name"
    assert report.warnings
    assert b"secret" not in b"".join(d for _, d in members(archive))


def test_unreadable_and_newer_schema_files_are_kept_byte_for_byte_and_reported(tmp_path):
    store, _, _ = make_library(tmp_path)
    (store.root / "broken.json").write_bytes(b"{not json")
    newer = json.loads((store.root / f"{store.list()[0][0].project.id}.json").read_text())
    newer.update(id="future", schema_version=99)
    (store.root / "future.json").write_text(json.dumps(newer))
    archive = tmp_path / "backup.zip"
    report = lb.create_backup(store.root, archive)
    unchecked = dict(report.unchecked)
    assert "unreadable when backed up" in unchecked["projects/broken.json"]
    assert "newer than this program" in unchecked["projects/future.json"]
    manifest = json.loads(dict(members(archive))[lb.MANIFEST])
    future = next(e for e in manifest["entries"] if e["path"] == "projects/future.json")
    assert future["schema_version"] == 99 and future["readable"] is False
    target = tmp_path / "restored"
    lb.restore_backup(archive, target)
    assert (target / "broken.json").read_bytes() == b"{not json"
    assert (target / "future.json").read_bytes() == (store.root / "future.json").read_bytes()


def test_a_readable_newer_schema_entry_is_verified_by_bytes_only(tmp_path):
    _, archive = backup(tmp_path)
    name = first_active(archive)

    def newer(raw):
        next(e for e in raw["entries"] if e["path"] == name)["schema_version"] = 99

    report = lb.verify_backup(rewrite(archive, tmp_path / "newer.zip", manifest=newer))
    assert dict(report.unchecked)[name] == "newer schema 99, not checked"


def test_backup_leaves_the_library_unchanged(tmp_path):
    store, _, _ = make_library(tmp_path)
    before = files(store.root)
    names = sorted(os.listdir(store.root))
    lb.create_backup(store.root, tmp_path / "backup.zip")
    assert files(store.root) == before and sorted(os.listdir(store.root)) == names


def test_backup_refuses_existing_target_target_inside_library_and_missing_library(tmp_path):
    store, archive = backup(tmp_path)
    content = archive.read_bytes()
    with pytest.raises(BackupError, match="already exists"):
        lb.create_backup(store.root, archive)
    assert archive.read_bytes() == content
    with pytest.raises(BackupError, match="outside the library"):
        lb.create_backup(store.root, store.root / "inside.zip")
    with pytest.raises(BackupError, match="not a directory"):
        lb.create_backup(tmp_path / "missing", tmp_path / "other.zip")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["backup.zip", "library"]


def test_backup_refuses_an_owned_library_and_publishes_nothing(tmp_path):
    store, _, _ = make_library(tmp_path)
    with LibraryOwnership(store.root), pytest.raises(LibraryBusyError):
        lb.create_backup(store.root, tmp_path / "backup.zip")
    assert not (tmp_path / "backup.zip").exists()


def test_verify_writes_nothing(tmp_path):
    _, archive = backup(tmp_path)
    before = sorted(os.listdir(tmp_path)), archive.read_bytes()
    lb.verify_backup(archive)
    assert (sorted(os.listdir(tmp_path)), archive.read_bytes()) == before


# ---- hostile and damaged archives -------------------------------------------------------------
@pytest.mark.parametrize(
    "name",
    [
        "../escape.json",
        "/absolute.json",
        "projects/../escape.json",
        "projects\\a.json",
        "projects/ä.json",
        "projects/",
        "projects/a.json/",
        "trash/a.json",
        "other/a.json",
        "projects/.hidden.json",
        "projects/a\x00.json",
    ],
)
def test_member_names_outside_the_allowlist_are_refused(tmp_path, name):
    _, archive = backup(tmp_path)
    bad = rewrite(archive, tmp_path / "bad.zip", extra=[(name, b"{}")])
    with pytest.raises(BackupError, match="not an allowed member name"):
        lb.verify_backup(bad)


@pytest.mark.filterwarnings("ignore:Duplicate name")
def test_duplicate_member_names_are_refused_including_case_only_collisions(tmp_path):
    _, archive = backup(tmp_path)
    name = first_active(archive)
    content = dict(members(archive))[name]
    case_twin = "projects/" + name.removeprefix("projects/").removesuffix(".json").upper() + ".json"
    assert case_twin != name
    for i, twin in enumerate((name, case_twin)):
        bad = rewrite(archive, tmp_path / f"dup{i}.zip", extra=[(twin, content)])
        with pytest.raises(BackupError, match="duplicate member name"):
            lb.verify_backup(bad)


def mark_encrypted(path: Path, name: str) -> None:
    """zipfile never writes the encryption flag, so set it in the central directory record."""
    raw = bytearray(path.read_bytes())
    target, pos = name.encode(), raw.find(b"PK\x01\x02")
    while raw[pos + 46 : pos + 46 + len(target)] != target:
        pos = raw.find(b"PK\x01\x02", pos + 4)
    raw[pos + 8] |= 0x1
    path.write_bytes(bytes(raw))


def test_symlink_encrypted_and_unknown_compression_members_are_refused(tmp_path):
    _, archive = backup(tmp_path)
    link = zipfile.ZipInfo("projects/link.json")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    bzip = zipfile.ZipInfo("projects/bz.json")
    bzip.compress_type = zipfile.ZIP_BZIP2
    for info, message in ((link, "not a regular file"), (bzip, "unsupported compression")):
        bad = rewrite(archive, tmp_path / "bad.zip", extra=[(info, b"{}")])
        with pytest.raises(BackupError, match=message):
            lb.verify_backup(bad)
    encrypted = rewrite(archive, tmp_path / "enc.zip", extra=[("projects/enc.json", b"{}")])
    mark_encrypted(encrypted, "projects/enc.json")
    with pytest.raises(BackupError, match="encrypted members are not supported"):
        lb.verify_backup(encrypted)


def test_a_local_header_name_that_differs_from_the_directory_is_refused(tmp_path):
    _, archive = backup(tmp_path)
    name = first_active(archive).encode()
    swapped = name.replace(b"projects/", b"projectz/")
    raw = archive.read_bytes()
    (tmp_path / "bad.zip").write_bytes(raw.replace(name, swapped, 1))  # local header comes first
    with pytest.raises(BackupError, match="cannot be read"):
        lb.verify_backup(tmp_path / "bad.zip")


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda m: m.update(format="something-else"), "not an MCDA Studio"),
        (lambda m: m.update(format_version=2), "newer than this program"),
        (lambda m: m.update(entries="none"), "no entries list"),
        (lambda m: m["entries"].append(dict(m["entries"][0])), "listed twice"),
        (lambda m: m["entries"].pop(), "in the archive but not in the manifest"),
        (lambda m: m["entries"][0].update(fingerprint=None), "needs project_id"),
        (lambda m: m["entries"][0].update(kind="other"), "invalid path or kind"),
        (lambda m: m["entries"][0].update(fingerprint="0" * 64), "fingerprint differs"),
    ],
)
def test_manifests_that_do_not_describe_the_archive_are_refused(tmp_path, edit, message):
    _, archive = backup(tmp_path)
    with pytest.raises(BackupError, match=message):
        lb.verify_backup(rewrite(archive, tmp_path / "bad.zip", manifest=edit))


def test_missing_or_invalid_manifest_and_missing_member_are_refused(tmp_path):
    _, archive = backup(tmp_path)
    items = members(archive)
    no_manifest = write_zip(tmp_path / "a.zip", [i for i in items if i[0] != lb.MANIFEST])
    with pytest.raises(BackupError, match="manifest.json is missing"):
        lb.verify_backup(no_manifest)
    bad_json = write_zip(tmp_path / "b.zip", [(lb.MANIFEST, b"{nope"), *items[1:]])
    with pytest.raises(BackupError, match="not valid JSON"):
        lb.verify_backup(bad_json)
    missing = write_zip(tmp_path / "c.zip", items[:-1])
    with pytest.raises(BackupError, match="in the manifest but not in the archive"):
        lb.verify_backup(missing)
    (tmp_path / "d.zip").write_bytes(b"not a zip")
    with pytest.raises(BackupError, match="not a readable backup archive"):
        lb.verify_backup(tmp_path / "d.zip")


def test_a_changed_byte_is_detected_even_when_the_fingerprint_is_unchanged(tmp_path):
    _, archive = backup(tmp_path)
    name = first_active(archive)

    def reindent(content: bytes) -> bytes:  # same length, same JSON, different bytes
        changed = content.replace(b"\n  ", b"\n\t ", 1)
        assert len(changed) == len(content) and changed != content
        return changed

    bad = rewrite(archive, tmp_path / "bad.zip", data={name: reindent})
    with pytest.raises(BackupError, match="content differs from the manifest"):
        lb.verify_backup(bad)


# ---- limits (enforced on actual bytes) --------------------------------------------------------
def test_member_size_limit(tmp_path, monkeypatch):
    _, archive = backup(tmp_path)
    monkeypatch.setattr(lb, "MAX_FILE_BYTES", 100)
    with pytest.raises(BackupError, match="member limit"):
        lb.verify_backup(archive)


def test_total_size_limit(tmp_path, monkeypatch):
    _, archive = backup(tmp_path)
    monkeypatch.setattr(lb, "MAX_TOTAL_BYTES", 2_000)
    with pytest.raises(BackupError, match="total limit"):
        lb.verify_backup(archive)


def test_member_count_limit(tmp_path, monkeypatch):
    _, archive = backup(tmp_path)
    monkeypatch.setattr(lb, "MAX_MEMBERS", 2)
    with pytest.raises(BackupError, match="the limit is 2"):
        lb.verify_backup(archive)


def test_compression_ratio_limit(tmp_path, monkeypatch):
    _, archive = backup(tmp_path)  # JSON deflates by more than 2:1
    monkeypatch.setattr(lb, "RATIO_FLOOR", 100)
    monkeypatch.setattr(lb, "MAX_RATIO", 2)
    with pytest.raises(BackupError, match="compression ratio above 2:1"):
        lb.verify_backup(archive)


def test_backup_refuses_a_file_over_the_limit_instead_of_writing_an_unrestorable_archive(
    tmp_path, monkeypatch
):
    store, _, _ = make_library(tmp_path)
    monkeypatch.setattr(lb, "MAX_FILE_BYTES", 100)
    with pytest.raises(BackupError, match="limit per file"):
        lb.create_backup(store.root, tmp_path / "backup.zip")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["library"]


# ---- restore ----------------------------------------------------------------------------------
def test_restore_refuses_any_existing_target(tmp_path):
    _, archive = backup(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(BackupError, match="already exists"):
        lb.restore_backup(archive, empty)
    assert list(empty.iterdir()) == []
    link = tmp_path / "link"
    link.symlink_to(empty)
    with pytest.raises(BackupError, match="already exists"):
        lb.restore_backup(archive, link)
    with pytest.raises(BackupError, match="does not exist"):
        lb.restore_backup(archive, tmp_path / "missing" / "target")


def test_restore_writes_nothing_when_the_archive_fails_verification(tmp_path):
    _, archive = backup(tmp_path)
    bad = rewrite(archive, tmp_path / "bad.zip", extra=[("../escape.json", b"{}")])
    with pytest.raises(BackupError):
        lb.restore_backup(bad, tmp_path / "restored")
    assert not (tmp_path / "restored").exists() and not (tmp_path / "escape.json").exists()


def test_new_files_are_created_exclusively(tmp_path):
    (tmp_path / "x.json").write_text("existing")
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(FileExistsError):
            lb._write_new("x.json", b"new", 0, fd)
    finally:
        os.close(fd)
    assert (tmp_path / "x.json").read_text() == "existing"


def test_a_failed_restore_removes_exactly_what_it_created(tmp_path, monkeypatch):
    _, archive = backup(tmp_path)
    content = archive.read_bytes()
    real, calls = lb._write_new, []

    def failing(name, data, modified_ns, dir_fd):
        calls.append(name)
        if len(calls) == 3:
            raise OSError("disk full (injected)")
        real(name, data, modified_ns, dir_fd)

    monkeypatch.setattr(lb, "_write_new", failing)
    with pytest.raises(OSError, match="injected"):
        lb.restore_backup(archive, tmp_path / "restored")
    assert not (tmp_path / "restored").exists() and archive.read_bytes() == content


def test_the_incomplete_marker_is_present_until_the_restore_has_been_rechecked(
    tmp_path, monkeypatch
):
    _, archive = backup(tmp_path)
    target = tmp_path / "restored"
    seen = []
    real = lb._recheck

    def spy(destination, entries):
        seen.append((destination / lb.INCOMPLETE_MARKER).exists())
        real(destination, entries)

    monkeypatch.setattr(lb, "_recheck", spy)
    lb.restore_backup(archive, target)
    assert seen == [True] and not (target / lb.INCOMPLETE_MARKER).exists()


# ---- the server refuses an unfinished restore -------------------------------------------------
def unfinished(tmp_path: Path) -> Path:
    root = tmp_path / "half"
    root.mkdir()
    (root / lb.INCOMPLETE_MARKER).write_text("restore in progress\n")
    return root


def test_ensure_restore_complete(tmp_path):
    lb.ensure_restore_complete(tmp_path)
    with pytest.raises(IncompleteRestoreError, match="unfinished restore"):
        lb.ensure_restore_complete(unfinished(tmp_path))


def test_app_startup_refuses_an_unfinished_restore(tmp_path):
    with (
        pytest.raises(IncompleteRestoreError),
        TestClient(create_app(unfinished(tmp_path), frontend_dir=False)),
    ):
        pass


def test_serve_refuses_an_unfinished_restore_before_listening(tmp_path, monkeypatch):
    import uvicorn

    monkeypatch.setattr(uvicorn.Server, "run", lambda self, sockets=None: None)
    result = CliRunner().invoke(
        cli, ["serve", "--store", str(unfinished(tmp_path)), "--port", "0", "--no-open"]
    )
    assert result.exit_code == 1 and "unfinished restore" in " ".join(result.output.split())


# ---- command line -----------------------------------------------------------------------------
# Rich wraps long messages at the terminal width, so phrases are matched on collapsed whitespace.
def test_cli_exit_status_is_0_clean_3_with_warnings_and_1_on_failure(tmp_path):
    store, _, _ = make_library(tmp_path)
    run = CliRunner().invoke
    archive = tmp_path / "clean.zip"
    clean = run(cli, ["library", "backup", "--store", str(store.root), "--to", str(archive)])
    assert clean.exit_code == 0, clean.output
    verified = run(cli, ["library", "verify", str(archive), "--json"])
    assert verified.exit_code == 0 and json.loads(verified.output)["active"] == 1
    restored = run(cli, ["library", "restore", str(archive), "--to", str(tmp_path / "r")])
    assert restored.exit_code == 0 and "mcda serve --store" in " ".join(restored.output.split())
    (store.root / ".restore-x.tmp").write_text("stage")
    warned = run(
        cli, ["library", "backup", "--store", str(store.root), "--to", str(tmp_path / "w.zip")]
    )
    assert warned.exit_code == 3 and "skipped" in " ".join(warned.output.split())
    again = run(cli, ["library", "restore", str(archive), "--to", str(tmp_path / "r")])
    assert again.exit_code == 1 and "already exists" in " ".join(again.output.split())
    (tmp_path / "junk.zip").write_bytes(b"junk")
    assert run(cli, ["library", "verify", str(tmp_path / "junk.zip")]).exit_code == 1
