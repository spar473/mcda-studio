# Classifier agreement benchmark

**Accepted — implemented and locally verified 2 November 2026** ([record](../development/classifier-agreement-benchmark-verification.md)). This is an offline script under
`scripts/`, outside the application and numerical engine. It evaluates imported labels for a
predefined task and split. It neither calls a model nor predicts outcomes for a decision project.

## Problem and scope

External classifiers can agree with one reviewer while the task itself is ambiguous. A benchmark
must first establish human–human agreement, disclose coverage and uncertainty, then compare an
external tool with a reviewed reference under a frozen evaluation protocol and trivial baseline.
Measure what the task defines; preference labels are not objective outcomes. Even high agreement
is not proof of truth, independence or generalization to a different population.

## Data model and schema/sidecar impact

Publish a standalone version-1 benchmark manifest schema. It records task definition and
instructions, ordered label vocabulary, unit of observation, population/time cutoff, entity/group
key, eligibility/exclusions, split method and immutable train/development/test item IDs, review
protocol, agreement statistic, declared threshold, confidence level, bootstrap seed/algorithm and
replicate count, adjudication policy, tool identity/version/card digest, and input file digests.
Input tables are `items`, long-form `human_labels` (item, reviewer token, label or abstention,
review time), `tool_outputs` (item, label or abstention, run time, optional score/probabilities),
and post-agreement `adjudications` (item, reference label, rationale, reviewer tokens, time).
Reviewer tokens are anonymous IDs, never real names in repository fixtures.

Only synthetic or appropriately licensed public data and invented labels are committed. Real data
and reports derived from it stay outside the checkout. The script refuses real-data inputs or
output paths inside the repository. Public data requires manifest source, licence and snapshot
hash; synthetic fixtures explicitly declare generation rules/seed. Paths are resolved before the
location check, including symlinks. No project, evidence or app schema changes or migrations are
needed. Unknown benchmark versions are refused; test manifest/report version-1 round trips and
all current project fixtures unchanged. Future report schema changes need explicit migrations
rather than reinterpretation of historical runs.

## Exact protocol and edge cases

1. Freeze the task, labels, split, observation cutoff and threshold **before** inspecting external
   outputs. Human reviewers label independently, blind to tools and each other. Evaluate human
   agreement on the held-out eligible items, before adjudication; retain all raw labels.
2. With two reviewers use unweighted Cohen's kappa for nominal labels; with three or more use
   Fleiss' kappa on a complete, fixed-size reviewer panel. Mixed panel sizes are refused initially.
   Report observed agreement, chance agreement, kappa, label marginals, coverage, counts and a 95%
   confidence interval. The CI uses a predeclared item/group bootstrap (10,000 replicates, fixed
   seed, percentile endpoints and explicit quantile algorithm); all labels for one item/entity
   move together. No resampling individual labels as if they were independent observations.
3. Recommend requiring the lower confidence bound to be at least 0.60 **and** complete-label
   coverage at least 80% before these labels can serve as the benchmark reference. This is an
   operational owner choice, not a universal statistical standard. Report coverage by class as
   well; the task's exclusions and abstentions cannot be silently hidden to improve agreement.
   Missing/abstaining human labels are omitted only from the complete-panel agreement subset,
   with the excluded IDs/reasons/counts retained. They are not another nominal task class.
4. If kappa is undefined (including chance agreement one), the CI cannot be estimated, coverage is
   too low or the threshold fails, output a reproducible **reference refused** report. Stop before
   tool-versus-reference scores, state the reason and recommend revising the task/review process.
   Do not relabel a poor-agreement reference “ground truth”. Do not tune the threshold after seeing
   results. Report how many bootstrap replicates were undefined; refuse the CI if any are
   undefined initially, rather than silently dropping them or changing its denominator.
5. Only after this gate, adjudicate disagreements under the frozen policy and record the rationale.
   An unresolved reference item is excluded from reference-based metrics, explicitly counted and
   listed. Coverage is reported against both all eligible test items and scorable reference items.
   No training/development data, entity overlap or post-cutoff feature leaks enter the test split.
6. For each tool show the full confusion matrix with an abstention column; per-class precision,
   recall and support; overall abstention and coverage; micro/macro summaries with definitions;
   and the majority-class baseline selected from the **training split**, with a declared stable
   vocabulary-order tie rule. Recall includes abstentions in its denominator. Precision uses
   predicted positives. Zero denominators produce `null`/“undefined” with counts, never zero or
   one. Absent classes remain visible; report metrics as unavailable when no reference exists.
7. Calibration is conditional on a score's declared semantics. A normalized full class-probability
   vector permits multiclass Brier score and fixed-bin reliability tables on the test split;
   unit-interval confidence in the chosen label permits correctness reliability only. Arbitrary
   numeric scores are reported as **not calibration-eligible**. Missing scores stay missing;
   score coverage is explicit. Bins, inclusion of exact endpoints and any class weighting are
   frozen in the manifest. Initial reliability bins are [0,.1), …, [.9,1], with observed count,
   mean reported probability and empirical frequency; no isotonic fitting on the test split.
8. The report includes manifest and every input digest, script/algorithm/environment versions,
   seed, bootstrap count, eligibility/exclusion ledger, raw count tables and a canonical digest.
   Repeated supported-environment runs reproduce bytes (exclude wall-clock execution time from
   the sealed report; retain tool run timestamps as supplied inputs). No claims about an outcome
   probability, causal validity or performance on a new population are made.

## Arithmetic and frozen numeric conventions

The [arithmetic contract](derived-measurements.md#arithmetic-contract) applies to verification.
This standalone script computes counts, coverage, Cohen/Fleiss agreement, kappa, confusion metrics,
Brier scores and reliability-bin summaries as exact `Fraction` values. Supplied decimal probability
or confidence values are parsed exactly from their decimal text; they are never sample weights.
The initial protocol requires probability vectors to sum exactly to one (published input-validation
tolerance **zero**), with no normalization or label coercion. This is a data-contract choice,
not a numerical-oracle tolerance. Reliability bins use exact decimal boundaries [0,.1), …, [.9,1].

Bootstrap resampling uses 10,000 seeded PCG64 replicates over sorted stable item/group IDs. Every
replicate's agreement statistic is rational; percentile endpoints use their nearest binary64
values and the declared linear quantile algorithm at .025 and .975. The operational lower-bound
gate compares that computed binary64 endpoint exactly with binary64 .60; coverage compares exact
rationals with 4/5. Display approximations are binary64. Reports identify these boundaries and
retain exact rational strings. Independent endpoint oracles derive forward rounding bounds;
replay, permutation invariants and repeated exports use exact equality, without a tolerance.

The fixed reviewer panel is declared globally. Missing rows and explicit abstentions are excluded
only from the complete-panel subset and retained in the coverage ledger; they never change the
panel size. Item resampling requires one item per entity; repeated entities require grouped
resampling. All labels for an item and all items in a group move together. Every undefined
replicate refuses the interval. Adjudication references the exact passed human-gate digest and
occurs after its declared confirmation time, while still blind to tool outputs. These local
protocol statements and supplied timestamps are provenance, not authenticated signatures.

## CLI, API and UI

Proposed command: `python scripts/classifier_agreement_benchmark.py --manifest FILE --output NEW_DIR`.
Inputs and outputs are local files; exclusive directory creation prevents overwriting a report.
Outputs are JSON, CSV count tables and a readable static HTML report with the human-agreement gate
at the top. There is no app API, UI, project import or provider endpoint. The report labels its
reference as human-reviewed task labels and distinguishes agreement, accuracy and calibration.
Reading it never imports model scores into a decision project.

Refuse duplicate item/reviewer labels, unknown labels/IDs, contradictory manifests, mismatched
hashes, overlapping entity splits, invalid timestamps/cutoffs, unsupported panel designs,
nonfinite/out-of-range scores, incomplete probability vectors, sums outside the published numeric
tolerance, leaked adjudications, wrong task/model versions, unsafe real-data locations and
partially valid input batches. No automatic label coercion, imputation or best-run selection.
An external tool's own confidence is never a sample weight.

## Verification plan

Independent fixtures compute confusion counts and Cohen/Fleiss expected agreement in exact
`Fraction` arithmetic, with no application imports; compare kappa and the metric denominators.
Use tiny enumerated resampling fixtures as an oracle for bootstrap endpoints, plus a second
independent bootstrap implementation for seeded larger cases. Properties cover permutation
invariance, symmetric human-reviewer swaps, split disjointness, class-label renaming, abstention
accounting, probabilities summing to one and byte reproducibility. Test empty/single-class panels,
undefined kappa, rare classes, all abstentions, score endpoints and the threshold immediately
below/at/above its limit. Use synthetic human disagreement to demonstrate reference refusal.

Mutants bypass the human gate, evaluate on training items, select the baseline from test labels,
drop abstentions from recall, replace undefined with zero, resample labels independently, discard
undefined bootstrap draws, use confidence as a weight or omit an input digest. Each must fail its
targeted suite; the unmodified copy must pass. Run the complete application gate as a compatibility
check even though this script is outside the application, and publish a dated verification record.

## Excluded

Model execution/training, network access, real repository datasets, investor profiles, outcome
prediction, claims that human labels are objective truth, automatic calibration/retraining,
post-hoc threshold optimization, performance leaderboards and app integration.

## Open owner decisions

1. **Agreement gate:** recommend lower 95% kappa bound ≥0.60 and complete-panel coverage ≥80%,
   fixed before testing; any change requires a new protocol/report version.
2. **Panel/CI:** recommend Cohen for two, Fleiss for a fixed larger nominal panel, 10,000 seeded
   item/group bootstrap replicates; refuse unsupported/missing-panel designs and undefined CIs.
3. **Reference resolution:** recommend explicit adjudication only after the agreement gate;
   unresolved items remain unscorable with reported coverage.
4. **Score semantics:** recommend calibration only for declared probability vectors or chosen-label
   confidence; arbitrary numeric scores receive an explicit unavailable label.
5. **Delivery/privacy:** recommend standalone JSON/CSV/HTML outside the app, repository fixtures
   synthetic by default, and real inputs and outputs outside the checkout.

## Owner decisions

Approved by the owner on 1 November 2026. All five recommendations accepted, as recorded below.

1. Gate: lower 95% kappa bound ≥0.60 and complete-panel coverage ≥80%, frozen before testing.
2. Cohen for two reviewers, Fleiss for a fixed larger panel; 10,000 seeded item/group bootstrap
   replicates; refuse undefined intervals and mixed panels.
3. Adjudication only after the gate passes; unresolved items unscorable with coverage reported.
4. Calibration only for declared probability vectors or chosen-label confidence; other scores
   labelled not calibration-eligible.
5. Standalone JSON/CSV/HTML outside the app; synthetic fixtures only; real inputs and reports
   refused inside the checkout.
