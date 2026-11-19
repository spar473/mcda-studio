# Venture screening study: NZ startups for due diligence (public information)

> **Real companies, public information, the author's own judgements.** This example names eight
> real New Zealand companies. Every fact comes from a public web page read on **4 November 2026**,
> and every rating is the study author's judgement against the written rubrics below. It is a
> **screening and prioritisation** model for a *hypothetical* fund: **not investment advice**, not a
> valuation, and not a prediction of any company's success. The companies were **not contacted**
> and are **not affiliated** with this project. Pages behind logins or paywalls were not used.
> Ratings rest on what the public record shows, so a quiet company scores lower than a loud one with
> the same substance. Corrections are welcome; nothing here should be read as a statement about a
> company beyond what its cited source says.
>
> **Disclosure:** Scentian Bio's chief executive is publicly listed as a judge in a University of
> Auckland entrepreneurship programme connected with the author. The author has no relationship
> with the company.

The question: *which early-stage New Zealand startups should a hypothetical generalist seed/Series A
fund prioritise for its next due-diligence slots?* The design and its decisions are in
[the design note](../../docs/design/vc-screening-study.md); this page states where every number
comes from.

```sh
python examples/nz_venture_screening/build.py
```

The script builds `project.json`, `evidence.json` and `decision.json` through the public services
API, and refreshes the gallery card in `examples/starter_templates/venture_screening_study/`.
Building twice on the same runtime and platform gives identical files; decision metadata records the execution environment. The engine has no venture-specific code: everything in this
study is data in `build.py`.

## The companies

| Company | Sector | Stage | Market segment |
| --- | --- | --- | --- |
| Captivate Technology | Climate and energy | Seed (observed) | Point-source carbon capture |
| Wellumio | Health and medtech | Seed (observed) | Portable magnetic resonance imaging |
| Scentian Bio | Agritech and food | Seed (observed) | Electronic nose (e-nose) |
| Hectre | Agritech and food | Series A (observed) | Fruit and vegetable sorting machines |
| Wych | Fintech and B2B software | Seed (judgement) | Open banking |
| Upstock | Consumer and marketplaces | Seed (judgement) | B2B food marketplace platforms |
| Kea Aerospace | Space and advanced hardware | Series A (judgement) | High-altitude pseudo-satellites (HAPS) |
| Hnry | Fintech and B2B software | Series B or later (observed) | Small-business accounting software |

Stage follows the rubric: the last disclosed round by its published label, with pre-Series A
mapped to Seed. Where no label is published (Wych, Upstock, Kea Aerospace) the stage is a
judgement from the round's size and reported dilution. **Hnry fails the mandate** (Series C is
later than Series A) and keeps its place in every ranking, with the failure shown beside it.

## The model

- **Mandate (screened, not scored):** HQ country, stage and sector, rated 0 in both profiles so their
  global weight is exactly 0. Three requirements read them: head office in New Zealand, stage at most
  Series A, sector in the fund's list (every sector except "Other").
- **Four scored objectives, sixteen criteria**, each with a rubric (in `build.py` and the design
  note). Five-level rubrics map to 0, 0.25, 0.5, 0.75, 1 and four-step ladders to 0, 1/3, 2/3, 1;
  equal spacing is itself a judgement. Every scale has fixed anchors, so adding or removing a company
  never moves another's value or class.
- **Market size:** US$ bn on a fixed domain [0.01, 200], concave piecewise-linear value
  (0.01→0, 0.1→0.15, 1→0.35, 5→0.65, 25→0.9, 200→1). **Market growth:** % CAGR, linear on [0, 40].
- **Profiles:** Technical/IP-led (the automatic default) and Commercial/traction-led, with the swing
  ratings in the design note. **Scenario:** linear market size on the same fixed domain.
- **Classes:** Prioritise for diligence (≥ 0.60), Monitor (≥ 0.40), Not now, fixed before any
  company was rated. An audit sample draws one company from Not now.
- **SMAA-2:** market size and growth vary uniformly across the publishers' full range; every
  scored rubric cell whose claim is a judgement varies by one level (0.25 / 0.5 / 0.25, or 0.5 / 0.5
  at a scale end); the preference run varies the four top-level ratings across both partners'
  values. Cells are independent.
- **PROMETHEE II:** its own weights (each objective 25, split equally over its four criteria;
  mandate criteria 0), V-shape on rubric levels with p = 2, linear on market size (q = 1, p = 20)
  and growth (q = 2, p = 10).
- **AHP:** deliberately not set up; 28 pairwise company judgements for each of 16 criteria (448)
  would have to be invented.

## Ratings

Rubric levels (1 = worst for the fund). An asterisk marks a **judgement** claim; the others are
**observed** facts from the cited page. Each cell's source, location and paraphrase is a claim in
`evidence.json`.

| Criterion | Captivate Technology | Wellumio | Scentian Bio | Hectre | Wych | Upstock | Kea Aerospace | Hnry |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Founder-problem expertise | 4* | 4 | 4 | 3 | 3* | 3 | 3 | 2* |
| Team completeness | 3* | 5* | 2* | 4 | 1* | 3* | 2* | 2* |
| Prior venture or operating track record | 3* | 3* | 4 | 4 | 2* | 5 | 4 | 1* |
| Advisors, board and key hires | 3* | 3* | 3* | 1* | 1* | 4 | 1* | 3* |
| Problem severity and willingness to pay | 2* | 3* | 2* | 1* | 2* | 1* | 2* | 2* |
| Differentiation and defensibility | 3* | 4 | 3 | 3 | 2* | 2* | 2* | 2* |
| Product or technology readiness | 3 | 3* | 3 | 4 | 4 | 4 | 2 | 4 |
| Regulatory and certification burden (minimise) | 4* | 2 | 4* | 4* | 3 | 4* | 2* | 3* |
| Competitive intensity (minimise) | 2* | 2* | 2* | 2* | 3* | 2* | 2* | 2* |
| Route to global markets | 3 | 4 | 2* | 4* | 4 | 4* | 3* | 5 |
| Customer validation | 2* | 2* | 3 | 4 | 4 | 4 | 2* | 4 |
| Commercial stage | 1* | 1 | 2* | 4 | 3* | 4* | 1* | 4 |
| Strategic partnerships and channels | 3 | 3 | 3 | 1* | 4 | 4 | 3 | 1* |
| Milestone delivery | 3* | 4* | 2* | 4* | 4* | 4* | 3* | 4* |

71 of the 112 scored rubric cells (14 rubric criteria × 8 companies) are judgements. Many low ratings mean "no public evidence on the
pages read" (for example no named board): that is a statement about the public record, recorded as
a judgement, and Open Questions lists it as something to ask.

## Market estimates

Each company's market is the narrowest named third-party segment containing its core product
(itself a judgement; Hectre's software is measured against fruit and vegetable sorting machines,
the closest segment with public estimates). The entered value is the **median of distinct
publishers' 2025 values** stated on their public pages; growth is the median of the same
publishers' stated forecast CAGRs. SMAA-2 draws across the full range. A page stating two 2025
values more than 5% apart is excluded: Spherical Insights' e-nose page (US$1.47bn and US$47bn).

<a id="market-estimates"></a>

| Company | Publisher | Page date | 2025, US$ bn | Forecast CAGR % |
| --- | --- | --- | --- | --- |
| Captivate Technology | [The Business Research Company (via GII)](https://www.giiresearch.com/report/tbrc1985099-point-source-carbon-capture-device-pscd-global.html) | 2026-03-16 | 3.45 | 14.6 |
| Captivate Technology | [Market Intelo](https://marketintelo.com/report/point-source-carbon-capture-market/amp) | 2026-06-11 | 7.2 | 15.3 |
| Wellumio | [Straits Research](https://straitsresearch.com/report/portable-magnetic-resonance-imaging-market) | 2026-09-18 | 2.71 | 5.8 |
| Wellumio | [The Business Research Company (via GII)](https://gii.tw/report/tbrc1706115-portable-magnetic-resonance-imaging-mri-global.html) | 2025-09-10 | 3.78 | 6.7 |
| Wellumio | [Mordor Intelligence](https://www.mordorintelligence.com/industry-reports/portable-magnetic-resonance-imaging-market) | 2026-09-11 | 4.38 | 6.05 |
| Wellumio | [Reportprime](https://www.reportprime.com/portable-mri-r9073.md) | 2026-11-04 | 0.47786 | 12.65 |
| Scentian Bio | [Global Market Insights](https://www.gminsights.com/industry-analysis/e-nose-electronic-nose-market) | 2026-08-01 | 0.0597 | 9.5 |
| Scentian Bio | [Mordor Intelligence](https://www.mordorintelligence.com/industry-reports/electronic-nose-market) | 2026-09-11 | 0.14628 | 12.26 |
| Scentian Bio | [Market Research Future](https://www.marketresearchfuture.com/reports/electronic-nose-market-22638) | 2026-10-27 | 1.58 | 10.1 |
| Scentian Bio | [Market.us](https://scoop.market.us/?p=58472) | 2025-07-22 | 44.01 | 18.5 |
| Hectre | [360iResearch (via GII)](https://www.giiresearch.com/report/ires2008217-fruit-vegetable-sorting-machine-market-by-machine.html) | 2026-07-30 | 1.26 | 7.28 |
| Hectre | [DIResearch (via MarketPublishers)](https://marketpublishers.com/report/equipment/food-beverage-equipment/fruit-n-vegetable-sorting-machine-research-report-dir.html) | 2025-06-01 | 0.76252 | 6.8 |
| Hectre | [PW Consulting](https://pmarketresearch.com/worldwide-fruit-and-vegetable-sorting-machine-market-research) | 2026-06-10 | 2.1854 | 7.12 |
| Wych | [Grand View Research](https://www.grandviewresearch.com/industry-analysis/open-banking-systems-market) | 2026-06-01 | 39.8 | 28.2 |
| Wych | [Next Move Strategy Consulting](https://www.nextmsc.com/report/open-banking-market-bf5510) | 2026-09-30 | 27.85 | 22.8 |
| Wych | [Precedence Research](https://www.precedenceresearch.com/open-banking-market) | 2026-09-21 | 35.72 | 21 |
| Upstock | [The Insight Partners](https://www.theinsightpartners.com/reports/b2b-food-marketplace-platform-market) | 2026-07-31 | 47.63 | 17.5 |
| Upstock | [Verified Market Research](https://www.verifiedmarketresearch.com/product/b2b-food-marketplace-platforms-market/) | 2026-09-01 | 28.14 | 16.2 |
| Kea Aerospace | [Reanin](https://www.reanin.com/reports/high-altitude-pseudo-satellites-market) | 2026-09-01 | 1.02 | 8.3 |
| Kea Aerospace | [SNS Insider](https://www.snsinsider.com/press-release/global-high-altitude-pseudo-satellite-market) | 2026-09-29 | 1.2 | 17 |
| Kea Aerospace | [Spherical Insights](https://www.sphericalinsights.com/blogs/top-10-high-altitude-pseudo-satellite-haps-market-companies-advancing-persistent-connectivity-and-surveillance) | 2026-09-01 | 1.13 | 21.65 |
| Kea Aerospace | [Aviation & Defense Market Reports (via GII)](https://www.giiresearch.com/report/avd1858531-global-high-altitude-pseudo-satellites-market.html) | 2025-11-01 | 3.9 | 12.73 |
| Hnry | [Market Research Future](https://marketresearchfuture.com/reports/small-business-accounting-software-market-32881) | 2026-09-17 | 8.22 | 6.92 |
| Hnry | [Market Intelo](https://marketintelo.com/report/small-business-accounting-software-market) | 2026-06-21 | 9.6 | 9.8 |

| Company | Entered size (median) | SMAA-2 range | Entered growth (median) | SMAA-2 range |
| --- | --- | --- | --- | --- |
| Captivate Technology | 5.325 | 3.45–7.2 | 14.95 | 14.6–15.3 |
| Wellumio | 3.245 | 0.47786–4.38 | 6.375 | 5.8–12.65 |
| Scentian Bio | 0.86314 | 0.0597–44.01 | 11.18 | 9.5–18.5 |
| Hectre | 1.26 | 0.76252–2.1854 | 7.12 | 6.8–7.28 |
| Wych | 35.72 | 27.85–39.8 | 22.8 | 21–28.2 |
| Upstock | 37.885 | 28.14–47.63 | 16.85 | 16.2–17.5 |
| Kea Aerospace | 1.165 | 1.02–3.9 | 14.865 | 8.3–21.65 |
| Hnry | 8.91 | 8.22–9.6 | 8.36 | 6.92–9.8 |

Scentian Bio's own figure (a food quality control market of over US$8bn) is kept as an open,
unreviewed *proxy* claim beside the median.

## Evidence

`evidence.json` is a version-1 dossier bound to `project.json`: 154 claims, one accepted claim per
entered measurement (reviewer "Study author (illustrative review)") plus two **disputed claims left
open**: Kea Aerospace's stage (an aggregator lists the last round as crowdfunding with no label)
and Scentian Bio's market size. A source published more than 12 months before the as-of date is
marked **outdated** (33 claims); all of Upstock's sources are, so its leading position rests on
evidence a diligence team would refresh first. Each claim's description starts with its kind:
Observed, Judgement or Proxy (the dossier format has no kind field; nothing in the format changed).

## Reading the study

Under both profiles Upstock leads and is the only company in Prioritise for diligence; Kea Aerospace
is in Not now; everyone else is in Monitor. Under the Commercial/traction-led profile Hectre sits
less than 0.001 below the Prioritise boundary. PROMETHEE II also puts Upstock first; SMAA-2 gives
it the first rank in most draws of the stated uncertainty, and in every draw of the partners'
weight range. These are preference values and sampled acceptabilities under the stated
assumptions, not probabilities of success.

`decision.json` is one **illustrative** version-2 decision record selecting Upstock for the next
diligence slot, with six analyses, its rationale, unresolved assumptions and review triggers, each
beginning "Illustrative:".

Without an evidence dossier, Open Questions lists 65 questions under Technical/IP-led and 64
under Commercial/traction-led in the base scenario. Weight questions exclude the mandate branch
and its descendants; their zero weight is deliberate. Loading evidence adds its own questions.

## Second rater (blind) and `rubrics.json`

`build.py` also writes `rubrics.json`: each scored leaf's ID, name, objective, scale type, labels
worst to best and rubric text, with the mandate leaves listed as screened and excluded. It holds
the scales' own wording and no rating. `scripts/rater_kit.py` turns it, with the project's names and
the evidence dossier's source links (never its values, descriptions, reviews or notes), into a
self-contained rater packet so a second person can rate the 112 rubric cells blind. See the
[design note](../../docs/design/blind-rater-kit.md). The packet, the rater's answers and every
label stay outside the checkout.

## Known limits

- Public information only, mostly company-published; self-reported figures are marked as such.
- No validation against outcomes: nothing here has been checked against what later happened.
- The mandate criteria carry no weight. The Sensitivity tab can still probe giving that branch
  a weight, and the dominance diagnostic compares mandate criteria too. Open Questions and the
  summary exclude those weight changes. PROMETHEE II reports the three mandate criteria as inert,
  as intended.
- Opening the gallery card produces a lineage receipt whose generic limitation text describes all
  starter values as invented; for this card that is wrong (the values are public facts and the
  author's judgements). Changing that shared text would change an existing export, so it is left
  for an owner decision.
