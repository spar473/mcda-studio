# Flood defence options: an invented feasibility and PROMETHEE II study

**Status:** Accepted by the owner, 18 November 2026, in chat (every recommended decision). Part of [method exemplars](method-exemplars.md), which sets
the shared rules (shape, invention, registration, verification). **Implemented and locally verified 19 November 2026** (development record, not included).

A small coastal town compares five ways of reducing flood risk. One measurement is a hard
requirement (a protection standard) that no score may offset. The study shows the
[feasibility check](feasibility-check.md) beside the rankings and
[PROMETHEE II](promethee-ii.md) beside MAVT. Every name and figure is invented.

## Why this study

- The feasibility check is stated today only in the venture study. A safety limit is the clearest
  non-venture reason for it, and the [method limitations](../mathematics/method-limitations.md)
  tell readers to state such a limit there, not to rely on a low weight.
- PROMETHEE II has no non-venture study. Its preference functions need thresholds in the
  measurement's own units, which public works supplies naturally (years, millions, hectares).

## Design

### 1. The model

Alternatives: *Raised sea wall*, *Dune restoration with pumping*, *Flood gates and raised road*,
*Managed retreat of the lowest street*, *Maintain the existing defences*.

| Group | Leaf | Scale | Direction |
| --- | --- | --- | --- |
| Protection | Flood protection standard | ratio, years (return period) | higher is better |
| Protection | Residual risk if overtopped | ordinal: low, medium, high | lower is better |
| Cost | Capital cost | ratio, NZD millions | lower is better |
| Cost | 50-year maintenance cost | ratio, NZD millions | lower is better |
| Environment and community | Habitat disturbed | ratio, hectares | lower is better |
| Environment and community | Consent pathway | ordinal: routine, notified, contested, not consentable | easier is better |
| Environment and community | Construction disruption | ratio, months | lower is better |

- **MAVT** reads value functions with fixed anchors and two profiles, *Safety-first* and
  *Cost-conscious*. No scenario.
- **Requirements** (two, in the leaf's own unit and labels):
  - protection standard at least 100 years, limit inclusive (a `bound` requirement, unit `years`);
  - consent pathway one of routine, notified or contested (a `labels` requirement).
- **PROMETHEE II** reads its own section: a direction, a weight and a preference function with
  thresholds for each leaf, and a number for each label on the two ordinal leaves. Its weights are
  stated separately from the swing ratings and say what they are: importances applied to
  preference degrees.
- **Saved method:** `mavt` (decision 1).
- **Stated sections:** MAVT inputs, `requirements` and `promethee`. Sorting, SMAA-2 and AHP are not
  stated, so the comparison view shows typed "not stated" errors for them.

### 2. Design intent (checked after the build, reported as found)

- **A cheap option cannot hide a failure.** *Maintain the existing defences* is the cheapest and
  fails the protection standard. It still appears in every ranking, with its failed requirement
  beside it. Nothing is filtered or reordered.
- **An exact limit.** One option's protection standard equals the limit exactly and passes,
  because the limit is inclusive.
- **Both requirement kinds fail somewhere.** Exactly one option fails the consent requirement.
- **A capped advantage.** Preference thresholds are set so that a large cost advantage reaches full
  preference and counts no further, and at least one pair's difference equals a threshold exactly,
  so it counts no preference. Whether PROMETHEE II and MAVT then order any two options differently
  is read from the comparison view, not assumed.
- **Wording.** The README says what the PROMETHEE II note says: a large advantage counts only up to
  full preference. It also says the ranking still compensates, and that the requirement is the
  hard limit. It does not call PROMETHEE II non-compensatory (see the
  [common note](method-exemplars.md#wording-finding-for-the-owner)).
- If the intent is not met, I adjust the invented inputs and say so in the record.

### 3. Edge cases

- **Pass and fail only.** A missing measurement makes a ranking unavailable, so this study shows no
  "unknown" requirement status; the README says that "unknown" exists and why it does not appear.
- Each requirement's unit equals the leaf's unit exactly; nothing is converted.
- PROMETHEE II's thresholds are in the leaf's units and, on ordinal leaves, in the stated codes.

## Excluded

- Soft constraints, penalties or weighting of a requirement; requirements on combinations of
  measurements.
- Sorting, SMAA-2, AHP and sidecars (see the common note).
- Any claim about real flood engineering, standards or costs.

## Verification

As the [common note](method-exemplars.md#5-verification-common-to-all-three), plus:

- `feasibility_oracle` recomputes every requirement's status and reason from the project JSON;
  `promethee_oracle` recomputes the flows, relations and flow-gap splits exactly.
- **Headline facts table (reviewed by the owner):** the five-by-two status grid and each overall
  status, the PROMETHEE II net flows and leader, and the MAVT leader under each profile.
- **Mutants** edit `build.py` and must fail the study's test: the protection limit made exclusive
  (the exact-limit option must flip to fail), the limit's value moved, the consent set widened, a
  cost leaf's direction flipped, a V-shape threshold changed, and the threshold that one pair hits
  exactly moved.

## Decisions

1. **Saved method `mavt`.** *Recommended:* the base reading, with Compare as the next click.
   *Alternative:* `promethee2`.
2. **Two requirements, one of each kind.** *Recommended.* *Alternative:* only the numeric one.
3. **No scenario.** *Recommended.* *Alternative:* one scenario, as the supplier examples have.

## Implementation notes

Built as designed, with the three decisions as recommended. What differed, and what the engine found
(read from the run and pinned in `tests/regression/test_method_exemplars.py`):

- **Ordinal labels are listed worst to best.** The table above lists them in a reading order. The
  engine reads an ordinal scale low to high and refuses a mapping that decreases along it
  (`ORDINAL_ORDER_VIOLATED`), so the residual-risk labels are stored as high, medium, low, and the
  consent labels as not consentable, contested, notified, routine. The requirement's allowed set and
  PROMETHEE II's codes are unaffected.
- **The requirement intent was met.** *Maintain the existing defences* fails the protection standard
  (25 years against at least 100), *Dune restoration with pumping* sits exactly on the inclusive
  limit (100 years) and passes, and *Managed retreat of the lowest street* is the one option that
  fails the consent requirement.
- **A failed option is still ranked.** *Managed retreat* leads PROMETHEE II and leads MAVT under
  *Cost-conscious*; *Maintain the existing defences* is third in PROMETHEE II. A test removes the
  requirements and finds every MAVT value and PROMETHEE II flow unchanged.
- **MAVT and PROMETHEE II differ under *Safety-first*** on four pairs, and agree on the leader under
  *Cost-conscious*. The design intent was a readable difference, which the engine found without any
  change to the first set of invented inputs.
- **An exact threshold is exercised.** *Managed retreat* (0.8 ha) and *Dune restoration* (0.4 ha)
  differ by exactly the 0.4 ha indifference threshold, which counts no preference.
- **The project is written at schema version 6**, the lowest that holds requirements and a
  PROMETHEE II section together.
