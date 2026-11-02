# External proposals

**Accepted — implemented and locally verified 1 November 2026.** This extends the existing boundary:
external outputs arrive as local files, remain proposals, and require a human review. No model is
run by the application. No project data leaves the machine. The engine answers preference
questions; categorical predictions and model scores are inputs under review.

## Problem and scope

The current evidence dossier supports numeric and categorical cell claims with `Origin` and
`Review`, but cannot preserve a typed external import, model-card reference, alternative tag or
suggested source claim as one reproducible reviewed intake. Add a generic proposal sidecar and
local JSON/CSV import, comparison, review, Open Questions and acknowledged separate-copy
compilation. Any external classifier tool, external model or language model can produce the
published files without an adapter or a code change.

## Data model and compatibility

A new `ExternalProposals` sidecar, version 1, contains the exact project fingerprint, locally
retained model cards and source records, original proposals, append-only review events and a
canonical digest. Each proposal contains a unique stable ID, versioned kind, subject, payload,
`tool_id`, `tool_version`, model-card reference and digest, timezone-aware run timestamp,
optional tool-reported confidence, and source IDs. Tool identity is an opaque local-data value,
never an engine integration. Human comparison claims remain evidence claims with human origins.

| Kind | Subject | Payload | Compilation effect after review |
| --- | --- | --- | --- |
| `categorical_cell` | Alternative and leaf criterion | Exactly one declared scale label | Existing categorical evidence claim |
| `numeric_cell` | Alternative and leaf criterion | Finite number and exact unit | Existing numeric evidence claim |
| `alternative_tag` | Alternative | Tag namespace, label, explanatory text | Reviewed annotation in the separate compilation bundle |
| `source_claim` | Alternative, optional criterion, source ID | Cited assertion text, excerpt/location; optional explicit compatible measurement | Reviewed source annotation; only an explicit typed measurement becomes an evidence claim |

Confidence is `{value, scale, meaning}` metadata, with a finite number and declared scale. A
unit-interval scale must lie in [0,1]; other scales need stated bounds. Absent confidence remains
absent. It is never a weight, multiplier, source-quality grade or a probability produced by the
engine. A missing model card is an unresolved reference and blocks acceptance; it never causes a
network fetch. A model card documents purpose and limitations; the stricter activation requirements
for a proxy criterion are in [its own note](disclosed-model-proxy-criterion.md).

A review selects a primary source reference and may append explicitly human-supplied supporting
references without rewriting the tool's references. At least one resolved source is required to
accept a cell proposal, tag or source assertion. Cell adaptation uses that selected primary
`Source` in the existing `Claim`; all supplemental references and their classifications remain in
the intake/comparison bundle, never blended into a quality grade.

Keep `EvidenceDossier` version 1 and project schemas 1–6 unchanged. Only active, compatible accepted/corrected cell proposals adapt to existing
`Claim`/`Origin`/`Review` and the existing preview/compiler. Pending/rejected/blocked proposals stay
in the complete intake bundle and Open Questions, not in the numerical compilation subset. Non-cell annotations are retained in a
new version-1 proposal-compilation envelope around the existing evidence compilation and the
reviewed annotation set. They do not fabricate a numerical criterion or silently alter project
metadata. Every compilation creates a separate static project copy plus its complete bundle.
Existing dossiers are readable as before; no migration or reinterpretation is needed. Unknown
sidecar or proposal-kind versions are refused. Round-trip old dossiers and published schema
examples in compatibility tests. If owner review instead selects embedded annotations, that is a
project-schema change requiring an explicit migration design and tested old/new fixtures first.

## Generic import contract

Publish `docs/schemas/external-proposals-v1.schema.json`, a CSV column specification and matching
minimal JSON/CSV examples. JSON uses the sidecar envelope and discriminated payloads above. CSV is
UTF-8 with one proposal per row, fixed required columns (`schema_version`, fingerprint, proposal
ID, kind, subject IDs, payload JSON, tool identity/version, model-card reference/digest,
run timestamp, confidence JSON or empty, source-IDs JSON). Source and model-card registries are
separate local JSON files in the same import operation; CSV cells never contain executable
expressions. Parse ID strings literally; no spreadsheet formula execution or implicit coercion.
Blank numeric values are missing, never zero. CSV line numbers appear in errors. Both importers
normalize to the same typed canonical object and digest. Refuse duplicate headers, extra fields,
ambiguous delimiters, duplicate proposal IDs, malformed JSON cells and any partially valid batch;
never import only the structurally valid rows. Well-typed but semantically incompatible rows
(unknown subject/source/card IDs, out-of-vocabulary labels or mismatched units) are retained as
blocked pending proposals with explicit issues; they cannot be accepted or compiled until resolved.
This preserves an original label for a genuine correction. Bound file size, row count and string length before allocation.

## API, CLI and UI

Proposed stateless operations: `proposals inspect`, `review`, `preview`, `compile`, `verify`, with
matching API endpoints and exclusive-create CLI output files. Bodies carry the project, sidecar,
expected review digest and workspace digest. Review/replay and compilation remain Python-owned.
The Evidence tab gains local import, per-proposal provenance/model card, comparison and review.
Accept, correct and reject require reviewer and timezone-aware time. Correction is a typed payload
replacement with reviewed provenance; the original payload and prior reviews are immutable in the history. Changing kind or
subject requires a new proposal linked to the original, rather than disguising a correction.
Review edits, project edits and changed imports invalidate compilation acknowledgement. Late
responses cannot create a candidate for a newer context. Unexported history joins existing leave
and Save guards. The accepted/corrected values compile through evidence into a separate copy;
rejected and pending proposals never compile.

### Filtered bulk review

Filter proposals by tool, kind, criterion and agreement/disagreement with a selected tool or
human comparison. Selection begins empty and is explicit. Preview lists every selected proposal
and its effective payload before confirmation. Apply writes one ordinary review event per item
with the same reviewer, timezone-aware time and note; the result is byte-identical to applying
those individual reviews in that same order. Blocked items or missing source/card references
cannot be selected or applied; revalidate all selections atomically at confirmation. No implicit
accept-all operation or automatic selection is offered. Add property tests for bulk/individual
byte equality and a reachable blocked-item-check mutant, alongside the existing verification plan.

## Edge cases and refusals

- Stale fingerprints allow historical inspection/export only. No automatic rebinding.
- Two tools on one cell, or a tool and a human, appear in adjacent columns with originals,
  effective reviewed payloads, sources and times. Equality uses exact label equality or exact
  normalized numeric/unit equality, not the ranking tie tolerance. Different units are
  incomparable until a human supplies an explicit conversion claim. Ranges stay ranges.
- Agreement is descriptive, not independent validation; shared sources are disclosed. Conflicting
  claims are never averaged. Even identical accepted claims do not bypass the compiler's single
  accepted claim per cell: the analyst selects one active evidence claim, retaining all other
  proposals for comparison. Accepting a conflicting active claim is refused until the earlier
  active claim is explicitly rejected/superseded by a recorded review. No last-write-wins rule.
- A pending item, missing card/source, invalid target, stale output or unresolved disagreement
  becomes an Open Question with affected IDs and the next human action. Rejecting a proposal
  resolves its pending question but preserves the original disagreement and review history.
- A tag is not a measurement, feasibility failure or preference penalty. A source assertion with
  no numeric/categorical measurement stays an annotation. A range is not converted into a
  distribution. Tool confidence never breaks a conflict or selects a source.
- Import refuses nonfinite values, malformed subjects/payloads/metadata, unsupported versions and
  confidence outside its declared scale. Acceptance/correction refuses unknown subjects, unresolved
  source/card references, unknown effective labels, incompatible units and correction payloads.
  Unknown labels/units may be corrected with a documented transformation; changing subject/kind or
  tool metadata requires a new linked proposal. A missing registry entry can be supplied locally,
  with the required digest, without changing the original proposal. Contradictory review events,
  unreviewed compilation and silent type conversion are refused. Never execute code,
  contact a provider, fetch a reference or infer weights from an imported output.

## Demonstrations and verification plan

Use invented Option A/B companies for an anonymised venture-screening intake: two external label
proposals on a categorical sector criterion, a corrected stage label, a rejected numeric claim,
a risk tag and a suggested source assertion. A supplier-risk classification demo exercises the
same kinds and reviewer workflow without investment terms. Both carry invented source references
and make clear that acceptance is a local human assertion, not a factual endorsement.

Concrete demo cases (all labels, values and references are invented; these are design tables,
not implemented import fixtures). Every row will carry the bound fingerprint, opaque local tool
ID/version, model-card reference/digest, run timestamp and cited synthetic source records. A
reported confidence such as 0.83 remains metadata in every review outcome.

| Venture-screening subject | External proposal | Human review | Retained/compiled effect |
| --- | --- | --- | --- |
| Option A / sector (`hardware`, `software`) | An external classifier tool: `software`; a second tool and a human: `hardware` | Correct the first to `hardware`; reject the second as not selected for compilation | Both originals and the human comparison remain adjacent; one corrected cell claim compiles |
| Option B / stage (`early`, `scaling`) | An external classifier tool: `early` | Accept, citing `local:synthetic-brief-b` (self-reported) | One accepted categorical cell; source classification stays disclosed |
| Option A / alternative tag | An external model: `follow_up_required` | Reject with reason | No criterion, penalty or feasibility failure is invented |
| Option B / suggested source claim | “A pilot is reported”, citing the same synthetic brief | Leave pending | An Open Question; no accepted fact or measurement |

| Supplier subject | External proposal | Human review | Retained/compiled effect |
| --- | --- | --- | --- |
| Option A / supply risk (`low`, `medium`, `high`) | An external classifier tool: `high`; another tool: `medium` | Correct the first to `medium`; retain the other pending | Show original disagreement and effective agreement, never an averaged risk score |
| Option B / supply risk | An external classifier tool: `low` | Accept with `local:synthetic-audit-b` (independent) | One accepted categorical cell |
| Option B / numeric score, unit `1` | An external model: 0.91 | Reject before any proxy activation | Original numeric proposal/card remain visible; the score never enters a value tree |
| Option B / alternative tag | `capacity_check`, source classification unknown | Accept the annotation | Kept in the compilation bundle; no measurement or weight effect |
| Option A / suggested source claim | “A delivery window is reported”, `local:synthetic-terms-a` | Leave pending | Source-review question, not an inferred performance value |

Independent tests reconstruct canonical JSON/CSV payloads and reviewed cell selection without
importing the application. Compare the compiled measurements and project bytes against the
existing evidence compiler, with untouched original/library bytes. Properties cover CSV/JSON
parity, history replay, ordering, correction preservation and no effect of confidence on any
numerical result. API/browser cases cover two-tool/human comparison, all three review outcomes,
Open Questions, stale/late responses, changed acknowledgement and reopen/export. Mutants remove
mandatory review, original preservation, fingerprint binding, source checks, single-cell selection,
confidence isolation or late-response guards. Prove each mutant is reachable and the unmodified
suite passes. Run the full gate and byte-identity script; record actual counts and limitations.

## Excluded

Provider connections, model execution/training, automated reviews, implicit proxy activation,
weight suggestions, outcome prediction, shared accounts, signed identities and automatic source
retrieval. The offline agreement benchmark is a separate development.

## Open owner decisions

1. **Non-cell storage:** recommend reviewed tags and source assertions in the compilation bundle,
   with no numerical/project-schema effect. Add an explicitly migrated annotation field only if
   persistence in project files is required.
2. **Multiple reviewed cell proposals:** recommend preserving every comparison while allowing
   exactly one active accepted evidence claim per cell, reusing the current compiler gate.
3. **Confidence vocabulary:** recommend the explicit scale/meaning metadata object above; never
   rescale or use it analytically.
4. **Import atomicity and limits:** recommend all-or-nothing structural import, retaining blocked
   semantic issues for correction, 8 MB, 2,000 proposals and
   2,000 review events, aligned with the existing workspace boundaries.
5. **Demonstrations:** recommend invented Option A/B data in both domains, with accept, correct
   and reject examples and no real profiles or tool names in repository content.

## Owner decisions

Approved by the owner on 1 November 2026. All five recommendations accepted, as recorded below.

1. Reviewed tags and source assertions live in the compilation bundle; no project-schema change.
2. Every comparison is preserved; exactly one active accepted evidence claim per cell.
3. Confidence is `{value, scale, meaning}` metadata only; never used analytically.
4. All-or-nothing structural import; semantically blocked rows retained for correction; limits
   8 MB, 2,000 proposals, 2,000 review events.
5. Invented Option A/B demos in both domains with accept, correct and reject; no real names.

**Amendment A — bulk review.** Add a filtered, multi-select review action, filtering by tool,
kind, criterion, agreement or disagreement with another tool or a human. One action writes one
separate review event per selected proposal, with the same reviewer, time and note. Confirmation
lists every affected proposal before application. There is no accept-all default, auto-selection,
or inclusion of items with blocked issues, missing sources or missing model cards. Property tests
must prove bulk equals the same individual reviews byte for byte; add a reachable mutant that
skips the blocked-item check.


## Implementation contract

The generic producer file is `ProposalIntake` version 1: fingerprint, original proposals and local
registries, optionally including a human-only dossier for comparison. `ExternalProposals` workspace
version 1 wraps it with the source snapshot, append-only review events, append-only registry-supply
events and a canonical digest. Both are new formats. Supply events add missing local sources/cards;
they cannot overwrite an existing registry entry or any original proposal/review. JSON Schema and
the exact CSV header are published in `docs/schemas/`; CSV and JSON normalize to identical workspaces.

An intake imported against the wrong project is explicitly unbound: its source snapshot is null,
its originals can be inspected/exported, and reviews, registry changes and compilation are blocked.
It is never assigned the open project's fingerprint. A workspace carrying history requires its
exact retained source; a compilation is reconstructed only against that source. No existing project,
evidence workspace, result or decision-record format changes.

The outer proposal compilation retains all metadata and annotations around an unchanged nested
evidence compilation. The nested bundle can be cited by existing version-2 decision records;
keep/cite the complete outer bundle alongside it for model cards, original units and supplemental
references. A corrected unit is explicit in the adapted claim while the original unit remains in
the intake. Exact comparison flags distinguish agreement, disagreement and incomparable values;
a mixed set does not turn an incomparable value into a disagreement. Comparison columns retain
all sources without a combined quality grade.

Bulk review uses the ordinary per-event transition, after an additional atomic eligibility check.
A CLI review first prints every affected proposal and a confirmation digest; repeating with that
exact digest writes the new file. GUI confirmation lists every selected item before applying its
candidate. Selection starts empty and filters never select rows. Review and compilation context
keys reject obsolete responses and invalidate acknowledgements. Files and exported artifacts are
limited to 8 MB; the encoded HTTP wrapper has a separate 24 MB pre-parse bound. Registry limits,
string/depth limits and the complete interchange contract are documented with the schemas.

See the [verification record](../development/external-proposals-verification.md) for actual gate
counts, byte identity, mutation reachability and remaining interface/storage limits.
