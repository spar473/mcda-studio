# Documentation

| If you want to… | Read |
| --- | --- |
| Use the application | [User guide](user-guide.md) |
| Understand the mathematics | [Specification](mathematics/specification.md) · [Method limitations](mathematics/method-limitations.md) |
| Understand how it is built | [Architecture overview](architecture/overview.md) · [Project file schema](architecture/project-schema.md) ([JSON Schema](architecture/project_schema.json)) |
| Use the HTTP API | [API contract](api/contract.md) · [OpenAPI document](api/openapi.json) |
| Pick up development | [Testing](development/testing.md) |
| See what was verified | [Validation](development/validation.md) · [Installation and startup](development/package-b-verification.md) · [Library ownership and recovery](development/package-c1-verification.md) · [Visible model](development/package-d1-verification.md) · [Analysis retry](development/analysis-retry-verification.md) · [Measurement coverage](development/measurement-coverage-verification.md) · [Library backup and restore](development/library-backup-verification.md) · [Method seam](development/method-seam-verification.md) · [Value-based sorting](development/value-based-sorting-verification.md) · [SMAA-2](development/smaa-2-verification.md) · [PROMETHEE II](development/promethee-ii-verification.md) · [AHP](development/ahp-verification.md) · [Method comparison](development/method-comparison-verification.md) · [Feasibility check](development/feasibility-check-verification.md) |
| See direction, limits and plans | [Roadmap](../ROADMAP.md) · [Known limitations](development/known-limitations.md) |
| Operate/recover a local library | [Ownership, restore, backup archives and manual drill](development/library-recovery.md) |
| Plan next development | [Roadmap](../ROADMAP.md) |
| Read about the original study | [Original study citation and summary](reference/original-study/) |

## Design notes

The [Evidence Workspace](design/evidence-workspace.md) and
[integrated sprint verification](development/integrated-workspace-verification.md) describe the
graphical evidence review/export workflow and its pending independent-user checkpoint.
[Separate-copy provenance](design/separate-copy-provenance.md) and
[decision records](design/decision-records.md) describe compilation bundles, copy receipts and
version-2 records ([compilation checks](development/evidence-compilation-verification.md),
[record checks](development/decision-records-verification.md)).
The [calculation workspace](design/calculation-workspace.md) describes formula authoring, review
and undoable application, and the [factor-uncertainty plan](design/derived-uncertainty-verification-plan.md)
the isolated evaluator ([checks](development/calculation-workspace-verification.md)).

Each note gives the exact rules behind one part of the interface.

| Note | Covers |
| --- | --- |
| [Live model canvas (value-tree diagram and measurement coverage implemented)](design/live-model-canvas.md) | Value-tree diagram, options column, linked editing, weights, presentation and bounded visual follow-ons |
| [Library backup and restore (implemented)](design/library-backup-and-restore.md) | Backup, verify and restore commands, archive safety checks, size limits and failure behaviour |
| [Method seam (backend contract implemented)](design/method-seam.md) | Method capabilities, result union, records, schema-version rule and method selection for the method track |
| [Feasibility check (implemented)](design/feasibility-check.md) | Mandatory requirements on individual measurements, pass, fail or unknown beside every ranking, units, exact limits, no compensation |
| [Method comparison view (implemented)](design/method-comparison.md) | Every method's reading of one model side by side, typed errors per column, agreement on leaders and classes with method-specific reasons, no consensus score |
| [AHP (implemented)](design/ahp.md) | Pairwise judgements for criteria and alternatives, eigenvector priorities, CI and CR against a named random-index table, the most inconsistent triad, distributive and ideal synthesis, published oracle |
| [PROMETHEE II (implemented)](design/promethee-ii.md) | Net outranking flows and the PROMETHEE I partial order, four preference functions, PROMETHEE's own weights, directions and codings, the explanation against MAVT, published oracles |
| [SMAA-2 (implemented)](design/smaa-2.md) | Sampled rank and class acceptability under stated measurement and weight uncertainty, exact intervals, seeds, storage of ranges |
| [Value-based sorting (implemented)](design/value-based-sorting.md) | Ordered classes on the overall value, boundary rule, class sensitivity, audit sample, and the rest of the method seam: result union, version-2 records and schema, method view |
| [Analysis context](design/analysis-context.md) | Shared scenario/profile selection, request identity, stale-response protection |
| [Previews](design/previews.md) | Read-only value-function and weight previews on incomplete models |
| [Value-function editor](design/value-function-editor.md) | Graphical and tabular editing, candidates, Apply/Cancel |
| [Weighting and profiles](design/weighting-and-profiles.md) | Swing ratings, derived weights, profile management, reference integrity |
| [Sensitivity](design/sensitivity.md) | One-way sensitivity, exact crossovers, stability, ties |
| [Scenarios](design/scenarios.md) | Sparse overrides, saved defaults, comparison with Base |
| [Results and exports](design/results-and-exports.md) | Charts, heatmap, dominance, JSON/CSV/SVG, CSV text safety, bounds |
