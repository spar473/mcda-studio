# Market research models and starter templates: verification

1 November 2026. Implements the [accepted design](../design/market-research-models.md), including
Amendment B. The pre-Part-B baseline (historical record, not included) remains the comparison
reference. The historical checkpoint (historical record, not included) records the new
point-mass test-specification error; the owner resolved it with the
[arithmetic contract](../design/derived-measurements.md#arithmetic-contract), recorded separately
in `3826bdd`. Engine arithmetic and all existing tolerances/oracles remain unchanged.

**Implemented and locally verified.** The complete application gate, original-output byte
comparison and final offline installed-package smoke passed.

## Implemented boundary

New version-1 `ModelChecks`, `ModelComparison`, output-run, checked-run, comparison-compilation,
starter-manifest and materialization/lineage formats remain separate from project schemas and old
sidecars. [Published JSON schemas](../schemas/model-comparison-v1.schema.json) and generated API
contracts expose typed versions; unknown versions and fields are refused. Existing project,
sidecar and result schemas match the original baseline. Only `OpenQuestionsRequest` gains optional
proposal/model inputs. No old result type, interpreter or factor-sampler arithmetic changes.

The checked-run envelope retains the unchanged factor record. Internal optional validation hooks
leave ordinary runs unchanged; twelve captured complete earlier factor records match byte for
byte. New quantity checks bind to the exact project/model/check digest and exact unit/kind/ID.
They check deterministic values and conservative supports before sampling, then every draw.
Violations abort with the failing draw/quantity; no sample thinning or zero substitution occurs.
Checks are data declarations, never inferred from units, source relationships or template names.

Output runs materialize the selected dependency closure and explicitly declared checks/quantile
groups. Unrelated unfinished quantities are omitted with an ID ledger while the original full
model remains retained. Source-bound runs do not require members of an unused probability group.
This makes missing inputs block only outputs/runs needing them. Shared
factor IDs still have one realization across formulas and alternatives. Units/scaling/conversions
remain explicit. Segment aggregation requires reviewed disjoint populations and a matching sum,
or an explicit used overlap model; duplicated populations cannot silently become disjoint.

Source intervals have no probability semantics. Exact discrete supports enumerate reachable
outputs; conservative enclosures do not claim proven extrema; sampled central 95% ranges retain
seed, draw count, empirical linear quantile algorithm, environment, traces and full-run digest.
The two deterministic values, ranges, factors, classifications, dates, definitions and reviews
remain side by side. A model disagreement persists even with overlapping ranges; incomparable
scope gets a concrete review question. No average, source-quality weighting or materiality cut-off
is calculated. One explicitly reviewed compatible output supplies one criterion cell through the
ordinary separate-copy compiler; the other model remains retained. Stale selection returns the
existing 412 `STALE_REVISION`. Historical bundles reconstruct against their source snapshots.

## Gallery, lineage and packaging

Four manifest-driven gallery items contain actual shipped workflows: Blank, Supplier selection,
Infrastructure procurement and an initial Venture screening starter. The initial screening data
has invented Option A/B classifier review and explicit bottom-up/top-down models, not a claim that
the later five-company study is already present. Its tasks contain no placeholder or coming-soon
item. Titles, domain content and tasks live in data. Legacy structure-only definitions are also
data; ordinary creation keeps its earlier contract.

Fresh projects receive a new ID, keep structural IDs and illustrative input values, clear human
reviews and saved runs, and show a persistent review warning. Worked examples retain the exact
original project and invented history. A receipt records template/version/content digest, source
and created fingerprints, sidecar digests, cleared fields and omitted artifacts. Sources and
original proposal payloads stay illustrative proposals; no old historical compilation is rebound.
Optional unattached simple-round formulas/checks are off by default, never auto-create a criterion,
and disclose all specified exclusions. Range checks prefer fundamental inputs; the examples do
not reach a derived-value check exactly at its boundary.

The loader verifies the manifest and every referenced file hash, canonical local paths, versions,
unique IDs, known kinds and bindings before materialization. It bounds files to 8 MB and total
materials to 32 MB. Hashes are not authenticity signatures. A browser round trip renders `1.0` as
`1`; verification reconstructs the declared sidecar types before hashing, without changing numeric
values. An actual changed value still fails. ZIP export contains the project, receipt, materialization
and individual sidecars. Reopening verifies exact keyed reproduction; an edited library project
with a worked example's ID is never silently replaced.

Wheel and source-archive inspections follow all manifest references and hashes, including the
legacy definitions. The installed smoke instantiates every starter through CLI and API with the
same keyed inputs, verifies lineage outside the checkout and drives the installed GUI. Dependencies
come only from a hash-verified local wheelhouse; no external network is used. The original
`examples/nz_deeptech_vc/` files remain byte-identical.

## Graphical and command workflows

New Project retains its structure-only form and adds the explicit fresh/worked gallery, optional
unchecked materials, lineage reopening and downloads before saving/opening the prepared project.
Calculated measurements shows the two formula graphs, inputs and declared ranges, individual
input reviews, comparison review, target scope and exact before/after cell diff. It requires both
acknowledgements, a reviewer and rationale. Reviewing a deterministic input clears that model's
uncertainty/check reviews and the comparison acknowledgement; later responses and changed targets
cannot publish/export a stale candidate. Model and checked-run exports have separate pending flags
joined to the existing Save/leave guard. Source bounds alone cannot enable a checked factor run.

The corresponding stateless API and CLI provide list/instantiate/verify/archive, inspect/review,
run-output, compile/verify and run-checked/verify-checked. CLI outputs use exclusive creation. Structure-only definitions load from immutable application
data, even when the ordinary examples directory is overridden; a fresh-process regression pins
that earlier startup/creation contract.
Both comparison models and source snapshots remain available when reopening an exported bundle.
Open Questions links the retained disagreement to Calculated measurements. No project data is sent
outside the local app, no reference is fetched, and no external model is run.

## Independent numerical verification and mutant reachability

`tests/regression/rounding_oracle.py` has no application imports. It propagates exact decimal
`Fraction` values and independently derived forward-error bounds under the cited standard model;
division refuses a denominator interval containing zero, and unsupported overflow/subnormal-only
bounds are refused. The unit helper includes the original 1 × .05 × 3 example and excludes a one
percent error. Integers/dyadic cases retain exact equality for each arithmetic formula shape.
Boundary tests pin `0.1 + 0.2 > 0.3` and the resulting inclusive-upper-check failure, with no tolerance.

Point-mass reduction obtains the deterministic reference through the existing compiler and uses
exact equality. Sampled discrete rows must equal enumerated rows exactly. Draw identities also
compare to deterministic compilations of the same realized inputs; independently bounded decimal
formula checks run alongside them. All pre-Part-B tests, tolerances and oracles remain intact. Tiny
supports, segment sums, conversions, source classifications, order invariance, explicit overlap,
missing data and checked ratio domains have direct checks. Browser downloads equal API results
exactly; keyed service/API/CLI materializations and checked runs also match exactly.

UI contract fixtures retain the actual recorded environment labels of their bundled reference
run while testing the current numerical implementation. Their full numeric bodies and digests
remain byte-exact. A simulated ambient system/version change must reproduce those same fixtures
and leave the live environment unchanged. Production run metadata is never overridden.

Every new mutation has one unique injection anchor; Python mutations parse successfully. The
focused isolated campaign caught its initial 17 and its unmodified copy passed; the added
source-bound dependency guard also has an isolated targeted mutation proof. The complete campaign
includes all 18. Relevant paths below are
under `tests/` (component paths are under `frontend/tests/components/`).

| Injected defect | Reachable evidence |
| --- | --- |
| Formula result shifted by one percent | Independent forward-bound assertion in `unit/test_model_comparisons.py`; one-percent rejection in `unit/test_rounding_oracle.py` |
| Duplicate shared-factor draw per alternative | Valid extra factor draws feed target outputs; `properties/test_model_properties.py` compares them to the same-draw deterministic compiler and oracle |
| Average model outputs | Completed overlapping models must retain 600,000 and 1,000,000 separately |
| Infer uniform draws from source bounds | Valid inferred marginal actually samples; source-range test requires zero draws, no seed and no distributions |
| Erase disagreement on range overlap | Both completed ranges overlap; the exact disagreement question must remain |
| Retain old acceptances in fresh copies | Four starter reset cases inspect every carried review and retained/omitted history |
| Ignore template digest | A changed manifest with an unchanged digest must refuse before materialization |
| Template-specific engine branch | An arbitrary new manifest ID must instantiate using the same generic path |
| Ignore quantity-check binding | Valid quantities with a deliberately changed check digest must refuse |
| Add hidden boundary tolerance | Binary64 boundary tests require exact inclusivity and pin the .1 + .2 crossing |
| Require unused probability-group members for source bounds | A retained group includes an unrelated missing factor; source-bound output must still complete, list that factor as omitted and use zero draws |
| Skip support preflight | A sentinel sampler must never be reached when declared support violates a check |
| Skip per-draw checking | A deliberately injected bad realization after valid preflight must abort at draw 0 |
| Compile an unreviewed comparison | Both outputs are available; only the comparison acceptance is absent |
| Ignore selection acknowledgement digest | A valid reviewed output/target with a stale digest must refuse |
| Ignore target scope | Change only the target population; exact unit and all other inputs remain valid |
| Compile without UI acknowledgement | All other controls are valid; clearing just the acknowledgement disables compilation |
| Publish a late UI review | A deferred valid review resolves after the project context changes; it must not become current |

## Full gate and byte identity

All ten application-gate commands passed. The full Python suite was then repeated with the added
fixture-portability test: **1,864 passed**. That verification-only adjustment changed no product
file or captured fixture byte; the final runtime wheel is byte-identical to the frozen product
build used for the complete campaign.

| Check | Final result | Change from pre-Part-B baseline |
| --- | --- | --- |
| Python | 1,864 passed | +109 |
| Frontend | 445 passed, 56 files | +15 |
| Browser | 110 passed | +7 |
| Mutations | 317/317 caught; 240 backend, 77 frontend; unmodified copy passes | +31 |
| Earlier numerical/export bodies | 969/969 byte-identical | Unchanged |
| Captured earlier complete factor-run records | 12/12 byte-identical | Unchanged |
| Python lint/format | Passed, 225 files | All required checks |
| Strict typing | Passed, 100 source files | All required checks |
| API/types and published model/component contracts | Current | All required checks |
| Acceptance workflows and frontend production build | Passed | All required checks |

This development adds 57 Python, six component and five browser tests, and 18 mutants, over the
completed External proposals development. The complete campaign still catches every earlier
formula mutant; the new one-percent formula mutant fails the independent forward-bound assertion.
No survivor or invalid injection was accepted.

Local timings: the initial full Python run (1,863 tests) took 77.94 seconds; the repeated expanded
run took 221.50 seconds while verification work was also running. The combined frontend check took
60.06 seconds, browser tests 319.38 seconds, and the complete mutation campaign 2,454.35 seconds.
These are local runs, not performance promises. The final 969-output comparison uses the original
pre-Part-B manifest, not a newly accepted baseline. Existing arithmetic/interpreter files and the
four historical example files have no diff against the original branch baseline.

Final package build: direct and source-rebuilt runtime wheels are byte-identical, SHA-256
`b08b12d16fa3a7d31be94145f2bf53147877a9f3b4b7bc356b235b824a899768`.
The source archive includes the final verification tools/tests. Offline installed smoke passed for
both wheel routes and the isolated command install, outside the checkout, with the installed GUI,
export/reopen/recovery, all four keyed starter CLI/API materializations and receipt verification.
The plain engine-only wheel and optional-API diagnostic also passed. No release or publication
was performed. The source archive SHA-256 is
`1131283651cb5391f5e17d5e7cd692a546bfa36f6385a4d95c9b5b14e7ed58a1`.

## Limits and remaining acceptance

Sidecars and lineage are explicit exported files, not library autosave or authenticated reviewer
signatures. Comparison declaration editing uses JSON alongside individual typed review actions;
there is no claim of a complete graphical multi-model authoring system. No bounds or probabilities
are inferred from missing information. Conservative support checks can refuse an otherwise valid
reused-factor image. Exact enumeration retains the existing finite-outcome limits; output runs
limit sampled quantity-by-draw work to 2,000,000 evaluations.

The first Venture screening gallery item intentionally contains only the existing two-option
proposal/model workflows; the approved later study extends it. Optional simple-round arithmetic
remains an illustration with the disclosed exclusions. No fresh-user usability checkpoint or new
hosted-CI run is claimed. The final release-readiness review will separately inventory all limits
and the required fresh-user tasks. No push, tag, release or main update is part of this development.
