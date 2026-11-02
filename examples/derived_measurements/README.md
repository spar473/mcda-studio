# Two synthetic calculation workflows

These checkout-only demonstrations use the same generic engine. All source values, review names
and dates are invented for testing. They are not evidence about real companies or suppliers.

| Model | Calculation | Expected outputs |
| --- | --- | --- |
| venture | addressable customers × adoption rate × annual revenue/customer | NZD 600,000/year and 640,000/year |
| supplier | setup + purchase volume × price + years × annual maintenance | NZD 155,000 and 161,000 |

Both alternatives share upstream factors. The supplier model also uses an intermediate purchase
volume. Formula reviews are explicit, just like source reviews. Build deterministically with
`.venv/bin/python examples/derived_measurements/build.py`.

From the repository root, preview a model:

```sh
.venv/bin/mcda derived preview examples/derived_measurements/venture-project.json examples/derived_measurements/venture-model.json > /tmp/venture-preview.json
```

Read the calculations, source/reviewer history, dimensions, issues and `review_digest`. To compile,
substitute that digest below and choose a new output path:

```sh
.venv/bin/mcda derived compile examples/derived_measurements/venture-project.json examples/derived_measurements/venture-model.json --review-digest DIGEST --output /tmp/venture-calculated.json
.venv/bin/mcda evaluate /tmp/venture-calculated.json
```

Repeat with `supplier-project.json` and `supplier-model.json`. Keep each original project, model
and preview together. The new project contains static measurements: changing a source requires a
new reviewed preview and new compilation. This slice does not embed a live formula in the project.
If any path already exists, compilation refuses to overwrite it.

In the local GUI, import either `*-project.json`, open **Measurements**, expand **Calculated
measurements**, and select its `*-model.json`. Inspect the expression, source factors and review
history, then download the calculation preview. Viewing changes no project bytes or undo history.
The interface can compile a reviewed preview: inspect the original-to-calculated target changes,
tick **I reviewed all target changes for the separate copy**, then **Compile reviewed copy**.
Export both the compiled project and the calculation bundle. Import the project through Projects
and choose a separate copy on ID conflict. The original project is preserved. Reopen the bundle
through **Calculation model** on the original project to verify its digest and reproduce the
compilation. **Recalculate preview** requires a fresh target acknowledgement. Formula/factor
editing still uses sidecars; no live formula migration is implied. No probability distribution is inferred. Deterministic compilation produces a static copy;
the separate factor-run workflow below propagates only explicitly reviewed distributions.

## Editing and applying in the GUI

Import either project and open **Measurements → Calculated measurements**. Select its
`*-model.json` (or **Start a new calculation model**) and enter your name. Under **Source inputs
and review**, revise a factor, for example `adoption_a` to 0.07 or `annual_units` to 1200: it is
pending, and the dependent calculations are unavailable, until you **Review** and accept it.
**Measurement changes** then shows current and calculated values; tick **I reviewed every
measurement change to apply** and **Apply to this project**. In both demonstrations a revision
like these changes which option leads: check **Results**. Undo removes the whole application.
Export the calculation workspace (and the bundle for this application) before Save, then reopen the
workspace later to reproduce the values. Formula errors are explained before acceptance, for example
adding a cost to a count.

## Fresh-user protocol — not yet performed

Use an independent participant unfamiliar with the application. Give them only these tasks, first
with the venture model and then the supplier model, without coaching:

1. Find the calculated result and explain where its number comes from.
2. Identify which source is shared by both alternatives and who reviewed it.
3. Explain what changing a source would require and whether the saved project changed while viewing.
4. Identify what the result does and does not say about uncertainty.

Record task completion, time, wrong turns, prompts needed and the participant's explanation.
Require correct source tracing and no confusion between a model estimate, evidence accuracy and a
probability. Review any failures before expanding formula editing. No independent human usability
checkpoint has passed.


## Fundamental-factor uncertainty

In the calculation panel, expand **Fundamental-factor uncertainty** and start a sidecar bound to
the current project and model. Name a reviewer, choose a source factor and its numeric marginal,
and **Set pending distribution**. Shared factors already share their realization. Add a quantile
group only to state shared quantiles between distinct factors. **Inspect factor assumptions**
shows source classifications, dependencies and pending reviews. Explicitly accept distributions
and coupling, choose a run type, draw count and seed, then **Run factor uncertainty**. Weights are
fixed; additional cell/weight uncertainty is refused, including cell uncertainty on a derived
target. No distribution is inferred from a range. Export the reviewed sidecar and completed run;
optionally retain a decision snapshot. Nothing edits the project. Open the run to verify it, or
load it in Open Questions to review shared-factor assumptions.

The same bound files evaluate through the CLI:

```sh
.venv/bin/mcda derived uncertainty-run PROJECT.json MODEL.json UNCERTAINTY.json --run smaa2_factors --draws 1000 --seed 7 --output /tmp/new-factor-run.json
.venv/bin/mcda derived verify-uncertainty /tmp/new-factor-run.json --replay
```

Select `--run mavt` or `--run mavt_sorting` for those draw types, or
`--evaluation exact_enumeration` for discrete factors. Sorting needs classes in the project.
The first sixteen realizations are displayed; a digest covers every draw. Any invalid draw aborts
with its index and factor/formula IDs. The record retains all input snapshots and versions;
replaying stochastic results requires the recorded supported environment. Acceptabilities describe
the stated assumptions, never source accuracy or a real-world outcome probability. The minimal
editor has no distribution plots or arbitrary correlation controls. See the
[integration verification](../../docs/development/factor-uncertainty-integration-verification.md).
