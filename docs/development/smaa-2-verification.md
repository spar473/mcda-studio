# SMAA-2: check record

**Date:** 30 October 2026, Pacific/Auckland. **Base:** `main` at `a1a7d11`, uncommitted working tree.
**Scope:** [SMAA-2](../design/smaa-2.md) as designed, with the owner's six accepted decisions:
stated ranges in an optional `smaa` section (schema version 3); fixed, unknown and rating-interval
weight uncertainty; independence plus shared draws; bulk evaluation with `math.fsum` near-ties;
exact enumeration for small discrete cases; class acceptability now. MAVT and sorting outputs are
unchanged.

## What changed

- **Domain:** `domain/uncertainty.py` (`SmaaModel`: four distribution kinds, cells, groups, shared
  draws, dependence); `Project.smaa` (optional, omitted when absent); `SCHEMA_VERSION` 3 with the
  identity migration 2 → 3, which refuses a version-2 file holding `smaa`; `SmaaResult`,
  `AcceptabilityEstimate`, `AlternativeAcceptability`, `InputToCheck`, `SmaaAnalysisRecord`.
- **Method:** `methods/smaa/` registers `smaa2` (`value_functions`, `swing_weights`,
  `acceptability`). Validation runs MAVT's checks, then 20 uncertainty rules (and the sorting
  rules when the project has classes), then parameters (`uncertainty`, `samples`, `seed`,
  `confidence`). The engine samples with `PCG64(seed)`, evaluates draws with MAVT's evaluators and
  weighting, sums in bulk and re-sums near-ties with `math.fsum`, enumerates small discrete cases
  exactly with fractions, counts ranks, sole and tied first and classes, and lists inputs to check.
  `intervals.py` gives Clopper–Pearson bounds from the regularised incomplete beta function.
- **Services and API:** a version-2 SMAA record builder; CSV tables `rank_acceptability`,
  `class_acceptability` and `inputs_to_check`; hidden-criterion checks read the project's leaves;
  `/evaluate` returns `SmaaResult` in the union; the record union uses a tagged callable
  discriminator (a plain `oneOf`); edit operations `set_smaa_model` and `clear_smaa_model`;
  removing an alternative or criterion prunes its stated uncertainty. OpenAPI and TypeScript
  types regenerated.
- **CLI:** `mcda uncertainty cell|group|share|clear`; `--samples`, `--seed` and `--uncertainty` on
  `evaluate`; an acceptability table, class table and inputs-to-check list under the label.
- **Frontend:** the Uncertainty editor tab; the Acceptability view (label, provenance, rank table
  with intervals, stacked bars, class table, inputs to check, reference ranking and notes); SMAA-2
  run settings in the analysis header as transient view parameters; the record check for SMAA
  records; `useMethodIssues` shared by the Classes and Uncertainty editors.
- **Tooling:** `scripts/byte_identity.py` also covers the sorting example and each method's
  declared CSV tables; a `SMAA` mutant group (12 backend, 3 frontend) with `--smaa-only`; two
  sorting mutants retargeted to lines this change touched; the browser model builder moved into
  `e2e/helpers.ts`.

## Checks

**Environment:** macOS 26.5.1 (arm64), Python 3.12.15, NumPy 2.5.4, Node 26.12.1, Google
Chrome 156.

| Check | Command | Before (`a1a7d11`) | After |
| --- | --- | --- | --- |
| Python tests | `.venv/bin/python -m pytest -q` | 815 passed | **903 passed**, 0 failed, 0 skipped (one upstream Starlette/httpx deprecation warning) |
| Ruff lint and format | `ruff check` / `ruff format --check` on `src tests scripts hatch_build.py` | Pass | Pass (113 files) |
| mypy `--strict` | `.venv/bin/mypy` | Pass (46 files) | Pass (51 files) |
| OpenAPI freshness | `scripts/export_openapi.py --check` | Pass | Pass (regenerated) |
| Acceptance demo | `scripts/acceptance_demo.py` | Pass | Pass |
| Acceptance evidence | `scripts/acceptance_evidence.py <new dir>` | Pass | Pass |
| Frontend gate | `npm --prefix frontend run check` | 338 Vitest | **347 Vitest**; TypeScript, ESLint, type freshness and build pass |
| Browser tests | `MCDA_PYTHON=… MCDA_CHROMIUM=… npm --prefix frontend run test:e2e` | 83 passed | **84 passed** (3.2 min) |
| Mutation check | `.venv/bin/python scripts/mutation_check.py` | 112 of 112 | **127 of 127 killed** (112 plus 15 SMAA); the unmutated copy passes |
| Timing | 10 000 draws, 50 × 40 performance fixture, ten uncertain cells, unknown top-level weights | — | median 0.27 s over five runs (first run 1.0 s) |

### MAVT and sorting byte identity

`scripts/byte_identity.py`, now covering the sorting example as well, hashed every output of the
four bundled examples under Base, each scenario and each explicit profile, with the code of
`a1a7d11` and with the new code: project bytes and fingerprints, validation, evaluation, records,
all-node sensitivity, probes, scenario comparison, previews, every export (JSON and each method's
CSV tables) and the HTTP bodies with their status. **All 565 outputs are byte-identical**,
including the record bodies under the new discriminator. The `MavtResult`, `MavtSortingResult`,
`AnalysisRecord` and `SortingAnalysisRecord` schemas are unchanged; `Project` gains the optional
`smaa` property, and the contract baseline was updated for exactly the two `Project` entries.

### New tests

86 Python tests, 9 Vitest cases and 1 browser case:

- **`tests/regression/test_smaa_reference.py` (45)** with **`smaa_oracle.py`**, plain Python checked
  in a clean interpreter to load no `mcda_studio` module: exact enumeration of a five-supplier case
  with a categorical cell, discrete cells and a shared draw (18 joint outcomes), and of a tie case,
  equal to the oracle's exact fractions for every rank, sole and tied first and class; sampled
  ties counted as competition ranks through the `fsum` path; the 3/7 case at five seeds
  (99.9 % intervals contain 4/7); intervals against exact binomial tails and SciPy to `1e-12` for
  every `k` of `n` = 1, 2, 7, 20; zero events with a non-zero upper bound, in the interval code and
  in a run.
- **`tests/unit/test_smaa.py` (31):** MAVT's checks first and unchanged; every validation code;
  local anchors and missing measurements still block; parameters; identical bytes for the same
  seed and different counts for another; each distribution sampled with its own shape (uniform,
  two triangulars, discrete); each run varying only its own inputs; a shared draw moving its cells
  together; the bulk path equal to a pure `fsum` path on all four examples; class and rank rows
  covering every draw; inputs to check labelled, and none (with a reason) for exact runs; the
  request limit; schema version 3 and byte-for-byte clearing; pruning on removal.
- **`tests/api/test_api_smaa.py` (10):** the union body with the label; the version-2 record and
  JSON export round trip with the digest recomputed; the three CSV tables; refusal of tables the
  run cannot fill; 422 `METHOD_NOT_SUPPORTED` for sensitivity, the probe and scenario comparison;
  previews still served; edit operations across schema versions; the CLI end to end, ending
  byte-identical to the starting file.
- **Vitest:** the Acceptability view (label, provenance, interval text, class table, inputs, bars,
  CSV tables, no MAVT views); the SMAA record check; run settings shown only for SMAA-2 and sent
  as view parameters; parameter merging in the context; the Uncertainty editor (distributions, a
  shared draw, rating intervals, labelled scales, invalid numbers, loading, removal, engine issues).
- **Browser (`frontend/e2e/smaa.spec.ts`):** a project built from blank in the GUI gets a range and
  unknown weights in the Uncertainty tab, is saved as version 3 with its method unchanged, shows
  the label and the engine's frequency and interval for Alpha, changes run without any edit, and
  exports the rank-acceptability CSV and a version-2 JSON.

**Existing tests changed,** because what they enumerate changed by design: the registered methods,
`/api/meta` and the unknown-method message (`test_api_method_seam.py`), `/api/health` and the save
route's version rule (`test_api_projects.py`), the edit-operation cases, the record schema test
(`test_api_sorting.py`, now a `oneOf`), the schema-version assertion (`test_schema_versions.py`),
the frontend `META` fixture, the method list and run-settings reset (`AnalysisControls.test.tsx`)
and the views-not-offered lines (`Sorting.test.tsx`). No assertion about an MAVT or sorting number
changed.

### Mutants

| Mutant | Killed by |
| --- | --- |
| Tied first places counted as sole first | tie cases |
| Near-ties never re-summed, so ties broken by position | sampled tie case |
| Triangular sampled as uniform | distribution shape cases |
| Seed ignored | seed case |
| Zero events get a zero upper bound, as a Wald interval would | zero-event cases |
| A performance run also varies the weights | run separation |
| Shared-draw cells keep their entered values | shared-draw case |
| Zero rating intervals not refused | validation cases |
| Unsupported dependence accepted | validation cases |
| A distribution may reach outside the domain | validation cases |
| Absent uncertainty section written as `null` | schema case |
| Section written as schema version 2 | schema case |
| Frontend: the Acceptability view drops its label | Acceptability test |
| Frontend: the record check accepts mismatched acceptabilities | record-check test |
| Frontend: run settings follow into another method | analysis-controls test |

**Found by the mutation runs and fixed in the tests or the harness, not the code:**

- *Shared-draw cells keep their entered values* first survived: the shared-draw test entered the
  same value for both cells, so cells left at their entered values also tied in every draw. The
  test now enters different values.
- *Sorting: absent section written as `null`* became invalid because a second `exclude_if` line
  appeared; it now targets the sorting field, and a matching SMAA mutant covers the new field.
- *V4 (records accept the wrong resolved profile)* became invalid because the record check's
  common fields were renamed when the SMAA branch was added; it was retargeted and is killed.
- Two sorting frontend mutants were retargeted to the lines this change rewrote (the method
  select now also clears run settings; the viewed parameters are merged).

## Acceptance

| Criterion | Result |
| --- | --- |
| The analytic two-weight case reproduces its crossover at 3/7 | Met (five seeds) |
| Enumerable cases match exactly | Met (exact fractions, equal to the oracle) |
| Zero observed events give a non-zero upper bound | Met |
| The same seed in the pinned environment gives identical output | Met (identical bytes) |
| Every output carries the label; nothing is called a probability of success | Met (result, CLI, GUI, exports) |
| MAVT and sorting outputs byte-identical | Met (565 outputs) |
| Full gate green; every new mutant killed | Met (127 of 127) |

## Behaviour changes

- `/api/health` reports schema version 3 and lists `smaa2`; `/api/meta` lists it with its tables.
- `PUT /api/projects/{id}` accepts declared versions up to 3.
- The record route's OpenAPI schema is a `oneOf` of the three record types instead of a
  `record_version` discriminator; the bodies are unchanged.
- MAVT and sorting Results name one more view they do not offer (Acceptability).
- Removing an alternative or criterion also removes its stated uncertainty.

## Not verified

- Hosted run 41036203183 (commit `10c4215`, 30 October 2026) passed every stage on Ubuntu 24.04:
  Python and contracts, the frontend and browser workflows, both distribution routes and the
  offline installed GUI smoke. The hosted mutation step runs only weekly or on demand.
- Identical streams across platforms or NumPy versions are not promised; results record the
  environment. Only this machine's environment was exercised.
- The installed-distribution smoke was not rerun locally (Playwright's bundled Chromium is not
  installed here); it passed on hosted CI (above).
- No human usability result is claimed; the fresh-user checkpoint is still pending.
