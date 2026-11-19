# Original study report

**Title:** *Prioritising New Zealand Deep-Tech Startups for Venture Capital Due Diligence*
**Author:** Sooyoung Park, September 2026. 11 pages; the analysis was carried out in DECERNS.
**Copyright:** © 2026 Sooyoung Park. All rights reserved.

**The report is not distributed with this project.** This page is its citation and a summary of
how each part is used. The software contains no venture-specific logic and never needed the report
to run. The study is encoded as data in
[`examples/nz_deeptech_vc/`](../../../examples/nz_deeptech_vc/) and checked by
`tests/regression/test_nz_deeptech_vc_reference.py`.

- **Real companies.** The report names four real startups, from public information. The scores are
  illustrative judgements made in September 2026, not investment advice or a statement about the
  companies, and there is no affiliation or endorsement.
- **Sources.** The report's own reference list credits its 15 public sources.
- **DECERNS.** The original analysis was carried out in DECERNS, which is credited in
  [ACKNOWLEDGEMENTS](../../../ACKNOWLEDGEMENTS.md).

## Contents, and how each part is used

| Section | Content | Used in MCDA Studio as |
| --- | --- | --- |
| a | Decision problem: screening for further due diligence, not an investment decision | Project description |
| b | Mind map of initial considerations (team, problem/solution, market, traction) | Background only |
| c | Four alternatives: Hyades, Forever Harvest, Kura Dynamics, Outlier Space | Alternatives |
| d, Fig. 1 | Value tree: 4 objectives, 8 leaves; reasons for merging or splitting criteria | Criteria tree |
| e(i)–(ii), Fig. 2 | Measurement rules, rubrics, performance matrix, market-proxy sources | Scales and measurements (Outlier Market Size 1.7129 unrounded) |
| f(i) | Direct rating of Founder Expertise (0/90/85/100), **not used** in the final model | Not modelled |
| f(ii) | Market Size piecewise function, elicited by bisection; points printed to 3 d.p. | Piecewise value function, rounding caveat |
| f(iii) | Problem Significance multi-aspect scale; all qualitative criteria use 0/25/50/75/100 | Qualitative value functions |
| g | Why MAVT was chosen | Method rationale |
| h(i) | Market Growth linear function; additive model; swing weights 100/90/80/70 and leaf ratings | Value function, weight profile |
| h(ii), Fig. 3 | Base and linear-scenario results | Regression oracle |
| i, Figs. 4–5 | One-way sensitivity thresholds; Market Size tie near 0.648 | Sensitivity regression oracle |
| References | 15 public sources (market reports, funding news) | Not used by the code |

The precision gap between the report's six-decimal Market Size partial values and the printed
control points is explained in the
[example's README](../../../examples/nz_deeptech_vc/README.md#known-limitation-rounded-control-points).
