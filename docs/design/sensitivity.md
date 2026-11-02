# One-way weight sensitivity

How the **Sensitivity** tab works. It explores the engine's one-way sensitivity analysis, and a
read-only probe endpoint returns exact values at any weight. The wire format is in the
[API contract](../api/contract.md).

## 1. What the view answers

One question at a time: *if the local weight of this one criterion were `t` instead of what the
profile implies, how would the alternatives score and rank?*

"Local weight" is the criterion's share **of its own sibling group**, not of the overall goal. The
other siblings are rescaled proportionally so the group still sums to one, keeping their ratios to
each other exactly as elicited. Varying an objective moves its whole subtree's influence; varying a
leaf redistributes inside its group while its parent's branch share is preserved.

Because every global leaf weight is a product of local weights along a path, and a path contains at
most one member of the affected group, each alternative's overall value is **affine** in `t`. That
is why crossovers are solved in closed form rather than searched for.

## 2. Sensitivity is strictly read-only

Moving the cursor, choosing another criterion, probing a crossover, hiding a line and switching
profile are all **view** operations. None of them:

* changes a raw swing judgement, a weight profile or a scenario;
* changes the saved analysis default or the project fingerprint;
* creates an undo/redo entry or marks the project unsaved;
* writes anything to the project store.

The probe endpoint takes a project snapshot in the request body and returns numbers; it never
reaches the store. Tests compare project JSON, stored bytes, ETags and fingerprints before and
after dozens of probes.

A cursor position is a *hypothesis*, not an elicited preference. Turning one into saved judgements
would need its own conversion rules and an explicit user action, so the feature deliberately does
not offer it.

## 3. Exact crossovers, not grid readings

The chart draws a sampled grid, but every number that matters comes from closed-form engine
output:

* **Crossovers** are exact roots of the affine difference between two alternatives, listed with
  the pair involved and which one leads on each side.
* **Clicking a crossover** probes that exact weight on the server; it is not snapped to the grid
  and not interpolated between samples.
* **Clicking the chart** snaps to the engine's own grid, and the readout shows the snapped weight
  rather than implying continuous precision.
* **Typing a weight** probes exactly that value.

A crossover is a **tie** between the crossing alternatives; it can occur below the winner. At a
first-winner crossover the engine reports both leaders at competition rank 1, the next at rank 3,
and a `TIED_ALTERNATIVES` diagnostic. The view shows that rather than inventing a unique winner at
the boundary. Ranks always come from the engine's competition ranking, where tied alternatives
share a rank and the next rank is skipped. They never come from a position in a sorted array.

A **pairwise swap below the leader is not a winner change.** The view states which of these
happened:

- the competition ranks changed;
- the rank-one winner set changed, including a tie forming or dissolving;
- neither.

These flags compare competition ranks and winner sets, not the sorted ID sequence. A sorted
sequence can stay the same while a tie forms.

## 4. Stability intervals

* *Winner unchanged over* — the range around the baseline in which the top alternative holds.
* *Full ranking unchanged over* — the range in which the complete order holds. If the baseline sits
  exactly on a crossover this is a single point, and the view says so rather than printing an empty
  interval.
* *First winner change above / below baseline* — the nearest weight in each direction at which the
  leader changes, or "none in this direction".

"None in this direction" means no different winner appears along **this one weight** over [0, 1].
It is not evidence of robustness to changing several weights at once, and the view does not claim
it is.

## 5. What cannot be varied

The engine refuses, and the selector disables, a criterion that is:

* an **only child** — its local weight is fixed at 1, so there is nothing to redistribute; or
* already at local weight 1 because every sibling rating is zero — the proportional redistribution
  of the others is undefined.

Both give a plain explanation instead of an empty or misleading plot. A zero-weight criterion with
an eligible sibling *can* be varied, and starts from a baseline of 0. A model where no criterion is
eligible says so once, rather than offering an empty selector.

## 6. Context and asynchronous identity

The tab resolves profile and scenario through the same shared analysis context as Weights and
Results, with the same precedence (explicit, then the scenario's profile, then the first profile),
and shows the resolved profile, scenario and revision above the chart.

Every request is keyed on the project fingerprint, the complete configuration, the selected
criterion and, for a probe, the probed weight. The probe response is additionally verified field by
field — including the **resolved profile**, which is checked separately from the configuration
because under automatic resolution the configuration can match while the engine resolves a
different profile. A response that does not match the live context is discarded, in-flight requests
are aborted when the context changes, and a previously ready chart is hidden immediately rather
than left under a new context's label.

`SensitivityResult` predates the provenance envelope and carries no fingerprint, configuration or
profile, so the sweep's identity rests on the request key plus the node id it echoes. That
asymmetry is deliberate: the existing endpoint's shape was left alone, and the new probe envelope
carries provenance explicitly.

## 7. Hiding alternatives

The legend toggles whether a line is drawn. It is a chart filter and nothing more: the hidden count
is stated, the numerical table still lists every alternative, and no weight, score or axis is
recalculated from the visible subset. The y-extent does follow the visible lines, which is a
drawing choice, not a renormalisation of the model.

## 8. Precision

Values are computed with `math.fsum`, the same summation as the real evaluation, so a probe at the
baseline weight equals the Results value exactly. The sweep's plotted grid uses a numpy matmul and
can differ by at most one ulp (measured 1.11e-16); that affects a line's position by far less than
a pixel and never a displayed number, because every number shown as text comes from the probe.
Display rounding is presentation only — the cursor keeps the full-precision weight, which is why
clicking a crossover shows something like `0.5688552162065278`.

## 9. Limits

Sensitivity is one-way and read-only. There is no multi-way sensitivity, no Monte Carlo analysis
and no way to save an explored weight. Sweeps and probes respect the viewed
[scenario](scenarios.md) and profile.
