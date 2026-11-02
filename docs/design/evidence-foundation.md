# Evidence sidecar foundation

This foundation now has a graphical [review/compile/export workspace](evidence-workspace.md)
with reproducible compilation bundles, and graphical [version-2 decision records](decision-records.md)
that cite those bundles. The CLI below still writes version-1 records. A
version-1 JSON dossier refers to one exact project fingerprint. Claims identify an alternative and
leaf, value and unit, source and location, date, description and source classification, human or
tool origin, optional tool version, and an optional stated numeric range. A tool proposal requires
an identifier. Independent-source classification is descriptive, not a judgement of accuracy.

An absent review is a proposal. A named reviewer explicitly accepts, corrects, or rejects each
claim, with a timezone-aware review time. Corrections retain the original claim. Only accepted or
corrected values enter the preview, and only one can be accepted per cell. A rejected or unreviewed
claim never fills a measurement. The preview reports missing cells, unreviewed and outdated claims,
and cells with differing unrejected claims. Those are visible warnings, not proof of quality and not
a rule that chooses a value. Existing project measurements remain as they were unless an accepted
claim explicitly replaces one. An independent source is not automatically trustworthy.

`mcda evidence preview` validates references, types, units, duplicate IDs and conflicting accepted
claims and emits a digest over the exact project, dossier, findings and proposed changes. The user
reviews this output. `mcda evidence compile` requires that digest, validates again, and writes a new
file using exclusive creation; it cannot overwrite the source or another existing file. Units must
match exactly, with no conversion. Invalid dossiers or stale previews do not compile. Compilation is
stable under claim reordering, although the dossier digest intentionally identifies the precise
serialized claim order. The range records the original claim and is not transferred to the project
or used as a distribution.

`mcda decision record` captures a separate JSON snapshot containing the decision owner, date,
selected alternative and rationale, unresolved assumptions, review triggers, exact project and
one or more completed analysis records. Optional evidence includes both the dossier and its source
project; creation recomputes compilation and refuses a mismatch with the recorded project. A
revision may reference a previous record whose digest is checked. The record's SHA-256 digest
detects accidental changes, but is not a digital signature or proof of authenticity. New records
are published without replacing an existing path; someone can still edit or delete local files
outside the application.

Graphical review and exported appended history are available in Evidence Workspace. There is no
signed reviewer identity, access control, evidence fetching, unit conversion, decision-record
browser, Markdown export or review reminder. A user can edit a sidecar outside the application;
reviewer identity is a local assertion. A dossier is linked to the original project, so retaining
both the dossier and source project is necessary for later reconstruction. CLI output is not yet a
complete provenance bundle and existing direct measurements can lack evidence. Decision records can
embed that bundle; record management and dossier-version migrations remain work for the next increment.

## Follow-up: derived uncertainty

For deterministic formulas, use a closed expression grammar and explicit unit algebra, with stable
references and cycle detection. For stochastic runs, sample named fundamental inputs once per draw,
reuse the same draw wherever the factor is referenced, and evaluate the expression graph each time.
The existing SMAA shared-draw groups represent a common quantile across marginal distributions; they
cannot represent an arbitrary formula graph or arbitrary dependence. Do not approximate a nonlinear
formula's output with a uniform interval. Until the graph and shared-factor sampler are implemented
and independently checked, formula uncertainty must be explicitly unsupported.
