# Method seam (backend contract): check record

**Date:** 28 October 2026, Pacific/Auckland. **Base:** `main` at `508f49b`, uncommitted working tree.
**Scope:** the backend contract of the [method seam](../design/method-seam.md) (§1, §2, §4 and §8),
with the owner's four accepted decisions. The result union, version-2 records, the schema-version
rule and the frontend method view arrive with value-based sorting (see the note's implementation
notes). No project-schema, numerical or dependency change; the API adds `methods` to `/api/meta`
and replaces the unreachable 501 with 422.

## What changed

- **`methods/base.py`:** the closed `Capability` vocabulary; the `Method` protocol gains `label`,
  `capabilities` and `validate`; `validate_analysis` (method-independent checks, then the method's
  own; `UNKNOWN_METHOD` for an unregistered name); `require_capability`; `require_record_v1`;
  `check_parameters`; `unregister` for tests.
- **MAVT:** `MavtMethod` declares its label and six capabilities. Its validation is the former
  effective-model validation, renamed `validate_value_model` and moved behind the method whole and
  in order, plus parameter checks. `MavtParameters` reads `dominance_check` as a strict boolean;
  aggregation and analysis records read it through that model.
- **Services:** sensitivity (sweep, all nodes, probe), scenario comparison and both previews check
  a capability; version-1 analysis records and exports require MAVT. The CLI and API share these
  checks.
- **Previews:** no longer refuse every method but `mavt` themselves (a sixth hard-wired place,
  found during implementation); an unknown method is still `UNKNOWN_REFERENCE`.
- **API:** `MethodNotSupportedError` maps to 422 `METHOD_NOT_SUPPORTED` with one detail naming
  the method, the requirement and its capabilities. `/evaluate` uses it instead of 501.
  `/api/meta` gains `methods`. OpenAPI and generated TypeScript types regenerated; the frontend
  test fixture gains the field.
- **Mutation harness:** a `SEAM_BACKEND` group (8 mutants), its runner and a `--seam-only` flag.
- **Docs:** design note status and implementation notes, API contract, project schema
  (analysis parameters), architecture overview (extending with a method), roadmap, testing,
  handover, validation, README and changelog.

## Checks

**Environment:** as in the [library backup record](library-backup-verification.md): macOS 26.5.1
(arm64), Python 3.12.15 in the project `.venv`, Google Chrome 156.

| Check | Command | Before (`508f49b`) | After |
| --- | --- | --- | --- |
| Python tests | `.venv/bin/python -m pytest -q` | 700 passed | **731 passed**, 0 failed, 0 skipped (one upstream Starlette/httpx deprecation warning) |
| Ruff lint and format | `ruff check` / `ruff format --check` on `src tests scripts hatch_build.py` | Pass | Pass (92 files) |
| mypy `--strict` | `.venv/bin/mypy` | Pass (41 files) | Pass (42 files) |
| OpenAPI freshness | `scripts/export_openapi.py --check` | Pass | Pass (regenerated: `MethodInfo`, `Meta.methods`) |
| Acceptance demo | `scripts/acceptance_demo.py` | Pass | Pass |
| Acceptance evidence | `scripts/acceptance_evidence.py <new dir>` | Pass | Pass |
| Frontend gate | `npm --prefix frontend run check` | 313 Vitest | **313 Vitest**; TypeScript, ESLint, type freshness and build pass |
| Browser tests | `MCDA_PYTHON=… MCDA_CHROMIUM=… npm --prefix frontend run test:e2e` | 81 passed | **81 passed** (4.4 min) |
| Mutation check | `.venv/bin/python scripts/mutation_check.py` | 86 of 86 | **94 of 94 killed** (86 plus 8 seam); the unmutated copy passes |

Every pre-existing test passes unchanged. The Python count rises by 31, all in
`tests/api/test_api_method_seam.py`.

### MAVT byte identity

A script evaluated every MAVT output for the three bundled examples, under Base and each
scenario, first with the code at `508f49b` and then with the new code (both imported from the
repository's `src`): project bytes and fingerprint, project-wide and effective validation,
evaluation, the analysis record, every export table as JSON and CSV, all-node sensitivity,
scenario comparison, the weight preview, every leaf's value-function preview and a probe. **All
164 outputs are byte-identical.**

### New tests

`tests/api/test_api_method_seam.py` registers a test-only fake method for one test at a time:

- **Declarations:** MAVT's label and exact capabilities; `/api/meta` lists MAVT, then the fake.
- **Gated routes**, each of sensitivity, probe, scenario comparison, value-function preview and
  weight preview: refused with the exact 422 body for a method lacking only that capability;
  served for a method declaring only it; served for MAVT.
- **Refusals:** `/evaluate` for a result without an API model; `/analysis/record` and
  `/analysis/export` for any method but MAVT; the CLI's `sensitivity --all` on a saved fake method.
- **Validation dispatch:** the fake's own issue replaces MAVT's checks on an incomplete project;
  duplicate profile IDs are still reported first; an unregistered method yields exactly
  `UNKNOWN_METHOD`, fails a gated route as `VALIDATION_FAILED` and `/evaluate` as
  `UNKNOWN_REFERENCE`, as before.
- **Parameters:** an unknown key adds exactly one `UNKNOWN_PARAMETER` warning after the unchanged
  report and leaves the ranking unchanged; `"no"`, `0`, `1`, `null` and `[true]` for
  `dominance_check` are each `INVALID_PARAMETER`; `true` equals the default and `false` disables
  dominance in records, on two examples.

### Mutants

| Mutant | Killed by |
| --- | --- |
| The capability check never refuses | gated-route refusals |
| Validation always runs MAVT's checks | validation dispatch |
| A version-1 record is built for any method | record and export refusals |
| Unknown parameters are silently ignored | unknown-parameter warning |
| `dominance_check` accepts loosely typed values | invalid-parameter cases |
| Sensitivity skips its capability check | sensitivity refusal |
| The weight preview skips its capability check | weight-preview refusal |
| An unsupported method maps to a generic 400 | exact 422 body |

## Acceptance (this part)

| Criterion | Result |
| --- | --- |
| MAVT results, records, exports, project bytes and fingerprints byte-identical on all three examples | Met (164 outputs) |
| Every existing test passes unchanged | Met |
| Each capability-gated route returns a typed 422 for a method without the capability | Met |
| MAVT validation codes, paths and messages unchanged | Met (moved whole; byte-identical reports) |
| Validation dispatches to the method; `UNKNOWN_METHOD` covers unregistered names | Met |
| Full gate green; all new mutants killed | Met |
| Fake method round-trips through a version-2 record and export | Deferred with version-2 records (sorting) |

## Behaviour changes

- A project naming an unregistered method reports `UNKNOWN_METHOD` instead of
  `UNSUPPORTED_METHOD`; a preview for it says "unknown MCDA method" instead of "previews support
  'mavt'". Both stay 422 with the same codes as before.
- A non-boolean `dominance_check` was read by truthiness; it is now an `INVALID_PARAMETER` error.
  An unknown parameter now adds a warning to the report and to result diagnostics. No bundled
  example has either.

## Not verified

- The installed-distribution smoke was not rerun locally. Hosted run 40679505555 (commit
  `c170610`, 29 October 2026), including the installed-distribution stage, passed.
- No second real method exists yet; the fake method stands in for it.
- No human usability result is claimed.
