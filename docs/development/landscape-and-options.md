# Landscape and options: MCDA Studio against other tools and approaches

> **Direction update, 27 October 2026:** the [current roadmap](../../ROADMAP.md) sets a
> general engineering decision-making direction. Domain-specific proposals below are historical
> context, not a preferred sector or firm for the product.

**Status:** historical options analysis with review amendments, 2026-10-26. It feeds the
implementation plan (historical record, not included). Nothing here is a release commitment.

## How to read this

- **Earlier source record:** the proposal recorded web searches on 2026-10-26. “Searched” in
  retained tables refers to that record, not a fresh verification in this review. Vendor/review
  claims are leads for evaluation, not independently established comparisons. One comparison
  source is written by a vendor (Analytica). Prices are omitted here; no pricing refresh was done.
- **Background:** general knowledge of the field, not re-checked on this date. Confirm it before
  quoting it publicly.
- This page compares **capabilities and approaches**. It is not a claim about how any product
  behaves inside. That rule matters most for DECERNS, which has never been observed.

## 1. Where MCDA Studio stands today

**Repository strengths (not a market-wide verification ranking):**

- Every number comes from one tested engine. It has exact closed-form crossovers, independent
  oracles and a mutation harness. Comparable verification evidence was not established by the earlier source collection.
  Absence from that collection does not establish that another product is unverified.
- Range-aware swing weighting with review warnings. The UI explicitly relates weights to stated swings. Comparing other products requires
  inspecting their elicitation workflow, not assuming that a field labelled “importance” ignores ranges.
- Exports that regenerate exactly, sparse scenarios and preference profiles.
- Local, open source (MIT) and inspectable.

**Gaps against the field:**

| Gap | Who covers it |
| --- | --- |
| Only one method | Libraries have 20–70+ methods; commercial suites usually offer 1–3 |
| No uncertainty analysis | DecideIT (intervals, second-order), Analytica (Monte Carlo), JSMAA (SMAA) |
| No sorting into classes | DEXi, ELECTRE TRI/FlowSort tools, UTADIS research code, JSMAA (SMAA-TRI) |
| No group elicitation | Comparion, 1000minds, D-Sight, decision-conferencing tools such as Hiview3 |
| Weak elicitation aids | M-MACBETH (qualitative difference judgements), 1000minds (PAPRIKA pairwise trade-offs) |
| Limited visual/guided structuring | Value-focused thinking / PrOACT practice; Hiview3 in decision conferences |
| No learning from data | Preference-learning research; ML classifiers |

## 2. The landscape

### 2.1 Desktop and web MCDA products

| Product | Method | Platform and price | Stands out for | Evidence |
| --- | --- | --- | --- | --- |
| 1000minds | PAPRIKA: pairwise choices between two-criterion trade-offs, giving additive value weights | Web; price not reviewed | Large stakeholder surveys; also used for conjoint analysis | Searched |
| Comparion (Expert Choice) | AHP | Web; price not reviewed | Facilitated group elicitation, consistency ratio | Searched |
| Decision Lens | AHP, ANP | Web; price not reviewed | Portfolio and budget governance | Searched |
| Visual PROMETHEE | PROMETHEE I/II, GAIA plane | Windows; free academic edition | Outranking, stability intervals, GAIA visual | Searched |
| D-Sight | PROMETHEE, MAUT | Web; price not reviewed | Group collaboration | Searched |
| Logical Decisions | MAUT, AHP | Windows; quote | Explicit value functions on one utility scale | Searched |
| Analytica | General influence diagrams; no packaged MCDA module | Windows and web; free edition limited to about 100 objects | Native Monte Carlo | Searched (vendor-written) |
| DecideIT 3.0 | Multi-criteria and decision trees with intervals, comparisons and second-order belief | Desktop | Severe uncertainty, interval tornado diagrams | Searched |
| M-MACBETH | MACBETH: qualitative difference judgements turned into interval value scales by linear programming, with consistency checks | Windows | Value functions and weights from words, not numbers | Background |
| Hiview3 | MAVT with swing weights | Windows | Decision conferencing; widely used in UK public sector | Background |
| DECERNS | Several methods (MAVT, AHP, PROMETHEE, TOPSIS among others) with GIS | Desktop | Spatial decisions | Background; **never observed** |

### 2.2 Free and academic tools

| Tool | What it does | Evidence |
| --- | --- | --- |
| Super Decisions | AHP and ANP, free | Background (named in a searched page) |
| Web-HIPRE | MAVT and AHP value trees in a browser, from Aalto University | Background |
| DEXi | Qualitative multi-attribute models with **rule tables**: options are classified into discrete classes, not scored | Background |
| JSMAA | Open-source Java SMAA: SMAA-2 (ranking), SMAA-TRI (sorting), SMAA-O (ordinal data) | Searched |
| diviz / XMCDA | Workflows of MCDA web services in a shared XML format | Background |
| jMAF / jRS | Dominance-based rough set approach (DRSA): if-then rules learned from example decisions | Background |

### 2.3 Libraries

| Library | Language | Coverage | Evidence |
| --- | --- | --- | --- |
| pyDecision | Python | 70+ methods, with an optional LLM layer to explain results | Searched |
| pyrepo-mcda | Python | About 20 methods (TOPSIS, VIKOR, PROMETHEE II, AHP, …) and objective weighting | Searched |
| pymcdm, scikit-criteria | Python | Broad sets of matrix-based methods | Searched (pymcdm, named only) / Background |
| MCDA (R), JMcDM (Julia) | R, Julia | Method collections | Searched (named) |

The listed libraries emphasise matrix-based methods. GUI, hierarchy, elicitation, scenario and
verification capabilities vary by package/version and were not systematically audited. They are
possible comparison implementations, not automatically independent numerical oracles.

### 2.4 Classifier models

"Classifier" covers two very different things here.

**(a) Multi-criteria sorting.** These methods assign each option to ordered classes, such as
*Proceed to diligence / Watch / Decline*, using the decision maker's preferences.

- **UTADIS:** an additive value model, as in MAVT, plus class thresholds on the overall value.
- **MR-Sort / ELECTRE TRI:** outranking against class boundary profiles.
- **Preference disaggregation:** learns the model's value functions, weights and thresholds from
  example assignments the analyst has already made, usually by linear programming.
- **Robust ordinal regression:** necessary/possible assignments quantify over the specified
  feasible model set and need exact optimisation or another justified formal procedure.
- **SMAA-TRI:** sampled class acceptability under a specified probability distribution. Finite
  sampling does not establish an assignment for every admissible model; observed frequency one
  or zero is not a universal proof.
- **Recent research:** monotone neural networks that learn marginal value functions, attention
  networks for interacting criteria, and recurrent networks for criteria that change over time. In
  one 2025 study UTADIS had the best precision but the worst recall. Results depend on the data,
  and no model wins everywhere (searched).

**(b) Machine-learning outcome predictors.** The earlier source list includes tree-based, LLM
and graph studies. The following are hypotheses from that review, not field-wide benchmarks:

- Tree ensembles are candidates for structured-data baselines; relative performance depends on the dataset and protocol.
- Funding history may be an influential feature; check leakage, observation date and label definitions.
- Recall and precision-at-K matter more to investors than accuracy.
- "Success" is defined inconsistently (next round, exit, unicorn), datasets range from about 900 to
  2 million companies, and many results are preprints.

These two answer different questions:

| | MCDA sorting (UTADIS, MR-Sort) | ML outcome classifier |
| --- | --- | --- |
| Question | "Which class does this option belong in, given **our** preferences?" | "How likely is outcome Y, given past data?" |
| Needs labelled outcomes | No. It needs preferences, or a few example assignments | Yes, many, and they carry survivorship and selection bias |
| Explanation | Explicit weights/functions/thresholds; still requires understandable assumptions | Depends on model; some predictors are intrinsically interpretable |
| Monotone in criteria | Enforced | Not unless constrained |
| Fits NZ early-stage data | Yes (a few ventures) | Poorly: small, sparse, censored outcomes |

### 2.5 LLM-assisted decision analysis

The earlier source list includes a review of LLM weight elicitation; this review did not
validate its field-wide conclusions. Studies compare LLM-generated AHP weights with expert panels,
simulate expert panels with several LLM agents (Best–Worst Method), or split AHP into
retrieval, criteria and weighting agents. Results vary by model and task.

The main risk for MCDA Studio: an LLM's weights are **not** the decision maker's preferences. The
safer uses are:

- structuring prompts (objectives, missing criteria);
- extracting evidence with citations, for a person to accept;
- explaining results in plain language using engine numbers only.

### 2.6 Other decision processes

| Process | What it adds | Relevance |
| --- | --- | --- |
| Value-focused thinking and PrOACT (Keeney; Hammond, Keeney and Raiffa) | Start from objectives, not options. PrOACT steps through problem, objectives, alternatives, consequences, trade-offs | A guided "new project" flow; checks for means-objectives masquerading as fundamental ones |
| Decision conferencing | A facilitated workshop with a live model on screen | Profiles already exist; this needs a presentation mode and fast what-ifs, not a server |
| Structured decision making (SDM) | PrOACT applied in environmental and public agencies | Same as above |
| Decision trees and influence diagrams | Sequential choices under risk, expected utility | A different model; outside the additive value tree |
| Robust decision making and other deep-uncertainty methods (RAND; Marchau et al. 2019) | Test options across many plausible futures instead of one forecast | Close to SMAA and scenario sweeps; supports "robust choice" language |
| Delphi and group aggregation | Iterated anonymous judgements; combining several decision makers | Comparing profiles, and showing disagreement explicitly |

## 3. Comparison limits and product direction

The earlier proposal scored whole categories (commercial suites, libraries and ML classifiers)
with strong/partial/none symbols. Those ratings are withdrawn: products vary and the source
collection cannot establish category-wide verification, exact-sensitivity or local-use claims.
Compare a named product/version against a specific user task and primary evidence before making
public competitive claims. Keep “not found in reviewed sources” distinct from “does not exist”.

The defensible product direction is a local, inspectable workspace where people build a value
model, see missing inputs and explain engine results. Existing linked charts already cover
ranking, contributions, partial values and dominance. The visual gap is a live structural canvas
with linked input coverage, not an absence of analytical charts. See the
code-backed review (historical record, not included) and [canvas design](../design/live-model-canvas.md).
Neither method breadth nor a lively diagram substitutes for validated calculations.

## 4. Options

S/M/L are retained historical relative scope labels, **not delivery estimates**. Actual scope,
schema and verification work need discovery before scheduling. “Reuse” means existing components
that may help; it does not imply low numerical risk.

| ID | Option | What it is | Reuse | General value | VC value | Size | Main risk |
| --- | --- | --- | --- | --- | --- | --- | --- |
| O1 | SMARTER (rank-order weights) | Ranks become ROC weights | High; profile method string exists; validation currently rejects it | Medium | Medium (fast first pass) | S–M | Low |
| O2 | **Value-based sorting (UTADIS-style)** | Ordered classes and thresholds on the overall MAVT value | Very high: same values; sensitivity extends to threshold crossings | High | **High** (triage *is* sorting) | M | Threshold-boundary semantics (define exactly like ties) |
| O3 | **SMAA for MAVT** | Sample uncertain weights and performances; rank and class acceptability indices | High: reuses evaluation in a loop | High | **High** (missing or uncertain evidence) | M–L | Stochastic testing: fixed seeds, analytic cases, honest tolerances |
| O4 | Preference disaggregation | Learn a UTADIS model (value functions, weights, thresholds) from the analyst's example assignments by LP; report robust assignments | Medium; needs O2 and a runtime LP solver (SciPy HiGHS) | Medium–high | High (calibrate to past decisions) | L | Overfitting few examples; SciPy becomes a runtime dependency |
| O5 | AHP | Pairwise matrices, eigenvector priorities, consistency ratio | Low; new data, result and UI | Medium (familiar to users) | Low | L | Rank reversal; competes with mature tools |
| O6 | PROMETHEE II | Preference functions, outranking flows | Low | Medium | Low–medium | L | Competes with Visual PROMETHEE and libraries |
| O7 | MACBETH-style elicitation | Qualitative difference judgements produce value functions and swing ratings by LP | Medium; output is the existing model | Medium–high (fewer number-guessing errors) | Medium | L | LP feasibility explanations are hard to make clear |
| O8 | Profile comparison (group view) | Ranks per profile side by side; disagreement map; optional SMAA across profiles | High | Medium | Medium (partners disagree) | S–M | Low |
| O9 | Guided structuring (PrOACT / value-focused thinking) | New-project flow: objectives first, a fundamental-against-means check, range prompts | High (UI only) | Medium | Medium | M | UX only; no numerical risk |
| O10 | LLM assistant (optional plugin) | Structuring prompts, cited evidence extraction, plain-language explanation | Outside the engine | Medium | Medium–high (evidence) | M–L | Privacy, cost, hallucination. Never sets weights by default |
| O11 | ML score as a proxy criterion (VC layer only) | An external classifier's score enters as a labelled *derived proxy* with a model card | Outside the engine | Low | Medium, *if* good data exists | M | Double counting funding signals; false precision; data licensing |

### What to avoid

- **Don't make ML success probability the engine's output.** It contradicts the project's core
  statement that scores are preferences, needs data the target use (NZ early stage) mostly lacks,
  and outcome labels carry survivorship bias. If O11 is ever built, it lives in the VC layer as one
  disclosed input.
- **Don't let an LLM fill in weights silently.** If O10 suggests weights at all, they go into a
  separate profile labelled "suggested, not elicited", and never into the default profile.
- **Don't chase method count.** Add a method only when it does something the current model
  can't, or when users ask for it by name.

**Applied to the canvas (2026-10-26):** value-focused thinking prompts, value-tree weight display
in the style of Hiview3 / Web-HIPRE, and a decision-conferencing presentation view are built into
the Canvas; group disagreement, MACBETH-style elicitation, sorting bands and SMAA acceptability are
mapped to later canvas hooks. See the [canvas design](../design/live-model-canvas.md#ideas-from-the-landscape-review-applied-to-the-canvas).

## 5. Earlier recommendation and retained decision

Interleave methods and VC work, as decided, but choose the methods by what they add to the value
model rather than by name recognition:

1. **Foundation (earlier proposal):** re-verify, packaging (pipx wheel), resilience.
2. **Method-neutral core plus SMARTER (O1):** a weighting-extension test, not validation of a different method interface.
3. **Value-based sorting (O2):** an explainable preference-based classifier. It is
   the natural shape of VC triage and useful generally (grading, eligibility bands).
4. **SMAA for MAVT (O3):** uncertainty with acceptability indices, with explicit analyst-approved distributions and dependence assumptions for uncertain inputs.
5. **VC evidence layer v1:** evidence, provenance and missing data, which compiles to a normal
   project and uses O2 and O3.
6. **Profile comparison (O8) and guided structuring (O9):** smaller UX slices, to fit between the
   larger ones.
7. **Preference disaggregation (O4):** learns from the analyst's examples. It is the
   interpretable answer to "use a classifier".
8. **Later, on demand:** AHP (O5), PROMETHEE (O6), MACBETH elicitation (O7), the LLM plugin
   (O10) and the ML proxy (O11).

This moves AHP and PROMETHEE later than in the first plan. Mature tools already cover them, and
for the VC use case they add less than sorting and uncertainty do.

**Decision (2026-10-26):** this recommendation was not adopted. The
implementation plan (historical record, not included) keeps AHP (P4) and
PROMETHEE II (P5) before sorting (P6) and SMAA (P7). The earlier recommendation is retained as the record of the trade-off, with technical
corrections and evidence caveats from this review. The updated plan moves a usable early evidence workflow forward without waiting for those
methods. Its accepted inputs compile to the current MAVT project; sorting/uncertainty remain later.

## Sources

Earlier proposal’s source list, recorded as searched on 2026-10-26 (not comprehensively
revalidated in this review):

- [Analytica: Best multi-criteria decision-making software, 2026 comparison](https://analytica.com/blog/best-multi-criteria-decision-making-software-2026-comparison) (vendor-written)
- [Analytica: Best decision analysis software 2026](https://analytica.com/blog/best-decision-analysis-software)
- [MCDA software in healthcare priority setting: a systematic review](https://link.springer.com/article/10.1007/s40273-019-00863-9)
- [MCDM software products: comparison and ranking in terms of usability and functionality](https://www.researchgate.net/publication/303848580_Multi-Criteria_Decision_Making_Software_Products_-A_Comparison_and_Ranking_in_Terms_of_Usability_and_Functionality)
- [Widely used MCDA methods: a comprehensive ranking](https://doi.org/10.3390/app16147269)
- [pyDecision: a library of MCDA methods with an LLM](https://arxiv.org/pdf/2404.06370)
- [pyrepo-mcda documentation](https://pyrepo-mcda.readthedocs.io/en/latest/)
- [JSMAA on GitHub](https://www.github.com/tommite/jsmaa)
- [Stochastic ordinal regression for multiple criteria sorting problems](https://pure.eur.nl/en/publications/stochastic-ordinal-regression-for-multiple-criteria-sorting-probl/)
- [Deck of Cards method for hierarchical, robust and stochastic ordinal regression](https://arxiv.org/pdf/2405.04313)
- [DecideIT 3.0: software for second-order based decision evaluations](https://mlanthology.org/isipta/2019/danielson2019isipta-decideit)
- [A second-order-based decision tool for evaluating decisions under severe uncertainty](https://pure.iiasa.ac.at/16170)
- [Data-driven preference learning methods for sorting problems with multiple temporal criteria](https://arxiv.org/abs/2309.12620)
- [Preference learning for multi-criteria sorting with interacting criteria (attention network)](https://www.sciencedirect.com/science/article/pii/S1566253525005160)
- [Deep preference learning for MCDA](https://www.sciencedirect.com/science/article/abs/pii/S0377221722005422)
- [Learning MR-Sort models from non-monotone data](https://arxiv.org/pdf/2107.09668)
- [Multiple criteria sorting models and methods, part I: survey](https://orbi.umons.ac.be/bitstream/20.500.12907/47566/2/Review_sorting_4OR_Part_1.pdf)
- [Predicting the success of startups using a machine learning approach](https://link.springer.com/article/10.1186/s13731-024-00436-x)
- [CNN-based deep learning for multiclass prediction of fintech startups](https://link.springer.com/article/10.1007/s41060-025-00999-2)
- [Beyond failure rates: startup success factors with machine learning](https://link.springer.com/article/10.1007/s42001-025-00398-4)
- [Predicting startup success using LLMs: an in-context learning approach](https://arxiv.org/html/2601.16568v2)
- [LLM graph reasoning for venture capital prediction](https://arxiv.org/html/2512.23489)
- [Large language models in MCDA weight elicitation: a systematic review](https://link.springer.com/chapter/10.1007/978-3-032-25146-6_17)
- [LLMs as virtual experts for AHP criteria weighting](https://www.sciencedirect.com/science/article/abs/pii/S0957417425037868)
- [LLM multi-agent simulation for Best–Worst Method weight elicitation](https://www.mdpi.com/2076-3417/16/12/6093)
- [Integrating AHP with LLMs for transparent MCDM](https://arxiv.org/pdf/2609.16779)
- [RAND: Making good decisions without predictions (robust decision making)](https://www.rand.org/pubs/research_briefs/RB9701.html)
- [Decision making under deep uncertainty (open access)](https://library.oapen.org/handle/20.500.12657/22900?show=full)
- [US Fish and Wildlife Service: overview of structured decision making](https://www.fws.gov/course/overview-structured-decision-making)

## 6. Review recommendation and technical corrections

The current recommendation is **A verify → B install/start reliably → C1 essential recovery → D
small live canvas → bounded visual/evidence/method packages**. Design and implementation can
overlap where their gates permit; all resilience features need not precede visual work. The
recorded AHP/PROMETHEE order remains in force. The earlier sorting-first argument remains above
as the history of the trade-off, not the active method sequence. No release versions or dates
are promised. See the roadmap for the fresh-decision user checkpoint.

- A MAVT objectives/value tree is not a sequential decision tree or influence diagram. Keep
  alternatives outside its hierarchy and do not introduce chance-node imagery.
- A small evidence intake/review/compile/dossier workflow can help an analyst now. Preserve source
  excerpts/locations, conflicting claims, acceptance history and transformations; missing inputs
  remain missing. Confidence is independent of performance. Correlation alone does not establish
  double counting; review conceptual overlap and shared evidence.
- Sorting should start with numeric boundaries. Profile boundaries can cross/coincide when
  weights or scenarios change; invalid order needs explicit diagnostics, invalid sensitivity
  intervals and a simulation policy, never silent class-label reordering.
- An interval is a feasible bound, not a distribution. Uniformity and independence are assumptions.
  Distinguish uncertain performances from uncertain preferences. Monte Carlo frequencies describe
  specified sampling measures; they are neither startup-success probabilities nor proof over all
  admissible models. Tie conventions and nonzero uncertainty bounds after zero observed events
  must be specified. The author's [SMAA manual](https://gertvv.r-universe.dev/smaa/doc/manual.html)
  explicitly describes probability-distribution integration.
- Reproducibility requires sampler/engine versions and a supported numeric environment, not seed
  alone; see [NumPy stream compatibility](https://numpy.org/doc/stable/reference/random/compatibility.html).
- SMARTER validates reuse of MAVT weighting, not general method/result dispatch. AHP needs its own
  interface test and mathematically valid oracles. Geometric-mean and eigenvector priorities can
  disagree; different implementations with shared assumptions do not alone establish correctness.
- Numerical compatibility can survive migration while bytes, added fields, fingerprints and
  record digests intentionally change. Preserve old records and their provenance rather than
  rewriting them to look current. See the roadmap's compatibility policy.

Only material technical claims used in this revision were checked against primary documentation;
the earlier competitor source list was not comprehensively revalidated. Treat its broad capability
counts and research conclusions as discovery leads until a focused primary-source check is done.
