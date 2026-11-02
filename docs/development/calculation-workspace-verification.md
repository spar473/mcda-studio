# Calculation workspace and factor uncertainty — 1 November 2026

Built on [graphical decision records](decision-records-verification.md) (`663e7d6`) on
`codex/integrated-evidence-workspace`. The branch was pushed with the owner's approval; nothing
was merged or tagged, and `main` is unchanged.

## Integration baseline

| Check | Actual result |
| --- | --- |
| Checkout | Clean at `663e7d6`, one worktree, five commits ahead of `main` (`6823357`); recovery bundle for `663e7d6` present outside the checkout. Idle Codex helper processes had this folder as their working directory; no file had changed in the previous 15 minutes |
| Hosted CI for `663e7d6` | Hosted CI passed (private working repository), 31 October 2026 UTC: every step on Ubuntu 24.04 passed, with 1,658 Python, 416 frontend and 100 browser tests, both distribution routes and the offline installed GUI (mutation step skipped on push, as configured). The Linux-specific Open Questions wording fix is therefore confirmed on hosted CI |
| Local baseline | 1,658 Python, 416 frontend and 100 browser tests passed |
| Boundary probe | 5,500 randomly damaged evidence, calculation, bundle, receipt and decision documents sent to the inspect, review, compile, binding and decision endpoints. Six requests returned HTTP 500: a decision record whose embedded analysis held `"nan"` or `"1e999"` in a numeric field made the seal computation raise an uncaught `ValueError` |
| Fix (`3bc814f`) | Seal computation refuses nonfinite numbers as `DECISION_RECORD_NONFINITE` (409 `EDIT_REFUSED`) for version-1 and version-2 records and predecessors. Seven new tests fail without the fix and pass with it; the probe then returned no 500 |

## Calculation workspace (live formula authoring)

Design: [calculation workspace](../design/calculation-workspace.md). The project schema, the
version-1 calculation model, the bounded interpreter and the compilation gate are unchanged.

- `domain/calculation_workspace.py`: version-1 workspace (start snapshot, original model,
  append-only events: unit, source, formula, review, remove, apply, rebind) with a digest.
- `services/calculation_workspace_service.py`: replay with typed refusals, relationship to the open
  project (`bound`, `earlier`, `different`), static factor usage through intermediates, per-formula
  checks with plain-language dimensional explanations, proposals and applications. Applying reruns
  `compile_copy`; the applied project equals the compiled copy byte for byte.
- `services/derived_service.py`: the preview body is now `_run`, also used by `trial` to evaluate
  one formula as if accepted (never digested or compiled). Dimensional errors carry their
  dimensions and the failing formula for explanations only; preview messages and digests are
  unchanged.
- API: `POST /api/calculations/inspect`, `/propose`, `/apply` (additive OpenAPI change).
- UI: **Measurements → Calculated measurements** opens models, workspaces and bundles; authoring,
  review, dependency graphs, measurement changes, apply (one editor batch, one undo step), separate
  copy, history, export and rebind. Unexported history joins the Save and leave guards.

Review fixes made before committing: every recalculation collapsed the panel's sections (the view
was briefly replaced by "Calculating…"), and exporting collapsed the whole panel because its open
state was forced only while dirty; both are now controlled state. Dimensionless units read
"(dimensionless)" instead of "1". Formula checks validate the project structure once per
inspection, not once per formula.

## Isolated factor-uncertainty evaluator

`domain/factor_uncertainty.py` and `services/factor_uncertainty_service.py` implement steps 1–5 of
the [plan](../design/derived-uncertainty-verification-plan.md); no analysis, endpoint or screen uses
them. The SMAA-2 engine is unchanged.

Independent checks (`tests/regression/test_factor_uncertainty_reference.py`, oracle without
application imports): exact discrete independent product (atoms 2, 4, 6, 12; mean 6, variance 14),
explicit quantile coupling (2 or 12; mean 7, variance 25) and an unequal-step coupling against a
two-pointer comonotone merge; shared identity across alternatives (B = 3X always exceeds A = 2X,
while independent resampling would reverse them with probability 1/4); X − X = 0, X/X·X = X and a
shared intermediate exactly on every draw; zero uncertainty reproducing the deterministic values
exactly; continuous product mean and variance and triangular mean within five standard errors from
exact moments; triangular quantiles against the CDF on 1,000 fixed variates; discrete frequencies
for independent and coupled draws; fixed-seed reproducibility, chunk-size invariance and
declaration/alternative-order invariance with keyed realisations; typed refusals for derived
outputs, unknown, duplicate, unreviewed or invalid distributions, unreviewed or overlapping groups,
stale models and projects, zero-denominator supports (including the disclosed conservative
`x − x + 1` case), negative ratio targets and overflow; an injected invalid draw refused with its
index and formula, never dropped.

## Checks run on the final tree

All on one tree containing both commits; the evaluator commit adds only isolated files.

| Check | Actual result |
| --- | --- |
| Full Python suite | 1,719 passed: 1,658 at `663e7d6`, plus 7 decision-record boundary, 26 calculation-workspace and 28 factor-uncertainty tests. Existing Starlette/httpx deprecation warning |
| Ruff, formatting, strict mypy | Passed (86 source files) |
| OpenAPI and generated TypeScript freshness | Passed; additive change (three endpoints and their schemas) |
| Full frontend check | 424 tests in 52 files passed (416 before; the calculation panel tests were ported and extended from 7 to 15); TypeScript, ESLint (0 warnings), type freshness and production build passed; existing large-chunk warning |
| Full browser gate | 102 passed in 4.8 minutes on a fresh throwaway store: the 100 earlier workflows, including both unchanged derived-measurement workflows, plus two calculation-workspace workflows |
| Acceptance scripts | `acceptance_demo.py` and `acceptance_evidence.py` passed |
| Existing numerical/export outputs | 969/969 byte-identical to `663e7d6` |
| Calculation mutation group (`--calculation-only`) | 35/35 killed (28 backend, 7 frontend), unmodified baseline passes. A first run killed 31: its baseline was reported failing only because a concurrent full test run caused frontend timeouts (every baseline suite then passed on a clean copy), and four mutants survived. One ran against the wrong suite; one was masked by replay raising the same code, now distinguished by message; two were real gaps (usage through intermediates, sub-unit changes), now tested. Three earlier calculation mutants were retargeted to the moved code |
| Uncertainty mutation group (`--uncertainty-only`) | 11/11 killed, unmodified baseline passes, after closing two gaps (declaration-order traversal with two independent factors; an unreviewed coupling with accepted distributions) |
| Decision mutation group (`--decision-only --backend-only`) | 18/18 killed, including the nonfinite-record mutant; unmodified baseline passes |
| Boundary probes | 5,500 damaged documents before the fix (6 server errors, all the decision case); afterwards 0 server errors in 5,500 requests and in 2,500 damaged calculation-workspace requests; every 4xx used the standard error envelope |
| Hosted CI for `94bf4a6` | Hosted CI passed (private working repository), 31 October 2026 UTC, on attempt 2: every step on Ubuntu 24.04 passed, with 1,719 Python, 424 frontend and 102 browser tests, both distribution routes and the offline installed GUI. Attempt 1 failed one browser test, the large-model measurement-coverage case, when Playwright's download of the stored project got `ECONNRESET`; the server logged no error and passed the remaining 55 workflows. Unchanged code, rerun of the failed job only, no test or tolerance changed. A keep-alive reuse race is suspected but was not reproduced locally (0 resets in 42 reuses near the 5 s keep-alive limit), so no fix was made |

The complete 282-mutant gate was not rerun as one job; groups untouched by these changes were last
recorded in the [decision records record](decision-records-verification.md).

## Human validation

No participant has run any task. Add to the prepared fresh-user protocol:

1. Revise a shared factor and explain why the calculated values disappear until it is reviewed.
2. Apply the reviewed calculation, then say what Undo removes and what Save stores.
3. Export the calculation workspace, reload, reopen it and explain "Bound to this project
   revision" and "Unchanged".
4. Write a formula that adds a cost to a count; explain the check message.

Record whether the participant confuses saving the project with exporting the workspace, a
calculated estimate with evidence, or a tool proposal with an accepted value.

## Not established

- Factor uncertainty is not connected to MAVT, sorting or SMAA-2, and has no interface; no
  sampled acceptability is produced. The MAVT/sorting near-tie oracle cases remain to be written
  with that integration.
- Workspace identities are local assertions and digests are unsigned. There is no autosave,
  workspace merging or rebinding across project IDs.
