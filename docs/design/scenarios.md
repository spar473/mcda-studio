# Scenarios and comparison

A **scenario** is a named variation of the base model. It can:

- point at a weight profile;
- **override** the value function of individual leaf criteria (sparse overrides).

Everything else is shared with the base model: the criteria tree, measurements, units and scale
anchor policies.

## Managing scenarios

Open **Scenarios** to create, duplicate, rename or delete a scenario, and to choose one for viewing.

**Overrides.**

- **Editing.** **Edit override for …** opens the same graphical and tabular
  [value-function editor](value-function-editor.md). It labels which functions are inherited from
  the base and which are overridden.
- **Apply** creates or replaces one sparse override.
- **Reset to Base** removes the override, so later changes to the base are inherited again.
- **Cancel or Escape** discards pending changes.

**What can and cannot change.** Scenario editing locks measurements, structure, units and anchor
policies. Control-point domains and direct-rating ranges stay editable. A criterion needs a shared
scale and an existing base or override function before its editor can open. Incomplete local
measurements never produce invented anchors.

**Undo and saving.** Each committed operation is one undo step. Save and reopen use the usual JSON
store with revision-conflict protection.

**IDs and copies.**

- **Renaming** keeps the scenario ID.
- **Duplicating** creates a new ID and independent copies of the overrides.

## Viewing versus saved defaults

Choosing a scenario or profile to *view* is transient. It creates no edit and no unsaved change.

- **Saving a default.** **Use viewed scenario as saved default** updates `analysis.scenario_id`.
  Then Save.
- **What the editor opens with.** Base / Automatic, whatever the saved defaults are.
- **Where saved defaults apply.** To CLI and API calls that omit a configuration. An explicit Base
  view takes precedence.
- **Deleting the saved-default scenario.** You must choose Base or another scenario to repair the
  default in the same operation. Undo restores both together.

## Profiles in scenarios

A scenario's profile dropdown stores a *reference*. Under automatic resolution, analysis uses:

1. the scenario's profile;
2. otherwise the first project profile.

An explicitly viewed profile overrides both. Comparison clears the scenario for the base side but
keeps an explicit profile. So under Automatic, Base and the scenario can use **different profiles**.
The interface names both and explains that score changes may come from weights as well as
functions. Deleting a profile that a scenario references requires choosing a replacement (see
[weighting and profiles](weighting-and-profiles.md)).

## Comparison: one scenario versus Base

The comparison service calculates for every alternative:

- scores and deltas
- competition ranks
- tied winner sets
- whether the ranking and the winner changed

**How rows are joined.** The frontend joins rows by stable alternative ID, never by name or array
position.

**What counts as a change.** A ranking change includes gaining or losing a tie, even when the
sorted order of IDs looks the same.

**What scores mean.** Scores are compensatory MAVT preference values, not probabilities or returns.

**On narrow screens** the comparison table scrolls horizontally, including by keyboard.

## Request safety and validation

**Request keys** include the revision, full configuration, scenario and profile context, and the
relevant parameters. Comparison also checks the echoed fingerprint, scenario IDs, resolved
profiles, configuration and alternative ID set. Out-of-date answers cannot overwrite newer ones.

**Validation is scoped to the model being analysed:**

- **Problems panel.** Lists problems in every saved configuration.
- **An invalid scenario elsewhere** does not block a valid base analysis.
- **An invalid selected configuration** shows diagnostics. Base output is never substituted for it.
- **Structural problems** such as duplicate IDs still block analysis.

**Sensitivity.** Sweeps and probes follow the selected scenario and profile, use the engine's
authoritative path shares and save nothing. The selected criterion survives revalidation, and stale
results are hidden at once. Text values come from exact probes (see [sensitivity](sensitivity.md)).

## Ranges and swing review

Changing a function's range or shape can change what a worst-to-best swing means.

- **Range warnings** ask you to review the swing judgements and the additive model's compensatory
  assumptions.
- **Acknowledgements** are session-only and tied to their context. They never edit judgements or
  fingerprints, and a materially different context asks again.
