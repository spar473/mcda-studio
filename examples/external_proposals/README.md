# External proposal demonstrations

Two invented Option A/B decisions exercise the same local import/review/compiler: venture
screening and supplier risk classification. Every company, source, tool output, confidence and
review is invented. These are illustrative workflows, not factual evidence or investment advice.
No external tool runs, no reference is fetched and no project data is sent to a provider.

`build.py` states every input. The screening labels are hardware/software and early/ready; the
supplier labels are low/medium/high risk and early/ready. Numeric measures are illustrative values
on [0,1]. The categorical value mappings and swing ratings are invented preferences, not outcome
probabilities. The imported numeric score 0.91 is rejected; it never activates a proxy criterion.
Confidence 0.83 is metadata only. Sources describe independent or self-reported relationships,
not numerical quality grades. Human comparison labels cite the same invented brief so agreement
is not independent validation.

For each domain the directory contains a project, JSON intake, equivalent CSV and local registry
JSON, explicit review events, a reviewed workspace and a reconstructible compilation bundle.
The worked history corrects the first cell proposal, accepts a readiness claim and an annotation,
rejects a numeric proposal and a tag, and leaves a second tool and a source assertion pending.
Original disagreement remains visible after the correction. The complete bundle preserves every
original payload, model card, source, confidence and review; only its selected cell subset reaches
the unchanged evidence compiler. The independent oracle is
`tests/regression/proposal_oracle.py`.

Rebuild without network access:

```sh
.venv/bin/python examples/external_proposals/build.py
```

In the GUI, import `supplier-project.json` (or `screening-project.json`) from Projects. Open
Evidence → External proposals and import its intake JSON. Alternatively select CSV, select its
registries JSON, then select its CSV. Filters do not select proposals. Choose a tool or human
comparison and inspect a cell's originals and effective values side by side. Explicitly select
`readiness_b` and `tag_b`, choose Accept, supply a reviewer/note and explicitly choose each sole
cited source. Preview lists both proposals; confirm that exact list. Review `cell_a_first`
individually and correct its full typed payload (`medium` for supplier, `hardware` for screening).
Reject `numeric_b`. Leave the other proposals pending and inspect Open Questions.

Acknowledge the compilation preview, compile and export both the separate project and the complete
proposal bundle. The source project/library and undo history stay unchanged. Export the nested
evidence compilation when citing it in an existing version-2 decision record. Keep the outer
proposal bundle beside that record for the complete intake metadata and annotations. Reopen the
outer bundle to verify replay; importing its project alongside the original uses the existing
separate-copy receipt workflow. Sidecars are exported files, not library autosave.

CLI example (create `work/` first; output files must not already exist):

```sh
.venv/bin/mcda proposals import examples/external_proposals/supplier-project.json examples/external_proposals/supplier-intake.json --output work/proposals.json
.venv/bin/mcda proposals inspect examples/external_proposals/supplier-project.json work/proposals.json --comparison-target human
.venv/bin/mcda proposals review examples/external_proposals/supplier-project.json work/proposals.json examples/external_proposals/supplier-reviews.json --bulk --output work/reviewed.json
```

The last command previews every affected proposal without creating the output. Repeat it with
`--confirm-selection DIGEST`, using the printed confirmation digest. The supplied event file has
one event per proposal with identical reviewer/time/note; an individual correction of an otherwise
blocked proposal uses a one-event file without `--bulk`. A blocked item cannot participate in bulk
review, even to reject it. There is no accept-all default. Inspect the reviewed workspace to obtain
its `review_digest` and `workspace.digest`, then:

```sh
.venv/bin/mcda proposals compile examples/external_proposals/supplier-project.json work/reviewed.json --review-digest REVIEW_DIGEST --workspace-digest WORKSPACE_DIGEST --output work/compilation.json
.venv/bin/mcda proposals verify work/compilation.json
```

JSON Schema and the exact CSV contract are in `docs/schemas/`. These demonstrations are currently
checkout examples; the later starter-gallery development packages its selected artifacts.
