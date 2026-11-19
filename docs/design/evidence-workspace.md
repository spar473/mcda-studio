# Local evidence review workspace

The Evidence tab adds a review, compile and export workflow around the existing version-1
dossier, Python preview and compilation rules. It does not edit the current project's measurements
or save sidecars inside the library. Selecting a source never fetches it or sends it to another
service.

`EvidenceWorkspace` version 1 wraps the original project snapshot, original dossier, an ordered
list of appended claim reviews and a digest. Import replays the reviews in Python to derive the
current dossier; there is no separately trusted cached current dossier. Original proposals and
reviews remain intact. Review identity is a local assertion, and the digest detects accidental
changes, not deliberate rewriting or impersonation. Version-1 dossier and project schemas are
unchanged. Exported current dossiers remain compatible with the existing CLI compilation path.

The UI submits an explicit review with a named reviewer, timezone-aware time and optional note.
Python checks the preview digest and project fingerprint, appends to a copy, and returns a
candidate. Acceptance/correction reuses the existing evidence preview's reference, unit, value
and unique-acceptance checks. Rejection remains available to resolve a conflicting dossier.
The analyst sees proposed measurement changes before confirming the candidate in the session.
Changing the project, file, selected claim or review fields invalidates that candidate. Nothing
is written by inspect or review endpoints. Missing weights, functions and measurements do not
prevent review of otherwise compatible claims.

Export the workspace to retain history; exporting only the current dossier loses the appended
history. A separate preview export records the exact compilation digest and changes. The
existing CLI still compiles into a new file only. Reloading the workspace reconstructs review state;
it does not accept proposals anew or update project measurements. Confirmed but unexported
reviews block accidental replacement by another file and participate in the editor's leave
guard. Project Save directs the analyst to export evidence first when needed. Exported files
remain under the user's filesystem controls; downloads cannot guarantee that a user retained a
file after initiating the export.

A changed project makes the dossier stale, suppresses the support audit and blocks new reviews.
A previously valid workspace can still be exported with its original project. A raw stale dossier
can be inspected, but cannot be exported as a reconstructed workspace with a falsely matching
source project. There is no automatic rebase or fingerprint rewriting. Undoing the project edit
restores the original context and makes its dossier eligible again.

## Graphical compilation

Accepting a claim is a review; compiling is a separate step. Below the review history, the
compilation section lists every measurement the copy would change: alternative, criterion, unit,
current measurement, compiled value and the supporting claim with its review and source. It also
counts what compilation does not resolve (unreviewed, outdated and conflicting claims, missing
measurements). Missing measurements stay missing in the copy, never zero.

Compile requires ticking that every listed change was reviewed. The acknowledgement and any
compiled candidate are keyed to the project fingerprint, the loaded document, the review form,
the preview digest and the workspace digest. Changing any of them, including selecting a claim to
review, clears both. A response that arrives after the context changed is discarded, and a response
whose fingerprint or digests differ from the acknowledged preview is refused.

`POST /api/evidence/compile` replays the history, checks that the workspace digest is the
acknowledged one, then calls `evidence_service.compile_copy` with the acknowledged review digest. That
is the same gate as the CLI: it revalidates references, units, scale values and single acceptance
per cell, and copies only accepted or corrected values. The response is a version-1
`EvidenceCompilation`:

| Field | Content |
| --- | --- |
| `workspace` | Original project, original dossier with its original reviews, appended reviews, workspace digest |
| `preview` | The exact preview that was acknowledged, including `before` values and the review digest |
| `project`, `compiled_fingerprint` | The separate compiled copy |
| `digest` | SHA-256 over the rest; detects accidental changes only |

The effective reviewed dossier is not stored: replaying the workspace derives it, so it cannot
drift from the retained history. The current project, its saved file, its undo history and the
library are untouched. The analyst exports the compiled project for analysis and the bundle for
provenance. Exporting the bundle also retains the review history, so it clears the
unexported-review guard.

Selecting a bundle in the Evidence tab verifies it in Python: the digest is checked, the history is
replayed and the whole compilation is reproduced and compared. The recorded changes are then shown
historically with their original measurements, and the history is inspected against the current
project as usual. In the original project, review can continue. Any other project gets the
existing stale-dossier protection.
[Separate-copy provenance](separate-copy-provenance.md) explains how an imported copy is related to
the bundle through a copy receipt without rebinding.

## Measurement support

Python audits the current project, independently of proposed compilation changes:

| Status | Meaning in this dossier |
| --- | --- |
| Missing | No measurement entered |
| Unsupported | Measurement entered, no claim recorded for the cell |
| Unverified | Claims recorded, no accepted claim whose value equals the entered measurement |
| Supported | One accepted/corrected matching claim, with valid references, scale and units |

These statuses concern recorded provenance, not numerical validity or factual accuracy. An
accepted value different from the entered measurement does not support that entered value.
An outdated source can still be accepted, so its freshness warning remains separately visible.
Self-reported, independent and unknown are descriptions of source relationships, not a quality
ordering. Conflicts are the existing preview's differing unrejected claims; they are not
automatically resolved by source classification or acceptance of another claim.

Open Questions reuses this audit to ask which source supports an entered value. The current
workspace dossier travels between Evidence and Open Questions within the session. There is no
composite importance score, assumption that an unsupported value is zero, or automatic change
to an analytical result.

## Limits

- Review history has a 2,000-event bound; the UI accepts local files up to 8 MB.
- Source contents are not embedded, extracted, fetched or validated. References are displayed
  for inspection; proposals can originate from a human or an identified external tool.
- The workspace does not prove that reviews pre-dating import were preserved by outside tools.
- Sidecar autosave, signed identities and evidence-version rebasing are deferred. Compilation
  produces a separate exported copy; it never edits the open project or writes the library, and
  importing that copy is a separate explicit action on the Projects screen.
- No project schema, MCDA engine, uncertainty distribution or numerical tolerance changes.
