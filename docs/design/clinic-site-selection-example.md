# Clinic site selection: an invented AHP study

**Status:** Accepted by the owner, 18 November 2026, in chat (every recommended decision). Part of [method exemplars](method-exemplars.md), which sets
the shared rules (shape, invention, registration, verification). **Implemented and locally verified 18 November 2026** (development record, not included).

A small authority chooses a site for a community health clinic from four candidate sites. It is the
first shipped study that states AHP pairwise judgements, set beside swing weighting that the same
author stated separately. Every name and figure is invented.

## Why this study

- AHP has an engine, an oracle and a design note ([AHP](ahp.md)) but no openable study.
- Siting is a familiar decision whose criteria mix measured quantities (minutes, services per hour,
  money) with judged ones (room to expand, community support), which is where pairwise judgement
  is most natural.
- It is small enough to read in full: 4 alternatives, 6 leaves, 42 judgements.

## Design

### 1. The model

Alternatives (plain descriptions): *Town centre site*, *Beside the hospital*, *Edge-of-town site*,
*Shared school site*.

| Group | Leaf | Scale | Direction |
| --- | --- | --- | --- |
| Access | Median travel time for the people served | ratio, minutes | lower is better |
| Access | Bus services per hour at the site | ratio, services/hour | higher is better |
| Cost | Land and build cost | ratio, NZD millions | lower is better |
| Cost | Annual running cost | ratio, NZD thousands/year | lower is better |
| Fit | Room to expand | ordinal: none, limited, ample | higher is better |
| Fit | Community support | ordinal: low, medium, high | higher is better |

- **MAVT** reads linear value functions with fixed anchors just outside the observed range on the
  four numeric leaves, and qualitative value functions on the two ordinal leaves. Two weight
  profiles, *Access-led* and *Cost-led*, with swing ratings stated per sibling group. No scenario.
- **AHP** reads only its own section: pairwise judgements for the three groups, for the two leaves
  in each group (3 + 1 + 1 + 1 = 6 judgements) and for the four sites on each of the six leaves
  (6 × 6 = 36). Judgements are literal values in `build.py` on the 1 to 9 scale. It reads no
  measurement, value function or swing rating.
- **Saved method:** `ahp` (decision 1). Viewing another method never changes the project.
- **Stated sections:** MAVT inputs and `ahp`. Sorting, SMAA-2 and PROMETHEE II are not stated, so
  the comparison view shows its usual typed "not stated" errors for them.

### 2. Design intent (checked after the build, reported as found)

- Exactly one site-versus-site matrix is deliberately a little inconsistent, with a consistency
  ratio above 0.10, so the example shows the `AHP_INCONSISTENT` warning, the Consistency panel
  listing inconsistent matrices first and the most inconsistent triad. All other matrices are
  consistent or under the threshold. The README says so.
- The two profiles' weights and the AHP criteria priorities are elicited separately. The README
  puts them side by side and says differences reflect different questions, not an error.
- If the intent is not met, I adjust the invented judgements and say so in the record; I do not
  touch the engine, the oracle or the threshold.

### 3. Edge cases

- Matrices are complete (4 items need 6 judgements) and values lie in 1 to 9; the largest matrix is
  4 items, far under the 15-item limit.
- Both syntheses are checked: distributive (the default) and ideal (the `synthesis` parameter).
- The README points to the Consistency panel, which lists every matrix's ratio, so a reader sees
  the flag next to the priorities.

## Excluded

- Group decisions (several judges), AHP sensitivity (not provided by the method) and any repair of
  an inconsistent matrix.
- Requirements, uncertainty and sidecars (see the common note).
- Any claim that AHP or swing weighting is the better elicitation.

## Verification

As the [common note](method-exemplars.md#5-verification-common-to-all-three), plus:

- `ahp_oracle` recomputes every priority, consistency ratio, triad and both syntheses from the
  project JSON; the engine must equal it.
- **Headline facts table (reviewed by the owner):** the AHP leader and the MAVT leader under each
  profile, the one flagged matrix and its triad, and the six criteria priorities.
- **Mutants** edit `build.py` and must fail the study's test: swapping the row and column of one
  judgement (changes a priority), making the flagged matrix consistent (the flag must disappear
  from the table), changing one weight profile's swing rating (the MAVT leader), and changing an
  ordinal label's position.

## Decisions

1. **Saved method `ahp`.** *Recommended:* it is the point of the study. *Alternative:* `mavt`.
2. **One deliberately inconsistent matrix.** *Recommended:* it shows the consistency check working.
   *Alternative:* all matrices consistent, so the example opens with no warning.
3. **No scenario.** *Recommended:* it keeps the study about weights and judgements.
   *Alternative:* add one scenario, as the supplier examples have.

## Implementation notes

Built as designed, with the three decisions as recommended. What the engine found (read from the run
and pinned in `tests/regression/test_method_exemplars.py`):

- AHP puts the Town centre site first under both syntheses; MAVT puts the Shared school site first
  under both profiles. The design intent was a readable difference, not agreement; the README says
  they are two readings of one model.
- Exactly one matrix is flagged: community support, consistency ratio about 0.164. Every other
  matrix is at or below about 0.03, so the intent was met with the first set of invented judgements.
- The project is written at schema version 5, the lowest that holds an AHP section.
