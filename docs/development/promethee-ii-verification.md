# PROMETHEE II: check record

**Date:** 31 October 2026, Pacific/Auckland. **Base:** `main` at `10c4215`, uncommitted working tree.
**Scope:** [PROMETHEE II](../design/promethee-ii.md) as designed, with the owner's seven accepted
decisions: an optional `promethee` section (schema version 4); flat leaf weights, normalised;
directions and codings stated in the section; the usual, U-shape, V-shape and linear functions;
a per-pair explanation with zones and the head-to-head and via-others split, detailed for up to 50
pairs; the MAVT side under the configured profile and scenario, omitted with a reason when MAVT is
invalid; and the shared `ranking` holding the PROMETHEE II order with `value` = net flow. MAVT,
sorting and SMAA-2 outputs are unchanged.

## Published examples

Both were sourced and reproduced before any engine code was written. The inputs and printed
results enter `tests/regression/test_promethee_reference.py` as data with their citations, under
CC BY 4.0; no text, table layout or figure is copied.

| Source | Reproduced |
| --- | --- |
| Podvezko and Podviezko (2010), *Technological and Economic Development of Economy* 16(1), 143–158, Table 3, variants 2 (usual), 3 (U-shape), 4 (V-shape) and 6 (linear) | All 48 printed flows (3·Φ⁺, 3·Φ⁻, 3·Φ, because the paper does not divide by n − 1) within half a unit of the last printed digit, and all 16 PROMETHEE II ranks, by the engine and by the oracle |
| Flachs and De Smet (2026), arXiv:2610.34481v1, Appendix A | The four net flows exactly in the oracle (1/5, −1/15, −3/5, 7/15) and to the printed precision by the engine |

Variant 6 hits its threshold exactly: Poland and Lithuania differ by 0.79 − 0.73 on criterion 5,
which is q₅ = 0.06 in decimal but 0.06000000000000005 in binary floating point. With the threshold
tolerance the engine counts no preference, as the paper does; a test shows that without it the
U-shape would count full preference.

## What changed

- **Domain:** `domain/outranking.py` (`PrometheeModel`: per leaf a direction, a weight, one of four
  preference functions and an optional coding); `Project.promethee` (optional, omitted when absent);
  `SCHEMA_VERSION` 4 with the identity migration 3 → 4, which refuses a version-3 file holding
  `promethee`; `PrometheeResult` with flows, single-criterion flows, the preference matrix, the
  PROMETHEE I pairs and `OutrankingExplanation`; `PrometheeAnalysisRecord`.
  `validate_measurements` gives the method-independent checks (alternatives, tree, performance
  table, scales and measurements) without MAVT's value functions or profiles; the helpers it shares
  with `validate_project` were extracted without changing the order of MAVT's issues.
- **Method:** `methods/promethee/` registers `promethee2` with the single capability `flows`.
  Validation runs the measurement checks, then 13 section rules (11 errors, 2 warnings), then
  parameters (none). `flows.py` computes every preference degree with the threshold tolerance,
  sums with `math.fsum`, divides by n − 1, ranks with MAVT's `1e-12` tie tolerance, derives the
  PROMETHEE I relations and asserts the invariants on every result (flow bounds, zero sum,
  Φ = Φ⁺ − Φ⁻ and Φ = Σ w̄ⱼ φⱼ). `explanation.py` runs the MAVT engine unchanged under the configured
  profile and scenario, lists every pair ordered differently with its gaps and split, gives
  criterion rows and up to three generated reasons for the first 50, and reports
  `EXPLANATION_LIMITED` or `EXPLANATION_UNAVAILABLE`. A request may compute at most 10⁶ preference
  degrees, the results limits' worst case.
- **Services and API:** a version-2 PROMETHEE record builder; CSV tables `flows`,
  `criterion_flows`, `partial_order` and `explanation`, each row carrying the flow label and none
  with a value column; `/evaluate` returns `PrometheeResult` in the union; edit operations
  `set_promethee_model` and `clear_promethee_model`; removing a criterion removes its entry.
  OpenAPI, the TypeScript types and `docs/architecture/project_schema.json` regenerated.
- **CLI:** `mcda promethee criterion|remove|clear`; `mcda evaluate --method promethee2` prints the
  flows under the label, the incomparable pairs, the rank comparison and the reasons.
- **Frontend:** the Outranking editor tab (direction, weight, function and thresholds per leaf,
  codes with a "Number in label order" helper for ordinal leaves, a shape drawn from q and p
  alone, and why swing weights are not reused); Flows, PROMETHEE I and Explanation views with the
  label, a bar chart on a fixed [−1, 1] axis titled "net flow", and their downloads; the record
  check for PROMETHEE records; the MAVT editors' previews requested for `mavt` while PROMETHEE II
  is viewed; `promethee.*` issues routed to the Outranking tab.
- **Tooling:** `scripts/byte_identity.py` also covers SMAA-2 at its default seed and sample count;
  a `PROMETHEE` mutant group (12 backend, 5 frontend) with `--promethee-only`.

## Checks

**Environment:** macOS 26.5.1 (arm64), Python 3.12.15, NumPy 2.5.4, Node 26.12.1, Google
Chrome 156.

| Check | Command | Before (`10c4215`) | After |
| --- | --- | --- | --- |
| Python tests | `.venv/bin/python -m pytest -q` | 903 passed | **1137 passed**, 0 failed, 0 skipped (one upstream Starlette/httpx deprecation warning) |
| Ruff lint and format | `ruff check` / `ruff format --check` on `src tests scripts hatch_build.py` | Pass (113 files) | Pass (123 files) |
| mypy `--strict` | `.venv/bin/mypy` | Pass (51 files) | Pass (57 files) |
| OpenAPI freshness | `scripts/export_openapi.py --check` | Pass | Pass (regenerated) |
| Acceptance demo | `scripts/acceptance_demo.py` | Pass | Pass |
| Acceptance evidence | `scripts/acceptance_evidence.py <new dir>` | Pass | Pass |
| Frontend gate | `npm --prefix frontend run check` | 347 Vitest | **359 Vitest**; TypeScript, ESLint, type freshness and build pass |
| Browser tests | `MCDA_PYTHON=… MCDA_CHROMIUM=… npm --prefix frontend run test:e2e` | 84 passed | **85 passed** (3.3 min) |
| Mutation check | `.venv/bin/python scripts/mutation_check.py` | 127 of 127 | **144 of 144 killed** (127 plus 17 PROMETHEE); the unmutated copy passes |
| Timing | `promethee2` on the 50 × 40 performance fixture with a section on every leaf (10⁵ preference degrees, explanation available, 769 pairs differ) | — | median 0.20 s over five runs |
| Timing | 100 alternatives × 100 leaves, the results limits' worst case (10⁶ preference degrees) | — | median 1.24 s over three runs |

### MAVT, sorting and SMAA-2 byte identity

`scripts/byte_identity.py`, now covering SMAA-2 as well, hashed every output of the four bundled
examples with the code of `10c4215` and with the new code: project bytes and fingerprints,
validation, evaluation, records, all-node sensitivity, probes, scenario comparison, previews,
every export (JSON and each method's CSV tables) and the HTTP bodies with their status, under Base,
each scenario and each explicit profile. SMAA-2 runs at its default seed and 10 000 draws with
unknown top-level weights stated, under Base and each scenario: eight real runs, evaluated,
recorded and exported. **All 645 outputs are byte-identical** (565 as before, plus 80 SMAA-2
outputs). The `MavtResult`, `MavtSortingResult`, `SmaaResult` and their record schemas are
unchanged; `Project` gains the optional `promethee` property, and the contract baseline was
updated for exactly the two `Project` entries.

### New tests

234 Python tests, 12 Vitest cases and 1 browser case:

- **`tests/regression/test_promethee_reference.py` (171)** with **`promethee_oracle.py`**, plain
  Python in exact fractions built from each input's decimal string, checked in a clean interpreter
  to load no `mcda_studio` module:
  - both published examples, by the engine and by the oracle, and the variant-6 threshold hit;
  - 60 generated cases (values and thresholds on a 0.1 grid, every function, both directions,
    ordinal and categorical codings, zero weights): every flow, single-criterion flow and
    preference index to `1e-12`, ranks and PROMETHEE I relations exactly. Across them, 66
    differences equal a threshold exactly, 30 alternatives tie and 37 pairs are incomparable;
  - the invariants on the same 60 cases;
  - 40 cases with MAVT value functions and ratings of their own (205 pairs ordered differently):
    exactly the pairs whose order differs, each flow gap equal to the oracle's head-to-head plus
    via-others computed separately, and every criterion's contribution and head-to-head part.
- **`tests/unit/test_promethee.py` (48):**
  - preference degrees by hand at 0, q and p, and the decimal-threshold case;
  - minimise, two alternatives (no via-others part), all weight on one criterion (Φ = φⱼ),
    codings, a PROMETHEE I incomparability with tied net flows, and an added alternative that
    reverses two others through the via-others part;
  - swing weights and value functions never read; the ranking holds flows;
  - every validation code, MAVT inputs not required, measurements still blocking, unknown
    parameters, a leaf that gains children, and the work limit;
  - the explanation: a capped advantage that flips the order (criteria, zones, thresholds and the
    exact reasons), zones within q and between q and p, omission with MAVT's codes, the 50-pair
    limit and its order, agreeing methods;
  - schema version 4 only when used, no `null`, `coding` omitted, clearing restores the bytes,
    the migration refusal, and pruning on criterion removal.
- **`tests/api/test_api_promethee.py` (13):** the union body with the label; the version-2 record
  and JSON export round trip with the digest recomputed; the four CSV tables with the label and no
  value column; the explanation table refused when MAVT is unavailable; 422 `METHOD_NOT_SUPPORTED`
  for sensitivity, the probe, scenario comparison and both previews; the previews served for
  `mavt` on the same project; analysis validation; edit operations across schema versions; the CLI
  end to end, ending byte-identical to the starting file.
- **`tests/api/test_api_editing.py` (2):** the two new edit operations give exactly the services'
  result.
- **Vitest:** the Flows, PROMETHEE I and Explanation views (label, provenance, table, no value or
  score heading, bars on the fixed [−1, 1] axis, relations with incomparable first, every pair
  with its zones, thresholds and reasons, the detail limit, the unavailable reason and its disabled
  table); the PROMETHEE record check; the Outranking editor (a full section applied as one edit,
  no assumed direction, the shape drawn without numbers, the engine's issues checked under
  `promethee2`, removal after confirmation); MAVT previews requested for `mavt` while PROMETHEE II
  is viewed.
- **Browser (`frontend/e2e/promethee.spec.ts`):** a project built from blank in the GUI keeps its
  weight previews while PROMETHEE II is viewed, gets its inputs in the Outranking tab, is saved as
  version 4 with its method unchanged, shows the label and the engine's flows, names the capped
  cost criterion and p = 10 in the explanation, and exports the flows CSV and a version-2 JSON.

**Existing tests changed,** because what they enumerate changed by design: the registered methods,
`/api/meta` and the unknown-method message (`test_api_method_seam.py`), `/api/health` and the save
route's version rule (`test_api_projects.py`), the result union and record list
(`test_api_sorting.py`), the frontend `META` fixture, the method list (`AnalysisControls.test.tsx`)
and the views-not-offered lines (`Sorting.test.tsx`). No assertion about an MAVT, sorting or SMAA-2
number changed.

### Mutants

| Mutant | Killed by |
| --- | --- |
| q and p swapped in the linear function | both published examples, hand-derived degrees, generated cases |
| Flows not divided by n − 1 | hand-derived cases, API cases |
| Minimise ignored | published examples, minimise case, capped-advantage case |
| U-shape counts a difference equal to q as preference | hand-derived degrees, decimal-threshold case, generated cases |
| Thresholds compared without the tolerance | decimal-threshold case, generated cases |
| Weights not normalised | invariants, hand-derived cases, API cases |
| Net flow taken as the positive flow alone | invariants on every result |
| Incomparable pairs reported as indifferent | incomparability case, generated cases |
| Via-others part dropped | split against the oracle, added-alternative case |
| A capped difference reported as partial | capped-advantage case |
| Absent section written as `null` | schema case |
| Section written as schema version 3 | schema case |
| Frontend: flows drawn on the 0–1 value axis | flow-axis test |
| Frontend: the Flows view drops its label | results test |
| Frontend: a pair ordered differently is missing | explanation test |
| Frontend: the record check accepts mismatched flows | record-check test |
| Frontend: MAVT previews requested for the viewed PROMETHEE method | previews test |

**Found by the mutation runs and fixed in the harness, not the code:** the first full run reported
143 of 144, because the SMAA mutant *section written as schema version 2* targeted the
`SECTION_VERSIONS` line, which now also lists `promethee`, so its text no longer occurred. It was
retargeted to the new line and is killed.

**Found while testing and fixed in the code:** the function shape's accessible name, "Shape of the
preference function for Cost", contained the function select's own name, so a search for that
control by its label found two elements. The shape is now "Function shape for Cost".

## Acceptance

| Criterion | Result |
| --- | --- |
| Both published examples reproduced: 48 flows and 16 ranks, and four net flows | Met (engine and oracle) |
| The oracle agrees with the engine to `1e-12` | Met (60 generated cases, plus 40 for the split) |
| Flows lie in [−1, 1] and net flows sum to zero | Met (asserted on every result) |
| Flows never shown as preference values, never averaged with MAVT, never given swing weights | Met (label everywhere, no value column, fixed flow axis, inputs read only from the section) |
| The explanation names the criteria and thresholds behind each difference in rank | Met |
| MAVT, sorting and SMAA-2 outputs byte-identical; lowest sufficient schema version written | Met (645 outputs; version 4 only with the section) |
| A GUI case from blank to export | Met |
| Full gate green; every new mutant killed | Met (144 of 144) |

## Behaviour changes

- `/api/health` reports schema version 4 and lists `promethee2`; `/api/meta` lists it with its
  tables.
- `PUT /api/projects/{id}` accepts declared versions up to 4.
- The record route's `oneOf` gains `PrometheeAnalysisRecord`; MAVT, sorting and SMAA-2 bodies are
  unchanged.
- MAVT, sorting and SMAA-2 Results name three more views they do not offer (Flows, PROMETHEE I,
  Explanation against MAVT).
- Removing a criterion also removes its PROMETHEE entry; a scale whose labels change, or a leaf
  that gains children, is reported by validation and never repaired.
- While a method that does not read the MAVT model is viewed, the MAVT editors request their
  previews for `mavt` with the same profile and scenario.

## Not verified

- Hosted run 41059807732 (commit `17b3c2d`, 31 October 2026) passed every stage on Ubuntu 24.04:
  Python and contracts, the frontend and browser workflows, both distribution routes and the
  offline installed GUI smoke. The hosted mutation step runs only weekly or on demand.
- The installed-distribution smoke was not rerun locally (Playwright's bundled Chromium is not
  installed here); it passed on hosted CI (above).
- Only this machine's environment was exercised.
- No human usability result is claimed; the fresh-user checkpoint is still pending.
