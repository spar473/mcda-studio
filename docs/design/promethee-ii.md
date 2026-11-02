# PROMETHEE II: net outranking flows, with an explanation against MAVT

**Status:** implemented and verified, 31 October 2026, with all seven recommended
[decisions](#decisions) accepted by the owner. See the
[check record](../development/promethee-ii-verification.md).

PROMETHEE II ranks alternatives by their net outranking flow. Each flow is built from pairwise
preference degrees on the raw measurements, so a large advantage on one criterion counts only up
to full preference and cannot simply offset a poor result elsewhere. It is the next method in the
owner's order of 28 October 2026 and comes through the [method seam](method-seam.md), like
[value-based sorting](value-based-sorting.md) and [SMAA-2](smaa-2.md). The earlier proposal is
plan §7 (historical record, not included), and the roadmap section "PROMETHEE II" sets the
scope. Where they differ, this note wins.

The oracle came first: both published examples below were sourced and reproduced in exact
arithmetic before this note was written.

## Published examples (the oracle)

| Source | Licence | What it supplies | Reproduced |
| --- | --- | --- | --- |
| V. Podvezko and A. Podviezko, "Dependence of multi-criteria evaluation result on choice of preference functions and their parameters", *Technological and Economic Development of Economy* 16(1), 143–158, 2010, [doi:10.3846/tede.2010.09](https://doi.org/10.3846/tede.2010.09) | CC BY 4.0 | Four countries on five criteria (four maximised, one minimised), with the 2003 statistics and expert weights the paper cites from Ginevičius et al. (2006). Its Table 3 gives Φ⁺, Φ⁻, Φ and both rankings under six variants. Variant 2 uses the usual function throughout, 3 the U-shape, 4 the V-shape and 6 the linear function. Variants 1 and 5 use the level function and are out of scope (decision 4) | All 48 printed flows of variants 2, 3, 4 and 6, to their printed precision of two or three decimals, and all 16 PROMETHEE II ranks |
| A. Flachs and Y. De Smet, "From outranking flow scores to linear programs: group decision making in PROMETHEE II", [arXiv:2610.34481v1](https://arxiv.org/abs/2610.34481), 2026, Appendix A | CC BY 4.0 | Four alternatives on two maximised criteria with weights 0.2 and 0.8: the usual function, and the V-shape with indifference (the linear function) with q = 1 and p = 3 | The four printed net flows, exactly: 1/5, −1/15, −3/5 and 7/15 (printed 0.2, −0.067, −0.6 and 0.467) |

**Definitions** follow J.-P. Brans and B. Mareschal, "PROMETHEE methods", chapter 5 of
J. Figueira, S. Greco and M. Ehrgott (eds.), *Multiple Criteria Decision Analysis: State of the Art
Surveys*, Springer, 2005, pp. 163–195: the preference-function types, flows normalised by n − 1, and
single-criterion net flows with Φ = Σ w̄ⱼ φⱼ.

**Two conventions differ.** Podvezko and Podviezko sum the preference indices without dividing by
n − 1, so their flows are three times the normalised flows used here (n = 4). The oracle compares
3·Φ with their printed values. Their PROMETHEE I rows use a dash notation the paper does not
define, so those rows are not used. Flachs and De Smet normalise as here.

**Use of the sources:** the inputs and printed results enter the tests as data, with the
citation, under CC BY 4.0. No text, table layout or figure is copied.

## What exists today

- **The method seam.** The `flows` capability is already in the vocabulary, reserved for
  PROMETHEE II; the seam's table gives it `flows` and nothing else. Methods own their validation,
  parameters, result type, version-2 record and CSV tables, and the frontend picks panels by
  method.
- **Measurements:** one per cell, on a numeric scale (interval or ratio) or a labelled one
  (categorical or ordinal, whose labels run low to high). A missing measurement is a core
  validation error (`MISSING_MEASUREMENT`) for every method.
- **Direction and weights belong to MAVT.** Direction lives only inside MAVT value functions
  (linear direction, piecewise shapes, qualitative mappings). Swing profiles give range-dependent
  MAVT weights; scenarios override profiles and value functions. All of these are MAVT inputs.
- **Schema version 3** (`sorting` 2, `smaa` 3), each section written only when used.
- **The previews** refuse a method without `value_functions` or `swing_weights`. The frontend
  sends the viewed configuration with them (`usePreviews`), so the MAVT editors' previews would be
  refused while PROMETHEE II is viewed (§8 fixes this).
- **The shared `ranking`** in every result is a list of `{alternative_id, name, value, rank}`
  (decision 7).

## Goals and non-goals

**Goals:**

- A PROMETHEE II complete ranking by net flow, with the PROMETHEE I partial order (preference,
  indifference, incomparability) as a secondary view.
- The usual, U-shape, V-shape and linear preference functions, with thresholds in each criterion's
  units.
- PROMETHEE's own weights, directions and codings in its own section, never taken from swing
  profiles or value functions.
- An explanation view that names the criteria and thresholds behind each difference between the
  PROMETHEE II and MAVT rankings.
- Flows labelled as flows on a [−1, 1] axis: never shown as preference values, never on the 0–1
  value axis, never combined with an MAVT number.
- **MAVT, sorting and SMAA-2 byte-identical** for unchanged inputs, proved with
  `scripts/byte_identity.py`.

**Non-goals (excluded):**

- PROMETHEE III–VI, GAIA and the level and Gaussian functions (decision 4).
- Weight sensitivity or stability intervals for PROMETHEE, PROMETHEE weight profiles or
  scenarios, and uncertainty in PROMETHEE inputs.
- Consensus or averaged scores across methods, and treating agreement on shared inputs as
  independent validation.
- Reading swing weights or value functions as PROMETHEE inputs.

## Design

### 1. Inputs, in PROMETHEE's own section

For each leaf criterion the section states:

- **direction:** `maximise` or `minimise`;
- **weight:** any non-negative number, normalised by the sum of all weights (decision 2);
- **function:** `usual`, `u_shape` (q), `v_shape` (p) or `linear` (q, p), with thresholds in the
  criterion's units;
- **coding:** a number for every label, required on categorical and ordinal leaves and refused on
  numeric ones (decision 3). Differences and thresholds on such a leaf are in coded units.

```json
"promethee": {
  "criteria": [
    {"criterion_id": "cost", "direction": "minimise", "weight": 3,
     "function": {"kind": "linear", "q": 10, "p": 100}},
    {"criterion_id": "maturity", "direction": "maximise", "weight": 1,
     "function": {"kind": "usual"}, "coding": {"Low": 1, "Medium": 2, "High": 3}}
  ]
}
```

The section states direction and coding for every leaf; neither is read from MAVT (decision 3).
A value function is MAVT's judgement of value and can be non-monotone, and its qualitative
mapping fixes a spacing that is a MAVT judgement. The editor says why swing weights are not
reused: they are trade-offs that depend on the measurement ranges, whereas PROMETHEE weights are
importances applied to preference degrees.

### 2. The calculation

Take n ≥ 2 alternatives. Let xₐⱼ be a's measurement on leaf j (its code on a labelled leaf), sⱼ be
+1 to maximise and −1 to minimise, and w̄ⱼ = wⱼ / Σ w.

- **Difference:** dⱼ(a, b) = sⱼ (xₐⱼ − x_bⱼ).
- **Preference degree:** Pⱼ(a, b) = Fⱼ(dⱼ(a, b)). F(d) is 0 for d ≤ 0, and for d > 0:

  | Function | F(d) |
  | --- | --- |
  | usual | 1 |
  | U-shape (q) | 0 if d ≤ q, else 1 |
  | V-shape (p) | d / p if d ≤ p, else 1 |
  | linear (q, p) | 0 if d ≤ q; (d − q) / (p − q) if q < d ≤ p; 1 if d > p |

- **Preference index:** π(a, b) = Σⱼ w̄ⱼ Pⱼ(a, b).
- **Flows:**
  - positive: Φ⁺(a) = (1 / (n − 1)) Σ_{b≠a} π(a, b);
  - negative: Φ⁻(a) = (1 / (n − 1)) Σ_{b≠a} π(b, a);
  - net: Φ(a) = Φ⁺(a) − Φ⁻(a).
- **Single-criterion net flow:** φⱼ(a) = (1 / (n − 1)) Σ_{b≠a} [Pⱼ(a, b) − Pⱼ(b, a)], so that
  Φ(a) = Σⱼ w̄ⱼ φⱼ(a).
- **PROMETHEE II:** competition ranks on Φ, with MAVT's `1e-12` tie tolerance.
- **PROMETHEE I:** a is preferred to b when Φ⁺(a) ≥ Φ⁺(b) and Φ⁻(a) ≤ Φ⁻(b) with at least one
  strict; a and b are indifferent when both are equal; otherwise they are incomparable. "Equal"
  means within `1e-12`.

Every sum uses `math.fsum`.

**Threshold comparisons use a tolerance.** A difference is compared with 0, q and p as equal when
it lies within `1e-12 × max(1, |xₐⱼ|, |x_bⱼ|)` of it. In binary floating point, 0.79 − 0.73 is
0.06000000000000005, so the U-shape, which jumps at q, would turn a difference of exactly q = 0.06
into full preference without the tolerance. The linear and V-shape functions are continuous, so
the tolerance only snaps them to 0 or 1 at their ends.

**Invariants, asserted on every result:**

- 0 ≤ Φ⁺, Φ⁻ ≤ 1 and −1 ≤ Φ ≤ 1;
- Σ Φ = 0 within n·`1e-12`;
- Φ = Φ⁺ − Φ⁻ and Φ = Σ w̄ⱼ φⱼ.

### 3. Outputs

`PrometheeResult` (`method: "promethee2"`) contains:

- **Flows:** per alternative, Φ⁺, Φ⁻, Φ and the PROMETHEE II rank.
- **Single-criterion net flows** φⱼ(a), and the **preference matrix** π(a, b).
- **The partial order:** every unordered pair as preferred (with which way), indifferent or
  incomparable.
- **The inputs used:** directions, stated and normalised weights, functions and codings.
- **The explanation** against MAVT (§4).
- **The label** "net outranking flows: these compare the alternatives with one another and are not
  preference values", on every table, chart, export and record.

### 4. The explanation against MAVT

- **MAVT side** (decision 6): the MAVT evaluation of the same project under the configuration's
  profile and scenario, computed by the MAVT engine unchanged. If MAVT's model is not valid, the
  explanation is omitted and lists the MAVT issue codes as the reason; PROMETHEE II still runs.
- **Rank comparison:** each alternative's MAVT rank beside its PROMETHEE II rank. Ranks only:
  values and flows never share an axis or a column.
- **Pairs ordered differently** (decision 5): every pair whose order differs between the two
  methods, a tie counting as an order. Each pair is oriented so that a is the alternative MAVT
  places higher (or, when MAVT ties them, the one PROMETHEE II places lower). Each pair gives:
  - the value gap V(a) − V(b) and the flow gap Φ(a) − Φ(b), each in its own method's units;
  - the flow gap split exactly into a **head-to-head** part, (2 / (n − 1)) [π(a, b) − π(b, a)],
    and a **via-others** part, the rest, which comes from how a and b each fare against the other
    alternatives. This shows when a third alternative changes the order of two others, a known
    property of PROMETHEE II;
  - per criterion:
    - the difference dⱼ(a, b) in the criterion's units;
    - its **zone**, naming the thresholds: no preference (|d| ≤ q), partial (between q and p), or
      full preference (|d| ≥ p, or any difference under the usual function), where any further
      difference counts the same;
    - the PROMETHEE contribution w̄ⱼ [φⱼ(a) − φⱼ(b)], with its head-to-head part;
    - the MAVT contribution, MAVT's own weighted partial-value difference;
  - **named reasons**, generated in Python, at most three:
    - the criteria that favour b most in PROMETHEE;
    - the criteria where a's MAVT advantage is reduced by a threshold, because it lies inside q
      or is capped at p.

    Each reason names the difference and the threshold, for example "Cost: Beta is 132 lower,
    beyond p = 100, so PROMETHEE counts full preference and no more".
- **Bounds:** every pair is listed with its gaps. Criterion detail and reasons are given for up
  to 50 pairs, taken in order of the larger rank change of the two alternatives, then MAVT rank.
  A diagnostic, `EXPLANATION_LIMITED`, says when pairs were left without detail.

No number in the result adds, averages or subtracts a value and a flow. The only cross-method
operation is comparing orders.

### 5. Storage and schema

Under decision 1, an optional `promethee` section joins the project, with
`SECTION_VERSIONS["promethee"] = 4`. A project that states PROMETHEE inputs is written as schema
version 4; every other project keeps the version it has today. Migration 3 → 4 is the identity and
refuses a version-3 file holding `promethee`.

**Edits:** `set_promethee_model` and `clear_promethee_model` replace the whole section, as for
classes and uncertainty. Removing a criterion removes its entry. A scale whose labels change, or a
leaf that gains children, is reported by validation and never silently repaired.

### 6. Validation

PROMETHEE II runs the method-independent checks (structure, alternatives, measurements against
scales, missing measurements), then its own rules. MAVT's checks do not apply to its inputs.

| Code | Severity | When |
| --- | --- | --- |
| `PROMETHEE_NOT_STATED` | error | the method is PROMETHEE II and the project has no section |
| `PROMETHEE_TOO_FEW_ALTERNATIVES` | error | fewer than two alternatives |
| `PROMETHEE_CRITERION_MISSING` | error | a leaf has no entry |
| `UNKNOWN_PROMETHEE_CRITERION` | error | an entry names an unknown criterion or a non-leaf |
| `DUPLICATE_PROMETHEE_CRITERION` | error | two entries for one leaf |
| `INVALID_PREFERENCE_FUNCTION` | error | q < 0, p ≤ 0, or q ≥ p for the linear function |
| `INVALID_PROMETHEE_WEIGHT` | error | a negative weight |
| `ZERO_PROMETHEE_WEIGHTS` | error | every weight is zero |
| `CODING_MISSING` | error | a labelled leaf without a code for each of its labels |
| `UNKNOWN_CODED_LABEL` | error | a code for a label the scale does not have |
| `UNEXPECTED_CODING` | error | a coding on a numeric leaf |
| `PROMETHEE_CRITERION_INERT` | warning | weight 0, or q at or above the largest difference observed on that leaf, so it never contributes |
| `ORDINAL_CODING_UNORDERED` | warning | an ordinal leaf's codes do not follow its label order |

PROMETHEE II has no parameters; an unknown parameter is reported as `UNKNOWN_PARAMETER` and ignored,
as for every method.

### 7. Method, records, API and CLI

- **Method** `promethee2`, label "PROMETHEE II (outranking flows)", capability `flows`. Every other
  capability-checked route (sensitivity, probes, scenario comparison and the previews) refuses it
  with 422 `METHOD_NOT_SUPPORTED`, as the seam requires.
- **Record:** `PrometheeAnalysisRecord`, version 2, calculation path `promethee2.v1`. CSV tables:
  `flows`, `criterion_flows`, `partial_order` and `explanation`.
- **API:** `/evaluate` returns `PrometheeResult` in the union; edit operations `set_promethee_model`
  and `clear_promethee_model`; `/api/meta` lists the method and its tables.
- **CLI:**
  - `mcda promethee criterion FILE CRITERION --maximise|--minimise --weight W [--usual |
    --u-shape Q | --v-shape P | --linear Q P] [--code LABEL=N ...]`;
  - `mcda promethee remove FILE CRITERION` and `mcda promethee clear FILE`;
  - `mcda evaluate --method promethee2` prints the flows table under the label, the incomparable
    pairs, the rank comparison and the reasons.
- **Bounds:** the work is n² × leaves preference degrees (10⁵ on the 50 × 40 performance fixture).
  The existing results limits apply, and the fixture's timing is recorded.

### 8. Frontend

- **An Outranking tab,** shown when the viewed method is PROMETHEE II or the project has the
  section. Per leaf, it holds:
  - the direction, the weight, and the function with its thresholds in the leaf's unit;
  - codes for labelled leaves, with a "number in label order" helper for ordinal leaves that
    writes explicit numbers;
  - a schematic of the function's shape, drawn from q and p alone, with no alternative or engine
    number on it;
  - a note on why swing weights are not reused.
- **A Flows panel:** the table of Φ⁺, Φ⁻, Φ and rank, and a bar chart of Φ diverging from zero on
  a fixed [−1, 1] axis titled "net flow", all under the label. The 0–1 value axis is never used.
  A **PROMETHEE I view** lists, for each alternative, those it is preferred to, indifferent to and
  incomparable with, with incomparable pairs shown first.
- **An Explanation panel:**
  - the rank comparison;
  - each pair ordered differently, with its criterion rows, zones, thresholds and reasons;
  - the reason when MAVT's side is unavailable.
- **The MAVT editors keep working while PROMETHEE II is viewed.** Their previews are requested
  for `mavt` with the same profile and scenario, because they edit the MAVT model. The preview
  routes still refuse PROMETHEE II itself.
- Python computes every number; the browser only draws them.

### 9. The cross-method rules

- PROMETHEE II never reads swing profiles, swing weights or value functions as its inputs.
- MAVT appears only on the explanation's MAVT side, in its own units, beside PROMETHEE's.
- No field combines the two methods.
- Flows never appear on the value axis or under the name "score".
- The later comparison view reads the two results separately.

## Verification plan

- **Published examples:**
  - Podvezko and Podviezko, variants 2, 3, 4 and 6: 3·Φ⁺, 3·Φ⁻ and 3·Φ within half a unit of
    the last printed digit, and the PROMETHEE II ranks;
  - Flachs and De Smet: the four net flows to the printed precision, and exactly as fractions in
    the oracle.
- **Oracle:** `tests/regression/promethee_oracle.py`, in plain Python with fractions built from
  the inputs' decimal strings:
  - It has its own preference functions, flows, partial order and pair decomposition, and is
    checked in a clean interpreter to load no `mcda_studio` module.
  - It is first checked against both published examples.
  - It then agrees with the engine to `1e-12` on generated cases: every function, both directions,
    codings, ties, and thresholds hit exactly.
- **Invariants** on every test model:
  - the flow bounds;
  - zero sum;
  - Φ = Σ w̄ⱼ φⱼ and Φ = Φ⁺ − Φ⁻;
  - head-to-head plus via-others equals the flow gap.
- **Hand-derived cases:**
  - U-shape at d = q gives 0;
  - linear at q and at p;
  - minimise;
  - codings;
  - n = 2, where via-others is zero;
  - all weight on one criterion, where Φ = φⱼ;
  - a PROMETHEE I incomparability;
  - an added alternative that reverses two others, shown through the via-others part.
- **Explanation:**
  - On a hand-built pair where a capped advantage flips the order, the right criteria, zones and
    thresholds are named.
  - It is omitted, with the reason, when MAVT is invalid.
  - The 50-pair limit and its diagnostic.
- **Validation:** every code.
- **Schema:** version 4 only when used, no `null` written, the migration refusal, and clearing that
  restores the bytes.
- **Byte identity:** MAVT, sorting and SMAA-2 outputs (SMAA-2 at its default seed) on every
  example, against the previous commit. `scripts/byte_identity.py` gains the SMAA-2 outputs.
- **Frontend and browser:**
  - the Outranking editor;
  - the Flows panel's label and axis, and the PROMETHEE I view;
  - the Explanation panel;
  - the MAVT editors' previews while PROMETHEE II is viewed;
  - a GUI case from blank: build a model, state the PROMETHEE inputs, run, read the flows, open the
    explanation and export.
- **Mutants** (`--promethee-only`):
  - q and p swapped in the linear function;
  - flows not divided by n − 1;
  - minimise ignored;
  - the U-shape counting d = q as preference;
  - weights not normalised;
  - net flow taken as Φ⁺ alone;
  - incomparable pairs reported as indifferent;
  - the via-others part dropped, so the gap no longer reconciles;
  - a capped difference reported as partial;
  - an absent section written as `null`;
  - the section written as version 3;
  - frontend: flows drawn on the 0–1 value axis;
  - frontend: the label dropped;
  - frontend: a pair ordered differently missing from the explanation.

## Acceptance

- Both published examples are reproduced: 48 flows and 16 ranks from Podvezko and Podviezko, and
  four net flows from Flachs and De Smet. The oracle agrees with the engine to `1e-12`.
- Flows lie in [−1, 1] and net flows sum to zero.
- Flows are never shown as preference values, never averaged with MAVT scores and never given
  swing weights.
- The explanation names the criteria and thresholds behind each difference in rank.
- MAVT, sorting and SMAA-2 outputs are byte-identical, and projects are written at the lowest
  sufficient schema version.
- A GUI case from blank to export passes.
- The full gate is green, and every new mutant is killed.

## Decisions

1. **Where PROMETHEE inputs live.** *Recommended:* an optional `promethee` section in the project
   file (schema version 4, written only when used), as for classes and uncertainty: fingerprinted,
   versioned, undoable and reproduced from one file. *Alternatives:*
   - method parameters, which are lost when another method is viewed and would carry
     per-criterion data in the configuration;
   - a sidecar file, which makes every record depend on two files staying in step.
2. **Weight structure.** *Recommended:* flat, one weight per leaf, any non-negative numbers
   normalised by their sum. This is the published method, and nothing about it resembles a swing
   profile. *Alternative:* hierarchical local weights per sibling group, multiplied down the tree.
   That is easier on deep trees, but it is not the classical method and invites copying the swing
   weights.
3. **Directions and codings.** *Recommended:* stated in the section for every leaf. The ordinal
   helper writes explicit numbers that the analyst can change. *Alternative:* read the direction
   from MAVT's linear value functions and the codes from its qualitative mappings. That means less
   typing, but it couples the methods and imports MAVT's value judgements into PROMETHEE, which
   the seam forbids. It also fails on piecewise and non-monotone functions.
4. **Preference functions.** *Recommended:* usual, U-shape, V-shape and linear now, as the roadmap
   scopes, with level and Gaussian later. The published oracle covers exactly these four.
   *Alternative:* all six now. Level has published variants in the same paper (1 and 5), but
   Gaussian has none in the sources found, and both need their own editor and explanation zones.
5. **Explanation basis.** *Recommended:* per pair ordered differently: per-criterion zones and
   thresholds, the head-to-head and via-others split, and generated reasons, with detail for up to
   50 pairs. *Alternatives:*
   - per-alternative single-criterion flow profiles only, which are smaller but name no
     threshold and cannot explain a particular swap;
   - an on-demand endpoint for one pair, which keeps results small but leaves the explanation out
     of exported records.
6. **The MAVT side of the explanation.** *Recommended:* the configured profile and scenario, with
   the explanation omitted (and the reason given) when MAVT's model is invalid. *Alternative:*
   require a valid MAVT model before PROMETHEE II runs at all. That is simpler to present, but it
   blocks PROMETHEE for a model without value functions and makes PROMETHEE depend on MAVT inputs.
7. **The shared `ranking` field.** *Recommended:* it holds the PROMETHEE II order. Its `value` is
   the net flow, and the API contract says so. No PROMETHEE view, CSV table or CLI line shows it
   under the word "value"; the panels read `flows`. This keeps every existing schema and byte
   unchanged. *Alternative:* make `value` optional and add a `net_flow` field to the shared rank
   type. That is cleaner to name, but it changes the published schema of every method's result
   and every frontend reader of `value`.
