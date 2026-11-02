"""POSIX advisory library ownership. The persistent file is a marker, never the lock itself."""

import json
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from mcda_studio.domain.errors import McdaError

LOCK_FILE = ".mcda-studio.lock"


class LibraryBusyError(McdaError):
    """Another cooperating writer owns this library."""


class LibraryLockError(McdaError):
    """Library ownership cannot be established safely."""


class LibraryOwnership:
    def __init__(self, root: Path, port: int | None = None) -> None:
        self.root = root.resolve()
        self.port = port
        self.fd: int | None = None
        self.pid = os.getpid()

    def __enter__(self) -> "LibraryOwnership":
        if os.name != "posix":
            raise LibraryLockError("Library ownership is supported on macOS/Linux only.")
        import fcntl

        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / LOCK_FILE
        try:
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                os.close(fd)
                raise LibraryLockError(f"Library lock is not a regular file: {path}")
            self.fd = fd
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                diagnostic = os.read(fd, 2048).decode("utf-8", errors="replace").strip()
                self.close()
                raise LibraryBusyError(
                    f"Library {self.root} is owned by another process "
                    f"({diagnostic or 'owner details unavailable'}). "
                    "Stop that server/writer before writing; do not delete its lock file."
                ) from None
            data = json.dumps({"pid": self.pid, "port": self.port}) + "\n"
            os.ftruncate(fd, 0)
            os.write(fd, data.encode())
            os.fsync(fd)
        except OSError as exc:
            self.close()
            raise LibraryLockError(f"Cannot lock library {self.root}: {exc}") from exc
        return self

    def close(self) -> None:
        if self.fd is not None:
            # Closing releases flock, including after ordinary process termination.
            os.close(self.fd)
            self.fd = None

    def __exit__(self, *args: object) -> None:
        self.close()


@contextmanager
def managed_write(path: str | Path) -> Iterator[None]:
    """Protect direct CLI output in a previously initialised library; leave other files ordinary."""
    destination = Path(path).expanduser()
    # Protect both the named directory and a symlink destination's directory when managed.
    roots = sorted({destination.absolute().parent.resolve(), destination.resolve().parent})
    from contextlib import ExitStack

    with ExitStack() as stack:
        for root in roots:
            marker = root / LOCK_FILE
            if marker.exists() or marker.is_symlink():
                stack.enter_context(LibraryOwnership(root))
        yield
