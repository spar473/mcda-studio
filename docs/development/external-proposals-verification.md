# External proposals verification

1 November 2026. Implements the [accepted design](../design/external-proposals.md), including the
owner's filtered bulk-review amendment. The pre-development baseline (historical record, not included)
was fully green before implementation. Work stays on `codex/integrated-evidence-workspace`; no
main-branch change, push, tag or release.

## Delivered boundary and interchange

New version-1 intake, review-workspace and compilation formats retain originals, local sources,
model cards/digests, tool/run metadata, confidence, human comparison claims, append-only reviews
and registry-supply events. No old project schema, sidecar version or result type changes.
Only the existing Open Questions request gains an optional proposal input; earlier responses and
numerical/export bodies remain pinned. Registry additions cannot replace earlier entries.

Generic JSON/CSV import has [published schemas and an exact CSV contract](../schemas/external-proposals-csv.md).
Structural errors refuse the complete batch; semantic issues remain visible and blocked. Unknown
labels/units can be corrected without changing the original payload. Missing source/card entries
can be supplied locally. No provider/model is run, reference fetched or project data sent out.

A raw stale intake remains explicitly unbound for inspection/export, with a null source snapshot.
History requires its exact retained source. Reviews and compilation refuse changed bindings and
acknowledgements; no fingerprint is rewritten. Files/exported artifacts are bounded to 8 MB,
proposals/reviews to 2,000, and the encoded HTTP wrapper to 24 MB before JSON parsing, including
chunked bodies. Typed limits are published with the interchange contract.

Reviewed cell proposals adapt to the existing evidence preview/compiler. Pending/rejected/blocked
rows stay outside its numerical subset. Exactly one active cell claim is allowed; replace it only
by explicitly rejecting the earlier selection. The outer bundle preserves all originals and
annotations around an unchanged evidence compilation. A corrected unit appears in the adapted
claim while its original remains in the intake. Tags/assertions never fabricate a criterion,
feasibility failure or weight. No sources, ranges or methods are averaged.

## Review and graphical workflow

Evidence → External proposals imports JSON, or CSV plus its local registries. Per-item cards,
original/effective payloads and source classifications remain visible. Filters select tool, kind,
criterion and original/effective agreement against another tool or human. Mixed relations retain
the actual flags: an incomparable unit does not become a disagreement. Missing original
measurements are explicit, not zero. Shared sources remain disclosed; agreement is descriptive.

Bulk selection starts empty, including after filter changes. Blocked items cannot be selected or
applied, even to reject them; individual correction/rejection remains available. One preview lists
**every** affected ID, original/correction, source and review metadata. Confirmation appends one
event per selected proposal, with identical reviewer/time/note. Accepted, corrected and rejected
bulk sequences equal ordered individual sequences byte for byte. CLI review also previews the
entire selection first and requires its exact confirmation digest before exclusive file creation.

Compilation separately acknowledges every cell change and retained annotation. Late/mismatched
imports, reviews and compilations cannot become current; changed context invalidates candidates
and acknowledgements. Unexported history joins Save/leave guards. Export the full proposal bundle
and separate project; export its unchanged nested evidence bundle for existing version-2 decision
records and keep/cite the complete outer bundle alongside it for intake metadata. Reopening
replays history and reconstructs compilation; no project/library/undo changes occur.

## Independent checks and reachable mutations

`tests/regression/proposal_oracle.py` imports no application code. It independently reconstructs
canonical payload digests, CSV payloads and selected cell values. Both invented screening and
supplier demos agree with it, normalize JSON/CSV identically and rebuild byte for byte in temporary
directories. Python-generated component snapshots and all published schemas are checked for
freshness. No reference file is rewritten by mutation tests.

| New injected defect | Reachability evidence |
| --- | --- |
| Imported output accepted without review | Pending-only compilation must equal the original project |
| Correction overwrites original | Correct 30 to 44; original intake must retain 30 and prior events |
| Review on another revision | Edit title only; new review must raise stale-revision refusal |
| Unresolved original source accepted | Keep a valid primary source but remove a different original reference |
| Two active cell claims | Correct first tool, then try accepting the second before explicit rejection |
| Confidence rescales measurement | Vary absent/0.01/1 confidence; project and analyses must be identical |
| Bulk blocked-item check skipped | Bulk rejection of a blocked item is refused; individual rejection is allowed |
| Missing/changed card accepted | Retain a valid subject/source but remove or change the card digest |
| Original registry entry replaced | Supply a changed source under its existing ID after an acceptance |
| Compilation acknowledgement ignored | Wrong review/history digests must refuse even with otherwise valid inputs |
| CSV valid subset imported | One valid and one malformed row must refuse the complete batch |
| Late import published | Resolve import after project change; no workspace may be published |
| Blocked checkbox enabled | A blocked row remains available for individual review but disabled for bulk |

All Python injection anchors were unique and their injected code parsed. The new mutations must
fail their targeted suite, and the unmodified scratch copy must pass. Browser checks exercise both
domains through bulk acceptance, individual correction/rejection, human/two-tool disagreement,
Open Questions, export/reopen/verification and unchanged saved project bytes.

## Full gate result

The complete final-tree gate passed all ten commands:

| Check | Pre-Part-B baseline | External proposals |
| --- | --- | --- |
| Python tests | 1,755 | 1,807 (+52) |
| Frontend tests | 430 in 53 files | 439 in 54 files (+9) |
| Real-browser tests | 103 | 105 (+2) |
| Mutations caught | 286/286 | 299/299 (+13): 224 backend and 75 frontend |
| Unmodified mutation copy | Passes | Passes |
| Earlier numerical/export outputs | 969 | 969/969 byte-identical |

Ruff lint and formatting passed (205 files), strict mypy passed (91 source files), OpenAPI and
frontend type freshness passed, both acceptance workflows passed, and frontend typing/lint/build
passed. Local runner durations: Python 45.00 seconds, combined frontend check 29.68 seconds,
browser 228.36 seconds and mutations 1,195.92 seconds. The focused mutation run separately caught
all 13 new defects with its unmodified copy passing. Its injection anchors were unique and every
Python injection parsed before execution.

A final `scripts/byte_identity.py` manifest was compared against the same pre-Part-B baseline:
969/969 unchanged. All pre-existing OpenAPI schemas remain identical except the Open Questions
request's additive optional proposal field; existing project/sidecar/result schemas, contract
fixtures and original example files are unchanged. Existing tests, tolerances and oracles were
not weakened. Local gate/byte logs and manifests are retained outside the checkout; the baseline
commit and commands in the linked baseline record reproduce the comparison.

A separate local smoke reviewed 400 proposals across 40 alternatives and 10 criteria, producing
400 separate review events and 400 compiled cell changes while preserving the original workspace.
Review plus compilation took 1.007 seconds in that single run; this is not a throughput guarantee.
The final browser compilation screenshot was inspected: current/compiled values, retained
original correction, annotations, pending questions and export actions were readable. No human
usability checkpoint or new hosted CI result is claimed.

## Limits

- Sidecars remain explicit files, without autosave, a shared review service or authenticated identities.
- Corrections use a typed JSON payload editor; bulk correction applies the entered payload to each
  selected item, while CLI event files can state distinct corrections with common review metadata.
- Human comparison claims are supplied in the intake/CSV registries. They remain comparison
  references, outside this intake's numerical selection; ordinary human evidence uses its existing compiler.
- Original and supplemental references are retained, without source fetching, quality weighting or
  claims of independent validation. A model card is disclosure, not proof of accuracy.
- The demonstrations are checkout examples at this step; the next development packages its
  selected starter artifacts. No new hosted CI or independent human usability result is claimed.
