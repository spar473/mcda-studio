# User guide

This guide walks through building and analysing a decision in MCDA Studio. Installation and
startup are in the [README](../README.md). The design notes in [`design/`](design/) give the
exact rules behind each screen.

## Contents

1. [Concepts in one minute](#1-concepts-in-one-minute)
2. [Create or open a project](#2-create-or-open-a-project)
3. [Build the model](#3-build-the-model)
4. [Value functions](#4-value-functions)
5. [Enter measurements](#5-enter-measurements)
6. [Elicit weights](#6-elicit-weights)
7. [Preference profiles](#7-preference-profiles)
8. [Sensitivity](#8-sensitivity)
9. [Scenarios](#9-scenarios)
10. [Results](#10-results)
11. [Value-based sorting](#11-value-based-sorting)
12. [SMAA-2: acceptability under uncertainty](#12-smaa-2-acceptability-under-uncertainty)
13. [PROMETHEE II: outranking flows](#13-promethee-ii-outranking-flows)
14. [AHP: priorities from pairwise judgements](#14-ahp-priorities-from-pairwise-judgements)
15. [Compare methods](#15-compare-methods)
16. [Feasibility check: mandatory requirements](#16-feasibility-check-mandatory-requirements)
17. [Save, export and recover](#17-save-export-and-recover)
18. [Interpreting the numbers](#18-interpreting-the-numbers)

## 1. Concepts in one minute

| Term | Meaning |
| --- | --- |
| Alternative | One option being compared |
| Objective | A branch of the value tree. It groups related criteria |
| Leaf criterion | The bottom of a branch. Only leaves carry measurements and value functions |
| Measurement | The raw reading of an alternative on a leaf, in its own unit or label |
| Value function | Converts a raw reading into a preference value between 0 (worst) and 1 (best) |
| Swing rating | How valuable it is to move a criterion from its worst to its best level, relative to its siblings |
| Weight profile | A named set of swing ratings, for example one per decision maker |
| Scenario | A variation that overrides some value functions and/or uses another profile |
| Overall value | Σ (global weight × partial value). A preference index between 0 and 1 |

## 2. Create or open a project

- **New project:** on the start page, choose one of the four starters (Blank, Supplier selection,
  Infrastructure procurement or Venture screening), or use **New project…** for a blank project or
  a template.
- **Examples:** import a bundled example. The `nz_deeptech_vc` example is a complete,
  fully worked model and a good place to start.
- **Stable IDs:** every alternative, criterion, profile and scenario has an ID that survives
  renaming and reordering.
- **Finding your way:** the editor's sidebar groups every screen into four stages: **Build** (project,
  model, alternatives, measurements, weights, requirements and any method inputs), **Analyse**
  (results, sensitivity, scenarios, compare), **Evidence** (evidence, open questions) and **Decide**
  (decision record). The bar above the content chooses the method, scenario and weight profile
  being viewed; **Details** shows the resolved profile and the project revision.

## 3. Build the model

In **Model**:

- **Alternatives.** Add, rename and remove alternatives.
- **Tree.** Build the objective tree to any depth. You can add a child or sibling, move items, and
  indent or outdent them.
- **Adding a child to a measured leaf** turns it into an objective, which removes its leaf data. You
  are asked to confirm, and Undo restores everything.
- **Removing items** shows their impact before you confirm.
- **Save is explicit.** There is no autosave. Use **Save** or Ctrl/Cmd+S.

**Model checks**, at the foot of the sidebar, counts errors and warnings. Errors open the list
automatically; warnings stay folded until you choose **Show notes**. Click an issue to jump to the
cell, node or rating it refers to. Incomplete drafts can be saved, but results need a complete, valid model.

## 4. Value functions

### Choose a scale

| Scale | Readings |
| --- | --- |
| Categorical | Unordered labels |
| Ordinal | Ordered labels. The spacing between them is your judgement, not assumed |
| Interval | Numbers where differences matter but zero is arbitrary |
| Ratio | Non-negative numbers with a true zero |

### Choose a function

The engine offers only the functions that suit the scale:

| Function | Rules |
| --- | --- |
| Linear | Increasing or decreasing. Fixed anchors, or local anchors taken from the alternatives' range |
| Piecewise-linear | Strictly increasing x, monotonic values, endpoints at 0 and 1 |
| Qualitative | One value for every label |
| Direct rating | Ratings within a stated numeric range |

**Fixed versus local anchors.** Local anchors depend on the alternatives. Adding or removing an
alternative can move them and change every partial value on that criterion. The app warns you when
that happens.

### Graphical editor

**Open graphical value-function editor** shows a plot and a table that edit the same candidate.

- **Moving points.** Drag a handle, or focus it and use the arrow keys (Shift for finer steps).
- **Adding a point.** Double-click the plot, or type two coordinates in the table.
- **Removing a point.** Select an interior point and press Delete.
- **Applying.** **Apply** commits the change as one undo step.
- **Cancelling.** **Escape** cancels the drag in progress; outside a drag, it closes the editor.
  **Cancel** discards everything.

The curve and each alternative's marker come from the engine, not the browser. Details:
[value-function editor](design/value-function-editor.md).

## 5. Enter measurements

Enter raw readings in **Measurements**, with their units.

- **Missing is missing.** An empty cell means missing, never zero.
- **Errors show on the cell.** A number outside a fixed domain is an error unless the function's
  out-of-range policy says to clamp.
- **Previews don't wait for everything.** Fixed-domain previews and weight previews work while
  other readings are still missing.

### Measurement coverage

The **Model → Canvas** table counts entered measurements across every structural leaf, including
collapsed branches. **Entered** includes zero and qualitative labels. **Entered · needs attention**
links to engine issues; **Missing · setup needed** distinguishes a missing input from criterion
setup. Setup and preference issues have separate links. An empty model asks you to add
alternatives/criteria and shows zero expected cells.

Use a cell to open its existing input or criterion setup, then **Return to coverage** (or the
**Model** tab) to restore cell focus. Arrow keys move between cells and pages; Home/End reach the
first/last criterion. Larger tables show 20 alternatives × 20 criteria per page, including in
Measurements. Counts always cover the whole model. Looking and paging do not edit or save it.
**Evidence provenance not recorded** means entry says nothing about evidence reliability or
confidence; no cell is verified.

## 6. Elicit weights

A weight answers this question: *how valuable is moving this criterion from its worst to its best
level over the stated range?* It is not abstract "importance".

1. In **Weights**, compare the siblings in one group at a time. Give the most valuable swing 100 by
   convention, and rate the others relative to it.
2. Work down the tree: rate the branches first, then the children within each branch.
3. Read the derived numbers next to your ratings:
   - the **local weight**, within the group;
   - the **branch share**;
   - the **global weight**, the leaf's share of the whole decision.

**Rules for ratings:**

- **Ratings are ratios.** They are non-negative and uncapped, and need not total 100.
- **Missing is not zero.** A missing rating blocks its group; a zero is valid as long as a sibling
  is positive.
- **All-zero groups are invalid.**
- **Only children** have local weight 1 without a rating.

**The swing cards** show each worst-to-best range, so you rate the real swing. If a range changes,
the app asks you to review the related ratings. It never changes them for you. Details:
[weighting and profiles](design/weighting-and-profiles.md).

## 7. Preference profiles

Use profiles for different decision makers or different judgement sets over the same tree.

- **Create** starts with no ratings; nothing is filled in.
- **Duplicate** makes an independent copy.
- **Delete** needs a replacement if a scenario or the saved default uses the profile. References
  are repaired in the same undoable step.
- **Viewing is not saving.** Switching profiles to view them does not change the saved default.
  **Use viewed profile as saved default** (or **Use automatic saved default**) does, and then you
  Save.

## 8. Sensitivity

**Sensitivity** varies one **local** weight from 0 to 1. Its siblings keep their ratios and are
rescaled to fill the rest.

- **The chart** is sampled. The listed **crossovers** are exact.
- **Exact probes.** Click a crossover or type a weight to probe that exact point on the server.
- **Ties share a rank** (1, 1, 3). A tie forming or dissolving at the top counts as a change of
  winner set.
- **Stability ranges** tell you how far the weight can move before the winner or the full ranking
  changes.
- **Some criteria cannot be varied.** Only children, and criteria already at weight 1, are disabled
  with an explanation.

Sensitivity is read-only and one-way. Moving the cursor never changes your ratings, and it is not
evidence of robustness to changing several weights at once. Details:
[sensitivity](design/sensitivity.md).

## 9. Scenarios

A scenario stores a profile reference and sparse **overrides** of leaf value functions. Scales,
units and measurements are shared with the base.

- **Edit overrides** in **Scenarios** with the same graphical editor.
- **Reset to Base** removes an override, so later base edits flow through again.
- **Comparison** shows one selected scenario against Base: scores, differences, ranks, and whether
  the ranking or winner changed.
- **Two profiles.** Base and the scenario may resolve different profiles. Both are named, because
  score changes may then come from weights as well as functions.

Details: [scenarios](design/scenarios.md).

## 10. Results

**Results** shows one completed analysis:

- **Overall values** on a fixed 0–1 axis, with competition ranks.
- **Weighted contributions** per leaf, which add up exactly to each overall value.
- **Partial-value heatmap**, alternative × criterion. Colours show preference values, and raw
  readings are listed separately.
- **Dominance matrix**, built from partial values. It is a diagnostic and never removes an
  alternative.
- **Scenario comparison** against Base.
- **Linked inspection.** Select any bar, segment or cell to see the alternative or criterion in
  full.

**Hiding series** is for inspection only. It never renormalises values, and hidden items are
always disclosed. Tables show every number without hovering, and matrices support arrow keys.
Details: [results and exports](design/results-and-exports.md).

## 11. Value-based sorting

Use it when the decision is about classes, such as *Qualified / Conditional / Not qualified* or
*Go / Hold / Stop*, rather than a full ranking. Each alternative goes to the best class whose lower
boundary its overall MAVT value reaches. The bundled **Supplier qualification** example shows it.

- **View it.** Choose **Method → Value-based sorting (MAVT)** in the analysis header. Viewing a
  method is like viewing a profile: it changes nothing in the project. **Use viewed method as saved
  default** makes it the saved method, as one step you can undo. A viewed method other than the
  saved one runs with its own default parameters.
- **Set classes** in the **Classes** tab, best first. Every class except the lowest needs a lower
  boundary between 0 and 1. A value within 10⁻¹² of a boundary goes to the higher class.
  Boundaries must decrease down the list; they are never reordered for you, so an out-of-order
  list shows an error to fix. **Apply classes** makes one undoable edit.
- **Audit sample (optional).** Pick a cut-off class, a sample size and a seed to list a few
  alternatives sorted below it for manual review of possible false negatives. The same seed always
  picks the same alternatives.
- **Results** starts with **Classes**: each class's value range and members, every alternative's
  class and its distance to the nearest boundary, and the audit sample. The ranking chart shows the
  classes as bands, and the ranking CSV gains class columns; a **Classes** CSV lists the classes.
- **Sensitivity** adds class bands to the chart and a **Class changes** table: the exact local
  weight at which each alternative's class first changes, below and above the baseline. Select a
  weight to probe it.
- **Use fixed anchors.** With local anchors, adding or removing an alternative can move others
  between classes; Results warns about this.

A project with classes is saved as schema version 2, which older versions of MCDA Studio cannot
open. **Remove all classes** returns it to version 1. Details:
[value-based sorting](design/value-based-sorting.md).

## 12. SMAA-2: acceptability under uncertainty

Use it when some inputs are uncertain and you want to know how often each option comes first, or
lands in each class, if those inputs vary as you state.

- **View it.** Choose **Method → SMAA-2 (sampled acceptability)**. As with any method, viewing it
  edits nothing.
- **State the uncertainty** in the **Uncertainty** tab. For a measurement, choose uniform (lower
  and upper), triangular (lower, mode, upper) or discrete outcomes with probabilities
  (`3=0.5, 5=0.5`); a labelled scale takes categorical outcomes. Ranges must stay inside the
  value-function range; nothing is clamped. Give two or more measurements the same **shared draw**
  name when they come from one source and should move together. For each group of sibling
  criteria, keep the weights **fixed**, make them **unknown** (any split equally likely) or give
  **rating intervals** for the raw swing ratings. **Apply uncertainty** makes one undoable edit.
  A missing measurement must still be entered: a distribution never fills it.
- **Run settings** in the analysis header choose what varies (measurements, weights or both), the
  number of draws and the seed. They change the view, not the project; the same seed always gives
  the same result on the same installation.
- **Results** shows **Acceptability**: for each option, the share of draws at each rank, with an
  exact interval, rank 1 split into sole and tied first; class shares when the project has
  classes; and a short list of inputs to check, marked as a heuristic. When every varying input is
  discrete and few enough, the shares are exact and have no interval.
- **Exports:** JSON (the record and the project) and three CSV tables: rank acceptability, class
  acceptability and inputs to check.

Every view says **sampled acceptability under these assumptions**: a share of draws is not the
probability that a choice succeeds, and it depends on the ranges you stated. Sensitivity and
scenario comparison are not offered for SMAA-2. A project with stated uncertainty is saved as
schema version 3; **Remove all uncertainty** returns it to the version it needed before. Details:
[SMAA-2](design/smaa-2.md).

## 13. PROMETHEE II: outranking flows

Use it as a cross-check where a large advantage on one criterion should not simply make up for a
poor result elsewhere. PROMETHEE II compares every pair of options criterion by criterion; a
difference counts only up to "full preference", however large it is.

- **View it.** Choose **Method → PROMETHEE II (outranking flows)**. As with any method, viewing it
  edits nothing, and the MAVT editors (value functions, weights) keep working while it is viewed.
- **State its inputs** in the **Outranking** tab, for every leaf criterion:
  - the **direction**: maximise or minimise. It is never read from the value function;
  - a **weight**: any non-negative number; the weights are divided by their sum. Swing weights are
    not reused, because they are trade-offs over MAVT's ranges, not importances;
  - a **preference function**: **usual** (any difference is full preference), **U-shape** (none up
    to q, then full), **V-shape** (growing to full at p) or **linear** (none up to q, growing to
    full at p), with q and p in the criterion's units. A small sketch shows the shape;
  - for a labelled scale, a **number for each label**. **Number in label order** fills 1, 2, 3, …
    for an ordinal scale; change them if the steps are not equal.

  **Apply outranking inputs** makes one undoable edit, and the engine's checks are listed below it.
- **Results** shows three views, all labelled **net outranking flows: these compare the
  alternatives with one another and are not preference values**:
  - **Flows:** each option's positive flow (how strongly it outranks the others), negative flow
    (how strongly they outrank it) and net flow, ranked by net flow, with bars on a fixed −1 to 1
    axis;
  - **PROMETHEE I:** for each option, those it is incomparable with, preferred to, indifferent to
    and below. Two options are incomparable when the positive and negative flows disagree; the net
    flow hides that;
  - **Explanation against MAVT:** each option's MAVT rank beside its PROMETHEE II rank, and every
    pair the two methods order differently. For each pair it gives the value gap and the flow gap,
    how much of the flow gap comes from the two options head to head and how much from how each
    fares against the others, each criterion's difference with its zone (within q, between q and p,
    or full preference and no more), and up to three reasons in words. If MAVT's model is
    incomplete, the explanation says why and the flows are still shown.
- **Exports:** JSON (the record and the project) and four CSV tables: flows, single-criterion
  flows, PROMETHEE I relations and the explanation.

Adding or removing an option can change every flow, and even the order of two others. Sensitivity
and scenario comparison are not offered for PROMETHEE II; the explanation uses the profile and
scenario selected in the header. A project with PROMETHEE inputs is saved as schema version 4;
**Remove all outranking inputs** returns it to the version it needed before. Details:
[PROMETHEE II](design/promethee-ii.md).

## 14. AHP: priorities from pairwise judgements

Use it when you would rather compare things two at a time than rate swings over ranges: which of
two criteria matters more, and how many times, and which of two options is better on a criterion.

- **View it.** Choose **Method → AHP (pairwise priorities)**. As with any method, viewing it edits
  nothing. AHP reads no weight profile or scenario, and the header says so.
- **Judge** in the **Pairwise** tab. There is one matrix for each group of sibling criteria and one
  for the alternatives on each leaf criterion. For each pair, choose which item is more important
  (or better) and by how much on Saaty's scale: 1 equal, 3 moderate, 5 strong, 7 very strong, 9
  extreme, with 2, 4, 6 and 8 between. Each pair is judged once; its reverse is derived.
- **Consistency, live.** Beside each matrix, Python computes the priorities, λmax, CI and the
  consistency ratio (CR) as you judge. A CR above 0.10 shows a warning and highlights the most
  inconsistent triad: three judgements that disagree, with the value the third would need to agree
  with the other two. It is a prompt to look again, never an automatic change, and it never blocks
  evaluation. **Apply judgements** makes one undoable edit.
- **Results** shows **AHP priorities** (each option's share of the goal, which sum to 1, with
  criterion priorities and each option's priority on every leaf) and **Consistency** (every
  matrix's CR, inconsistent ones first, with its triad). Synthesis is distributive unless the
  `synthesis` parameter says `ideal` (CLI: `--synthesis ideal`).
- **Exports:** JSON (the record and the project) and four CSV tables: priorities, criterion
  priorities, local priorities and consistency.

Every view says **AHP priorities under these pairwise judgements: shares of the goal that sum to
one, not MAVT values or swing weights**. In distributive synthesis, adding or removing an option,
even a copy of one, can change the order of two others. A project with AHP judgements is saved as
schema version 5; **Remove all judgements** returns it to the version it needed before. Details:
[AHP](design/ahp.md).

## 15. Compare methods

The **Compare** tab shows every method's own reading of the model side by side, for the profile and
scenario selected in the header.

- **Columns:** one per method. Each names what it read (value functions and a profile, stated
  uncertainty, PROMETHEE inputs or pairwise judgements) and its parameters, and shows each option's
  rank and that method's own number: overall value, rank-1 acceptability with its interval, net
  flow or AHP priority. Each number sits on its method's own scale.
- **A method that cannot read the model** shows why, with its codes (for example `AHP_NOT_STATED`),
  and a button that opens the tab where you state its inputs.
- **Above the table:** whether the methods that ran put the same option first, which option each
  puts first when they do not, and each method's own reason: for SMAA-2 how often its leader comes
  first, for PROMETHEE II the criteria and thresholds behind the difference, for AHP that it reads
  its own judgements and which matrices are inconsistent. Where sorting and SMAA-2 both use classes,
  differences in class are listed too.
- **Downloads:** the comparison as JSON, or a CSV with one row per option and method.

There is no combined score. Methods that share inputs agreeing is not independent confirmation, and
the view says so.

## 16. Feasibility check: mandatory requirements

Some requirements are not trade-offs: a price ceiling, a legal minimum, a required certification.
State them in the **Requirements** tab, and each option is checked against them **outside** every
score.

- **Add a requirement** by choosing a leaf criterion. A numeric leaf takes a minimum, a maximum or
  both, each including the limit itself unless you untick **itself passes**, in the criterion's own
  unit (prefilled and shown beside the field); a different unit is an error, and nothing is
  converted. A labelled leaf takes the allowed labels; on an ordinal leaf, **At least …** ticks that
  label and every label above it, **At most …** that label and every label below it, and the
  stored list is exactly what is ticked.
- **The result of the draft** appears below as you edit, computed in Python: each option **passes**,
  **fails** or is **unknown** for each requirement, with the reason, such as "51 NZD is above the
  maximum 45 NZD". A missing measurement, or one of the wrong kind, is **unknown**, never a failure.
  Overall, any failure is a failure; otherwise any unknown is unknown; otherwise the option passes.
  Limits are compared exactly as entered.
- **Apply requirements** saves the list as one change you can undo; **Remove all requirements**
  removes them.
- **Beside every ranking:** when requirements exist, Results shows the feasibility table under the
  ranking, with JSON and CSV downloads, and the Compare tab has a Feasibility column. No ranking
  is reordered or filtered, and no score can offset a failure: an option that fails keeps its place
  and is flagged.

Requirements read only measurements, so the profile, scenario and method selected above never change
them. A project with requirements is saved as schema version 6; removing them returns it to the
version it needed before. Details: [feasibility check](design/feasibility-check.md).

## 17. Save, export and recover

**Saving:**

- **Format.** **Save** writes JSON at schema version 1, 2 when the project has classes, or 3 when
  it states uncertainty. The
  dashboard download is the stored project file.
- **Conflicts.** If the file changed since you opened it, you choose: keep editing, reload, or save
  a separate copy. Never force an overwrite just to dismiss the dialog.
- **Unsaved work is session-only.** Unsaved edits and undo history are lost on refresh or close, so
  save first.

**Exporting from Results:**

| Format | Contents |
| --- | --- |
| JSON | The complete analysis record and the source project, at full precision, with provenance. Re-running it reproduces the record exactly |
| CSV | Ranking, contributions, partial values, comparison and dominance tables, with context. Spreadsheet formula-like text is visibly encoded (`TEXT:` prefix) |
| SVG | Ranking, contribution and comparison charts, with labels and context |

**When something fails:**

- **Analysis error.** Restore the connection, then choose the Retry button under the message
  (Retry analysis, Retry analysis check, Retry sensitivity, Retry probe or Retry comparison). It
  re-sends the same request and never changes the project. Previews retry on your next edit.
- **Save error.** Retry Save directly; your draft is kept.
- **Recalculation.** While results are recalculating, out-of-date results are hidden and late
  downloads are suppressed.

**Deleting and backing up:**

- **Deleting** a project moves it to the library's `.trash` folder. Restore it from
  **Projects → Recently deleted**, under its original ID or as a copy; nothing is overwritten.
- **Back up** the whole library, including Recently deleted, with the command line. Stop the
  server first; a backup is refused while a server owns the library. Run one server per library.

  ```sh
  mcda library backup --store ~/.mcda-studio/projects --to ~/backups/projects-2026-10-27.zip
  mcda library verify ~/backups/projects-2026-10-27.zip
  mcda library restore ~/backups/projects-2026-10-27.zip --to ~/restored-projects
  ```

  Backup never overwrites a file, verify writes nothing, and restore only creates a new folder.
  Each command exits `0` when it completed, `3` when it completed with warnings (such as a skipped
  temporary file or a project too new to check) and `1` when it failed. Open a restored library
  with `mcda serve --store ~/restored-projects`. Details:
  [backup and restore](design/library-backup-and-restore.md).

## 18. Evidence and calculated measurements

For local source review, open **Evidence** and load a dossier for this exact project revision.
Inspect sources, proposals and current measurement support, select a claim, name the reviewer
and preview an acceptance, correction or rejection before confirming it. Export the review
workspace to retain the original project/dossier and appended history. Accepting a claim does
not change a measurement: under **Compile reviewed evidence into a separate copy**, check each
listed change, tick the acknowledgement and compile. Export the compiled project copy and the
evidence compilation bundle; the open project is unchanged. Import the copy through Projects. If
the original is still there, choose **Import as a separate copy** and download the copy receipt.
Selecting the bundle in Evidence later verifies and shows it; selecting the receipt relates it to
the imported copy ([details](design/separate-copy-provenance.md)). The CLI compilation step remains
available. Open Questions uses the reviewed workspace dossier. Support labels concern provenance, not factual or numerical validity;
independence does not establish correctness. See the [evidence demonstration](../examples/evidence_demo/README.md).

To record a decision, open **Decision**. State the owner, date, outcome (select an alternative
or defer), alternatives considered, rationale, unresolved assumptions and review triggers, and
choose up to six analyses (method, profile and scenario). Add any evidence compilation or
calculation bundles with their copy receipts. **Preview decision record** builds the record in
Python. It shows unavailable analyses explicitly, failed or unresolved requirements beside the
choice, and which measurements each bundle set. **Export decision record** saves the file; nothing
is stored in the library. To revise, open the record, choose **Revise this record**, change what
changed and export the new record, which names its predecessor. See
[decision records](design/decision-records.md).

For calculations, expand **Calculated measurements** in Measurements. **Start a new calculation
model**, or load a model, an exported calculation workspace or a calculation bundle. Enter your
name, then add units, source factors (value, unit, source reference, and whether you or an
identified tool proposed it) and formulas with an optional target measurement. A new or revised
factor or formula is pending until you review it; a formula can be accepted only once its check
shows that it calculates with consistent dimensions. Each target shows its dependency graph,
intermediate values and which factors are shared across alternatives. **Measurement changes**
lists every current and calculated value: tick the acknowledgement and **Apply to this project**
to set them as one edit you can undo, or compile a separate copy instead. Applying offers the
calculation bundle, which decision records can cite. Saving stores the project only: export the
calculation workspace to keep the formula history (Save asks first while it is unexported), and
reopen that file later to reproduce the calculation. See the
[calculation workspace](design/calculation-workspace.md) and the
[calculation demonstrations](../examples/derived_measurements/README.md). Factor uncertainty is not
yet integrated.

## 19. Interpreting the numbers

- **Scores are preferences.** They are not probabilities, forecasts or financial returns.
- **Additive MAVT compensates.** A strong criterion can make up for a weak one. Screen hard
  requirements separately before the analysis.
- **It assumes preferential independence:** how much you value one criterion should not depend on
  the levels of the others. The software cannot check this for you.
- **Partial values share 0–1; raw units do not.** Never compare raw readings across criteria.
- **One-way sensitivity is not robustness.** It varies one weight at a time.
- **A class is a threshold on the overall value,** not a pass/fail test of any one measurement
  and not a prediction. A strong criterion can lift an alternative into a better class.
- **An acceptability is a share of draws** under the ranges you stated, not a probability of
  success. Narrow or wide ranges change it; it says nothing about ranges you did not state.
- **A net flow compares the options with one another.** It is not a preference value and never
  shares an axis with one, and it changes when an option is added or removed. Agreement between
  PROMETHEE II and MAVT on shared measurements is not independent validation.
- **An AHP priority is a share of the goal under your pairwise judgements.** A low consistency
  ratio says the judgements agree with each other, not that they are right.

See [method limitations](mathematics/method-limitations.md) for the full list.

### Formula precision and quantity-check boundaries

Formulas use binary64 arithmetic in their written expression-tree order. Exports retain the full
computed precision; a rounded screen label does not change a stored value. Quantity checks compare
computed values directly with their declared bounds, without a tolerance. For example,
`0.1 + 0.2` computes as `0.30000000000000004` and fails an inclusive upper check of `0.3`.
Prefer checks on fundamental inputs where possible, and allow explicit model headroom rather
than declaring a derived check exactly at a boundary your example reaches.

### Starter gallery and lineage

New project includes a four-item gallery: Blank, Supplier selection, Infrastructure procurement
and Venture screening. Every item states the tasks and local files it actually contains. Optional
materials start unchecked. **Create my project** creates a new ID, keeps illustrative input values
and structural IDs, clears human reviews and saved run snapshots, and marks the project as needing
your review. **Open worked example** retains its exact invented reviews and fingerprint.

Download the materials with their lineage receipt before opening the prepared project. The ZIP
also contains individual sidecars for Evidence and Calculated measurements. Reopen the materials
file in the gallery to verify its manifest, hashes, project and cleared fields. An edited saved
project with a worked example's ID must be handled explicitly; opening an example never silently
replaces it. A receipt proves local lineage, not factual accuracy or a reviewer's identity.

### Comparing two formula models

In Measurements → Calculated measurements → Model comparisons, open a comparison file. Inspect
both graphs, deterministic values, inputs, classifications, dates, reviews and declared scopes.
Source bounds, conservative support enclosures, exact discrete supports and sampled central 95%
ranges have different meanings and retain their labels. A sampled range records its seed,
quantile algorithm, draw count and environment; it describes the declared model distribution.

A model disagreement stays in Open Questions even when the ranges overlap. Unknown or different
populations, geography, periods, currency bases or units remain incomparable until reviewed.
There is no average, overlap percentage or materiality cut-off. Missing factors block the outputs
that require them; unrelated draft quantities remain retained with an explicit omission ledger.

Review deterministic inputs first, then their distributions/groups and quantity checks separately.
Changing an input clears those later reviews and the comparison acknowledgement. A check applies
to the deterministic inputs, declared support and every draw; a bad draw aborts without thinning
the sample. Conservative support checks can refuse a valid repeated-factor image whose enclosure
is wider. Source bounds do not create a uniform distribution.

Choose one output, alternative and criterion, review the exact scope and before/after cell diff,
and record a reviewer and rationale. Compile the acknowledged selection into a separate copy and
export its bundle. The other model and disagreement remain retained. A changed context invalidates
the selection; the API returns 412 `STALE_REVISION`. Historical bundles are verified against their
retained source project and remain readable. The selected model can also run with reviewed
quantity checks through MAVT, sorting or fixed-weight factor-based SMAA-2; distributions must be
explicitly declared. Review and run files require explicit export; saving a project does not
save its sidecars.

CLI counterparts are `starter-templates list/instantiate/verify/archive` and
`model-comparisons inspect/review/run-output/compile/verify/run-checked/verify-checked/verify-output`.
Use each command's `--help` for its input files. Output files are created exclusively.


## Optional disclosed model proxy

Compare has a separate optional proxy workspace. Prepare its declaration, state the fixed numeric
scale and score meaning, chosen existing parent, compared profiles and an explicit proxy swing
rating for each profile. Missing ratings are empty, and zero is an explicit judgement. Author
model-card facts, feature lineage/dates and overlap resolutions in the declaration JSON. Record
edits before running; edits clear prior acceptances and disable the plan. A changed feature
observation date creates a new score-review draft and requires newly reviewed proposals.

Inspect and export the separate score-review draft, then import and review fixed numeric proposals
against that draft using the proposal reviewer. Bind the exact reviewed workspace and model card.
Review each required card fact and feature/overlap declaration, record licence compatibility and
review the complete plan. An explicitly reviewed unknown needs a reason and acknowledgement;
unknown or incompatible licence/restrictions block. Shared criterion/factor IDs are shown for
review; no automatic semantic overlap detector or removal is claimed.

The enable toggle creates a separate analysis preview. Review the before/after weight shares and
acknowledge the card, overlap, changed weights and any unknown facts. Run both copies together.
MAVT, value-based sorting and fixed-weight factor SMAA-2 are supported; factor inputs and run
parameters travel in the proxy-inputs file. The external proxy score stays fixed. Paired PROMETHEE
II/AHP comparisons are unavailable; their ordinary method columns remain separate. Changing the
context invalidates a paired candidate, including when returning to an earlier profile.

Both copies, failed-half reasons, feasibility, the score calculation and complete review history
remain in the export. Export both project copies and the complete pair, or export inputs/history
to continue later. Reopening a complete pair verifies both halves against their original snapshot.
Save stores the project, so it directs pending proxy work back to Compare for export or discard.
The original project is the without-proxy baseline. No average, confidence weight or probability of
an outcome is calculated. Exports retain full precision; screen formatting only changes display.

The local CLI mirrors this workflow through `proxy start`, `revise`, `inspect`, `preview-pair`,
`run-pair` and `verify`; output files are created exclusively. No external model or source URL is
accessed. This workflow supplies reviewed input provenance, not evidence that a model is accurate.
