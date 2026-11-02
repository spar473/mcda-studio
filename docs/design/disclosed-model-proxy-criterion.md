# Disclosed model proxy criterion

**Accepted — implemented and locally verified.** External model outputs may be
reviewed inputs. They are never the engine's prediction, and preference values are never
presented as probabilities of an outcome. This mechanism is off by default.

## Problem, scope and relationship to proposals

An external model's numeric score can summarize signals already represented in a value tree and
can carry selection or survivorship bias. Quietly adding it gives apparent independent evidence
and can count the same concept twice. Permit one explicitly labelled derived proxy criterion in
an optional analysis copy, with a model card, declared features and a mandatory comparison with a
copy that omits it. External proposals provide intake/review, not automatic proxy activation.
This is a generic mechanism; domain examples supply their own content.

## Data model, sidecars and schema

Propose `ProxyCriterionPlan` version 1, bound to the source project fingerprint and a reviewed
numeric proposal digest. It records the target criterion definition (label beginning “Disclosed
model proxy”), raw score/unit, fixed value function, explicit swing judgements per requested
profile, model-card reference/digest, declared input features, review history, overlap findings
and acknowledgement, and activation choice. The score becomes a reviewed fundamental factor;
an identity formula targets the proxy criterion in the calculation workspace. “Derived” describes
the provenance and transformation; it does not mean the engine runs the external model.

A model card requires purpose, training-data period and population, observation cutoff, declared
outcome/label definition if applicable, base rate and population denominator, known biases
including survivorship/selection, calibration evidence and its evaluation population/period,
licence and use restrictions, model version, and source references. A field may explicitly state
“unknown” or “no evidence supplied”, with a reason and human review, rather than inventing data.
Missing fields block activation; explicit unknowns remain visible unresolved limitations and
require an acknowledgement. Licence unknown/incompatible blocks activation until resolved.
A missing calibration study never turns an arbitrary score into a probability.

Each declared feature has a stable feature ID, description, source lineage, observation date,
and optional links to existing criterion and source-factor IDs. An overlap record says “same
concept”, “shared evidence”, “possible overlap” or “reviewed distinct”, with rationale. Correlation
alone does not establish conceptual double counting. Exact shared IDs trigger a warning; text-only
features require an explicit analyst review rather than a purported semantic detector.

The source project schemas and old result types are unchanged. A version-1 proxy-comparison bundle
retains the source project, plan, model card, reviewed score, both materialized projects, their
calculation bundles/configurations/results, warnings and digests. No proxy field is silently added
to old projects. New sidecars reject unknown versions; existing project and calculation models
round-trip unchanged. If embedded activation flags or model-card fields are later requested,
stop for an explicit project migration and old/new compatibility fixtures.

## Exact with/without semantics

The base project excludes the optional proxy. “Enable” materializes a separate copy by inserting
one new generic leaf under the explicitly chosen existing parent and adding analyst-stated swing
ratings; missing ratings block the run. The baseline copy is the original tree, with its original
ratings and resolved profile/scenario, so the without-proxy run reproduces it byte for byte.
Existing siblings' ratings are retained; ordinary normalization changes their shares in the
with-proxy copy, and that consequence is disclosed. We never set a weight silently, reassign a
model's confidence as a weight, or pretend zero weight removes a criterion from all methods.

Initial supported comparisons are MAVT, value-based sorting and factor-based SMAA-2 with fixed
weights. Run the same non-proxy factor draws/seed in both copies by stable factor identity and
record the coupling, so differences cannot be attributed to unrelated draws. The proxy is a fixed
reviewed numeric input initially; uncertain proxy scores and mixed weight uncertainty need a
separate oracle gate. PROMETHEE II/AHP are visibly unavailable for this paired comparison until
method-specific criteria weights/pairwise judgements and removal semantics are specified. No
method inherits another method's weights. Existing ordinary comparison remains available.

Every analysis using the proxy must contain both completed halves, or explicitly mark the pair
unavailable with the failed half's reasons. Never publish only the more favourable half. The
method comparison view shows separate “without disclosed proxy” and “with disclosed proxy”
columns, source/model-card disclosure, weight changes, rank/class differences and feasibility.
No consensus score, averaged rank or probability of outcome is produced.

## API and UI

Proposed `proxy inspect`, `preview-pair`, `run-pair`, `verify` and matching stateless endpoints.
The calculation workspace displays the score's identity formula, provenance and reviews. A
separate off-by-default toggle creates a preview, not a project edit. Require acknowledgement of
the card, feature overlap and weight differences before running. Late responses, changed scores,
features, cards, reviews, profiles or scenarios invalidate the paired candidate. Export both
copies and the comparison bundle; the base project is untouched. Decision snapshots may cite the
complete pair and the reason for enabling the proxy. Pending card/overlap/licence items enter
Open Questions. Source references are local or displayed text, never fetched.

## Edge cases and refusals

- Refuse unreviewed/rejected scores, stale project/proposal/card digests, absent feature declarations,
  nonfinite scores, out-of-domain scores under the chosen value function, licence restrictions,
  unknown targets, cyclic formula references and missing proxy swing ratings.
- An explicitly unknown card fact is a limitation, not a default value or evidence of safety.
  Activation requires its acknowledgement; no acknowledgement fabricates calibration.
- Feature overlap is displayed beside affected criteria and factors. Activation blocks until the
  analyst records whether to remove an overlapping criterion, use only the baseline, or retain
  both with a stated rationale. Removal is another explicit materialized model, never hidden
  inside weights. Preserve that additional model and its identity in the bundle.
- Duplicate proxy IDs or several active proxies are refused initially. A criterion's display name
  cannot conceal its proxy role. A model update or a new observation date requires a new reviewed
  proposal and invalidates the old plan.
- Non-proxy missing measurements remain missing in both copies. Feasibility is evaluated beside
  scores, never satisfied by the proxy. Failure in one half is not replaced by results from the
  other half. Scenario overrides and profile precedence use ordinary engine rules in each copy.
- No probability-oriented label is shown for the engine's result, even if the imported score was
  reported on [0,1]. The raw model score and its supplier's declared meaning remain disclosed.

## Verification plan

Independent rational MAVT/sorting oracles reconstruct both trees and their normalized weights;
near-tie and boundary cases verify existing tolerances. Factor-draw oracle cases prove common
non-proxy realizations in both copies and exact fixed-score reduction. Properties check that
turning the proxy off reproduces the original project/results, confidence metadata has no effect,
source edits invalidate plans, and both halves are always retained. Test incomplete cards,
explicit unknowns, overlap resolutions, licence refusal, absent profiles/scenarios, zero/missing
ratings, stale responses and full history/export reopening. Mutants silently activate the proxy,
reuse confidence as weight, hide a failed half, drop the baseline, ignore an overlap or change a
shared draw. Run the full gate and byte-identity proof, then record what was actually checked.

## Arithmetic and implementation boundary

The [unchanged arithmetic contract](derived-measurements.md#arithmetic-contract) applies.
Engine-to-engine baseline, replay, coupling and CLI/API/GUI checks are bit-exact. Independent
MAVT/sorting oracles reconstruct decimal rationals and propagate rounding bounds; exact dyadic
cases retain exact equality. Existing method tie/boundary tolerances are unchanged. Exported
numbers keep full precision; screen formatting does not alter the stored paired results.

Plans are disabled replayable sidecars, reviewed numeric proposals bind to an exported separate
score-review draft, and ordinary calculation bundles retain the score identity formulas. Licence
compatibility is an explicit review; unknown licence or use restrictions block activation. An
explicit removal cannot erase a feasibility requirement. `proxy start/revise/inspect/preview-pair/
run-pair/verify` and corresponding local stateless endpoints share the same implementation. Stale
review/preview requests use the existing 412 `STALE_REVISION`. See the
[verification record](../development/disclosed-model-proxy-verification.md) for actual checks and
remaining authoring/usability limits.

## Excluded

Training, inference, provider access, predictive calibration inside the engine, automated feature
selection, automatic debiasing, multiple proxies, uncertainty on the proxy itself, proxy-specific
PROMETHEE/AHP comparisons and an engine outcome probability. No investment recommendations are
provided by this feature.

## Open owner decisions

1. **Activation/storage:** recommend an off-by-default, sidecar-defined optional leaf materialized
   only into a separate analysis copy; the original project is the without-proxy baseline.
2. **Incomplete model evidence:** recommend required fields with explicit reviewed unknowns for
   unavailable facts, blocking missing fields and unresolved licence compatibility.
3. **Overlap policy:** recommend mandatory explicit resolution/acknowledgement; no automatic
   criterion removal or guessed overlap score.
4. **Initial methods and uncertainty:** recommend MAVT, sorting and fixed-weight factor-based
   SMAA-2 pairs, one fixed proxy score; defer other combinations until independent checks exist.
5. **Proxy weight:** recommend explicit analyst swing ratings for every compared profile, with
   before/after normalized shares displayed; no prefilled nonzero weight.

## Owner decisions

Approved by the owner on 1 November 2026. All five recommendations accepted, as recorded below.

1. Sidecar-defined optional leaf, materialised only in a separate analysis copy; the original
   project is the without-proxy baseline.
2. Required model-card fields; explicitly reviewed unknown allowed and shown as a limitation;
   missing fields or unresolved licence block activation.
3. Overlap must be explicitly resolved or acknowledged; no automatic removal or guessed overlap.
4. Initial pairs: MAVT, value-based sorting and fixed-weight factor-based SMAA-2; one fixed proxy
   score; PROMETHEE II and AHP visibly unavailable for the pair.
5. Analyst swing ratings required for every compared profile; show before/after weight shares;
   no prefilled nonzero weight.
