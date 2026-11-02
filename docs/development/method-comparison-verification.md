# Method comparison view: check record

**Date:** 31 October 2026, Pacific/Auckland. **Base:** `main` at `209c703`, uncommitted working tree.
**Scope:** the [method comparison view](../design/method-comparison.md) as designed, with the
owner's six accepted decisions:

- a read-only route that runs each method through its unchanged record builder and lays the
  results side by side;
- every registered method, as its reading or its typed error, with an optional subset;
- the header's profile and scenario, and each method's saved parameters only when it is the saved
  method;
- each method's own rank and quantity, SMAA-2 ranked by rank-1 acceptability;
- agreement on the leading alternative and classes only, with method-specific reasons;
- JSON and long CSV downloads.

Every earlier output is unchanged.

## What changed

- **Domain:** `domain/comparison.py`: `MethodComparison`, `ComparisonColumn`, `ComparisonCell`,
  `ColumnError`, `Agreement`, `LeaderGroup`, `ClassAgreement` and `ColumnReason`. Numbers live only
  in cells, each in one column; agreement holds identities, flags, a share already in a cell, and
  text. No schema change.
- **Service:** `services/comparison_service.py`.
  - **Columns:** it builds each requested method's own record (version 1 for MAVT, version 2 for
    the others) under the selected profile and scenario. Each column carries the method's label,
    inputs, configuration, calculation path, record digest and own label.
  - **Cells:** each cell is taken from that record, with at most two notes (dominance, a class
    boundary, tied first places, PROMETHEE I incomparability, an ideal score).
  - **Failed columns:** a method that fails becomes a failed column with the API's own mapping of
    its error.
  - **Agreement:** it compares leaders (SMAA-2's is `leader_id`) and sorting's classes with
    SMAA-2's most frequent class.
  - **Reasons:** each column whose leader differs from MAVT's gets reasons from its own result:
    - SMAA-2: rank-1 acceptability and its interval, and "no alternative takes rank 1 in half of
      the draws";
    - PROMETHEE II: its explanation's reasons for the two leaders, and PROMETHEE I
      incomparability;
    - AHP: that it reads its own judgements, and its inconsistent matrices;
    - sorting: ties.
  - **Downloads:** the JSON document and a long CSV, one row per alternative and method (a failed
    method has one row with its error), with the CSV text policy.
  - **Methods registry:** `methods.base.registered_methods()` gives registration order.
- **API:**
  - `POST /api/methods/compare` and `/api/projects/{id}/methods/compare`;
  - `POST /api/methods/compare/export` and its stored variant, checked against the expected
    project fingerprint (412 when stale);
  - 422 `UNKNOWN_REFERENCE` for an unregistered method;
  - OpenAPI and the TypeScript types regenerated.
- **CLI:** `mcda compare-methods FILE [--method M ...] [--profile] [--scenario] [-o FILE]` prints
  each method's rank and quantity, failed methods with their codes, leader agreement, class
  differences, reasons and the context sentence.
- **Frontend:**
  - **The Compare tab:**
    - column headers name the method, its quantity and range, what it read, its parameters and its
      own label;
    - cells show the method's own rank and number, each on a meter with that method's own range;
    - a failed column shows its code and issue codes, with a link to the editor tab that fixes it;
    - agreement, reasons and the context sentence appear above the table;
    - rows can be ordered by any one column's rank;
    - JSON and CSV downloads.
  - **Tab bar fix:** a method editor opened from elsewhere now shows its tab in the tab bar (found
    by the browser test: the Pairwise link opened a tab that was hidden until AHP was viewed).
- **Tooling:**
  - `tests/builders.every_section` states every method's section deterministically;
  - `scripts/byte_identity.py` also covers AHP with fixed consistent judgements;
  - a `COMPARISON` mutant group (7 backend, 3 frontend) with `--comparison-only`.

## Checks

**Environment:** macOS 26.5.1 (arm64), Python 3.12.15, NumPy 2.5.4, Node 26.12.1, Google
Chrome 156.

| Check | Command | Before (`209c703`) | After |
| --- | --- | --- | --- |
| Python tests | `.venv/bin/python -m pytest -q` | 1404 passed | **1446 passed**, 0 failed, 0 skipped (one upstream Starlette/httpx deprecation warning) |
| Ruff lint and format | `ruff check` / `ruff format --check` on `src tests scripts hatch_build.py` | Pass (132 files) | Pass (138 files) |
| mypy `--strict` | `.venv/bin/mypy` | Pass (62 files) | Pass (64 files) |
| OpenAPI freshness | `scripts/export_openapi.py --check` | Pass | Pass (regenerated) |
| Acceptance demo | `scripts/acceptance_demo.py` | Pass | Pass |
| Acceptance evidence | `scripts/acceptance_evidence.py <new dir>` | Pass | Pass |
| Frontend gate | `npm --prefix frontend run check` | 365 Vitest | **371 Vitest**; TypeScript, ESLint, type freshness and build pass |
| Browser tests | `MCDA_PYTHON=… MCDA_CHROMIUM=… npm --prefix frontend run test:e2e` | 86 passed | **87 passed** (3.1 min) |
| Mutation check | `.venv/bin/python scripts/mutation_check.py` | 159 of 159 | **169 of 169 killed** (159 plus 10 comparison); the unmutated copy passes |
| Timing | the comparison on the 50 × 40 performance fixture with every section stated (three methods run; sorting has no classes and AHP has too many alternatives) | — | median 1.55 s over three runs |

### Byte identity: every earlier method

`scripts/byte_identity.py` was run on the code of `209c703` and on the new code.
- **It now also covers AHP,** with fixed consistent judgements under Base, on all four examples.
  All four are real runs, of 13 or 14 matrices each.
- **All 789 outputs are byte-identical:** 741 as before, plus 48 AHP outputs.
- **Schemas:** no project, result or record schema changed.

### New tests

42 Python tests, 6 Vitest cases and 1 browser case:

- **`tests/regression/test_comparison_reference.py` (24)** with **`comparison_oracle.py`**. The
  oracle is plain Python, and a clean-interpreter check confirms it loads no `mcda_studio` module.
  - **Cases:** three examples, bare and with every section stated, under Base, each scenario and
    each profile (22 cases).
  - **Ok columns:** every rank, quantity and class equals the oracle's reading of that method's own
    `/evaluate` body, and the column's leaders equal the method's.
  - **Failed columns:** the column's status, code and issue codes equal the `/evaluate` error.
  - **Agreement:** the flag, the leader groups, the class rows and which methods get reasons equal
    the oracle's.
  - **No combination:** a further test checks the agreement's only numbers are shares already in
    SMAA-2's cells.
- **`tests/unit/test_method_comparison.py` (12):**
  - **Requests:** a subset in registry order; an unknown method refused.
  - **Columns:** a failed column with its codes and inputs; the limit shown in every column;
    columns naming inputs, parameters and their own labels; the saved method's parameters kept.
  - **Ties:** a tied leader against a single one; a shared tie, which is still not agreement.
  - **Reasons:** PROMETHEE II's reasons equal to its explanation of the two leaders; SMAA-2's
    "half of the draws"; AHP's inconsistent matrix.
  - **Classes and MAVT:** a sorting/SMAA-2 class disagreement; no reasons without MAVT.
- **`tests/api/test_api_methods_compare.py` (6):**
  - both routes and a subset;
  - the 422 for an unregistered method;
  - the JSON download, and the long CSV with one quantity name per method, the context sentence
    and 412 when stale;
  - a failed method's CSV row;
  - the CLI command, including `-o` and `--method`.
- **Vitest (`ComparePanel.test.tsx`):**
  - the request, and column headers in order with method, quantity, inputs, parameters and own
    label;
  - each method's own numbers, a failed column's typed error and its link;
  - each column's own axis;
  - leader groups and reasons, rows ordered by one column's rank, and the download;
  - the agreement sentence.
- **Browser (`frontend/e2e/method_comparison.spec.ts`):**
  - a project built from blank in the GUI is given every section but AHP's and imported;
  - the AHP column shows `AHP_NOT_STATED`, and its link opens the Pairwise tab;
  - after judging, every column runs;
  - the view names PROMETHEE II's different leader with its reason, keeps the flow axis at −1 to
    1, and downloads a CSV of ten rows, each with its own method's quantity.

**Existing tests changed:** none. `tests/builders.py` gains `every_section`.

### Mutants

| Mutant | Killed by |
| --- | --- |
| A method silently dropped from the columns | reference cases |
| Every column labelled with the first method | label case |
| A failed column omitted instead of shown | reference cases, failed-column case |
| SMAA-2's leader taken from MAVT's reference ranking | reference cases |
| Agreement declared when columns share a tied leader | shared-tie case |
| A reason taken from the wrong pair | PROMETHEE reason case |
| Class agreement always declared | class-disagreement case |
| Frontend: two columns drawn on a shared axis | axis test |
| Frontend: a column header without its method | header test |
| Frontend: a failed column hides its typed error | failed-column test |

**Found by the mutation runs and fixed in the tests:** *agreement declared when columns share a
tied leader* first survived, because the tied-leader case also had different leader sets. A case
where MAVT and sorting share the same tie was added.

## Acceptance

| Criterion | Result |
| --- | --- |
| No averaged, consensus or aggregated score | Met (schema check, and every number equals one method's own) |
| Every column names its method, inputs and parameters; a method that cannot read the model shows its typed error | Met (API, CLI, GUI) |
| Every number equals the method's own `/evaluate` result | Met (22 reference cases) |
| Every earlier output byte-identical | Met (789 outputs) |
| A GUI case; full gate green; every new mutant killed | Met (169 of 169) |

## Behaviour changes

- New routes: `POST /api/methods/compare`, `/api/projects/{id}/methods/compare`,
  `/api/methods/compare/export` and its stored variant.
- New CLI command: `mcda compare-methods`.
- A new Compare tab. A method editor tab opened by a link now appears in the tab bar even when the
  viewed method does not use it.

## Not verified

- Hosted run 41151138594 (commit `61ff58e`, 31 October 2026) passed every stage on Ubuntu 24.04:
  Python and contracts, the frontend and browser workflows, both distribution routes and the
  offline installed GUI smoke. The hosted mutation step runs only weekly or on demand.
- The installed-distribution smoke was not rerun locally (Playwright's bundled Chromium is not
  installed here); it passed on hosted CI (above).
- Only this machine's environment was exercised.
- No human usability result is claimed; the fresh-user checkpoint is still pending.
