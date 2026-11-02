# Roadmap

**Status:** consolidated 27 October 2026; sequence revised by owner decision on 28 October 2026
(see [owner decisions](#owner-decisions-28-october-2026)). Proposals carry no dates or release
numbers. The
code-backed plan (historical record, not included) keeps the detailed specifications: for
completed work (installation and startup, library ownership and recovery, the visible model) and
for the method phases. Verification evidence lives in the
[validation records](docs/development/validation.md). Where this page and older documents differ,
this page sets the direction and order. Dated records keep their original content and package codes.

Status labels used below:

- **Implemented**: the code is in this repository.
- **Verified**: automated checks are recorded: tests, independent oracles, the mutation harness and
  hosted CI where stated. **No human usability checkpoint has passed yet.**
- **Proposed**: specified here or in the plan; nothing is built.

## Direction

MCDA Studio is a general **engineering decision-making workspace**. It supports technical design,
procurement, technical diligence and investment-related decisions without depending on any firm,
sector or geography. The numerical engine stays domain-neutral. Domain knowledge lives in worked
examples and templates. A framework for domain packs, plugins or methods is added only when a
concrete use case needs it. The original venture-screening study remains a regression example with
its provenance; it does not set the product's audience.

## The workflow

Frame the decision → define requirements → model alternatives and preferences → review evidence →
analyse trade-offs → record a choice → revisit assumptions.

| Stage | Today | Next work |
| --- | --- | --- |
| Frame the decision | **Partial.** Project title and description, an objectives-first canvas with structuring hints. Implemented and verified | The decision record captures who decides and on what basis |
| Define requirements | Mandatory requirements on individual measurements (numeric bounds in the criterion's unit, allowed labels), each alternative pass, fail or unknown beside every ranking, never inside a score. Implemented and verified 31 October 2026 | Requirements on combinations of measurements, only on evidence of need |
| Model alternatives and preferences | Value trees, four scale types, value functions, hierarchical swing weights, profiles and scenarios, with measurement coverage on the canvas. Implemented and verified (oracles, mutation harness, hosted CI for the engine) | Evidence workflow for where measurements come from |
| Review evidence | Evidence Workspace reviews local claims, compiles acknowledged changes into a separate exported copy with a reproducible bundle, and verifies imported copies through receipts; the CLI path remains | Durable sidecar management |
| Analyse trade-offs | Ranking, contributions, partial values, dominance, exact one-way sensitivity, scenario comparison and retry after a failed request. Implemented and verified | Uncertainty, only on evidence of need |
| Record a choice | **Partial.** CLI decision snapshots retain rationale, analyses and optional evidence | Record browser and exports |
| Revisit assumptions | **Partial.** CLI snapshots retain assumptions and review triggers | List and surface triggers |

## Three different kinds of "not known"

These are never converted into one another. Missing is not a range, a range is not a disagreement,
and a disagreement is not averaged.

| Kind | Example | Handling today | Planned |
| --- | --- | --- | --- |
| Missing measurement | A supplier has not reported a defect rate | Validation error; ranking unavailable; never zero. Measurement coverage shows where | The evidence workflow lists what to collect. Never imputed |
| Measurement uncertainty | A mass of 4.2 ± 0.3 kg, or two vendors' conflicting claims | SMAA-2 accepts stated distributions; the CLI evidence dossier records claims and ranges without treating ranges as distributions | Integrate reviewed evidence with uncertainty analysis while preserving dependencies |
| Stakeholder preference differences | Two reviewers weight cost differently | Separate weight profiles and scenarios, each with its own results | A side-by-side profile comparison is optional later work |

## Sequence

### Owner decisions, 28 October 2026

The owner decided to build the method track now, without waiting for its triggers, and to finish
with an in-depth worked example in the venture-screening domain. The earlier trigger-gated order
(AHP → PROMETHEE II → value-based sorting → SMAA) is replaced by the order below. The triggers in
each method's section are kept as what to watch for when real users try the methods.

1. **Cross-method verification** is the organising idea: one decision model, examined through
   several methods, showing where they agree and why they differ. Methods are never averaged into
   a consensus score, and one method's weights are never reused as another's (see
   [not planned](#not-planned)).
2. **Method order:** method seam → value-based sorting → SMAA-2 → PROMETHEE II → AHP → method
   comparison view. Sorting is small and maps onto class decisions; SMAA reuses the MAVT engine and
   addresses uncertainty; PROMETHEE II adds a check where strong criteria cannot simply offset weak
   ones; AHP adds pairwise elicitation, compared with swing weighting.
3. **The trade-study example becomes a venture-screening study**, developed from the original
   study. It is the flagship case that exercises every method, the feasibility check, the evidence
   workflow and the decision record. Venture-specific content stays in the example; the engine
   stays domain-neutral.
4. **Public release:** a new public repository created from a single commit of the finished tree.
   This working repository stays private with its full history.

### Owner decisions, 1 November 2026

All twenty recommendations in the four linked design notes are accepted. Bulk proposal review
adds explicit filtered multi-selection, one review event per selected item, full confirmation and
blocked-item exclusion. The starter gallery describes only workflows present in the shipped build,
with no placeholder items. Implementation order: External proposals → Market research models and
starter templates → Disclosed model proxy criterion → Classifier agreement benchmark → the
invented flagship study. Existing project/sidecar/result formats and earlier outputs stay pinned;
work stops for an owner decision if those boundaries or the accepted substance must change.
Each development has its complete gate, verification record and local commit; no push or release.

Every development keeps the same process: a design note, owner review, implementation, the full
gate and a check record.

### Sequence

| Order | Development | State |
| --- | --- | --- |
| 1 | **Analysis retry** | Implemented and verified 27 October 2026 ([record](docs/development/analysis-retry-verification.md)) |
| 2 | **Measurement coverage** | Implemented and verified 27 October 2026 ([record](docs/development/measurement-coverage-verification.md)) |
| 3 | **Library backup and restore** | Implemented and verified 27 October 2026 ([record](docs/development/library-backup-verification.md)) |
| 4 | **Method seam** | Implemented and verified: backend contract 28 October 2026 ([record](docs/development/method-seam-verification.md)); the result union, version-2 records, schema-version rule and method view 29 October 2026, with sorting ([design note](docs/design/method-seam.md)) |
| 5 | **Value-based sorting** | Implemented and verified 29 October 2026 ([design note](docs/design/value-based-sorting.md), [record](docs/development/value-based-sorting-verification.md)) |
| 6 | **SMAA-2** | Implemented and verified 30 October 2026 ([design note](docs/design/smaa-2.md), [record](docs/development/smaa-2-verification.md)) |
| 7 | **PROMETHEE II** | Implemented and verified 31 October 2026 ([design note](docs/design/promethee-ii.md), [record](docs/development/promethee-ii-verification.md)) |
| 8 | **AHP** | Implemented and verified 31 October 2026 as the full method ([design note](docs/design/ahp.md), [record](docs/development/ahp-verification.md)) |
| 9 | **Method comparison view** | Implemented and verified 31 October 2026 ([design note](docs/design/method-comparison.md), [record](docs/development/method-comparison-verification.md)) |
| 10 | **Feasibility check** | Implemented and verified 31 October 2026 ([design note](docs/design/feasibility-check.md), [record](docs/development/feasibility-check-verification.md)) |
| 11 | **Evidence workflow** with the **decision record** | Graphical evidence review, compilation and bundle export with history, support audit and receipt-verified separate copies ([design](docs/design/evidence-workspace.md), [copies](docs/design/separate-copy-provenance.md)); graphical version-2 decision records with analyses, feasibility, cited bundles, measurement trace and linked revisions ([design](docs/design/decision-records.md)). Record browsing, signing and library storage remain |
| — | **Open Questions** | Partial: read-only CLI, API and editor view for missing inputs, feasibility, one-way weight/class changes, SMAA-2 heuristics, method disagreement, local dossier gaps and fixed-anchor measurement-range crossings ([design](docs/design/open-questions-follow-up.md)) |
| — | **Derived measurements** | Reviewed local formula models, dimensions/dependencies, CLI compilation and graphical preview/compile/export with reproducible bundles ([design](docs/design/derived-measurements.md)); a graphical calculation workspace authors, reviews and applies formulas as one undoable edit with replayable history ([design](docs/design/calculation-workspace.md), [record](docs/development/calculation-workspace-verification.md)); fundamental-factor sampling and exact enumeration are verified against independent answers ([plan](docs/design/derived-uncertainty-verification-plan.md)); separate factor-based MAVT, sorting and SMAA-2 runs, reviewed marginal/group editing and replayable decision/run snapshots are implemented ([integration record](docs/development/factor-uncertainty-integration-verification.md)); weights remain fixed |
| — | **External proposals** | **Implemented and locally verified 1 November 2026**: generic JSON/CSV imports, mandatory individual or filtered bulk review, exact comparisons, Open Questions and separate-copy compilation ([design](docs/design/external-proposals.md), [record](docs/development/external-proposals-verification.md)) |
| — | **Market research models** | **Implemented and locally verified 1 November 2026**: reviewed model ranges, persistent disagreements, checked factor runs and four data-driven starter templates with lineage ([design](docs/design/market-research-models.md), [record](docs/development/market-research-models-verification.md)) |
| — | **Disclosed model proxy criterion** | **Implemented and locally verified 2 November 2026**: off-by-default reviewed proxy plans, model-card/overlap disclosures, explicit swings and paired with/without analyses ([design](docs/design/disclosed-model-proxy-criterion.md), [record](docs/development/disclosed-model-proxy-verification.md)) |
| — | **Classifier agreement benchmark** | **Implemented and locally verified 2 November 2026**: standalone offline script, synthetic cohorts, independent oracles, published version-1 schemas and nine reachable mutants ([design](docs/design/classifier-agreement-benchmark.md), [record](docs/development/classifier-agreement-benchmark-verification.md)) |
| 12 | **Venture-screening study** (the flagship trade study) | Proposed — deferred by owner 2 November 2026; planned after the first public release |
| 13 | **Public release** | A new public repository from one commit of the finished tree |
| — | **Fresh-user checkpoint** | Protocol ready; **pending a participant**. Can run at any point; no human result is claimed until it does |

Hosted CI was green for the method seam's backend contract (run 40679505555, 29 October 2026).

### The method seam

Built first, before any second method ([design note](docs/design/method-seam.md)):
- a separate result type for each method;
- method-owned validation and declared capabilities;
- a typed "method not supported" error;
- result panels chosen by method.

MAVT results stay byte-identical for unchanged inputs. Each method's development section below
sets its scope and acceptance criteria. The full specifications are in
plan §5–§9 (historical record, not included).

### Optional and deferred

- **Optional, small:** SMARTER rank-based weights; a profile comparison view; a decision-risk
  register built from sensitivity crossovers; a one-page decision memo export; OpenAPI
  declarations for every error response. The first three are candidates for the venture-screening
  study.
- **Deferred until a design exists:** durable recovery of unsaved drafts.
- **Deferred until a use case requires it:** domain packs, sector calculators (for example
  ownership and dilution arithmetic) and an optional local assistant. External model scores as
  proxy criteria are now covered by the off-by-default disclosed model proxy.

## Developments

### Analysis retry: implemented and verified

- **Scope:** a Retry action on failed requests for results, the scoped analysis check, sensitivity
  (sweep and probe) and scenario comparison. It re-sends the same request identity. A Retry captured
  under an older context does nothing, and the request debounce keeps repeated clicks to one request.
- **Acceptance (met):** Retry shows loading, then the engine result; it never edits, saves or adds
  undo history; a late answer to a superseded request never appears; after the project changes, a
  Retry requests the current context only.
- **Verification:** 9 Vitest cases, 3 Playwright cases against the real backend, and 3 new mutants.
- **Excluded:** previews (Weights, value-function and canvas weights still re-request on the next
  edit); Save, which already had its own retry.

### Fresh-user checkpoint

- **Scope:** someone other than the author installs the app cleanly and builds a fresh decision in
  any domain: at least two objectives, three leaf criteria and three alternatives. The protocol is
  in plan §2 (historical record, not included).
- **Depends on:** nothing. Measurement coverage (done) makes the missing-input tasks easier to observe.
- **Acceptance**, each observed directly and completed unaided or with at most one recorded hint:
  - **Build:** reaches a model with zero validation errors and evaluates it.
  - **Missing inputs:** with one measurement left blank, finds it, states the missing count and
    explains why ranking is unavailable. Says that an entered zero counts as entered.
  - **Explain results:** explains the top alternative's position using its two largest weighted
    contributions. States that scores are preferences, not probabilities or predictions.
  - **Sensitivity:** for one criterion, reads the exact crossover weight and names which
    alternatives swap. Says that one-way sensitivity does not cover changing several weights at once.
  - **Control:** identifies the active profile and scenario; undoes, saves, reopens and restores a
    deleted test project.
  - **Gallery:** starts a project from the starter gallery, says which starters exist and that a
    fresh illustrative project starts with no reviews or runs.
  - **Proposal review:** reviews imported external proposals, accepting one, correcting one and
    rejecting one, and explains that confidence is metadata, never a weight.
  - **With/without proxy:** runs a disclosed model proxy comparison and explains that the original
    project stays the baseline and both readings are shown, not averaged.
- **Verification:** a dated session record in `docs/development/` listing tasks, outcomes, hints,
  misunderstandings and resulting fixes. Critical misunderstandings, such as reading a score as a
  probability or missing as zero, are fixed before any method expansion.
- **Excluded:** statistical claims from one participant; a screen-reader audit (separate); any
  judgement of decision quality.

### Measurement coverage: implemented and verified

- **Scope:** an alternatives × leaf-criteria matrix on the canvas showing missing, entered and
  entered-with-issues cells. Counts include collapsed branches. Each cell opens the existing
  measurement editor; unconfigured criteria lead to setup. Large models page (20 × 20), and so does
  the Measurements editor they open. Semantics follow
  [the canvas design](docs/design/live-model-canvas.md), where this work is called "connected
  coverage".
- **Depends on:** the visible model (done). No schema, API or numerical change.
- **Acceptance (met):** numeric zero counts as entered; an empty model never shows 100%; navigating,
  selecting and paging never edit the project or trigger evaluation; focus returns correctly; the
  wording never presents coverage as confidence or quality.
- **Verification:** 35 Vitest cases, 4 Playwright cases against the real backend, 4 new mutants,
  and five-run timings on 50 × 40 and 100 × 100 models, all within budget
  ([record](docs/development/measurement-coverage-verification.md)).
- **Excluded:** evidence status, sources or confidence (the evidence workflow); editing inside
  cells beyond the existing editor.

### Library backup and restore: implemented and verified

- **Scope:** `mcda library backup --store DIR --to FILE.zip` (projects, `.trash/` and a manifest of
  ID, fingerprint, schema version, size, hash and modification time), `mcda library verify
  FILE.zip`, and `mcda library restore FILE.zip --to NEW_DIR`. Rules are in the
  [design note](docs/design/library-backup-and-restore.md).
- **Depends on:** library ownership and recovery (done).
- **Acceptance (met):** a round trip preserves every byte, fingerprint and modification time;
  verify detects a changed, missing, extra or duplicated file; restore refuses any existing
  target; backup respects the running server's library ownership; `mcda serve` refuses an
  incomplete restore.
- **Verification:** 47 unit cases (including every hostile-archive case), one real-process case,
  11 mutants (one per guard), and the tool-based recovery drill in
  [library recovery](docs/development/library-recovery.md).
- **Excluded:** scheduled backups, cloud storage, encryption and a GUI.

### Venture-screening study (flagship trade study)

**Deferred by owner 2 November 2026; planned after the first public release.** Nothing below is
built yet.

- **Scope:** a new example developed from the original study: a screening decision across several
  early-stage companies with
  - deal-breaker screens (the feasibility check);
  - sourced evidence claims, each accepted or left open (the evidence workflow);
  - MAVT with at least two partner profiles and one scenario;
  - classes such as Invest / Watch / Pass (value-based sorting);
  - SMAA-2 under stated weight and measurement uncertainty;
  - a PROMETHEE II cross-check, and AHP priorities compared with the original swing weights;
  - a decision record.

  It ships with `build.py`, a README that states where every number comes from, and an
  independent oracle for each method.
- **Depends on:** every development above it in the sequence.
- **Acceptance:** evaluates identically through the CLI and the GUI; each oracle lives in
  `tests/regression` and does not import `mcda_studio`; it is bundled like the other examples;
  packaging and smoke checks are updated.
- **Verification:** regression oracles per method; distribution smoke including the new example.
- **Excluded:** venture-specific logic in the engine (for example dilution arithmetic), decision
  rules tied to any firm, outcome or success predictions, and non-public information about real
  companies. Whether companies are named from public sources or anonymised is an open decision.

### Feasibility check: implemented and verified

Built 31 October 2026 as the [design note](docs/design/feasibility-check.md) decides (requirements
in the project file, open decision 2, and all seven decisions accepted as recommended): bounds and
allowed labels on leaf measurements, pass, fail or unknown per alternative and requirement with
exact comparison at every limit, its own route and exports, and the status beside every ranking.
Verification: an independent oracle at every exact limit and one floating-point step either side,
byte identity of every earlier output including the comparison, and 14 new mutants
([record](docs/development/feasibility-check-verification.md)). The scope below was the proposal.

- **Scope:** mandatory requirements on leaf measurements, such as a numeric bound with units or a
  required category. Each alternative is evaluated as **pass, fail or unknown**. A missing
  measurement is unknown, never fail. Requirements are checked **outside** aggregation: they do not
  depend on weights, profiles or value functions, and no score can compensate for a failed one. The
  ranking stays visible, with feasibility shown beside it and never hidden inside it.
- **Distinct from sorting:** value-based sorting assigns classes from the *aggregate* value against
  thresholds on the overall scale. Feasibility tests *individual measurements* against hard limits.
  They are different developments, and sorting stays in the method track.
- **Depends on:** the method seam; a storage decision (see open
  decisions).
- **Acceptance for the design note:** it covers requirement types, inclusive and exclusive bounds,
  units, unknown handling, scenarios, sensitivity (requirements are unaffected by weights), exports,
  and schema migration or sidecar compatibility.
- **Verification once built:** a plain-Python oracle; boundary tests at exact limits, unit errors
  and missing values; mutants for `≤` versus `<`, unknown treated as fail or pass, and a failed
  requirement compensated by a score.
- **Excluded:** soft constraints and penalties, class sorting, probabilistic feasibility.

### Evidence workflow

- **Scope:** a sidecar file linked to the project by fingerprint. It holds claims with alternative
  and criterion IDs, value and unit, source (a URL or a local document reference), excerpt,
  location, retrieval date and kind (observed, judgement or proxy). Several claims may target one
  cell. Each claim is explicitly accepted, rejected or superseded, with actor and time. Accepted
  claims compile deterministically into a **copy** of the project after a reviewed diff. The output
  includes a missing-information checklist and a dossier. It starts as a CLI and file format; a
  review screen follows.
- **Depends on:** nothing numerical; it uses the existing edit operations.
- **Acceptance:** conflicting claims leave the cell missing until one is accepted; compiling twice
  gives byte-identical output; rejected claims never compile; unit conversions are explicit; every
  compiled measurement traces to exactly one accepted claim; the source project never changes.
- **Verification:** unit and property tests (idempotence, claim-order independence), round trips, a
  CLI acceptance script, and mutants for "rejected claim compiles", "latest claim silently wins" and
  "missing cell filled".
- **Excluded:** automated or AI extraction, confidence used as a multiplier, web fetching,
  multi-user review.

### Decision record

- **Scope:** an append-only local record containing:
  - the chosen alternative and a written rationale;
  - the decision owner and date;
  - the model fingerprint and the analysis-record digest it relied on, with its profile and scenario;
  - the evidence digest, once the evidence workflow exists;
  - unresolved assumptions, including missing cells;
  - a review trigger, as a date and/or a condition.
  It exports as JSON and Markdown.
- **Depends on:** the existing analysis-record digest; the evidence workflow is optional at first.
- **Acceptance:** an unknown alternative is refused; later edits never alter a record; the app shows
  "model changed since this decision" when fingerprints differ; due review triggers are listable; a
  revision is a new record linked to its predecessor.
- **Verification:** unit and immutability tests, CLI acceptance, and mutants for an overwritten
  record and an ignored fingerprint mismatch.
- **Excluded:** approval workflows, notifications, multi-user use, outcome analytics.

### AHP: implemented and verified

Built 31 October 2026 as the [design note](docs/design/ahp.md) decides: the owner chose the full
method (open decision 5) and accepted all nine recommended decisions. Judgements live in an
optional `ahp` section (schema version 5); priorities are eigenvectors by power iteration with a
LAPACK cross-check, CR uses the Saaty and Tran (2007) table, and synthesis is distributive by
default with ideal as a parameter. Verification: a published CC BY matrix reproduced, an exact
oracle, byte identity of every earlier method, and 15 new mutants
([record](docs/development/ahp-verification.md)). The scope below was the proposal.

- **Trigger (to watch for; built ahead of it by owner decision):** at the fresh-user checkpoint or
  later, people cannot express weights as swings over
  stated ranges, distrust them, or ask to compare options in pairs.
- **Scope:**
  - **Judgements:** pairwise judgements on the 1/9–9 scale, stored as upper-triangle entries.
    Reciprocals are derived, never stored.
  - **Priorities:** from the principal eigenvector, with a stated tolerance.
  - **Consistency:** the consistency index, and a ratio against a named random-index table. A
    ratio above 0.10 is a warning, not an error. Matrices of size one and two are defined
    explicitly.
  - **Editor:** a pairwise editor with verbal labels and a live consistency preview computed in
    Python. It identifies the most inconsistent triad.
  - **Form, decided when triggered:**
    - an **elicitation view**, whose pairwise questions are about swings over the stated ranges, so
      the resulting weight profile keeps its MAVT meaning;
    - a **full method**, which also compares options in pairs for each leaf criterion and
      synthesises them, distributive mode by default.
- **Depends on:** a schema migration for stored judgements in either form; the method seam for the
  full method.
- **Acceptance:**
  - Published worked examples reproduce their printed priorities and consistency ratios.
  - Every result names its random-index table and synthesis mode.
  - MAVT results stay unchanged for unchanged inputs.
  - Migrated projects keep every ID, judgement, profile and scenario.
  - A blank-to-export GUI case passes: enter matrices, see and fix a consistency warning, evaluate,
    save, reopen and export.
- **Verification:**
  - Oracles: published examples and a consistent 3 × 3 matrix, plus an independent eigensolver
    cross-check.
  - Tests for convergence failure.
  - Mutants for a wrong reciprocal, an off-by-one random-index lookup, unnormalised priorities and
    swapped synthesis modes.
- **Excluded:** treating consistency as proof of validity; using a full AHP model's priorities as
  MAVT weights; group aggregation of judgements; ANP.

### PROMETHEE II: implemented and verified

Built 31 October 2026 as the [design note](docs/design/promethee-ii.md) decides (all seven owner
decisions accepted as recommended): PROMETHEE's own directions, weights, preference functions and
codings live in an optional `promethee` section (schema version 4); net flows rank the
alternatives, PROMETHEE I is the secondary view, and the explanation compares orders with MAVT pair
by pair, splitting each flow gap into its head-to-head and via-others parts. Verification: two
published examples (Podvezko and Podviezko 2010; Flachs and De Smet 2026) reproduced, an
independent exact oracle, invariants on every result, byte identity of MAVT, sorting and SMAA-2,
and 17 new mutants ([record](docs/development/promethee-ii-verification.md)). The scope below was
the proposal.

- **Trigger (to watch for):** a decision needs checking against a method where strong criteria cannot simply offset
  weak ones. This happens when reviewers dispute whether a large advantage should make up for a poor
  result, or when incomparability between options matters.
- **Scope:**
  - **Ranking:** a net-flow ranking, with the PROMETHEE I partial order as a secondary view.
  - **Preference functions:** usual, U-shape, V-shape and linear first, with indifference and
    preference thresholds in each criterion's units.
  - **Weights:** per-criterion weights of its own, stored separately from swing profiles.
  - **Inputs:** raw performances with a direction. Categorical criteria need an explicit ordinal
    coding.
  - **Explanation view:** shows which criteria and thresholds make its ranking differ from MAVT's.
- **Depends on:** the method seam; a published worked example, sourced as an oracle before any code.
- **Acceptance:**
  - Flows lie in [−1, 1] and net flows sum to zero.
  - Flows are never shown as preference values, never averaged with MAVT scores and never given
    swing weights.
  - The explanation names the criteria and thresholds behind each difference in rank.
  - MAVT results stay unchanged.
  - Migration follows the same rules as AHP.
  - A blank-to-export GUI case passes.
- **Verification:** the published example and an independent plain-Python oracle; invariant tests;
  mutants for swapped indifference and preference thresholds, flows not divided by n − 1, and an
  ignored minimise direction.
- **Excluded:** PROMETHEE III–VI and GAIA; consensus scores across methods; treating agreement on
  shared inputs as independent validation; shipping without the explanation view.

### Value-based sorting: implemented and verified

Built 29 October 2026 as the [design note](docs/design/value-based-sorting.md) decides (all six
owner decisions accepted as recommended), with the rest of the method seam. Verification: 84 new
Python tests, 25 Vitest and 2 browser cases, an independent oracle on the new supplier
qualification example, MAVT byte identity over 410 outputs, and 18 new mutants
([record](docs/development/value-based-sorting-verification.md)). The scope below was the
proposal.

- **Trigger (to watch for):** people decide by class, such as Go / Hold / Stop or qualify / reject, rather than by
  a full ranking, or already apply cut-offs to the overall score.
- **Scope:**
  - **Classes:** ordered classes with numeric boundaries on the overall value scale. A value
    exactly on a boundary, within the existing 1e-12 tolerance, goes to the higher class.
  - **Boundaries:** must be strictly ordered and more than twice the tolerance apart. They are
    never silently reordered.
  - **Results:** each option's class and its distance to the nearest boundary.
  - **Sensitivity:** adds the exact weight at which each option first changes class.
  - **Anchors:** a warning recommends fixed anchors, because with local anchors adding an option
    can move others between classes.
  - **Audit sample:** a sample of options below a cut-off, so that false negatives can be reviewed.
  - **Display:** class bands on the ranking and sensitivity charts, and a class column in CSV.
- **Depends on:** the method seam, or the part of it sorting needs; a sorting variant of an existing
  example (for example supplier qualification), with the original fixtures unchanged. It is
  distinct from the feasibility check, which tests individual measurements against hard limits.
- **Acceptance:**
  - Classes match a plain-Python oracle at, just above and just below each boundary.
  - Empty and single classes are valid.
  - Invalid boundaries are refused with a clear message.
  - Class-change points match exact roots.
  - MAVT values stay unchanged.
- **Verification:** the oracle, boundary and tie tests, and mutants for `<` versus `≤` at a
  boundary, an inverted class order and a class-change root with the wrong sign.
- **Excluded:** boundaries defined by reference options (a later option that needs crossing rules);
  learning thresholds from past decisions (research); ELECTRE TRI.

### SMAA: implemented and verified (SMAA-2)

Built 30 October 2026 as the [design note](docs/design/smaa-2.md) decides (all six owner
decisions accepted as recommended): stated ranges live in an optional `smaa` section (schema
version 3), rank and class acceptability ship together, and small discrete cases are enumerated
exactly. Verification: an independent oracle, the analytic 3/7 case, exact intervals checked
against SciPy, byte identity of MAVT and sorting, and 15 new mutants
([record](docs/development/smaa-2-verification.md)). The scope below was the proposal.

- **Trigger (to watch for):** measurement or preference uncertainty, rather than missing data, keeps a decision
  open. For example, accepted ranges or unresolved conflicting claims make reviewers ask how often
  the leading option stays ahead.
- **Scope:** a written specification comes before any sampling. It covers:
  - **Uncertain inputs:** analyst-stated ranges or distributions for unresolved measurements, and
    for weights where wanted. A missing measurement stays missing unless the analyst supplies an
    explicit model. Bounds alone are never treated as a distribution.
  - **Separate runs:** performance, preference and combined uncertainty run separately.
  - **Dependence:** stated explicitly. Unsupported dependence is refused, not assumed away.
  - **Outputs:** rank and class acceptability frequencies with exact (Clopper–Pearson) intervals,
    a recorded seed and environment, and the label "sampled acceptability under these assumptions".
  - **Inputs to check:** a list of the uncertain inputs most likely to change the decision,
    labelled as a heuristic.
- **Depends on:** a way to record unresolved inputs with stated ranges, which comes with the
  evidence workflow; value-based sorting for class acceptability, though rank acceptability can
  come first.
- **Acceptance:**
  - The analytic two-weight case reproduces its known crossover at 3/7.
  - Enumerable discrete cases match their exact probabilities.
  - Zero observed events give a non-zero upper bound.
  - Reruns with the same seed are identical in the pinned environment.
  - No output is called a probability of success or a value of information.
- **Verification:** those analytic cases; tie, interval, malformed-distribution and dependence
  tests; mutants for rank and tie handling, a wrong distribution and an ignored seed. Any vectorised
  path must first match the existing exact summation.
- **Excluded:** proofs of robustness over every admissible weight (a separate method); central
  weights and confidence factors until they are defined; correlated or MCMC sampling; distributions
  inferred automatically from data.

### Method comparison view: implemented and verified

Built 31 October 2026 as the [design note](docs/design/method-comparison.md) decides (all six
owner decisions accepted as recommended): a read-only route runs each method through its own
record builder and lays the results side by side, with typed errors per column, agreement on
leaders and classes only, and reasons from each method's own result. Verification: an independent
oracle against every method's own `/evaluate` body, byte identity of every earlier method, and 10
new mutants ([record](docs/development/method-comparison-verification.md)). The scope below was the
proposal.

- **Scope:** one model shown through every method that supports it: MAVT ranking, sorting classes,
  SMAA rank acceptabilities, PROMETHEE II net flows and AHP priorities, side by side. It marks
  where the methods agree on the leading option and class, and where they differ, with the
  method-specific reason (for example a PROMETHEE II veto-like preference threshold, or an SMAA
  rank-1 acceptability below one half).
- **Depends on:** the method seam and at least two methods beyond MAVT.
- **Acceptance:** no averaged or consensus score; every column names its method, inputs and
  parameters; a method that does not support the model says so with its typed error; MAVT results
  are unchanged.
- **Verification:** component and browser tests on the supplier and venture-screening examples;
  mutants for a silently dropped method and a mislabelled column.
- **Excluded:** consensus scores, rank aggregation across methods, and reusing one method's weights
  in another.

## Optional research (needs evidence first)

- Learning a sorting model from recorded decisions (preference disaggregation, robust ordinal
  regression), reported as consistency with N examples. It needs a history of decision records.
- MACBETH-style elicitation.
- Assisted evidence extraction: only after a human-labelled audit shows acceptable precision and
  reviewers catch seeded errors. Its output is always proposals into the evidence workflow.
- Staged decisions, real options and portfolio questions: these need defensible probabilities and
  payoffs.
- DECERNS behavioural comparison: needs authorised access; it is not a dependency.

## Not planned

- Outcome or success-probability predictions as the engine's output.
- Model-generated scores or weights entering an analysis without explicit acceptance.
- Consensus scores averaged across methods, or one method's weights reused in another.
- Fuzzy variants and ELECTRE, for now.
- Generic plugin or domain-pack frameworks ahead of a concrete need.
- Decision rules or profiles tied to any organisation.

## Open decisions

1. **Fresh-user participant:** who it will be, and when.
2. **Where feasibility requirements live:** *decided 31 October 2026:* in the project file, as an
   optional `requirements` section (a tested schema migration).
3. **Where evidence and decision-record files live:** beside each project in the library, or in a
   separate folder.
4. **Companies in the venture-screening study:** named from public sources only, every number
   sourced and the study marked illustrative; or anonymised composites built from the original
   study's data (recommended for the public version).
5. **AHP form:** *decided 31 October 2026:* the full method. The weight-elicitation view can follow
   if the fresh-user checkpoint asks for it.
6. **Timing of the public release.**
