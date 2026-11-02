# Decision records

A decision record is an exported, immutable-by-convention JSON snapshot of who decided what, on
which analyses and evidence. Python builds and verifies every record. The Decision tab and API
create records in memory only: they never write the project library, and an earlier record file
is never changed. Revising a decision creates a new record linked to its predecessor.

Version-1 records (`mcda decision record`) remain readable and can be revised. The CLI still
writes version 1; the graphical workflow writes version 2.

## Version 2 contents

| Part | Content |
| --- | --- |
| `decision` | Owner, date, outcome (`selected` or `deferred`), selected alternative, alternatives considered, rationale, unresolved assumptions, review triggers and at most six analysis configurations |
| `project`, `project_fingerprint` | The exact project the decision was made on |
| `analyses` | One snapshot per requested configuration: `completed` with the complete sealed analysis record, or `unavailable` with the reason and issues. Nothing is dropped |
| `feasibility` | The existing feasibility check (`checked`, `no_requirements` or `unavailable`); failed and unresolved requirements for the selection appear as notices beside the choice, with no override |
| `supporting_artifacts` | Complete evidence compilation and calculation bundles, each with its copy receipt when cited from an imported copy |
| `anchors` | How each artifact relates to the record: its compiled project is the record's project (`compiled` or receipt-`verified_copy`), or it is the original project of another cited artifact (a calculation compiled on top of compiled evidence) |
| `measurement_trace` | For every entered measurement: the artifact that set it (evidence claim, or calculation with its fundamental source factors) and the value it replaced, or `entered` when no cited artifact set it |
| `notices` | Unavailable analyses, the analysis universe, failed or unresolved requirements for the selection, directly entered measurements and a project change since the predecessor |
| `previous_digest`, `predecessor` | The predecessor's digest and a summary of its decision (owner, date, outcome, rationale, project fingerprint) |
| `digest` | SHA-256 of the canonical record without its digest |

Alternatives considered are a declaration only. Every recorded analysis uses all of the project's
alternatives, so outranking, pairwise and ranking analyses keep their universe; the record notes the
difference. The analysis selection is explicit and bounded; no combination is evaluated
automatically. Scores are preferences and SMAA-2 frequencies are not outcome probabilities.

## Anchoring rules

An artifact is accepted only when its compiled fingerprint, or the copy fingerprint of its
receipt, equals the record's project or the original project of an already anchored artifact.
Anchoring therefore forms a single chain. Duplicates, two artifacts claiming the same project, an
outdated or unrelated receipt, and an artifact that relates to nothing are refused with explicit
codes. Every artifact is fully verified (digest, replay, reconstruction) before it is anchored.
Similar measurements never relate an artifact to a project.

## Verification on reopening

Creation and reopening share one reference check: every considered and selected alternative must
exist in the recorded project (`DECISION_UNKNOWN_ALTERNATIVE`, `DECISION_UNKNOWN_SELECTION`).
Reopening then checks each analysis snapshot against its declared configuration:

| Code | Refused |
| --- | --- |
| `DECISION_ANALYSIS_COUNT` | Not exactly one snapshot per declared configuration |
| `DECISION_ANALYSIS_CONFIGURATION` | A snapshot whose configuration differs from the declared one |
| `DECISION_ANALYSIS_RECORD_MISSING` | A `completed` snapshot without its sealed record |
| `DECISION_ANALYSIS_STATUS` | A `completed` snapshot with a reason, or an `unavailable` one with a record or no reason |
| `DECISION_ANALYSIS_SUBSTITUTED` | A sealed record whose method or configuration (result and envelope) differs from the declaration, even if its own digest is intact |
| `DECISION_ANALYSIS_DIGEST`, `DECISION_ANALYSIS_PROJECT` | A sealed record that fails its own digest or belongs to another project |

These are validation errors (HTTP 422 `VALIDATION_FAILED` with each code in the details), never
server exceptions. Version-1 records are checked for an unknown chosen alternative in the same
way, and a revision fully verifies its predecessor first. Reopening also re-verifies every
artifact and re-derives anchors, the measurement trace, feasibility and notices, all of which
must match exactly. Analyses are not rerun: SMAA-2 repeatability is promised only in the
environment each result records. A record is readable whatever project is open. It reports
whether the open project is exactly the recorded one and never rebinds to a changed project.

When the predecessor file is supplied, its digest must equal `previous_digest` and its summary
must match exactly. Without that file, a consistently re-signed summary cannot be detected:
digests detect accidental changes, not deliberate rewriting, and reviewer and owner identities
are local assertions.

## Limits

- Records are files the user keeps; there is no record browser, library storage, signature or
  access control. A revision must use a project with the same ID as its predecessor (as in
  version 1).
- At most six analyses and eight artifacts per record. Records embed complete projects and
  bundles, so they grow with the cited artifacts.
- Chains of copies need a receipt per import; a receipt that was not downloaded at import time
  cannot be regenerated.
- The CLI does not yet create version-2 records or cite bundles.
