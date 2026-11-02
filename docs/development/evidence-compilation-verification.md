# Graphical evidence compilation and separate-copy provenance — 1 November 2026

## Baseline

Branch `codex/integrated-evidence-workspace` at `a8a4362`, clean tree, one worktree, no
`AGENTS.md`. No other writer was active: no other Claude session was running, and the Codex
sessions had completed (their helper processes had the folder open but had written nothing since
the `a8a4362` commit). A recovery bundle of every ref was written outside the checkout and
verified by cloning (HEAD and tree hashes matched; it contains `6823357`, `4fed5f5` and `a8a4362`).
Focused evidence, derived, decision and project tests passed before any change (100 tests).

## What was built

- `services/evidence_compilation_service.py`: version-1 `EvidenceCompilation` (review workspace,
  exact preview, compiled project, fingerprint, digest). It compiles through
  `evidence_service.compile_copy` after replaying the history and checking the acknowledged
  workspace digest. Verification checks the digest, replays the history and reconstructs the
  whole bundle. The effective dossier is derived, never stored.
- `domain/provenance.py`, `services/provenance_service.py`: version-1 `ProjectCopyReceipt`,
  issued by `import?on_conflict=new_id`, and `bind`, which classifies a project against a verified
  evidence or calculation bundle as `compiled`, `source`, `verified_copy` or `different` by exact
  fingerprints. `derived_service.verify_bundle` was extracted unchanged from `preview_document`.
- API: `POST /api/evidence/compile`, `/api/evidence/compilation/inspect`, `/api/provenance/binding`.
  The import response gains `copy_receipt`. OpenAPI and generated types were regenerated.
- UI: the Evidence compilation section (target-change table, explicit acknowledgement,
  context-keyed candidates, two exports), the recorded-compilation view with its provenance
  status, the shared `ArtifactBindingStatus` (also used for calculation bundles) and the copy
  receipt download on Projects.

Design: [Evidence Workspace](../design/evidence-workspace.md#graphical-compilation),
[separate-copy provenance](../design/separate-copy-provenance.md). No project schema,
dossier, workspace or calculation-bundle format changed, and no numerical engine or tolerance was
touched.

## Checks run on the final tree

| Check | Actual result |
| --- | --- |
| Full Python suite | 1,622 passed (1,594 before; 28 new), existing Starlette/httpx deprecation warning |
| Ruff, formatting, strict mypy | Passed (81 source files) |
| OpenAPI and generated TypeScript freshness | Passed |
| Full frontend check | 408 tests in 51 files passed; TypeScript, ESLint (0 warnings), type freshness and production build passed; existing large-chunk warning |
| Full browser gate | 98 passed in 4.2 minutes on a fresh throwaway store (96 before plus the two new domain workflows; the calculation workflows were extended) |
| Acceptance scripts | `acceptance_demo.py` and `acceptance_evidence.py` passed |
| Existing numerical/export outputs | 969/969 byte-identical to `a8a4362` (`scripts/byte_identity.py`) |
| Evidence/provenance mutation subset | 24/24 killed (11 new backend, 5 new frontend, 8 existing), unmodified baseline passes |
| Complete mutation gate | 227/227 killed, unmodified baseline passes (see below) |

New tests: `tests/unit/test_evidence_compilation.py` (history retention, CLI equivalence,
accepted/corrected only, missing not zero, conflicting/duplicate/unit/reference refusals, stale
preview/project/history, six tamper cases, historical inspection), `tests/unit/test_provenance.py`
(exact relationships for both artifact kinds, later edits, other projects, ID-only
transformations, five receipt tamper cases), `tests/api/test_api_evidence_compilation.py` (both
domains end to end over HTTP, including the conflict import and receipt), component tests for
acknowledgement, digest mismatch, delayed responses (project change and intent change while open),
blocking, reopening and receipt refusal, and `frontend/e2e/evidence-compilation.spec.ts`.

The browser workflow uses the exact bundled `nz_deeptech_vc` and `supplier_qualification`
projects with their unmodified `examples/evidence_demo` dossiers. It checks that the stored
fingerprint equals the dossier's and never rewrites it. Each run reviews, acknowledges, compiles,
exports both files, imports the copy as a separate project, downloads the receipt and reopens
the bundle in the copy. There the bundle is historical with review blocked until the receipt
verifies it. In the original project it reopens as the source with review enabled, and the
original's saved bytes and undo stay unchanged throughout. The calculation workflows now also
verify their imported copy through its receipt.

Mutation notes: as for calculation bundles, removing the initial bundle-digest guard alone is
equivalent to the reconstruction comparison and is not counted. The frontend early return for a
delayed compile response is likewise backed by the candidate key, so removing it alone is
equivalent and is not listed. Instead, a component test covers a delayed response after an intent
change while the panel stays open.

## Complete mutation gate

`scripts/mutation_check.py` (no filter) ran on a snapshot of the committed `0253148` code: all
227 applicable mutants were killed (162 backend, 65 frontend: the 211 earlier cases plus the 16
evidence-compilation and provenance cases), and the unmodified baseline passed every runner. The
command exited 0. No survivor, invalid target or equivalent case arose in this run; the two
equivalent guards described above are not listed as mutants. This result covers Priority A only.
Decision-record mutants are recorded separately in the
[decision records record](decision-records-verification.md).

## Not established

- Hosted CI was not run; nothing was pushed.
- No participant usability or screen-reader checkpoint has been run. The prepared protocol in the
  [integrated sprint record](integrated-workspace-verification.md#independent-fresh-user-checkpoint--prepared-not-run)
  applies; add: "compile the reviewed evidence, import the copy beside the original, and explain
  what the copy receipt shows and does not show".
- Receipts and digests are unsigned checksums; they do not authenticate people or prove accuracy.
- Decision records do not yet cite compilation bundles or receipts (next increment).
