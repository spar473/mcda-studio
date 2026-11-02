# Validation

The visible model is implemented, and its Canvas is now a left-to-right value-tree diagram. See
[visible-model verification](package-d1-verification.md) for current checks, timings and outstanding human
acceptance. Earlier milestone counts below remain historical records. Measurement coverage,
library backup and restore, the method seam, value-based sorting, SMAA-2, PROMETHEE II, AHP, the
method comparison view and the feasibility check are implemented; the evidence workflow with the
decision record is next.


This page records how MCDA Studio is verified and what the latest full verification found. How to
run each check is in [testing](testing.md).

> **Summary.** The complete quality gate passed on 26 October 2026. The engine reproduces the
> printed results of the VC reference study, and independent oracles for that study and for the
> infrastructure example. This is an engineering assessment backed by tests. It is not external
> certification, a universal browser or accessibility claim, or DECERNS compatibility.

The feasibility check adds a separate [check record](feasibility-check-verification.md) (31
October 2026: 1503 Python, 380 frontend and 88 browser tests, 183 of 183 mutants; every status
equal to an independent oracle at every exact limit; 969 earlier outputs byte-identical).
The method comparison view adds a separate [check record](method-comparison-verification.md) (31
October 2026: 1446 Python, 371 frontend and 87 browser tests, 169 of 169 mutants; every column
equal to its method's own result; 789 earlier outputs byte-identical).
AHP adds a separate [check record](ahp-verification.md) (31 October 2026: 1404 Python, 365
frontend and 86 browser tests, 159 of 159 mutants; a published matrix reproduced; MAVT, sorting,
SMAA-2 and PROMETHEE II outputs byte-identical over 741 outputs).
PROMETHEE II adds a separate [check record](promethee-ii-verification.md) (31 October 2026: 1137
Python, 359 frontend and 85 browser tests, 144 of 144 mutants; two published examples reproduced;
MAVT, sorting and SMAA-2 outputs byte-identical over 645 outputs).
SMAA-2 adds a separate [check record](smaa-2-verification.md) (30 October 2026: 903 Python, 347
frontend and 84 browser tests, 127 of 127 mutants; MAVT and sorting outputs byte-identical over 565
outputs).
Value-based sorting, with the rest of the method seam, adds a separate
[check record](value-based-sorting-verification.md) (29 October 2026: 815 Python, 338 frontend and
83 browser tests, 112 of 112 mutants; MAVT outputs byte-identical over 410 outputs; hosted run
40860274947 green).
The method seam's backend contract adds a separate [check record](method-seam-verification.md)
(28 October 2026: 731 Python, 313 frontend and 81 browser tests, 94 of 94 mutants; MAVT outputs
byte-identical on all three examples).
Library backup and restore adds a separate [check record](library-backup-verification.md)
(27 October 2026: 700 Python, 313 frontend and 81 browser tests, 86 of 86 mutants, including 11
backup mutants).
Measurement coverage adds a separate [check record](measurement-coverage-verification.md)
(27 October 2026: baseline 651 Python, 278 frontend and 77 browser tests, 71 of 71 mutants; after,
652 Python, 313 frontend and 81 browser tests, 75 of 75 mutants). During that run a Hypothesis
property test found a subnormal span on which its NumPy reference (`np.interp`) overflowed to `inf`
while the engine correctly returned 0.5. The reference now uses exact rational arithmetic, and the
case is pinned as a regression test; engine code is unchanged.
Analysis retry adds a separate [check record](analysis-retry-verification.md)
(27 October 2026: 651 Python, 278 frontend and 77 browser tests, 71 of 71 mutants).
Library ownership and recovery add a separate [record](package-c1-verification.md).
Installation and startup add a separate [check record](package-b-verification.md).
The historical application results below remain intact; missing build tooling in the planning
pass was a distribution-check gap, not a failure of these application tests.

## Latest full run (26 October 2026)

**Environment:** macOS 26.5.1 (arm64), Python 3.12.15, Node 26.12.1, npm 11.20.0, Google Chrome
155.0.8059.85.

**Python packages:** numpy 2.5.4, pydantic 2.14.1, typer 0.27.3, rich 15.0.0, fastapi 0.162.0,
starlette 1.10.0, uvicorn 0.54.0, httpx 0.28.1, pytest 9.1.1, hypothesis 6.170.9, scipy 1.18.1,
ruff 0.17.2, mypy 2.4.0.

| Gate | Result |
| --- | --- |
| Python tests (`pytest`) | **616 passed**, 0 skipped |
| Frontend unit/component tests (Vitest) | **234 passed** (24 files) |
| Browser tests (Playwright, native Chrome) | **67 passed** |
| Mutation check | **64 of 64 mutants killed**; the unmodified baseline passes |
| Ruff lint and format | Pass |
| mypy `--strict` | Pass (37 source files) |
| OpenAPI and TypeScript type freshness | Pass |
| TypeScript, ESLint (0 warnings), production build | Pass |
| Acceptance demo (save, reopen in a fresh process, reproduce) | Pass |
| Acceptance evidence script (oracles, reconciliation, timings) | Pass |

The only warning is an upstream Starlette/httpx `TestClient` deprecation notice. It is not a test
failure. No assertion or numerical tolerance has ever been loosened to obtain a pass.

## Reference results

### NZ deep-tech VC study

Each value printed in the report must **round** to the printed digits, which is stricter than a
half-unit tolerance. An independent plain-Python oracle in the test module, with no `mcda_studio`
imports, recomputes everything from the report's inputs. Scores and weights agree to 1e-12, and
crossovers to 1e-9.

| Quantity | Report | Engine |
| --- | --- | --- |
| Base overall values (FH / Outlier / Kura / Hyades) | 0.723 / 0.660 / 0.599 / 0.573 | 0.7226678550207962 / 0.6599105426568632 / 0.5985654393128845 / 0.5733847765581512 |
| Parent weights (Team, P&S, Market, Traction) | 0.2941 / 0.2647 / 0.2353 / 0.2059 | same to 4 d.p. |
| Global leaf weights | 0.1783 0.1159 0.1254 0.1393 0.1307 0.1046 0.1211 0.0848 | same to 4 d.p. |
| Linear Market Size scenario (FH / Outlier / Hyades / Kura) | 0.723 / 0.652 / 0.573 / 0.556 | 0.7226678550207962 / 0.6522895803586373 / 0.5733847765581512 / 0.5561197227066853 |
| Linear Market Size partial values | 0.000000 / 0.013279 / 0.128440 / 1.000000 | same, within 5e-7 |
| Market Growth partial values | 0.000 / 1.000 / 0.062 / 0.569 | rounds to printed |
| Tie at the Market Size crossover | FH and Hyades ≈ 0.648; global weight ≈ 0.205 | tie at 0.648; weight 0.2054 |

| First winner change | Report | Engine (exact) | Engine − oracle |
| --- | --- | --- | --- |
| Team (parent) | Outlier at ≈ 0.569 | 0.5688552162065278 | −6.7e-16 |
| Market (parent) | Hyades at ≈ 0.674 | 0.6736973263477098 | 1.1e-16 |
| Market Size (local) | Hyades at ≈ 0.873 | 0.8727820972886765 | 0 |
| Problem & Solution, Traction | none over [0, 1] | none | — |

A probe at each exact crossover reports competition ranks **1, 1, 3, 4**. The one known precision
gap, caused by the report's rounded control points, is explained in the
[example README](../../examples/nz_deeptech_vc/README.md#known-limitation-rounded-control-points).

### Other independent checks

| Check | What it verifies |
| --- | --- |
| `tests/regression/test_supplier_selection.py` | A separate 5-alternative problem. Every score, weight, scenario and one crossover is recomputed by a plain-Python oracle, to 1e-12 |
| `tests/regression/test_infrastructure_procurement.py` | Three levels, 3/2/2/1 children, an only child, a zero rating, two disagreeing profiles and a profile-aware scenario. A hand-written oracle checks weights, values and the structure itself, so the fixture cannot be quietly simplified |
| GUI-built Auckland living decision (`case-b-new-project.spec.ts`) | A model created entirely through the GUI. Scenario result: Riverside 0.5915343915343916, Downtown 0.5735449735449736, Hilltop 0.3846560846560847, matching an independent TypeScript oracle and the CLI |
| Hand-checked 2×2 Cost/Quality case | 0.7333 / 0.5667, with the winner flipping at exactly 3/7, including a baseline exactly on the crossover (a tie) |
| Three siblings rated 50/30/20 | Setting the first local weight to 0.7 gives 0.7 / 0.18 / 0.12 |
| Piecewise interpolation | Cross-checked against `numpy.interp` |
| Sensitivity crossovers | Cross-checked against `scipy.optimize.brentq` on a separate evaluation path, to 1e-9 |
| Property tests (Hypothesis) | Monotonicity, normalisation on random trees, convex-combination bounds, order invariance, fixed-anchor independence, preview invariants, save/load round trips |
| Exports | JSON regenerates exactly. GUI-built CSV equals the Python bytes. SVG provenance parses. Hostile CSV text (formulas, whitespace, control and full-width characters) is encoded without changing stored text |

## Mutation testing

`scripts/mutation_check.py` injects 64 deliberate defects, one at a time, into a scratch copy of
the repository. The relevant suite must fail for each one. The defects span:

- API and store rules: partial edits, ignored `If-Match`, path traversal, destructive delete;
- weighting and profiles;
- sensitivity redistribution and tie reporting;
- scenario isolation;
- analysis records and exports;
- frontend logic: stale responses, cancellation, hidden series.

Mutants that turn out to be equivalent or unreachable are replaced or reported as such, never
counted as "killed".

## Defects found by verification and fixed

| Found by | Defect | Fix |
| --- | --- | --- |
| VC linear scenario | A scenario override that makes a criterion use local anchors produced no `LOCAL_ANCHORS` warning | Always warn, naming the scenario path; regression test added |
| Fresh-seed property run | Sensitivity redistribution computed `1 − λ` by subtraction and lost about 4 digits near λ ≈ 1 | Sum the sibling weights instead; tolerance-1e-14 test |
| Surviving mutant | No test pinned that the domain tolerance is relative to the span, not the anchor magnitude | Test added |
| Edge-case probe | Local anchors whose spread is floating-point noise were silently stretched to 0–1 | New `NEAR_DEGENERATE_LOCAL_ANCHORS` warning |
| Native browser run | Overlapping whole-scale edits could restore an older lower bound | Measurement controls are disabled while an edit is in flight |
| Independent test | A preview output aliased a scenario override | The effective override is copied |
| Mutation W8 | A stale response could be accepted when the configuration matched but the resolved profile differed | Responses check the resolved profile separately |
| Mutation S1 | Sweep and probe had duplicate redistribution code | Consolidated into one implementation |
| Native Firefox review | At an exact crossover, the probe said "ranking unchanged" when a tie formed, because it compared sorted ID lists | It now compares competition ranks and rank-one winner sets; two new mutants guard it. No numbers changed |

## Performance

These timings are for the deterministic fixture `tests/fixtures/performance_project.json`: 50
alternatives, 40 leaves, 52 nodes, three levels, 2,000 measurements, two profiles and two
scenarios. Backend timings are medians of five warm runs on the machine above. They are workload
observations, not guarantees.

| Backend operation | Median (ms) |
| --- | ---: |
| Project load | 2.41 |
| Weight/range preview | 93.72 |
| Full evaluation | 16.35 |
| Sensitivity sweep and exact crossovers | 20.14 |
| Exact probe | 11.48 |
| Base completed record | 22.90 |
| Scenario completed record | 42.97 |
| Contribution CSV, with context verification | 201.09 |

**In the browser** (earlier native run): load and tree took about 0.1 s, results and charts about
1.3 s, a scenario switch about 1.3 s, and a JSON download about 0.3 s (790 KB). The weight/range
preview is the clearest optimisation target. Nothing so far needs a database, worker or cache.

## Not validated

| Item | Status |
| --- | --- |
| DECERNS behavioural or file compatibility | Not validated. No authorised installation has been examined |
| Safari, screen readers, WCAG conformance | Not tested or claimed. Chrome is automated; Firefox and an embedded browser were checked by hand |
| Multi-user or network deployment | Out of scope (see [known limitations](known-limitations.md)) |
| Methods other than additive MAVT | Not implemented |
| Unrounded control points of the source study | Not available; the printed points are used |
