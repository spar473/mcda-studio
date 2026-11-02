# Disclosed model proxy criterion: verification

2 November 2026. Implements the [accepted design](../design/disclosed-model-proxy-criterion.md).
The pre-Part-B baseline (historical record, not included) remains the numerical/export reference;
the [market-models record](market-research-models-verification.md) is the preceding development.
The [owner's arithmetic contract](../design/derived-measurements.md#arithmetic-contract) applies.

**Implemented and locally verified.** All ten application-gate commands, the complete mutation
campaign and unmodified controls, original-output byte comparison and offline installed-package
checks passed. All existing test tolerances, arithmetic and independent oracles remain unchanged.

## Implemented boundary

New version-1 disclosure-plan, inputs and paired-comparison sidecars retain the original project,
immutable proposal intake and review events, exact card/digest, distinct tool-wrapper/model versions, feature/source declarations,
explicit overlap resolutions, analyst swing ratings, review history and both analysis copies.
Published schemas are `docs/schemas/proxy-plan-v1.schema.json`, `proxy-inputs-v1.schema.json`
and `proxy-comparison-v1.schema.json`. No old project, sidecar or result schema changes. The only
earlier API schema addition is an optional proxy input to the Open Questions request; its result
schema is unchanged. Engine arithmetic, the interpreter and factor sampler are unchanged.

Plans begin disabled and without carried reviews. Every append-only revision names its reviewer,
records a timezone-aware supplied time and reason, and chains to the previous digest. Declaration
edits clear reviews, score binding and activation. Score rebinding and further disclosure reviews
invalidate the complete-plan acceptance and activation. Exported history is replayed, never
trusted merely because it contains an acceptance flag. Unknown versions and fields are refused.

One visibly labelled new `disclosed_proxy_` criterion is inserted under the declared root/group in
a separate copy. Existing proxy-role IDs cannot be hidden by changing a display name. The original
without-proxy project and configuration retain their serialized bytes. Each compared profile needs
an explicit nonnegative swing rating, including an explicitly entered zero; no nonzero rating is
prefilled. Original sibling ratings remain intact. Before/after normalized global shares are shown
for every compared profile, with ordinary scenario/profile precedence.

The private score-review draft is exported before importing/reviewing numeric proposals against
its exact fingerprint. One accepted or corrected fixed numeric score per alternative is required;
competing accepted scores, stale bindings, absent cards/sources and mismatched model versions block
activation. Feature observation dates bind into the exported draft fingerprint; a changed date
requires new proposals/reviews against the new draft. Every score becomes a reviewed fundamental factor and an identity formula in an
ordinary calculation compilation. Raw confidence metadata remains retained but analytically unused.
The human dossier remains a retained comparison, following the existing proposal compiler policy;
its historical accepted reviews are preserved rather than silently rewritten or averaged. Only
the explicitly selected tool measurements supply the proxy. Supporting assertions without a
measurement remain retained and do not become additional numeric scores. No external model is
run and no reference is fetched.

All required model-card facts need sourced, explicit reviews. Reviewed unknowns require a reason,
remain visible limitations and need a separate acknowledgement. Unknown or incompatible licence
and use restrictions always block. Features retain stable IDs, descriptions, source lineage and
observation dates. Known cutoffs and run dates constrain observation dates. Shared criterion/factor
IDs produce a visible warning; text-only declarations require review, without semantic guessing.
Every feature needs an explicit reviewed overlap resolution. Baseline-only resolutions block proxy
runs. Explicit removals preserve an additional identified model; removal cannot erase a feasibility
requirement or the chosen proxy parent.

MAVT, value-based sorting and fixed-weight fundamental-factor SMAA-2 pairs are supported. The proxy
score is fixed. The original factor run reproduces byte for byte; both halves reuse the same
non-proxy factor identities, seed and sampling path. A separate count/hash covers every non-proxy
factor realization, including draws beyond the retained trace. Existing unsupported uncertainty
combinations still refuse. PROMETHEE II/AHP paired runs explicitly retain two unavailable halves.
Ordinary method comparison remains independent.

Every pair retains both projects, configurations, calculation bundle and completed results or
failed-half reasons. One failed half makes the complete pair unavailable, preserving the successful
half and the failed copy rather than publishing a favourable result alone. Feasibility badges are shown in each aligned ranking row, with complete requirement checks
available below; the proxy never satisfies an existing requirement. No consensus, average,
model-confidence weight or outcome probability is computed.

## Workflows and context guards

Compare contains an off-by-default retained proxy workspace. Declaration editing uses JSON;
individual card/feature/overlap/licence reviews are explicit typed actions. The existing proposal
reviewer handles the separate score draft. Before running, the analyst reviews the complete plan,
enables the preview and acknowledges card, overlap, changed shares and any unknown facts.
Unrecorded declaration edits block running. Context generations invalidate paired candidates and
acknowledgements permanently, including when returning to an earlier profile. Late responses cannot
publish into another project/profile/scenario or edited declaration. Pending exports join the
existing Save/leave guard; tab changes retain the workspace. Exports include both project copies,
complete pair and original input/review history. Historical reopening performs complete replay.

CLI `proxy start`, `revise`, `inspect`, `preview-pair`, `run-pair` and `verify` share the stateless
service and HTTP operations under `/api/proxy/`. Exclusive CLI outputs never overwrite a file.
Stale preview/review digests use the existing 412 `STALE_REVISION`. Open Questions reports pending
card, overlap and licence work, and retains explicitly unknown facts as limitations.

## Numerical checks and mutant reachability

The independent `tests/regression/proxy_oracle.py` imports no application module. It reconstructs
both trees, scores, sibling normalization and path shares from declared source inputs, plan edits
and accepted/corrected proposal payloads, rather than engine-materialized measurements. It uses
exact decimal `Fraction` values and the
independently derived bounds in `rounding_oracle.py` (Higham, second edition, §2.2). Dyadic fixtures
assert exact equality; decimal fixtures assert that the binary64 result lies inside the propagated
bound, and reject a one-percent error. The formula mutant is separately run against the decimal-only case and fails the
forward-bound assertion; its unmodified control passes. Hierarchical insertion, scenario precedence and existing
sorting boundary/tie rules are pinned. The original advertised method tolerances are unchanged.

Engine-to-engine tests use exact serialized equality for the baseline project/result, original
complete factor record, HTTP/CLI/service parity, replay and confidence invariance. Sampled discrete
factor rows must equal enumerated rows exactly. Both fixed proxy scores remain identical across
all draws. Generated-input properties also verify confidence invariance and the disabled baseline
over varied measurements/ratings (twelve examples each). Feasibility remains typed through browser
number normalization; a proxy-favoured alternative cannot offset a failed requirement. The coupling digest covers the complete run, not just the first sixteen rows.

Each new Python mutation has a unique source anchor and parses before injection. The focused
runner reports the assertion reached, and refuses to count a collection/infrastructure failure as
a kill. The complete campaign also checks the unmodified copy and every earlier formula mutant.

| New mutant | Reachable check |
| --- | --- |
| Silently activate disabled plan | A complete reviewed plan remains explicitly disabled; run must refuse |
| Use confidence as a swing weight | Change only confidence, rebind/review, require both projects/results byte-identical |
| Hide a failed half in overall status | Baseline completes; proxy score exceeds its fixed value-function domain; entire pair stays unavailable |
| Drop the original baseline | Original project/result serialized equality and independent reconstruction |
| Ignore baseline-only overlap | Every disclosure is reviewed and activation explicit; this resolution must still block |
| Change shared draws | Shift only the with-proxy seed; every-draw coupling and original-record reproduction must fail |
| Change the identity formula score | Independent exact dyadic values and decimal forward bounds |
| Replace explicit zero swing with nonzero default | Proxy remains present at exactly zero weight with unchanged values |
| Ignore unknown-fact acknowledgement | A reviewed unknown calibration fact blocks until separately acknowledged |
| Ignore preview revision | Otherwise valid request with stale digest returns the existing stale-revision refusal |
| Count a supporting assertion as a numeric score | An accepted assertion without a measurement remains retained but must not block the one selected numeric score |
| Hide failed feasibility beside a preferred rank | The rank table must show the failed requirement beside the favoured option |
| Let proxy preference offset a failed requirement | The proxy-favoured alternative must retain its failed feasibility status in both halves |
| Reuse old scores after an observation-date change | Change only a declared feature date; the exported review draft fingerprint changes and the old reviewed workspace must refuse |
| Permit stale feature-factor model links | The factor declaration has a different project fingerprint; even a deterministic pair must refuse |
| Ignore licence restrictions | Reviewed incompatible/unknown licence/restrictions remain blockers |
| Skip UI acknowledgements | All other inputs valid; each missing acknowledgement disables running |
| Misattribute a late pair to the current context | Deferred pair resolves after a profile change and must never become current |

An early optional late-response mutant removed only the response guard but retained the original
candidate key. That mutation remained hidden by the independent key check. The campaign now models
an actual misattribution fault by publishing the late response under the current key. The strengthened
suite also returns to the prior context and requires invalidation, and checks unrecorded edits.
No formula mutant survived either the focused checks or the complete campaign. Every earlier
formula mutant remains caught under the unchanged and strengthened verification boundary.

## Gate, packaging and compatibility evidence

| Check | Result |
| --- | --- |
| Full Python suite | 1,916 passed in the complete suite |
| Frontend | 451 tests in 57 files passed |
| Browser | 113 passed in the complete browser suite |
| Mutations | 335/335 caught: 255 backend, 80 frontend; unmodified copy passes |
| Original numerical/export outputs | 969/969 byte-identical against the original pre-Part-B manifest |
| Python lint/format and strict typing | Passed, 238 formatted files and 105 typed source files |
| API/types and published new schemas | Current; old project/sidecar/result schemas unchanged |
| Offline installed package smoke | Passed: both wheel routes, isolated command install, installed GUI and all starter manifests |
| Installed proxy CLI/API/replay | Passed outside the checkout; entire paired output exactly equals the service fixture |

Direct and source-rebuilt runtime wheels are byte-identical, SHA-256
`85afa638e1b94dff05f1de5674a70060d8a32fc31a33814bcffbefc28d003ef4`.
The source archive has SHA-256
`555c130e92427baf12fc21b701a37ae449fe8d860ec6a93e7f97e3291f869545`.
The final source archive includes the independent hierarchy/scenario/near-tie checks and the
verification-runner reachability evidence. Both installed wheel routes, the isolated command
install, GUI and final installed proxy CLI/API replay pass. Dependencies came
from the existing hash-verified local wheelhouse, with no external network. No push or publication.
The original historical example files and existing arithmetic modules have no diff from `f80a6f6`.

## Limits

This mechanism reviews supplied fixed scores; it does not train, execute, calibrate or validate an
external model's claims. Human review statements are local provenance, not authenticated signatures.
Disclosure/feature authoring uses JSON alongside typed individual review controls. No usability
claim or new human checkpoint is made. Files/history require explicit export; they are not library
autosave. Only one proxy, fixed proxy scores and the three stated paired methods are supported.
Conservative factor support guards and original finite-work limits still apply. Removal requires
explicit linked criteria and preserves feasibility constraints. Other uncertainty combinations and
method-specific paired semantics remain excluded as accepted. Hosted CI is not claimed for unpushed
local changes. The later study supplies the full invented screening workflow.


This development adds **52 Python tests, six frontend tests, three browser tests and eighteen
mutants** over Market models. Against the pre-Part-B baseline, totals rise from 1,755 to 1,916
Python, 430 to 451 frontend, 103 to 113 browser and 286 to 335 mutations. All 969 earlier output
bodies and twelve complete earlier factor records remain byte-identical. The original historical
example and the existing expression interpreter/factor-sampler files have no diff from the
pre-Part-B commit. Earlier unsuccessful new-code/test checks were corrected without changing any
existing test expectation, tolerance or oracle. The new browser test waits for the preview before
editing review metadata; the stale-response protection remains enabled.

Local gate timings: 68.57 s, 40.45 s, 248.73 s, 1436.88 s for Python, combined frontend, browser and the complete mutation campaign respectively. These are local observations, not performance promises. Hosted CI has not run these unpushed changes.
