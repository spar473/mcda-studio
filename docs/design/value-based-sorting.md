# Value-based sorting

**Status:** accepted design, 29 October 2026; **implemented** 29 October 2026 (see the
[implementation notes](#implementation-notes) and the
[check record](../development/value-based-sorting-verification.md)). The owner accepted all six
[decisions](#decisions) on 29 October 2026, as recommended.

Value-based sorting is the first decision method after MAVT to come through the
[method seam](method-seam.md). It assigns each alternative to an ordered class, such as
*Qualified / Conditional / Not qualified*, by comparing its overall MAVT value with fixed numeric
boundaries. It is the method the roadmap calls "Value-based sorting"; the earlier proposal is
plan §8 (historical record, not included), and this note decides it. Where they differ, this
note wins.

Sorting is also the development that completes the seam. The parts the seam deferred until a real
second result existed arrive here: the discriminated result union (seam §3), version-2 analysis
records and per-method export tables (§5), omitted method sections and the lowest sufficient
schema version (§6), and the frontend panel registry with the transient method view (§7).

## What exists today

- **The seam's backend contract.** `Method` declares a name, label and capabilities and owns its
  validation and parameters. `classes` is already in the closed `Capability` vocabulary. Routes
  refuse a missing capability with 422 `METHOD_NOT_SUPPORTED`. Version-1 records and exports are
  refused for any method but MAVT (`require_record_v1`).
- **MAVT values.** `prepare_mavt` and `build_mavt_result` compute every overall value with
  `math.fsum`; ranks are competition ranks with the tie tolerance `TIE_TOL = 1e-12`.
- **Exact sensitivity.** Along a one-way proportional weight change every overall value is affine
  in the varied weight, so crossovers are closed-form roots (specification §5).
- **Local anchors.** Validation already warns `LOCAL_ANCHORS` per leaf: adding or removing an
  alternative can change every score on that criterion.
- **Hard-wired in five places still:** `/evaluate` and the frontend read `MavtResult` directly;
  `AnalysisRecord` and `AnalysisExportDocument` exist only as version 1; `Project` has no method
  section and always writes `schema_version: 1`; the Results workspace has one fixed panel list;
  the method can only be changed by editing the saved configuration.

## Goals and non-goals

**Goals:**

- Ordered classes with numeric boundaries on the overall value scale, the boundary rule stated
  once and applied identically by evaluation, sensitivity, the probe, records and exports.
- Each alternative's class and its distance to the nearest boundary; the exact weight at which each
  alternative first changes class in sensitivity; a warning that recommends fixed anchors; an audit
  sample below a cut-off for reviewing possible false negatives.
- Class bands on the ranking and sensitivity charts, a Classes panel and editor, class columns in
  CSV.
- A sorting variant of supplier selection, *supplier qualification*, as a new bundled example.
- The seam remainder listed above, with its deferred verification.
- **MAVT byte-identical:** for unchanged inputs, MAVT results, records, exports, project bytes and
  fingerprints do not change, on all three bundled examples, Base and every scenario.

**Non-goals (excluded):**

- Boundaries defined by reference alternatives or boundary profiles (they can cross under changed
  weights and need crossing rules); learning boundaries from past decisions; ELECTRE TRI.
- Per-scenario or per-profile boundaries: boundaries are fixed on the value scale and shared by
  every scenario and profile.
- Comparing classes between Base and a scenario. Scenario comparison stays the MAVT comparison of
  values and ranks; class comparison is a candidate for the method comparison view.
- Feasibility: sorting uses the aggregate value; testing individual measurements against hard
  limits is the separate feasibility check.
- Class acceptability under uncertainty (SMAA-2).

## Design

### 1. The sorting rule

Add §7 "Value-based sorting" to the [specification](../mathematics/specification.md):

- **Classes** `C_1` (best) … `C_q`, with `q ≥ 1`, stored best first. Every class except the lowest
  has a **lower boundary** `b_h`, the overall value needed to enter it. The lowest class `C_q` has
  none and takes every remaining value.
- **Assignment.** With `τ = 1e-12` (the existing tie tolerance):

  `class(a) = C_h`, where `h = 1 + #{k < q : U(a) < b_k − τ}`.

  Equivalently `a ∈ C_h` when `b_h − τ ≤ U(a) < b_{h−1} − τ`, taking `b_0 = +∞` and `b_q = −∞`.
  A value within `τ` of a boundary, on either side, goes to the **higher** class.
- **Validity.** Every boundary is finite and lies in [0, 1] (decision 2). Boundaries decrease
  strictly from the best class down, each more than `2τ` below the one above, so the tie bands
  `[b − τ, b + τ]` never overlap. Boundaries are never sorted, merged or relabelled automatically.
- **Empty and single classes are valid.** A class no alternative reaches is shown empty. With one
  class (`q = 1`) there are no boundaries and every alternative is in it.
- **Distance to the nearest boundary.** `d(a) = min_k |U(a) − b_k|`, naming that boundary by its
  class (the higher boundary on an exact tie between two). An alternative with `d(a) ≤ τ` is
  *on the boundary*. With one class there is no boundary, and distance is absent.
- **Meaning.** Classes inherit every MAVT assumption, including compensation: a class says only
  that the overall preference value reached a stated threshold. It is not a probability, a
  prediction or a pass/fail test of any single measurement.

### 2. The stored model: a `sorting` section

```json
"sorting": {
  "classes": [
    { "id": "qualified", "name": "Qualified", "description": "", "lower_boundary": 0.7 },
    { "id": "conditional", "name": "Conditional", "description": "", "lower_boundary": 0.6 },
    { "id": "not_qualified", "name": "Not qualified", "description": "", "lower_boundary": null }
  ],
  "audit": { "below_class_id": "conditional", "sample_size": 1, "seed": 2026 }
}
```

- `SortingModel(classes: list[SortingClass] = [], audit: SortingAudit | None = None)`;
  `SortingClass(id, name, description = "", lower_boundary: FiniteFloat | None = None)`;
  `SortingAudit(below_class_id, sample_size: StrictInt, seed: StrictInt)`.
- `Project.sorting: SortingModel | None = None`. The section belongs to `mavt_sorting` (seam §8):
  MAVT never reads it. A project may keep a sorting section while its saved method is MAVT; MAVT
  results are then unchanged, but the file is version 2 (§7).
- Each boundary sits on the class it admits into (decision 1). Moving a class moves its boundary
  with it, so an out-of-order list becomes a validation error to fix, never a silent
  reinterpretation.
- Types are checked at the model boundary; rules are validation issues (§3), so an incomplete
  draft can still be saved, as for scales and swing ratings.
- **Edit operations:** `set_sorting_model` replaces the whole section (the Classes editor applies
  one draft as one undo step), `clear_sorting_model` removes it, and `set_analysis_method` sets the
  saved method (§10).

### 3. Validation

`MavtSortingMethod.validate` runs MAVT's checks unchanged and in the same order, so every MAVT
code, path and message is identical under sorting; then the sorting checks; then parameter checks.
Sorting's parameter model is MAVT's (`dominance_check`); the audit settings are model inputs and
live in the section, not in parameters (decision 4).

| Code | Severity | When |
| --- | --- | --- |
| `NO_SORTING_MODEL` | error | the method is `mavt_sorting` and the project has no `sorting` section |
| `NO_CLASSES` | error | the section has no classes |
| `DUPLICATE_CLASS_ID` | error | a class ID repeats |
| `DUPLICATE_CLASS_NAME` | warning | class names repeat, ignoring case |
| `MISSING_CLASS_BOUNDARY` | error | a class other than the lowest has no lower boundary |
| `UNEXPECTED_CLASS_BOUNDARY` | error | the lowest class has one; it takes every remaining value |
| `BOUNDARY_OUT_OF_RANGE` | error | a boundary lies outside [0, 1] |
| `BOUNDARIES_NOT_DECREASING` | error | a boundary is not more than 2 × 10⁻¹² below the one above it; the message names both classes and says boundaries are never reordered automatically |
| `UNKNOWN_AUDIT_CLASS` | error | the audit cut-off names no class |
| `AUDIT_BELOW_LOWEST_CLASS` | error | the cut-off is the lowest class, so nothing can fall below it |
| `INVALID_AUDIT_SAMPLE_SIZE` | error | the sample size is below 1 |
| `SORTING_LOCAL_ANCHORS` | warning | an effective leaf function uses local anchors. One warning naming every such leaf: adding or removing an alternative can move others between classes; fixed anchors are recommended for sorting |

Paths follow the house form (`sorting.classes[qualified].lower_boundary`, `sorting.audit`). Only
the effective model counts, so a scenario override that introduces local anchors triggers the
anchor warning when that scenario is viewed. The project-wide editor report (`validate_project`)
is unchanged; sorting issues appear wherever the analysis validation of the viewed method is
shown: Results, Sensitivity and the Classes editor.

### 4. The `mavt_sorting` method, its result and the result union

- **Method:** name `mavt_sorting`, label "Value-based sorting (MAVT)", capabilities: MAVT's six
  plus `classes`. It evaluates through `prepare_mavt` and the MAVT result builder, then assigns
  classes. Ranking, values, contributions, partial values, weights and dominance are MAVT's, field
  for field (an invariant test compares them on every example).
- **Result types.** Today's `MavtResult` fields move unchanged, in order, into a shared base;
  `MavtResult` keeps `method: "mavt"` and its JSON, and `MavtSortingResult` adds
  `method: "mavt_sorting"` and:
  - `boundary_tolerance` (1e-12);
  - `classes`: every class best first, with rank, lower and upper boundary and member IDs in rank
    order, empty classes included;
  - `assignments`: one per alternative in rank order, with class ID and rank, `on_boundary`, the
    nearest boundary's class ID and the distance to it;
  - `audit_sample` (§5) or null.

  This is decision 3 of the seam ("extends `MavtResult` with classes") implemented through a
  shared base, so each type keeps its own method tag and MAVT's schema is unchanged.
- **Diagnostics:** MAVT's, plus an `ON_CLASS_BOUNDARY` info for each alternative within `τ` of a
  boundary, naming the class it was given. **Assumptions:** MAVT's, plus one sentence stating the
  boundary rule.
- **The union.** `AnalysisResultUnion = Annotated[MavtResult | MavtSortingResult,
  Field(discriminator="method")]`. `/evaluate` returns it; OpenAPI gains a tagged union and the
  generated TypeScript types narrow by `result.method`. An MAVT body is byte-identical.

### 5. Audit sample

- **Configured** in the sorting section (`audit`); absent by default.
- **Pool:** every alternative whose class lies strictly below `below_class_id`.
- **Selection:** sort the pool by the hexadecimal SHA-256 of `"<seed>:<alternative_id>"`, then by
  ID, and take the first `min(sample_size, pool size)`. This is a seed-keyed pseudo-random sample:
  deterministic, independent of the project's alternative order, the platform and NumPy, and
  reproducible by hand. A new seed draws a new sample; adding an alternative never reorders the
  others (decision 4).
- **Output:** cut-off class, seed, requested size, pool size, the selected IDs in selection order
  and the stated selection rule. Info diagnostics when the pool is smaller than requested
  (`AUDIT_SAMPLE_IS_WHOLE_POOL`) or empty (`AUDIT_POOL_EMPTY`).
- **Wording:** "a sample of alternatives below the cut-off, for manual review of possible false
  negatives". It estimates nothing, carries no interval, and never changes a class.

### 6. Sensitivity: exact class changes

- Boundaries are constant in the varied weight `t`, and `V_a(t)` is affine (specification §5).
  For alternative `a` and boundary `b_k`, `g(t) = V_a(t) − (b_k − τ)` is affine, and `a` is in
  `C_k` or better exactly when `g(t) ≥ 0`. Where `g(0) ≥ 0` and `g(1) < 0`, or the reverse, the
  class changes at

  `t* = g(0) / (g(0) − g(1))`,

  the exact weight at which the engine's own rule switches (decision 3). The class at `t*` itself
  is always the higher one. Unlike rank crossovers, change points at `t = 0` and `t = 1` are kept,
  because the class is defined there.
- **Reported per alternative:** the class at the baseline weight; every change point with the
  boundary's class and the classes just below and just above the weight; the **first change when
  raising** the weight (the smallest change point at or above the baseline after which the class
  differs from the baseline class) and **when lowering** it (mirrored); and the class-stable
  interval. An alternative whose baseline value is within `1e-12` of a boundary adds
  `BASELINE_ON_CLASS_BOUNDARY`, as `BASELINE_ON_CROSSOVER` does for ranks.
- **Probe:** the class of every alternative at the probed weight, from the same rule, so the
  cursor readout and the change points agree.
- **Types:** `SortingSensitivityResult(SensitivityResult)` adds `method: "mavt_sorting"`, the
  classes and the class changes; `SortingSensitivityProbe(SensitivityProbe)` adds the class at the
  probed weight. The routes return `SensitivityResult | SortingSensitivityResult` (and likewise for
  the probe), so an MAVT body gains no key.
- **Scenario comparison** stays the MAVT comparison for sorting (see non-goals).

### 7. Project files: schema version 2, written only when needed

- `SCHEMA_VERSION` becomes 2: the highest version this program reads and writes. Migration 1 → 2
  is the identity. A version-1 file that contains `sorting` is refused ("schema version 1 cannot
  contain 'sorting'").
- **Lowest sufficient version (seam §6).** `Project.required_schema_version()` is 2 when `sorting`
  is present, otherwise 1. Every serialisation (saved files, API bodies and the canonical JSON
  behind fingerprints) writes that version and **omits** `sorting` when absent, never as `null`.
  Results report the same version. The in-memory `schema_version` read from a file is not
  authoritative; it is normalised on output.
- **Consequences:** an MAVT-only project keeps its version-1 bytes and fingerprint, and older
  installations keep opening it. A project with classes is version 2, which an older installation
  refuses with its existing "newer than this program supports" message. Clearing the classes
  returns a project to version 1 with the bytes it had before they were added. A hand-written
  version-2 file without a sorting section is re-saved as version 1.
- The OpenAPI document and TypeScript types mark `sorting` optional. The project JSON Schema and
  the [project schema](../architecture/project-schema.md) page gain the section and the rule.

### 8. Version-2 analysis records and per-method exports

- **Version 1 is unchanged:** MAVT only, byte for byte, with its digest rule.
- **The version-2 envelope** carries `record_version: "2"`, `record_digest`, `method`,
  `method_label`, `calculation_path`, `numerical_tolerance`, `csv_text_policy`, `project_title`,
  `scenario_name`, `resolved_profile_name`, `alternative_order` and `configuration`.
- **The sorting record** adds its result (`MavtSortingResult`, calculation path
  `mavt_sorting.math_fsum.v1`) and the value-model context the shared MAVT panels need, which it
  may hold because it declares `contributions`: criteria, path shares, contribution totals,
  dominance relations, the Base comparison and its diagnostics. The MAVT record builder's context
  code is shared, without changing version 1's construction or bytes. The digest rule is the same:
  SHA-256 of canonical JSON without the digest.
- `/analysis/record` returns `AnalysisRecord | SortingAnalysisRecord`, discriminated by
  `record_version`. When a later method adds its own version-2 record, the version-2 member becomes
  a union discriminated by `method`. A registered method without a record type is still refused
  with 422 `METHOD_NOT_SUPPORTED` (`analysis_record`).
- **Export document:** `export_version: "2"` wraps a version-2 record with the same source project
  and presentation. A version-1 export is MAVT by definition.
- **CSV tables are declared per method.** MAVT keeps its five. Sorting offers `ranking`,
  `classes`, `contributions`, `partial_values`, `dominance` and `comparison`; a table the method
  does not declare is refused. Sorting's `ranking` adds `class_id`, `class_name`, `class_rank`,
  `on_boundary`, `nearest_boundary_class_id`, `distance_to_nearest_boundary` and
  `in_audit_sample`; the new `classes` table has one row per class (ID, name, rank, lower and upper
  boundary, member count and members, and whether it is in the audited pool). The context columns
  carry `export_version` "2" and the sorting calculation path. SVG metadata embeds the sorting
  result.
- **Verification moved here from the seam:** a version-2 round trip (record → export → re-read,
  digest recomputed) with the real sorting method; the fake test method keeps proving refusals.

### 9. API and CLI

- **API:** the unions above on `/evaluate`, `/analysis/record`, `/analysis/export`,
  `/sensitivity` and `/sensitivity/probe` (draft and stored forms); the three edit operations;
  `mavt_sorting` in `/api/meta`; OpenAPI and TypeScript types regenerated; the
  [API contract](../api/contract.md) updated.
- **CLI:**
  - `mcda classes set FILE --class "Qualified=0.70" --class "Conditional=0.60"
    --class "Not qualified"` (best first; IDs generated from names, as for alternatives);
  - `mcda classes audit FILE --below conditional --size 1 --seed 2026`;
  - `mcda classes clear FILE`;
  - `mcda method FILE mavt_sorting` sets the saved method;
  - `--method` on `evaluate`, `sensitivity` and `compare` views another method once.

  `evaluate` prints a class column for sorting; `sensitivity --criterion` prints a second table of
  first class changes. Output assertions in tests match on collapsed whitespace.

### 10. Frontend

- **Method view (seam §7).** The analysis header gains a Method select listing the methods from
  `/api/meta` by label. The viewed method is part of the transient `AnalysisSelection`: no edit,
  no unsaved change, and part of every request key, so stale-response protection already covers
  it. A viewed method other than the saved one uses its own default parameters (decision 5).
  **Use viewed method as saved default** is one undoable `set_analysis_method` edit, beside the
  existing profile and scenario equivalents.
- **Panel registry.** `results/panels.ts` maps each method to its ordered panels and the
  capability each needs: `mavt` → the current six, unchanged; `mavt_sorting` → Classes, then the
  same six. A panel whose capability is missing is not shown, and one line names the views the
  method does not offer. A method without registered panels gets a single explanatory message.
- **Records.** The record check accepts version 2 for `mavt_sorting` with the same identity checks,
  plus: every alternative assigned exactly once, classes best first, every assignment naming a
  listed class.
- **Classes panel (Results):** the class table (rank, name, value range, members); each
  alternative's class and distance to the nearest boundary, with on-boundary marked; the audit
  sample; the sorting diagnostics. It states that classes are cut-offs on the compensatory MAVT
  value, not probabilities or predictions.
- **Classes editor:** a Classes tab, shown when the viewed method uses classes or the project has a
  sorting section. It edits a draft (add, rename, reorder and remove classes; boundary inputs;
  audit settings) and applies it as one undo step, or cancels. Sorting issues show inline; Remove
  classes asks for confirmation. Reordering never re-sorts boundaries.
- **Charts:** class bands behind the ranking chart's bars along the value axis, labelled with class
  names and boundary values; horizontal bands on the sensitivity chart, with a marker at each
  visible alternative's first class change; the cursor readout shows classes from the probe. CSV
  selection offers only the tables the method declares.
- **Python stays the only source of mathematics.** The frontend never assigns classes or computes
  distances or change points. It positions bands from the engine's boundary values.

### 11. The supplier qualification example

- `examples/supplier_qualification/`: `build.py` reuses supplier selection's data, tree, functions,
  profiles and scenario, then adds three classes, an audit setting and the saved method
  `mavt_sorting`. The three existing examples stay byte-unchanged, including their pinned hashes.
- **Anchors:** logistics cost uses fixed anchors from 1.0 to 6.0 NZD/unit, just outside the
  observed 1.1 to 5.9 (decision 6). The README states that this differs from supplier selection,
  where those anchors are local.
- **Classes:** Qualified (from 0.70), Conditional (from 0.60), Not qualified. Computed with the
  current engine, this gives:

  | Context | Qualified | Conditional | Not qualified |
  | --- | --- | --- | --- |
  | Base | Apex 0.7383, Delta 0.7317 | Evergreen 0.6231 | Brightline 0.5943, Cobalt 0.4036 |
  | Cost-focused profile | none (empty class) | Apex 0.6755, Delta 0.6280, Evergreen 0.6081 | Brightline 0.5922, Cobalt 0.4645 |
  | Linear-defects scenario | Apex 0.7415, Delta 0.7317 | Evergreen 0.6423, Brightline 0.6263 | Cobalt 0.4357 |

  So it shows an empty class, a class change across a scenario, and a near miss (Brightline,
  0.0057 below Conditional). The audit samples one supplier from below Conditional.
- The README calls the boundaries illustrative cut-offs, not recommendations. The example is
  bundled like the others: build hook, examples list, installed-distribution smoke, acceptance
  scripts that enumerate examples, and a reviewed addition to the contract baseline.

### 12. The cross-method rules

Sorting reads MAVT's values and its own section, nothing else. No class is derived from a rank
position. Every sorting output names its method, calculation path and boundaries. MAVT never reads
`sorting`. No route or type combines results from two methods.

## Verification plan

- **MAVT byte identity.** A committed script, `scripts/byte_identity.py`, writes a manifest of
  SHA-256 hashes for every MAVT output on the three bundled examples, Base and every scenario:
  project bytes and fingerprint; project-wide and effective validation; evaluation; the version-1
  record; every export table as JSON and CSV; all-node sensitivity; a probe; scenario comparison;
  the weight preview and every leaf's value-function preview; and the HTTP bodies of `/evaluate`,
  `/analysis/record`, `/analysis/export`, `/sensitivity` and the probe. It runs against `c170610`
  (the previous commit) and the new code, and the manifests must be identical.
- **Unit tests:** assignment at each boundary, `2τ` above and below, and within `τ` on both sides;
  empty and single classes; every validation code; nearest boundary and distance; the audit
  selection; the result fields MAVT shares are equal to MAVT's.
- **Property tests:** assignment is monotone in value; changing alternative order never changes a
  class or the audit sample.
- **Oracle:** `tests/regression/sorting_oracle.py`, plain Python reading the example's
  `project.json` directly. It computes values, classes, distances, the audit sample and class
  change roots for every leaf weight. A test proves that importing it in a clean interpreter loads
  no `mcda_studio` module; the comparison test then checks the engine against it.
- **Sensitivity:** change points equal the analytic roots and agree with `brentq` on an
  independent evaluation path; the probed class `1e-9` on either side of each point agrees with the
  reported classes.
- **Schema writing and migration:** an MAVT-only project saves as version 1 with identical bytes;
  with classes, as version 2; both reload. Adding and then clearing classes restores the original
  bytes. A version-1 file containing `sorting` is refused. A version-2 file is refused when the
  supported version is 1. The 1 → 2 migration leaves all three example fingerprints unchanged.
- **API:** the union shapes in OpenAPI; a version-2 record and export round trip; CSV class
  columns; refusal of the `classes` table for MAVT and of records for a method without a record
  type.
- **Vitest:** the panel registry; viewing a method creates no edit; "use as saved default" is one
  undo step; the version-2 record check; bands placed from engine values; the Classes editor's
  draft, apply, cancel and validation.
- **Playwright against the real backend:** the GUI acceptance case from blank (add classes, set
  boundaries, evaluate, read an exact class change in sensitivity, export CSV with the class
  column); the supplier qualification example's classes; switching method never dirties the
  project.
- **Mutants**, a new `SORTING` group with `--sorting-only`:
  - `<` instead of `≤` at a boundary (an on-boundary value goes to the lower class);
  - an inverted class order;
  - a class-change root with the wrong sign;
  - a version-2 record written for MAVT;
  - a schema version written too high (always the newest);
  - an absent sorting section written as `null`;
  - out-of-order boundaries silently sorted instead of refused;
  - the audit pool including the cut-off class;
  - the frontend showing the Classes panel for MAVT;
  - the method view writing an edit.

## Acceptance

- Classes match the oracle at, just above and just below every boundary, including inside the
  tolerance band.
- Empty and single classes are valid; invalid boundaries are refused with a clear message and
  never reordered.
- Class-change points match exact roots, and the class on each side agrees with direct evaluation.
- MAVT results, records, exports, project bytes and fingerprints are byte-identical on all three
  examples, Base and every scenario; every existing test passes unchanged.
- The three existing fixtures are byte-unchanged; the new example evaluates identically through
  the CLI and the GUI.
- The version-2 round trip and the schema-writing tests pass.
- The GUI acceptance case passes from blank to export.
- The full gate is green and every new mutant is killed.

## Decisions

Accepted by the owner on 29 October 2026, as recommended ("accept all").

1. **Where boundaries are stored.** *Recommended:* on each class, as the lower boundary needed to
   enter it, with none on the lowest class (§2). The list reads top-down like the classes, and a
   reordered list becomes a visible error. *Alternative:* separate boundary objects naming both
   adjacent classes (plan §8.3). They need extra rules (exactly one per adjacent pair, in order)
   and add no meaning while every boundary is a number.
2. **Boundary range.** *Recommended:* refuse boundaries outside [0, 1]. Overall values always lie
   there, so such a boundary separates nothing and usually means a unit slip (60 for 0.60).
   *Alternative:* accept any finite number and show the resulting always-empty class.
3. **Where a class-change weight sits.** *Recommended:* the exact weight at which the engine's rule
   switches, where `V_a(t) = b − 10⁻¹²` (§6). Evaluating or probing at any weight then agrees with
   the reported changes. It differs from the plain boundary root by `10⁻¹²/|s|`, where `s` is the
   value's slope; that is invisible at four decimals unless an alternative barely moves while
   sitting on a boundary. *Alternative:* the plain root `V_a(t) = b`, a literal copy of the
   crossover rule, which can disagree with evaluation for such near-flat alternatives.
4. **What the audit sample is.** *Recommended:* the seed-keyed pseudo-random sample of §5, with its
   settings stored in the sorting section. It covers the whole rejected region; the nearest misses
   are already visible from distance to the boundary. *Alternative:* the k alternatives closest
   below the cut-off, which repeats information already shown. *Also:* settings as method
   parameters instead of in the section; they would then travel with the saved configuration and
   be dropped when another method is viewed (decision 5).
5. **Parameters when another method is viewed.** *Recommended:* a viewed method other than the
   saved one runs with its own default parameters, and "use as saved default" also clears the saved
   parameters, listing them in the confirmation when there are any. One method's parameters are
   then never applied to another. No bundled example has parameters. *Alternative:* carry the saved
   parameters to every viewed method, which turns unknown keys into warnings and lets a shared key
   such as `dominance_check` cross methods silently.
6. **Anchors in the qualification example.** *Recommended:* fixed anchors for logistics cost (1.0
   to 6.0 NZD/unit), the practice the sorting warning recommends; tests cover the warning itself.
   Values move by at most 0.0036 from supplier selection (§11). *Alternative:* keep the local
   anchors, so the example shows the warning but models the practice the note advises against.

## Implementation notes

Implemented 29 October 2026 as designed, MAVT byte-identical (410 outputs; see the
[check record](../development/value-based-sorting-verification.md)). Where the code refines the
design:

- **Modules:** `domain/sorting.py` (the section), `methods/sorting/classes.py` (rule, result,
  audit sample, validation), `methods/sorting/sensitivity.py` (class changes and the probe),
  `ValueModelResult` and the sorting types in `domain/results.py`, `RecordEnvelopeV2` and
  `SortingAnalysisRecord` in `domain/analysis_record.py`.
- **`BASELINE_ON_CLASS_BOUNDARY`** is raised when an alternative's baseline *value* is within
  `1e-12` of a boundary (§6, wording corrected). Testing showed that a value on a boundary can sit
  several times `1e-12` away from the change point in *weight*, so a test on weights missed it.
- **`/api/meta`** lists each method's `export_tables`, so the frontend offers only the CSV tables
  the viewed method declares without hard-coding them.
- **`mcda validate`** also prints the saved method's own issues (for example the sorting rules)
  when the saved method is not MAVT; the project-wide report itself is unchanged.
- **Direction of a change below the baseline.** Lowering a weight past a change point leads to the
  class *below* it (`class_before`), raising it to the class above (`class_after`). An early draft
  of the CLI and the Sensitivity table showed `class_after` both ways; this was found while writing
  the browser case, fixed, and is guarded by a test and a mutant in each.
- **TypeScript.** A sorting sensitivity body is structurally a subtype of the MAVT one, so the
  generated union collapsed during inference. The frontend types the MAVT bodies with
  `method?: never` and narrows on `method`.
- **Classes editor IDs** are generated once from the name when a class is added and stay stable on
  rename, as for alternatives and criteria.
- **Example.** The supplier qualification classes, values and audit sample are exactly those in
  §11; its `build.py` imports supplier selection's build script.
