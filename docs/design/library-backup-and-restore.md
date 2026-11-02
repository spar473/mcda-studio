# Library backup and restore

**Status:** implemented locally, 27 October 2026, in `src/mcda_studio/storage/library_backup.py`
([checks](../development/library-backup-verification.md)). The owner accepted the four
[decisions](#decisions) below. Small refinements made while building it are listed under
[implementation notes](#implementation-notes).

This note turns the roadmap's **Library backup and restore** development into rules that can be
tested. It builds on [library ownership and recovery](../development/library-recovery.md), which
already provides the ownership lock, the `.trash/` naming rules and a no-overwrite restore for
single projects. Today a whole-library backup is a manual drill that copies the folder with
`shutil.copytree`. This development replaces that drill with three commands that check their own
work.

## Goals and non-goals

**Goals:**

- One file holds a whole library: active projects, deleted entries in `.trash/` and a manifest.
- Anyone can check that file, without MCDA Studio writing anything.
- A restore produces a fresh library whose projects match the backup's bytes and fingerprints, or
  else fails with nothing half-published.
- A hostile or damaged archive can never write outside the target, overwrite a file or exhaust
  the disk.

**Non-goals (excluded):**

- scheduled, incremental or cloud backups;
- encryption, signatures or proof of who made an archive;
- a GUI or HTTP API;
- backing up while a server runs (online backup);
- merging into an existing library, or restoring a single project;
- Windows (library ownership is POSIX-only today).

## Commands

```sh
mcda library backup --store DIR --to FILE.zip
mcda library verify FILE.zip
mcda library restore FILE.zip --to NEW_DIR
```

- **`backup`:**
  - takes library ownership for its whole run, so it is refused while a server or writer owns
    the library;
  - reads every included file once, and writes and verifies the archive;
  - publishes the archive without overwriting anything.
- **`verify`:** applies every safety and integrity check below and writes nothing.
- **`restore`:**
  - verifies first;
  - then creates a **new** library directory and extracts into it under that library's
    ownership;
  - then re-checks the result.

Every command prints a short report: the counts of active and deleted entries, any skipped or
unreadable files, and the result. With `--json`, the report is machine-readable.

**Exit status**, the same for all three commands:

| Code | Meaning |
| --- | --- |
| `0` | Completed; everything was archived, verified or restored |
| `3` | Completed with warnings: something was skipped (backup) or not checked, such as a newer-schema entry. The report lists each one |
| `1` | Failed; see [failure behaviour](#failure-behaviour) for what is left |

Typer's own usage errors keep their usual code `2`.

## What a backup contains

| Source in the library | In the archive | Notes |
| --- | --- | --- |
| `<id>.json` at the top level, regular file, name matches the project ID pattern | `projects/<id>.json` | Bytes copied exactly |
| `.trash/<id>.<stamp>.json`, regular file, name matches the trash pattern | `trash/<id>.<stamp>.json` | Bytes copied exactly |
| The archive's own record | `manifest.json` | Written first |

Everything else is left out and listed in the report as **skipped**, with a reason:

- the lock marker `.mcda-studio.lock`;
- leftover `.restore-*.tmp` and `.<name>.tmp` stage files;
- other hidden files, subdirectories and non-JSON files;
- symlinks and non-regular files (FIFOs, devices).

Symlinks are never followed, so a backup cannot pull in data from outside the library.

**Unreadable projects are still backed up.** A file that is malformed, fails validation, or uses a
newer schema version is archived byte for byte and marked unreadable in the manifest, with the
error. A backup exists to preserve data, not to judge it. This mirrors how Projects and Recently
deleted already list unreadable files instead of hiding them.

## Manifest

```json
{
  "format": "mcda-studio-library-backup",
  "format_version": 1,
  "created_at": "2026-10-27T09:15:02.123456Z",
  "app_version": "0.1.0",
  "app_schema_version": 1,
  "entries": [
    {
      "path": "projects/supplier_selection.json",
      "kind": "active",
      "size": 18342,
      "sha256": "…",
      "modified_ns": 1793001234567890123,
      "readable": true,
      "project_id": "supplier_selection",
      "schema_version": 1,
      "fingerprint": "…",
      "error": null
    }
  ],
  "skipped": [{ "name": ".restore-ab12.tmp", "reason": "temporary stage file" }]
}
```

- **Two hashes, two jobs.**
  - `sha256` covers the exact bytes, so any change to an archived file is detected.
  - `fingerprint` is the existing `Project.fingerprint()`, computed over canonical JSON after
    migration. It ties the backup to the revision identity used by Save and conflict checks.
  - Unreadable entries have `sha256` but no fingerprint.
- **`modified_ns`** restores modification times. Projects are listed most-recently-modified
  first, so losing the times would reorder the library. ZIP timestamps are too coarse
  (2 seconds, local time) to rely on.
- **No source path.** Absolute library paths can contain a user name. The manifest records none
  by default.
- **The manifest is not proof of authenticity.** It lives inside the same archive, so it catches
  accidental damage and truncation, not deliberate tampering. The docs say so plainly.

## Backup procedure

1. **Resolve and check the paths.**
   - Resolve `--store`; it must be an existing directory.
   - `--to` must not exist and must not be inside the library (otherwise a later backup could
     sweep in an earlier one, and a restore could nest libraries).
2. **Take library ownership** with the existing `LibraryOwnership`.
   - A running server makes this fail with its PID and port. The message says to stop the server
     first; it never suggests deleting the lock.
   - If the library has no marker yet, taking ownership creates one, as any `ProjectStore` write
     already does. The marker is never archived.
3. **Enumerate entries.**
   - Use `os.scandir` without following symlinks. Classify each entry using the table above, and
     sort the result so archives come out in a deterministic order.
4. **Read each included file exactly once** into memory.
   - Open it with `O_NOFOLLOW`, then check with `fstat` that it is a regular file.
   - Read it in full, enforcing the per-file size limit as it reads.
   - Hash those same bytes and write those same bytes to the archive. The manifest can then never
     describe different content from what was stored.
5. **Write the archive to a temporary file** created with `mkstemp` in the destination
   directory.
   - Use ZIP with `DEFLATED` compression, writing `manifest.json` first.
   - Flush and `fsync` the file.
6. **Verify the temporary archive** with the same code as `verify`.
7. **Publish without overwriting.**
   - Hard-link the temporary file to `--to`, which fails if anything already exists there
     (`os.link`, as single-project restore already does). Then `fsync` the directory and remove
     the temporary name.
   - A filesystem that cannot hard-link fails explicitly. It never falls back to an overwriting
     rename.
8. **Release ownership.** The source library is never modified, apart from the lock marker's
   diagnostic content.

## Safety and integrity checks (`verify`, and the first step of `restore`)

These checks run on the archive itself. The manifest is never trusted for safety.

**Archive members:**

- **Allowed names only.** Each member name must exactly match one of three ASCII patterns:
  - `manifest.json`;
  - `projects/<ID>.json`, using the existing project ID pattern;
  - `trash/<ID>.<YYYYMMDDTHHMMSSffffffZ>.json`.

  This alone rejects:
  - traversal (`..`), absolute paths, backslashes and drive letters;
  - NUL characters and non-ASCII look-alike characters;
  - directory entries.
- **No duplicates.** A member name may appear only once, also when compared case-insensitively
  (macOS file systems are case-insensitive by default, so `A.json` and `a.json` would collide on
  disk).
- **No special members.** Refuse:
  - members whose stored mode marks a symlink or anything other than a regular file;
  - encrypted members;
  - compression methods other than stored or deflated.
- **Matching headers.** Python's `zipfile` already refuses a member whose local header name
  differs from its central-directory name. A test pins that behaviour.

**Size limits.** These are module constants, not command options, and are enforced while
reading, never by trusting the sizes the archive declares. Backup applies the same limits, so it
never writes an archive that restore would refuse. Changing a value is a code change with its own
test.

| Limit | Value |
| --- | --- |
| Members | 100,000 |
| One project file, uncompressed | 64 MiB |
| `manifest.json` | 32 MiB |
| Total uncompressed size | 4 GiB |
| Compression ratio per member | 200:1, above 1 MiB |

**Manifest:**

- It must parse, carry `format` and a `format_version` this application knows, and list each
  member exactly once.
- No member may be missing from the manifest, and no manifest entry may be missing from the
  archive.

**Content:**

- Each member's size and `sha256` must match its manifest entry.
- Each readable entry must load, and its ID must match its name and manifest entry. Its
  fingerprint must match.
- An entry that uses a newer schema than this application is checked by bytes only and reported
  as "newer schema, not checked". That is a warning, not a failure, so an older application can
  still verify a backup made by a newer one.

## Restore procedure

1. **Verify the archive completely** before writing anything. Any failure stops here, with
   nothing written.
2. **Claim the target.**
   - `--to` must not exist. Restore creates it with `os.mkdir`, which fails if anything already
     exists there, and that is the claim. A symlink at that path is refused.
   - It then takes ownership of the new library, so no server can open it mid-restore.
3. **Write the incomplete marker.** Write `.mcda-restore-incomplete` first and `fsync` it.
4. **Write each member.**
   - The name comes only from the fixed mapping (`projects/<id>.json` → `<id>.json`, and
     `trash/<entry>` → `.trash/<entry>`).
   - Open it relative to the target's directory descriptor with
     `O_CREAT | O_EXCL | O_NOFOLLOW`.
   - Write the verified bytes, apply `modified_ns` with `os.utime`, and `fsync` the file.
   - `ZipFile.extract` and `extractall` are never used.
5. **Re-check the result.**
   - `ProjectStore(target).list()` and `list_trash()` must return exactly the manifest's readable
     IDs, fingerprints and deleted entries.
6. **Finish.** Remove the incomplete marker, `fsync` the directory, release ownership, and print
   the report with the next step (`mcda serve --store NEW_DIR`).

**Server guard:** `mcda serve` (and the app lifespan, for direct ASGI startup) refuses a library
that contains `.mcda-restore-incomplete`, and says to delete that directory and restore again. This
stops a half-restored library being used as if it were whole. It is the only change outside the
new commands.

## Failure behaviour

| Failure point | What is left | What the user is told |
| --- | --- | --- |
| Backup, any handled error | No file at `--to`; temporary file removed; library unchanged | The error, and that nothing was published |
| Backup, process killed | Possibly a stray temporary file next to `--to`; never a partial file at `--to` | (Docs) Delete stray temporary files by hand |
| Verify | Nothing written | Each failed check, with the member name |
| Restore, verification fails | Nothing written | The failed checks |
| Restore, handled error after claiming the target | Restore removes exactly the files it created, then the directory. It never uses `rmtree` | The error; the target path is free again |
| Restore, process killed | Target with `.mcda-restore-incomplete`; the server refuses it | (Docs) Delete that directory and restore again |

The archive and the source library are never modified by `verify` or `restore`.

## Relation to existing recovery

- **Recently deleted** still restores single projects inside a running library. Backups do not
  replace it.
- The **manual drill** in the recovery note becomes: back up, verify, restore to a new directory,
  serve it, restore one deleted project, then compare fingerprints. The `copytree` script stays
  documented as the fallback for libraries this tool refuses.
- **Rollback:** before upgrading MCDA Studio, take a backup with the old version. An older
  application refuses newer schemas, and a backup made earlier keeps the old bytes intact. The
  manifest records the application and schema versions to make that visible.

## Verification plan

**Unit tests:**

- every allowed-name pattern, accepting and rejecting cases;
- duplicates, including case-only collisions;
- symlink-mode, directory and encrypted members, and unknown compression;
- each size limit, using archives whose declared sizes lie;
- a missing manifest, an extra or missing member, one changed byte, a wrong fingerprint and a
  newer-schema entry;
- the manifest round trip.

**Integration and process tests:**

- **Round trip:** active projects, deleted entries and an unreadable file restore with identical
  bytes, fingerprints and modification times. Recently deleted works in the restored library.
- **Running server:** backup is refused with the owner details.
- **Target checks:** restore refuses an existing target, including an empty directory and a
  symlink.
- **Library left alone:** backup does not modify the library.
- **Exit status:** `0` for a clean run, `3` for a skipped file and for a newer-schema entry, `1`
  for each failure class.
- **Server guard:** `mcda serve` and direct ASGI startup refuse a library holding
  `.mcda-restore-incomplete`.
- **Injected failures:** an I/O failure after N files (cleanup is exact); a killed process
  (the marker remains and `serve` refuses the target).

**Mutants**, one per guard:

- name allowlist loosened;
- duplicate check removed;
- size limit read from the declared size;
- `O_EXCL` dropped;
- ownership not taken;
- target-exists check removed;
- hash comparison skipped;
- incomplete marker not written.

**Docs:** the recovery note, user guide and testing counts are updated when this is built.

## Acceptance

- A round trip preserves every byte, fingerprint and modification time, including `.trash/`.
- `verify` detects a changed, missing, extra or duplicated file.
- Restore refuses an existing target and never writes outside it.
- Backup refuses a library owned by a running server.
- Every hostile-archive case above is refused before anything is written.
- All new mutants are killed and the full gate stays green.

## Decisions

Accepted by the owner on 27 October 2026:

1. **Restore target must not exist.** This is stricter than the roadmap's original "refuses a
   non-empty target". Creating the directory is the only portable way to claim it atomically; an
   existing empty directory could be swapped or filled between the check and the write.
2. **Exit status `0` / `3` / `1`:** completed, completed with warnings, failed. See
   [commands](#commands).
3. **Size limits are constants** with the values in the table above, not command options.
4. **`mcda serve` refuses an incomplete restore.** See [restore procedure](#restore-procedure).

## Implementation notes

Refinements made while building it, 27 October 2026:

- **The lock marker is excluded silently.** Every managed library has `.mcda-studio.lock`, so
  listing it as "skipped" would make every backup exit `3`. Stage files, hidden files,
  subdirectories, symlinks and badly named files are still listed.
- **Permission-only ZIP modes are accepted.** Many ZIP writers, including Python's `writestr`,
  store permission bits without a file-type bit. A member is refused only when it declares a type
  other than a regular file, such as a symlink.
- **The incomplete marker is written before ownership is taken,** so a crash at any later point
  leaves a library the server refuses.
- **`verify` reports unchecked entries, not skipped files.** Skipped files are listed in the
  manifest and by `backup`; they are not part of the archive, so `verify` has nothing to check.
- **Backup holds the included files in memory** while it writes the archive, up to the 4 GiB total
  limit. Project files are small in practice; streaming is a possible later refinement.
- **The mutation harness** has a `BACKUP_BACKEND` group (11 mutants) and a `--backup-only` flag.
