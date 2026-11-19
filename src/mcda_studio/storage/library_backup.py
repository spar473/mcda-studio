"""Whole-library backup archives: create, verify and restore without overwriting anything.

The rules each guard enforces are in ``docs/design/library-backup-and-restore.md``. In short:

* **Backup** owns the library while it reads, reads each file once, and archives exactly those
  bytes with a manifest of sizes, hashes, fingerprints and modification times. It publishes the
  archive with a no-overwrite hard link after verifying it.
* **Verify** trusts nothing in the archive for safety: member names must match a fixed allowlist,
  sizes are limited while reading, and every byte is checked against the manifest.
* **Restore** verifies first, claims a new directory with ``mkdir``, writes each member with
  ``O_EXCL | O_NOFOLLOW`` under that library's ownership, and re-checks the result. A marker file
  flags the library as incomplete until the end; the server refuses such a library.
"""

import hashlib
import json
import os
import re
import stat
import tempfile
import time
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcda_studio.domain.errors import McdaError
from mcda_studio.domain.project import SCHEMA_VERSION, Project
from mcda_studio.runtime import package_version
from mcda_studio.storage.json_repository import JsonProjectRepository
from mcda_studio.storage.library_lock import LOCK_FILE, LibraryOwnership
from mcda_studio.storage.project_store import TRASH_DIR, ProjectStore

FORMAT = "mcda-studio-library-backup"
FORMAT_VERSION = 1
MANIFEST = "manifest.json"
INCOMPLETE_MARKER = ".mcda-restore-incomplete"

# Limits are constants by design; changing one is a code change with its own test.
MAX_MEMBERS = 100_000
MAX_FILE_BYTES = 64 * 2**20
MAX_MANIFEST_BYTES = 32 * 2**20
MAX_TOTAL_BYTES = 4 * 2**30
MAX_RATIO = 200
RATIO_FLOOR = 2**20

_ID = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}"
_STAMP = r"[0-9]{8}T[0-9]{12}Z"
_ACTIVE_FILE = re.compile(rf"(?P<id>{_ID})\.json", re.ASCII)
_TRASH_FILE = re.compile(rf"(?P<id>{_ID})\.{_STAMP}\.json", re.ASCII)
_ACTIVE_MEMBER = re.compile(rf"projects/(?P<name>{_ID}\.json)", re.ASCII)
_TRASH_MEMBER = re.compile(rf"trash/(?P<name>{_ID}\.{_STAMP}\.json)", re.ASCII)
_HEX64 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)  # fixed, so equal libraries give equal archives

_repo = JsonProjectRepository()


class BackupError(McdaError):
    """A backup, verification or restore was refused or failed; nothing was published."""


class IncompleteRestoreError(McdaError):
    """The library is a restore that did not finish."""


@dataclass
class BackupReport:
    active: int = 0
    deleted: int = 0
    skipped: list[tuple[str, str]] = field(default_factory=list)
    unchecked: list[tuple[str, str]] = field(default_factory=list)

    @property
    def warnings(self) -> bool:
        return bool(self.skipped or self.unchecked)

    def to_json(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "deleted": self.deleted,
            "skipped": [{"name": n, "reason": r} for n, r in self.skipped],
            "unchecked": [{"path": p, "reason": r} for p, r in self.unchecked],
        }


def ensure_restore_complete(root: str | Path) -> None:
    """Refuse a library that a restore created but never finished."""
    if os.path.lexists(Path(root).expanduser() / INCOMPLETE_MARKER):
        raise IncompleteRestoreError(
            f"{root} is an unfinished restore ({INCOMPLETE_MARKER} is present). Delete that "
            "directory and restore the backup again."
        )


# ---- shared helpers ---------------------------------------------------------------------------
def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _describe(path: str, data: bytes, modified_ns: int) -> dict[str, Any]:
    """Manifest entry for one archived file; an unreadable file is kept, with its error."""
    kind = "active" if path.startswith("projects/") else "trash"
    name = path.split("/", 1)[1]
    entry: dict[str, Any] = {
        "path": path,
        "kind": kind,
        "size": len(data),
        "sha256": _sha256(data),
        "modified_ns": modified_ns,
        "readable": False,
        "project_id": None,
        "schema_version": None,
        "fingerprint": None,
        "error": None,
    }
    try:
        raw = json.loads(data.decode("utf-8"))
        if isinstance(raw, dict) and type(raw.get("schema_version")) is int:
            entry["schema_version"] = raw["schema_version"]
        project = _load(kind, name, raw)
    except (McdaError, ValueError) as exc:
        entry["error"] = str(exc).splitlines()[0]
        return entry
    entry.update(readable=True, project_id=project.id, fingerprint=project.fingerprint())
    return entry


def _load(kind: str, name: str, raw: Any) -> Project:
    """Load as the library itself would: the ID must agree with the file name."""
    project = _repo.from_dict(raw)
    pattern = _ACTIVE_FILE if kind == "active" else _TRASH_FILE
    match = pattern.fullmatch(name)
    if match is None or match["id"] != project.id:
        raise BackupError(f"{name} contains project id {project.id!r}; the name must agree")
    if kind == "trash":
        project.tree()  # Recently deleted refuses corrupt structures; so does a backup check.
    return project


def _read_regular(name: str, dir_fd: int) -> tuple[bytes, int]:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise BackupError(f"{name} is not a regular file")
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise BackupError(f"{name} is larger than the {MAX_FILE_BYTES}-byte limit per file")
    return data, info.st_mtime_ns


def _scan(dir_fd: int) -> list[os.DirEntry[str]]:
    with os.scandir(dir_fd) as entries:
        return sorted(entries, key=lambda e: e.name)


def _skip_reason(entry: os.DirEntry[str], pattern: re.Pattern[str]) -> str | None:
    if entry.is_symlink():
        return "symlink, not followed"
    if entry.name.startswith(".") and entry.name.endswith(".tmp"):
        return "temporary stage file from an interrupted save or restore"
    if entry.name.startswith("."):
        return "hidden file"
    if entry.is_dir(follow_symlinks=False):
        return "subdirectory"
    if not entry.is_file(follow_symlinks=False):
        return "not a regular file"
    if pattern.fullmatch(entry.name) is None:
        return "name is not a project file name"
    return None


def _collect(root: Path, report: BackupReport) -> list[tuple[str, bytes, int]]:
    """Read every included file once; the same bytes are hashed and archived."""
    members: list[tuple[str, bytes, int]] = []
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for entry in _scan(root_fd):
            if entry.name == LOCK_FILE:
                continue  # the ownership marker is expected and never archived
            if entry.name == TRASH_DIR and not entry.is_symlink() and entry.is_dir():
                trash_fd = os.open(
                    TRASH_DIR, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
                )
                try:
                    for item in _scan(trash_fd):
                        reason = _skip_reason(item, _TRASH_FILE)
                        if reason:
                            report.skipped.append((f"{TRASH_DIR}/{item.name}", reason))
                            continue
                        data, mtime = _read_regular(item.name, trash_fd)
                        members.append((f"trash/{item.name}", data, mtime))
                finally:
                    os.close(trash_fd)
                continue
            reason = _skip_reason(entry, _ACTIVE_FILE)
            if reason:
                report.skipped.append((entry.name, reason))
                continue
            data, mtime = _read_regular(entry.name, root_fd)
            members.append((f"projects/{entry.name}", data, mtime))
    finally:
        os.close(root_fd)
    if len(members) + 1 > MAX_MEMBERS:
        raise BackupError(f"the library has more than {MAX_MEMBERS - 1} files to back up")
    if sum(len(data) for _, data, _ in members) > MAX_TOTAL_BYTES:
        raise BackupError(f"the library is larger than the {MAX_TOTAL_BYTES}-byte backup limit")
    return members


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


# ---- backup -----------------------------------------------------------------------------------
def create_backup(store: str | Path, archive: str | Path) -> BackupReport:
    """Archive a stopped library to a new file; refuses an owned library or an existing file."""
    root = Path(store).expanduser().resolve()
    if not root.is_dir():
        raise BackupError(f"library {root} is not a directory")
    requested = Path(archive).expanduser().absolute()
    parent = requested.parent.resolve()
    if not parent.is_dir():
        raise BackupError(f"directory {parent} for the backup does not exist")
    target = parent / requested.name
    if os.path.lexists(target):
        raise BackupError(f"{target} already exists; choose a new backup file name")
    if _inside(target, root):
        raise BackupError("write the backup outside the library it backs up")
    report = BackupReport()
    with LibraryOwnership(root):
        members = _collect(root, report)
        entries = [_describe(path, data, mtime) for path, data, mtime in members]
        manifest = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "app_version": package_version(),
            "app_schema_version": SCHEMA_VERSION,
            "entries": entries,
            "skipped": [{"name": n, "reason": r} for n, r in report.skipped],
        }
        text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        if len(text.encode("utf-8")) > MAX_MANIFEST_BYTES:
            raise BackupError(f"the manifest would exceed the {MAX_MANIFEST_BYTES}-byte limit")
        fd, tmp = tempfile.mkstemp(dir=parent, prefix=f".{target.name}.", suffix=".partial")
        staged = Path(tmp)
        try:
            with os.fdopen(fd, "wb") as stream:
                with zipfile.ZipFile(stream, "w") as zf:
                    zf.writestr(_zip_info(MANIFEST), text.encode("utf-8"))
                    for path, data, _ in members:
                        zf.writestr(_zip_info(path), data)
                stream.flush()
                os.fsync(stream.fileno())
            checked = verify_backup(staged)
            try:
                os.link(staged, target, follow_symlinks=False)
            except FileExistsError:
                raise BackupError(
                    f"{target} appeared during the backup; nothing was replaced"
                ) from None
            except OSError as exc:
                raise BackupError(
                    f"cannot publish {target} without overwriting ({exc}); nothing was published"
                ) from exc
            _fsync_dir(parent)
        finally:
            with suppress(OSError):
                staged.unlink()
    checked.skipped = report.skipped
    return checked


# ---- verify -----------------------------------------------------------------------------------
@contextmanager
def _open_archive(archive: str | Path) -> Iterator[zipfile.ZipFile]:
    path = Path(archive).expanduser()
    try:
        stream = path.open("rb")
    except OSError as exc:
        raise BackupError(f"cannot open {path}: {exc}") from exc
    try:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise BackupError(f"{path} is not a regular file")
        try:
            with zipfile.ZipFile(stream) as zf:
                yield zf
        except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
            raise BackupError(f"{path} is not a readable backup archive: {exc}") from exc
    finally:
        stream.close()


def _member_kind(name: str) -> str | None:
    if name == MANIFEST:
        return "manifest"
    if _ACTIVE_MEMBER.fullmatch(name):
        return "active"
    if _TRASH_MEMBER.fullmatch(name):
        return "trash"
    return None


def _check_members(zf: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    """Structural checks on the archive itself, before any content is trusted."""
    infos = zf.infolist()
    if len(infos) > MAX_MEMBERS:
        raise BackupError(f"archive has {len(infos)} members; the limit is {MAX_MEMBERS}")
    problems: list[str] = []
    members: dict[str, zipfile.ZipInfo] = {}
    seen: set[str] = set()
    for info in infos:
        name = info.filename
        if _member_kind(name) is None:
            problems.append(f"{name!r}: not an allowed member name")
            continue
        folded = name.casefold()
        if folded in seen:
            problems.append(f"{name!r}: duplicate member name")
            continue
        seen.add(folded)
        # Many writers store permission bits only; refuse a member that declares any other type.
        file_type = stat.S_IFMT(info.external_attr >> 16)
        if file_type and file_type != stat.S_IFREG:
            problems.append(f"{name!r}: not a regular file (symlink or special member)")
        if info.flag_bits & 0x1:
            problems.append(f"{name!r}: encrypted members are not supported")
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            problems.append(f"{name!r}: unsupported compression method {info.compress_type}")
        members[name] = info
    if MANIFEST not in members and not problems:
        problems.append(f"{MANIFEST} is missing")
    if problems:
        raise BackupError("archive refused:\n" + "\n".join(problems))
    return members


class _Budget:
    def __init__(self) -> None:
        self.used = 0

    def read(self, zf: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> bytes:
        """Read one member, enforcing limits on actual bytes, never on declared sizes."""
        try:
            with zf.open(info) as stream:
                data = stream.read(limit + 1)
        except (zipfile.BadZipFile, OSError, EOFError, RuntimeError, ValueError) as exc:
            raise BackupError(f"{info.filename!r}: cannot be read: {exc}") from exc
        if len(data) > limit:
            raise BackupError(f"{info.filename!r}: larger than the {limit}-byte member limit")
        if len(data) > RATIO_FLOOR and len(data) > MAX_RATIO * max(info.compress_size, 1):
            raise BackupError(f"{info.filename!r}: compression ratio above {MAX_RATIO}:1")
        self.used += len(data)
        if self.used > MAX_TOTAL_BYTES:
            raise BackupError(f"archive expands beyond the {MAX_TOTAL_BYTES}-byte total limit")
        return data


def _check_manifest(raw: Any, members: dict[str, zipfile.ZipInfo]) -> list[dict[str, Any]]:
    if not isinstance(raw, dict) or raw.get("format") != FORMAT:
        raise BackupError(f"{MANIFEST} is not an MCDA Studio library backup manifest")
    version = raw.get("format_version")
    if type(version) is not int or version < 1:
        raise BackupError(f"{MANIFEST} has no valid format_version")
    if version > FORMAT_VERSION:
        raise BackupError(
            f"backup format {version} is newer than this program supports ({FORMAT_VERSION}); "
            "upgrade MCDA Studio"
        )
    entries = raw.get("entries")
    if not isinstance(entries, list):
        raise BackupError(f"{MANIFEST} has no entries list")
    problems: list[str] = []
    paths: set[str] = set()
    for i, entry in enumerate(entries):
        where = f"entries[{i}]"
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            problems.append(f"{where}: not an entry object with a path")
            continue
        path = entry["path"]
        kind = _member_kind(path)
        if kind in (None, "manifest") or entry.get("kind") != kind:
            problems.append(f"{where}: {path!r} has an invalid path or kind")
            continue
        if path in paths:
            problems.append(f"{where}: {path!r} is listed twice")
            continue
        paths.add(path)
        ints = ("size", "modified_ns")
        if any(type(entry.get(k)) is not int or entry[k] < 0 for k in ints):
            problems.append(f"{where}: size and modified_ns must be non-negative integers")
        if not isinstance(entry.get("sha256"), str) or not _HEX64.fullmatch(entry["sha256"]):
            problems.append(f"{where}: sha256 must be 64 lowercase hex digits")
        if type(entry.get("readable")) is not bool:
            problems.append(f"{where}: readable must be true or false")
        elif entry["readable"] and (
            not isinstance(entry.get("project_id"), str)
            or type(entry.get("schema_version")) is not int
            or not isinstance(entry.get("fingerprint"), str)
            or not _HEX64.fullmatch(entry["fingerprint"])
        ):
            problems.append(f"{where}: a readable entry needs project_id, schema and fingerprint")
    archived = set(members) - {MANIFEST}
    problems += [f"{p!r}: in the archive but not in the manifest" for p in sorted(archived - paths)]
    problems += [f"{p!r}: in the manifest but not in the archive" for p in sorted(paths - archived)]
    if problems:
        raise BackupError("manifest does not match the archive:\n" + "\n".join(problems))
    return entries


def _check_content(entry: dict[str, Any], data: bytes, report: BackupReport) -> str | None:
    """Return a problem, or None. Records entries that are kept but cannot be fully checked."""
    path = entry["path"]
    if len(data) != entry["size"] or _sha256(data) != entry["sha256"]:
        return f"{path!r}: content differs from the manifest (size or sha256)"
    if not entry["readable"]:
        report.unchecked.append((path, f"unreadable when backed up: {entry.get('error')}"))
        return None
    if entry["schema_version"] > SCHEMA_VERSION:
        report.unchecked.append((path, f"newer schema {entry['schema_version']}, not checked"))
        return None
    try:
        project = _load(entry["kind"], path.split("/", 1)[1], json.loads(data.decode("utf-8")))
    except (McdaError, ValueError) as exc:
        return f"{path!r}: no longer loads: {str(exc).splitlines()[0]}"
    if project.id != entry["project_id"] or project.fingerprint() != entry["fingerprint"]:
        return f"{path!r}: project id or fingerprint differs from the manifest"
    return None


def _verified(zf: zipfile.ZipFile) -> tuple[list[dict[str, Any]], dict[str, zipfile.ZipInfo]]:
    members = _check_members(zf)
    text = _Budget().read(zf, members[MANIFEST], MAX_MANIFEST_BYTES)
    try:
        raw = json.loads(text.decode("utf-8"))
    except ValueError as exc:
        raise BackupError(f"{MANIFEST} is not valid JSON: {exc}") from exc
    return _check_manifest(raw, members), members


def verify_backup(archive: str | Path) -> BackupReport:
    """Check an archive completely; writes nothing."""
    report = BackupReport()
    with _open_archive(archive) as zf:
        entries, members = _verified(zf)
        budget = _Budget()
        problems: list[str] = []
        for entry in entries:
            data = budget.read(zf, members[entry["path"]], MAX_FILE_BYTES)
            problem = _check_content(entry, data, report)
            if problem:
                problems.append(problem)
            elif entry["kind"] == "active":
                report.active += 1
            else:
                report.deleted += 1
    if problems:
        raise BackupError("archive failed verification:\n" + "\n".join(problems))
    return report


# ---- restore ----------------------------------------------------------------------------------
def _write_new(name: str, data: bytes, modified_ns: int, dir_fd: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(name, flags, 0o644, dir_fd=dir_fd)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
        os.fsync(fd)
        os.utime(fd, ns=(modified_ns, modified_ns))
    finally:
        os.close(fd)


def _recheck(target: Path, entries: list[dict[str, Any]]) -> None:
    """The restored library must hold exactly the manifest's bytes and checked fingerprints."""
    for entry in entries:
        kind, name = entry["path"].split("/", 1)
        disk = target / (name if kind == "projects" else f"{TRASH_DIR}/{name}")
        if _sha256(disk.read_bytes()) != entry["sha256"]:
            raise BackupError(f"restored {disk.name} differs from the backup")
    expected = {
        e["project_id"]: e["fingerprint"]
        for e in entries
        if e["kind"] == "active" and e["readable"] and e["schema_version"] <= SCHEMA_VERSION
    }
    store = ProjectStore(target)
    active = {s.project.id: s.fingerprint for s in store.list()[0] if s.project.id in expected}
    if active != expected:
        raise BackupError("restored projects do not match the backup's fingerprints")
    trash = {t.entry for t in store.list_trash()}
    if trash != {e["path"].split("/", 1)[1] for e in entries if e["kind"] == "trash"}:
        raise BackupError("restored deleted entries do not match the backup")


def restore_backup(archive: str | Path, target: str | Path) -> BackupReport:
    """Restore into a directory that must not exist yet; verifies before writing anything."""
    report = verify_backup(archive)
    requested = Path(target).expanduser().absolute()
    parent = requested.parent.resolve()
    if not parent.is_dir():
        raise BackupError(f"directory {parent} for the restored library does not exist")
    destination = parent / requested.name
    try:
        os.mkdir(destination)  # the claim: fails if anything, even a symlink, is already there
    except FileExistsError:
        raise BackupError(
            f"{destination} already exists; restore only into a new directory"
        ) from None
    except OSError as exc:
        raise BackupError(f"cannot create {destination}: {exc}") from exc
    created: list[tuple[str, int]] = []  # (name, dir_fd) of every file this restore wrote
    root_fd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    trash_fd: int | None = None
    try:
        # The marker comes first, so a crash at any later point leaves a refused library.
        _write_new(INCOMPLETE_MARKER, b"restore in progress\n", time.time_ns(), root_fd)
        created.append((INCOMPLETE_MARKER, root_fd))
        with LibraryOwnership(destination):
            with _open_archive(archive) as zf:
                entries, members = _verified(zf)
                budget = _Budget()
                for entry in entries:
                    data = budget.read(zf, members[entry["path"]], MAX_FILE_BYTES)
                    if _sha256(data) != entry["sha256"]:
                        raise BackupError("the archive changed during the restore")
                    kind, name = entry["path"].split("/", 1)
                    if kind == "trash" and trash_fd is None:
                        os.mkdir(TRASH_DIR, dir_fd=root_fd)
                        trash_fd = os.open(
                            TRASH_DIR, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
                        )
                    dir_fd = root_fd if kind == "projects" else trash_fd
                    assert dir_fd is not None
                    _write_new(name, data, entry["modified_ns"], dir_fd)
                    created.append((name, dir_fd))
            if trash_fd is not None:
                os.fsync(trash_fd)
            os.fsync(root_fd)
            _recheck(destination, entries)
            os.unlink(INCOMPLETE_MARKER, dir_fd=root_fd)
            os.fsync(root_fd)
    except BaseException:
        # Remove exactly what this restore created; never a recursive delete.
        for name, dir_fd in reversed(created):
            with suppress(OSError):
                os.unlink(name, dir_fd=dir_fd)
        with suppress(OSError):
            os.unlink(LOCK_FILE, dir_fd=root_fd)
        if trash_fd is not None:
            with suppress(OSError):
                os.rmdir(TRASH_DIR, dir_fd=root_fd)
        with suppress(OSError):
            os.rmdir(destination)
        raise
    finally:
        if trash_fd is not None:
            os.close(trash_fd)
        os.close(root_fd)
    return report
