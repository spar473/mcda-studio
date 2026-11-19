# Portable outputs: the same bytes on every platform

**Status:** direction accepted by the owner in chat on 16 November 2026, answering the decisions
in the classifier comparison report (development record, not included):
"let make it compatible for both platforms" (the supplier golden tie) and "across" (byte identity
should hold across platforms, not only within one). The details below are Claude Code's design
within that direction, reported for the owner's review in the
development record (not included).

## The problem

Every byte-identity record before 16 November compared a Mac with the same Mac. The first Linux
gate found two things:

1. **188 of the 969 historical output bodies differ** between the Mac's manifest and Linux. They are
   the sensitivity outputs, the SMAA-2 outputs and the method comparisons that contain them.
2. **The supplier qualification golden report** names a different "closest change" for three
   alternatives on Linux.

Comparing Linux with native Windows found the same kind of differences. Four causes, all outside
the stated mathematics:

| Where | What differs between platforms |
| --- | --- |
| One-way sensitivity (`methods/mavt/sensitivity.py`) | Overall values on the grid and at the endpoints are `partial @ weights`, a BLAS product. Apple Accelerate and OpenBLAS sum the terms in different orders, so the last bit differs. (Linux and Windows both use OpenBLAS and agree; the Mac does not. No summation order tried on Linux reproduced the Mac's hashes.) The MAVT evaluation itself already uses `math.fsum`, which is why its outputs match everywhere. |
| SMAA-2 intervals (`methods/smaa/intervals.py`) | Clopper-Pearson bounds bisect on the incomplete beta function, which calls `math.lgamma`, `math.log`, `math.log1p`, `math.exp` and `**`. These come from the platform's C maths library (Apple libm, glibc, the Microsoft runtime), which may round the last bit differently, and the bisection carries that into the bounds. |
| SMAA-2 sampling (`methods/smaa/engine.py`) | Exponential draws use `np.log1p` (the C library again). Overall values per draw use `np.einsum`, and group totals use `ndarray.sum`, whose summation order can depend on the build and the CPU's vector instructions. Near-ties are already re-summed with `math.fsum`, so ranks were protected, but the guarantee rested on luck elsewhere. |
| The closest change in the screening summary (`services/screening_summary_service.py`) | Two candidates that need the same weight change (lowering one of two siblings is raising the other) were compared with a strict `<`, so the last-bit noise above chose between them. |

A fifth difference is deliberate: SMAA-2, the factor runs and the model checks **record the machine**
(`environment`: Python version, NumPy version, operating system and processor). That record says
where a result was computed. It stays.

## Design

### Portable elementary functions

A new module, `src/mcda_studio/methods/portable.py`, provides `log`, `log1p`, `exp`, `lgamma` and
`power` built only from IEEE 754 operations that every platform rounds identically: `+`, `-`, `*`,
`/`, comparisons and exact scaling by powers of two (`frexp`, `ldexp`). The operations run in a
fixed order, one at a time, so the result has the same bit pattern on every IEEE 754 platform. The
algorithms are the classic fdlibm reductions (argument reduction by powers of two and `ln 2`, a
fixed minimax polynomial), Goldberg's `log1p` identity, and Stirling's series with an upward shift
for `lgamma`. Accuracy: within a few units in the last place of the correctly rounded value, tested
against a `decimal` oracle at 40 digits.

One algorithm serves both Python floats and NumPy arrays (a small backend supplies `frexp`, `ldexp`
and a branch-free `select`), so the scalar path in the intervals and the array path in the sampler
cannot drift apart.

### Where it is used

- **Sensitivity:** every `partial @ weights` becomes the existing `overall_values` (`math.fsum`,
  correctly rounded and therefore portable), the same summation the evaluation uses.
- **SMAA-2 intervals:** `math.lgamma`, `math.log`, `math.log1p`, `math.exp` and `**` become their
  portable versions. The bisection is unchanged.
- **SMAA-2 sampling:** `np.log1p` becomes the portable array `log1p`; group totals and per-draw
  overall values are accumulated column by column, left to right, with elementwise NumPy additions
  and multiplications (each correctly rounded per element). The PCG64 stream is already portable.
- **Closest change:** candidates whose weight changes differ by at most `TIE_TOL` (1e-12, the
  engine's ranking tolerance) are a tie, and the candidate met first in tree order (the order the
  criteria are already examined in) is kept. This is a stated rule where there was none.

Nothing else changes. No formula, estimator, sample count, seed, tolerance, schema, route or
interface text changes. The draws are the same uniforms mapped through the same functions; values
move only in their last bits.

### What changes in outputs, once

Values computed through the four places above can move in their last bits on every platform. The
969 historical bodies are therefore regenerated once: on Linux, this development compares the new
manifest with the old one and lists every changed output. The **Mac's pinned bodies change too**,
and the change cannot be checked from this Windows machine: the owner runs one command on the Mac
(below) to confirm the Mac now produces the Linux bytes.

The supplier golden report is regenerated under the stated tie rule. It is the only pinned fixture
file that changes. The client SVG fixtures, the factor records and `ExportCharts.tsx` do not depend
on these code paths and stay unchanged (checked, not assumed).

### Checking it across platforms

- `scripts/byte_identity.py --portable` writes the same manifest with the machine record held fixed
  (`platform` reports a fixed Python version, system and processor while the manifest is built), so
  every other byte, including digests over the record, can be compared between machines. The
  default mode is unchanged.
- `tests/fixtures/portable-outputs.json` pins the portable manifest's hashes of the sensitivity and
  SMAA-2 outputs of the four examples, and a regression test regenerates them. **The gate on any
  platform now fails if that platform computes different bytes**, so the next Mac gate checks the
  Mac.
- A unit test pins a digest of the portable functions over a fixed grid of inputs, so the
  functions themselves are checked bit for bit on every platform that runs the tests.

## Edge cases and refusals

- `log` of a non-positive number, `log1p` at or below −1, and `lgamma` at or below 0 raise
  `ValueError`, as the `math` versions do. `exp` above 709.78 raises `OverflowError`; below −745.2 it
  returns 0.0. NaN and infinities are not inputs on these paths (the callers validate first) and
  raise `ValueError`.
- Subnormal inputs and results are handled by `frexp`/`ldexp`, which are exact or correctly rounded
  per IEEE 754.
- The tie rule compares weight changes, which lie in [0, 1], so an absolute tolerance is right.

## Excluded

- **Native Windows** stays unsupported for the application (the library lock refuses it). Its one
  remaining difference is that a project saved on Windows gets CRLF line endings; that is storage
  behaviour on an unsupported platform and is not changed here.
- No removal or change of the `environment` record (that would be a result schema change).
- No change to the factor services, AHP, PROMETHEE II or sorting arithmetic: they already use
  `math.fsum` and correctly rounded operations, and their outputs already match across platforms.

## Verification

- Accuracy of each portable function against a `decimal` oracle (40 digits) over many inputs,
  including subnormals, values near 1 and huge arguments; refusals as above; the scalar and array
  paths agree bit for bit.
- The interval tests against `scipy.stats.beta.ppf` and the exact binomial oracle keep their 1e-12
  tolerance unchanged.
- Bit-pattern digests pinned in tests (functions, sensitivity and SMAA-2 outputs), so platforms are
  compared at gate time.
- Linux and native Windows produce identical portable manifests for all 969 outputs except the
  documented CRLF save bytes.
- New mutants for every new behaviour (polynomial terms, reductions, the `log1p` branch, the
  `lgamma` shift, the column-wise sums, the tie rule).
