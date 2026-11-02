# Fundamental-factor uncertainty — implementation and mathematical gates

## Status (1 November 2026)

The approved integration (steps 6–8 and release gate 6) is implemented in separate factor-based
runs; see the [verification record](../development/factor-uncertainty-integration-verification.md)
for actual final checks and limits. The isolated evaluator status below records the starting point.

Steps 1–5 below are implemented as an **isolated evaluator** that no analysis, endpoint or screen
uses yet: `domain/factor_uncertainty.py` (a version-1 `FactorUncertaintyModel` bound to the project
fingerprint and the deterministic model digest) and `services/factor_uncertainty_service.py`
(`plan`, `sample`, `enumerate_outcomes`). Algorithm `factor-sampling.v1`: PCG64 row-major uniforms,
one column per independent factor (sorted IDs) then per quantile group (sorted IDs), chunk-size
invariant; every draw evaluates every formula once in a deterministic dependency order with the
bounded interpreter. Preflight uses conservative interval arithmetic for zero denominators,
overflow and negative ratio targets. The independent checks are in
`tests/regression/test_factor_uncertainty_reference.py` with `factor_uncertainty_oracle.py`
([record](../development/calculation-workspace-verification.md)).

At that starting point, not yet done: feeding sampled measurements into MAVT/sorting (step 6), SMAA-2 integration (step
7), graphical distribution editing and recorded stochastic results (step 8), and the MAVT/sorting
near-tie oracle cases (release gate 6). The SMAA-2 engine and its outputs are unchanged.
The calculation workspace supplies the revision model the plan required.

## Plan

## Model and execution boundary

Use a separately versioned uncertainty sidecar bound to the deterministic model digest and
project fingerprint. It names fundamental source-factor IDs, not final measurements. Initially
support the existing numeric uniform, triangular and discrete marginal semantics only. A
factor with no distribution uses its accepted deterministic value. No distribution is inferred
from source ranges, formula extrema or corrected claims. Acceptance of a factor value does not
constitute acceptance of a distribution.

Each factor ID has one identity throughout the dependency graph and across all alternatives.
Independent factors each receive one variate per draw. Explicit quantile groups receive one
shared uniform variate, passed through each declared marginal's quantile function. This expresses
perfectly shared quantile draws; it is not a generic covariance/correlation model. Reject arbitrary
correlation matrices, pairwise coefficients, copulas, undeclared groups and a factor in multiple
groups. Reusing a named factor requires no quantile group: it already denotes the same draw.

Validate the deterministic graph, units, targets, accepted inputs and resource limits before
sampling. Traverse sorted stable factor IDs and a deterministic topological formula order, never
alternative display order. Record the seed, RNG family, sampler/quantile algorithm version,
model/distribution digests, environment versions, exact draw count and dependency declaration.
The algorithm must specify whether its sequence is chunk-size invariant and test that claim.
Record accepted deterministic inputs separately from sampled realizations and calculated targets.

Evaluate every formula for every draw using that draw's accepted factor realizations. A shared
factor or intermediate is evaluated once per draw. Populate only the declared targets in a
temporary measurement matrix, then use the existing MAVT functions, weighting, tie rules and
sorting rules. State explicitly which weight uncertainty is supported; reject combinations
until they have their own cross-checks. Existing cell uncertainty on a derived target is a
double specification and must be refused, rather than sampled independently a second time.

Reject arithmetic domains that cannot be established as supported. Detect division by zero,
nonfinite results, overflow and invalid value-function domains with factor/formula IDs and draw
index. Never discard a bad draw, reduce the denominator, clamp outside policy or substitute zero.
Conservative preflight may reject a support containing an invalid denominator even when a
continuous marginal assigns probability zero to the exact bad point; disclose that restriction.
Incomplete models return typed errors, not partially usable acceptabilities.

The first implementation should be an isolated evaluator with an explicit result type and
independent tests. Integrate into SMAA-2 only after the evaluator's gate passes. No existing
project schema field should silently acquire live-formula semantics. Embedded formulas require
a separate version migration, provenance/revision snapshots and atomic undo/redo tests first.

## Independent oracles and acceptance cases

Oracle modules must not import `mcda_studio`, reuse its expression interpreter, RNG mapping,
quantile implementation, unit checking or aggregation. Keep exact algebra in `Fraction` and
enumerate tiny discrete supports explicitly. Existing `derived_oracle.py` and `smaa_oracle.py`
provide conventions, not production sampler code.

| Case | Independent expected result |
| --- | --- |
| Independent sum | E[X+Y] = E[X]+E[Y]; Var(X+Y) = Var(X)+Var(Y) |
| Independent product | E[XY] = E[X]E[Y]; Var(XY) = Var(X)Var(Y) + Var(X)E[Y]² + Var(Y)E[X]² |
| Exact discrete product | Independent X equally 1 or 3, Y equally 2 or 4: outputs 2, 4, 6, 12 with probability 1/4 each; mean 6, variance 14 |
| Explicit quantile coupling | The same marginals under one quantile draw give outputs 2 or 12 with probability 1/2 each; mean 7, variance 25 |
| Shared identity across alternatives | A = 2X and B = 3X for positive X: B always exceeds A. For X equally 1 or 3, independently resampling X would incorrectly let A exceed B with probability 1/4 |
| Shared identity within an expression | X−X is exactly zero and X/X exactly one on strictly positive support, for every draw |
| Shared intermediate | Two downstream formulas referencing the same named intermediate use exactly the same realized intermediate |
| Zero uncertainty | Point-mass factors reproduce the deterministic trace, measurement matrix, MAVT values/ranks and sorting classes exactly |
| Nonlinear range fallacy | The discrete product has four atoms above; a uniform distribution on [2,12] has different moments/support and must never appear |

For continuous tests use analytic moments for the declared uniform and triangular marginals,
plus a separately implemented reference quantile transform for fixed variates. Pre-register
statistical error bounds using variance/fourth moments and the number of draws, then supplement
with exact fixed-variate comparisons; do not loosen thresholds after observing results. Sampling
agreement alone cannot prove dependency identity, so test factor/intermediate traces directly.

Additional release gates:

1. Fixed seed reproduces the complete result and metadata in the supported environment.
2. Reordering alternatives, formulas, factors and distribution declarations preserves keyed
   realizations/results; renaming an ID intentionally changes the input digest.
3. Supported chunk-size changes preserve keyed results if claimed by the algorithm version.
4. Unknown references, cycles, rejected/missing factors, dimensional mismatches, unsupported
   dependence and duplicate target uncertainty fail before producing a usable result.
5. Inject an invalid draw and verify a typed failure with its index; prove the denominator was
   not reduced and no acceptable-looking partial result is returned.
6. Feed exact enumerated raw measurements through an independent MAVT/sorting oracle; check
   near-tie and class-boundary cases using existing tolerances, without weakening them.
7. Run all existing SMAA-2 discrete/continuous reference cases and byte-identity fixtures for
   every pre-existing method with unchanged inputs.
8. Add mutations for resampling shared factors, sampling an output interval, independent group
   draws, changed factor traversal, skipped invalid draws and missing model digests.

Only then add graphical distribution editing, derived-input questions and recorded decision
snapshots of these stochastic results. Label sampling frequencies as acceptability under the
declared assumptions, never investment-success probability, confidence in a source, causation
or a composite decision-relevance score.


## Approved integration contract

`factor_analysis_service` feeds realized raw measurements through ordinary MAVT and sorting and
uses the existing SMAA-2 rank/class and interval functions. Run types `mavt`, `mavt_sorting` and
`smaa2_factors` are explicit, separate from the earlier method registry and cell-based run types.
Only fixed weights are supported. Additional cells, shared cell draws and uncertain weights are
refused; the deterministic calculation gate refuses cell uncertainty on any derived target.
Every draw recomputes local anchors; an invalid realized domain aborts with its index. Fixed
value-function support domains are checked before sampling. An explicitly declared clamp policy
remains ordinary MAVT policy; the sampler never invents clamping.

New `factor_uncertainty_run` version-1 files retain original inputs, deterministic reference,
seed, RNG, algorithm/environment versions, exact draw/outcome count, dependency declaration,
model/distribution and complete-draw digests, and the first sixteen full realization traces.
Decision snapshots optionally wrap the existing version-2 deterministic decision and calculation
bundle beside the factor run. No project-schema or existing sidecar migration is needed. Unknown
new-envelope versions are refused and existing formats round-trip unchanged. Verification checks
binding and integrity without rerunning a stochastic result; replay is explicit and compares the
complete result in the recorded environment. Digests are unsigned, identities are local assertions.

The minimal editor provides uniform/triangular/discrete parameters, explicit quantile-group
membership/rationale, review and import/export. No density plots or distribution-history editor
is claimed. Inspect can show pending assumptions; Open Questions can also consume a verified run.
The [record](../development/factor-uncertainty-integration-verification.md) lists remaining limits.

## Arithmetic clarification (1 November 2026)

The [arithmetic contract](derived-measurements.md#arithmetic-contract) governs new verification:
engine-to-engine claims are bit-exact, and exact-oracle comparisons use independently propagated
rational forward-error bounds. Existing engine arithmetic, interpreter order, checks and pinned
outputs are unchanged. All formula mutants must remain caught; any survivor is a stop.
