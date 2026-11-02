# Library backup and restore: check record

**Date:** 27 October 2026, Pacific/Auckland. **Base:** `main` at `eeb6935`, uncommitted working tree.
**Scope:** library backup and restore as specified in the
[design note](../design/library-backup-and-restore.md), with the owner's four accepted decisions.
No API, OpenAPI, project-schema, frontend, dependency or numerical change.

## What changed

- **New module** `src/mcda_studio/storage/library_backup.py`:
  - `create_backup`: takes library ownership, reads each included file once with `O_NOFOLLOW`,
    archives those exact bytes with a manifest, verifies the temporary archive, then publishes it
    with a no-overwrite hard link.
  - `verify_backup`: allowlisted member names, duplicate and case-only collisions, member types,
    encryption and compression method, constant limits enforced on actual bytes, manifest-to-archive
    agreement, SHA-256 per member and fingerprints for readable entries. Writes nothing.
  - `restore_backup`: verifies first, claims a new directory with `mkdir`, writes the incomplete
    marker, takes ownership, writes every member with `O_CREAT | O_EXCL | O_NOFOLLOW`, restores
    modification times, re-checks bytes, fingerprints and Recently deleted, then removes the marker.
    A handled failure removes exactly the files it created; it never deletes recursively.
  - `ensure_restore_complete`: the guard used by `mcda serve` (`startup.run_server`) and by the
    app lifespan for direct ASGI startup.
- **CLI:** `mcda library backup --store DIR --to FILE.zip`, `mcda library verify FILE.zip` and
  `mcda library restore FILE.zip --to NEW_DIR`, each with `--json`. Exit `0` completed, `3`
  completed with warnings, `1` failed.
- **Mutation harness:** a `BACKUP_BACKEND` group (11 mutants), its runner and a `--backup-only`
  flag.
- **Docs:** design note status and implementation notes, the recovery operating note, user guide,
  README, testing, known limitations, roadmap, plan, handover, validation and changelog.

Refinements to the design, all recorded in its implementation notes:
- the lock marker is excluded without a warning;
- ZIP members with permission-only modes are accepted;
- the incomplete marker is written before ownership is taken;
- `verify` reports unchecked entries only;
- backup holds the included files in memory, up to the 4 GiB limit.

## Checks

**Environment:** macOS 26.5.1 (arm64), Python 3.12.15 in the project `.venv`, Node 26.12.1,
npm 11.20.0, Google Chrome 156.0.8078.48.

| Check | Command | Before (`eeb6935`) | After |
| --- | --- | --- | --- |
| Python tests | `.venv/bin/python -m pytest -q` | 652 passed | **700 passed**, 0 failed, 0 skipped (one upstream Starlette/httpx deprecation warning) |
| Ruff lint and format | `ruff check` / `ruff format --check` on `src tests scripts hatch_build.py` | Pass | Pass (90 files) |
| mypy `--strict` | `.venv/bin/mypy` | Pass (40 files) | Pass (41 files) |
| OpenAPI freshness | `scripts/export_openapi.py --check` | Pass | Pass |
| Acceptance demo | `scripts/acceptance_demo.py` | Pass | Pass |
| Acceptance evidence | `scripts/acceptance_evidence.py <new dir>` | Pass | Pass |
| Frontend gate | `npm --prefix frontend run check` | 313 Vitest | **313 Vitest**; TypeScript, ESLint, type freshness and build pass |
| Browser tests | `MCDA_PYTHON=… MCDA_CHROMIUM=… npm --prefix frontend run test:e2e` | 81 passed | **81 passed** (3.2 min; no frontend change) |
| Mutation check | `.venv/bin/python scripts/mutation_check.py` | 75 of 75 | **86 of 86 killed** (75 plus 11 backup); the unmutated copy passes |

The Python count rises by 48: 47 cases in `tests/unit/test_library_backup.py` and one real-process
case in `tests/integration/test_library_coordination.py`.

### New tests

`tests/unit/test_library_backup.py`:
- **Round trip:** active projects and Recently deleted restore with identical bytes and
  modification times; fingerprints match; a deleted project restores in the restored library to
  the original revision.
- **Contents:** the lock marker is never archived; a clean library has no warnings; symlinks (not
  followed, target bytes absent), stage files, hidden files, subdirectories and badly named files
  are skipped and listed; unreadable and newer-schema files are kept byte for byte and reported;
  a readable newer-schema entry is checked by bytes only.
- **Backup refusals:** an existing target, a target inside the library, a missing library and an
  owned library; the library is left unchanged; `verify` writes nothing.
- **Hostile archives:** 11 disallowed member names (traversal, absolute, backslash, non-ASCII, NUL,
  directories, wrong prefixes, hidden names); exact and case-only duplicates; symlink, encrypted
  and BZIP2 members; a local header name that differs from the central directory; eight manifest
  mismatches; a missing or invalid manifest; a missing member; a non-ZIP file; a changed byte that
  leaves the fingerprint unchanged.
- **Limits:** per member, total, member count and compression ratio, each on actual bytes; backup
  refuses a file over the limit instead of writing an archive restore would refuse.
- **Restore:** refuses an existing empty directory, a symlink and a missing parent; writes nothing
  when verification fails; creates files exclusively; an injected failure leaves no target
  directory; the incomplete marker exists until the re-check passes.
- **Server guard:** `ensure_restore_complete`, app startup and `mcda serve` refuse an unfinished
  restore.
- **CLI:** exit `0` for clean backup, verify (`--json`) and restore; `3` with a skipped file; `1`
  for an existing restore target and a non-ZIP file.

`tests/integration/test_library_coordination.py::test_library_backup_tool_respects_a_running_server_and_round_trips_through_one`
runs the real commands as subprocesses: a backup is refused while a real server owns the library,
with its PID and port; after the server stops, backup, verify and restore succeed, and a server on
the restored library lists the original fingerprint and restores the deleted project.

### Mutants

All 11 `BACKUP_BACKEND` mutants are killed (also run alone with `--backend-only --backup-only`):
- member-name allowlist removed;
- duplicate check removed;
- member size limit removed;
- `O_EXCL` replaced by `O_TRUNC` when restoring;
- backup without library ownership;
- restore into an existing directory;
- size compared but hash skipped;
- incomplete marker never written;
- archive members missing from the manifest accepted;
- `mcda serve` guard removed;
- app-startup guard removed.

## Acceptance

| Criterion | Result |
| --- | --- |
| Round trip preserves every byte, fingerprint and modification time, including `.trash/` | Met |
| `verify` detects a changed, missing, extra or duplicated file | Met |
| Restore refuses any existing target and never writes outside it | Met |
| Backup refuses a library owned by a running server | Met (real process) |
| Every hostile-archive case is refused before anything is written | Met |
| `mcda serve` refuses an incomplete restore | Met |
| All new mutants killed; full gate green | Met |

## Not verified

- The hosted Linux run, including the installed-distribution stage, passed; see the follow-up below.
- A killed process mid-restore is simulated by a pre-made marker and by injected failures, not by
  sending a signal to a restoring process.
- Very large libraries near the 4 GiB limit; timings were not measured.
- No human usability result is claimed.

## Follow-up: hosted CI, 28 October 2026

The first hosted Linux runs that included this development (run 40649840671 for `764d5d3` and
run 40651347705 for `8c41c0c`) failed two of its tests, with the commands behaving correctly:
`test_cli_exit_status_is_0_clean_3_with_warnings_and_1_on_failure` and
`test_library_backup_tool_respects_a_running_server_and_round_trips_through_one`. Rich wraps error
messages at the terminal width, and the runner's temporary path put a line break inside the
phrases the tests looked for ("already exists", "owned by another process"). Locally the paths
differ, so the break fell elsewhere.

The tests now match phrases on collapsed whitespace, as other CLI tests already do. Engine and
command code are unchanged. A sweep of 21 widths (`COLUMNS` 40 to 120) failed the old tests at 6
widths and the new tests at none; the full Python suite passes, 700 tests. Two older tests in
`test_workflow.py` still fail below about 60 columns because tables are squeezed; hosted CI renders
at Rich's default of 80, so they were left unchanged. Hosted run 40652287706 (commit `508f49b`)
passed every stage: 700 Python, 313 frontend and 81 browser tests, both distribution routes.
