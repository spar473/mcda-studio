# Value-function editor

To open the editor, select a leaf criterion in **Model** and choose **Open graphical value-function
editor**. The precise form controls remain available beside it.

The editor is a *candidate* workspace. None of these edits or saves the project:

- typing
- dragging
- switching between the plot and the table
- selecting a point
- fitting the chart

Only **Apply** commits a change.

## What you edit and what the engine calculates

The table and the plot handles edit the same candidate. Numeric x values keep their measurement
unit. What you can edit depends on the function type:

| Function | What you can edit |
| --- | --- |
| Piecewise-linear | Interior handles: x and value. Endpoint handles: x only. An endpoint selector chooses lower = 0 / upper = 1, or the reverse |
| Linear | Direction (increasing or decreasing) and fixed or local anchors |
| Direct rating | Its own minimum and maximum |
| Qualitative | One labelled dot per label, with no interpolation. Categorical labels have no order; ordinal labels keep their declared order |

The curve, the dots and each alternative's partial value all come from
`POST /api/value-functions/preview`, which uses the Python evaluator. TypeScript only maps
coordinates and passes your inputs along. It never interpolates preferences, derives local anchors
or scores alternatives.

**Where the numbers are shown:**

- **Equivalent table.** A named table shows raw readings, partial values, missing or invalid states
  and clipping.
- **Tooltips** keep names and raw readings.
- **Off-screen markers** are drawn at the chart edge. This is a drawing position only; it is not
  preference clamping.

## Domains and the viewport

- **Stable viewport.** It does not change during a gesture. **Fit current domain to chart** refits
  it on purpose after you change endpoints or ranges.
- **Effective domain shown.** The domain and its source are shown even when they differ from stored
  scale bounds that are not in use.
- **Hidden settings are kept.** A piecewise function keeps its local/fixed settings out of sight.
  Switching back to linear makes them active again.
- **No invented anchors.** Switching between numeric kinds requires a resolved domain.
- **Local functions need every reading.** A local function with any required reading missing has no
  curve and no movable anchors.
- **Fixed functions don't.** A valid fixed function can be previewed even when unrelated weights or
  readings are missing.

## Pointer, keyboard and table input

**Moving points.** Drag a handle, or focus it and use the arrow keys (Shift for finer steps). Both
write the same fields as the table and request the same preview. Endpoint preference values stay
fixed.

**Adding and removing points.**

- **Add:** type two coordinates in the table, or double-click the plot.
- **Remove:** select a point and use Remove or Delete. Only interior points can be removed.
- **Placement:** new points are inserted before the last endpoint.

**Validation.**

- **Nothing is auto-corrected.** Coordinates are never silently sorted, monotonicity is never
  forced, and values are never smoothed.
- **Problems are diagnostics.** Wrong order, duplicates, bad endpoints, domains or judgements appear
  as engine diagnostics with paths.
- **Your input is kept.** Invalid or incomplete input stays in place. Out-of-date curves and markers
  disappear immediately.

**Cancelling.**

- **Inside a gesture.** If a drag is cancelled, the pointer capture is lost, or you press Escape
  mid-drag, the candidate returns to how it was before that gesture.
- **Outside a gesture.** Escape cancels the dialog.
- **Cancel** discards everything with no edit, fingerprint change or undo entry. Focus stays inside
  the dialog.

## Apply and save

**Apply requires:**

- the backend to report the function as `ready`
- no half-typed numbers
- no gesture in progress
- the same analysis context as when the editor opened
- your explicit acknowledgement that preference ranges or judgements changed

Measurement readiness is separate. A fixed function can be applied while the project still has
missing or invalid readings. The model then stays a draft until the data is fixed; the editor never
fabricates readings.

**What Apply does.** Apply sends one `POST /api/edit` batch, `set_scale` then `set_value_function`.
That is one undo step. Save then stores it through the conflict-aware store.

**Saving with a candidate open.**

- **Pending candidates are shown** in the header.
- **Ctrl/Cmd+S and Save** apply a valid, acknowledged candidate first, then save.
- **Invalid or unacknowledged candidates** block the save with an explanation. Navigating away lets
  you keep editing or discard.
- **Closing the browser** warns about pending candidates.

**Context safety.**

- **Preview keys** include the fingerprint, full configuration, criterion and candidate. Out-of-date
  requests are aborted and ignored.
- **Context changes block Apply.** If the revision, scenario, profile or criterion changes while the
  editor is open, Apply is blocked and you are asked to reopen. A candidate is never silently
  rebased.
- **Base versus scenario.** From **Model**, Apply changes the base function. To change a scenario's
  function, use **Edit override** on **Scenarios** (see [scenarios](scenarios.md)).

**Acknowledgements.**

- **The candidate acknowledgement** resets on every further edit, including A→B→A and cancelled
  gestures.
- **Swing review is separate.** After Apply, the session's swing-review warning still asks you to
  review the new context. Acknowledging a candidate never means the ratings were reviewed.
- **Neither changes data.** Neither acknowledgement changes ratings, fingerprints, stored bytes or
  history.

## Limits

- **Sampling.** Up to 501 sample points. Too many control points produce an explicit diagnostic.
- **Accessibility.** The precise tables are the accessible alternative to plot input. No
  screen-reader or cross-browser certification is claimed.
