# Measurement ranges — 31 October 2026

Base: combined checkpoint `d7f8f8c` on `main`. The current chat is the integration owner.
The app inventory showed no other active Codex chat in this checkout, and the process inventory
showed no other repository writer. No reset, reconstruction or push was performed.

Before consolidation, 410 tracked and untracked files were archived with a verified hash manifest
in a durable local directory outside the repository.
Ignored historical project artifacts were preserved separately; dependencies, caches and browser
output were excluded from the commit. The combined checkpoint contains both agents' source work.

## Implemented

Accepted evidence ranges matching entered numeric measurements can produce actionable Open
Questions through CLI, API and editor. Only one cell varies; anchors, weights, other measurements,
profile and scenario are fixed. Existing MAVT and class assignment functions decide change flags.
Linear, direct-rating and monotone piecewise-linear functions are supported, including decreasing
functions, flat segments, zero weights, closed endpoints and singleton ranges.

The target score is affine on each segment. Exact rational inversion finds contacts with other
alternatives' score-minus-tolerance and class-boundary-minus-tolerance levels. The response retains
exact coordinate ratios as well as rounded values. Flat contacts are intervals. Score extrema
occur at endpoints or control points; the target's competition rank and sorting class are monotone
in its score, so evaluating these extrema decides whether either can differ from baseline.
Engine-evaluated witnesses are separate from analytical contacts: rounding a root does not decide
which side of a boundary a representable measurement occupies. A contact alone may leave the
rank or class unchanged. No global robustness or probability-distribution claim is made.

Local linear anchors, out-of-domain bounds, missing/invalid models, stale dossiers, unreviewed
claims and ranges attached to a different accepted or corrected value are explicitly unavailable.
Shared upstream factors are held fixed, not propagated. A complete evidence support audit remains
outstanding.

## Reproduce

Run the focused mathematical, question and API tests:

```sh
.venv/bin/python -m pytest -q tests/unit/test_measurement_range.py tests/unit/test_questions.py tests/api/test_api_questions.py tests/regression/test_measurement_range_oracle.py
.venv/bin/python scripts/mutation_check.py --measurement-range-only --backend-only
```

The independent oracle imports NumPy/SciPy, never the application; generated increasing/decreasing
piecewise models are checked against interpolation and numerical roots. Rational hand examples,
tolerance-adjacent values and fresh ordinary engine evaluations check boundaries and witnesses.

For the browser demonstration, import `examples/supplier_qualification/project.json`, open
Open Questions and select a local copy of `examples/evidence_demo/supplier.json` with its first
claim set to value 42 and range [20, 60]. The synthetic source is explicitly illustrative.
Expand **Measurement range analysis** to inspect witnesses and boundary contacts. No project
measurement or saved byte changes. The browser suite automates this with an isolated project ID
and a dossier fingerprint obtained from that exact imported copy.

The full browser run preceding this change failed on a 409 from a duplicate VC example ID, not a
performance assertion. The tests now use separate IDs and bind dossiers to those exact imports.
The earlier Playwright trace-artifact failure has no confirmed root cause; assertions are unchanged.

Combined verification: 1,543 Python tests passed; 385 frontend tests passed; TypeScript, ESLint,
generated types, build, Ruff, formatting, mypy (73 source files), OpenAPI freshness, acceptance demo
and acceptance evidence passed. All 969 numerical/export outputs matched `61ff58e` byte for byte.
The complete browser suite passed 91/91 in 3.7 minutes, including unchanged performance assertions.
Seven targeted range mutants were killed and the unmodified scratch baseline passed. The other
mutation groups were not rerun in this increment. After final wording and CLI-test additions,
the affected question/API tests were rerun; product mathematics was unchanged. Logs are retained
with the durable checkpoint. No independent human usability session has occurred.
