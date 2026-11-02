# AHP: check record

**Date:** 31 October 2026, Pacific/Auckland. **Base:** `main` at `17b3c2d`, uncommitted working tree.
**Scope:** [AHP](../design/ahp.md) as the full method (open decision 5), with the owner's nine
accepted decisions:

- an optional `ahp` section (schema version 5), each pair stored once as the entry that is at
  least 1;
- any judgement value from 1 to 9;
- the project's one criteria tree;
- power iteration in plain Python, checked against LAPACK;
- the Saaty and Tran (2007) random indices for up to 15 items;
- distributive synthesis by default and ideal as a parameter;
- Koczkodaj's triad as the inconsistency hint;
- openly licensed published examples only;
- no weight profile or scenario in AHP results.

MAVT, sorting, SMAA-2 and PROMETHEE II outputs are unchanged.

## Published examples

Both sources were found and reproduced before any engine code was written. Their numbers enter
`tests/regression/test_ahp_reference.py` as data with their citations, under CC BY 4.0; no text,
table layout or figure is copied.

| Source | Reproduced |
| --- | --- |
| Kampourakis, Kavallieratos, Spathoulas, Gkioulos and Katsikas (2025), "LLM-Assisted AHP for Explainable Cyber Range Evaluation", arXiv:2512.10487, Equation 7 and Table 2 | Nine of the ten printed weights to three decimals. C1 is 0.31573, matching the text's "≈0.316"; the table prints 0.317, apparently rounded so the column sums to 1. λmax = 10.91953 and the weights agree with LAPACK to 10⁻¹⁰, and CR = 0.0686 is "well below 0.10", as printed. The most inconsistent triad is (C1, C5, C9) |
| Nguyen (2020), "Evaluating and Ranking Criteria for Mathematics Graduate Education Admissions through the Analytic Hierarchy Process", arXiv:2011.05376, Table 12 | The engine's random-index table equals the printed one (Saaty and Tran 2007) for every n from 1 to 15 |

No openly licensed example with alternative matrices and a synthesis was found, so synthesis is
verified against exact hand-built hierarchies.

## What changed

- **Domain:**
  - `domain/pairwise.py` (`AhpModel`: judgements per sibling group and per leaf);
  - `Project.ahp`, optional and omitted when absent;
  - `SCHEMA_VERSION` 5, with the identity migration 4 → 5, which refuses a version-4 file holding
    `ahp`;
  - `AhpResult`, `AhpMatrixResult`, `AhpMatrixPreview`, `AhpTriad` and `AhpAnalysisRecord`;
  - `ConvergenceError`, mapped to 422 `AHP_NO_CONVERGENCE`;
  - `validate_structure`, which runs the alternative and tree checks without measurements. Its
    shared helper was extracted from `validate_measurements` without changing PROMETHEE II's
    issues.
- **Method:** `methods/ahp/` registers `ahp` with the single capability `consistency`.
  - **Validation:** the structural checks, then ten section rules (shared with the preview), then
    the `synthesis` parameter.
  - **`matrix.py`:** builds each reciprocal matrix and runs power iteration with `math.fsum`
    (tolerance 10⁻¹⁴, at most 10 000 iterations). Matrices of one and two items are handled
    explicitly. It computes CI and CR against the named table, flags a warning above 0.10, and
    finds Koczkodaj's most inconsistent triad.
  - **`engine.py`:** multiplies local priorities down the tree, synthesises in either mode, ranks
    with MAVT's 10⁻¹² tolerance, and reports `AHP_INCONSISTENT` warnings.
- **Services and API:**
  - a version-2 AHP record builder;
  - CSV tables `priorities`, `criterion_priorities`, `local_priorities` and `consistency`, each row
    carrying the label;
  - `/evaluate` returns `AhpResult` in the union;
  - a read-only `POST /api/ahp/preview` for one drafted matrix;
  - edit operations `set_ahp_model` and `clear_ahp_model`; removing an alternative or criterion
    removes the judgements and entries that name it;
  - OpenAPI, the TypeScript types and `docs/architecture/project_schema.json` regenerated.
- **CLI:** `mcda ahp judge|remove|clear|check`; `mcda evaluate --method ahp [--synthesis ideal]`
  prints the priorities under the label and every matrix's consistency.
- **Frontend:**
  - the Pairwise editor tab: one matrix per sibling group and per leaf, with Saaty's verbal scale,
    a stored non-integer value kept as "custom", and a live preview computed in Python showing
    priorities, λmax, CI, CR, the warning and the triad's three rows highlighted;
  - the AHP priorities and Consistency views and their downloads;
  - the record check for AHP records, which expects no profile or scenario;
  - a header note that AHP reads no weight profile or scenario;
  - `ahp.*` issues routed to the Pairwise tab.
- **Tooling:**
  - `scripts/byte_identity.py` also covers PROMETHEE II, with a fixed stated section;
  - an `AHP` mutant group (10 backend, 5 frontend) with `--ahp-only`;
  - the SMAA-2 and PROMETHEE II schema-version mutants retargeted to text that later sections do
    not change.

## Checks

**Environment:** macOS 26.5.1 (arm64), Python 3.12.15, NumPy 2.5.4, Node 26.12.1, Google
Chrome 156.

| Check | Command | Before (`17b3c2d`) | After |
| --- | --- | --- | --- |
| Python tests | `.venv/bin/python -m pytest -q` | 1137 passed | **1404 passed**, 0 failed, 0 skipped (one upstream Starlette/httpx deprecation warning) |
| Ruff lint and format | `ruff check` / `ruff format --check` on `src tests scripts hatch_build.py` | Pass (123 files) | Pass (132 files) |
| mypy `--strict` | `.venv/bin/mypy` | Pass (57 files) | Pass (62 files) |
| OpenAPI freshness | `scripts/export_openapi.py --check` | Pass | Pass (regenerated) |
| Acceptance demo | `scripts/acceptance_demo.py` | Pass | Pass |
| Acceptance evidence | `scripts/acceptance_evidence.py <new dir>` | Pass | Pass |
| Frontend gate | `npm --prefix frontend run check` | 359 Vitest | **365 Vitest**; TypeScript, ESLint, type freshness and build pass |
| Browser tests | `MCDA_PYTHON=… MCDA_CHROMIUM=… npm --prefix frontend run test:e2e` | 85 passed | **86 passed** (3.5 min) |
| Mutation check | `.venv/bin/python scripts/mutation_check.py` | 144 of 144 | **159 of 159 killed** (144 plus 15 AHP); the unmutated copy passes |
| Timing | `ahp` with 15 alternatives × 100 leaves in ten groups of ten, random (highly inconsistent) judgements: 111 matrices | — | median 0.13 s over five runs; at most 60 iterations per matrix |

### Byte identity: MAVT, sorting, SMAA-2 and PROMETHEE II

`scripts/byte_identity.py` was run on the code of `17b3c2d` and on the new code.
- **It now also covers PROMETHEE II:** every leaf maximised, weight 1, the usual function, and
  labels coded by their position. PROMETHEE II runs under Base and each scenario.
- **All eight PROMETHEE II runs are real results**, each with its explanation against MAVT and
  pairs ordered differently.
- **All 741 outputs are byte-identical:** 645 as before, plus 96 PROMETHEE II outputs.
- **Schemas:** none of the earlier methods' result or record schemas changed. `Project` gains the
  optional `ahp` property, and the contract baseline was updated for exactly the two `Project`
  entries.

### New tests

267 Python tests, 6 Vitest cases and 1 browser case:

- **`tests/regression/test_ahp_reference.py` (227)** with **`ahp_oracle.py`**. The oracle is plain
  Python in exact fractions, and a clean-interpreter check confirms it loads neither `mcda_studio`
  nor NumPy.
  - The published matrix and the printed random-index table.
  - The engine against LAPACK on 120 generated reciprocal matrices of 3 to 15 items, from Saaty's
    scale in both orientations: λmax and every priority to 10⁻¹⁰, CI, RI, CR and the flag from the
    oracle's formula, and the triad, its index and its consistent value from the oracle.
  - The closed form λmax = 1 + t + 1/t for four 3 × 3 matrices.
  - 40 generated consistent hierarchies in both synthesis modes: local and global priorities,
    overall priorities, ideal scores and ranks against the oracle's exact fractions to 10⁻¹².
  - 20 inconsistent hierarchies against the oracle fed LAPACK's priorities.
- **`tests/unit/test_ahp.py` (26):**
  - **Small matrices:** one and two items, a consistent matrix, a planted inconsistency named
    by its triad, and the warning at the threshold versus above it.
  - **Errors and synthesis:** non-convergence as an error, global priorities down a two-level tree,
    the copy case (distributive synthesis reverses two alternatives, ideal does not), and ideal
    scores.
  - **Independence:** the result names no profile or scenario and carries the label; MAVT inputs
    never change AHP.
  - **Validation:** every validation code, and the swap hint.
  - **Inconsistency:** it is a result warning, not a validation error.
  - **Preview and schema:** the preview, schema version 5 and clearing, and pruning on removal.
- **`tests/api/test_api_ahp.py` (12):**
  - the union body with the label and the inconsistent matrix flagged;
  - the version-2 record and its JSON export round trip;
  - the four CSV tables, with the label and no value column;
  - 422 `METHOD_NOT_SUPPORTED` for five routes;
  - the preview route, and non-convergence as a 422;
  - edit operations across schema versions;
  - the CLI end to end, ending byte-identical to the starting file.
- **`tests/api/test_api_editing.py` (2):** the two new edit operations give exactly the services'
  result.
- **Vitest:**
  - **Results:** the AHP views (label, provenance, priorities, criterion priorities, the
    consistency table with inconsistent matrices first and their triads, CSV tables) and the AHP
    record check, including its null profile.
  - **Pairwise editor:** a full model applied as one edit with each pair stored once; the live
    preview, the warning and the triad's three rows, which clear once the judgement is fixed; a
    custom value kept; and removal after confirmation.
- **Browser (`frontend/e2e/ahp.spec.ts`):** a project built from blank in the GUI gets a third
  criterion and is judged with a cyclic top-level matrix. It shows the warning with the triad and
  its three rows, is fixed, and is saved as version 5 with its method unchanged. It then shows the
  label and the engine's priorities, exports the priorities CSV and a version-2 JSON, and reopens
  with its judgements.

**Existing tests changed,** because what they enumerate changed by design:
- the registered methods, `/api/meta` and the unknown-method message (`test_api_method_seam.py`);
- `/api/health` and the save route's version rule (`test_api_projects.py`);
- the result union and record list (`test_api_sorting.py`);
- two tests that used `ahp` as an example of an unregistered method (`test_previews.py`, which now
  uses `electre`, and `test_workflow.py`);
- the frontend `META` fixture, the method list (`AnalysisControls.test.tsx`) and the
  views-not-offered lines (`Sorting.test.tsx`).

No assertion about an earlier method's number changed.

### Mutants

| Mutant | Killed by |
| --- | --- |
| A wrong reciprocal (the value mirrored instead of inverted) | small-matrix, closed-form and hierarchy cases |
| An off-by-one random-index lookup | published matrix, LAPACK cases, two-item case |
| Unnormalised priorities | small-matrix and LAPACK cases |
| Distributive and ideal synthesis swapped | hierarchy cases, copy case |
| The warning at CR ≥ 0.10 instead of above it | threshold case |
| The triad index taking one of its two ratios | published matrix, LAPACK cases (the planted triad cannot tell: its stated value lies below the product, where both ratios agree) |
| Global priorities not multiplied down the tree | two-level tree, hierarchy cases |
| The iteration cap ignored, returning a partial vector | non-convergence cases (engine and API) |
| An absent section written as `null` | schema case |
| The section written as version 4 | schema case |
| Frontend: the AHP view drops its label | results test |
| Frontend: the triad's rows not highlighted | editor test |
| Frontend: the consistency warning not shown | editor test |
| Frontend: the record check accepts mismatched priorities | record-check test |
| Frontend: the record check expects the viewed profile and scenario | record-check test |

**Fixed in the harness:** adding `ahp` to `SECTION_VERSIONS` changed the line that the SMAA-2 and
PROMETHEE II schema-version mutants targeted. Both now target a fragment that later sections leave
alone, and both are killed. The first full run then reported 158 of 159: the analysis-retry mutant
*V4 (records accept the wrong resolved profile)* targeted the profile comparison that AHP's
record check rewrote. It was retargeted to the new comparison, and a second full run killed all
159.

## Acceptance

| Criterion | Result |
| --- | --- |
| The published matrix reproduces its printed weights and agrees with LAPACK; the random-index table equals the printed one | Met |
| Every result names its random-index table and synthesis mode | Met (result, record, CSV, CLI, GUI) |
| Matrices of one and two items are explicit; CR above 0.10 warns and never blocks | Met |
| Earlier methods byte-identical; lowest sufficient schema version written; IDs, judgements, profiles and scenarios kept | Met (741 outputs; version 5 only with the section) |
| A GUI case from blank: matrices, a consistency warning fixed, evaluate, save, reopen and export | Met |
| Full gate green; every new mutant killed | Met (159 of 159) |

## Behaviour changes

- `/api/health` reports schema version 5 and lists `ahp`; `/api/meta` lists it with its tables.
- `PUT /api/projects/{id}` accepts declared versions up to 5.
- The record route's `oneOf` gains `AhpAnalysisRecord`, and the result union gains `AhpResult`.
- New route: `POST /api/ahp/preview`.
- Earlier methods' Results name two more views they do not offer (AHP priorities, Consistency).
- Removing an alternative or criterion also removes AHP judgements that name it; nothing new is
  ever judged automatically.

## Not verified

- Hosted run 41146266072 (commit `209c703`, 31 October 2026) passed every stage on Ubuntu 24.04:
  Python and contracts, the frontend and browser workflows, both distribution routes and the
  offline installed GUI smoke. The hosted mutation step runs only weekly or on demand.
- The installed-distribution smoke was not rerun locally (Playwright's bundled Chromium is not
  installed here); it passed on hosted CI (above).
- Only this machine's environment was exercised.
- No human usability result is claimed; the fresh-user checkpoint is still pending.
