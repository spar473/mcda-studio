# Engineering trade study: an invented study that states every method

**Status:** Accepted by the owner, 18 November 2026, in chat (every recommended decision). Part of [method exemplars](method-exemplars.md), which sets
the shared rules (shape, invention, registration, verification). **Implemented and locally verified 19 November 2026** (development record, not included).

A team chooses a concept for an autonomous inspection vehicle that will survey a long service
tunnel. This is the flagship of the three: the one study that states **every** method section, so
the comparison view shows five real columns and the feasibility check sits beside them. It is the
non-venture counterpart of `nz_venture_screening`, and it is the "engineering trade study" the
28 October 2026 plan had before the venture study replaced it. Every name and figure is invented.

## Why this study

- Engineering design is the project's stated home ground, and measurement uncertainty is natural
  here: a mass of 4.2 ± 0.3 kg is the roadmap's own example of a stated measurement range.
- It exercises everything at once: value functions and swing weights, sorting into classes,
  SMAA-2 under uncertain measurements and uncertain weights, PROMETHEE II's capped preferences,
  AHP's pairwise judgements and hard requirements.

## Design

### 1. The model

Alternatives: *Wheeled rover*, *Tracked crawler*, *Legged walker*, *Tethered crawler*,
*Small aerial drone*.

| Group | Leaf | Scale | Direction |
| --- | --- | --- | --- |
| Performance | Endurance | ratio, minutes | higher is better |
| Performance | Payload capacity | ratio, kg | higher is better |
| Performance | Obstacle capability | ordinal: low, medium, high | higher is better |
| Cost | Unit cost | ratio, NZD thousands | lower is better |
| Cost | Annual maintenance cost | ratio, NZD thousands/year | lower is better |
| Risk | Technology maturity | ordinal: concept, prototype, proven | higher is better |
| Risk | Operator skill needed | ordinal: low, medium, high | lower is better |

Five alternatives, seven leaves, three groups. The saved method is `mavt` (decision 1).

### 2. Each section, and who states it

- **MAVT:** value functions with fixed anchors (recommended for sorting, which warns on local
  anchors, so none are used); two
  profiles, *Performance-led* and *Cost-led*; one scenario that changes one measurement
  assumption, as the supplier examples' scenarios do.
- **Sorting:** three classes, *Shortlist*, *Reserve* and *Drop*, with illustrative boundaries on
  the overall value. No audit sample.
- **SMAA-2:** triangular or uniform distributions on endurance and payload for each concept
  (a stated test spread), a triangular distribution on unit cost for two concepts, a categorical
  distribution on technology maturity for one concept, `rating_intervals` weight uncertainty on the
  top-level group, and one shared draw for two cells from the same quote. Dependence is
  `independent`, the only supported kind. Parameters are the defaults (10 000 samples, seed 0, 0.95
  confidence).
- **PROMETHEE II:** its own direction, weight and preference function with thresholds per leaf,
  and codes on the three ordinal leaves.
- **AHP:** pairwise judgements for the three groups (3), the leaves of each group (3 + 1 + 1) and
  the five concepts on each of the seven leaves (7 × 10 = 70): 78 judgements, literal values in
  `build.py`. All matrices are consistent or under the 0.10 threshold, so the flagship opens
  without a warning (the clinic study shows the warning).
- **Requirements:** payload capacity at least a stated minimum (`bound`, inclusive, in kg), and
  technology maturity one of prototype or proven (`labels`).

The weights of MAVT, PROMETHEE II and AHP are stated separately and are never reused across methods.
The engine writes the lowest schema version that holds the stated sections; I do not choose it.

### 3. Design intent (checked after the build, reported as found)

- **A strong score cannot hide a failure.** The concept at the concept stage fails the maturity
  requirement. It stays in every ranking and class, with its failed requirement beside it.
- **Classes under uncertainty.** At least one concept sits close enough to a class boundary that its
  class acceptability under SMAA-2 is spread over more than one class.
- **Methods are read side by side.** The comparison view shows each method's leader and, where they
  differ, each method's own reason. Whether the methods agree is read from the engine, not assumed.
  Agreement would not be independent validation.
- **Feasibility is not probabilistic.** The requirement tests each entered value. SMAA-2 draws can
  fall below a limit that the entered value meets; the README says so.
- If the intent is not met, I adjust the invented inputs and say so in the record.

### 4. Edge cases

- A distribution's support must lie inside its value function's domain; the build checks this and
  validation refuses otherwise. A missing measurement is never filled by a distribution.
- Sorting boundaries are fixed on the value scale and shared by both profiles and the scenario.
- AHP matrices are at most 5 items, far under the 15-item limit.

## Excluded

- A decision record, evidence or any other sidecar; an audit sample; correlated sampling beyond one
  shared draw; probabilistic feasibility; unit conversion.
- Any claim about real vehicles, suppliers or costs.

## Verification

As the [common note](method-exemplars.md#5-verification-common-to-all-three), plus:

- `sorting_oracle`, `promethee_oracle`, `ahp_oracle` and `feasibility_oracle` recompute from the
  project JSON. SMAA-2 is a sampled run, so it is checked by interval containment at several seeds,
  as in the [SMAA-2 note](smaa-2.md); `comparison_oracle` recomputes the agreement from each
  method's own result.
- **Headline facts table (reviewed by the owner):** each method's leader, each concept's class under
  each profile, the requirement grid, the seven AHP leaf priorities and the SMAA-2 leader.
- **Mutants** edit `build.py` and must fail the study's test: a class boundary moved, a payload
  limit made exclusive, a distribution kind swapped (uniform for triangular), the weight-uncertainty
  interval narrowed, the shared draw removed, one AHP judgement's row and column swapped, a
  PROMETHEE II direction flipped, and a unit changed.

## Decisions

1. **Saved method `mavt`.** *Recommended:* the base reading, with Compare as the next click.
   *Alternative:* `smaa2`, to open on acceptabilities.
2. **No audit sample and no sidecars.** *Recommended:* it keeps the study about methods.
   *Alternative:* add the audit sample used by supplier qualification.
3. **Five concepts and seven leaves.** *Recommended:* wide enough for classes and acceptabilities,
   small enough to read. *Alternative:* four concepts, which makes three classes thin.

## Implementation notes

Built as designed, with the three decisions as recommended, except for the SMAA-2 section. What
differed, and what the engine found (read from the run and pinned in
`tests/regression/test_method_exemplars.py`):

- **SMAA-2 uses only what the existing independent sampler covers.** The design called for
  triangular distributions on some cells and one shared draw. `smaa_sampling_oracle` draws uniform and
  categorical cells and rating intervals, and draws cells independently; the exact oracle covers only
  all-discrete models. This note's own rule is that oracles are not changed, so the study uses uniform
  ranges (12 cells: ten ranges, one more range on unit cost, one categorical maturity) and rating
  intervals on the top-level group, with no shared draw. Every number of the shipped SMAA-2 model is
  therefore checked by an independent sampler. The engine's triangular, discrete and shared-draw
  features are exercised elsewhere (the venture study) and not here. Adding a test-side sampler for
  them is a possible later change; it is not needed for this study.
- **Class shares are checked by a sampler written in the test.** The existing sampler returns rank
  shares only. The test draws with the same stream and order and counts `sorting_oracle.class_of`.
- **MAVT is checked against the existing `sorting_oracle`**, scenario included, so no hand-written
  recomputation was needed here.
- **The sorting boundaries were chosen after the values were known**, so that one concept sits close
  to the *Shortlist* boundary. They are illustrative judgements, and the README and record say so.
- **Design intent, as found.** Both failing concepts stay in every ranking and class with their
  requirement beside them, but neither scores strongly: the *Legged walker* is last under every method
  and the *Small aerial drone* is fourth. "A strong score cannot hide a failure" is therefore not
  shown by this study (the flood study shows it), and I did not tune the inputs to force it. Class
  acceptability is spread: the *Wheeled rover* and the *Tethered crawler* each sit in two classes in
  roughly a third and two thirds of draws, and the *Small aerial drone* in two. The five methods
  agree on the leader under *Performance-led*, and MAVT and sorting lead differently from SMAA-2,
  PROMETHEE II and AHP under *Cost-led*.
- **AHP opens without a warning:** the largest consistency ratio is about 0.052.
- **The project is written at schema version 6.**
