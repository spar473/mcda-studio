# Hierarchical swing weighting and preference profiles

How the **Weights** screen works and how preference profiles are managed. The screen makes the
engine's weighting visible and lets you elicit it. It does not redefine the mathematics.
The formulas are in the [mathematical specification](../mathematics/specification.md) and the wire
format is in the [API contract](../api/contract.md).

## 1. What a swing rating means

A swing rating is **not** a percentage of importance. It is the decision maker's judgement of how
valuable it would be to move one criterion from its **worst** to its **best** defined level, while
the other branches stay at their worst levels. Only the *ratios* between siblings carry meaning.

Giving Founder Expertise 100 and Team Coverage 65 says that the full stated swing in founder
expertise is worth about 100/65 ≈ 1.54 times the full stated swing in team coverage. It does not
say founder expertise is "100% important". Because the judgement is attached to a stated range,
**changing a scale range changes the meaning of its rating** — which is why the application raises a
swing review when an effective range changes, and why the engine's `weight_basis` sentence is shown
beside the inputs.

The GUI suggests 100 for the most valuable swing in a group as a convention only. Raw ratings are
uncapped, need not sum to 100, and imported values above 100 are kept exactly as supplied.

## 2. Three quantities that are never interchangeable

| Quantity | Reference level | Source |
| --- | --- | --- |
| Raw swing rating | its own sibling group; ratios only | elicited from the user, stored |
| Local weight λᵢ = rᵢ / Σrₖ | its own sibling group; the group sums to one | derived |
| Branch share (objective) | the overall goal; a group's shares sum to its parent's share | derived |
| Global weight (leaf) | the overall goal; all leaves sum to one | derived |

The Weights screen labels all four, gives each its own column, and keeps a legend visible rather
than relying on hover. Bars encode **local** weights only, so bar lengths are comparable inside a
group but not between groups. No derived weight is editable anywhere: there is no operation that
writes a local or global weight.

Selecting any item shows its derivation — each step down its root path with that step's raw rating,
local weight and branch share, ending in the global weight. Every number in that table comes from
the engine; the browser performs no weight arithmetic. In the
[NZ deep-tech VC example](../../examples/nz_deeptech_vc/), selecting Founder Expertise shows Team's
share 0.2941, the local Founder Expertise share 0.6061 within Team, and the resulting global weight
0.1783.

## 3. Zero, missing and invalid stay distinct

| Input | Meaning | Effect |
| --- | --- | --- |
| A rating of 0 | "this swing carries no value for me" | a valid local weight of 0, if a sibling is positive |
| No rating | no judgement has been supplied | `MISSING_JUDGEMENT`; the group derives nothing |
| All siblings 0 | normalisation is undefined | `ZERO_SUM_JUDGEMENTS`; the group derives nothing |
| Negative or non-finite | not a swing judgement | `INVALID_JUDGEMENT`; refused |
| An only child | its weight is necessarily one | local weight 1, **no rating is invented** |

A missing rating is never read as zero and a zero is never reported as missing; the rating cell
states which it is. An only child shows "only item (weight 1)" and "Not supplied; not required",
and its sibling total is reported as not supplied rather than as a number. If a rating *is*
supplied for an only child it must still satisfy the ordinary validity rules.

While any sibling group is invalid, **no** derived weights or bars are shown for the whole model —
an incomplete model is never dressed up as a partial but plausible weight set. Stated ranges remain
visible and reviewable in that state, because range information does not depend on the ratings.
Weight previews also work with an incomplete performance table: preview readiness and full model
evaluation readiness are separate judgements.

## 4. Swing cards and worst-to-best ranges

Each child gets a card showing the swing being judged. For a leaf that is its own stated range; for
an objective it is the list of its descendants' ranges, since the group swing is the combination of
them. Cards report the resolved domain, its source (`fixed`, `control_points`, `rating_range` or
`local`), the scale type and the unit.

Endpoints follow the value function rather than the raw numbers, so a **decreasing** cost criterion
reports its highest cost as the worst level and its lowest as the best. Labelled scales report
their anchors ("Very Low" → "Very High"), not numeric category codes, and a categorical scale is
annotated as having no intrinsic order. A locally anchored criterion names its source and warns
that its range depends on the current alternative set, so a changed range needs swing review.
A range that cannot be resolved says so, with the engine's diagnostics, and is never guessed.

## 5. Preference profiles

A profile is a named set of raw swing ratings with a stable id. Several profiles can hold different
decision makers' judgements over one shared value tree.

* **Create** adds a profile with no ratings. Nothing is imputed, and a draft profile with
  incomplete judgements is permitted and savable under the existing validation rules.
* **Duplicate** deep-copies the ratings into an independent profile. Later edits to either side
  never affect the other; no state is shared.
* **Rename** changes the display name only. Ids, ratings and every reference stay intact.
* **Delete** refuses the last remaining profile, and refuses a referenced profile unless the user
  explicitly chooses a replacement (see below).
* **Select** chooses which profile you are viewing and editing. This is session state only.

Every profile edit is one atomic operation through `project_service`, so it is one undo step and
one unsaved-change transition.

### Viewing versus the saved default

Switching the viewed profile does **not** change the project. It creates no edit, no undo entry and
no unsaved-change marker, and it never rewrites `analysis.weight_profile_id`. Changing the saved
default is a separate, explicitly confirmed action, and it changes only that one field — the saved
scenario, method and parameters are preserved. The panel always states both the profile being
viewed (with its stable id) and the saved default, so the two cannot be confused.

Expanding or collapsing part of the weight tree, selecting a criterion, hovering a bar, scrolling
and acknowledging a swing-review warning are likewise all transient: none of them touches stored
data or the undo history.

### Resolution precedence

`Project.resolve_profile` is the authority, and the GUI mirrors it for display only:

1. the explicitly selected profile, when one is supplied;
2. otherwise the selected scenario's profile, when the scenario names one;
3. otherwise the project's first profile, as the documented fallback.

An id that names no existing profile is an error, not a cue to pick another profile: the engine
raises `UNKNOWN_REFERENCE`, and the screen names the unresolved id and shows no weights instead of
claiming the project has no profile.

### Reference integrity on deletion

A profile may be resolved by a scenario or by the saved analysis configuration, either explicitly
or *automatically* as the first profile. Deletion lists those dependencies and refuses to proceed
until the user either cancels or names a different existing profile as the replacement. Every
affected reference — scenario and saved analysis alike — is then rewritten in the same immutable
edit, so the operation can never leave a dangling profile id behind and never falls back silently
to whichever profile happens to be first afterwards. An automatic reference is deliberately made
explicit by the replacement, so deleting the first profile cannot quietly re-point a saved analysis
at a different one. One undo restores the whole change, references included.

## 6. Asynchronous identity

Every weight preview is keyed by project fingerprint, complete configuration, resolved scenario and
resolved profile, and the response is verified against the live context before it is displayed. A
response that belongs to an obsolete context — most importantly a profile the user has already
switched away from — is discarded, and in-flight requests are aborted on every change. A previously
ready result is hidden immediately when the context changes, so one profile's weights can never be
read as another's, and a late or cancelled response cannot overwrite the current screen.

## 7. Supported weighting methods

Only swing weighting is supported. A profile with any other `method` produces
`UNSUPPORTED_WEIGHT_METHOD`. For how profiles are used elsewhere, see
[sensitivity](sensitivity.md), [scenarios](scenarios.md) and [results](results-and-exports.md).
