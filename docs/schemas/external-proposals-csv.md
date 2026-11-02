# Local proposal interchange version 1

[JSON intake](external-proposals-v1.schema.json), [review workspace](external-proposals-workspace-v1.schema.json)
and [compilation](proposal-compilation-v1.schema.json) are published JSON Schemas. Python is the
validation authority, including cross-field rules; no schema URI is fetched. Generate/check with
`scripts/export_proposal_schemas.py [--check]`. Tests compare every published schema to its model.

A producer supplies an intake with the exact project fingerprint, sources, locally retained model
cards, original proposals and optional human comparison dossier. Import creates a new workspace
containing that intake, its exact source project, an empty review history and a canonical SHA-256
digest. If the fingerprint differs, import retains an explicitly null source snapshot for
historical inspection/export only; reviews, registry additions and compilation remain blocked.
A workspace reopens by replay, not by trusting a stored current state. Separate registry
supply events may add missing entries but cannot replace an original entry; originals remain intact.
New sidecars are version 1; no old project, dossier, workspace or result type changes.

CSV is UTF-8, without a byte-order mark, comma-delimited with ordinary RFC-style double quoting,
one proposal per row, using this exact header order:

```text
schema_version,project_fingerprint,proposal_id,proposal_version,kind,alternative_id,criterion_id,payload_json,tool_id,tool_version,model_card_id,model_card_digest,run_at,confidence_json,source_ids_json,replaces_proposal_id
```

Both version columns contain the literal `1`. The payload is JSON with its own matching `kind`;
confidence is JSON or an empty field when absent; source IDs are a JSON array. A blank criterion
or replacement ID means absent. Numeric values appear only as finite JSON numbers in payloads,
never as empty strings, booleans or numeric strings. Unit fields are explicit strings or JSON null.
Identifiers and strings are literal; no expressions, spreadsheet formulae or code are executed.
The parser rejects duplicates, extra/missing headers, ambiguous delimiters and malformed rows,
reporting physical CSV line numbers. No valid subset is imported after a structural error.

CSV is accompanied by one local registry JSON containing exactly `project_fingerprint`, `sources`,
`model_cards` and `human_dossier` (null if absent). The source and card registries have IDs as keys.
Examples of both formats are in `examples/external_proposals/`; JSON and CSV normalize to the same
canonical workspace encoding and digest, sorting original proposals by ID without changing their payloads. CSV exports
intake only; review history always travels in workspace JSON.

Model-card digests are SHA-256 of the normalized card's JSON: sorted object keys, UTF-8,
`ensure_ascii=False`, separators `(',', ':')`, no trailing newline. Workspace/bundle digests use
that same encoding of their complete normalized object excluding only the outer `digest` field.
Defaults participate. Digests detect accidental changes and do not authenticate tool or reviewer
identities. Confidence is `{value, scale, meaning}`: `scale` is `unit_interval` or an explicit
`{name, lower, upper}` object, with the value inside those finite inclusive bounds. It never enters
mathematics, weighting, source selection or conflict resolution.

Files and generated exported artifacts are limited to 8 MB, intakes to 2,000 proposals and histories
to 2,000 reviews. Registries have at most 2,000 entries each, strings at most 10,000 characters
(with tighter typed-field limits), JSON nesting at most 32, and reference arrays at most 64 IDs.
The HTTP transport wrapper is independently bounded to 24 MB before JSON parsing, including
chunked bodies. Structural refusal is atomic. Semantic issues remain blocked for review; correcting
an unknown label/unit preserves the original. Changing kind/subject/tool identity needs a new
linked proposal. Missing inputs remain missing and differing sources are never averaged.
