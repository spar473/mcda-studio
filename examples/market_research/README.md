# Invented formula models and starter materials

These numbers, sources and reviews are invented illustrations, not evidence about a real market
or investment advice. `build.py` creates the four data-only starter manifests under
`examples/starter_templates/`; it never edits the historical reference example.

The initial Venture screening starter contains Option A/B, classifier proposals, and explicit
bottom-up and top-down formulas. Its card lists only these existing workflows. The later
five-company study will extend it in its own development.

The bottom-up example has 10,000 eligible customers × .05 adoption × 1,200 money/customer/year:
600,000 money/year. Separately reviewed marginals are a discrete 8,000/10,000/12,000 customer
count with probabilities .25/.50/.25, uniform adoption .04–.06, and triangular price
1,000/1,200/1,400. Their conservative support enclosure is 320,000–1,008,000. Shared factor IDs
mean the same draw across formulas; a reused output is never sampled again.

The other model is 100,000,000 money/year × .01, giving 1,000,000 money/year. The declared
source bounds 80,000,000–120,000,000 give 800,000–1,200,000 after the share transformation.
These bounds are not a probability distribution. The ranges overlap; the disagreement question
remains. Both have the same explicitly invented population, geography, period, unit and currency
basis. Nothing averages them or chooses a preferred model.

Optional unattached arithmetic is off by default. Its invented simple primary round uses
4,000,000 pre-money, 1,000,000 new cash and a .6 prior share. Post-money is their sum, new share
is new cash/post-money, and diluted share is prior share × pre-money/post-money. Reviewed checks
require nonnegative inputs, a positive denominator and shares in [0,1]. Option pools,
convertibles, preferences, multiple rounds and contractual terms are excluded. No formula becomes
a criterion merely because its file is selected.

Fresh projects retain illustrative input values and structural IDs, clear human acceptances and
historical runs, and export a lineage receipt. Worked examples retain their exact invented reviews
and original fingerprint. Download the materials archive and open each sidecar explicitly in its
workspace. No data is fetched or sent.

Run `python examples/market_research/build.py` to regenerate local fixtures. A run record includes
its actual environment; content hashes therefore include that recorded environment. Within the
same environment, the fixture builder is checked for byte-identical repeat builds. The independent
formula oracle derives exact rational values and forward rounding-error bounds under the
[arithmetic contract](../../docs/design/derived-measurements.md#arithmetic-contract).
