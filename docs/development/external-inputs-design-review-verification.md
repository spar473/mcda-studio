# External inputs and research-model design review verification

1 November 2026. Part A's design-only follow-up to the
[factor-uncertainty integration](factor-uncertainty-integration-verification.md).

## Scope

Four proposed notes, each with problem/scope, typed data and schema/sidecar implications, API/UI,
precise edge cases and refusals, independent-oracle/property/mutation plans, excluded items and
five numbered owner decisions with recommendations:

- [External proposals](../design/external-proposals.md): generic JSON/CSV intake, original payloads,
  explicit accept/correct/reject reviews, provenance, side-by-side comparisons, pending questions
  and compatible accepted-input compilation through existing evidence into a separate copy.
- [Market research models](../design/market-research-models.md): reviewed bottom-up/top-down formula
  outputs, declared range meanings and persistent model disagreements, generic quantity checks,
  data-only starter manifests and optional unattached ownership formulas.
- [Disclosed model proxy criterion](../design/disclosed-model-proxy-criterion.md): off by default,
  required model card/features, overlap acknowledgement, explicit preference ratings and complete
  with/without comparison pairs.
- [Classifier agreement benchmark](../design/classifier-agreement-benchmark.md): offline frozen
  task/split, human-agreement gate, adjudication, abstention-aware metrics, meaningful score
  calibration only, trivial baseline and reproducible digested reports.

The roadmap lists all four as **Proposed**, after Derived measurements and before the flagship
study, in the owner's implementation order. No implemented sequence moved. Handover and changelog
state the stop. Every Owner decisions section remains pending; recommendations are not approvals.
No Part B implementation, new project schema, example/study data, classifier execution, provider
connection, migration or model result is included in this step. No existing source/test files
change relative to A1 commit `b5156bd`. New sidecars are proposals only; future version/migration tests
are specified in the notes.

## Owner review

External-proposal import separates structural refusal from retained blocked semantic issues, so an
out-of-vocabulary label can actually be corrected while preserving the original. Only compatible,
active accepted/corrected claims enter the existing numerical compiler; the full proposal set and
all references remain in its bundle. Model-card/source references are local and never fetched.
The market design's constraints are generic declared quantity checks, not template-specific
financial logic. The proposed kappa threshold is an operational owner decision, not a claim of a
universal statistical standard. Real benchmark inputs/reports stay outside the checkout.

## Checks

The complete local gate passed again after the design-only changes:

| Check | Result |
| --- | --- |
| Python | 1,755 passed |
| Frontend | 430 passed in 53 files |
| Browser | 103 passed |
| Mutations | 286/286 caught: 213 backend and 73 frontend; unmodified copy passes |
| Previous numerical/export outputs | 969/969 byte-identical to the pre-A1 baseline |
| Ruff lint and formatting | Passed; 193 files already formatted |
| Strict mypy | Passed, 87 source files |
| OpenAPI and generated frontend type freshness | Passed |
| Acceptance demo and evidence workflows | Passed |
| Frontend typecheck, lint and production build | Passed |

The gate runner recorded 41.41 seconds for Python, 29.42 for the combined frontend check,
228.92 for browser tests and 1,204.57 for mutations. Command results and individual logs are in
a local temporary directory, as are the before and after byte manifests. These are local
execution artifacts, not shipped fixtures.

Additional design checks confirmed that all four notes contain exactly five numbered open
decisions with recommendations and a pending Owner decisions section, and that their relative
links resolve. The invented market example's arithmetic was checked independently with exact
fractions. `git diff --check` passed. Source, tests, scripts, frontend and examples have no changes
relative to A1 commit `b5156bd`; no tests, tolerances, oracles or reference outputs were weakened
for this design step.

## Stop

The four notes require the owner's reply before any Part B development or the flagship study.
No new hosted CI or independent human-usage result is claimed. All work remains locally committed
on `codex/integrated-evidence-workspace`; nothing is pushed, tagged or released.
