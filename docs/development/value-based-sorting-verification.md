# Value-based sorting and the rest of the method seam: check record

**Date:** 29 October 2026, Pacific/Auckland. **Base:** `main` at `c170610`, uncommitted working tree.
**Scope:** [value-based sorting](../design/value-based-sorting.md) as designed, with the owner's six
accepted decisions, and the parts of the [method seam](../design/method-seam.md) deferred to it
(§3 result union, §5 version-2 records and per-method exports, §6 schema-version rule, §7
frontend method view). Also the housekeeping folded into this change. Project schema version 2 is
added; MAVT outputs are unchanged.

## What changed

- **Domain:** `domain/sorting.py` (`SortingModel`, `SortingClass`, `SortingAudit`);
  `Project.sorting` (optional, omitted when absent); `SCHEMA_VERSION` 2 with
  `required_schema_version()` and a serializer that writes the lowest sufficient version; the
  identity migration 1 → 2, which refuses a version-1 file holding `sorting`. MAVT's result fields
  moved unchanged into `ValueModelResult`; new `MavtSortingResult`, class, assignment, audit and
  class-change types, `SortingSensitivityResult`, `SortingSensitivityProbe`, `RecordEnvelopeV2`,
  `SortingAnalysisRecord`, `AnalysisExportDocumentV2` and the unions.
- **Method:** `methods/sorting/` registers `mavt_sorting` (MAVT's six capabilities plus `classes`).
  Validation runs MAVT's checks unchanged, then twelve sorting codes, then parameters. Evaluation
  sorts a completed MAVT result. Sensitivity and the probe add exact class changes;
  `endpoint_values` is shared with the MAVT sweep, which computes the same expressions as before.
- **Services:** version-2 sorting records through `VERSION_2_RECORDS`, with the value-model context
  factored out of the version-1 builder; per-method CSV tables (`EXPORT_TABLES`), the sorting
  `ranking` columns and a `classes` table; edit functions `set_sorting_model`,
  `clear_sorting_model`, `sorting_classes` and `set_analysis_method`.
- **API:** unions on `/evaluate`, `/analysis/record`, `/analysis/export`, `/sensitivity` and the
  probe; three edit operations; `/api/meta` methods gain `export_tables`; `PUT` accepts any
  version from what the content needs up to the newest; `/api/health` reports schema version 2.
  OpenAPI and TypeScript types regenerated.
- **CLI:** `mcda classes set|audit|clear`, `mcda method`, `--method` on `evaluate`, `sensitivity`
  and `compare`; class columns and a class-change table; `mcda validate` adds the saved method's
  own issues when it is not MAVT.
- **Frontend:** Method select and **Use viewed method as saved default** in the analysis header;
  `results/panels.ts`; Classes view in Results; Classes editor tab; class bands on the ranking and
  sensitivity charts; class-change table and probe classes in Sensitivity; version-2 record checks;
  swing-review identity limited to scenario and profile.
- **Example:** `examples/supplier_qualification/` (build script, README, project file), bundled in
  the wheel, the release check, the installed smoke and the acceptance evidence.
- **Tooling:** `scripts/byte_identity.py`; a `SORTING` mutant group (12 backend, 6 frontend) with
  `--sorting-only`; the seam's sensitivity mutant retargeted to the moved line.
- **Housekeeping:** GitHub Actions pinned to `checkout` v7.0.1, `setup-python` v7.1.0,
  `setup-node` v7.1.0 and `upload-artifact` v7.0.2, all running on Node 24 (the last hosted run
  warned that the v4/v5 actions targeted Node 20); `test_workflow.py` and `test_runtime.py` made
  independent of terminal width; the seam record notes hosted run 40679505555.

## Checks

**Environment:** macOS 26.5.1 (arm64), Python 3.12.15 in the project `.venv`, Node 26.12.1, Google
Chrome 156.

| Check | Command | Before (`c170610`) | After |
| --- | --- | --- | --- |
| Python tests | `.venv/bin/python -m pytest -q` | 731 passed | **815 passed**, 0 failed, 0 skipped (one upstream Starlette/httpx deprecation warning) |
| Ruff lint and format | `ruff check` / `ruff format --check` on `src tests scripts hatch_build.py` | Pass | Pass (104 files) |
| mypy `--strict` | `.venv/bin/mypy` | Pass (42 files) | Pass (46 files) |
| OpenAPI freshness | `scripts/export_openapi.py --check` | Pass | Pass (regenerated) |
| Acceptance demo | `scripts/acceptance_demo.py` | Pass | Pass |
| Acceptance evidence | `scripts/acceptance_evidence.py <new dir>` | Pass | Pass (now hashes four example files) |
| Frontend gate | `npm --prefix frontend run check` | 313 Vitest | **338 Vitest** (337 at `d5e2d20`, plus one added for a surviving mutant); TypeScript, ESLint, type freshness and build pass |
| Browser tests | `MCDA_PYTHON=… MCDA_CHROMIUM=… npm --prefix frontend run test:e2e` | 81 passed | **83 passed** (3.0 min) |
| Mutation check | `.venv/bin/python scripts/mutation_check.py` | 94 of 94 | **112 of 112 killed** after the follow-up (the first run at `d5e2d20`: 109 of 112, see Mutants); the unmutated copy passes |
| Installed distribution | `build_release.py --skip-frontend`, `smoke_install.py --browser --wheelhouse …` | Not rerun locally for the seam | **Not completed:** both archives built; the browser stage stopped because Playwright's own Chromium is not installed on this machine |
| CLI width sweep | the CLI test files at `COLUMNS` 40 to 120 in steps of 4 (21 widths) | 5 failures at 40, 1 at 44–60 | All pass at every width |

### MAVT byte identity

`scripts/byte_identity.py` hashed every MAVT output of the three bundled examples under Base, each
scenario and each explicit profile, once with the code of `c170610` (extracted with `git archive`)
and once with the new code, both imported from their own `src`. The outputs: the stored file, the
re-saved project and its saved bytes, the fingerprint, project-wide and effective validation, the
CLI's `evaluate --json`, evaluation, the version-1 record, all-node sensitivity, a probe, scenario
comparison, the weight preview, every leaf's value-function preview, the JSON export and all five
CSV tables, and the HTTP bodies (with status) of `/validate`, `/evaluate`, `/analysis/record`,
`/analysis/validate`, `/sensitivity`, the probe, `/scenarios/compare`, both previews and every
export. **All 410 outputs are byte-identical.**

The OpenAPI schemas of `MavtResult`, `SensitivityResult`, `SensitivityProbe`, `AnalysisRecord` and
`AnalysisExportDocument` are unchanged. `Project` gains the optional `sorting` property; in the
response schema `schema_version` no longer advertises a default, because the server now always
computes it. The contract baseline was updated for exactly these two `Project` entries and the new
example's hash, as a reviewed change.

### New tests

84 Python tests, 25 Vitest cases (24 at `d5e2d20`, one added in the follow-up) and 2 browser cases:

- **`tests/unit/test_sorting.py` (39):** the boundary rule at, `2τ` above and below, and within `τ`
  of each boundary; class summaries, empty and single classes; nearest boundary and ties; every
  validation code, including boundaries exactly representable either side of `2e-12`
  (`2⁻³⁹`, `2⁻³⁸`); out-of-order boundaries refused, never reordered; MAVT checks first and
  unchanged; the anchor warning for a scenario only when viewed; the audit sample (seed-keyed,
  order-independent, whole and empty pool); every MAVT field carried over on all three MAVT
  examples; MAVT ignoring the section; the saved-method edit.
- **`tests/unit/test_schema_versions.py` (8):** MAVT-only projects migrate and re-save as version 1
  with identical bytes and an unchanged fingerprint; classes make version 2 and clearing them
  restores the original bytes and fingerprint; results report the needed version; a version-1 file
  holding `sorting` is refused; a version-1 program refuses a version-2 file with its existing
  message; a declared version above what the content needs is written lower.
- **`tests/unit/test_sorting_sensitivity.py` (5):** hand-derived change weights on a two-option
  model; every change point of the example against `brentq` on the independent probe path and the
  probed class `1e-9` either side; first changes bracketing the baseline; the
  baseline-on-boundary warning; MAVT fields unchanged and no sorting keys on MAVT bodies.
- **`tests/properties/test_sorting_properties.py` (3):** monotone in value; the best boundary
  reached; classes and the audit sample independent of alternative order.
- **`tests/regression/test_supplier_qualification.py` (15)** with **`sorting_oracle.py`**, a
  plain-Python oracle that reads the project JSON and is checked in a clean interpreter to load no
  `mcda_studio` module: the shipped file equals its build script; values, classes, distances and the
  audit sample under Base, the cost-focused profile and the scenario; the documented classes; a
  boundary placed at each supplier's own value and `±0.5τ`, `±2τ` from it; every class-change
  weight of every criterion in all three contexts (to `1e-12`).
- **`tests/api/test_api_sorting.py` (11):** the result union and an unchanged MAVT body; tagged
  unions in OpenAPI; the version-2 record and JSON export round trip with the digest recomputed;
  version 1 kept for MAVT; sorting CSV columns and the `classes` table; refusal of `classes` for
  MAVT; sorting sensitivity and probe bodies; edit operations across schema versions; the
  saved-method operation; a stored sorting project; the CLI end to end, ending byte-identical to
  the starting file.
- **`tests/api/test_api_editing.py` (+3):** each new operation equals the service call.
- **Vitest:** the panel registry; sorting Results (classes, assignments, audit sample, band
  positions, CSV tables) and MAVT's "does not offer" line; record checks by version and class
  integrity; the method view (parameters, keys, swing review, no edit, one undo step that leaves
  the view alone); the analysis controls; the Classes editor (apply, reorder without sorting,
  invalid numbers, cancel, audit, remove, engine issues); sorting sensitivity bands, markers, the
  class-change table and probe classes.
- **Browser (`frontend/e2e/sorting.spec.ts`):** a project built from blank in the GUI gets two
  classes through the Classes tab, shows them in Results, reads the exact class-change weights in
  Sensitivity against the engine, and exports a version-2 JSON and the class columns in CSV; the
  qualification example opens as sorting, can be viewed as MAVT with no edit and no change to the
  stored bytes, and "use as saved default" is undone in one step.

**Existing tests changed,** because what they enumerate changed by design: the registered-method
and `/api/meta` lists and the unknown-method message (`test_api_method_seam.py`), `/api/health`'s
schema version and methods, and the save route's version rule (`test_api_projects.py`), the
migration test's in-memory version (`test_storage.py`), the edit-operation cases
(`test_api_editing.py`), and the frontend `META` fixture. The housekeeping changed two CLI test
files to match on collapsed whitespace and render tables at a fixed width. No assertion about an
MAVT number changed.

### Mutants

All new mutants are in the `SORTING` group (`--sorting-only`).

| Mutant | Killed by |
| --- | --- |
| `<=` at a boundary, so a value on it goes to the lower class | boundary-rule cases |
| Class order inverted | class summaries, oracle |
| Class-change root with the wrong sign | hand-derived roots, oracle |
| A version-2 record written for MAVT | MAVT record and export tests |
| Schema version written too high (always the newest) | schema-version tests |
| Absent sorting section written as `null` | schema-version tests |
| Out-of-order boundaries accepted | validation cases |
| Audit pool includes the cut-off class | audit sample tests |
| Local-anchor warning never raised | anchor warning tests |
| A version-1 file holding `sorting` accepted | schema-version tests |
| A new saved method keeps the old parameters | saved-method tests |
| CLI shows the class above for a change below | CLI test |
| Frontend: panel registry ignores capabilities | registry test |
| Frontend: Classes panel registered for MAVT | registry test |
| Frontend: method view writes the saved default | analysis-controls test |
| Frontend: viewed method reuses the saved parameters | method-view test |
| Frontend: record check accepts any version | record-check test |
| Frontend: Sensitivity shows the class above for a change below | sorting sensitivity test |

**First full run and follow-up.** The first full run, on the code committed as `d5e2d20`, killed
109 of 112. Two new frontend mutants survived, through weak tests rather than wrong code:

- *Viewed method reuses the saved parameters:* the method-view test used
  `toMatchObject({ parameters: {} })`, which matches any parameters object. It now requires the
  parameters to equal `{}`.
- *Record check accepts any version:* every refused record also failed the method check, so the
  version check was never the only guard tested. A new case relabels a record's method so that only
  its version is wrong, both ways.

The existing mutant V12 (path shares replaced by local weights) was invalid, because the record
refactor moved its target line; it was retargeted to the new line. Engine and frontend code are
unchanged by the follow-up. The `--sorting-only` group then killed 18 of 18, the results group 5
of 5 (V12 included), and a second full run 112 of 112.

The seam's deferred mutants are covered: a version-1 MAVT record written as version 2, an absent
section written as `null`, and the lowest-sufficient rule replaced by "always the newest".

## Acceptance

| Criterion | Result |
| --- | --- |
| Classes match the oracle at, just above and just below every boundary, including the tolerance band | Met |
| Empty and single classes are valid; invalid boundaries refused clearly and never reordered | Met |
| Class-change points match exact roots, and the class on each side agrees with direct evaluation | Met (oracle to 1e-12; `brentq` and probes) |
| MAVT results, records, exports, project bytes and fingerprints byte-identical on all three examples, Base and every scenario | Met (410 outputs) |
| The three existing fixtures byte-unchanged; the new example identical through CLI and GUI | Met (contract baseline hashes; CLI and browser tests) |
| Version-2 round trip and schema-writing tests | Met |
| GUI case from blank to export | Met (browser case) |
| Full gate green; every new mutant killed | Met (112 of 112 after the follow-up) |

## Behaviour changes

- `/api/health` reports `schema_version` 2 and lists `mavt_sorting`; `/api/meta` lists it with
  `export_tables` for every method.
- `PUT /api/projects/{id}` now accepts a body declaring any version from what its content needs up
  to 2, and stores it at the lowest sufficient version. A body declaring 2 for an MAVT-only project
  used to be refused and is now stored as version 1.
- A version-1 file containing `sorting` is refused on load. The in-memory `schema_version` of a
  loaded project is what its content needs (1 for every existing project), where it used to be the
  file's.
- An unknown-method message lists `mavt, mavt_sorting`.
- The Results workspace for MAVT shows one extra line naming the views MAVT does not offer
  (Classes). The analysis header gains a Method select.
- Viewing another profile or scenario still asks for a swing review when ranges change; viewing
  another method no longer would.
- `mcda validate` on a project whose saved method is not MAVT also reports that method's issues.

## Not verified

- Hosted run 40860274947 (commit `d5e2d20`, 29 October 2026) passed every stage on Ubuntu 24.04,
  including the browser tests, both distribution routes and the offline installed GUI smoke, with
  the Node 24 action versions and no deprecation annotation. Hosted run 41005422053 (commit
  `a1a7d11`, the mutant follow-up) passed every stage too. The hosted mutation step runs only
  weekly or on demand.
- The installed-distribution smoke did not complete locally: `smoke_browser.mjs` needs Playwright's bundled Chromium, which is not installed here. It passed on hosted CI (above).
- No human usability result is claimed; the fresh-user checkpoint is still pending.
- Classes are not compared between Base and a scenario (a stated non-goal).
