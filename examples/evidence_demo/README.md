# Evidence review demonstrations

> **Fabricated data.** `vc.json` attaches invented market-size claims to one of the real companies
> in the [`nz_deeptech_vc`](../nz_deeptech_vc/README.md) example, and `vc-decision.json` is an
> invented decision record. They exist only to demonstrate the review workflow. They are not
> evidence about, or a statement on, that company.

## Graphical review and export

Import the exact bundled `nz_deeptech_vc` or `supplier_qualification` project, open **Evidence**,
and select its `vc.json` or `supplier.json` dossier here. Inspect the source, proposal origin,
review status, conflicting values and current measurement support. Choose **Review
unreviewed_example**, name yourself, reject the conflicting proposal, and select **Preview review**.
Inspect the proposed changes, then **Confirm review in workspace**. Acceptance/correction is also
supported; only one claim can be accepted per measurement, so explicitly reject the earlier
accepted claim before accepting a replacement.

## Graphical compilation and a separate copy

After confirming the review, the **Compile reviewed evidence into a separate copy** section lists
each measurement the copy would change with its unit, current value and supporting claim. Tick
**I reviewed every measurement change for the separate copy**, then **Compile reviewed copy**.
Export both **Export compiled project copy** and **Export evidence compilation bundle**. The open
project, its saved file and undo history do not change.

On **Projects → Import file…**, select the compiled project. Because the original project is still
there, choose **Import as a separate copy**, then **Download copy receipt**. Open the copy, select
the bundle in **Evidence**: it is verified and shown historically, with review blocked. Select the
receipt under **Copy receipt (optional)** to see the verified relationship: only the project ID
changed. In the original project, the same bundle is recognised as its source. See
[separate-copy provenance](../../docs/design/separate-copy-provenance.md).

**Export review workspace** retains the original project, original dossier and appended history.
Reload the app and select that exported workspace to resume. **Export reviewed dossier** and
**Export compilation preview** produce the inputs for the CLI workflow below. Reviewing does not
update the project, and exported dossiers bind to the original project fingerprint. Editing the
project makes the dossier stale; there is no automatic rebinding. Open Questions uses the reviewed
dossier while the workspace is open. See the [design](../../docs/design/evidence-workspace.md) and
[pending independent-user protocol](../../docs/development/integrated-workspace-verification.md).

## Graphical decision records

In the imported copy, open **Decision**. Name an owner, choose the selected alternative, write a
rationale, assumptions and triggers, and keep or add analyses (at most six). Under **Supporting
bundles and copy receipts**, select the evidence compilation bundle and its copy receipt. Then
choose **Preview decision record**: the record shows the analyses (including any explicitly
unavailable), feasibility beside the choice, the receipt-verified bundle and which measurements
it set. **Export decision record**. Later, open the record under **Open a decision record**,
choose **Revise this record**, change an assumption, preview and export the revision. Opening the
revision with its predecessor confirms the link; the first record file is never changed. See
[decision records](../../docs/design/decision-records.md).

These checkout-only dossiers use fabricated claims and reviewers; they are not evidence about real companies or
suppliers. Both use the same domain-neutral CLI and leave the bundled projects untouched. Each has
one reviewed value, a conflicting unreviewed claim and an outdated flag. An uncertainty range
records a stated range only: it is not a probability distribution and does not drive SMAA-2.

From the repository root, choose either pair:

```sh
.venv/bin/mcda evidence preview examples/nz_deeptech_vc/project.json examples/evidence_demo/vc.json
.venv/bin/mcda evidence preview examples/supplier_qualification/project.json examples/evidence_demo/supplier.json
```

Inspect the change, gaps, conflict, and `review_digest` in the JSON. Copy the digest from the
chosen preview into the corresponding command, replacing `<digest>`:

```sh
.venv/bin/mcda evidence compile examples/nz_deeptech_vc/project.json examples/evidence_demo/vc.json --review-digest '<digest>' -o /tmp/mcda-vc-evidence-copy.json
.venv/bin/mcda evidence compile examples/supplier_qualification/project.json examples/evidence_demo/supplier.json --review-digest '<digest>' -o /tmp/mcda-supplier-evidence-copy.json
```

Choose a new output filename if it already exists. Inspect the copy and run `mcda evaluate` on it.
The preview is not a decision record; its digest binds the source project, dossier, issues and
proposed changes. If either input changes, generate and review a new preview.

After compiling the copies, create illustrative decision records:

```sh
.venv/bin/mcda decision record /tmp/mcda-vc-evidence-copy.json examples/evidence_demo/vc-decision.json --evidence-file examples/evidence_demo/vc.json --evidence-project examples/nz_deeptech_vc/project.json -o /tmp/mcda-vc-decision.json
.venv/bin/mcda decision record /tmp/mcda-supplier-evidence-copy.json examples/evidence_demo/supplier-decision.json --evidence-file examples/evidence_demo/supplier.json --evidence-project examples/supplier_qualification/project.json -o /tmp/mcda-supplier-decision.json
```

Each record includes the project, complete analysis, rationale and evidence snapshot. A later
revision can pass `--previous /tmp/mcda-supplier-decision.json` and a new output filename.
