# Local library ownership and recovery (C1)

Implemented for the scoped macOS/Linux local-filesystem workflow. No Windows, network filesystem,
remote/multi-user server or uncooperative-writer guarantee is claimed. No project-schema or
numerical-engine change. Verification is recorded in [C1 verification](package-c1-verification.md).

## Ownership and CLI cooperation

The server acquires an exclusive, nonblocking POSIX `flock` on `<library>/.mcda-studio.lock`
for its lifetime. Normal shutdown closes the descriptor; termination releases OS ownership too.
The marker remains with PID/port diagnostics. **A leftover file or PID is not ownership**: only
successful OS-lock acquisition decides. Never delete, rename or replace a live lock file to force
access; that would create a different inode and defeat cooperation. A lock symlink/nonregular file
is refused. Canonical library paths make ordinary directory aliases share ownership.

CLI startup takes ownership after binding a port but before running the server or opening a
browser. The app lifespan also takes ownership for direct ASGI/factory use. Nested use of the
same `ProjectStore` reuses its owner's descriptor; worker-thread writes take the existing RLock
without deadlocking on another process lock. Independent `ProjectStore` objects/processes do not
implicitly share ownership. A second server fails with owner PID/port where recorded; distinct
libraries can operate simultaneously. Direct ASGI startup records PID with no known port.

Every `ProjectStore` mutation acquires the same protection if it does not already own the library.
Existing per-project `If-Match`/fingerprint conflicts remain independent: ownership excludes other
cooperating processes, while conditional save protects two editors using the owning server.

A library becomes **managed** when a server or `ProjectStore` first creates its marker. Direct
CLI project edits, new/copy writes and result-file outputs check their destination directory (and
resolved symlink destination) for that marker. In a managed directory they acquire the same lock;
in-place edits hold it across load → modify → save. While the server runs, write through its API,
or stop it before using direct-file CLI writes. Read-only CLI evaluation can still read snapshots.
For `--output` to an unrelated directory, the CLI writes only there and leaves the library alone.

Ordinary CLI work on unrelated files does not create library markers or acquire library ownership.
Do not begin an unmanaged direct-file write and initialise its directory as a server library at
the same time: establish management first. Keep the marker after shutdown. Direct CLI commands
still use their normal file-path/ID semantics; when creating new projects, create outside the
library and import through Projects so filenames match the stored IDs.

These are advisory locks for cooperating MCDA processes. Editors, file sync, older MCDA versions,
arbitrary Python scripts and other external programs can ignore them. Stop the server before
external modifications, directory moves, backup recovery or lock-file maintenance. This is not
hostile concurrent-filesystem isolation. Do not expose the unauthenticated server on a network.
Primary API references: [Python flock](https://docs.python.org/3.12/library/fcntl.html) and
[descriptor-relative link/open operations](https://docs.python.org/3.12/library/os.html#os.link).

## Recently deleted

Projects → **Recently deleted** lists each entry, title, UTC-derived deletion time, readability
and whether the original ID is active. Unknown/unreadable entries remain visible with their error;
they are never automatically deleted, repaired or silently adopted.

- **Restore** uses the original ID and preserves its numerical inputs and fingerprint. Incomplete
  drafts may be restored; invalid schema/tree data is refused. Canonical JSON formatting is used,
  so externally reformatted recovery JSON need not retain its original whitespace bytes.
- **Restore as copy** is offered when the original ID exists. It creates a fresh stable ID and a
  deliberately different fingerprint, keeping all other project data. It never overwrites the
  active project. A conflict arising after listing returns an actionable error and refreshes the
  recovery list so the copy action is offered.
- **Both successful modes retain the original trash entry.** Once restored, that entry normally
  reports an active-ID conflict and offers copy restoration. The UI explains retention; it is not
  a second deleted active project. Repeated copy restores deliberately create additional projects.
- There is no permanent purge, durable-draft recovery or change to editor undo/redo in C1.
  Whole-library backup archives came later (see below).

Existing entries use `<project-id>.<YYYYMMDDTHHMMSSffffffZ>.json`. Restore validates the entire
name/timestamp, reads relative to an opened nonsymlink `.trash` directory using no-follow flags,
requires a regular file and checks that the stored ID matches the filename. Symlinked directories,
symlinked entries, FIFOs, traversal and ID mismatches are refused without changing recovery data.
Unreadable/malformed files remain recoverable by hand, subject to their actual contents.

Under library ownership, restore serialises/flushes/fsyncs a hidden stage file in the library,
reloads it for verification, then publishes with an atomic hard link that **fails if any destination
entry exists**, including a symlink. It syncs the directory and cleans the hidden stage. No
check-then-overwrite or `os.replace` is used for restoration. The trash entry is never unlinked.
A crash before publication leaves recovery data intact; a crash after publication may leave both
a valid active file and a hidden stage, plus the retained trash entry. Refresh Projects before
retrying after a reported I/O failure. Leftover `.restore-*.tmp` files are not active projects;
inspect them only while stopped. Filesystems that cannot provide the required link/sync operations
fail explicitly rather than falling back to an overwriting publication.

API: `GET /api/trash`; `POST /api/trash/{entry}/restore` with `{ "as_copy": false }` (or true).
Successful restore returns 201 with the normal project document, Location and ETag. Errors use the
existing envelope: 409 `PROJECT_EXISTS`/`LIBRARY_BUSY`, 422 `TRASH_ENTRY_INVALID` or
`TRASH_ENTRY_UNREADABLE`, 404 for a missing entry, and 500 `RESTORE_FAILED` for publication failure.
Do not add numerical restore logic or saved analytical results to project files.

## Backup archives (27 October 2026)

`mcda library backup`, `verify` and `restore` replace the copy-based drill below as the normal
route. Rules, limits and failure behaviour are in the
[design note](../design/library-backup-and-restore.md); checks are in the
[check record](library-backup-verification.md). The drill with the tool:

1. Stop every server and direct-file CLI writer for the library.
2. `mcda library backup --store /absolute/library --to /absolute/new-backup.zip`. It refuses an
   owned library, an existing file and a destination inside the library.
3. `mcda library verify /absolute/new-backup.zip`.
4. `mcda library restore /absolute/new-backup.zip --to /absolute/new-recovered`. The target must
   not exist. Restore verifies first and re-checks bytes and fingerprints afterwards.
5. `mcda serve --store /absolute/new-recovered --open`, then continue with steps 4–5 of the manual
   drill below.

Exit status is `0` (completed), `3` (completed with warnings, each listed) or `1` (failed). A
restore that was killed leaves `.mcda-restore-incomplete` in the target, and `mcda serve` refuses
that directory: delete it and restore again. Keep the manual drill below for a library the tool
refuses, for example one holding a file over the size limits.

## Manual stopped-library backup/recovery drill

This is an operating procedure, the fallback to the backup commands above. First run it with
disposable libraries, as the integration test does. Use the installed Python environment
containing MCDA.

1. Stop all servers and direct-file CLI writers for the source library. Keep a retained application
   wheel and its version/build identity separately; an older application refuses newer schemas.
2. Choose a **nonexistent** backup directory and a different **nonexistent** recovery directory.
   Include hidden files and `.trash`; copying only `*.json` loses deleted recovery entries.
3. Run the following with explicit paths. It refuses an owned source library and existing targets;
   it preserves symlinks as symlinks instead of following them outside the library.

```sh
python - /absolute/source-library /absolute/new-backup /absolute/new-recovered <<'PY'
import shutil, sys
from pathlib import Path
from mcda_studio.storage.library_lock import LibraryOwnership
from mcda_studio.storage.project_store import ProjectStore
source, backup, recovered = map(Path, sys.argv[1:])
with LibraryOwnership(source):
    expected = {p.project.id: p.fingerprint for p in ProjectStore(source).list()[0]}
    shutil.copytree(source, backup, symlinks=True)
shutil.copytree(backup, recovered, symlinks=True)
actual = {p.project.id: p.fingerprint for p in ProjectStore(recovered).list()[0]}
assert actual == expected, (expected, actual)
print('Readable active project fingerprints match. Inspect unreadable files separately.')
print('Recovered deleted entries:', len(ProjectStore(recovered).list_trash()))
PY
mcda serve --store /absolute/new-recovered --open
```

4. Open a recovered active project. Inspect Recently deleted, restore a deleted project, reopen it
   and compare its fingerprint with the original deleted project's fingerprint. A same-ID restore
   matches; restore as copy intentionally does not. Confirm the trash data remains intact.
5. Keep the original library and backup untouched until the recovered library is accepted. Copied
   lock diagnostics may be stale; no OS lock is carried by a filesystem copy. Never recover over
   an active/nonempty library. If a step fails, keep all source/backup/recovery data for inspection;
   do not “fix” it by purging trash or deleting a live lock file.

`tests/integration/test_library_coordination.py::test_stopped_library_backup_and_fresh_location_recovery_drill`
exercises this sequence with temporary libraries, includes `.trash`, refuses an existing recovery
target, starts the recovered library in a fresh process, and checks original/restored fingerprints.
