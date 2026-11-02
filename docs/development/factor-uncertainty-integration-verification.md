# Fundamental-factor uncertainty integration verification

1 November 2026. Implements the approved integration and release gate in the
[uncertainty plan](../design/derived-uncertainty-verification-plan.md). Work stayed on
`codex/integrated-evidence-workspace`; no push, tag, release or main-branch change.

## Baseline and execution

The clean starting commit was `bb2dc32`. The entire gate was run before applying changes to the
checkout. Preparation and focused checks used a separate temporary staging checkout while the
immutable baseline mutation copy finished. The initial sandbox attempt could not bind localhost;
it was stopped and the complete baseline rerun with localhost/process access. Browser tests used
the installed Chrome, as documented in [testing](testing.md); the first attempt without that
setting could not launch the browser and was replaced, not counted as a test result.

Baseline: 1,719 Python tests; 424 frontend tests in 52 files; 102 browser tests; 969 numerical/export
outputs captured by `scripts/byte_identity.py`. Lint, formatting, strict typing, OpenAPI freshness
and both acceptance scripts passed. All 282 baseline mutations were caught and their unmodified
copy passed. Final-tree results are recorded below.
Local execution is on macOS. No new hosted run or human usability result is claimed.

## Delivered behavior and schema boundary

- Factor-based **MAVT draws**, **value-based sorting draws** and **SMAA-2 with fundamental
  factors** are separate run types. The existing method registry, cell-based SMAA-2 and earlier
  output types/algorithms are unchanged. Each draw uses a temporary raw-measurement matrix,
  ordinary MAVT value functions/weights/ranks and sorting rules; SMAA-2's existing rank/class
  path and Clopper–Pearson estimates summarize the resulting draws. Scores are never averaged
  across sources or methods.
- Every factor and formula is realized once per draw using the approved dependency sampler.
  Fixed weights only: additional cell uncertainty, uncertain weights or other dependence
  combinations are refused. The existing calculation gate is the single authority refusing
  cell uncertainty on a derived target; it is exercised before the other combination checks.
- Conservative formula support preflight remains as approved, including refusal of denominator
  supports containing zero even when an exact continuous point has zero probability. Fixed
  value-function support domains are checked before sampling against the same conservative
  enclosures; this can reject a reused-factor expression whose actual image would fit. Local linear
  anchors are recomputed by ordinary MAVT for every draw, including refusal of a degenerate realized range.
  Clamping occurs only under the explicitly stated existing value-function policy.
- Unused incomplete factors also return typed validation refusals. Arithmetic, nonfinite
  factor/target and value-function errors abort the whole run with a typed code, draw index and factor/formula IDs. No bad draw is discarded or assigned zero, and no
  reduced denominator produces acceptable-looking output.
- New `factor_uncertainty_run` version-1 sidecars retain the source project, calculation model,
  uncertainty declaration, run parameters, accepted deterministic inputs, reference result,
  acceptabilities, first 16 complete factor/formula/measurement/value/rank/class traces, a digest
  covering every draw, dependency order/columns, source questions and limitations. They record
  seed, RNG family, both algorithm versions, model/distribution digests, exact draw count and
  environment. Exact enumeration records the number of joint outcomes, no RNG and no sampling
  intervals; the requested seed is retained but unused.
- Optional decision snapshots wrap the existing version-2 deterministic decision record and its
  calculation bundle beside the stochastic result. The factor view also shows feasibility on the
  deterministic reference and decision notices;
  draw counts are not conditioned on feasibility. This preserves feasibility, rationale and
  measurement lineage without pretending a sampled realization is the project. Reopening checks
  binding and digest; complete stochastic replay is explicit and environment-bound. Unsigned
  digests and locally asserted identities do not establish authenticity.

Project schemas 1–3, `DerivedModel` version 1 and `FactorUncertaintyModel` version 1 are unchanged;
there is no project migration. This is the first version of the new run envelope, so there is no
older run format to migrate. Tests reject an unknown run/uncertainty version and round-trip the
existing inputs. Older outputs are checked byte for byte rather than updating their baselines.

## API, CLI and graphical workflow

Stateless `POST /api/factor-uncertainty/inspect`, `/run` and `/verify` share one Python service;
`/verify` optionally replays. Draw errors use HTTP 422 `INVALID_FACTOR_DRAW`, with indexed details.
A malformed/changed/nonfinite retained record is refused, not returned through an HTTP 500.
`/api/open-questions` optionally receives a verified local factor run record; stale bindings are
reported as unavailable and never rebound.

CLI:

```sh
.venv/bin/mcda derived uncertainty-run PROJECT.json MODEL.json UNCERTAINTY.json --run smaa2_factors --draws 1000 --seed 7 --output NEW_RUN.json
.venv/bin/mcda derived verify-uncertainty NEW_RUN.json --replay
```

`--run mavt` and `--run mavt_sorting` select the other run types; `--evaluation exact_enumeration`
requires discrete factors. `--profile`, `--scenario` and optional `--decision DETAILS.json` are
explicit. Output creation is exclusive. No input project or library file is written.

In **Measurements → Calculated measurements**, open a model/workspace and expand
**Fundamental-factor uncertainty**. Start/import a bound sidecar, name a reviewer, set pending
uniform/triangular/discrete marginals and optional quantile groups, inspect dependency questions,
and explicitly accept the distributions/coupling before running/exporting as reviewed. Drafts
(including stale or pending declarations) can be exported without accepting or rebinding them.
Select run type, sampling or exact enumeration, draw count and seed. The result retains the
currently viewed profile/scenario, with late replies rejected on a selection change. It shows
deterministic preference values separately from acceptabilities and the trace; optionally include a decision snapshot.
Export the sidecar/run before Save or leaving. Changed parameters hide an earlier current result
while retaining an explicit export action for its historical snapshot; stale/late replies cannot
be exported as the current run. Open an exported record to verify it historically. Open Questions
can load the same record to ask about shared factors and source classifications.

## Independent verification and mutations

The new `tests/regression/factor_analysis_oracle.py` imports no application code. It reconstructs
raw-measurement conversion, weighted sums, competition ranks and sorting boundaries independently.
Exact discrete cases include five near-tie offsets through all three run types, class boundaries,
point-mass reduction, fixed-seed sampled traces and shared factor identity, order invariance,
unsupported combinations, bad arithmetic/value-function draws, conservative support refusal,
local-anchor recomputation, stated clamp policy, pre-sampling limits and decision/record replay.
The previously established product/sum/dependence/quantile oracles continue to run unchanged.

New API/CLI cases compare complete service, HTTP and CLI records, prove stored-project byte
identity, preserve pending distributions/questions, refuse malformed versions and records, and
exercise typed bad draws. Frontend cases cover mandatory review, Python errors, late replies,
wrong context and retained stale sidecars. The real-browser case authors/reviews a shared-source
marginal, evaluates and exports a decision/run, reopens/replays it, checks stored bytes and loads
its questions. No real company/person data or provider requests are introduced.

Four new backend mutations exercise actual row thinning with a reduced denominator, sampling a
factor twice, failing to share a reused factor, and silently accepting cell uncertainty on a
derived target. The last one targets the authoritative guard, so it actually permits the forbidden
run rather than only changing an error code. Existing uncertainty mutations remain reachable and
the unmodified mutation copy must pass. Frontend mutation runs now fail fast after their first
real test failure, matching the Python runners’ existing `-x`; the ordinary full frontend gate
still runs every test and the unmodified mutation copy has no failures at which to stop early.
No assertion, oracle or tolerance changed. Final counts are recorded after the complete gate.

## Final checks

All ten full-gate commands passed on the final implementation tree. No test, tolerance, oracle
or reference fixture was weakened or regenerated to hide a numerical change.

| Check | Baseline (`bb2dc32`) | Final A1 result |
| --- | --- | --- |
| Python unit/API/integration/property/regression suite | 1,719 | **1,755 passed** (+36: 33 regression cases and 3 API/CLI cases) |
| Full frontend check | 424 in 52 files | **430 passed in 53 files** (+6); TypeScript, ESLint with zero warnings, generated-type freshness and production build passed |
| Full browser gate, real backend and throwaway store | 102 | **103 passed** (+1) |
| Full mutation harness | 282/282 | **286/286 caught** (+4), comprising 213 backend and 73 frontend; no survivors or invalid anchors, unmodified copy passes |
| Ruff and format check | Passed | Passed |
| Strict mypy | Passed, 86 source files | Passed, 87 source files |
| Committed OpenAPI freshness | Passed | Passed; additive endpoints/sidecar types, existing project/result schemas unchanged |
| `acceptance_demo.py`, `acceptance_evidence.py` | Passed | Both passed |
| Earlier numerical/export outputs | 969 captured | **969/969 byte-identical** using `scripts/byte_identity.py` |

All 15 uncertainty mutations, including the four new defects listed above, were caught. The new
injections have unique anchors and parse as valid Python; they are not syntax-error kills. The
full unmodified mutation copy passed its suites. Frontend fail-fast affects only how soon a
mutant's first genuine failure ends that run; the ordinary full frontend gate ran all 430 cases.

The full A1 Python run took 92.96 s, frontend check 85.55 s, browser gate 463.16 s and mutation gate
2,459.02 s. The existing Starlette/httpx deprecation and Vite large-chunk advisory remain; neither
was suppressed. A result viewport screenshot was inspected: reference preferences, selected
profile/scenario, feasibility and acceptability counts are readable, and the source project's
missing-measurement status remains unchanged. This is automated/visual QA, not a human checkpoint.

Raw command logs for this local run are under a local temporary directory; the baseline is under
a local temporary directory. The committed counts above are the durable record.

## Limits and remaining work

The graphical editor is intentionally minimal: numeric fields/arrays and a group list, no density
plots, drag handles, arbitrary correlations, graphical comparison of sampled distributions,
append-only distribution-edit history or live formulas embedded in a project. Retain earlier
exported sidecars/runs for revision history. The run envelope holds only the first 16 full draws;
all draws are covered by the digest and can be replayed in the supported recorded environment.
Stochastic decisions open through the factor panel/CLI, not the ordinary Decision-tab record
browser. The 8 MB request/import limit still applies; embedded projects, models and decisions
can make large records unsuitable for graphical reopening. No uncertain-weight combination,
automatic evidence-range inference, source-quality weight, network integration or outcome
prediction is implemented. Human usability and hosted CI remain unverified for this development. The four following designs remain proposals only.
