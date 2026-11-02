# Feasibility check: mandatory requirements on individual measurements

**Status:** implemented and verified, 31 October 2026 ([check
record](../development/feasibility-check-verification.md)). The owner decided (open decision 2) that
requirements live in the project file, and accepted all seven recommended [decisions](#decisions).

A feasibility check tests each alternative's individual measurements against hard limits, such as
"unit price at most 45 NZD" or "certification is ISO 9001 or better", and reports **pass, fail or
unknown** for each requirement and each alternative. It sits **outside** aggregation. It reads no
weights, profiles, value functions or method inputs, and no score can compensate for a failed
requirement. The ranking stays visible, with feasibility shown beside it and never hidden inside it.
The roadmap section "Feasibility check" sets the scope; where they differ, this note wins.

## What exists today

- **Measurements:** one per alternative and leaf, a number on an interval or ratio scale (with an
  optional unit) or a label on a categorical or ordinal scale (labels run low to high). A missing
  measurement is a validation error for every method today.
- **Scenarios** override value functions and choose a profile; they never change measurements.
- **Value-based sorting** is different: it assigns classes from the *aggregate* value against
  thresholds on the overall scale. Feasibility tests *individual measurements* against hard limits.
- **Five methods and the comparison view** each read their own inputs; none has a notion of a
  mandatory requirement. A strong overall value can today hide a disqualifying measurement.
- **Schema version 5** (`sorting` 2, `smaa` 3, `promethee` 4, `ahp` 5), each section written only
  when used.

## Goals and non-goals

**Goals:**

- Requirements on leaf measurements: numeric bounds (minimum, maximum or both, each inclusive or
  exclusive, in the leaf's stated unit) and allowed labels.
- Pass, fail or unknown for every alternative and requirement, and overall: any fail is fail;
  otherwise any unknown is unknown; otherwise pass. A missing measurement is unknown, never fail.
- Shown beside every method's ranking and in the comparison view, with its own exports; no ranking
  is filtered, reordered or changed.
- **Every earlier output byte-identical** for unchanged inputs.

**Non-goals (excluded):**

- Soft constraints, penalties or weighting of requirements, and "pass by a margin" scores.
- Requirements on aggregates (that is value-based sorting) or on combinations of measurements.
- Probabilistic feasibility (for example from SMAA-2 draws) and unit conversion.
- Removing or hiding failing alternatives from any ranking.

## Design

### 1. Requirements, in their own section

```json
"requirements": [
  {"id": "price_cap", "name": "Unit price within budget", "criterion_id": "unit_price",
   "kind": "bound", "unit": "NZD", "maximum": 45, "maximum_inclusive": true,
   "rationale": "Board-approved budget"},
  {"id": "certified", "name": "Certified quality system", "criterion_id": "certification",
   "kind": "labels", "allowed": ["iso9001", "iso9001_14001"]}
]
```

- **`bound`** (numeric leaves): `minimum` and/or `maximum`, each with `*_inclusive` (default
  true), and `unit`, which must equal the leaf's unit exactly (decision 2).
- **`labels`** (labelled leaves): the allowed labels. For an ordinal leaf the editor offers "at least
  X" and "at most X", which write the explicit set (decision 1).
- `id` (stable), `name` and an optional `rationale` are for people and exports.

The section is method-independent: no method reads it, and it reads no method's inputs.

### 2. Evaluation

For a requirement on leaf `j` and an alternative `a` with measurement `x`:

- **unknown** if `x` is missing, or not usable on the leaf's scale (a label on a numeric scale, a
  number or unknown label on a labelled one), with the reason (decision 3);
- **unknown** if multiple measurements name the same alternative and criterion, even if their
  values agree: the conflicting entries must be resolved rather than choosing one by order;
- for `bound`: **pass** if `x` satisfies every stated limit (`x ≥ min` or `x > min`, `x ≤ max` or
  `x < max`), otherwise **fail**, with the limit it breaks;
- for `labels`: **pass** if `x` is allowed, otherwise **fail**.

Comparisons are exact: no arithmetic comes before them, so there is no tolerance (decision 6).
Each alternative's overall status is fail if any requirement fails, otherwise unknown if any is
unknown, otherwise pass. With no requirements, there is no feasibility result.

### 3. The result

`FeasibilityResult` contains:

- the project fingerprint and the requirements as evaluated;
- per alternative: its overall status, and per requirement its status, measurement and reason (for
  example "47.5 NZD is above the maximum 45 NZD", or "no measurement");
- per requirement: how many alternatives pass, fail and are unknown;
- the label "feasibility: each requirement is tested on its own measurement; no score offsets a
  failure".

It does not depend on the method, profile or scenario: scenarios never change measurements, and
requirements never read weights (decision 7).

### 4. Where it appears

- **Its own read-only route**, `POST /api/feasibility` (and per stored project), and its own
  exports: JSON and a CSV with one row per alternative and requirement (decision 4). No method's
  result or record changes.
- **Beside every ranking:** the Results views of every method and the comparison view show each
  alternative's overall status next to it, with the failing requirements on hover and in a
  Feasibility panel. Nothing is filtered or reordered (decision 5).
- **CLI:** `mcda requirement bound|labels|remove|clear` and `mcda feasibility FILE`; `mcda
  evaluate` and `mcda compare-methods` print each alternative's status beside it when the project
  has requirements.
- **A Requirements editor tab** with the requirement list, a per-leaf form for bounds (in the leaf's
  unit, shown beside the field) or labels (with the ordinal helper), and the live result as you
  type, computed in Python.

### 5. Storage and schema

An optional `requirements` list joins the project, written only when non-empty, with
`SECTION_VERSIONS["requirements"] = 6`; every other project keeps its version. Migration 5 → 6 is
the identity and refuses a version-5 file holding `requirements`. Edits: `set_requirements` and
`clear_requirements` replace the whole list. Removing a criterion removes its requirements;
removing a label from a scale is reported by validation, never repaired.

### 6. Validation

| Code | Severity | When |
| --- | --- | --- |
| `UNKNOWN_REQUIREMENT_CRITERION` | error | a requirement names an unknown criterion or a non-leaf |
| `DUPLICATE_REQUIREMENT_ID` | error | two requirements share an id |
| `REQUIREMENT_SCALE_MISMATCH` | error | a `bound` on a labelled leaf, or `labels` on a numeric one |
| `REQUIREMENT_UNIT_MISMATCH` | error | a bound's unit differs from the leaf's unit |
| `EMPTY_REQUIREMENT` | error | a bound with neither limit, or an empty label set |
| `INVALID_BOUNDS` | error | minimum above maximum, or equal with either side exclusive |
| `UNKNOWN_REQUIRED_LABEL` | error | an allowed label the scale does not have |
| `REQUIREMENT_ALWAYS_PASSES` | warning | a labels requirement that allows every label |

Requirement errors block only the feasibility result; methods ignore requirements entirely.

## Verification plan

- **Oracle:** `tests/regression/feasibility_oracle.py`, plain Python checked in a clean interpreter
  to load no `mcda_studio` module, recomputing every status, reason class and overall status from the
  project JSON.
- **Boundary tests:** values exactly at each limit, inclusive and exclusive, just inside and just
  outside (adjacent floating-point numbers); both limits; labels at the edges of an ordinal helper.
- **Unknowns:** a missing measurement, a wrong-type measurement and an unknown label are unknown,
  never fail or pass, and an alternative with one unknown and no failure is unknown overall.
- **Independence:** changing weights, profiles, value functions, scenarios or any method section
  never changes the result; a failing alternative keeps its rank in every method.
- **Validation:** every code. **Schema:** version 6 only when used, no empty list written, the
  migration refusal, clearing that restores the bytes, and pruning on criterion removal.
- **Byte identity:** every earlier output (MAVT, sorting, SMAA-2, PROMETHEE II, AHP and the
  comparison), with `scripts/byte_identity.py` gaining the comparison.
- **Frontend and browser:** the editor and its live result, status beside every method's ranking
  and in the comparison view, and a GUI case from blank: add requirements, see pass, fail and
  unknown, confirm the ranking is unchanged, and export.
- **Mutants** (`--feasibility-only`):
  - an inclusive bound compared with `<` (and an exclusive one with `≤`);
  - a missing measurement treated as fail;
  - a missing measurement treated as pass;
  - a failed requirement compensated (overall pass when the alternative ranks first, or when most
    requirements pass);
  - unknown outranking fail in the overall status;
  - the unit check skipped;
  - an absent section written as an empty list;
  - the section written as version 5;
  - frontend: a failing alternative hidden from a ranking;
  - frontend: the status not shown beside the ranking;
  - frontend: unknown shown as pass.

## Acceptance

- Requirement types, inclusive and exclusive bounds, units and unknown handling behave as in §2,
  matching the oracle at every exact limit.
- Requirements never depend on weights, profiles, value functions or scenarios, and no score can
  offset a failure.
- Every ranking stays complete and unchanged, with feasibility beside it.
- Every earlier output is byte-identical; projects are written at the lowest sufficient version.
- A GUI case from blank passes; the full gate is green, and every new mutant is killed.

## Decisions

1. **Requirement kinds.** *Recommended:* numeric bounds and allowed-label sets, with the ordinal
   "at least / at most" helper writing an explicit set, so what is stored is always what is tested.
   *Alternative:* store ordinal thresholds as their own kind, which reads naturally but changes
   meaning silently if the labels are reordered.
2. **Units.** *Recommended:* every bound states its unit, which must equal the leaf's unit exactly;
   a mismatch is an error, and nothing is converted. *Alternative:* no unit field, implicitly the
   leaf's unit, which goes silently wrong if the leaf's unit is later changed (for example from
   NZD to thousands of NZD).
3. **Unknown.** *Recommended:* a missing measurement is unknown, and so is one that is unusable on
   the leaf's scale, with its reason; overall, any fail is fail, then any unknown is unknown.
   *Alternative:* treat an unusable measurement as a validation error that blocks the check, which
   hides every other alternative's result behind one bad cell.
4. **Where results live.** *Recommended:* a result, route and export of its own, read beside every
   ranking, so no method's result, record or bytes change. *Alternative:* embed feasibility in each
   method's record, which changes five record schemas and ties requirements to methods.
5. **Effect on rankings.** *Recommended:* none: failing alternatives keep their place in every
   ranking and are flagged beside it. *Alternative:* an option to rank only feasible alternatives,
   which changes method outputs and hides alternatives; excluded by the roadmap's "never hidden".
6. **Comparing at a limit.** *Recommended:* exact comparison with no tolerance, since a measurement
   is compared as entered, with no arithmetic before it; limits are shown at full precision.
   *Alternative:* a relative tolerance as elsewhere, which would let 45.000000000001 pass a maximum
   of 45 that was meant to be hard.
7. **Scenarios.** *Recommended:* requirements apply in every scenario and profile; since scenarios
   never change measurements, feasibility is the same everywhere and says so. *Alternative:*
   per-scenario requirements, which turn a hard requirement into a preference.
