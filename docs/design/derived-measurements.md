# Deterministic derived measurements: foundation

This is a working calculation sidecar, CLI preview/compile and API/editor preview/compile-export,
not live formulas embedded in a project. A version-1 model binds to one exact project fingerprint.
It stores named source factors, reviewed formulas and explicit unit dimensions. Formula IDs also
name intermediate results. Optional alternative/criterion IDs attach a result to a measurement.
Shared factors have one stable ID and are evaluated once; the trace records both immediate
dependencies and all fundamental source IDs. Provenance and review reuse the evidence models.
Human/tool proposals without acceptance do not supply values. Corrections preserve recorded claims.

The bounded interpreter walks a Python syntax tree; it never calls `eval`, `exec` or `compile`.
Only numeric constants, names, unary signs, +, -, *, /, and min/max with 2–16 arguments are allowed.
Addition, subtraction and min/max require identical dimensions. Products add dimension exponents;
division subtracts them. The result must match its declared unit dimensions and, for a target,
the criterion's exact unit symbol. Unit `1` is dimensionless. Unit definitions are explicit analyst
judgements, with no implicit conversion, scaling or currency equivalence. For example, annual
revenue per customer has dimensions NZD/customer/year; multiplying by customers and a dimensionless
adoption rate yields NZD/year. This result is a model estimate, not validated market evidence.

The model is limited to 256 factors, 128 formulas, 128 unit definitions, 2000 characters and 128
syntax nodes per expression, 64 dependency levels and dimension exponents within ±16. Cycles,
unknown names/units, missing accepted inputs, unsupported syntax, division by zero, nonfinite
results and excessive nesting have explicit codes. Rejected/unreviewed formulas cannot compile.
Duplicate IDs or targets, invalid target references and stale project revisions are refused.
Any error blocks compilation of the whole preview; valid partial calculations may still be shown.
An existing SMAA distribution on a formula target is refused because it cannot represent the
upstream-factor model.

The preview includes the complete model snapshot, calculations, source IDs, issues and digests.
Compilation requires its exact review digest, revalidates, and produces a new static project.
The CLI uses exclusive file creation; graphical exports use browser downloads and never write
library files. The project schema and its numerical
methods are unchanged. Keep the original project, model and preview together: the compiled project
does not embed formulas or automatically recalculate when a factor changes. The editor displays
and downloads the preview, requires explicit review of all target changes, and compiles/exports
a separate static project copy. The [calculation workspace](calculation-workspace.md) adds
graphical authoring, review and in-place application on top of this model and gate.
Existing undo/redo and saving are untouched because previews perform no edit operation.

The version-1 calculation bundle retains the original project, full reviewed preview/model,
compiled project, compiled fingerprint and artifact digest. Loading a bundle verifies its digest
and reconstructs the entire compilation in Python before previewing against the current project.
It never rebinds the model to a changed project. Export the normal project for analysis and the
bundle for provenance. A static project alone contains no formula trace. Neither API compilation
nor export writes the library or silently replaces existing measurements. Explicit recalculation
invalidates the previous target-review acknowledgement and export candidate. Bundle revalidation
is checked against this deterministic engine version; no cross-version migration is claimed.

## Separate fundamental-factor uncertainty integration

The [focused implementation and independent verification plan](derived-uncertainty-verification-plan.md)
specifies exact discrete dependency cases and analytic-moment gates. The separate integration now
implements factor-based MAVT/sorting/SMAA-2 runs with fixed weights; see the
[record](../development/factor-uncertainty-integration-verification.md). The remaining paragraphs
retain the design rationale; formulas are still sidecars, not embedded live project fields.

The existing SMAA-2 shared-draw model uses a common uniform variate through each cell's quantile
function (`smaa/engine.py`, `_sample`). It expresses the declared quantile coupling between cells;
it cannot represent a nonlinear derived output by giving that output its min/max as a uniform
distribution. The deterministic sidecar deliberately has no distribution fields.

A later extension should reuse numeric distribution validation on fundamental factor IDs, draw
each independent factor once per sample, and evaluate the dependency graph in topological order
for that same sample across all alternatives. References to a shared factor must reuse exactly
the same sampled value. Distinct factors may share a quantile draw only when that specific coupling
is explicitly stated; arbitrary correlations must remain unsupported. Use stable factor ordering,
recorded seed, algorithm/version and model digest. Feed the resulting raw measurements through
the ordinary value functions before MAVT aggregation. Do not draw a second output distribution.
Refuse unsupported dependence and supports allowing invalid arithmetic or out-of-domain results;
never silently discard invalid draws or replace them with zero.

Verify products/sums against analytic moments and small independent exact enumerations, shared
factor identities across alternatives, zero-variance reduction to this deterministic engine,
sample reproducibility and alternative-order invariance. Only after that should the extension
enter SMAA-2 results or inputs-to-check. A one-dimensional evidence range is not a distribution.

## Arithmetic contract

Owner clarification, 1 November 2026. This corrects a new test specification; it does not relax
an existing tolerance or change engine arithmetic.

1. Engine arithmetic remains IEEE-754 binary64. Declared decimal inputs convert to the nearest
   double. Each formula node is evaluated once in fixed expression-tree order, with one rounding
   per operation. There is no reassociation, fused operation, decimal mode or rational mode.
   The existing expression interpreter and factor evaluator remain unchanged; all pinned outputs
   remain byte-identical.
2. Engine-to-engine claims use bit-exact `==`, without tolerance: point mass versus the existing
   deterministic/compile path, enumeration versus sampling of the same support values,
   CLI/API/GUI parity, replay, chunk invariance and the proxy pair's baseline reproduction.
   Tests obtain deterministic reference values from that existing path rather than recomputing
   floating arithmetic in a test.
3. Engine-to-exact-oracle claims retain the exact decimal-string `Fraction` result and an
   independently derived forward rounding-error bound. Use the standard model
   `fl(x op y) = (x op y)(1 + δ)`, `|δ| ≤ u = 2⁻⁵³`
   (Higham, *Accuracy and Stability of Numerical Algorithms*, 2nd ed., §2.2).
   An exactly representable input contributes zero error; another contributes `|x|u`.
   For addition/subtraction, operand error is `e_x + e_y`. For multiplication it is
   `|x|e_y + |y|e_x + e_x e_y`. For division it is at most
   `(e_x + |x/y|e_y) / (|y| - e_y)`; refuse a denominator interval containing zero.
   Each operation then adds `u (|exact result| + operand-error bound)`. Compute these bounds
   exactly with `Fraction`, independently of the application. Assert
   `|Fraction.from_float(engine) - exact| ≤ bound`; this is not a fixed tolerance.
   Keep exact equality cases for integers/dyadic inputs and exactly representable intermediate
   results for every formula shape. Bounds must not claim support outside their stated arithmetic
   model (for example overflow). Formula mutants must still be caught; a survivor is a stop.
4. Quantity checks and boundaries compare the computed binary64 value exactly with the declared
   bound's binary64 value, without hidden tolerance. For example `0.1 + 0.2` produces
   `0.30000000000000004`, which fails an inclusive upper check of `0.3`. This is the same
   boundary policy as feasibility and the independent `allowed` oracle. Prefer starter checks on
   fundamental factors; do not put a derived check at a boundary reached exactly by the example.
5. Exports retain full precision. Screen rounding is display formatting only.
