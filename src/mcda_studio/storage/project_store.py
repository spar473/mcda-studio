"""A directory of project files, addressed by project id.

This is the persistence service behind the API (and anything else that wants "a library of
projects" rather than a single path). It adds three guarantees on top of ``JsonProjectRepository``:

* **Identity**: the file name is ``<project id>.json`` and the id inside the file must match, so a
  project cannot be stored under a different identity than the one it carries.
* **No silent overwrite**: ``create`` refuses an id that exists; ``replace`` can be made
  conditional on the revision (fingerprint) the caller last saw, so two editors cannot silently
  overwrite each other. Lifetime library ownership coordinates cooperating processes; see
  ``docs/api/contract.md`` for external-writer limits.
* **Recoverable deletion**: ``delete`` moves the file into ``.trash/`` instead of unlinking it.
"""

import json
import os
import re
import stat
import tempfile
import threading
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from mcda_studio.domain.common import Id
from mcda_studio.domain.errors import (
    McdaError,
    ModelStructureError,
    ProjectExistsError,
    ProjectLoadError,
    ProjectNotFoundError,
    StaleRevisionError,
)
from mcda_studio.domain.project import Project
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text
from mcda_studio.storage.library_lock import LibraryOwnership

_ID = TypeAdapter(Id)
TRASH_DIR = ".trash"
_TRASH_NAME = re.compile(
    r"(?P<id>[A-Za-z0-9][A-Za-z0-9_.-]{0,63})\.(?P<stamp>\d{8}T\d{12}Z)\.json\Z"
)


class InvalidTrashEntryError(McdaError):
    """An unsafe trash path/name was refused."""


class UnreadableTrashEntryError(McdaError):
    """Recovery data cannot be safely interpreted."""


class RestoreError(McdaError):
    """Publication failed; recovery data is retained."""


@dataclass(frozen=True)
class TrashEntry:
    entry: str
    project_id: str | None
    title: str | None
    deleted_at: datetime | None
    readable: bool
    conflict: bool
    error: str | None


@dataclass(frozen=True)
class StoredProject:
    project: Project
    fingerprint: str
    updated_at: datetime


@dataclass(frozen=True)
class UnreadableFile:
    file: str
    error: str


class InvalidProjectIdError(McdaError):
    """The id is not a legal project id (so it can never be a safe file name)."""


class ProjectStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser()
        self._repo = JsonProjectRepository()
        self._lock = threading.RLock()
        self._owner: LibraryOwnership | None = None

    @contextmanager
    def ownership(self, port: int | None = None) -> Iterator[None]:
        """Server lifetime ownership; nested use on this store never reacquires its OS lock."""
        with self._lock:
            if (
                self._owner is not None
                and self._owner.fd is not None
                and self._owner.pid == os.getpid()
            ):
                nested = True
            else:
                nested = False
                owner = LibraryOwnership(self.root, port)
                owner.__enter__()
                self._owner = owner
        try:
            yield
        finally:
            if not nested:
                with self._lock:
                    assert self._owner is not None
                    self._owner.close()
                    self._owner = None

    @contextmanager
    def _mutation(self) -> Iterator[None]:
        with self._lock, self.ownership():
            yield

    # ---- helpers ------------------------------------------------------------------------
    def path_for(self, project_id: str) -> Path:
        try:
            _ID.validate_python(project_id)
        except ValidationError:
            raise InvalidProjectIdError(f"{project_id!r} is not a valid project id") from None
        path = (self.root / f"{project_id}.json").resolve()
        if path.parent != self.root.resolve():  # defence in depth; the Id pattern forbids '/'
            raise InvalidProjectIdError(f"{project_id!r} is not a valid project id")
        return path

    @staticmethod
    def _mtime(path: Path) -> datetime:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)

    def _read(self, path: Path) -> StoredProject:
        project = self._repo.load(path)
        if path.stem != project.id:
            raise ProjectLoadError(
                f"{path.name} contains project id {project.id!r}; the file name and the id "
                "inside the file must agree"
            )
        return StoredProject(project, project.fingerprint(), self._mtime(path))

    # ---- queries ------------------------------------------------------------------------
    def exists(self, project_id: str) -> bool:
        return self.path_for(project_id).is_file()

    def get(self, project_id: str) -> StoredProject:
        path = self.path_for(project_id)
        with self._lock:
            if not path.is_file():
                raise ProjectNotFoundError(f"no project with id {project_id!r}")
            return self._read(path)

    def list(self) -> tuple[list[StoredProject], list[UnreadableFile]]:
        """All readable projects (most recently modified first) and the files that were not."""
        found: list[StoredProject] = []
        unreadable: list[UnreadableFile] = []
        with self._lock:
            if not self.root.is_dir():
                return [], []
            for path in sorted(self.root.glob("*.json")):
                if path.name.startswith("."):
                    continue
                try:
                    found.append(self._read(path))
                except McdaError as exc:
                    unreadable.append(UnreadableFile(path.name, str(exc).splitlines()[0]))
        found.sort(key=lambda s: (s.updated_at, s.project.id), reverse=True)
        return found, unreadable

    # ---- commands -----------------------------------------------------------------------
    def create(self, project: Project) -> StoredProject:
        path = self.path_for(project.id)
        with self._mutation():
            if path.exists():
                raise ProjectExistsError(f"a project with id {project.id!r} already exists")
            self._repo.save(project, path)
            return self._read(path)

    def replace(self, project: Project, expected_fingerprint: str | None = None) -> StoredProject:
        """Overwrite an existing project. With ``expected_fingerprint`` the write only happens
        if the stored project is still exactly the revision the caller based its edit on."""
        path = self.path_for(project.id)
        with self._mutation():
            if not path.is_file():
                raise ProjectNotFoundError(f"no project with id {project.id!r}")
            if expected_fingerprint is not None:
                current = self._read(path).fingerprint
                if current != expected_fingerprint:
                    raise StaleRevisionError(
                        f"project {project.id!r} was changed by someone else since you opened "
                        "it; reload it (or save a copy) instead of overwriting"
                    )
            self._repo.save(project, path)
            return self._read(path)

    def delete(self, project_id: str) -> Path:
        """Move the project file to ``.trash/``; returns where it went."""
        path = self.path_for(project_id)
        with self._mutation():
            if not path.is_file():
                raise ProjectNotFoundError(f"no project with id {project_id!r}")
            trash = self.root / TRASH_DIR
            trash.mkdir(parents=True, exist_ok=True)
            if trash.is_symlink():
                raise InvalidTrashEntryError("Trash directory must not be a symlink.")
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            target = trash / f"{project_id}.{stamp}.json"
            path.replace(target)
            return target

    def _trash_directory(self) -> int:
        path = self.root / TRASH_DIR
        try:
            return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except FileNotFoundError:
            raise ProjectNotFoundError("No deleted entries in this library.") from None
        except OSError as exc:
            raise InvalidTrashEntryError(f"Unsafe or unreadable trash directory: {exc}") from exc

    def _trash_identity(self, entry: str) -> tuple[str, datetime]:
        match = _TRASH_NAME.fullmatch(entry)
        if not match:
            raise InvalidTrashEntryError(
                "Invalid deleted-entry name; select an entry from Recently deleted."
            )
        try:
            deleted = datetime.strptime(match["stamp"], "%Y%m%dT%H%M%S%fZ").replace(tzinfo=UTC)
        except ValueError:
            raise InvalidTrashEntryError("Invalid deletion timestamp in entry name.") from None
        return match["id"], deleted

    def _load_trash(self, directory: int, entry: str) -> Project:
        expected_id, _ = self._trash_identity(entry)
        try:
            fd = os.open(entry, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, "r", encoding="utf-8") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise InvalidTrashEntryError("Deleted entry is not a regular file.")
                project = self._repo.from_dict(json.load(stream))
            if project.id != expected_id:
                raise InvalidTrashEntryError("Deleted entry name and stored project ID must agree.")
            project.tree()  # Incomplete models are fine; corrupt structures are not.
            return project
        except FileNotFoundError:
            raise ProjectNotFoundError(
                "Deleted entry no longer exists; refresh Recently deleted."
            ) from None
        except (OSError, UnicodeError, ValueError, ProjectLoadError, ModelStructureError) as exc:
            raise UnreadableTrashEntryError(
                f"Cannot read deleted entry; recovery data retained: {exc}"
            ) from exc

    def list_trash(self) -> Sequence[TrashEntry]:
        with self._lock:
            try:
                directory = self._trash_directory()
            except ProjectNotFoundError:
                return []
            try:
                entries = []
                for entry in sorted(os.listdir(directory), reverse=True):
                    project_id, deleted, title = None, None, None
                    try:
                        project_id, deleted = self._trash_identity(entry)
                        project = self._load_trash(directory, entry)
                        title = project.title
                        conflict = os.path.lexists(self.root / f"{project.id}.json")
                        entries.append(
                            TrashEntry(entry, project_id, title, deleted, True, conflict, None)
                        )
                    except McdaError as exc:
                        entries.append(
                            TrashEntry(entry, project_id, title, deleted, False, False, str(exc))
                        )
                return entries
            finally:
                os.close(directory)

    def restore(self, entry: str, as_copy: bool = False) -> StoredProject:
        """Publish without overwrite; retain the recovery entry on success as well as failure."""
        self._trash_identity(entry)
        with self._mutation():
            directory = self._trash_directory()
            staged: Path | None = None
            root_fd = None
            try:
                project = self._load_trash(directory, entry)
                if as_copy:
                    new_id = uuid.uuid4().hex[:16]
                    if new_id == project.id:
                        raise RestoreError("Could not allocate a new ID; retry restore as copy.")
                    project = self._repo.from_dict(
                        {**project.model_dump(mode="json"), "id": new_id}
                    )
                destination = self.root / f"{project.id}.json"
                # Atomic publication refuses any existing entry, including a symlink.
                root_fd = os.open(self.root.resolve(), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                fd, name = tempfile.mkstemp(dir=self.root, prefix=".restore-", suffix=".tmp")
                staged = Path(name)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(to_json_text(project))
                    stream.flush()
                    os.fsync(stream.fileno())
                if self._repo.load(staged) != project:
                    raise RestoreError(
                        "Staged project failed verification; recovery data retained."
                    )
                try:
                    os.link(
                        staged.name,
                        destination.name,
                        src_dir_fd=root_fd,
                        dst_dir_fd=root_fd,
                        follow_symlinks=False,
                    )
                except FileExistsError:
                    raise ProjectExistsError(
                        f"Project ID {project.id!r} already exists; restore as a copy instead."
                    ) from None
                os.fsync(root_fd)
                return self._read(destination)
            except OSError as exc:
                raise RestoreError(
                    "Restore could not complete; recovery data retained. "
                    f"Refresh Projects before retrying: {exc}"
                ) from exc
            finally:
                if staged is not None:
                    with suppress(OSError):
                        staged.unlink(missing_ok=True)
                if root_fd is not None:
                    os.close(root_fd)
                os.close(directory)
