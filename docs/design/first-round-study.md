# Looking back: five first rounds

**Status:** Accepted by the owner in chat, 13 November 2026, through the
first-round study prompt (development record, not included).
The owner also requested deletion of `examples/nz_preseed_reference_cases/` in this session.
Ratings remain a draft; accepting this design does not review any rating.

**Owner amendment in this session, 13 November 2026:** after reviewing the original-window
draft's 43 missing cells, the owner requested wider windows, then selected **12 months before
the anchor through 180 days after it**. This replaces the prompt's original 90-day window rule.
Earlier captures of the company's own website remain allowed. The original anchors stay fixed;
the sidecar snapshot moves to the new last day. Later-in-window information can describe progress
after the round, so this is no longer an announcement-day information set. Unresolved gaps still
require evidence or a separate owner decision; widening the window does not authorise imputation.

**Final scope decision in this session, 13 November 2026:** after the wider-window draft and
both CLI refusals were available, the owner selected **"Accept the 39 missing cells and finalize
the unranked study"**. All five companies stay. No gap receives an invented rating. Both profiles'
ranks, classes and sensitivity are unavailable, and the report must say so. This explicitly
replaces the prompt's expectation of a completed ranking/class table with an unavailable-results
table and a complete list of the 39 accepted gaps.

**Owner amendment, 14 November 2026 (chat; supersedes the final scope decision above and the
"missing stays missing" rule below for these 39 cells):** keep the original goal, a ranked
look-back set beside what happened next. In answer to explicit yes/no questions the owner chose:

1. **The venture study's own convention** for the 39 cells. Where the eligible sources read say
   nothing, the rubric's lowest "nothing public" label applies (*None named*, *None public*, *No
   offshore route stated*, *Pre-revenue*, *Company claim only*, *No dated public milestone*,
   *Concept*), exactly as `examples/nz_venture_screening` does ("No board or advisors named on the
   pages read" gives *None named*). Regulatory burden is a sector judgement ("no product approval
   regime identified", or approval required where the product is a medicine). Competitive
   intensity names funded or listed players from a publisher page captured inside the company's
   window, never a favourable "no competitor identified" from silence. Free public research inside
   the agreed windows may replace an absence rating with a finding.
2. Every such claim states its basis (absence rule, sector judgement or window exception) at the
   start of its description; the README counts each basis per company. **The rule penalises a thin
   public record and therefore biases against companies that later closed**; the README, the
   report and the walkthrough say so.
3. **One window exception:** Argo Navis Aerospace's stage is rated *Pre-seed* from SatNews
   (13 March 2023), which reports WNT Ventures' 2020 pre-seed round; the in-window website already
   named WNT Ventures. It applies to that mandate cell only and is never a reference-case rating
   (it is dated after the snapshot, and mandate leaves carry no weight).
4. The reference cases use the new **leave-one-out** option (`exclude_same_id`, see
   [reference cases](reference-cases.md)) so each company is compared with the other four.

The build now refuses to write while any cell is missing, and the README reports the engine's
ranks and classes under both profiles beside the outcomes. Outcomes still enter no input.

## The decision

Which of five New Zealand companies would a hypothetical seed/Series A fund have prioritised
for diligence using public information around each company's first funding round? This is a
look-back showcase, not a prediction, a validation study or investment advice. The companies were
neither contacted nor affiliated. Five selected companies cannot show whether the method predicts
anything. Outcomes say nothing about the people involved.

| Company | Anchor: first public report | First allowed day | Snapshot / last allowed day |
| --- | --- | --- | --- |
| Vertus Energy | 27 October 2021 | 27 October 2020 | 25 April 2022 |
| Croptide | 14 December 2021 | 14 December 2020 | 12 June 2022 |
| RosterLab | 17 December 2021 | 17 December 2020 | 15 June 2022 |
| Argo Navis Aerospace | 21 September 2020 | 21 September 2019 | 20 March 2021 |
| Helico | 9 May 2022 | 9 May 2021 | 5 November 2022 |

Argo Navis's anchor is the earliest saved website capture naming WNT Ventures, not a confirmed
round announcement date. Helico's first round was labelled **seed**. These qualifications stay
visible in the example and report.

## Sources and rating rules

Read the venture study's criteria tree, fixed scales, value functions, profiles, sorting classes
and mandate requirements at build time. Copy `rubrics.json` byte for byte: its wording is not
rewritten. The market-year exception below is explicit in the example and evidence descriptions.
Do not copy alternative-specific uncertainty, scenarios or other methods' judgements.

Use sources published or captured from the first allowed day through the last day, inclusive. Earlier
archived captures of the company's own website may also support ratings. Other earlier sources
and all sources after the window are context only. A publisher page captured before the window
does not qualify merely because its estimate concerns an earlier year. Paywalled bodies, logins
and the unreadable Business Wire release are excluded. Raw pages stay under `$MCDA_DATA`; the
repository contains short claims in our own words, source URLs and dates.

Rate a leaf only where an eligible source supports the venture rubric step. Each rating notes
that step, the evidence and any uncertainty. Absence of a statement is not evidence of no
regulatory burden, no competitors, no revenue, or an unpaid trial. Missing stays missing; never
insert zero or a favourable label to make a ranking run. List every gap for the owner. The engine
refuses a screening ranking for the whole project if required cells are missing; a ranked result
therefore requires dated support or an explicit owner decision for every remaining gap, recorded
in the report. Do not change engine validation to work around that refusal.

### Market size and growth

Use the median of distinct publishers' public estimates for the narrowest named segment containing
the core product, and the median of the same publishers' stated forecast CAGRs. Use a value for
the anchor year, or the latest stated year not after it. Do not extrapolate from a future value,
back-calculate a base-year value or infer a missing CAGR. The publisher page itself must have
been captured or published inside the company's window. Record publisher, segment, original URL,
archive URL/capture date, stated year, size in US$ bn and forecast CAGR/period.

One publisher is allowed and flagged when fewer than two eligible paired estimates exist. Two
pages from one publisher count once. A broad containing segment is explicitly flagged; an
adjacent segment is excluded. Conflicting figures within a page require resolution or exclusion.
All estimates and exclusions are fixed before analysis; do not tune them after seeing ranks.

## Files and separation of outcomes

`examples/nz_first_round_retrospective/build.py` deterministically writes `project.json`,
`evidence.json`, `reference-cases.json`, `rubrics.json` and `README.md`. The build has no network
dependency or dependency on private saved pages. Every performance has exactly one dated,
unreviewed evidence claim, tool origin `claude-code`, marked "draft; author review pending".
The report identifies Codex's extension of the earlier Claude Code draft honestly.

Outcomes live only in the reference-cases sidecar and README, and beside the results in the run
report. They never enter a project, evidence dossier, rubric, weight, class or market selection.
The sidecar uses existing version 1, `criteria_from` equal to this project's id, snapshot dates
equal to the last days above, and a context row for each round's announcement/anchor date. Its
labelled ratings match project measurements; numeric market claims remain in evidence because
reference-cases version 1 does not rate numeric criteria. Validate the sidecar and stop on any
issue before writing any generated file. Add a build-level lower-window guard as the service's
snapshot guard checks only the upper bound.

## Hindsight and exclusions

The earlier ratings were drafted by Claude Code with knowledge of the outcomes; Codex extends
and checks the draft in this run, also knowing those outcomes. Author review is pending. A blind
re-rating packet is a next step, not a completed independent assessment. Public-source survival
differs between companies; missing evidence is not a finding about company quality.

Exclude Outlier Space and Marloo, outcome-based tuning of criteria, weights, classes or ratings,
and every claim of predictive accuracy. No mathematics, stored schema, pinned fixture or old
output changes. No model/API call, paid service, account, push, tag or release.

## Verification

Build twice and compare bytes with each other and shipped files. Check exact inheritance from
the venture study and byte-identical rubrics; every evidence date and labelled reference rating;
one claim per cell, pending review and no outcome leakage. Inject sources one day outside each
boundary, including an allowed earlier own-site capture, and an invalid sidecar: the build must
refuse before writing. Independently calculate market medians with standard-library decimal or
fraction arithmetic in tests, without importing the application. Add reachable mutants for new
build guards, inheritance, market aggregation and outcome separation.

Run the full gate serially, the development's mutation group and unmodified control, and compare
the 969 historical output bodies. Run CLI evaluation and screening summary under both profiles,
and reference cases for one company with outcomes off and on; save results and refusals under
`$MCDA_DATA/first-round-study-2026-11-13/runs/`. Report unavailable results plainly without
manufacturing ranks, classes or sensitivity results. Update the browser test to use this example
while retaining its complete outcomes-switch and view-only assertions.
