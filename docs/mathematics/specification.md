# Mathematical specification: additive MAVT

Every equation implemented, with its assumptions. Notation: alternatives *a*, leaf criteria
*j = 1..m*, measurement *z_j(a)*.

## 1. Measurement scales

`categorical` (unordered labels), `ordinal` (ordered labels, spacing **not** assumed equal),
`interval` (numeric, arbitrary zero), `ratio` (numeric, true zero; values must be ≥ 0).

Admissible value functions per scale (anything else is a validation error):

| Scale | linear | piecewise_linear | direct_rating | qualitative |
| --- | :-: | :-: | :-: | :-: |
| categorical | | | | ✔ |
| ordinal | | | | ✔ |
| interval | ✔ | ✔ | ✔ | |
| ratio | ✔ | ✔ | | |

## 2. Value functions (all map into [0, 1])

* **Linear, increasing:** `v(x) = (x − L) / (U − L)`; **decreasing:** `v(x) = (U − x) / (U − L)`,
  with `U > L`. Anchors L, U are `fixed` (stated) or `local` (min/max over the alternatives). The domain
  tolerance for floating-point noise is `1e-9 * (U - L)`: relative to the *span*, never to the
  magnitude of the anchors (pinned by a regression test).
* **Piecewise linear:** for control points `(x_0,v_0) … (x_k,v_k)` with strictly increasing `x`,
  `v(x) = v_i + (v_{i+1} − v_i)(x − x_i)/(x_{i+1} − x_i)` on `[x_i, x_{i+1}]`.
  Required: values in [0,1]; monotone (non-decreasing or non-increasing) and not constant;
  **endpoint convention** — worst end has value 0, best end value 1. Domain = `[x_0, x_k]`.
* **Qualitative:** explicit `label → value`, covering exactly the scale's labels, values in [0,1],
  worst label 0 and best label 1; for ordinal scales, values must not decrease along the label order.
* **Direct rating:** the measurement is a rating on `[r_min, r_max]`, rescaled linearly to [0, 1].
* **Domain policy:** a numeric measurement outside the domain (beyond a 1e‑9 relative tolerance for
  floating-point noise) is an error (`OUT_OF_DOMAIN`). The only alternative is the explicit
  `out_of_domain="clamp"` policy, which clamps and reports `CLAMPED_MEASUREMENT`. Nothing
  extrapolates silently.

## 3. Hierarchical swing weighting

For each sibling group with raw ratings `r_1..r_n ≥ 0` (not all zero):

`λ_i = r_i / Σ_k r_k`.

For a leaf *j*, the global weight is the product of local weights along its root path:

`w_j = Π_{e ∈ path(j)} λ_e`, hence `Σ_j w_j = 1` (each group sums to 1, telescoping down the tree).

An only child needs no rating (`λ = 1`). A zero rating is allowed for a sibling so long as the
group sum is positive.

**Interpretation.** A swing weight is the importance of the swing from the worst to the best level
*over the stated scale range*, not abstract importance. Changing a scale's anchors changes what its
weight means. This text is stored in every result (`weight_basis`).

## 4. Additive MAVT

`V(a) = Σ_j w_j · v_j(z_j(a))`, computed with `math.fsum`.

Ranking uses competition ranking: `rank(a) = 1 + #{b : V(b) > V(a) + 1e‑12}`; tied alternatives
share a rank (1,1,3) and a `TIED_ALTERNATIVES` diagnostic is emitted.

**Dominance diagnostic (reported, never applied).** *a* dominates *b* if `v_j(a) ≥ v_j(b)` for all
*j* and `>` for at least one, compared on partial values. Alternatives are never removed.

**Assumptions** (also stored in every result):
1. *Compensatory*: a poor score on one criterion can be offset by a good score on another.
2. *Preferential independence*: preferences on a criterion do not depend on the levels of the others.
3. Partial values are normalised to [0, 1] over the same ranges the swing weights refer to.
4. No imputation of missing data.

## 5. One-way weight sensitivity

Choose a node *k* in sibling group *S* with local weight `λ_k < 1`. Replace it by `t ∈ [0,1]` and
scale the others proportionally:

`λ_i(t) = (1 − t)/(1 − λ_k) · λ_i  (i ∈ S, i ≠ k)`, `λ_k(t) = t`.

Undefined (raises `SensitivityError`) when `k` has no siblings or `λ_k = 1`.

**Exact crossovers.** Each root path contains at most one member of *S*, so every global weight is
*affine* in `t`. Partial values do not depend on `t`, so `V_a(t)` is affine and so is
`D_ab(t) = V_a(t) − V_b(t)`. Its root is therefore closed-form from the endpoints:

`t* = D_ab(0) / (D_ab(0) − D_ab(1))`, reported when `D_ab(0)` and `D_ab(1)` have strictly opposite
signs and `0 < t* < 1`.

No grid search or iteration is involved; tests cross-check against `scipy.optimize.brentq` on an
independent evaluation path. The sweep grid (default 101 points, always including the baseline
weight) is only for plotting.

**Reported:** values and rankings per grid point; all crossovers (with who leads before and after);
rank-change points; first winner change when raising and when lowering the weight; the weight
interval over which the full ranking, and the winner, are unchanged.

**Winner change** is found by evaluating the leader on each interval between consecutive
crossovers (rankings are constant inside an interval), then walking away from the baseline.

## 6. Scenarios

A scenario overrides the weight profile and/or the value function of chosen leaves.
`compare_scenarios` evaluates baseline and each scenario and reports ranking and winner changes.
Overrides are validated like base value functions (compatibility, domain, anchors).

## 7. Value-based sorting (`mavt_sorting`)

Value-based sorting assigns each alternative to one of ordered classes `C_1` (best) … `C_q`,
`q ≥ 1`, by its overall MAVT value `U(a)` from §4. It adds no aggregation of its own: every value,
weight, contribution and rank is MAVT's. See the
[design note](../design/value-based-sorting.md).

**Boundaries.** Every class except the lowest has a lower boundary `b_h`, the overall value needed
to enter it; the lowest class has none. Boundaries are fixed on the value scale and shared by every
scenario and profile. They must lie in [0, 1] and decrease strictly from the best class down, each
more than `2τ` below the one above (`τ = 1e‑12`, the ranking tie tolerance), so the tie bands
`[b − τ, b + τ]` never overlap. They are never sorted or relabelled automatically.

**Assignment.**

`class(a) = C_h`, where `h = 1 + #{k < q : U(a) < b_k − τ}`.

Equivalently `a ∈ C_h` when `b_h − τ ≤ U(a) < b_{h−1} − τ`, taking `b_0 = +∞` and `b_q = −∞`. A
value within `τ` of a boundary, on either side, goes to the **higher** class. Empty classes are
valid; with one class every alternative is in it.

**Distance.** `d(a) = min_k |U(a) − b_k|`, naming the nearest boundary by its class (the higher
one on an exact tie). An alternative with `d(a) ≤ τ` is on the boundary. With one class there is
no boundary and no distance.

**Audit sample.** Optionally, `n` alternatives sorted below a cut-off class are chosen for manual
review of possible false negatives: the pool is ordered by the hexadecimal SHA-256 of
`"<seed>:<alternative id>"`, then by ID, and the first `n` are taken. It estimates nothing and never
changes a class.

**Class changes in one-way sensitivity.** With the varied weight `t` (§5), `U_a(t)` is affine and
boundaries are constant, so `g(t) = U_a(t) − (b_k − τ)` is affine and `a` is in `C_k` or better
exactly when `g(t) ≥ 0`. Where `g(0)` and `g(1)` fall on different sides, the class changes at

`t* = g(0) / (g(0) − g(1))`,

the weight at which this assignment rule switches; at `t*` the alternative is in the higher class.
Change points at `t = 0` and `t = 1` are kept, because the class is defined there. Reported per
alternative: the class at the baseline, every change point with the classes just below and just
above it, the first change when raising and when lowering the weight, and the class-stable
interval. An alternative whose baseline value is within `τ` of a boundary is flagged
(`BASELINE_ON_CLASS_BOUNDARY`).

**Meaning.** A class says only that the compensatory overall value reached a stated threshold. It
is not a probability, a prediction or a test of any single measurement; with local anchors, adding
an alternative can move others between classes.

## 8. SMAA-2 (`smaa2`)

SMAA-2 reports how often each alternative takes each rank, and each class when the project has
classes (§7), when stated inputs are drawn from stated distributions. Every draw is evaluated with
the additive model of §4. See the [design note](../design/smaa-2.md).

**Stated inputs.** Per measurement: uniform on `[l, u]`, triangular `(l, m, u)`, or discrete
(numeric values or scale labels with probabilities summing to one; the probabilities are used as
exact fractions normalised to sum to one). The support lies inside the value-function domain and
is never clamped; a missing measurement stays missing. Per sibling group: *fixed* (the profile's
ratings), *unknown* (local weights `Dirichlet(1, …, 1)`, drawn as normalised exponentials) or
*rating intervals* (each raw rating uniform on its interval, then normalised; a draw summing to
zero is refused). Inputs are independent, except cells in a *shared draw*, which use one common
uniform `U` through their own quantile functions (comonotone). A run varies the measurements, the
weights, or both.

**Draws.** `Generator(PCG64(seed))`; each draw takes uniforms for the varying groups (tree order,
children in order), then the independent cells (alternative, then leaf order), then the shared
draws. Quantiles: uniform `l + U(u − l)`; triangular `l + √(U(u − l)(m − l))` for
`U < (m − l)/(u − l)`, else `u − √((1 − U)(u − l)(u − m))`; discrete: the first outcome whose
cumulative probability exceeds `U` (numbers ascending, labels in scale order).

**Exactness.** Values are summed in bulk; a draw in which two values, or a value and a class
switching point `b − 10⁻¹²`, lie within `10⁻⁹` is summed again with `math.fsum`, and ranks
(competition, §4) and classes (§7) come from that. Ties share a rank: a rank row sums to one,
a rank column can sum above one, and rank 1 is also reported as *sole* and *tied* first.

**Exact enumeration.** When every varying input is discrete and the joint outcomes number at most
100 000, the probabilities are computed exactly over all outcomes (shared draws split `[0, 1)` at
every member's cumulative probabilities) and reported with no interval.

**Intervals.** For `k` events in `n` draws, the two-sided Clopper–Pearson interval at level
`1 − α`: lower `B⁻¹(α/2; k, n − k + 1)`, upper `B⁻¹(1 − α/2; k + 1, n − k)`, with `0` and `1` at
`k = 0` and `k = n`; at `k = 0` the upper bound is `1 − (α/2)^{1/n} > 0`. `B⁻¹` is found by
bisection on the regularised incomplete beta function.

**Inputs to check (heuristic).** For each varying input, the leading alternative's rank-1
frequency in draws with that input in its upper half (its uniform above 0.5, or for an unknown
group its local weight above the median) minus that in the lower half; the five largest absolute
differences. Association in these draws, not causation or a value of information.

**Meaning.** Sampled acceptability under these assumptions: a property of the stated
distributions and the model, not a probability of success and not proof that a conclusion holds
for every admissible weight.

## 9. PROMETHEE II (`promethee2`)

PROMETHEE II ranks alternatives by their net outranking flow, computed from pairwise differences
in the raw measurements through stated preference functions. It reads only its own section:
never swing weights or value functions. Definitions follow J.-P. Brans and B. Mareschal,
"PROMETHEE methods", in J. Figueira, S. Greco and M. Ehrgott (eds.), *Multiple Criteria Decision
Analysis: State of the Art Surveys*, Springer, 2005. See the [design note](../design/promethee-ii.md).

**Inputs.** For each leaf `j`: a direction `sⱼ = +1` (maximise) or `−1` (minimise), a weight
`wⱼ ≥ 0` with `w̄ⱼ = wⱼ / Σ w`, a preference function `Fⱼ`, and on a labelled leaf a number for
every label; `xₐⱼ` is the measurement, or its code. `n ≥ 2` alternatives.

**Preference degrees.** `dⱼ(a, b) = sⱼ (xₐⱼ − x_bⱼ)` and `Pⱼ(a, b) = Fⱼ(dⱼ(a, b))`, with `F(d) = 0`
for `d ≤ 0` and, for `d > 0`:

| Function | F(d) |
| --- | --- |
| usual | 1 |
| U-shape (q ≥ 0) | 0 if d ≤ q, else 1 |
| V-shape (p > 0) | d / p if d < p, else 1 |
| linear (0 ≤ q < p) | 0 if d ≤ q; (d − q) / (p − q) if q < d < p; 1 if d ≥ p |

`d` is compared with 0, q and p as equal within `10⁻¹² × max(1, |xₐⱼ|, |x_bⱼ|)`, so a difference
that equals a threshold in decimal counts as that threshold in binary floating point.

**Flows.** `π(a, b) = Σⱼ w̄ⱼ Pⱼ(a, b)`; `Φ⁺(a) = Σ_{b≠a} π(a, b) / (n − 1)`;
`Φ⁻(a) = Σ_{b≠a} π(b, a) / (n − 1)`; `Φ(a) = Φ⁺(a) − Φ⁻(a)`. Single-criterion net flows
`φⱼ(a) = Σ_{b≠a} [Pⱼ(a, b) − Pⱼ(b, a)] / (n − 1)`, so `Φ = Σⱼ w̄ⱼ φⱼ`. Every sum uses `math.fsum`.
Asserted on every result: `0 ≤ Φ⁺, Φ⁻ ≤ 1`, `−1 ≤ Φ ≤ 1`, `Σ Φ = 0` within `n × 10⁻¹²`, and both
decompositions within `10⁻¹²`.

**Rankings.** PROMETHEE II: competition ranks on `Φ` with the `10⁻¹²` tie tolerance of §4.
PROMETHEE I: `a` is preferred to `b` when `Φ⁺(a) ≥ Φ⁺(b)` and `Φ⁻(a) ≤ Φ⁻(b)` with one strict;
indifferent when both are equal; otherwise incomparable. Equal means within `10⁻¹²`.

**Explanation against MAVT.** For each pair that MAVT (§4, under the selected profile and scenario)
and PROMETHEE II order differently, a tie counting as an order, oriented so that `a` is the one MAVT
places higher (or, when MAVT ties them, the one PROMETHEE II places lower):

- the value gap `V(a) − V(b)` and the flow gap `Φ(a) − Φ(b)`, each in its own units;
- the flow gap split into a head-to-head part `2 [π(a, b) − π(b, a)] / (n − 1)` and a via-others
  part `Σ_{c≠a,b} {[π(a, c) − π(c, a)] − [π(b, c) − π(c, b)]} / (n − 1)`, which is zero for
  `n = 2`;
- per criterion: `dⱼ(a, b)`, its zone from `Fⱼ(|dⱼ|)` (0: no preference; strictly between: partial;
  1: full, *capped* when `|dⱼ|` lies beyond the point where full preference begins), the PROMETHEE
  contribution `w̄ⱼ [φⱼ(a) − φⱼ(b)]` with its head-to-head part, and MAVT's weighted partial-value
  difference.

No quantity adds, averages or subtracts a value and a flow.

**Meaning.** A net flow compares the alternatives with one another: adding or removing an
alternative can change every flow, and the order of two others. It is not a preference value,
and agreement with MAVT on shared measurements is not independent validation.

## 10. AHP (`ahp`)

AHP derives priorities from pairwise judgements: criteria within each sibling group of the tree,
and alternatives on each leaf. It reads no measurements, value functions, profiles or scenarios.
Definitions follow T. L. Saaty, *The Analytic Hierarchy Process*, McGraw-Hill, 1980; the random
indices are Saaty and Tran (2007), and the triad index is Koczkodaj (1993). See the
[design note](../design/ahp.md).

**Matrices.** For `n` items, `M[i][i] = 1`, a stated judgement gives `M[r][c] = v` with
`1 ≤ v ≤ 9`, and `M[c][r] = 1 / v`. Every pair must be judged; `n ≤ 15`.

**Priorities.** `n = 1`: `w = (1)`. `n = 2`: `w = (v / (1 + v), 1 / (1 + v))`, λmax = 2. `n ≥ 3`: power
iteration from `(1, …, 1)`, `w ← Mw / maxᵢ (Mw)ᵢ` with every sum in `math.fsum`, until the largest
change is at most `10⁻¹⁴` (at most 10 000 iterations, or an error); then `w ← w / Σ w` and
λmax = Σᵢ (Mw)ᵢ.

**Consistency.** For `n ≥ 3`, `CI = max(0, (λmax − n) / (n − 1))` and `CR = CI / RI(n)` with
RI = 0, 0, 0.52, 0.89, 1.11, 1.25, 1.35, 1.40, 1.45, 1.49, 1.52, 1.54, 1.56, 1.58, 1.59 for
`n` = 1 to 15; for `n ≤ 2`, CI = CR = 0 by definition. `CR > 0.10` is a warning. The most
inconsistent triad maximises `min(|1 − M[i][k] / (M[i][j] M[j][k])|, |1 − M[i][j] M[j][k] / M[i][k]|)`
over `i < j < k` (the first in item order on ties); the third judgement would be consistent at
`M[i][j] M[j][k]`.

**Synthesis.** A leaf's global priority `gⱼ` is the product of the local priorities on its path, so
`Σ gⱼ = 1`. With `pⱼ(a)` the alternatives' priorities on leaf `j`: distributive
`P(a) = Σⱼ gⱼ pⱼ(a)`; ideal `S(a) = Σⱼ gⱼ pⱼ(a) / maxᵦ pⱼ(b)` and `P(a) = S(a) / Σᵦ S(b)`. Ranks are
competition ranks on `P` with the `10⁻¹²` tolerance of §4.

**Meaning.** A priority is a share of the goal under the stated judgements, not an MAVT value or a
swing weight. Consistency measures agreement among the judgements, not their validity; under
distributive synthesis, adding or removing an alternative can change the order of two others.

## 11. Feasibility check (not a method)

See the [design note](../design/feasibility-check.md). For a requirement on leaf `j` and an
alternative `a` with measurement `x = x(a, j)`:

- **unknown** if `x` is missing, is a label on a numeric leaf, a number on a labelled leaf, or a
  label the scale does not have;
- for a `bound` with limits `L` and `U` (each optional): **pass** if `x ≥ L` (or `x > L` when the
  minimum is exclusive) and `x ≤ U` (or `x < U`), otherwise **fail**;
- for `labels` with the allowed set `A`: **pass** if `x ∈ A`, otherwise **fail**.

Comparisons are exact floating-point comparisons of the measurement as entered with the limit as
entered; no arithmetic precedes them, so there is no tolerance. The overall status of `a` is fail
if any requirement fails, otherwise unknown if any is unknown, otherwise pass. Bounds are in the
leaf's own unit, which the requirement states and must match; nothing is converted.

**Meaning.** Feasibility says only whether stated hard limits hold for the measurements as entered.
It reads no weights, value functions, profiles or scenarios, so it is the same under every one of
them, and no score offsets a failure. It changes no ranking.
