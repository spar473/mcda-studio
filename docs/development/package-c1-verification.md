# C1 verification: essential library coordination and safe restore

Date: 2026-10-26 (Pacific/Auckland). Started and finished on `main` at
`3c382ab5e310d8c2f1b56444772e7d523c34ee36`, with uncommitted package B/planning work present.
No applicable `AGENTS.md` found. Existing work was preserved; no reset, clean, stash, commit,
push, tag or publication. See the final status snapshot below.

## Delivered design and scope

- POSIX lifetime library ownership, integrated with Package B startup and the app lifespan.
  Cooperating store mutations and managed-directory CLI outputs use the same protection.
  Owning worker writes reuse the owner's lock; project-level conditional-save conflicts remain.
- Deleted-entry listing and original-ID/new-ID-copy restoration using the existing serializers
  and API error conventions. Publication is staged, verified and atomically refuses existing
  destination entries, including symlinks. Both successful modes retain recovery data.
- Compact Recently deleted interface with restore/copy, readable failures/unreadable entries,
  refreshed project lists and an explicit retention explanation.
- [Manual stopped-library backup/recovery procedure](library-recovery.md), exercised on disposable
  data with deleted entries, a fresh recovery location, fingerprints and actual server reopening.

Canvas, numerical logic/services, project schema, durable drafts, purge and automated backup
archives are unchanged/deferred. Original numerical oracle values, tolerances, project fixtures,
contract-baseline hashes and frontend dependency lock are unchanged. No new dependency is needed.

The earlier plan suggested consuming/moving original-ID entries. C1 deliberately retains the
entry in both modes: no failure or uncertain completion removes the original recovery copy.
A successful restore makes the ID active and the retained row offers copy restoration. Repeated
copy actions deliberately create new projects; the interface explains this.

## Environment and exact checks

macOS 26.5.1 arm64; Python 3.12.15; Node 26.12.1; npm 11.20.0; existing native Chrome at
`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`. Existing Python numeric versions
and locks from B were retained. Temporary B build tools and verified wheelhouse were reused.
Hosted Linux CI is configured, not executed; no Windows verification/support claim.

Commands were run from the repository root:

| Command | Result |
| --- | --- |
| `git status --short`, `git branch --show-current`, `git rev-parse HEAD`, applicable-instruction search | Existing B/docs work preserved; main/HEAD above; no applicable AGENTS.md |
| `.venv/bin/python -m pytest -q tests/unit/test_recovery.py tests/api/test_api_recovery.py` | 18 passed |
| `.venv/bin/python -m pytest -q tests/integration/test_library_coordination.py` | 6 passed in 4.61 s; required localhost/process execution permission |
| `.venv/bin/python -m pytest -q` | 647 passed in 15.25 s; one existing Starlette/httpx deprecation warning. Ran with execution permission for localhost/process cases |
| `.venv/bin/ruff check src tests scripts hatch_build.py` | Passed |
| `.venv/bin/ruff format --check src tests scripts hatch_build.py` | Passed, 88 files |
| `.venv/bin/mypy` | Passed, 40 source files |
| `.venv/bin/python scripts/export_openapi.py --check` | Passed; generated with `scripts/export_openapi.py` and `npm --prefix frontend run gen:types` after new recovery routes |
| `.venv/bin/python scripts/acceptance_demo.py` | Passed, including save and fresh-process reopen |
| `.venv/bin/python scripts/acceptance_evidence.py <temporary directory>` | Passed, exact VC crossovers/oracles, contribution reconciliation, performance fixture reproduction and exact reopen |
| `npm --prefix frontend run check` | Passed: typecheck, ESLint, generated types, 237 tests across 25 files and production build |
| `MCDA_PYTHON="$PWD/.venv/bin/python" MCDA_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' npm --prefix frontend run test:e2e` | 68 passed in 1.6 min, including actual UI restore/copy/reopen; disposable server/store only |
| `.venv/bin/python scripts/mutation_check.py` | Passed: 68/68 killed, including all four C1 mutants; unmodified scratch baseline passed |
| `<temporary tools environment>/bin/python scripts/build_release.py --skip-frontend --out dist/c1` | Passed: direct wheel, sdist, wheel rebuilt from extracted sdist without isolation/index/Node, archive inspection and missing-GUI negative gate |
| `MCDA_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' <temporary tools environment>/bin/python scripts/smoke_install.py --dist dist/c1 --browser --wheelhouse <temporary wheelhouse>` | Passed on final artifact hashes: both wheel routes and isolated pipx, including installed GUI restore and second-owner refusal |
| `git diff --check` and relative documentation links | Passed: 134 relative file links across 15 documents resolve; whitespace check passed |

## What the tests establish

The six integration cases use real independent processes and disposable libraries: same-library
second-server refusal with owner PID/port, separate libraries simultaneously usable, managed CLI
write refusal while owned and success after shutdown, unrelated CLI writes unaffected, normal
shutdown and SIGKILL releasing ownership, interruption before/after restore publication, and
stopped-library backup/recovery into a fresh location including trash. Restored/reopened original
IDs keep their fingerprints; copy IDs change fingerprints and keep all other project data.

Focused storage/API cases cover entry-name/timestamp validation, traversal, symlinked trash and
entries, destination symlinks, nonregular/FIFO entries, mismatched IDs, unreadable JSON,
original-ID conflicts, new-ID copies, repeated failed ownership acquisition, stale lock diagnostics,
symlink lock refusal, stage/link/directory-sync failures and retention of original recovery data.
After an uncertain post-publication failure, a valid active project may already exist; the
original entry remains and the user is told to refresh before retrying.

The frontend cases check ordinary restore with active-list refresh, copy actions on conflict,
unreadable-entry visibility and a conflict arriving after listing. The real browser case restores,
copies and opens the model through the Projects interface. Existing editor undo/redo and conflict
cases continue to pass. API-only and served-client fixtures now use separate libraries; an old
“restart” test was changed into a genuinely sequential restart because overlapping ownership is
now intentionally rejected. Their original save/result assertions were retained.

Four added honest mutants remove OS acquisition, skip source-ID validation, replace no-overwrite
publication with overwriting replace, or unlink retained recovery data. They run focused tests
that exercise those rules. The unmodified scratch baseline must pass before kill counts count.

## Distribution artifacts

C1 uses `dist/c1/`, retaining B's existing `dist/` artifacts/evidence.

- `dist/c1/direct/mcda_studio-0.1.0-py3-none-any.whl`
- `dist/c1/from-sdist/mcda_studio-0.1.0-py3-none-any.whl`
- `dist/c1/mcda_studio-0.1.0.tar.gz`, `MANIFEST.sha256`
- `dist/c1/smoke-evidence/result.json` and browser exports/screenshots.

Direct/rebuilt wheel SHA-256:
`338d2e915193ad4a1e71da25293478c73c0d778f0a4d52a575246d13417fd1a8`.
Both routes have identical wheel bytes. These are dirty-working-tree development artifacts, not
published releases. Installed recovery screenshots were visually inspected. Installed smoke now checks second-owner refusal and Recently deleted restore
in addition to B's GUI/assets, example evaluation, export and fresh-process reopening guarantees.

## Remaining limitations and exit assessment

OS locks are advisory. External programs and older MCDA versions can bypass them; hostile
concurrent directory replacement is not isolated. Direct CLI protection applies to a previously
managed destination directory with its persistent marker. Initialise management before mixing
server/CLI writes; ordinary unrelated files remain ordinary. Do not delete/replace a live marker.
Direct ASGI ownership knows PID but may not know port. No network-filesystem or Windows guarantee.

Restoration requires same-filesystem hard-link and directory-sync support; it fails clearly
rather than using an overwriting fallback. An abrupt crash may leave hidden stage files, which
are not active projects; the original trash entry remains. No automated purge/recovery cleanup is
introduced. Hosted Linux execution remains pending.

C1 exit criteria are satisfied on the locally verified macOS scope, including the final artifact
recheck. Hosted Linux execution remains pending, not inferred from local results.
D1 Visible model is next and is not started here. C2 backup tooling, durable drafts, permanent deletion and
canvas remain separate.

## Final working-tree state

Original package B and planning work remains uncommitted alongside C1. The original B artifacts
in `dist/` were retained; C1 artifacts use `dist/c1/`. No numerical/domain/method/service code,
reference project JSON, contract-baseline fixture or frontend dependency lock was modified.

`git status --short` snapshot:

```text
 M CHANGELOG.md
 M README.md
 M docs/README.md
 M docs/api/contract.md
 M docs/api/openapi.json
 M docs/development/handover.md
 M docs/development/known-limitations.md
 M docs/development/testing.md
 M docs/development/validation.md
 M frontend/src/api/client.ts
 M frontend/src/api/schema.ts
 M frontend/src/api/types.ts
 M frontend/src/components/Dashboard.tsx
 M pyproject.toml
 M scripts/mutation_check.py
 M src/mcda_studio/api/app.py
 M src/mcda_studio/api/errors.py
 M src/mcda_studio/api/schemas.py
 M src/mcda_studio/cli.py
 M src/mcda_studio/storage/project_store.py
 M tests/api/test_api_contract.py
 M tests/api/test_api_projects.py
?? .github/
?? docs/design/live-model-canvas.md
?? docs/development/baseline-review-2026-10-26.md
?? docs/development/landscape-and-options.md
?? docs/development/library-recovery.md
?? docs/development/package-b-verification.md
?? docs/development/package-c1-verification.md
?? docs/development/plan-next-phases.md
?? examples/supplier_selection/README.md
?? frontend/e2e/recovery.spec.ts
?? frontend/src/components/RecentlyDeleted.tsx
?? frontend/tests/components/RecentlyDeleted.test.tsx
?? hatch_build.py
?? requirements/
?? scripts/build_release.py
?? scripts/smoke_browser.mjs
?? scripts/smoke_install.py
?? src/mcda_studio/runtime.py
?? src/mcda_studio/startup.py
?? src/mcda_studio/storage/library_lock.py
?? tests/api/test_api_recovery.py
?? tests/integration/test_library_coordination.py
?? tests/unit/test_recovery.py
?? tests/unit/test_runtime.py
```

