# Calculation workspace: authoring and applying reviewed formulas

The calculation workspace lets an analyst create and revise source factors, unit definitions and
formulas in the interface, review them, and apply the reviewed result to the open project, without
editing JSON by hand. It is a separate local file, like the
[Evidence Workspace](evidence-workspace.md). The project schema, the version-1 calculation model,
the bounded interpreter and the [compilation gate](derived-measurements.md) are unchanged.

## Why a sidecar, not formulas inside the project

Embedding live formulas in the project would need a schema migration, provenance snapshots inside
undo history, referential integrity on every tree/alternative edit and a decision about what a
project without its formulas means for older installations. None of that is needed to author,
review, apply and reproduce a calculation:

- the workspace keeps the full authoring and review history beside the project;
- applying produces exactly the project the existing compilation gate would compile, as one
  ordinary undoable edit;
- the existing calculation bundle documents each application, and decision records already cite
  bundles by exact fingerprint.

The cost is that formulas live outside the project file: keep the exported workspace with it.
Embedding remains a candidate once real use shows that a separate file is a burden; it would need
its own schema version, migration and atomic undo/redo tests first.

## Format (version 1)

`CalculationWorkspace` holds the project snapshot it starts from, the original version-1 model
(possibly empty) and an ordered, append-only list of events, with a SHA-256 digest that detects
accidental changes, not deliberate rewriting. Reopening replays the events in Python; there is no
trusted cached current model.

| Event | Effect on replay | Refused when |
| --- | --- | --- |
| `unit` | Declares a unit's base dimensions | The unit is `1`, already defined, or the limit is reached |
| `source` | Defines or redefines a factor (value, unit, source reference, human/tool origin) | It carries a review, or the ID names a formula |
| `formula` | Defines or redefines a formula and its optional target measurement | It carries a review, or the ID names a factor |
| `review` | Accepts, corrects (factors only) or rejects one factor or formula | The entry is unknown; a formula correction; a non-numeric factor correction |
| `remove` | Removes a factor or formula | The entry is unknown |
| `apply` | Applies the reviewed calculation to the bound project | The recorded review digest, outcome or resulting fingerprint does not reproduce |
| `rebind` | Binds the workspace to another revision of the same project, recorded in full | Another project ID, or the same revision |

A definition never carries a review. Redefining a factor therefore leaves it pending: every
calculation that depends on it is unavailable until the factor is accepted again. The earlier
definition and its review stay in the history. A formula's acceptance is about its expression,
target and unit, so revising a factor does not reset formula reviews. Accepting a formula requires
it to calculate (all its inputs accepted, its dimensions consistent, its target valid); the
interface shows that check before acceptance. Rejection is always available. These acceptance
checks guard the interface; the preview remains the authoritative gate on replay.

Unit definitions are never redefined: a different dimension needs a new unit name, so no accepted
formula silently changes meaning.

## Relationship to the open project

Python classifies the open project against the workspace's chain of bound revisions (its start and
every `apply` or `rebind`):

| Relationship | Rule | Allowed |
| --- | --- | --- |
| `bound` | The open project is the latest bound revision | Edit, review, apply, compile a separate copy, export |
| `earlier` | It is an earlier bound revision, for example after Undo of an application | Read; Redo returns to `bound`; rebind is explicit |
| `different` | Anything else | Read; rebind to the open project is explicit and recorded |

A raw model file bound to another revision can be read, not exported as a workspace or rebound,
because there is no snapshot of the project it was written for. There is no automatic rebinding,
no loose fingerprint comparison and no rewriting of an artifact.

## Applying

Applying requires the bound relationship, an error-free preview, the exact review digest the
analyst acknowledged, and at least one calculated value that differs from the current measurement.
Python reruns the existing `compile_copy` gate on the bound project and returns:

- the candidate workspace with its `apply` event and the resulting fingerprint;
- the target assignments, in compilation order;
- the version-1 calculation bundle for this application.

The editor applies the assignments as one `set_performance` batch, so the whole application is one
undo step, and checks that the resulting fingerprint equals the bundle's compiled fingerprint before
confirming the candidate. A failed edit discards the candidate. Because the applied project is
byte-identical to the compiled copy, the bundle's relationship to the open project is `compiled`
and a version-2 decision record can cite it without any schema change.

Applying replaces existing manual values only for the listed, acknowledged targets; it never clears
a measurement. Targets with stated SMAA-2 uncertainty remain refused. Missing inputs stay missing.

## Stale context, undo and saving

- The target acknowledgement is keyed to the preview digest, which covers the project, model,
  calculations and issues. Any confirmed event, recalculation, project edit or undo clears it.
- Responses for an earlier context are discarded; a candidate whose fingerprint differs is refused.
- Workspace events are append-only. "Discard calculation changes since export" returns to the last
  opened or exported workspace; there is no per-event undo inside the workspace.
- Project Save stores the project only. While workspace events are unexported, Save and leaving the
  editor direct the analyst to export the workspace first, as for unexported evidence reviews.
  Downloads are not automatic history: a workspace that was never exported cannot be recovered.

## Limits

- At most 2,000 events and the existing model limits (256 factors, 128 formulas, 128 units);
  rebind events embed the full project, so the 8 MB request bound applies.
- Identities are local assertions; digests are unsigned and detect accidental changes only.
- Applying/compiling writes deterministic values only. The separate factor-run editor follows
  the [uncertainty plan](derived-uncertainty-verification-plan.md); no distribution is inferred or
  embedded in a project.
- No autosave, no merge of two workspaces and no rebinding across project IDs.
