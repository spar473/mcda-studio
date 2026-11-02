# Live model canvas: first implementation specification

**27 October 2026 — measurement coverage implemented locally.** The canvas now includes indexed
measurement presence/issues, stable-ID editor destinations and focus return, and explicit 20 × 20
paging (also at the measurement destination). [Executed checks](../development/measurement-coverage-verification.md)
record counts and five timing runs per fixture. Human usability and screen-reader checks remain
pending. This note supersedes the original coverage-proposal status retained below.

Status: D1 Visible model implemented locally, 2026-10-26, then the Canvas was redrawn as a
left-to-right value-tree diagram with an options column, editor shortcuts, engine weights,
structuring hints and a presentation view (see [Canvas diagram](#canvas-diagram-implemented-locally-2026-10-26)).
D2's coverage matrix and the remaining follow-on scope are still proposals. See
[D1 verification](../development/package-d1-verification.md) for executed checks and remaining
human acceptance. The full specification below retains the combined D1/D2 design; measurement
coverage (cells, counts, paging) is **not** part of the current implementation.

## D1 implementation boundary

`EditorScreen` owns transient Canvas/Outline and collapsed IDs; its existing draft and criterion
selection remain authoritative. `TreePanel` retains all existing structural actions and confirmations.
`ModelTree` renders flat HTML treeitems with explicit levels, sibling positions and stable IDs;
`model/visibleTree.ts` indexes and walks relationships iteratively, including structural-error checks.
No graph library, API, schema field or numerical calculation was added. `ProjectPanel` is reused
for the synthetic goal and `Inspector` for criteria. Presentation state is discarded on project
switch/reload. Accepted edits use the existing operation/session/save path.

Arrows/Home/End select and focus rows; Space selects; Enter or Edit selected item focuses the
existing Name editor; Delete opens the existing confirmation for the focused ID. Collapsing an
ancestor of the selection selects/focuses that ancestor; external selection reveals its ancestors.
Accepted deletion clears affected selection and focuses Add top-level objective; failed deletion
retains selection. Undo removing a focused node also returns focus to that control.

Names wrap, IDs distinguish duplicates, and indentation caps at six levels to preserve reading
space; deeper rows explicitly show actual level and parent ID. Long Inspector breadcrumbs expand
on demand. Current validation issue counts propagate to ancestors and unconfigured leaves show
Setup needed. These are input/setup messages, not evidence verification or decision quality.
Malformed structures render every incoming item in a labelled flat fallback with diagnostics;
structural edits are disabled until the source hierarchy is corrected. The Problems panel remains
available for project-level/unmapped issues. Existing preview guards are reused unchanged.

## Canvas diagram (implemented locally, 2026-10-26)

The owner asked for the Canvas to read like the value-tree figure in the original study report
(Figure 1): goal on the left, objectives, then leaf criteria, with the options in a column on the
right. It is still a MAVT **value tree**, not a sequential decision tree: no decision or chance
nodes, and options are not descendants. Outline is unchanged.

| Part | Behaviour and boundary |
| --- | --- |
| Layout | `model/diagram.ts` places each visible terminal (leaf or collapsed branch) on its own CSS-grid row and spans each branch over its visible descendants, iteratively. Columns are tree depth. Cards keep the D1 flat `treeitem` semantics, roving focus and keys; connectors are decorative SVG measured from the laid-out cards (`aria-hidden`) |
| Goal | The existing goal button moves into the diagram's first column; its Swing chip opens the top-level weight group |
| Options column | All alternatives in a separately coloured region, fed by one dashed bracket from every visible terminal, with “each option is scored on all N leaf criteria; options are not part of the hierarchy”. N counts every structural leaf, collapsed or not. Each option opens its existing name field on Alternatives. No per-pair lines (the figure's 32 lines would be 10,000 at the supported maximum) and no coverage cells: those remain D2 |
| Chips | Objectives (and the goal) show **Swing**, with the number of sibling ratings missing in the resolved profile (presence only; an only child needs none). Leaves show **Value fn**, or **Value fn needed** when scale/function are unset. Swing opens that group on Weights and focuses its first rating; Value fn opens the existing value-function editor; Value fn needed selects the leaf and focuses Measurement type. Chips are pointer shortcuts (`tabIndex=-1`); the Inspector's “Edit swing weights for this group” and existing value-function button are the keyboard routes |
| Weights | Optional (“Show weights”, on by default). The existing weight-preview endpoint supplies local weight, branch share and global weight; cards show `local · of goal` to three decimals and the accessible name uses the exact terms. Connector thickness follows the share of the goal. Shown only when `weights_ready`; otherwise “none are shown or assumed”. The request key excludes the selected criterion, so selecting, collapsing and scrolling never request weights; edits and profile/scenario changes do, with the existing key gating against late responses. Exact values stay on the Weights tab |
| Hints | Value-focused thinking prompts in the diagram: objectives before options (counting existing options), ranges before weights (counting leaves still needing a measurement and range), then options. The Inspector asks “Fundamental or means?” for objectives. Text only, no scoring |
| Presentation | “Present” shows a read-only, full-width diagram with title, description, resolved profile/scenario, live-draft status (“unsaved changes” or the saved revision), open engine errors and the preference/evidence caveats. Selection and collapse are local; Enter/Delete/undo shortcuts do nothing; Escape or “Exit presentation” returns focus to Present. It is the live draft, not a frozen snapshot |

Accepted limitation: models wider than the panel scroll horizontally inside the labelled
“Model diagram” region; at 1440 px the four-column VC example needs a short scroll to reveal the
options column, and the presentation view shows it whole. No graph library, API, schema or
numerical change was added.

### Ideas from the landscape review, applied to the canvas

Sources are the [landscape and options](../development/landscape-and-options.md) review; its
evidence caveats apply. “Built” means implemented locally in this pass.

| Source | Idea | Applied as | Status |
| --- | --- | --- | --- |
| Value-focused thinking, PrOACT (Keeney; Hammond, Keeney and Raiffa) | Objectives before options; fundamental versus means objectives | Diagram hints and the Inspector prompt | Built (prompts only; no automatic means-objective detection) |
| Hiview3, Web-HIPRE, Logical Decisions (background) | Weights read on the value tree itself | Engine local/branch/global weights on cards; thickness by share of goal | Built (static display). Animated flows and per-profile overlays remain the weight-flow follow-on |
| Decision conferencing (Hiview3 practice) | A live model on screen for a group | Read-only presentation view | Built (no collaboration server; no frozen snapshot export) |
| The original study's value-tree figure | Goal → objectives → criteria → options, with method markers | Left-to-right diagram; Swing / Value fn chips as shortcuts | Built |
| Comparion, 1000minds, Delphi (group elicitation) | Show where decision makers disagree | Profile comparison overlay: per-branch weight differences between two explicit profiles | Follow-on (needs the profile-comparison envelope) |
| M-MACBETH (background) | Elicit by qualitative difference judgements | Launch an elicitation helper from a Value fn or Swing chip | Option O7; method design first |
| DEXi, UTADIS, MR-Sort (sorting) | Class bands such as Proceed / Watch / Decline | Show class boundaries beside the options column | Waits for value-based sorting (P6) |
| JSMAA, robust decision making | How often an option holds a rank under uncertainty | Acceptability bars in the options column | Waits for SMAA (P7); sampled, never “holds for every weight” |
| DecideIT, Analytica | Decision trees and influence diagrams | Not applied: a different model with chance nodes | Out of scope by design |

## User goals and example interactions

A person building a fresh decision should see what they have built, what they still need, and
where to edit it before any ranking is possible. The primary diagram is a MAVT objectives/value
tree: **Goal → objectives → criteria**. Alternatives are options evaluated against its leaves,
not children in that tree. This is not a sequential decision tree; there are no chance nodes or
probability branches.

Example: “Choose a laboratory site” has objectives Cost and Research access, three leaf criteria
and three sites. The user adds Research access with the existing tree controls, adds its criteria,
renames a leaf and sees the canvas update after each successful edit response. Clicking that leaf
selects its existing Inspector. The coverage matrix says “7 of 9 measurements entered; 2 missing”.
Clicking an empty cell opens the correct measurement input; a numeric zero changes that cell to
Entered. Missing scale settings lead to the criterion editor instead. Collapsing Cost reduces
visual clutter while its badge still reports missing descendant inputs. No score is invented.

Once the model is valid, the user opens existing results to inspect contributions. The MVP does
not embed analytical overlays into the structural canvas. “Complete inputs” means inputs are
present and separately validated, not that this is a good decision or attractive investment.

## MVP scope and exclusions

Include a goal card, expandable objective/criterion hierarchy, stable-ID selection, validation
badges, distinct alternatives panel and linked alternatives × leaf-criteria coverage table.
Reflect accepted additions, renames, deletions, undo and redo from the current draft. Retain
ordinary forms/tables and existing structural controls, including their destructive confirmations.
Provide clear empty states, keyboard operation, readable names and restrained transitions.

Exclude weight-flow diagrams, new contribution calculations, advanced sensitivity animation,
new analysis methods, multi-user collaboration, free-form graph editing, graph persistence,
canvas export and drag-and-drop reparenting. Existing buttons for structural moves remain in the
ordinary tree view. Reparenting changes sibling weighting relationships and can discard leaf
models/performance data; a future pointer gesture needs an explicit semantics and recovery design.

## Layout and linked selection

Use the existing Model tab with a labelled **Canvas / Outline** view switch. The initial canvas
shows a vertically arranged hierarchy with modest indentation, branch connectors and HTML cards;
it need not require pan/zoom. Keep the outline available as a compact view. A responsive layout:

```text
Model: [Canvas | Outline]          [existing add/remove controls]
[Goal: project.title]              [existing Inspector / editing destination]
  ├─ Objective                      Name, description, measurement settings
  │   ├─ Criterion [inputs needed]   Selected node and issue details
  │   └─ Criterion
  └─ Objective                    [Alternatives — distinct heading/region]
      └─ Criterion                  Site A · 2/3 entered; Site B · 3/3 entered
[Coverage matrix: alternatives × all leaf criteria]
[existing validation panel / linked issue list]
```

On narrow windows stack the inspector and alternatives after the hierarchy, with a labelled
horizontal scroll area for the table. Keep full labels available without relying on hover;
wrap names, allow expanding long labels and show IDs/path when names duplicate. Connectors
communicate parenthood only. No arrows connect alternatives as tree descendants.

- The goal is a synthetic view of `project.title`, not a saved criterion with a new ID or weight.
  Selecting it opens/focuses `ProjectPanel` title/settings. Top-level leaves are permitted; do not
  invent intermediate objectives. An unconfigured leaf is labelled “Criterion · setup needed”.
- Node selection writes the existing `analysis.criterionId` via `store.selectAnalysis`. All views
  read that ID. Selecting a node reveals it and shows Inspector; an explicit Edit action/Enter
  focuses its name. Ordinary arrow navigation stays in the tree, avoiding focus theft.
- Alternatives are a separate region. Selecting a card highlights its matrix row; an Edit action
  opens `AlternativesPanel` and focuses its existing name editor. Add a focus-target prop/token to
  that panel: it currently has no external selection/focus API. Do not build a second name form.
- A matrix cell selects both stable IDs, highlights the corresponding leaf/row and opens the
  Measurements tab through the existing `focusCell` mechanism. If the leaf has no scale, open its
  Inspector/measurement settings instead and explain why. If a scale is available but invalid,
  open the input and its validation details; do not hide the issue behind a coverage badge.
- Column headings select/reveal a leaf; row headings select the alternative and expose Edit.
  Remember a return target so returning from an editor restores the selected row/cell and scroll.
  Navigating from validation uses the same destinations, not a separate canvas routing scheme.
- Collapsing a branch containing selection first selects/focuses that branch. External selection
  (issue, matrix heading or ordinary editor) expands the required ancestors. Collapsing alone
  never edits the project. Coverage always includes **all** leaves, not only visible branches;
  any later filter must label displayed versus total counts.

## State, actions and components to reuse

The only project source is `state.session.draft.project`, paired with that draft's validation
and fingerprint. Do not create a graph store, shadow editable node names, graph JSON, or a second
save path. Unsaved text inside existing commit controls remains a local field draft until its
normal commit event; canvas labels reflect the accepted project edit immediately, not on Save.
A failed edit retains the last accepted structure and displays the existing notice.

| Existing file/component | Reuse / bounded change |
| --- | --- |
| `frontend/src/components/EditorScreen.tsx` | Own view switch, destinations and focus return; pass current project/validation, existing `apply`, add action and context |
| `TreePanel.tsx` | Keep outline and destructive dialogs/move semantics. Extract a small shared structural toolbar/action controller only if duplication would otherwise be required |
| `Inspector.tsx`, `ProjectPanel.tsx`, `MeasurementEditor.tsx`, `ValueFunctionEditor.tsx` | Existing editors, candidate guards and commit actions; add focus destination where necessary |
| `AlternativesPanel.tsx`, `MeasurementsPanel.tsx` | Existing `add/rename/remove_alternative`, `set/clear_performance`; extend focus targeting without changing save semantics |
| `state/editorStore.ts`, `model/session.ts` | `apply(operations)`, `undo`, `redo`, `save`, save-copy/conflict handling; no parallel history |
| `state/analysisContext.ts` | Shared criterion selection and ID reconciliation; keep profile/scenario selection unchanged |
| `model/tree.ts` | `buildTree`, `leaves`, `pathNodes`, ordering and stable IDs; index/memoise if profiling requires |
| `model/issues.ts`, `ValidationPanel.tsx` | `parseIssuePath`, criterion/performance/judgement issues and linked destinations; do not duplicate mathematical validation |
| `state/useAnalysisRequest.ts`, `usePreviews.ts`, `useAnalysisRecord.ts` | Cancellation, key/provenance checks and completed-record guards; retain existing behavioural tests |
| `components/ui.tsx`, `styles.css` | Existing commit fields, focus styles, confirmations and responsive styling |

Proposed new files: `components/ModelCanvas.tsx` (composition), `components/ObjectivesCanvas.tsx`
(hierarchy), `components/CoverageMatrix.tsx` (counts/navigation) and, only as needed, a small
`model/coverage.ts` for indexed display facts. Names are recommendations, not required interfaces.
Use ordinary React state in EditorScreen for collapsed IDs, view mode, alternative ID and active
cell/focus token. This is one transient UI selection context, not a second project model. On
unmount it may reset; persisting a layout is outside MVP.

Keep stable selection across renames and unrelated edits. `reconcileSelection` currently clears a
removed criterion; use this predictable null fallback and show “Select an item”. After confirmed
removal, focus the surviving structural toolbar (or goal when no nodes remain). Clear a removed
alternative/cell; when a criterion becomes a branch, clear its cell selection. Undo restores data
but does not resurrect a selection that the user has since changed. Reconcile collapsed IDs against
the new tree. Do this after a successful edit, not before a request that might fail. Selection
must never attach to a new node merely because it occupies an old list position.

All project edits use `store.apply` and the current operation types. Existing add/remove/rename,
measurement, scale and preference editing must remain one ordinary undo step per logical action;
atomic multi-operation edits stay atomic. Reuse pending/saving/confirmation/unsaved-candidate
guards. No form navigation may bypass an existing value-function candidate's Apply/Discard/Stay
handling. Save and Ctrl/⌘+S retain their current semantics.

## Coverage and validation semantics

For A alternatives and L valid structural leaves, expected cells = A × L. Count distinct known
alternative/leaf pairs with a stored value; zero and valid qualitative labels count as entered.
A populated cell can still have a validation error. Do not coerce missing to zero, count orphaned
measurements, or count duplicate measurements twice. Duplicate/invalid references remain visible
in validation. With no alternatives/leaves show “Add alternatives/criteria” and expected cell
count zero; never show “100% complete” for an empty matrix.

| Cell status | Meaning/action |
| --- | --- |
| Missing | No entered measurement; button opens its input |
| Entered | A measurement exists; provenance/acceptance is not recorded in schema v1 |
| Entered · needs attention | Measurement exists and engine issues identify a cell problem; show text and linked issue |
| Setup needed | Criterion model is incomplete; distinguish measurement presence from setup, link to Inspector |

Presence and issue status are separate dimensions. A cell may say “Missing · setup needed”. Do not
invent a “valid” or “verified” badge just because no cell-specific issue was emitted: validation
can stop early or report issues at the criterion/profile level. Show relevant errors and warnings
on nodes, with text/icons as well as colour. Branch badges may aggregate descendant measurement,
model and judgement issues by ID, without double-counting the same issue. Group-level/unmapped
issues remain in ValidationPanel. Label the active profile/scenario and distinguish general
project issues from context-specific analytical readiness.

Show counts such as “7/9 entered; 2 missing; 1 entered cell needs attention”, plus separate setup
and preference issue links. Never derive a “decision quality”, confidence, investment attractiveness
or reward score from coverage. Data entry and validation are distinct from evidence reliability.
The current `Performance` schema has no source/accepted fields; metadata on an alternative is
not cell provenance. For MVP show “Evidence provenance not recorded”. When the evidence sidecar
workflow exists, it may add independent Sourced / Accepted statuses only for a version-matched
mapping with claim/source/excerpt/acceptance history. Changed manual measurements must make that
mapping stale; a populated cell alone must never be labelled verified evidence.

## Incomplete/error behaviour and API boundary

**No new API or project-schema fields are required for MVP.** Current `ProjectDocument` contains
the structure and validation; current edit operations cover all requested changes. Counts,
layout and joining IDs are permissible frontend work. The project title supplies the goal.
Any evidence-digest or provenance API is a separately scoped evidence package, not a hidden MVP
requirement. Generated API types remain untouched if the contract does not change.

Canvas renders on blank/incomplete drafts without requesting full evaluation. No structure,
coverage badge, expand/collapse or alternative highlight needs a numerical request. Invalid tree
input must show the engine's structural issue and a safe labelled flat fallback rather than
silently omit unreachable nodes or recurse forever. Note that the server normally rejects corrupt
trees on save; handle a malformed incoming draft defensively without declaring it valid. Missing
metadata must not prevent reading structure; use the existing loading/error state for editing.

Inspector currently mounts `CriterionPreview` for a selected leaf. Selecting a different criterion
may legitimately request that existing **criterion preview**, but must not request full evaluation.
Collapse, viewport changes and alternative highlights must not remount it or recreate its context
unnecessarily. Keep analytics unmounted until requested, or disabled when invalid. Any existing
analytics visible during an edit immediately hide old values when fingerprint/configuration
changes. Cancel and key-gate old successes **and failures**; cancellation alone is insufficient.
Validate responses against resolved profile/scenario/configuration and candidate. Delayed requests
must not paint a value onto a renamed/deleted criterion or different project. Transport failures
show structure plus actionable notices; do not fabricate scores or replace unknown values with zero.
Retain completed-record export validation; the canvas adds no numerical export path.

## Accessibility and visual character

Use a semantic nested HTML tree with labelled HTML controls; connectors are decorative and hidden
from accessibility APIs. Implement one tree tab stop/roving focus, `aria-selected`, branch
`aria-expanded`, level/position semantics and visible focus. Arrow up/down moves through visible
nodes; left collapses/goes to parent; right expands/goes to first child; Home/End reaches first/last;
Enter selects/opens editing and Space selects. Disclosure controls must not trigger a structural
edit. Delete opens the same confirmation, never an immediate delete. Keep global undo/save keys
out of text-field editing as they are today. Offer a labelled “Edit selected item” control for
keyboard/touch users. Confirm the exact focus behaviour with tests rather than inheriting all
assumptions from the existing outline implementation.

Use real table row/column headers and cell buttons whose accessible names include alternative,
criterion and status. For larger paged matrices, show current row/column ranges and keyboard
reachable paging controls; keep no more than one active cell tab stop with arrow navigation,
Enter to open, and labelled instructions. Returning restores focus; no mandatory hover or colour
interpretation. Test screen-reader announcement of the tree, cell status, edit destination and
confirmation. Existing automated accessibility coverage is sampled, not a WCAG certification.

Wrap readable names at ordinary zoom, permit explicit overflow for very deep trees/tables and
retain controls at 200% zoom/narrow widths. Avoid auto-zoom/pan on edits. Use a neutral palette,
selected outline and restrained issue colours. A brief optional opacity/position transition can
explain insertion/removal or a status change; no continuous pulses, decorative rewards or rank
celebrations. Honour `prefers-reduced-motion: reduce` by removing transitions and smooth scroll.
Keep focus stable through transitions and announce accepted additions/removals succinctly using a
polite status region, without announcing every render. Later numerical transitions must show
engine values and never imply interpolated frames are newly evaluated facts.

## Stack and performance

Recommend React + CSS/HTML for this bounded hierarchical view, with decorative SVG connectors
only if CSS is insufficient. It fits the existing React 19/TypeScript/Vite stack, HTML controls,
manual SVG chart precedent and dependency budget. [React Flow](https://reactflow.dev/learn/advanced-use/accessibility) provides node/edge interaction
and built-in keyboard/accessibility support, but adds a dependency and graph-interaction conventions
that still need integration with this tree’s editors and focus model. Most of that machinery
serves features excluded from MVP. A layout library could help a future free-form diagram; reconsider only after a
measured layout need. Do not install anything in this pass.

`services/results_service.py` enforces results/export bounds of 100 alternatives, 100 leaves,
1,000 nodes, 10,000 measurements, 8 MiB project requests and 16 MiB records/exports. These are
**results/export bounds**, not a universal editor size cap. Do not claim a new edit limit. Existing
performance fixture is 50 × 40 (52 nodes, 2,000 cells); historical timings are observations.

Build node/child, performance-pair and issue indexes once per relevant draft revision; avoid a
linear scan of all measurements/issues for every cell. Collapse is presentation-only and should
not rerun validation. Deep data needs iterative traversal or guarded depth handling, not an
unguarded recursive renderer. Do not pre-render 10,000 editor inputs. Recommend explicit table
paging (initially 20 alternatives × 20 criteria) above the small-model threshold; show total
counts and navigate across pages to selected cells. Memoise derived facts before considering
virtualisation; add no cache/database/worker without measurement.

Measure initial display, accepted-edit-to-paint, selection/keyboard response and DOM size on the
existing fixture and a 100 × 100 / 1,000-node bounded fixture, including deep and broad branches.
Provisional acceptance budget on the recorded local test machine: selection/expand paint within
200 ms and initial canvas within 1 s after document receipt. Report repeated measurements,
environment and outliers; revise the budget with evidence rather than masking delays with motion.
Outside tested bounds show counts, a compact/paged fallback and an explicit performance caveat;
keep forms reachable and do not imply numerical analysis supports an oversized project.

## Approved sequencing for later implementation

After package B and essential library coordination/restore, deliver this design in two slices:

- **D1 Visible model:** synthetic goal/objectives tree, click-to-edit, collapse/expand and updates
  through accepted edits and undo/redo. Keep ordinary editors and validation available.
- **D2 Connected coverage:** separate alternatives and entered/missing measurement cells, linked
  to the correct editor, with explicit counts and provenance limits.

This records the user’s sequence; package B implements neither slice. Each slice must satisfy its
applicable keyboard, incomplete-model, history/save and request-isolation criteria before the next.

## Short implementation sequence

1. Add read-only Model canvas/outline composition and the synthetic goal; connect current draft,
   criterion selection and Inspector. Establish keyboard/focus behaviour before animation.
2. Connect existing structural controls; render accepted rename/add/remove and undo/redo updates;
   define deleted-selection and failed-edit fallbacks. Preserve ordinary outline controls.
3. Add separate alternatives, indexed coverage/statuses and linked destinations using existing
   forms; handle unconfigured leaves, duplicate labels, empty states and paged large matrices.
4. Add restrained transitions/reduced motion, responsive layout and performance measurements.
   Keep numerical requests isolated; extend stale-response regression tests only where affected.
5. Run the meaningful checks below and the documented full gate, then the roadmap's real-user
   checkpoint. Review failures without changing numerical tolerances or fixtures to gain a pass.

## Acceptance criteria and meaningful tests

These tests assert behaviour, accessible names and stored outcomes, not internal component layout
or implementation-helper calls. No screenshot-only or animation-timing oracle is sufficient.

| Scenario | Observable acceptance / appropriate test |
| --- | --- |
| Blank build | Goal visible with no fabricated objectives/options; adding objective/leaf/alternative changes structure after accepted edits while ranking remains unavailable (component + real-backend browser) |
| Selection | Pointer/keyboard selects the same ID in canvas/outline/Inspector; duplicate names do not select the wrong node; matrix opens/focuses the correct alternative/leaf input (component/browser) |
| Rename | Commit name in the existing editor; canvas, headings and paths update before Save and retain ID/measurements; rejected edits retain accepted label and show notice (component/browser) |
| Deletion | Cancel confirmation changes nothing; accepted deletion clears affected selection and focuses safe control; deleting a branch removes its covered cells; failed deletion retains selection (browser with failure interception) |
| History/save | Add/rename/delete/performance entry each undo/redo consistently across views; save/reopen retains model; only selecting/collapsing/paging leaves project bytes, fingerprint, dirty state and undo unchanged (store/component/browser) |
| Missing/invalid | Unknown and zero differ; invalid entered data differs from missing; no scale links to setup; no score/confidence/verified-evidence badge appears; hidden/collapsed leaves remain in counts (component/browser) |
| Structural error | Cycle/orphan/duplicate-ID input produces safe fallback and actionable issue without silently dropping items or hanging (defensive component test) |
| Stale analytics | Delay old preview/record successes and errors, edit/delete node or switch profile/scenario, resolve newer request first; no old number/error appears in current view or downloads (hook + selected browser integration) |
| Request isolation | Observe network: selection may issue criterion preview; expand/collapse, alternatives highlight and paging send no evaluation/record/edit/save request (browser) |
| Keyboard/accessibility | Tree arrows, Home/End, Enter/Space, disclosure, matrix navigation, focus-return and destructive confirmation usable without pointer; names/statuses announced; no keyboard trap (component/browser + screen-reader walkthrough) |
| Motion/responsive | Reduced-motion emulation removes motion while changes remain understandable; narrow and 200% zoom keep names and controls accessible (browser + manual) |
| Scale | Existing fixture and bounded maximum fixture meet measured budgets, counts/pages remain correct, all cells are reachable and no stale numeric requests are triggered by navigation (browser/performance record) |

Retain existing numerical regression, preview, session, store and export checks. Useful new test
locations: `frontend/tests/components/ModelCanvas.test.tsx`, `CoverageMatrix.test.tsx`, selection
integration tests alongside `TreePanel.test.tsx`, and `frontend/e2e/live-model-canvas.spec.ts`.
The analyst comprehension checkpoint remains separate from passing automated tests.

## Follow-on visual packages (separate approvals/scopes)

All calculations remain in Python. Frontend geometry, display counts and ID joins are permitted;
weights, values, ranking, contribution aggregation, agreement statistics and sensitivity roots
must come from the numerical engine. Each package retains incomplete structure with actionable
issues and hides unavailable analytics. Keys include revision, effective configuration, resolved
profile/scenario and candidate inputs as appropriate; late successes/failures/exports are rejected.

| Package | Prerequisites and scope | Acceptance |
| --- | --- | --- |
| Weight flows | D; reuse weight preview and engine `local_weights`, `global_weights`, `path_shares`. Can work before performances are complete where preview readiness allows. Label local sibling weight, branch share of goal and leaf global weight distinctly; range-aware context visible | Zero/only-child/invalid sibling groups and multi-level fixture match engine; unavailable weights show issues, never zero; widths are geometry only; profile switch rejects late flows |
| Contribution exploration | Existing `ResultsPanel`, `ContributionsChart`, partial heatmap and completed records already work. Extend linked canvas selection to show strengths/weaknesses as partial values versus weighted contributions on the 0–1 preference scale | Figures/tables/exports agree with the completed record; hidden criteria do not change total/rank; zeros/ties and active ranges visible; no frontend recomputation or fabricated partial results on incomplete models |
| Live what-if | Existing `ValueFunctionEditor` already has a read-only candidate and atomic Apply/Cancel. Extend to one bounded candidate type at a time (e.g. swing ratings), with a Python candidate-preview service only if existing endpoints cannot express it | Baseline and candidate clearly labelled; invalid candidate explains why; preview cannot save or enter history; Apply is one atomic undoable edit; Cancel/Escape leaves bytes unchanged; model/context change invalidates candidate or requires explicit rebase; old candidate results cannot replace current ones |
| Sensitivity display | Existing `SensitivityPanel`/Chart and engine exact crossovers/probe, plus linked selection. Add focused annotations/navigation before advanced animation | Display exact engine roots and ties (including 3/7 and VC fixtures), distinguish plotting grid from exact probes; only-child/local-weight-one unavailable cases explained; one-way stability never called global robustness; cursor does not save/evaluate the model anew |
| Profile comparison | Existing independent profiles and effective-context handling; Python endpoint/envelope for a bounded set of completed records and optional tie-aware agreement statistic | Same revision/scenario/performances with explicit profile differences; show where values/ranks agree/disagree and differences in swing judgements; incomplete profile labelled unavailable; no silently pooled “consensus” or averaging of weights; stale batch rejected |
| Presentation mode | Existing model/results and transient view state; clean-install user checkpoint; explicit snapshot/context header | Read-only discussion view with readable goal/tree, alternatives, assumptions, missing-input list and figures; revision/profile/scenario and unsaved status visible; normal editors remain reachable; viewing leaves saved bytes/history unchanged; frozen snapshot versus live draft is explicit; no collaboration server implied |

These extend existing capability rather than prescribe fixed release dates. Profile comparison
and presentation can be useful before any new method. No sampled uncertainty or sorting feature
is smuggled into a visual package.
