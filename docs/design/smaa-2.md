# SMAA-2: sampled acceptability under stated uncertainty

**Status:** accepted design, 29 October 2026; **implemented** 30 October 2026 (see the
[implementation notes](#implementation-notes) and the
[check record](../development/smaa-2-verification.md)). The owner accepted all six
[decisions](#decisions) on 30 October 2026, as recommended.

SMAA-2 (stochastic multicriteria acceptability analysis) asks how often each alternative takes
each rank, and each class, when uncertain inputs are drawn from distributions the analyst states.
It is the next method in the owner's order of 28 October 2026 and comes through the
[method seam](method-seam.md) like [value-based sorting](value-based-sorting.md). The earlier
proposal is plan §9 (historical record, not included); the roadmap section "SMAA" sets the
scope. Where they differ, this note wins.

The specification comes first (§1–§5). Nothing is sampled until it is accepted.

## What exists today

- **One deterministic MAVT engine.** `prepare_mavt` produces the partial-value matrix, local and
  global weights and resolved domains; `overall_values` sums with `math.fsum`; `rank_values` gives
  competition ranks with the `1e-12` tolerance. Value-based sorting assigns classes from those
  values with `class_index`.
- **The method seam, complete.** A method declares capabilities (`acceptability` is already in the
  vocabulary), owns its validation and parameters, returns a tagged result, writes a version-2
  record and declares its CSV tables; the frontend picks panels by method; projects are written at
  the lowest schema version that can hold them.
- **One value per cell.** A measurement is a single number or label. A missing measurement is a
  validation error, never imputed. Nothing in the project records a range, a distribution or a
  dependence between inputs.
- **Randomness:** none anywhere in the engine. NumPy 2.x is a runtime dependency; SciPy is a
  development dependency only (independent cross-checks), so no runtime code may use it.

## Goals and non-goals

**Goals:**

- Rank acceptability `b_i^r` (how often alternative `i` takes rank `r`) and, when the project has
  classes, class acceptability, under stated uncertainty in measurements, in weights, or both,
  each run separately.
- Exact (Clopper–Pearson) intervals for every reported frequency, a recorded seed, sample count,
  algorithm version and environment, and identical output for the same seed in the pinned
  environment.
- Every output labelled "sampled acceptability under these assumptions". Never a probability of
  success, a confidence that a choice is right, or a value of information.
- A short, labelled heuristic list of the uncertain inputs most associated with the leading
  alternative's rank-1 frequency.
- **MAVT and sorting byte-identical** for unchanged inputs, proved with `scripts/byte_identity.py`.

**Non-goals (excluded):**

- Proofs that a conclusion holds for every admissible weight (a different, optimisation-based
  method); central weight vectors and confidence factors until they are defined; correlated,
  copula or MCMC sampling; distributions inferred from data; imputing a missing measurement.
- Uncertainty in value functions, scales or class boundaries (only measurements and weights).
- Scenario comparison of acceptabilities (a candidate for the method comparison view).

## Design

### 1. What is uncertain, and how it is stated

Uncertainty is stated as data, owned by the SMAA method (seam §8). Where it is stored is
decision 1; the content is the same either way:

- **Measurement uncertainty, per cell** (alternative × leaf), replacing that cell's single value
  in SMAA runs only:
  - `uniform` on `[lower, upper]`;
  - `triangular` with `lower ≤ mode ≤ upper`;
  - `discrete`: listed values with probabilities summing to 1 (numeric scales);
  - `categorical`: listed labels with probabilities summing to 1 (labelled scales).

  The support must lie inside the leaf's value-function domain; a distribution that reaches
  outside it is a validation error, never clamped. A cell without a stated distribution keeps its
  entered value. A missing measurement stays missing and still blocks the run: a distribution is
  not a way to fill it.
- **Preference uncertainty, per sibling group** (decision 2):
  - `fixed`: the profile's ratings, as in MAVT;
  - `unknown`: local weights uniform on the group's simplex, `Dirichlet(1, …, 1)`, the classical
    SMAA "no preference information" assumption;
  - `rating_intervals`: each raw swing rating uniform on a stated `[lower, upper]`, then normalised
    within the group; a draw whose ratings are all zero is refused, not skipped.

  These are different probability measures over weights, and the result says which was used.
- **Dependence** is stated, never assumed silently (decision 3). The section has
  `dependence: "independent"` (every cell and every group drawn independently) and, optionally,
  **shared-draw groups**: listed cells that use one common uniform draw through their own
  quantile functions, for inputs from one source. Anything else is refused with
  `UNSUPPORTED_DEPENDENCE`.
- **Local anchors:** a leaf whose effective function uses local anchors cannot have uncertain
  cells, because its anchors would move draw by draw. That is an error
  (`SMAA_LOCAL_ANCHORS_UNCERTAIN`) recommending fixed anchors.

### 2. Runs and parameters

SMAA's parameters (method-owned, in `analysis.parameters`):

| Parameter | Meaning | Default |
| --- | --- | --- |
| `uncertainty` | `"performance"`, `"preference"` or `"combined"`: which stated inputs vary in this run | `"combined"` |
| `samples` | number of draws, 1 000 to 100 000 | 10 000 |
| `seed` | non-negative integer | 0 |
| `confidence` | interval level | 0.95 |

A performance run keeps every group `fixed`; a preference run keeps every cell at its entered
value. A run with nothing uncertain under its setting is an error (`NOTHING_UNCERTAIN`), not a
trivial 100 %.

### 3. Sampling and evaluation

- **Generator:** `numpy.random.Generator(PCG64(seed))`, one stream, drawn in a fixed order: for
  each draw, groups in tree order, then cells in alternative-then-leaf order, then shared groups.
  The order, the algorithm name (`smaa2.pcg64.v1`) and the NumPy version are recorded.
- **Evaluation** reuses MAVT: per draw, partial values from the sampled measurements through the
  same evaluators, global weights through the same weighting code, overall values and competition
  ranks with the same tolerance, and classes with `class_index` when the project has classes.
- **Exactness rule** (decision 4). Overall values are computed in bulk with NumPy, then every draw
  in which two alternatives (or an alternative and a class boundary) lie within `1e-9` of each
  other is re-evaluated with `math.fsum`, and ranks and classes come from that. Ranks and classes
  are then exactly those of the reference path. A test runs both paths on every example and
  requires identical rank and class counts.
- **Ties:** competition ranks, as everywhere. A row of rank acceptabilities sums to 1, but a rank
  column can sum above 1 because tied alternatives share a rank. Rank 1 is also reported split
  into *sole* and *tied* first place. Ties are never split fractionally.
- **Exact enumeration** (decision 5): when every stated input is discrete or categorical and the
  joint outcome space has at most 100 000 combinations, the result is computed exactly by
  enumeration instead of sampling, and labelled exact.

### 4. Outputs

`SmaaResult` (`method: "smaa2"`) contains:

- **Rank acceptability:** per alternative and rank, the count, the frequency and its
  Clopper–Pearson interval; sole and tied first place.
- **Class acceptability** when the project has classes (decision 6): per alternative and class,
  the same.
- **Provenance:** run kind, sample count (or "exact enumeration" and the number of outcomes),
  seed, algorithm, confidence level, the full uncertainty specification used, dependence, the
  environment (Python, NumPy, platform) and the project fingerprint.
- **Inputs to check (heuristic):** for each uncertain input, the leading alternative's rank-1
  frequency in draws where that input's quantile is above versus below one half. The five largest
  absolute differences are listed and labelled "heuristic: association in these draws, not
  causation or value of information".
- **The label** "sampled acceptability under these assumptions" on every table, chart, export and
  record.

**Intervals.** Clopper–Pearson, from the exact binomial tails, computed in pure Python (bisection
on the binomial cumulative distribution summed with `math.fsum` in log space), with no SciPy at
runtime. Zero observed events give a lower bound of 0 and a non-zero upper bound; all events give
an upper bound of 1 and a lower bound below 1. Tests compare with `scipy.stats.beta.ppf`. Exact
enumeration reports the probability with no interval.

### 5. Reproducibility

The same project, configuration and seed in the pinned environment give byte-identical results
and records. Other NumPy versions or platforms are not promised identical streams; the record
states the environment so a difference can be explained. A request can be cancelled (the
existing request identity and abort), and a cancelled run returns nothing partial.

### 6. Storage and schema

Under the recommendation for decision 1, an optional `smaa` section joins the project, with
`SECTION_VERSIONS["smaa"] = 3`: a project that states uncertainty is written as schema version 3;
every other project keeps the version it has today (1, or 2 with classes). Migration 2 → 3 is the
identity and refuses a version-2 file holding `smaa`.

### 7. Method, records, API and CLI

- **Method** `smaa2`, label "SMAA-2 (sampled acceptability)", capabilities `value_functions`,
  `swing_weights` and `acceptability`. No `weight_sensitivity`, `contributions`, `value_scores` or
  `scenario_comparison`: those routes refuse it with 422, as the seam requires.
- **Validation:** MAVT's checks first (the deterministic model must be complete and valid), then
  the uncertainty rules (§1), then parameters.
- **Record:** `SmaaAnalysisRecord`, version 2, calculation path `smaa2.pcg64.v1`; CSV tables
  `rank_acceptability`, `class_acceptability` (when classes exist) and `inputs_to_check`.
- **Bounds:** samples × alternatives × leaves ≤ 10⁸ per request; the existing results limits
  apply. Timings for 10 000 draws on the 50 × 40 performance fixture are recorded.
- **API:** `/evaluate` returns `SmaaResult` in the union; edit operations to set and clear cell
  distributions and group uncertainty; `/api/meta` lists the method and its tables.
- **CLI:** `mcda uncertainty set-cell|set-group|clear`, `mcda evaluate --method smaa2
  [--samples N --seed S --uncertainty performance|preference|combined]`.

### 8. Frontend

- An **Uncertainty** tab, shown when the viewed method is SMAA-2 or the project states
  uncertainty: a per-cell distribution editor reached from Measurements and coverage, a per-group
  weight-uncertainty editor beside Weights, and the dependence setting.
- An **Acceptability** panel: the rank-acceptability table with intervals, stacked bars per
  alternative, class acceptability when there are classes, the run's provenance and the
  inputs-to-check list, all under the required label. No 0–1 "score" axis is reused from MAVT.
- Python computes every frequency and interval; the browser only draws them.

### 9. The cross-method rules

SMAA-2 reads the MAVT model and its own section. It never averages its frequencies with MAVT
values, never presents them as a score, and never feeds them into another method.

## Verification plan

- **Analytic two-weight case:** the two-option model whose rank order switches at cost weight
  3/7, with the group `unknown`: rank-1 acceptability is 4/7 and 3/7. Sampled frequencies must
  contain these in their intervals at several seeds; exact enumeration is not possible here.
- **Enumerable cases:** discrete-only inputs computed by exact enumeration, compared with a
  hand-derived oracle exactly (rational arithmetic), and sampled runs of the same cases checked
  against them with their intervals.
- **Intervals:** zero and all events; small and large `n`; comparison with SciPy to `1e-12`.
- **Reproducibility:** the same seed twice gives identical bytes; a different seed differs.
- **Exactness rule:** the bulk path with fsum re-evaluation equals a pure fsum path on every
  example, rank for rank and class for class.
- **Malformed inputs and dependence:** every validation code; unsupported dependence refused;
  all-zero rating draws refused; out-of-domain support refused; missing measurements still block.
- **Oracle:** `tests/regression/smaa_oracle.py`, plain Python with its own generator-free
  enumeration and its own interval code, not importing `mcda_studio`.
- **Byte identity:** MAVT and sorting outputs on every example, against the previous commit.
- **Frontend and browser:** the Uncertainty editor, the Acceptability panel and its label, and a
  GUI case from blank: state ranges, run, read acceptabilities with intervals, export.
- **Mutants** (`--smaa-only`): rank and tie handling (sole and tied first place merged; ties split
  fractionally), a wrong distribution (uniform used for triangular), an ignored seed, a vectorised
  path without the fsum re-evaluation, Clopper–Pearson replaced by a Wald interval, a performance
  run that also varies weights, and an all-zero rating draw skipped instead of refused.

## Acceptance

- The 3/7 case is reproduced; enumerable cases match exactly; zero events give a non-zero upper
  bound; the same seed gives identical output in the pinned environment.
- Every output carries the label; nothing is called a probability of success.
- MAVT and sorting outputs are byte-identical; the full gate is green; every new mutant is killed.

## Decisions

Accepted by the owner on 30 October 2026, as recommended ("accept all").

1. **Where analyst-stated ranges live before the evidence workflow exists.** *Recommended:* an
   optional `smaa` section in the project file (schema version 3, written only when used). Ranges
   are then fingerprinted, versioned, undoable and reproduced from one file, and the evidence
   workflow can later compile accepted ranges into it. *Alternatives:* a sidecar file linked by
   fingerprint, which keeps the project unchanged but makes every SMAA record depend on two files
   staying in step; or method parameters, which are lost when another method is viewed and would
   carry per-cell data in the configuration.
2. **Weight uncertainty kinds.** *Recommended:* `fixed`, `unknown` (uniform local weights per
   group) and `rating_intervals`, chosen per sibling group. *Alternative:* only `unknown`, the
   classical SMAA default; simpler, but it cannot express "cost matters more than risk, but by an
   uncertain amount".
3. **Dependence.** *Recommended:* independence stated explicitly, plus shared-draw groups for inputs
   from one source; everything else refused. *Alternative:* independence only, which cannot
   express two claims that stand or fall together.
4. **Evaluation path.** *Recommended:* bulk NumPy values with `math.fsum` re-evaluation of every
   near-tie draw, so ranks and classes are exactly the reference path's at bulk speed.
   *Alternative:* `math.fsum` for every draw, simpler but much slower on large models (to be
   measured before choosing), with a lower sample cap.
5. **Exact enumeration for small discrete cases.** *Recommended:* yes, below 100 000 joint
   outcomes; it makes "enumerable cases match exactly" literal and gives users exact numbers when
   they are cheap. *Alternative:* sampling only, with enumerable cases checked statistically.
6. **Class acceptability now.** *Recommended:* yes. Sorting exists, classes come from the same
   `class_index`, and the cost is one more table. *Alternative:* rank acceptability first, as the
   roadmap allows, with classes in a later slice.

## Implementation notes

Implemented 30 October 2026 as designed; MAVT and sorting byte-identical (565 outputs; see the
[check record](../development/smaa-2-verification.md)). Where the code refines the design:

- **Modules:** `domain/uncertainty.py` (the `smaa` section), `methods/smaa/validation.py`
  (parameters and the 20 rules), `methods/smaa/engine.py` (sampling, the exactness rule, exact
  enumeration, inputs to check), `methods/smaa/intervals.py` (Clopper–Pearson); `SmaaResult` and
  `SmaaAnalysisRecord`.
- **`ranking`** in `SmaaResult` is MAVT's reference ranking at the entered measurements and the
  profile's ratings; acceptabilities never enter it. **`classes`** carries the class bands (as the
  sorting result does) rather than bare IDs, so exports name the classes.
- **The record union** is told apart by a callable discriminator (version 1, or the version-2
  method name). Pydantic writes a nested discriminator as an object inside an OpenAPI mapping,
  which is not valid OpenAPI; the tagged form publishes a plain `oneOf`. The MAVT and sorting
  record bodies are unchanged.
- **Run settings in the GUI** (uncertain inputs, draws, seed) are part of the transient view
  (`AnalysisSelection.parameters`), like the viewed method; choosing another method clears them.
  The saved parameters are set through the CLI or the API.
- **Edits** replace the whole section (`set_smaa_model`, `clear_smaa_model`), as for classes; the
  Uncertainty editor applies a draft as one undo step. Removing an alternative or criterion also
  removes its stated uncertainty, as it removes its measurements.
- **Class acceptability** needs valid classes: when the project has a sorting section, its rules
  are checked under SMAA-2 too.
- **Exact enumeration** uses the probabilities as exact fractions normalised to sum to one, so a
  stated 0.1 + 0.2 + 0.7 is a distribution, and the oracle does the same.
- **Measured:** 10 000 draws on the 50 × 40 performance fixture with ten uncertain cells and
  unknown top-level weights take a median of 0.27 s (five runs).
