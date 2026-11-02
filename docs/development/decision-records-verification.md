# Graphical decision records with artifact provenance — 1 November 2026

Built on [graphical evidence compilation](evidence-compilation-verification.md) (`0253148`).

## What was built

- `domain/decision.py`: `DecisionDetails` (owner, date, `selected`/`deferred` outcome,
  alternatives considered, rationale, assumptions, triggers, at most six unique configurations).
  Version-1 models are unchanged.
- `services/decision_record_service.py`: version-2 records with explicit analysis snapshots
  (unavailable analyses keep their reasons and issues), the feasibility snapshot, cited bundles and
  receipts, exact-fingerprint anchoring (including calculation-on-evidence chains), a
  per-measurement trace, notices and predecessor links. Reopening re-verifies artifacts and
  re-derives everything deterministic. Version-1 records verify by digest and can be revised.
- API: `POST /api/decisions/preview` and `/api/decisions/inspect`. Records arrive as JSON objects
  validated in the endpoint, so analysis-record schemas stay response-only. The OpenAPI change is
  additive: 16 new schemas, none renamed or altered.
- UI: a **Decision** tab (`DecisionRecordPanel`, `DecisionRecordView`). It keeps its draft across
  tabs, binds previews to the project, details, artifacts and predecessor, refuses records for
  another revision, and opens records historically. Revising pre-fills a new linked record, and an
  unexported preview joins the existing leave guard.

Design: [decision records](../design/decision-records.md).

## Checks run on the final tree

| Check | Actual result |
| --- | --- |
| Full Python suite | 1,658 passed (1,622 after Priority A; 36 new), existing Starlette/httpx deprecation warning |
| Ruff, formatting, strict mypy | Passed (82 source files) |
| OpenAPI and generated TypeScript freshness | Passed; the contract change is additive only |
| Full frontend check | 416 tests in 52 files passed; TypeScript, ESLint (0 warnings), type freshness and production build passed; existing large-chunk warning |
| Full browser gate | 100 passed in 3.6 minutes on a fresh throwaway store (98 plus the two decision workflows) |
| Acceptance scripts | `acceptance_demo.py` and `acceptance_evidence.py` passed |
| Existing numerical/export outputs | 969/969 byte-identical to `a8a4362` |
| Decision mutation subset (`--decision-only`) | 20/20 killed (17 backend, 3 frontend), unmodified baseline passes; run before the final inactive-tab rendering fix, whose code these mutants do not target |
| Complete combined mutation gate | 247/247 killed on the final tree (179 backend, 68 frontend: the 227 Priority A cases plus the 20 decision cases), unmodified baseline passes, exit 0. Priority A's own 227/227 result is recorded separately in its [record](evidence-compilation-verification.md#complete-mutation-gate) |

New tests: `tests/unit/test_decision_record_v2.py` covers outcomes; the analysis universe;
unavailable analyses; failed and unresolved requirements; receipts; calculation-on-evidence
chains in both citation orders; revisions with version-1 and version-2 predecessors;
historical reading after edits; seven re-signed tamper cases; unknown considered and selected
alternatives on creation and reopening, with and without requirements; nine snapshot cases
(missing record, unavailable with record or without reason, completed with reason, swapped
sealed records, another method, changed snapshot or declared configuration, dropped snapshot);
and version-1 records with an unknown choice. `tests/api/test_api_decisions.py` runs
preview, inspection and revision without library writes and checks malformed, tampered and
unknown-alternative input. With and without requirements, it checks that unknown selections,
missing completed records and substituted sealed analyses return 422 `VALIDATION_FAILED` with
their codes. The suite would surface a server exception as a failure. Component tests and
`frontend/e2e/decision-records.spec.ts` (both domains) cover the Decision tab.

Review fixes made before committing:

- Reopening previously re-checked neither the decision's alternatives against the recorded project
  nor snapshot consistency. A re-signed record could name an unknown alternative (a server
  exception when requirements exist), mark an analysis completed without its record, or pair a
  sealed analysis with another configuration. Reference validation is now shared by creation and
  verification. Snapshot status, record presence and the sealed method and configuration are
  checked explicitly, and a revision fully verifies its predecessor.
- The first full browser run failed one Case A test. The Decision tab stayed mounted while hidden,
  so its generic "Scenario" control shadowed the editor's own. The panel now keeps its draft but
  renders nothing while inactive, and its analysis controls have specific names. The rerun passed
  100/100.

Equivalent guard, not listed as a mutant: the relationship check inside anchoring is defensive,
because a matched fingerprint always binds as `compiled` or `verified_copy`.

## Human validation

No participant or screen-reader checkpoint has been run. Tasks to add to the
[prepared protocol](integrated-workspace-verification.md#independent-fresh-user-checkpoint--prepared-not-run):

1. In the imported copy, record a decision citing the compilation bundle and its receipt. Explain
   which measurement came from which claim and what value it replaced.
2. Explain why SMAA-2 (or another analysis) is listed as unavailable, and what a feasibility
   failure beside the choice means for the decision.
3. Reopen the record after editing the project; explain "shown historically".
4. Revise the record after changing an assumption; confirm that the first file is unchanged and
   that the revision names it.

Record misunderstandings of "alternatives considered" against the analysis universe, and of
receipts as proof of origin rather than of accuracy.

## Not established

- Hosted CI was not run; nothing was pushed.
- Records and receipts are unsigned; owner and reviewer identities are local assertions.
- The CLI still writes version-1 records only; there is no record browser or library storage.
