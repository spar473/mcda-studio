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
| Method | SMAA-2 samples independent inputs, or inputs sharing one draw, from uniform, triangular and discrete distributions only | No correlation, copulas, MCMC or distributions inferred from data; no central weights or confidence factors; no proof that a conclusion holds for every weight. Repeatability is promised only in the same environment (Python, NumPy, platform), which every result records |
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
| Data | The VC example's Market Size control points are rounded in the source | Printed inputs are kept, and the tests use the rounding interval. No hidden precision is invented |
| Enhancement | No heatmap SVG, no PNG/PDF reports, one scenario compared at a time | JSON, CSV and three SVG chart types are available |
| Research | No authorised DECERNS installation has been examined | Not a release blocker. DECERNS compatibility is not claimed |

## Roadmap (proposed, not started)

The direction, order and work-package acceptance criteria are in [ROADMAP.md](../../ROADMAP.md).
The code-backed plan (historical record, not included) keeps the detailed specifications; its
baseline review (historical record, not included) distinguishes checks rerun then from historical
claims. Implemented so far: installation and startup ([checks](package-b-verification.md)), library
ownership and recovery with its [manual recovery drill](library-recovery.md), the
[visible model](../design/live-model-canvas.md) ([checks](package-d1-verification.md)),
analysis retry ([checks](analysis-retry-verification.md)), measurement coverage
([checks](measurement-coverage-verification.md)), library backup and restore
([checks](library-backup-verification.md)), the method seam
([checks](method-seam-verification.md)), value-based sorting
([checks](value-based-sorting-verification.md)), SMAA-2 ([checks](smaa-2-verification.md)), PROMETHEE II
([checks](promethee-ii-verification.md)), AHP ([checks](ahp-verification.md)), the method comparison
view ([checks](method-comparison-verification.md)) and the feasibility check
([checks](feasibility-check-verification.md)). Coverage shows only whether a measurement was
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
