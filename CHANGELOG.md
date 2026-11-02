# Changelog

## Unreleased — Showcase design

- Add a start page with the four starters as cards, a branded app bar and a tidier projects table.
- Group the editor's screens into a Build, Analyse, Evidence and Decide sidebar; move the revision
  into **Details** and fold warnings into **Model checks** (errors still open automatically).
- Refresh the visual style and add README screenshots. No numerical, file-format or API change;
  every existing test passes unchanged.

## Unreleased — Release clean-up

- Lead the README with the general product description and starter gallery; move the Evidence
  Workspace and external-proposal paragraphs into Features.
- Stop distributing the original study report; keep its citation and summary. Add a disclaimer to
  the real-company example. Remove an empty tracked R history file. Replace local temporary paths in
  verification records with neutral wording.
- Defer the venture-screening study by owner decision; add gallery, proposal-review and
  with/without proxy tasks to the fresh-user protocol.

## Unreleased — Classifier agreement benchmark

- Add a standalone offline benchmark script: human agreement gate with exact kappa, coverage and a
  seeded grouped bootstrap; post-gate reference; exact confusion, abstention, majority-baseline and
  calibration summaries; sealed JSON, count CSV and escaped HTML reports.
- Publish strict version-1 manifest and report schemas; refuse reports the verifier could not
  reopen and malformed digests. Verify against independent no-application oracles, derived
  percentile bounds and nine reachable mutants; see the [record](docs/development/classifier-agreement-benchmark-verification.md).

## Unreleased — Disclosed model proxy criterion

- Add disabled, replayable disclosure plans, required sourced model-card reviews, explicit unknowns,
  licence compatibility, declared feature overlap and per-profile swing ratings.
- Add separate with/without MAVT, sorting and fixed-weight factor SMAA-2 pairs, retaining both
  completed halves or a whole-pair unavailable result, ordinary baseline bytes and all-draw coupling.
- Add local CLI/API, Compare workspace, explicit acknowledgements, permanent context invalidation,
  protected exports/reopening and Open Questions. Existing project/sidecar/result formats remain unchanged.
- Verify exact dyadic/rationally bounded decimal oracles, baseline and confidence invariance,
  installed parity and reachable mutants; see the [record](docs/development/disclosed-model-proxy-verification.md).

## Unreleased — Market research models and starter templates

- Add separately versioned quantity checks, scoped model-output runs and reviewed comparisons
  with distinct range meanings, persistent disagreement questions and one selected cell supplier.
  Keep source relationships descriptive; never average models or infer distributions from bounds.
- Add a four-item data-driven starter gallery with fresh review resets, intact worked examples,
  manifest/file verification, portable lineage, exclusive CLI exports and installed-package assets.
  The initial screening starter describes its existing two-option workflows; optional unattached
  simple-round arithmetic remains off by default with explicit checks and exclusions.
- Add graphical input/comparison review, scope and target-diff acknowledgements, checked factor
  runs, historical export/reopening and Open Questions. No old project/sidecar/result format changes.
- Record the owner's unchanged binary64 arithmetic clarification, exact engine-to-engine tests and
  independent rational forward-error bounds. Preserve the historical checkpoint (historical record, not included).
  The [finished verification record](docs/development/market-research-models-verification.md) records
  all gate, mutation, byte-identity, package and remaining-usability evidence.

## Unreleased — External proposals

- Add version-1 generic local JSON/CSV intake, immutable originals, source/model-card disclosure,
  confidence metadata and replayable review/registry history without changing existing formats.
- Add explicit accept/correct/reject review, filtered multi-selection, one event per selected
  proposal and complete confirmation. Block unresolved items, changed contexts and conflicting
  active cell claims; never infer weights from confidence or average disagreements.
- Add exact original/effective tool/human comparisons, Open Questions, acknowledged compilation
  through the existing evidence compiler and complete outer-bundle verification/export/reopening.
  Pending/rejected/blocked rows and annotations stay outside numerical aggregation.
- Add CLI confirmation digests, stateless bounded endpoints, Save/leave guards, published schemas,
  independent oracles and invented screening/supplier demonstrations. Earlier outputs remain
  byte-identical; all 13 new mutations are caught by the complete gate.

## Design review — accepted external inputs and research models

- Specify External proposals, Disclosed model proxy criterion, Classifier agreement benchmark
  and Market research models, including schema/sidecar boundaries, edge-case refusals, independent
  verification plans and numbered owner decisions. Add the four proposals to the roadmap without
  changing the implemented sequence. This was the design-only step; implementation is recorded
  in the entries above. The owner accepted all twenty recommendations with bulk-review and
  shipped-gallery amendments on 1 November 2026.

## Unreleased — fundamental-factor uncertainty integration

- Add separate factor-based MAVT, value-based sorting and SMAA-2 runs with fixed weights. Raw
  derived measurements use the ordinary Python value functions, tie and boundary rules; exact
  discrete enumeration and seeded sampling retain dependencies. Refuse double specification,
  unsupported combinations and invalid supports/draws without thinning the denominator.
- Retain the exact project/model/distribution inputs, seed, RNG and algorithm/environment
  versions, dependency declarations, draw count, deterministic inputs, sampled trace and full-run
  digest in a new version-1 run envelope, optionally with an existing decision/calculation
  snapshot. Existing project schemas and method outputs are unchanged.
- Add local inspect/run/verify endpoints and CLI commands, a minimal marginal/quantile-group
  editor with explicit review/export guards, historical reopening and derived-factor questions.
  No provider access or distributions inferred from evidence ranges.

## Unreleased — isolated fundamental-factor uncertainty evaluator

- Add a version-1 `FactorUncertaintyModel` bound to the project fingerprint and the deterministic
  model digest: accepted uniform, triangular or discrete distributions on source factors only, and
  explicitly reviewed quantile groups. Formula results are never given distributions.
- Add `factor_uncertainty_service` (`factor-sampling.v1`): validation and conservative interval
  preflight before any draw, seeded PCG64 sampling that is chunk-size and declaration-order
  invariant, one evaluation of every factor and formula per draw, exact enumeration for discrete
  factors, and typed refusal of any invalid draw with its index. Not yet used by any analysis,
  endpoint or screen; SMAA-2 is unchanged.

## Unreleased — calculation workspace: formula authoring and applying

- Add a version-1 calculation workspace: the starting project snapshot, the original model and an
  append-only history of unit, factor and formula definitions, reviews, removals, applications and
  rebinds, replayed in Python on reopening. Definitions never carry their own review, so a revised
  factor is pending until accepted again; units are never redefined.
- Author and review in **Measurements → Calculated measurements**: factors with source reference and
  human or identified-tool origin, formulas with optional targets, per-formula checks with
  plain-language dimensional explanations, dependency graphs, intermediate values and shared-factor
  usage. Accepting a formula requires it to calculate.
- Apply a reviewed calculation to the open project as one undoable edit. Python reruns the existing
  compilation gate; the applied project is byte-identical to the compiled copy, and the returned
  calculation bundle binds to it as `compiled` for decision records. Undo is recognised as an
  earlier bound revision; rebinding is explicit and recorded. Save is guarded while the workspace
  is unexported.
- New endpoints `POST /api/calculations/inspect`, `/propose` and `/apply`; no project-schema change.
- Refuse imported decision records containing NaN or infinity with `DECISION_RECORD_NONFINITE`
  instead of an HTTP 500.

## Unreleased — graphical decision records with artifact provenance

- Add a Decision tab and version-2 records: owner, date, selected or deferred outcome,
  alternatives considered, rationale, assumptions, triggers and at most six explicit analyses.
  Unavailable analyses are recorded with their reasons; feasibility failures and unresolved
  requirements are shown beside the choice without an override.
- Cite evidence compilation and calculation bundles (with copy receipts for imported copies).
  Artifacts anchor by exact fingerprints, including a calculation compiled on top of compiled
  evidence, and every measurement records which artifact set it and the value it replaced.
- Export, reopen and revise records: reopening re-verifies artifacts and re-derives anchors,
  trace, feasibility and notices; a revision names its predecessor, which is never changed.
  Version-1 records remain readable and revisable; the CLI still writes version 1.

## Unreleased — graphical evidence compilation and separate-copy provenance

- Compile reviewed evidence from the Evidence tab into a separate project copy. Show each target
  change with unit, current value and supporting claim; require explicit acknowledgement bound to
  the project, history, review intent and preview. `evidence_service.compile_copy` remains the gate.
- Export a version-1 evidence compilation bundle (original project, original dossier, appended
  reviews, exact preview, compiled copy, digests); the effective dossier is derived by replay.
  Reopening verifies the digest, replays history and reproduces compilation; a changed project is
  inspected historically, never rebound. The open project, its saved bytes and undo stay unchanged.
- Importing a project as a separate copy now returns a version-1 copy receipt recording the single
  project ID change. A binding service relates evidence and calculation bundles to the current
  project by exact fingerprints only: compiled, source, receipt-verified copy or different.

## Unreleased — reviewed calculation exports

- Compile a reviewed calculation preview through the interface into a downloadable static project
  copy. Show original-to-calculated target changes and require explicit acknowledgement before
  compilation. The Python digest/validation gate remains authoritative; no library writes occur.
- Export and reopen a calculation bundle containing the original project, reviewed model/trace
  and compiled output. Verify its digest and reconstruct compilation when reopening. Preserve
  calculation state across tabs; explicit recalculation invalidates the prior acknowledgement.
- Inspect formula review status and declared unit dimensions, including formulas blocked by
  rejected/missing factors. Live formula/factor editing and uncertainty propagation remain deferred;
  add the focused uncertainty design and independent verification plan without a sampler.

## Unreleased — integrated evidence review

- Add an Evidence Workspace with local dossier inspection, human/tool provenance, source
  classification, explicit accept/correct/reject previews and confirmation. Export/reopen a
  versioned bundle retaining the original project, original dossier and appended review history.
- Reuse Python validation and preview digests. Block stale-context reviews and protect unexported
  history on leaving. Read-only inspection/review endpoints never edit project/library files.
- Audit missing, unsupported, unverified and supported measurements separately; add actionable
  Open Questions for entered values without accepted matching claims. Independence does not imply
  correctness, and absent support does not imply numerical invalidity.
- Fix a platform-specific Open Questions wording test by comparing the threshold with the
  sensitivity service. Independent numerical checks and tolerances are unchanged.

## Unreleased — deterministic calculation foundation

- Add versioned local formula models with reviewed source factors, human/tool provenance, explicit
  dimensions, bounded arithmetic/min/max and dependency/cycle validation. CLI preview/compile
  creates a new static project copy after digest review; existing files are never replaced.
- Add a read-only calculation API and Measurements preview with formula/source explanations and
  a complete preview download. Include synthetic bottom-up market sizing and supplier TCO demos.
  Live in-project formulas, automatic recalculation and uncertainty propagation remain deferred.

## Unreleased — measurement-range analysis

- Screen accepted, matching numeric evidence ranges for possible rank or class changes using fixed
  anchors and existing MAVT and sorting rules. Report analytical boundary contacts, exact ratios, flat contact intervals and evaluated witnesses
  through CLI, API and editor. Unsupported ranges are explicit; multi-input robustness is not assessed. No probability distribution is inferred.

## Unreleased — evidence questions

- Open Questions can inspect a locally selected evidence dossier for unreviewed, outdated and
  conflicting claims. It reports provenance and refuses to use a stale or invalid dossier; viewing
  claims never accepts them or changes the project.

## Unreleased — class and uncertainty questions

- Open Questions now reuses class-boundary sensitivity and the original SMAA-2 inputs-to-check
  heuristic, retaining the run settings and warning that associations are not value of information.
  Unavailable analyses and exact enumeration are reported explicitly.

## Unreleased — Open Questions foundation

- Add a read-only Open Questions CLI, API and editor tab for missing measurements, unresolved
  mandatory requirements, one-way MAVT winner-change weights and method leader disagreements. It identifies signals not yet
  assessed and states the limits of one-way sensitivity.

## Unreleased — evidence sidecar foundation

- Add a versioned local evidence dossier and CLI preview/compile workflow. Claims retain source,
  origin, review and optional stated ranges; unreviewed or rejected claims never become inputs.
  Compilation checks the preview digest and writes a new file. Include synthetic VC and supplier
  dossiers. Add separate decision snapshots with analyses, rationale, optional evidence and revision
  links. This is a partial foundation; graphical review and record management remain outstanding.

## Unreleased — feasibility review follow-up

- Treat duplicate measurements for a required cell as unknown, rather than choosing the last
  entry. Show and allow retry of an unavailable feasibility check in the method comparison view.

## Unreleased — feasibility check

- Add the feasibility check: mandatory requirements on individual leaf measurements, in an optional
  `requirements` section of the project file (schema version 6, written only when used). A `bound`
  states a minimum, a maximum or both, each inclusive or exclusive, in the criterion's own unit,
  which must match exactly and is never converted; `labels` states the allowed labels, with "at
  least" and "at most" helpers for ordinal scales that write the explicit set.
- Each alternative passes, fails or is unknown for each requirement, with the reason (for example
  "51 NZD is above the maximum 45 NZD"); overall, any failure is fail, then any unknown is unknown.
  A missing or unusable measurement is unknown, never a failure. Limits are compared exactly. No
  method reads requirements, requirements read no weights, profiles, value functions or scenarios,
  and no score offsets a failure: no ranking is filtered, reordered or changed.
- Eight validation codes (`NO_REQUIREMENTS`, `DUPLICATE_REQUIREMENT_ID`,
  `UNKNOWN_REQUIREMENT_CRITERION`, `REQUIREMENT_SCALE_MISMATCH`, `REQUIREMENT_UNIT_MISMATCH`,
  `EMPTY_REQUIREMENT`, `INVALID_BOUNDS`, `UNKNOWN_REQUIRED_LABEL`) and the warning
  `REQUIREMENT_ALWAYS_PASSES`; they block only the feasibility result. Removing a criterion removes
  its requirements; removing a label is reported, never repaired.
- `POST /api/feasibility` (and per stored project), and `/api/feasibility/export` for the JSON
  document and a CSV with one row per alternative and requirement; edit operations
  `set_requirements` and `clear_requirements`. CLI: `mcda requirement bound|labels|remove|clear`
  and `mcda feasibility`; `mcda evaluate` and `mcda compare-methods` print each alternative's status
  beside the ranking.
- Frontend: a Requirements tab with the live result of the draft computed in Python, the status
  beside the ranking in Results with its own downloads, and a Feasibility column in the comparison.
- Add an independent feasibility oracle, reference, unit, API and CLI tests (57 Python),
  9 Vitest and 1 browser case, 14 `FEASIBILITY` mutants (`--feasibility-only`), and extend
  `scripts/byte_identity.py` to the method comparison: 969 outputs byte-identical to `61ff58e`. See
  `docs/development/feasibility-check-verification.md`.

## Unreleased — method comparison view

- Add the method comparison view: every registered method's own reading of one model, side by side,
  under the selected profile and scenario. Each column names its method, the inputs it read and its
  parameters, and shows each alternative's rank and quantity in that method's own terms (overall
  value, rank-1 acceptability with its interval, net flow, AHP priority), or the method's typed
  error (for example `VALIDATION_FAILED` with `AHP_NOT_STATED`). There is no consensus, average or
  aggregated score, and no number combines two methods.
- Agreement compares leading alternatives (SMAA-2's is its leader by rank-1 acceptability, not its
  MAVT reference ranking) and sorting's classes with SMAA-2's most frequent class. Where a method's
  leader differs from MAVT's, the reason comes from that method's own result: SMAA-2's rank-1
  acceptability, PROMETHEE II's explanation of the two leaders and PROMETHEE I incomparability, or
  AHP's own judgements and inconsistent matrices. Every view states that agreement between methods
  that share inputs is not independent validation.
- `POST /api/methods/compare` (and per stored project), with an optional method subset (422
  `UNKNOWN_REFERENCE` for an unregistered one), and `/api/methods/compare/export` for the JSON
  document and a long CSV, one row per alternative and method. CLI: `mcda compare-methods`.
- Frontend: a Compare tab with each column on its own axis and a link from a failed column to the
  editor that fixes it; a method editor opened by such a link now shows its tab.
- Add an independent comparison oracle, reference, unit, API and CLI tests (42 Python), 6 Vitest and
  1 browser case, 10 `COMPARISON` mutants (`--comparison-only`), `tests/builders.every_section`,
  and extend `scripts/byte_identity.py` to AHP: 789 outputs byte-identical to `209c703`. See
  `docs/development/method-comparison-verification.md`.

## Unreleased — AHP

- Add AHP (`ahp`, "AHP (pairwise priorities)") as the full method: criteria are judged in pairs
  within each sibling group of the project's criteria tree, and alternatives in pairs on each leaf,
  on Saaty's 1–9 scale. Local priorities are principal eigenvectors (power iteration in plain
  Python with `math.fsum`, tolerance 10⁻¹⁴, at most 10 000 iterations; failing to converge is a 422
  `AHP_NO_CONVERGENCE`, never a partial result). Matrices of one and two items are defined
  explicitly.
- Every matrix reports λmax, CI, RI and CR against the named Saaty and Tran (2007) random-index
  table for 1 to 15 items; a CR above 0.10 is a warning (`AHP_INCONSISTENT`), never an error, and
  each matrix names its most inconsistent triad by Koczkodaj's index with the value that would
  make it consistent.
- Global criterion priorities multiply down the tree; alternatives are synthesised in distributive
  mode by default or ideal mode (`synthesis`), with the ideal score kept. Results carry the label
  "AHP priorities under these pairwise judgements: shares of the goal that sum to one, not MAVT
  values or swing weights" and name no weight profile or scenario, because AHP reads neither.
- State judgements in a new optional `ahp` section (schema version 5, written only when used): each
  pair once, as the matrix entry that is at least 1, its reciprocal derived. Ten validation codes;
  measurements, value functions and profiles are not AHP inputs. Removing an alternative or
  criterion removes the judgements that name it; nothing is ever judged automatically.
- Version-2 `AhpAnalysisRecord` and exports with four CSV tables (`priorities`,
  `criterion_priorities`, `local_priorities`, `consistency`); a read-only `POST /api/ahp/preview`
  for one drafted matrix; edit operations `set_ahp_model` and `clear_ahp_model`. CLI:
  `mcda ahp judge|remove|clear|check` and `--synthesis` on `evaluate`.
- Frontend: a Pairwise editor tab on Saaty's verbal scale with a live consistency preview from
  Python and the most inconsistent triad's rows highlighted; AHP priorities and Consistency views;
  a header note that AHP reads no profile or scenario.
- Add an independent AHP oracle (exact fractions), the published 10 × 10 matrix of Kampourakis et
  al. (2025) and the random-index table printed by Nguyen (2020), both CC BY 4.0, LAPACK as an
  independent eigensolver, unit, reference, API and CLI tests (267 Python), 6 Vitest and 1 browser
  case, 15 `AHP` mutants (`--ahp-only`), and extend `scripts/byte_identity.py` to PROMETHEE II: 741
  MAVT, sorting, SMAA-2 and PROMETHEE II outputs byte-identical to `17b3c2d`. See
  `docs/development/ahp-verification.md`.

## Unreleased — PROMETHEE II

- Add PROMETHEE II (`promethee2`, "PROMETHEE II (outranking flows)"): alternatives ranked by net
  outranking flow, with the PROMETHEE I partial order (preferred, indifferent, incomparable) as a
  secondary view. Flows are normalised by n − 1, lie in [−1, 1], sum to zero, and carry the label
  "net outranking flows: these compare the alternatives with one another and are not preference
  values" everywhere. The shared `ranking` holds the PROMETHEE II order; its `value` is the net
  flow, and no view, table or CLI line shows it as a value.
- State PROMETHEE's own inputs in a new optional `promethee` section (schema version 4, written
  only when used): per leaf a direction, a weight (normalised by the sum), the usual, U-shape,
  V-shape or linear preference function with thresholds in the leaf's units, and a code for each
  label of a labelled leaf. Nothing is read from swing profiles or value functions. Thirteen
  validation codes cover missing or unknown entries, invalid thresholds and weights, codings, and
  inert or unordered criteria; MAVT's checks do not apply, and a missing measurement still blocks.
- Differences are compared with 0, q and p within `1e-12 × max(1, |x_a|, |x_b|)`, so a difference
  equal to a threshold in decimal counts as that threshold. Every sum uses `math.fsum`; the
  invariants are asserted on every result; a request computes at most 10⁶ preference degrees.
- An explanation against MAVT (the unchanged MAVT engine under the configured profile and
  scenario): the rank comparison and every pair the methods order differently, with the value gap,
  the flow gap split into head-to-head and via-others parts, and, for up to 50 pairs, each
  criterion's difference, zone (no preference, partial or full, naming q and p) and contributions
  in each method's own units, plus up to three generated reasons. It is omitted with MAVT's issue
  codes when MAVT's model is invalid; PROMETHEE II still runs.
- Version-2 `PrometheeAnalysisRecord` and exports with four CSV tables (`flows`,
  `criterion_flows`, `partial_order`, `explanation`). Sensitivity, scenario comparison and the
  previews refuse the method with 422.
- Edit operations `set_promethee_model` and `clear_promethee_model`; removing a criterion removes
  its entry. CLI: `mcda promethee criterion|remove|clear` and `--method promethee2` on `evaluate`.
- Frontend: an Outranking editor tab with each function's shape drawn from its thresholds, Flows,
  PROMETHEE I and Explanation views with a fixed [−1, 1] net-flow axis, and the MAVT editors'
  previews requested for `mavt` while PROMETHEE II is viewed.
- Add an independent PROMETHEE oracle (exact fractions from decimal strings), the two published
  examples as data with citations, unit, reference, API and CLI tests (234 Python), 12 Vitest and 1
  browser case, 17 `PROMETHEE` mutants (`--promethee-only`), and extend `scripts/byte_identity.py`
  to SMAA-2 at its default seed: 645 MAVT, sorting and SMAA-2 outputs byte-identical to `10c4215`.
  See `docs/development/promethee-ii-verification.md`.

## Unreleased — SMAA-2

- Add SMAA-2 (`smaa2`, "SMAA-2 (sampled acceptability)"): how often each alternative takes each
  rank, and each class when the project has classes, when stated inputs vary. Every draw is
  evaluated with the MAVT model; ranks are competition ranks and classes follow the sorting rule.
- State uncertainty in a new optional `smaa` section (schema version 3, written only when used):
  uniform, triangular, discrete and categorical distributions per measurement; fixed, unknown
  (uniform local weights) or rating-interval weights per sibling group; independence stated
  explicitly, with shared draws for inputs from one source. Twenty validation codes refuse
  supports outside the value-function domain, local anchors on uncertain criteria, bad
  probabilities, unknown or duplicate references, zero rating intervals and unsupported
  dependence. A missing measurement still blocks: a distribution never fills it.
- Runs vary the measurements, the weights or both (`uncertainty`), with `samples`, `seed` and
  `confidence` parameters. Sampling uses `PCG64(seed)`; values are summed in bulk and every
  near-tie draw again with `math.fsum`, so ranks and classes are exactly the reference path's.
  Discrete cases with at most 100 000 joint outcomes are enumerated exactly instead.
- Results report counts, frequencies and pure-Python Clopper–Pearson intervals (no SciPy at
  runtime), rank 1 split into sole and tied first, class acceptability, a labelled heuristic list
  of inputs to check, the seed, algorithm and environment, and the label "sampled acceptability
  under these assumptions" everywhere. Sensitivity and scenario comparison refuse the method
  with 422.
- Version-2 `SmaaAnalysisRecord` and exports with three CSV tables (`rank_acceptability`,
  `class_acceptability`, `inputs_to_check`). The record union is now told apart by a tagged
  discriminator that publishes a plain `oneOf`; MAVT and sorting bodies are unchanged.
- Edit operations `set_smaa_model` and `clear_smaa_model`; removing an alternative or criterion
  removes its stated uncertainty. CLI: `mcda uncertainty cell|group|share|clear` and `--samples`,
  `--seed` and `--uncertainty` on `evaluate`.
- Frontend: an Uncertainty editor tab, an Acceptability panel with intervals, bars and class
  shares, and SMAA-2 run settings in the analysis header as part of the transient view.
- Add an independent SMAA oracle (exact rational enumeration and binomial-tail intervals), unit,
  reference, API and CLI tests (86 Python), 9 Vitest and 1 browser case, 15 `SMAA` mutants
  (`--smaa-only`), and extend `scripts/byte_identity.py` to the sorting example: 565 MAVT and
  sorting outputs byte-identical to `a1a7d11`. See `docs/development/smaa-2-verification.md`.

## Unreleased — value-based sorting, and the rest of the method seam

- Add value-based sorting (`mavt_sorting`, "Value-based sorting (MAVT)"): ordered classes with
  numeric lower boundaries on the overall MAVT value. A value within 1e-12 of a boundary goes to
  the higher class. Boundaries must lie in [0, 1], decrease strictly and be more than 2e-12 apart;
  they are never reordered. Empty and single classes are valid. MAVT's values, ranks,
  contributions and dominance are carried over unchanged.
- Results report each alternative's class, its distance to the nearest boundary and whether it is
  on one; an optional audit sample lists alternatives below a cut-off class, chosen by the SHA-256
  of `"<seed>:<id>"`. Local anchors raise `SORTING_LOCAL_ANCHORS`, recommending fixed anchors.
  Twelve sorting validation codes, from `NO_SORTING_MODEL` to `INVALID_AUDIT_SAMPLE_SIZE`.
- Sensitivity and the probe add exact class changes: every change point, the first change when
  raising and when lowering the weight, the class-stable interval and the class at the probed
  weight. `BASELINE_ON_CLASS_BOUNDARY` flags a baseline value on a boundary.
- Complete the method seam: `/evaluate` returns a result union tagged by `method`; version-2
  analysis records (`SortingAnalysisRecord`) and exports (`export_version: "2"`) beside unchanged
  version-1 MAVT records; CSV tables declared per method (sorting adds `classes` and class columns
  in `ranking`), listed in `/api/meta` as `export_tables`.
- Project schema version 2 adds the optional `sorting` section. Files are written with the lowest
  sufficient version and omit absent sections, so MAVT-only projects keep their version-1 bytes and
  fingerprints. A version-1 file holding `sorting` is refused. `PUT /api/projects/{id}` accepts
  any version from the one the content needs up to the newest; `/api/health` reports version 2.
- Edit operations `set_sorting_model`, `clear_sorting_model` and `set_analysis_method` (which clears
  the previous method's parameters). CLI: `mcda classes set|audit|clear`, `mcda method`, and
  `--method` on `evaluate`, `sensitivity` and `compare`; `mcda validate` also shows the saved
  method's own issues.
- Frontend: a Method select in the analysis header (a transient view, with **Use viewed method as
  saved default** as one undo step), Results panels chosen by method, a Classes panel and a Classes
  editor, class bands on the ranking and sensitivity charts, a class-change table and classes in
  the probe readout. Viewing another method no longer triggers the swing-range review.
- Add the `supplier_qualification` example (supplier selection with fixed logistics anchors and
  three classes), bundled like the others. The three existing examples are byte-unchanged.
- Add an independent sorting oracle, unit, schema, property, API and CLI tests (84 Python), 25
  Vitest and 2 browser cases, 18 `SORTING` mutants (all 112 mutants killed) (`--sorting-only`) and
  `scripts/byte_identity.py`, which proves the 410 MAVT outputs byte-identical to `c170610`. See
  `docs/development/value-based-sorting-verification.md`.
- Housekeeping: GitHub Actions moved off Node 20 (`checkout` v7.0.1, `setup-python` v7.1.0,
  `setup-node` v7.1.0, `upload-artifact` v7.0.2); five CLI tests made independent of terminal width
  (messages matched on collapsed whitespace, tables rendered at a fixed width); the method seam's
  check record notes hosted run 40679505555.

## Unreleased — method seam (backend contract)

- Methods declare a label and capabilities from a closed vocabulary; MAVT declares six. `/api/meta`
  lists every registered method with its capabilities.
- Validation runs the method-independent checks and then the configured method's own `validate`.
  MAVT's checks moved behind it unchanged (same codes, paths, messages and order). An unregistered
  method is reported as `UNKNOWN_METHOD`, replacing `UNSUPPORTED_METHOD`.
- Methods parse their own parameters. MAVT reads `dominance_check` as a strict boolean: an unknown
  key now warns (`UNKNOWN_PARAMETER`) and a wrongly typed known key is an error
  (`INVALID_PARAMETER`) instead of being read by truthiness.
- Sensitivity, probes, scenario comparison and previews check a capability in the service layer, so
  the CLI and the API refuse alike. Version-1 analysis records and exports are refused for any
  method but MAVT. A refusal is 422 `METHOD_NOT_SUPPORTED` naming the method, the requirement and
  the method's capabilities; it replaces the unreachable 501. Previews no longer hard-code `mavt`.
- MAVT outputs are byte-identical for all three examples (164 compared outputs). The result union,
  version-2 records, the schema-version rule and the frontend method view arrive with value-based
  sorting. See `docs/development/method-seam-verification.md`.

## Unreleased — library backup and restore

- Add `mcda library backup --store DIR --to FILE.zip`, `mcda library verify FILE.zip` and
  `mcda library restore FILE.zip --to NEW_DIR`. A backup holds active projects, Recently deleted
  entries and a manifest of sizes, SHA-256 hashes, fingerprints and modification times.
  Unreadable and newer-schema files are kept byte for byte and reported.
- Backup takes library ownership (refused while a server runs), never follows symlinks, never
  writes inside the library and publishes with a no-overwrite hard link after verifying.
- Verify and restore refuse member names outside a fixed allowlist, duplicates (including
  case-only), symlink, encrypted and unknown-compression members, manifest mismatches, changed
  bytes and archives over constant limits enforced on actual bytes. Restore needs a new directory,
  writes with `O_EXCL | O_NOFOLLOW`, re-checks the result, and removes exactly what it created on
  a handled failure.
- `mcda serve` and app startup refuse a library holding `.mcda-restore-incomplete`.
- Exit status: `0` completed, `3` completed with warnings, `1` failed.
- Add unit, hostile-archive and real-process tests and 11 `BACKUP_BACKEND` mutants. See
  `docs/development/library-backup-verification.md`. No API, schema or numerical change.
- Make two backup CLI tests match phrases on collapsed whitespace: on hosted Linux, Rich wrapped
  the error message inside the phrase they looked for. Behaviour is unchanged.

## Unreleased — measurement coverage

- Add an alternatives × structural-leaf coverage table to the Model canvas. Presence and engine
  issues are independent: zero and qualitative labels count as entered; missing stays missing.
  Counts include collapsed branches and distinct known pairs, with separate setup/preference links.
- Open the existing measurement inputs or Inspector by stable ID; restore cell focus on return.
  Renames preserve selection; removal or a leaf becoming a branch clears it, including across undo.
- Page coverage and its measurement destination at 20 alternatives × 20 criteria. Navigation is
  transient and leaves project bytes, fingerprint and undo history unchanged.
- State “Evidence provenance not recorded”; coverage makes no confidence or quality claim.
- Add unit, component, real-backend browser, mutation and five-run performance checks. See
  `docs/development/measurement-coverage-verification.md`. No API, schema, Python, numerical or
  dependency change.
- Make the browser test for preview request isolation count only the criterion under test.
  Keyboard moves select as they focus, so on slower machines a leaf passed over for longer than the
  120 ms preview debounce legitimately requested its own preview; hosted CI counted it as a second
  request. Behaviour is unchanged.
- Fix the piecewise-linear property test's reference: `np.interp` overflows to `inf` on a
  subnormal span where the engine is correct, so the reference now uses exact rational arithmetic,
  and the counterexample is a pinned regression test. Engine code is unchanged.

## Unreleased — analysis retry and consolidated roadmap

- Add Retry to failed analysis requests: results, the scoped analysis check, sensitivity (sweep and
  probe) and scenario comparison. Retry re-sends the same request identity with a fresh signal and
  shows loading meanwhile. A retry captured under an older context does nothing. Retrying never
  edits the project, its fingerprint or its undo history. Previews are unchanged.
- Add Vitest, Playwright and mutation checks for Retry. See
  `docs/development/analysis-retry-verification.md`.
- Consolidate the roadmap (`ROADMAP.md`) around a general engineering decision workflow, with
  acceptance criteria for each near-term package, and align the README, handover, known
  limitations, user guide and plan. Dated records keep their content.
- No API, schema, dependency or numerical change.

## Unreleased — canvas value-tree diagram

- Redraw Canvas as a left-to-right value tree (goal → objectives → criteria) after the original
  study's value-tree figure, with a separate options column fed by one bracket from every leaf.
- Add Swing / Value fn shortcut chips to the existing weight-group and value-function editors, with
  Inspector keyboard routes; options open their existing name field.
- Show the engine's local weight, branch share and global weight on cards when weights are ready;
  selecting or collapsing never requests them. Add objectives-first structuring hints and a
  read-only presentation view of the live draft.
- No API, schema, dependency or numerical change. See `docs/design/live-model-canvas.md`.

## Unreleased — package D1

- Add Canvas/Outline structural model views with a synthetic goal and existing editing destinations.
- Reflect accepted edits and undo/redo; add stable-ID keyboard selection, collapse/reveal and setup/issues.
- Keep long labels readable, honour reduced motion and render malformed hierarchies safely.
- Add interaction, request-isolation, large-tree and installed-GUI checks; no numerical/API/schema changes.
- Fix: a focus request for a disabled field (clicking the goal while a rename's edit is pending) now
  waits until the field is enabled instead of being lost, and yields to any control focused meanwhile.
- Fix: `mcda sensitivity --all -o` now takes the same library ownership as other CLI result outputs.
- See `docs/development/package-d1-verification.md`; D2 coverage remains unimplemented.

## Unreleased — package C1

- Add POSIX lifetime library ownership and cooperating managed-directory CLI write protection.
- Restore deleted projects without overwriting active files; retain recovery entries in both restore modes.
- Add Recently deleted listing, restore/copy actions, conflict/unreadable messages and API contracts.
- Add process, interruption, backup-drill, browser and mutation checks; preserve numerical logic/schema.
- See `docs/development/package-c1-verification.md` and `library-recovery.md`.

## Unreleased — package B

- Bundle the GUI and three examples in wheel and source distributions; support installed resource lookup.
- Add build identity and actionable startup diagnostics; open browsers after server readiness.
- Add hash-pinned Python 3.12 environments, archive/build checks, isolated venv/pipx GUI smoke tests and Linux CI configuration.
- Preserve project schema and numerical logic. Verification is recorded in `docs/development/package-b-verification.md`.
- Fix: a server restarted promptly on the same port no longer fails with "Address already in use"
  from connections left in TIME_WAIT (`SO_REUSEADDR` on POSIX, as uvicorn uses); a port with a
  live listener is still refused.

## 0.1.0 — 2026-10-26

First public release: a complete local additive MAVT application.

- **Generic engine.** Arbitrary-depth value trees; categorical, ordinal, interval and ratio
  scales; linear, piecewise-linear, qualitative and direct-rating value functions; fixed and local
  anchors with explicit out-of-domain policy.
- **Weighting.** Hierarchical swing weighting with several independent preference profiles and
  atomic reference repair.
- **Sensitivity.** One-way analysis with exact closed-form crossovers, stability intervals and a
  read-only probe.
- **Scenarios.** Sparse value-function overrides and profile references, compared with Base.
- **Results.** Linked ranking, weighted contributions, partial-value heatmap and dominance.
- **Exports.** Full-precision JSON, formula-safe CSV and labelled SVG, all verified against a
  completed record.
- **Persistence and API.** Versioned JSON project files (schema 1) with conflict-aware saves, a CLI
  (`mcda`) and a documented HTTP API.
- **Verification.** 616 Python, 234 frontend and 67 browser tests; 64 of 64 mutants killed; three
  examples checked against independent oracles.

This release also renamed the VC reference example to `examples/nz_deeptech_vc/` and reorganised
the documentation.

## Development milestones (before the first release)

These milestones were developed privately. Test counts are those recorded when each milestone was
verified.

| Milestone | Delivered | Python / frontend / browser tests, mutants |
| --- | --- | --- |
| Stage 1: engine | Generic domain model, MAVT value functions and weighting, exact one-way sensitivity, JSON persistence, CLI, VC and supplier oracles | 190 / — / — / 9 |
| Stage 2A: application | FastAPI service, React editor, project lifecycle, validation navigation, undo/redo, save conflicts | 353 / 115 / 24 / 19 |
| B0–B1: context and previews | Shared analysis context with stale-response protection; read-only value-function and weight previews | 402 / 142 / 28 / 19 |
| B2: value-function editor | Linked graphical/tabular editor with atomic Apply and save guards | 445 / 162 / 38 / 19 |
| B3: weighting and profiles | Swing cards, authoritative branch shares, multiple profiles, infrastructure oracle | 486 / 181 / 43 / 29 |
| B4: sensitivity | Interactive one-way sensitivity workspace and exact probe | 532 / 193 / 48 / 41 |
| B5: scenarios | Scenario management, sparse overrides, comparison with Base | 563 / 210 / 54 / 50 |
| B6: results and exports | Linked charts, heatmap, dominance, reproducible JSON/CSV/SVG exports | 612 / 233 / 63 / 62 |
| B7: release acceptance | Integrated GUI acceptance, recovery and performance evidence, tie-reporting fix | 616 / 234 / 67 / 64 |
