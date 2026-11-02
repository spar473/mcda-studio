# Market research models and starter templates

**Accepted — implemented and locally verified (1 November 2026).** Domain content belongs in data
and templates. The engine remains a general engineering decision workspace. This development
follows External proposals; it does not add predictive outputs or an external data connection.

## Problem and scope

A single market-size entry hides populations, prices, adoption assumptions, source relationships
and disagreements between models. Use the calculation workspace for reviewed bottom-up formulas
(customers × adoption × price, segment sums), with A1's fundamental-factor uncertainty, and retain
separate top-down estimates. Add an engine-neutral comparison of two reviewed formula outputs to
Open Questions, plus a minimal New Project template gallery built from existing examples.
Venture screening is the most complete starter; supplier selection and infrastructure procurement
remain equally ordinary applications of the same engine.

## Models, data and schema/sidecars

Template content supplies unit definitions, factors, formulas and illustrative source/review
history. A bottom-up segment records eligible customer count, dimensionless adoption and annual
price per customer; its formula yields currency/year. Sum segments only with matching dimensions
and explicitly disjoint populations. A shared population or adoption factor has one ID and one
draw across formulas/alternatives. A segment total is an intermediate formula, not a new random
variable. Top-down inputs describe population/market definition, geography, date, unit and any
reviewed share/filter transformations. Unit conversion or inflation/currency adjustments are
explicit reviewed factors; there is no implicit equivalence.

Every fundamental factor carries existing `Source.classification`: `independent`, `self_reported`
or `unknown`, source reference/location/date, human/tool origin, and review. These are source
relationships, not numerical quality grades. Multiple claims remain separate; selecting an
accepted deterministic value is not acceptance of an uncertainty distribution. Outdated or
self-reported evidence remains disclosed. No range, disagreement or formula extremum automatically
becomes a uniform distribution. Quantile groups declare shared quantiles only; no invented
covariance or causal dependence.

Reuse `DerivedModel` version 1, `CalculationWorkspace` version 1 and `FactorUncertaintyModel`
version 1. Add three small engine-neutral sidecars, each version 1:

- `ModelComparison`: bound project fingerprint, two model/run digests and formula IDs, comparison
  label, comparable scope declarations, range kinds, explicit analyst review, and provenance.
  Two estimates of the same target do not both target the same criterion cell. Choose at most one
  for compilation; the other remains an intermediate formula or separate model output.
- `ModelChecks`: bound project fingerprint and model digest, with data-declared quantity checks
  (source/formula ID, exact unit, finite lower/upper bounds and inclusive flags). One generic
  validator checks deterministic values and declared supports before sampling, then every draw;
  unknown quantities/units, reversed bounds and any violated check refuse the run. These checks
  are never penalties or invented measurements. Templates use them for nonnegative counts/prices,
  adoption in [0,1], and valid share/denominator domains. No financial or template-name dispatch
  enters the validator; changing a check requires a new review/digest.
- `StarterTemplate`: stable ID/version/title/domain description, manifest of relative local
  artifact paths with hashes and kinds, source/example version, suggested tasks and reset policy.
  A generic instantiation receipt records template digest/version, new project fingerprint,
  generated sidecar digests and fields/reviews deliberately cleared.

Runs/comparisons retain their applicable reviewed `ModelChecks` snapshot and digest. An absent
check is not inferred from a unit or template name.

No field is added to existing project schemas and no old sidecar gains new live semantics. Unknown
versions are refused. Old project, calculation and uncertainty round trips and existing byte
outputs are pinned. These are new formats with no previous version to migrate; later changes need
explicit versioned migrations and fixtures. Never rewrite a reviewed historical artifact's
fingerprint to make it current. Template instantiation is an explicit creation of new inputs with
a lineage receipt, not verification/rebinding of an old compilation bundle.

## Comparison semantics and edge cases

Keep top-down and bottom-up outputs side by side, with formulas, inputs, source classifications,
dates, definitions and reviews. Open Questions calls this a **model disagreement to review**,
including when numeric ranges overlap; overlap is not evidence that the definitions or assumptions
agree. The disagreement is between two models, not the existence of a range. Never average the
estimates, their endpoints, sources or method results. No combined score or preferred-source rule.

A comparison declares its scope: population, geography, period, currency basis and unit. Unknown
or incompatible scope gives an “incomparable until reviewed” question, rather than a difference
number. Numeric disagreement is not statistical significance or proof that either estimate is
wrong. Duplicated segment populations require an explicit de-duplication/overlap model or are
refused; independence is never inferred from separate source documents.

Range kinds are explicit and never interchanged:

- A reviewed source interval is a stated bound, not a distribution or confidence interval.
- Exact discrete model support reports all reachable minima/maxima under declared dependence.
- A conservative interval enclosure is labelled an enclosure, not proven extrema.
- Sampled central 95% ranges use a specified empirical quantile algorithm and record seed,
  algorithm/environment, draw count and digests. They describe the declared model distribution;
  they are not source accuracy or the probability of a real-world outcome.

Show different kinds with their labels; do not compute overlap percentages across unlike kinds.
Initial comparison needs no inferred “material difference” threshold: retain both and ask which
assumptions explain the difference. A human can record a rationale and choose which compatible
reviewed output supplies a criterion, without erasing the other model. Corrected factors invalidate
old runs/comparison acknowledgements; original inputs/runs stay readable. Missing factors block
only affected outputs and any run needing them, never contribute zero to a segment sum. Rejected
or unreviewed models cannot supply compiled measurements. Bad draws abort, never thin the sample.

## Invented comparison example

For one explicitly declared population, period and currency basis, use the following illustrative
inputs; none is evidence about a real market. Distribution choices are separately reviewed
assumptions for the example, not inferred from source bounds.

| Bottom-up factor | Accepted base | Explicit marginal | Source classification |
| --- | --- | --- | --- |
| Eligible customers | 10,000 customers | Discrete 8,000 / 10,000 / 12,000 with probabilities .25 / .50 / .25 | independent |
| Adoption | .05 | Uniform .04 to .06 | unknown |
| Annual price | 1,200 currency/customer/year | Triangular 1,000 / 1,200 / 1,400 | self_reported |

`customers * adoption * annual_price` gives a deterministic 600,000 currency/year and a positive
product-support enclosure [320,000, 1,008,000] under the declared dependence (independent factors
here). A separate top-down formula `market_total * reachable_share` uses a reviewed total
100,000,000 currency/year and share .01, giving 1,000,000 currency/year. If the total carries only
reviewed bounds [80,000,000, 120,000,000], its transformed bounds are [800,000, 1,200,000]; no
probability distribution is inferred. Source classifications remain alongside each factor.

Show both deterministic outputs and both labelled ranges. Their overlap does not resolve the
model disagreement or create a combined estimate. Ask which population filters, adoption and
price assumptions explain the difference. A sampled central range, if requested, is a third
explicit range kind computed in Python with the recorded quantile algorithm, not substituted for
either support/source bound. Only one reviewed output may target a given criterion cell; retain
the other as an intermediate for this comparison.

## Minimal template gallery and instantiation

New Project offers **Blank**, **Supplier selection**, **Infrastructure procurement** and **Venture
screening**, with a short task description and “illustrative data” label. A manifest-driven loader
uses the same project/sidecar validation for every starter; no template-specific Python condition,
value function, method dispatch or hard-coded domain vocabulary enters domain/methods/services.
Template definitions and gallery copy live with `examples/` or `templates/` data.

The starter model inventory is data: supplier cost/quality and qualification, infrastructure cost
and procurement trade-offs, and the most complete screening starter (reviewed external proposals,
bottom-up segments, top-down comparison, shared factors, profiles/scenario, feasibility, sorting,
method cross-check instructions and decision-record tasks as those features become available).
New starter fixtures use invented/anonymised alternatives and invented source/reviewer records;
never copy real identities or profiles from a historical reference example into a new template.
Keep the historical regression example byte-identical. Build starters deterministically; Part B
may fill the complete screening template only
after its dependencies exist. Do not claim an unimplemented workflow in the gallery. Ship only existing starter parts before
the study and extend them during that step; never show placeholder or coming-soon items.

Default “create my project” generates a new project ID, preserves structural IDs and illustrative
input values, clears claimed human acceptances and dated decisions/runs, and marks all carried
inputs as illustrative proposals requiring review. Recompute bindings only for these explicitly
new draft sidecars and record the template lineage receipt. A separate **Open worked example**
retains the original complete illustrative provenance and fingerprint for demonstration. It never
pretends its reviewers accepted the user's new decision. Nothing fetches or sends data. The
normal save/import/undo workflows remain generic.

Ownership/dilution arithmetic belongs **optionally in the venture template as reviewed formulas**:
for a deliberately simple primary round, post-money = pre-money + new cash; new investor share =
new cash / post-money; existing holder's diluted share = prior share × pre-money / post-money.
Declare currency, share basis and denominator assumptions. Recommend including this as an
unattached illustrative calculation, off by default and outside the value tree unless the analyst
explicitly creates a criterion. Refuse nonpositive denominators and invalid share ranges; disclose
that option pools, convertibles, preferences, multiple rounds and contractual terms are excluded.
No ownership-specific engine code, valuation advice or inferred financing terms.

## API and UI

Stateless `model-comparisons inspect/preview/verify` and template `list/instantiate` API
operations, with corresponding CLI materialization for reproducibility. Calculation UI shows each
model's graph, deterministic and sampled outputs separately, factors and reviews. Open Questions
links both exact models/runs with a concrete review action. A reviewed target-selection diff uses
the ordinary compiler into a separate copy. Changed models/project/run digests invalidate that
selection and late responses. New Project's gallery previews what will be created and what reviews
will be reset; export/save remain explicit. Reference selection never opens a URL automatically.

## Verification plan

Independent exact formula/MAVT oracles cover customer × adoption × price, disjoint segment sums,
unit conversions, shared-factor draws and zero uncertainty. Tiny discrete top-down/bottom-up
examples retain both distributions and ranges without an average. Properties cover factor
identity, dimensional consistency, declaration/alternative order, point-mass reduction, unchanged
source classification and template instantiation parity across domains. Boundary tests include
zero customers/adoption/price, adoption 0 and 1, negative ratio factors, overlapping segments,
missing factors, bad denominators, out-of-domain draws and incomparable units/periods/scopes.

API/CLI/GUI must instantiate identical keyed inputs and evaluate identically. Browser cases start
each gallery item, show illustrative-review warnings, reopen lineage, retain a disagreement with
overlapping ranges and refuse stale run selections. Packaging/smoke checks inspect manifests and
all referenced files in wheels/sdists; no network is needed. Mutants duplicate shared-factor draws,
average models, convert ranges to uniform distributions, erase disagreements on overlap, import
old acceptances into a new project, ignore a template digest or insert a template-specific engine
branch. Run the full gate and previous-output byte identity; record real counts and remaining
human-usability checks.

## Excluded

Market-data retrieval, outcome forecasts, automatic evidence-quality weighting, automatic choice
of top-down or bottom-up, population de-duplication guesses, financial recommendation, a generic
plugin framework, cloud templates and ownership-specific engine code.

## Open owner decisions

1. **Template creation:** recommend a data manifest gallery with Blank plus the three starters;
   distinguish fresh unreviewed copies from intact worked examples, with lineage receipts.
2. **Range comparison:** recommend explicitly labelled range kinds and a persistent model
   disagreement question even on overlap; no automatic average or materiality cutoff.
3. **Compilation target:** recommend one explicitly selected reviewed model output per cell;
   retain the other estimate as an intermediate or separate model.
4. **Ownership arithmetic:** recommend optional, unattached simple-round formulas in the venture
   template, off by default, with the exclusions and denominator/share checks above.
5. **Review reset:** recommend clearing human acceptances and decision/run snapshots in fresh
   projects, preserving them only in the explicitly opened worked example.

## Owner decisions

Approved by the owner on 1 November 2026. All five recommendations accepted, as recorded below.

1. Manifest-driven gallery: Blank, Supplier selection, Infrastructure procurement, Venture
   screening; fresh unreviewed copies distinguished from intact worked examples, with lineage
   receipts.
2. Labelled range kinds; a persistent model-disagreement question even when ranges overlap; no
   average and no materiality cut-off.
3. One explicitly selected reviewed model output per criterion cell; the other kept as an
   intermediate or separate model.
4. Optional, unattached simple-round ownership formulas in the venture template, off by default,
   with denominator and share checks and the stated exclusions.
5. Fresh projects clear human acceptances and decision/run snapshots; only the explicitly opened
   worked example keeps them.

**Amendment B — gallery honesty.** Describe only workflows present in the shipped build. If the
starter precedes the flagship study, ship its existing parts and extend it during the study step.
Never show a placeholder or coming-soon gallery item.

## Arithmetic clarification (1 November 2026)

Apply the [arithmetic contract](derived-measurements.md#arithmetic-contract): engine-to-engine
claims are bit-exact; exact-rational oracles independently derive forward rounding-error bounds.
Quantity checks use the computed binary64 value with no hidden tolerance: `0.1 + 0.2` exceeds an
inclusive upper bound of `0.3`. Starter checks prefer fundamental factors and never put a derived
check at a boundary reached exactly by the example. Exports retain full precision; formatting
on screen does not change a stored value. A stale selection returns the existing
**412 `STALE_REVISION`** response; no new 409 mapping is introduced.

Implementation and actual checks: [Market research models verification](../development/market-research-models-verification.md).
