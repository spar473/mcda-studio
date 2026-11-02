# Testing and quality gates

Every change should pass the full gate below before it is merged. Results of the latest run are in
[validation](validation.md).

## One-time setup

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements/build-py312.txt -r requirements/dev-py312.txt
.venv/bin/python -m pip install --no-deps --no-build-isolation -e '.[dev]'
npm --prefix frontend ci
cd frontend && npx playwright install chromium && cd ..   # or set MCDA_CHROMIUM to an installed Chrome
```

## The full gate

Run these from the repository root:

```sh
.venv/bin/python -m pytest -q                       # Python: unit, API, integration, property, regression
.venv/bin/ruff check src tests scripts hatch_build.py              # lint
.venv/bin/ruff format --check src tests scripts hatch_build.py     # formatting
.venv/bin/mypy                                      # strict typing of src/
.venv/bin/python scripts/export_openapi.py --check  # committed OpenAPI is current
.venv/bin/python scripts/acceptance_demo.py         # save, reopen in a fresh process, reproduce
.venv/bin/python scripts/acceptance_evidence.py /tmp/mcda-evidence   # oracles, reconciliation, timings
npm --prefix frontend run check                     # tsc, ESLint (0 warnings), type freshness, Vitest, build
MCDA_PYTHON="$PWD/.venv/bin/python" npm --prefix frontend run test:e2e   # Playwright browser tests
.venv/bin/python scripts/mutation_check.py          # every applicable injected defect must be caught
```

The Python suite now includes independent localhost servers and forced-termination tests, all on
temporary libraries. A sandbox must permit localhost/process execution; do not skip those cases
and call the full gate passed.

The browser tests and the mutation check take a few minutes each. Run them one at a time.

### Environment notes

- **Use the virtualenv path exactly as written** (`.venv/bin/python`). Resolving its symlink can
  pick a different Python that lacks the dependencies.
- **Browser tests use a throwaway store**, `frontend/.e2e-store`, on port 8799 (override with
  `MCDA_E2E_PORT`). Never point them at a real project library.
- **Use an installed Chrome** by setting `MCDA_CHROMIUM`, for example
  `'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'` on macOS.
- **Rebuild and restart after code changes.** Rebuild `frontend/dist` before checking the production
  build by hand, and restart any running `mcda serve`.

## What each suite covers

| Suite | Location | Covers |
| --- | --- | --- |
| Unit | `tests/unit/` | Value functions, weighting, aggregation, validation (including failure cases), sensitivity and probes, previews, swing ranges, profiles, scenarios, analysis records, store, storage and library backup archives |
| API | `tests/api/` | Every endpoint, error envelopes, edit operations against the service layer (identical results), contract freshness, exports |
| Integration | `tests/integration/` | Create → modify → save → load → evaluate, a CLI-only model build, fresh-process reproduction |
| Property | `tests/properties/` | Hypothesis tests of invariants on generated models |
| Regression | `tests/regression/` | The VC, supplier, supplier qualification and infrastructure examples against independent oracles; `sorting_oracle.py` recomputes classes, distances, the audit sample and class-change weights, `smaa_oracle.py` exact SMAA-2 enumerations and intervals, `promethee_oracle.py` exact PROMETHEE II flows, relations and flow-gap splits, `ahp_oracle.py` exact AHP priorities, consistency, triads and both syntheses, from the project JSON, `comparison_oracle.py` each method's own cells and the agreement, from each method's own `/evaluate` body, and `feasibility_oracle.py` every requirement's status and reason class, each overall status and every validation code, from the project JSON |
| Frontend | `frontend/tests/` | Pure model helpers, the editor store, analysis-context and request hooks, components, results |
| Browser | `frontend/e2e/` | Real-backend GUI workflows (see the [frontend README](../../frontend/README.md#end-to-end-tests)) |
| Mutation | `scripts/mutation_check.py` | That the suites detect every applicable injected defect; dated records give actual counts |

## Rules for tests

The partial evidence and decision-record CLI foundation has focused checks:

```sh
.venv/bin/python -m pytest -q tests/unit/test_evidence.py tests/unit/test_decision_record.py
```

See the [synthetic demonstrations](../../examples/evidence_demo/README.md) for a reproducible
preview, compilation and decision snapshot in both domains. These examples are checkout-only.

The deterministic calculation foundation and its independent rational demo oracles are exercised by:

```sh
.venv/bin/python -m pytest -q tests/unit/test_derived.py tests/api/test_api_derived.py tests/regression/test_derived_reference.py
.venv/bin/python scripts/mutation_check.py --derived-only --backend-only
```

The integrated evidence workspace and calculation exports add these focused gates:

```sh
.venv/bin/python -m pytest -q tests/unit/test_evidence_workspace.py tests/api/test_api_evidence.py tests/unit/test_derived_compilation.py
.venv/bin/python scripts/mutation_check.py --evidence-workspace-only
.venv/bin/python scripts/mutation_check.py --derived-only
```

Graphical evidence compilation, compilation bundles and separate-copy receipts add:

```sh
.venv/bin/python -m pytest -q tests/unit/test_evidence_compilation.py tests/unit/test_provenance.py tests/api/test_api_evidence_compilation.py
MCDA_PYTHON="$PWD/.venv/bin/python" npm --prefix frontend run test:e2e -- e2e/evidence-compilation.spec.ts e2e/derived-measurements.spec.ts
```

`--evidence-workspace-only` also runs the `EVIDENCE` compilation and `PROVENANCE` mutants. See the
[evidence compilation record](evidence-compilation-verification.md).

Version-2 decision records add:

```sh
.venv/bin/python -m pytest -q tests/unit/test_decision_record_v2.py tests/unit/test_decision_record.py tests/api/test_api_decisions.py
MCDA_PYTHON="$PWD/.venv/bin/python" npm --prefix frontend run test:e2e -- e2e/decision-records.spec.ts
.venv/bin/python scripts/mutation_check.py --decision-only
```

See the [decision records record](decision-records-verification.md).

The calculation workspace adds:

```sh
.venv/bin/python -m pytest -q tests/unit/test_calculation_workspace.py tests/regression/test_calculation_workspace_reference.py tests/api/test_api_calculations.py
MCDA_PYTHON="$PWD/.venv/bin/python" npm --prefix frontend run test:e2e -- e2e/calculation-workspace.spec.ts e2e/derived-measurements.spec.ts
.venv/bin/python scripts/mutation_check.py --calculation-only
```

The isolated factor-uncertainty evaluator adds:

```sh
.venv/bin/python -m pytest -q tests/regression/test_factor_uncertainty_reference.py
.venv/bin/python scripts/mutation_check.py --uncertainty-only --backend-only
```

The integrated factor runs add:

```sh
.venv/bin/python -m pytest -q tests/regression/test_factor_analysis_reference.py tests/api/test_api_factor_uncertainty.py
MCDA_PYTHON="$PWD/.venv/bin/python" npm --prefix frontend run test:e2e -- e2e/factor-uncertainty.spec.ts
.venv/bin/python scripts/mutation_check.py --uncertainty-only --backend-only
```

The uncertainty group includes the existing sampler and new integration mutations. See the
[factor integration record](factor-uncertainty-integration-verification.md) for actual counts,
near-tie oracles, supported combinations and previous-output byte identity.

See the [integrated sprint record](integrated-workspace-verification.md) for final combined
counts, local/hosted distinctions and the pending independent-user protocol. Review exports
reopen original inputs and appended history; calculation bundles reconstruct compilation before
previewing. Browser tests also exercise both domain examples without changing the source project.

The [calculation demonstrations](../../examples/derived_measurements/README.md) include a reproducible
CLI procedure and a fresh-user protocol. They are checkout-only; no human checkpoint has run.

- **Independent oracles stay independent.** Oracle code in the regression tests must not import
  `mcda_studio`.
- **Never loosen a tolerance or an assertion** to get a pass. If a number changes, find out why.
- **Generated files must match their generators:**
  - Each `examples/*/project.json` must equal what its `build.py` writes.
  - `tests/fixtures/performance_project.json` must equal what
    `scripts/build_results_performance_fixture.py` writes.
  - `docs/api/openapi.json` must match the app, and `frontend/src/api/schema.ts` must match that
    document.
  - `tests/fixtures/contract_baseline.json` pins schemas and example hashes. Update it only for a
    deliberate, reviewed change.
- **Mutants must be honest.** A new mutant must be reachable and must fail the suite it targets.
  Report equivalent or unreachable mutants instead of counting them as killed.

## External proposals

```sh
.venv/bin/python -m pytest -q tests/unit/test_external_proposals.py tests/properties/test_proposal_properties.py tests/regression/test_external_proposals_reference.py tests/api/test_api_proposals.py
.venv/bin/python scripts/export_proposal_schemas.py --check
.venv/bin/python scripts/export_proposal_test_fixtures.py --check
MCDA_PYTHON="$PWD/.venv/bin/python" npm --prefix frontend run test:e2e -- e2e/external-proposals.spec.ts
.venv/bin/python scripts/mutation_check.py --proposals-only
```

The new group covers mandatory review, original preservation, fingerprint binding, source and
model-card checks, single-cell selection, confidence isolation, CSV atomicity, registry immutability,
compilation acknowledgements, blocked bulk selections and late replies. Bulk properties compare
accepted, corrected and rejected event sequences byte for byte with individual reviews. Demo
rebuilds use temporary directories, never change reference files during a mutation run, and use
only invented inputs. Published schemas and Python-generated component snapshots are checked by
the regression suite. Existing project/result schemas and byte baselines remain pinned.

## Regenerating generated files

```sh
.venv/bin/python examples/nz_deeptech_vc/build.py
.venv/bin/python examples/supplier_selection/build.py
.venv/bin/python examples/infrastructure_procurement/build.py
.venv/bin/python scripts/build_results_performance_fixture.py
.venv/bin/python scripts/export_openapi.py
npm --prefix frontend run gen:types
```

## Distribution build and clean install

Use Python 3.12 with the build lock installed, plus Node for preparing GUI assets. Build tooling
is part of this package, not a precondition for the earlier application-test record. See
[dependency locks](../../requirements/README.md) for their scope and regeneration.

```sh
.venv/bin/python scripts/build_release.py
# Or, after npm ci and npm run build: append --skip-frontend
.venv/bin/python -m pip download --require-hashes --only-binary=:all: -r requirements/runtime-py312.txt -r requirements/build-py312.txt --dest /tmp/mcda-wheels
MCDA_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' .venv/bin/python scripts/smoke_install.py --browser --wheelhouse /tmp/mcda-wheels
```

On Linux omit `MCDA_CHROMIUM` after installing Playwright Chromium as above. These scripts use
POSIX venv paths on the two scoped platforms; Windows is not claimed. Never use a real library.

`build_release.py` normally runs `npm ci` and the frontend build. It then builds a direct wheel
and an sdist, extracts the sdist outside the checkout, and builds its wheel with no build isolation
or index access. The build lock supplies the backend; no Node/frontend generation occurs during
sdist rebuilding. Archive inspection checks GUI assets, examples and metadata; a negative build
with the GUI removed must fail. Output: `dist/direct/`, `dist/from-sdist/`, sdist and `MANIFEST.sha256`.
No command uploads or publishes anything.

`smoke_install.py` creates fresh venvs outside the checkout, clears source/resource overrides,
checks the installed module path, installs the runtime lock and each local wheel with `[api]`,
starts a disposable localhost server, loads index/JS/CSS, opens the VC example through the GUI,
compares full-precision values to the reference numbers, downloads analysis JSON, re-evaluates
its exported project and restarts the server to reopen its library. It also tests a plain
engine-only wheel and the exact consumer `pipx install '/path/to/wheel.whl[api]'` route with an
isolated pipx home/bin directory. Browser mode drives that pipx GUI too. Temporary installs,
servers and stores are cleaned up; evidence is copied to `dist/smoke-evidence/`.

Without `--browser` only HTTP/CLI checks run; do not call that a browser/GUI acceptance pass.
Subprocess failures retain diagnostic output. Use `--dist <directory>` to keep a different output
root; the scripts never resolve frontend assets from the checkout on behalf of the installed app.

Linux CI (`.github/workflows/ci.yml`) runs Python 3.12 and Node 26.12.1, the application gate,
archive paths and installed GUI smoke. Mutation checks run manually/weekly. CI configuration is
not evidence of an actual hosted run until pushed/executed; the installation check record shows
what was actually run. Platform expansion needs its own deliberate scope.

## Library ownership and recovery checks

See [ownership and manual recovery](library-recovery.md) and [actual results](package-c1-verification.md).
Focused commands:

```sh
.venv/bin/python -m pytest -q tests/unit/test_recovery.py tests/api/test_api_recovery.py tests/integration/test_library_coordination.py
```

The process suite tests two independent servers, separate libraries, normal/abrupt shutdown,
managed CLI protection, interrupted restore before/after publication and the stopped-library
backup drill. API/unit cases cover traversal, symlinks, FIFOs, ID conflicts/mismatches, unreadable
entries and injected publication failures. The frontend adds Recently deleted component cases
and `frontend/e2e/recovery.spec.ts`. Four added mutants remove ownership, ID validation,
no-overwrite publication or recovery retention; unmodified baselines must still pass.

Library backup and restore have their own suite and mutant group:

```sh
.venv/bin/python -m pytest -q tests/unit/test_library_backup.py tests/integration/test_library_coordination.py
.venv/bin/python scripts/mutation_check.py --backend-only --backup-only
```

The unit suite covers round trips (bytes, fingerprints, modification times and Recently deleted),
skipped and unreadable files, every hostile-archive case (names, duplicates, symlink, encrypted and
unknown-compression members, header mismatches, manifest mismatches, changed bytes), each size
limit, existing targets, injected restore failures, the incomplete-restore guard and exit codes.
The process test refuses a backup while a real server owns the library, then round-trips through
the commands and a restarted server. Eleven `BACKUP_BACKEND` mutants remove one guard each.

The method seam's rules are in `tests/api/test_api_method_seam.py`, which registers a test-only
fake method per test; eight `SEAM_BACKEND` mutants remove one guard each:

```sh
.venv/bin/python -m pytest -q tests/api/test_api_method_seam.py
.venv/bin/python scripts/mutation_check.py --backend-only --seam-only
```

Value-based sorting and the seam's schema rule have their own suites and a `SORTING` group of 12
backend and 6 frontend mutants:

```sh
.venv/bin/python -m pytest -q tests/unit/test_sorting.py tests/unit/test_sorting_sensitivity.py \
  tests/unit/test_schema_versions.py tests/properties/test_sorting_properties.py \
  tests/regression/test_supplier_qualification.py tests/api/test_api_sorting.py
.venv/bin/python scripts/mutation_check.py --sorting-only
```

SMAA-2 has its own suites and a `SMAA` group of 12 backend and 3 frontend mutants. Its oracle,
`tests/regression/smaa_oracle.py`, enumerates discrete cases with exact fractions and computes
Clopper–Pearson bounds from exact binomial tails; the reference tests also compare the intervals
with SciPy and reproduce the analytic 3/7 case:

```sh
.venv/bin/python -m pytest -q tests/unit/test_smaa.py tests/regression/test_smaa_reference.py \
  tests/api/test_api_smaa.py
.venv/bin/python scripts/mutation_check.py --smaa-only
```

PROMETHEE II has its own suites and a `PROMETHEE` group of 12 backend and 5 frontend mutants. Its
oracle, `tests/regression/promethee_oracle.py`, computes preference degrees, flows, the PROMETHEE I
relations and the head-to-head and via-others split in exact fractions built from each input's
decimal string. The reference tests reproduce two published examples (Podvezko and Podviezko 2010,
variants 2, 3, 4 and 6; Flachs and De Smet 2026, Appendix A), cited in the test module, and then
compare the engine with the oracle on generated cases:

```sh
.venv/bin/python -m pytest -q tests/unit/test_promethee.py \
  tests/regression/test_promethee_reference.py tests/api/test_api_promethee.py
.venv/bin/python scripts/mutation_check.py --promethee-only
```

AHP has its own suites and an `AHP` group of 10 backend and 5 frontend mutants. Its oracle,
`tests/regression/ahp_oracle.py`, builds reciprocal matrices, gives exact priorities of consistent
matrices, CI and CR, Koczkodaj's triads and both syntheses in exact fractions. The reference tests
reproduce a published matrix (Kampourakis et al. 2025) and the printed random-index table (Nguyen
2020), both cited in the test module, and check the engine's power iteration against LAPACK
(`numpy.linalg.eig`) on generated matrices:

```sh
.venv/bin/python -m pytest -q tests/unit/test_ahp.py tests/regression/test_ahp_reference.py \
  tests/api/test_api_ahp.py
.venv/bin/python scripts/mutation_check.py --ahp-only
```

The method comparison view has its own suites and a `COMPARISON` group of 7 backend and 3
frontend mutants. Its oracle is each method itself: every column must equal that method's own
`/evaluate` result, and `tests/regression/comparison_oracle.py` recomputes leaders and agreement
from those bodies. `tests/builders.every_section` states every method's section on a project:

```sh
.venv/bin/python -m pytest -q tests/unit/test_method_comparison.py \
  tests/regression/test_comparison_reference.py tests/api/test_api_methods_compare.py
.venv/bin/python scripts/mutation_check.py --comparison-only
```

The feasibility check has its own suites and a `FEASIBILITY` group of 11 backend and 3 frontend
mutants. `tests/regression/feasibility_oracle.py` recomputes every status from the project JSON;
the reference cases place bounds exactly at, and one floating-point step either side of, every
measurement of every bundled example, inclusive and exclusive, and spoil one cell of each kind
(missing, a label on a numeric leaf, a number on a labelled one, an unknown label):

```sh
.venv/bin/python -m pytest -q tests/unit/test_feasibility.py \
  tests/regression/test_feasibility_reference.py tests/api/test_api_feasibility.py
.venv/bin/python scripts/mutation_check.py --feasibility-only
```

**Earlier methods' byte identity.** A change that must leave earlier methods untouched is
proved with `scripts/byte_identity.py`: hash every MAVT, sorting, SMAA-2, PROMETHEE II, AHP and
method comparison output of the bundled examples (Base, each scenario and each profile, service and
HTTP; SMAA-2 at its default seed with unknown top-level weights; PROMETHEE II and AHP with fixed
stated sections; the comparison bare and with every section, with both downloads) for the previous
commit and for the working tree, then compare:

```sh
git archive <previous commit> | tar -x -C /tmp/old
.venv/bin/python scripts/byte_identity.py --root /tmp/old --out /tmp/old.json
.venv/bin/python scripts/byte_identity.py --root . --out /tmp/new.json
.venv/bin/python scripts/byte_identity.py --compare /tmp/old.json /tmp/new.json
```

**CLI output tests** match messages on collapsed whitespace (`" ".join(text.split())`) and render
tables at a fixed console width, because CI runs at 80 columns and Rich wraps and truncates.

The installed smoke now also refuses a second installed server on the same library and
drives restoration through the installed Recently deleted UI. Run both archive routes and
`smoke_install.py --browser` after lifecycle changes. The CI workflow runs the same gates, both
archive routes and the installed smoke on hosted Ubuntu 24.04. Report local macOS and hosted Linux
results separately, and treat a configured but unrun workflow as unverified.

## Visible model checks

`frontend/e2e/visible-model.spec.ts` builds an incomplete model through controls, checks duplicate
names, accepted rename/history/deletion failures, goal editing, presentation byte identity, malformed
input and request isolation. It captures blank/small/large/deep/long-label states and five timing
runs per fixture. `visibleTree.test.ts` exercises iterative traversal including a 10,000-node chain;
`ModelTree.test.tsx` covers linked selection, keyboard/focus and defensive fallbacks.

The installed `smoke_install.py --browser` additionally builds/edits/undoes/redoes/saves/reopens a
small model in each installed GUI and writes `installed-visible-model.png` and `.json`.
Use `--dist dist/d1` for the visible-model evidence. See [visible-model verification](package-d1-verification.md). Automated
keyboard checks and screenshot inspection do not replace screen-reader or independent user trials.

### Model comparisons, starter lineage and arithmetic

Focused checks:

```sh
.venv/bin/python -m pytest tests/unit/test_model_comparisons.py tests/unit/test_starter_templates.py tests/unit/test_rounding_oracle.py tests/properties/test_model_properties.py tests/regression/test_market_models_reference.py tests/api/test_api_model_comparisons.py
.venv/bin/python scripts/export_model_schemas.py --check
.venv/bin/python scripts/export_model_test_fixtures.py --check
.venv/bin/python scripts/mutation_check.py --models-only
```

The [arithmetic contract](../design/derived-measurements.md#arithmetic-contract) requires exact
engine-to-engine equality and independent rational forward-error bounds for exact-oracle checks.
The oracle has no application imports; the one-percent mutant must be caught under its bound.
Inclusive boundaries still compare binary64 values without tolerance. Keep the historical
checkpoint as evidence of the corrected new test specification; do not change engine arithmetic.
The model/starter browser suite drives all four gallery items and both selection/reopening paths.
Packaging inspection follows every manifest reference and hash, and the installed smoke uses the
same keyed starter request through CLI and API outside the source checkout.


### Disclosed proxy comparisons

`tests/test_proxy_criterion.py`, `tests/test_proxy_api_cli.py` and
`tests/regression/test_proxy_reference.py` exercise disabled/reviewed plans, unknown facts/licence,
explicit overlap and removal, missing/zero swing ratings, exact baseline/confidence invariance,
all-draw coupling, complete failed pairs, replay and CLI/API parity. The independent rational
oracle reconstructs both value trees and derives decimal rounding bounds. Dyadic cases remain
exact, and the ordinary method's tie/boundary tolerance is pinned unchanged. UI component and
browser checks cover separate columns, visible mandatory feasibility, acknowledgements, retained
history, browser number normalization and stale context. Generated confidence/off-state properties
are in `tests/properties/test_proxy_properties.py`; the original project/results remain byte-exact.

Run `python scripts/mutation_check.py --proxy-only` for the focused semantic faults and the
unmodified controls. The complete gate includes these mutants and all earlier formula mutants.
New proxy schemas and synthetic UI fixtures have freshness checks in the Python suite; regenerate
with `scripts/export_proxy_schemas.py` and `scripts/export_proxy_test_fixtures.py` when changing
the new sidecars. No old schema/version or oracle is updated by those scripts.

### Classifier agreement benchmark

`tests/unit/test_classifier_agreement_benchmark.py` checks the standalone script against
independent no-application oracles: exact Cohen/Fleiss kappa, references, confusion and
calibration from the raw tables; an independent replay of every bootstrap replicate with exact
chunking equality; and binary64 percentile endpoints under a derived forward-error bound. It also
covers refusals, schema round trips and unknown versions. Run
`python scripts/mutation_check.py --benchmark-only` for its nine reachable mutants. Regenerate the
committed schemas with `python scripts/classifier_agreement_benchmark.py --write-schemas docs/schemas`.
