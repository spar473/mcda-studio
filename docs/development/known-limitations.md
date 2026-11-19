# Known limitations and roadmap

MCDA Studio is a complete, tested **local additive MAVT** application within the operating envelope
below. This page lists what it does not do yet, ordered by priority, and the proposed next steps.
Mathematical limits of the method itself are in
[method limitations](../mathematics/method-limitations.md).

## Supported operating envelope

| Area | Supported |
| --- | --- |
| Users | One local user, one server per project library |
| Network | Loopback only (`127.0.0.1`), no authentication, no CORS |
| Method | Additive MAVT with hierarchical swing weighting; value-based sorting of its values into ordered classes; SMAA-2 acceptabilities under stated measurement and weight uncertainty; PROMETHEE II net outranking flows with the PROMETHEE I partial order and an explanation against MAVT; AHP priorities from pairwise judgements; a view comparing every method's reading side by side |
| Size (results/exports) | 100 alternatives, 100 leaves, 1,000 nodes, 10,000 measurements |
| Browsers | Automated in Chrome. Firefox and an embedded browser were checked by hand |
| Python / Node | Python 3.12+, Node 20.19+ (tested on Python 3.12.15, Node 26.12.1) |

## Limitations

| Priority | Limitation | Current handling |
| --- | --- | --- |
| Important | Advisory POSIX library ownership; no authentication | Cooperating servers/CLI writes are coordinated; external programs can bypass locks. Verified on macOS and on hosted Ubuntu 24.04 CI. Windows is unsupported: library writes and `serve` refuse on non-POSIX systems. Keep loopback only |
| Important | Unsaved drafts and undo history are session-only | Leave/refresh guards, explicit Save, conflict choices and backups. Durable draft recovery needs its own design |
| Enhancement | Retry covers analysis requests, not previews | Results, the scoped analysis check, sensitivity (sweep and probe) and scenario comparison offer Retry; Weights, value-function and canvas-weight previews re-request on the next edit; Save has its own retry |
| Method | Feasibility requirements test one measurement each | A requirement is a bound or a set of allowed labels on one leaf; requirements on combinations of measurements, soft constraints, penalties and probabilistic feasibility are excluded. Limits are compared exactly in the leaf's own unit, with no conversion ([design](../design/feasibility-check.md)) |
| Method | Feasibility never filters a ranking | Failing alternatives keep their place in every method's ranking, flagged beside it; there is no "rank only feasible alternatives" option. Read the status beside the ranking |
| Compatibility | A project with requirements is schema version 6 | Older versions refuse it; removing the requirements returns it to the version it needed before |
| Recovery | Successful restores retain recovery entries | Recently deleted supports original-ID restore or new-ID copies, without overwrite. No permanent purge; see the manual recovery drill |
| Recovery | Backups are manual, offline and unsigned | `mcda library backup/verify/restore` archive a stopped library and restore into a new folder. No scheduled or online backup; the manifest detects damage, not deliberate tampering; backup holds the files in memory up to its 4 GiB limit ([design](../design/library-backup-and-restore.md)) |
| Distribution | GUI/examples now bundled; API extra remains explicit | Use `wheel[api]`; source-checkout overrides remain supported. Both wheel routes and isolated pipx passed the installed smoke locally (macOS) and on hosted Ubuntu 24.04 CI; other platforms and Python versions are not claimed |
| Distribution | Public requirements are ranges; checks use Python 3.12 hash locks | Separate runtime/dev/build locks retain baseline numerical versions; broader Python/platform coverage is not claimed |
| Important | OpenAPI does not declare every non-422 response | The full error table is in the [API contract](../api/contract.md#errors) |
| Important | Larger Weights previews enumerate every range | Measured at 117 ms for a 50 × 40 model. Optimise only when larger workloads need it |
| Important | CSV repeats provenance and can be larger than JSON | 16 MiB download bound with an explicit error; JSON is the exact, compact record |
| Important | Sampled browser and accessibility coverage | Keyboard tables, labelled controls, visible focus, narrow and zoom checks. No Safari support claim, no screen-reader or WCAG audit |
| Method | Compensation and preferential independence cannot be checked automatically | They are modelling judgements. The assumptions and range warnings are shown in the app |
| Method | Value-based sorting uses numeric boundaries only | Boundaries are fixed numbers on the overall value, shared by every scenario and profile. Boundaries set by reference alternatives, per-scenario boundaries, learnt boundaries and ELECTRE TRI are not offered ([design](../design/value-based-sorting.md)) |
| Method | Classes are not compared between Base and a scenario | Scenario comparison stays values and ranks; switch the scenario to read its classes. A side-by-side class comparison is a candidate for the method comparison view |
| Method | SMAA-2 samples independent inputs, or inputs sharing one draw, from uniform, triangular and discrete distributions only | No correlation, copulas, MCMC or distributions inferred from data; no central weights or confidence factors; no proof that a conclusion holds for every weight. Since 16 November 2026 the arithmetic is portable: the same NumPy version gives the same bits on Linux and Windows (checked) and on a Mac (checked 16 November: the pinned digests match and all 969 historical outputs are byte-identical to Linux's); another NumPy version may draw a different random stream. Every result still records its environment ([design](../design/portable-outputs.md)) |
| Method | SMAA-2 has no sensitivity or scenario comparison, and its GUI run settings are not saved | Switch the scenario or profile to rerun; set saved parameters through the CLI or API |
| Compatibility | A project with stated uncertainty is schema version 3 | Older versions refuse it; removing the uncertainty returns it to the version it needed before |
| Method | PROMETHEE II offers the usual, U-shape, V-shape and linear preference functions only | No level or Gaussian function, no PROMETHEE III–VI and no GAIA. Weights are flat leaf weights normalised by their sum; there are no PROMETHEE weight profiles, scenarios or input uncertainty ([design](../design/promethee-ii.md)) |
| Method | PROMETHEE II has no sensitivity or scenario comparison | Its explanation compares orders with MAVT under the selected profile and scenario; change them to compare again. The explanation is omitted, with MAVT's issue codes, while MAVT's model is invalid |
| Method | PROMETHEE II's explanation details at most 50 pairs | Every pair ordered differently lists its gaps; criterion detail and reasons are given for the 50 with the largest rank changes, and a diagnostic says so |
| Size | PROMETHEE II computes at most 10⁶ preference degrees (alternatives² × leaves) per request | The results limits' worst case; about 1.2 s at 100 alternatives × 100 leaves on the development machine |
| Compatibility | A project with PROMETHEE inputs is schema version 4 | Older versions refuse it; removing the inputs returns it to the version it needed before |
| Method | AHP is the full method only, with at most 15 items per matrix | No weight-elicitation view, ratings mode, group aggregation, incomplete-matrix completion or ANP. The random-index table (Saaty and Tran 2007) covers 1 to 15 items, so a project needs at most 15 alternatives and 15 children per group for AHP ([design](../design/ahp.md)) |
| Method | AHP distributive synthesis can reverse two alternatives when another is added or removed | A known property, stated in every result; ideal synthesis (`synthesis: ideal`) keeps each leaf's best at 1. Consistency is a warning above 0.10 and is never repaired |
| Method | AHP has no sensitivity, scenarios or weight profiles | AHP reads only its own judgements; the profile and scenario selectors do not change its priorities |
| Compatibility | A project with AHP judgements is schema version 5 | Older versions refuse it; removing the judgements returns it to the version it needed before |
| Method | The method comparison compares leading alternatives and classes only | No rank correlation, consensus or aggregated score; one profile and scenario at a time; each method runs with its saved parameters only when it is the saved method, otherwise its defaults. It runs every method, so its cost is their sum (about 1.6 s on the 50 × 40 performance fixture) ([design](../design/method-comparison.md)) |
| Compatibility | A project with classes is schema version 2 | Older MCDA Studio versions refuse it with their "newer than this program" message; removing the classes returns it to version 1. MAVT-only projects are unchanged |
| Data | The venture screening study rests on public information read once, on 4 November 2026 | 71 of 112 rubric ratings are the author's judgements; most sources are company-published; 33 claims are older than a year. Market sizes are the median of disagreeing publisher estimates. Not validated against outcomes and not investment advice ([study](../../examples/nz_venture_screening/README.md)) |
| Method | The screening summary's closest change varies one weight at a time | It is the smallest one-way change of a criterion's global weight that moves a rank or class, not robustness over every combination; zero-weight criteria are not varied; above 50 criterion nodes the column is skipped. The summary is not exported ([design](../design/screening-summary.md)) |
| Enhancement | The starter lineage receipt calls every starter's carried values invented | True for the invented starters, not for the real-company study; the gallery no longer repeats it, but the receipt is an export body and changing it is an owner decision |
| Data | The VC example's Market Size control points are rounded in the source | Printed inputs are kept, and the tests use the rounding interval. No hidden precision is invented |
| Method | What-if weights are a slim, session-only trial | Only the four stated top-level scored raw ratings of a MAVT or value-based-sorting view can be varied; only the Results screening summary and ranking chart re-rank. It never projects evidence, edits a rating or source, or saves a profile; the open-question column is hidden and the company detail, Sensitivity, partner comparison and all analysis, SVG and factor-run downloads show a Reset message until Reset. Saving a trial as a profile is deferred |
| Method | Profile comparison is two profiles at a time | Separate screenings under each profile with engine rank movement; there is no combined ranking, and other methods are labelled as a MAVT comparison |
| Method | The closest-change values are one-way and make no prediction | Each is the smallest single-weight change that alters a class or neighbour; none is a probability, a robustness region over all weights or a forecast of company success |
| Data | The screening-summary fixture compares floats only up to six named fields | `frontend/tests/fixtures/screening-summary.json` is regenerated in a temporary location and compared exactly (structure, types, keys, ids, ranks, classes, statuses, counts and strings); only finite floats at `rows.*.value`, `rows.*.margin`, `rows.*.drivers.*.contribution`, `rows.*.fragility.base_local_weight`, `.local_weight` and `.weight_change` are excluded, so a different platform's last-digit float differences do not fail it |
| Important | Showcase checks ran on one platform | macOS arm64, Python 3.12.15, NumPy 2.5.4 and Chrome. No Linux, Safari, screen-reader or human usability run is claimed |
| Enhancement | No heatmap SVG, no PNG/PDF reports, one scenario compared at a time | JSON, CSV and three SVG chart types are available |
| Important | The blind rater kit cannot represent labels made before the protocol freeze | The author rated on 4 November 2026. The benchmark requires human review times inside its frozen window, so `scripts/rater_kit.py author-labels` stamps the author's rows with the freeze time and the manifest description records the real date. The benchmark was not changed. With eight companies as bootstrap groups the agreement interval will be wide, so the gate may refuse; that is the benchmark working as designed ([design](../design/blind-rater-kit.md)) |
| Enhancement | The screening report is a snapshot, and its closest change is one-way | It is one self-contained HTML file for sharing, not a decision record: no rationale or review history. Each closest change moves one weight at a time. Its fixed statements are neutral; a study's own conditions (whose information, whether anyone was contacted) appear only because the project's description or a note file says so, so a project with no such description prints none. Its judgement-only count relies on the documented convention that a judgement claim's source description starts "Judgement", and reports none for a dossier that does not follow it. No chart or PDF is produced; print to PDF from a browser ([design](../design/screening-report.md)) |
| Important | The typed-proposal runner's first real model run is unevaluated | The free local model (`Qwen/Qwen2.5-1.5B-Instruct`) answered all 112 venture-study questions in three completed runs on 7 November 2026, and its proposals import and preview in the application with no change. That is not an accuracy result: nothing was compared with the study author's ratings or any human label, the runs differ from one another in many cells, and averaging over option orders cancels a letter-position preference in the average without making the probabilities calibrated. A fourth run was stopped for lack of memory. The `laya` backend was implemented on 16 November 2026 against the installed package's source and tested only with a fake `laya` module; its first real runs are recorded separately, and the `jev` client has been run only against a local mock of the documented endpoint ([design](../design/typed-proposal-runner.md)) |
| Important | Model output is a proposal, not a measurement, and its confidence is not calibrated | Every proposal needs a person's review. Probabilities are the model's own, uncalibrated, and metadata only. Nothing compares a model with the study author's ratings until a second human rater has labelled the cells and the benchmark's agreement gate has passed |
| Enhancement | Snapshots are private copies taken after the study's as-of date | The pages were fetched politely, not redistributed, and may differ from what the author read on 4 November 2026. A page behind a login, paywall or a robots.txt refusal is skipped (one page of the venture study's 41 was refused by robots.txt), and a page that needs JavaScript yields little text |
| Enhancement | The name-swap check shows sensitivity to names, not correctness | `compare-runs` reports which answers changed when listed names were swapped; it neither says which set of answers is right nor finds names itself. The owner supplies the swap list, and no real list is committed ([design](../design/name-swap-check.md)) |
| Enhancement | Option-order averaging removes position bias from the average, not miscalibration | A local model's probabilities are averaged over every cyclic order of the options, so a preference for a letter position cancels; the averaged probabilities are still the model's own, uncalibrated, and `order_top_agreement` (how often the rotations agree with the average) is a stability figure, not accuracy. `--order-averaging none` exists for comparison only ([design](../design/typed-proposal-runner.md#amendment-option-order-averaging-and-cleaner-page-text)) |
| Enhancement | The version-2 page text filter is a heuristic | `reextract` drops repeated lines and short lines shared with another page of the same host; it can drop a genuine short line that happens to repeat across a site and keeps long boilerplate that appears once per page. Version 1 is kept beside it, and the questions record which was used |
| Important | Decision impact checks one cell at a time, not combinations | Each labelled cell is varied alone with everything else fixed, so two ratings moving together can change a result that neither changes alone. It does not say a rating is wrong or how likely a change is, covers only qualitative and ordinal cells with positive weight (numeric cells have the measurement-range questions), and its reasons depend on the dossier convention that marks judgement-only claims ([design](../design/decision-impact.md)) |
| Important | Reference cases describe similarity of ratings, not prospects | Similarity is one minus the mean label gap over the labelled criteria with positive weight that both sides rated, at each case's snapshot date. Numeric criteria are not compared (version 1); every compared criterion counts equally unless profile weighting is chosen; a case sharing fewer than half the compared criteria is not ranked. The snapshot guard checks the dates of the sources a rating cites, not whether a claim was knowable then, and a reference set's author usually knows the outcomes when rating. A small set is not representative and public sources under-report cases that closed ([design](../design/reference-cases.md)) |
| Data | The first-round retrospective ranks on a thin public record | Since 14 November 2026 (owner decision) the 39 cells its sources are silent on carry the rubric's lowest "nothing public" label or a sector judgement, as the venture study does; a thin record therefore lowers a score, which biases against companies that later closed (Argo Navis has 7 absence-rule cells). Ranks 2 to 5 change if a single absence-rule cell moves one step. Argo Navis's stage uses one window exception (a 2023 report of its 2020 round). Windows run from 12 months before each anchor through 180 days after it, so some inputs describe post-round progress. Market segments are broad for Vertus, RosterLab and Argo Navis; Argo Navis and Helico have only one paired publisher estimate. The same companies are the reference cases; leave-one-out (`exclude_same_id`) removes self-matches. Ratings were drafted with hindsight, author review pending; five selected cases cannot establish prediction ([design](../design/first-round-study.md)) |
| Research | No authorised DECERNS installation has been examined | Not a release blocker. DECERNS compatibility is not claimed (research note, not included) |

## Roadmap (proposed, not started)

The direction, order and work-package acceptance criteria are in the roadmap (not included).
The code-backed plan (development record, not included) keeps the detailed specifications; its
baseline review (development record, not included) distinguishes checks rerun then from historical
claims. Implemented so far: installation and startup (development record, not included), library
ownership and recovery with its manual recovery drill (development record, not included), the
[visible model](../design/live-model-canvas.md) (development record, not included),
analysis retry (development record, not included), measurement coverage
(development record, not included), library backup and restore
(development record, not included), the method seam
(development record, not included), value-based sorting
(development record, not included), SMAA-2 (development record, not included), PROMETHEE II
(development record, not included), AHP (development record, not included), the method comparison
view (development record, not included) and the feasibility check
(development record, not included). Coverage shows only whether a measurement was
entered; integrated evidence provenance and the human usability and screen-reader checkpoints remain pending.

Evidence has a graphical review, compilation and export workflow with retained history, a
support audit and reproducible bundles; imported copies are related to bundles through unsigned
copy receipts, which must be downloaded at import time. Version-2 decision records cite those
bundles and trace measurements to them; records are unsigned exported files with no browser or
library storage, and the CLI still writes version 1.
Open Questions includes fixed-anchor measurement-range crossings, with analytical
boundary contacts and engine-evaluated witnesses; it does not propagate shared factors or establish
global robustness. Derived measurements support graphical authoring and review in a calculation
workspace, application to the open project as one undoable edit, separate static copies and
reproducible calculation bundles. Formulas live in the exported workspace file, not in the project;
there is no autosave, merging of workspaces or rebinding across project IDs, and uncertainty
propagation remains.
Support auditing concerns the supplied dossier and current entered measurements; propagation of
evidence support through formula inputs into decision records remains outstanding.
A fresh-user checkpoint is pending
a participant. No human usability checkpoint has passed yet.

Independent numerical reference checks remain release gates. Authorised DECERNS behavioural
comparison is separate research, not a dependency of the application roadmap.
