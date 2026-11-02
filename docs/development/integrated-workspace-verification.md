# Integrated decision-engineering sprint — 1 November 2026

## Baseline (Milestone 0)

The initial checkout was clean on `main` at `68233571ccf7d9cda4cec81f450d2a4014259335`,
with one worktree, no repository/ancestor `AGENTS.md` and no concurrent agent edits.
Work continues on local branch `codex/integrated-evidence-workspace`. No push is authorised.

The latest hosted run (private working repository, 31 October 2026 UTC) was
for that exact commit: 1,569 Python tests passed and one failed. Its Open Questions wording test
hard-coded a macOS decimal representation of a weight threshold; Linux differed by about 2e-16.
The wording test now checks the value returned by the sensitivity service, as its neighbouring
class-threshold test does. The independent numerical reference suites and their tolerances are
unchanged. No hosted rerun is claimed.

Local baseline: 1,570 Python tests passed with localhost/process execution enabled. An earlier
sandbox-only attempt had 1,563 passes and seven loopback-bind permission failures; those tests
were rerun, not skipped. Existing Starlette/httpx deprecation warning remains.

## Milestone 1

Implemented: [Evidence Workspace](../design/evidence-workspace.md), stateless Python inspection
and review endpoints, retained original project/dossier and appended review history, local
review/preview/confirm/export/reopen, source classifications, stale-context protection, current
measurement support audit and support questions linked back to Evidence.

Changed areas: `domain/evidence_workspace.py`, `services/evidence_workspace_service.py`,
`services/questions_service.py`, API schemas/routes and generated contracts, Evidence tab and
workspace component, editor leave guards, Questions integration, focused unit/API/component/
real-backend browser tests and mutation cases. Existing evidence and calculation compilation
rules remain authoritative and unchanged.

Verification results are recorded below after the final combined gate. Browser tests exercise
synthetic venture and supplier dossiers, explicit reviews, preview versus confirmation, export,
reopening, unchanged project bytes/undo and stale context after editing and undoing a project.
Automated tests do not constitute independent participant validation.

Milestone checks: all 1,586 Python tests passed; all 393 frontend tests, TypeScript, ESLint,
generated types and production build passed. Ruff, formatting, strict mypy and OpenAPI freshness
passed. Six focused real-backend browser workflows passed (three new Evidence workflows and
three existing Open Questions workflows). Six backend and two frontend evidence mutants were
caught, with unmodified scratch baselines passing. Acceptance demo and evidence scripts passed.
An initial browser run exposed an exact select-label lookup and a wrong test title locator; an
explicit select name and corrected test resolved them, then all six workflows passed. The complete combined browser and
mutation gates are recorded separately after subsequent changes. Existing large-chunk build
warning and Starlette/httpx warning remain; no threshold was changed.

Milestone 1 commit: `4fed5f5`.

## Milestone 2 — reviewed calculation exports (bounded slice)

The interface now shows current-to-calculated target changes, all formula definitions/reviews
and declared unit dimensions. After explicit target acknowledgement it calls the existing Python
compilation/digest gate and offers a static project export plus a reproducible calculation bundle.
The bundle retains the original project, reviewed model/trace, compiled project and digests.
Reopening verifies the artifact and reconstructs compilation in Python. Calculations survive tab
navigation; explicit recalculation invalidates previous target acknowledgement/export candidates.

Changed areas: `services/derived_service.py`, API schemas/routes and generated contracts,
`DerivedMeasurementsPanel`, its editor mounting, independent-reference regression coverage plus
bundle unit/API/component tests, both real-backend domain workflows and mutation cases. Users
can export and import a separate compiled copy through the interface without editing JSON.
The source project and its undo history remain unchanged. Existing manual target values are
shown before replacement and retained in the bundle's original snapshot.

This completes the static review/compile/export slice, not all of Priority B. Formula/factor
creation and editing, live recalculation, embedded provenance, sidecar autosave and a project
schema migration remain deferred. Dossier claims and accepted calculation factors remain
distinct inputs. Graphical decision records and propagation of formula provenance into historical
decision records are not implemented. No complete source-to-decision-record workflow is claimed.

Priority C remains design-only: [fundamental-factor uncertainty and independent test plan](../design/derived-uncertainty-verification-plan.md).
It includes analytic moments, exact discrete independent versus quantile-coupled products,
shared-factor identity and rank reversal counterexamples, deterministic reduction, invalid-draw
refusal, fixed-seed/order tests and existing SMAA-2 regressions. No output-range approximation or
partial sampling implementation was introduced.

## Combined verification

The final combined gate exercised the implementation in this tree. The 969 existing numerical/export
outputs were byte-identical to `6823357`. Both real-browser calculation demos exercise preview,
target acknowledgement, compilation, two artifact exports, bundle reopening, separate-copy import
and unchanged original project bytes. Original numerical engines and tolerances are unchanged.

Mutation audit: removing the first bundle-digest guard survived because complete reconstruction
also compares the artifact digest. This is equivalent with respect to acceptance/refusal (the
diagnostic text can differ); it is not counted as a killed integrity defect. It was replaced by
a reachable original-project snapshot corruption. No production guard or test assertion was
removed to force a mutation result.

| Check | Actual result |
| --- | --- |
| Full Python suite | 1,594 passed; existing Starlette/httpx deprecation warning |
| Full frontend check | 398 passed across 50 files; TypeScript, ESLint, generated types and production build passed |
| Full browser gate after the final review-message fix | 96 passed in 3.5 minutes, including existing performance assertions, both domain workflows and the unexported-review leave guard |
| Python lint/format/typing | Ruff and formatting passed; strict mypy passed for 78 source files |
| API contracts | OpenAPI and generated TypeScript freshness passed; project schema unchanged |
| Existing numerical/export outputs | 969/969 byte-identical to `6823357` |
| Acceptance scripts | `acceptance_demo.py` and `acceptance_evidence.py` passed, including fresh-process reopening and independent oracles |
| Complete mutation audit | Initial full run: 210/211 caught, unmodified baselines passed, one equivalent checksum case identified as described above |
| Corrected final mutation coverage | All 151 backend cases rerun and caught with unmodified baselines passing; all 60 unchanged frontend cases caught in the full run. This covers all 211 final applicable cases; it is not a claim that the original full command exited green |
| Local distribution builds | Direct wheel, sdist and wheel rebuilt from sdist passed archive inspection; both wheels have identical hashes. No clean-install GUI smoke rerun |
| Visual inspection | Reviewed claim and compiled-copy captures inspected for legibility; no participant or screen-reader validation claimed |

Commands: the full gate from `testing.md`, then `scripts/mutation_check.py --backend-only` after
replacing the equivalent backend mutation. No implementation or frontend test changed between
those mutation runs. An earlier mutation run was interrupted when the final review-error message
and its regression were added; it is not counted as a completed gate. No tolerance, assertion,
performance threshold or production guard was weakened. The existing large-chunk build warning
remains. The preceding hosted Actions failure has not been rerun because nothing was pushed.

Local logs, before/after numerical hashes, browser captures, acceptance evidence and development
distributions are retained under ignored `dist/integrated-sprint-2026-11-01/`. The record above is
committed; generated verification artifacts are not. Evidence/calculation demonstration sidecars
remain checkout-only. Distribution build checks do not constitute a release or installed-GUI check.

The local fresh-user protocol below is prepared but has not been run. No participant usability,
screen-reader accessibility, hosted rerun or public release is claimed.

## Independent fresh-user checkpoint — prepared, not run

Use a participant who has not implemented or reviewed this workflow. Give no walkthrough. Start
with an imported `nz_deeptech_vc` project and its `examples/evidence_demo/vc.json` dossier, then
repeat with `supplier_qualification` and `supplier.json`. Calculation demonstrations are in
`examples/derived_measurements`; import their exact paired project/model separately. Explain
only that the data are synthetic and scores/ranking frequencies do not predict success.

Ask the participant to:

1. Find one source, interpret its classification and identify who proposed its claim.
2. Find a measurement with no accepted matching evidence and explain whether it is invalid.
3. Reject the conflicting unreviewed proposal, preview the effect, confirm and export history.
4. Reopen the exported workspace and find the original proposal and review history.
5. Explain a calculated estimate, its units, original assumptions and shared source inputs.
6. Explain one sensitivity result and distinguish a range from a probability distribution.
7. Find a related Open Question and describe the evidence or investigation needed to resolve it.
8. Record a decision if that interface is supported; otherwise record that this step is unavailable.

For each domain record elapsed time, first action, wrong turns, misunderstandings, exact hints,
whether completion was independent, and the participant's interpretation of what changed.
Specifically probe acceptance versus project compilation, outdated versus rejected, independence
versus correctness, unsupported versus missing, and downloaded versus autosaved history. Record
data-loss or incorrect-inference failures separately from navigation friction. Do not declare
usability validated without an actual independent participant and retained observations.
