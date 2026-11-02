# Feasibility check: check record

**Date:** 31 October 2026, Pacific/Auckland. **Base:** `main` at `61ff58e`, uncommitted working tree.
**Scope:** the [feasibility check](../design/feasibility-check.md) as designed, with requirements in
the project file (open decision 2) and the owner's seven accepted decisions:

- numeric bounds and allowed-label sets, with the ordinal "at least / at most" helper writing an
  explicit set;
- every bound states its unit, which must equal the leaf's exactly; nothing is converted;
- a missing or unusable measurement is unknown, with its reason; overall, any fail is fail, then
  any unknown is unknown;
- a result, route and export of its own, read beside every ranking;
- no effect on any ranking;
- exact comparison at every limit, with no tolerance;
- the same requirements in every scenario and profile.

Every earlier output is unchanged.

## What changed

- **Domain:**
  - `domain/requirements.py`: `BoundRequirement` and `LabelsRequirement`, told apart by `kind`.
  - `domain/feasibility.py`: `FeasibilityResult`, `AlternativeFeasibility`, `RequirementCheck`,
    `RequirementSummary` and the label "feasibility: each requirement is tested on its own
    measurement; no score offsets a failure".
  - `Project.requirements`, optional, with `SECTION_VERSIONS["requirements"] = 6`; migration 5 → 6
    refuses a version-5 file holding requirements.
- **Service:** `services/feasibility_service.py`.
  - **Validation:** eight error codes and one warning (design §6). They block only the
    feasibility result; methods ignore requirements.
  - **Evaluation:** each check is exact, with a reason such as "51 NZD is above the maximum 45 NZD"
    or "no measurement"; limits are printed at full precision.
  - **Overall:** fail, then unknown, then pass; per-requirement counts.
  - **Downloads:** the JSON document and a CSV with one row per alternative and requirement, with
    the CSV text policy, refused when the project fingerprint is stale.
  - **Edits:** `set_requirements` (an empty list removes the section) and `clear_requirements`;
    `remove_criterion` removes the requirements on what it removes. Removing a label is reported
    by validation, never repaired.
- **API:**
  - `POST /api/feasibility` and `/api/projects/{id}/feasibility`;
  - `POST /api/feasibility/export` and its stored variant (412 when stale);
  - edit operations `set_requirements` and `clear_requirements`;
  - OpenAPI, the TypeScript types and `docs/architecture/project_schema.json` regenerated.
- **CLI:**
  - `mcda requirement bound|labels|remove|clear` (`--at-least` and `--at-most` for ordinal
    leaves);
  - `mcda feasibility FILE [-o FILE]`;
  - `mcda evaluate` and `mcda compare-methods` print each alternative's status beside the ranking,
    or why it could not be checked.
- **Frontend:**
  - **The Requirements tab:** a requirement per leaf, with the leaf's unit prefilled and shown,
    "itself passes" for inclusive limits, label checkboxes and "At least …" and "At most …" on ordinal leaves; the
    live result of the draft computed in Python; Apply, Cancel and Remove all (confirmed).
  - **Beside every ranking:** Results shows the feasibility table under the ranking with JSON and
    CSV downloads; the Compare tab gains a Feasibility column. Nothing is filtered or reordered.
  - Issues on `requirements[...]` paths open the Requirements tab.
- **Tooling:**
  - `scripts/byte_identity.py` also covers the method comparison;
  - a `FEASIBILITY` mutant group (11 backend, 3 frontend) with `--feasibility-only`;
  - the contract baseline records the new optional `requirements` field.

## Checks

**Environment:** macOS 26.5.1 (arm64), Python 3.12.15, NumPy 2.5.4, Node 26.12.1, Google
Chrome 156.

| Check | Command | Before (`61ff58e`) | After |
| --- | --- | --- | --- |
| Python tests | `.venv/bin/python -m pytest -q` | 1446 passed | **1503 passed**, 0 failed, 0 skipped (one upstream Starlette/httpx deprecation warning) |
| Ruff lint and format | `ruff check` / `ruff format --check` on `src tests scripts hatch_build.py` | Pass (138 files) | Pass (145 files) |
| mypy `--strict` | `.venv/bin/mypy` | Pass (64 files) | Pass (67 files) |
| OpenAPI freshness | `scripts/export_openapi.py --check` | Pass | Pass (regenerated) |
| Acceptance demo | `scripts/acceptance_demo.py` | Pass | Pass |
| Acceptance evidence | `scripts/acceptance_evidence.py <new dir>` | Pass | Pass |
| Frontend gate | `npm --prefix frontend run check` | 371 Vitest | **380 Vitest**; TypeScript, ESLint, type freshness and build pass |
| Browser tests | `MCDA_PYTHON=… MCDA_CHROMIUM=… npm --prefix frontend run test:e2e` | 87 passed | **88 passed** (3.8 min, run while the mutation check ran) |
| Mutation check | `.venv/bin/python scripts/mutation_check.py` | 169 of 169 | **183 of 183 killed** (169 plus 14 feasibility); the unmutated copy passes |
| Timing | the feasibility check on the 50 × 40 performance fixture with one requirement per leaf (2000 checks) | — | median 9.3 ms over five runs |

### Byte identity: every earlier output

`scripts/byte_identity.py` was run on the code of `61ff58e` and on the new code.

- **It now also covers the method comparison,** on all four examples, bare and with SMAA-2,
  PROMETHEE II and AHP sections stated, under Base, each scenario and each profile: the service
  result, the HTTP body and both downloads by service and over HTTP. With the sections stated,
  every method with its section runs (sorting runs where the example has classes).
- **All 969 outputs are byte-identical:** 789 as before, plus 180 comparison outputs.
- **Schemas:** the project schema gains only the optional `requirements` field; no result or record
  schema changed. A project without requirements keeps its version, bytes and fingerprint.

### New tests

57 Python tests, 9 Vitest cases and 1 browser case:

- **`tests/regression/test_feasibility_reference.py` (31)** with **`feasibility_oracle.py`**. The
  oracle is plain Python, and a clean-interpreter check confirms it loads no `mcda_studio` module.
  - **Cases:** each of the four examples with a requirement set built from its own measurements:
    on every numeric leaf, bounds placed exactly at, and one floating-point step either side of,
    every measured value, minimum and maximum, inclusive and exclusive, plus point and open
    intervals; on every ordinal leaf every "at least" and "at most" set; on every categorical leaf
    each single label (174 to 435 requirements per example).
  - **Spoiled variants:** each example again with one missing measurement, a label on a numeric
    leaf, a number on a labelled leaf and an unknown label.
  - **Match:** every status and reason class, every overall status, the failed and unknown lists,
    the per-requirement counts and the warnings equal the oracle's. A further check confirms the
    cases reach every outcome.
  - **Exact limits:** a measurement equal to an inclusive maximum passes, to an exclusive one
    fails, and one step below fails, with the limit printed in full.
  - **Validation:** 13 invalid lists, every code equal to the oracle's.
- **`tests/unit/test_feasibility.py` (18):**
  - the supplier example's passes and failures with their reasons; a missing measurement unknown,
    and a failure winning over an unknown; the overall order; full-precision limits;
  - **independence:** every method section, a new profile, a changed value function and a changed
    rating leave the result unchanged; every method's cells are identical with and without
    requirements;
  - requirement errors block only the feasibility result; no requirements, no result;
  - **schema:** version 6 only when used, clearing restores the bytes, the version-5 refusal, no
    empty list written, pruning on criterion removal, a removed label reported;
  - the allow-everything warning; both downloads and the stale refusal.
- **`tests/api/test_api_feasibility.py` (6):** both routes; 422 with codes, and `/evaluate`
  unaffected by broken requirements; an unchanged ranking; the edit operations and schema
  versions; both downloads with 412 when stale; the CLI from `requirement bound` to `requirement
  clear`, with the status printed beside `evaluate` and `compare-methods`.
- **`tests/api/test_api_editing.py` (2 cases):** `set_requirements` and `clear_requirements` equal
  their direct service calls.
- **Vitest (9):**
  - **`RequirementsPanel.test.tsx`:** a bound in the leaf's unit checked live and applied as one
    change; both ordinal helpers writing an explicit set; an unreadable limit refused before anything
    is sent; Remove all only after confirmation.
  - **`Feasibility.test.tsx`:** every alternative in project order with unknown never shown as
    pass; both downloads; the section under a complete ranking in Results, and none without
    requirements; the Feasibility column in the comparison, hiding no row.
- **Browser (`frontend/e2e/feasibility.spec.ts`):** a project built from blank in the GUI gets a
  cost cap and a quality floor at Alpha's own value in the Requirements tab; the live result shows
  Alpha passing and Beta failing with its reason; after Apply the project is saved as version 6;
  Results keeps the same ranking with feasibility beside it and downloads a CSV of four rows; the
  comparison keeps both rows with the status column; clearing a measurement makes Alpha unknown,
  not failed.

**Existing tests changed:** the contract baseline and the project JSON Schema gain the optional
`requirements` field; the health and save tests expect schema version 6.

### Mutants

| Mutant | Killed by |
| --- | --- |
| An inclusive minimum compared with `>` | reference cases |
| An inclusive maximum compared with `<` | reference cases, exact-limit case |
| An exclusive minimum compared with `≥` | reference cases |
| An exclusive maximum compared with `≤` | reference cases, exact-limit case |
| A missing measurement treated as fail | reference cases, missing-measurement case |
| A missing measurement treated as pass | reference cases, missing-measurement case |
| A failure compensated when most requirements pass | reference cases, overall-order cases, supplier case, routes, CLI |
| Unknown outranking fail | reference cases, missing-measurement case, overall-order cases |
| The unit check skipped | validation reference cases, unit case, 422 case, CLI |
| An absent section written as an empty list | empty-list case, edit operations |
| The section written as version 5 | version case, edit operations, routes, downloads, CLI |
| Frontend: a failing alternative hidden from the comparison | Compare column test |
| Frontend: the status not shown beside the ranking | Results test |
| Frontend: unknown shown as pass | feasibility table test, Compare column test |

Each row was confirmed by running the mutant against the feasibility suites without stopping at
the first failure.

## Acceptance

| Criterion | Result |
| --- | --- |
| Requirement types, inclusive and exclusive bounds, units and unknowns behave as in §2, matching the oracle at every exact limit | Met (8 reference cases, 13 validation cases) |
| Requirements never depend on weights, profiles, value functions or scenarios; no score offsets a failure | Met (independence and overall-order cases) |
| Every ranking stays complete and unchanged, with feasibility beside it | Met (unit, API, Vitest and browser) |
| Every earlier output byte-identical; projects written at the lowest sufficient version | Met (969 outputs; version tests) |
| A GUI case from blank; full gate green; every new mutant killed | Met (183 of 183) |

## Behaviour changes

- Project files may hold a `requirements` list and are then schema version 6.
- New routes: `POST /api/feasibility`, `/api/projects/{id}/feasibility`, `/api/feasibility/export`
  and its stored variant; new edit operations `set_requirements` and `clear_requirements`.
- New CLI commands `mcda requirement` and `mcda feasibility`; `mcda evaluate` (without `--json`)
  and `mcda compare-methods` print a feasibility line when the project has requirements.
- A new Requirements tab; a feasibility section in Results and a column in the comparison when
  the project has requirements.

## Not verified

- Hosted CI has not run on this change yet.
- The installed-distribution smoke was not rerun locally (Playwright's bundled Chromium is not
  installed here).
- Only this machine's environment was exercised.
- No human usability result is claimed; the fresh-user checkpoint is still pending.
