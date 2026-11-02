# NZ deep-tech venture-capital reference study

> **Disclaimer.** These are real companies, named from public information. The scores are
> illustrative judgements made in September 2026. Nothing here is investment advice or a statement
> about the companies. There is no affiliation with, or endorsement by, any of them.

> **Screening disclaimer.** This example names four real New Zealand startups. Every rating, value
> function and weight in it is the author's own judgement, made in September 2026 from public and
> partly promotional sources. It is a screening model for deciding which company to look at more
> closely next. It is **not**:
>
> - investment advice;
> - a statement about any company's quality or prospects;
> - a prediction of returns or success.
>
> A rating such as "Low Customer Validation" means only that little validation was publicly visible
> at the time, not that none exists. The companies did not take part and have not reviewed these
> ratings.

This is the study MCDA Studio was first built to reproduce: *Prioritising New Zealand Deep-Tech
Startups for Venture Capital Due Diligence* (September 2026). The original analysis was carried out
in DECERNS. The report is not distributed with the project; its citation and a summary are in
[`docs/reference/original-study/`](../../docs/reference/original-study/).

Here the study is expressed in the generic project schema. **No venture-capital logic exists in the
engine**; this is data only. It is the main regression fixture for the mathematics.

**The decision.** Which of four early-stage NZ deep-tech startups should a hypothetical seed fund
prioritise for further due diligence? The alternatives are Hyades, Forever Harvest, Kura Dynamics
and Outlier Space. They are judged against four objectives (Team, Problem & Solution, Market,
Traction) and eight leaf criteria.

## Files

| File | What it is |
| --- | --- |
| `build.py` | Builds the project through the public services API, transcribing the report. Run `python examples/nz_deeptech_vc/build.py` to regenerate the two JSON files |
| `project.json` | The study: 4 alternatives, 4 parent objectives, 8 leaf criteria, measurements, value functions, swing judgements, and the `linear_market_size` scenario |
| `expected_weights.json` | The eight global leaf weights as printed in the report (4 d.p.) |

A test (`test_fixture_file_is_exactly_what_build_py_generates`) fails if `project.json` and
`build.py` ever disagree.

## What was transcribed, and from where

| Item | Report section | Modelled as |
| --- | --- | --- |
| Alternatives | c | `hyades`, `forever_harvest`, `kura_dynamics`, `outlier_space` |
| Value tree | d, Figure 1 | parents `team`, `problem_solution`, `market`, `traction`; leaves `founder_expertise`, `team_coverage`, `problem_significance`, `solution_viability`, `market_size`, `market_growth`, `customer_validation`, `execution_maturity` |
| Six qualitative criteria | e(i), f(iii) | ordinal scale Very Low…Very High; qualitative value function 0 / 0.25 / 0.50 / 0.75 / 1.00 |
| Performance matrix | e(ii), Figure 2 | DECERNS codes 1–5 stored as the level labels; Outlier's Market Size is the **unrounded 1.7129** |
| Market Size | f(ii) | ratio scale (US$ bn), local, concave piecewise-linear through the printed control points (1.380, 0), (2.552, 0.252), (5.077, 0.5), (10.037, 0.748), (26.450, 1) |
| Market Growth | h(i) | ratio scale (% CAGR), local, linear `(g − 8.71)/(23.10 − 8.71)` |
| Swing ratings | h(i) | parents Team 100, Problem & Solution 90, Market 80, Traction 70; leaves 100/65, 90/100, 100/80, 100/70 |
| Linear scenario | i | `linear_market_size` replaces only the Market Size value function with a linear one over the local range |

The report's Founder Expertise **direct-rating** exercise (0 / 90 / 85 / 100, section f(i)) is *not*
part of the model, because the report did not use it in the final model.

## Reference results

| Alternative | Base | Linear Market Size | Rank change |
| --- | ---: | ---: | --- |
| Forever Harvest | 0.7226678550207962 | 0.7226678550207962 | 1 → 1 |
| Outlier Space | 0.6599105426568632 | 0.6522895803586373 | 2 → 2 |
| Kura Dynamics | 0.5985654393128845 | 0.5561197227066853 | 3 → 4 |
| Hyades | 0.5733847765581512 | 0.5733847765581512 | 4 → 3 |

| Weight raised | First winner change |
| --- | ---: |
| Team (parent) | Outlier Space at 0.5688552162065278 |
| Market (parent) | Hyades at 0.6736973263477098 |
| Market Size (local, inside Market) | Hyades at 0.8727820972886765 |
| Problem & Solution, Traction | none over [0, 1] |

At each crossover the two leaders tie, with competition ranks 1, 1, 3, 4.

## Known limitation: rounded control points

The report prints the Market Size control points to three decimals, but quotes the resulting
partial values to six: Outlier 0.071541 and Kura 0.453102. With the printed points, the engine
gives **0.071579** and **0.453150**, a difference of 3.8e-5 and 4.8e-5.

The cause is that the report's points were "lightly adjusted when entered in DECERNS" and are shown
rounded. Searching every control-point set inside the ±0.0005 rounding interval finds sets that
reproduce both six-decimal values, so the report is internally consistent. The unrounded entries
were never published, so they **are not invented**: the project uses the printed points.

The effect is under 1e-5 on any overall value, and no printed score changes a digit. The test
checks that both the report's value and the engine's value lie inside the interval the rounding
allows. Nothing was loosened.

## What the tests check

`tests/regression/test_nz_deeptech_vc_reference.py` has 28 tests, none skipped. They check:

- the project's structure;
- base scores and ranking, and parent, local and global weights;
- the Market Growth and Founder Expertise partial values;
- the rounding-interval check above;
- the linear scenario's values, partial values and ranking, and that it changes only Market Size;
- the first winner change for every parent and for Market Size, including the two "none" cases;
- the tie and global weight at the Market Size crossover;
- an independent plain-Python oracle (no `mcda_studio` imports) for scores, weights and
  crossovers, to 1e-12 and 1e-9.

**The comparison rule:** a value printed to *n* decimals must *round* to the printed digits. That
is stricter than an absolute tolerance of half a unit.

Passing these tests shows that the generic engine reproduces the documented model. It does **not**
prove compatibility with every DECERNS configuration.
