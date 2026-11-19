# Read-only previews

Two endpoints let the interface show value-function curves and derived weights before a whole model
is complete. Both are read-only, and both use the same Python code as full evaluation. Wire formats
are in the [API contract](../api/contract.md).

## Value-function preview

`POST /api/value-functions/preview`

**Request fields:**

- `project`
- `criterion_id`
- an optional `configuration`
- an optional `candidate`
- `sample_count` (default 101, range 2–501)

**How a candidate works:**

- **Contents.** It may contain a `scale` and/or a `value_function`.
- **Omitted fields** inherit from the effective base or scenario definition.
- **An explicit `null`** clears that field for the candidate only.
- **Replacements, not patches.** A supplied scale or function replaces the effective one whole and
  is validated with its schema defaults.
- **Nothing is stored.** No project is edited or saved.

**What comes back:**

- provenance: the original `project_fingerprint`, full `configuration`, and resolved
  `weight_profile_id` and `scenario_id`
- the echoed candidate and its `candidate_fingerprint`
- the effective scale and function, and the `resolved_domain`
- the readiness flags `curve_ready` and `measurements_complete`
- curve samples
- markers for each alternative's raw reading and partial value
- structured diagnostics

### Readiness, honestly reported

- **`curve_ready`** means the function can be inspected. It does **not** mean the project can be
  evaluated. A valid fixed-domain function is previewable even while other criteria, weights or
  measurements are incomplete.
- **Bad readings are reported, not guessed.** Missing, invalid or out-of-domain readings keep their
  raw markers with `null` partial values and a diagnostic. With an explicit clamp policy, the
  evaluator supplies endpoint values and the marker reports the clamping.
- **`measurements_complete`** needs at least one alternative and a valid, complete set of relevant
  readings.

### Local domains

A local linear domain needs a valid reading from every relevant alternative. If any is missing,
duplicated, of the wrong type, negative on a ratio scale or degenerate, there is no resolved domain
and no curve.

Adding or removing an alternative changes the fingerprint and re-resolves local domains. Existing
alternatives' partial values may then change. `LOCAL_ANCHORS` and `SWING_RANGE_REVIEW` explain that
dependence. Fixed-anchor curves do not depend on the alternative set.

### Sampling

- **What is always included.** Samples include both endpoints and every piecewise knot, and never
  exceed the requested budget.
- **Fewer samples are possible.** There may be fewer than the budget when knots coincide with
  probes.
- **No silent truncation.** If the budget cannot hold every knot, or a span cannot be represented,
  the result is `PREVIEW_SAMPLE_LIMIT` and no curve. Knots are never silently dropped.
- **Qualitative functions** return labelled values with no implied numeric spacing.

## Weight preview

`POST /api/weights/preview`

- **Request:** `project` and an optional `configuration`.
- **What it needs:** a sound tree and a valid selected swing profile. Scales, performance data and
  the number of alternatives do not matter.
- **What comes back:** provenance, `weights_ready`, complete local and global weights, sibling
  rating totals, the `weight_basis` sentence and diagnostics.

Rules:

- **No partial weight sets.** Invalid or missing ratings never return a partially normalised set.
- **Only children.** An only child gets local weight one from the engine rule. Its raw judgement
  stays absent, and its sibling total is reported as `null`.
- **Group totals.** Root-level totals use the key `<root>`. Other groups use their parent's stable
  ID.
- **Overflow is an error.** A rating sum that overflows is reported as `INVALID_WEIGHTS`.

## Errors versus incomplete models

Unknown references or methods, duplicate profile or scenario IDs, and a malformed tree return the
standard HTTP error envelope. A model that is merely *incomplete* returns HTTP 200 with readiness
flags and diagnostics.

A missing profile does not block a fixed value-function preview. The weight preview reports
`NO_WEIGHT_PROFILE`.

## Architecture and non-mutation

- **Types stay outside the project.** Response and candidate types live in `domain/previews.py`.
  They are not part of `Project` or the saved schema.
- **One set of rules.** `domain/validation.validate_leaf_model` exposes the same leaf rules used by
  full validation, so previews and evaluation cannot disagree.
- **No duplicated maths.** `methods/mavt/previews.py` calls the existing domain resolver, evaluator
  builder, weight computation and judgement checks. `analysis_service` coordinates them, and FastAPI
  only validates and translates. No calculation is repeated in TypeScript or in the HTTP handlers.
- **Copies, not references.** Inputs are deep-copied where they enter outputs. A preview never
  changes project JSON, fingerprints, history, files or ETags, and mutating an output cannot change
  the input.
- **Same request safety.** The frontend hooks use the shared analysis context, the same request
  keys, cancellation and provenance checks.
