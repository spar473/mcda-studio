# Invented classifier-agreement inputs

These are synthetic nominal labels and anonymous reviewer/tool identifiers. No external model
was run, no real data was used, and no outcome is predicted. The standalone script is outside
the application. The benchmark is implemented and locally verified; see the
[verification record](../../docs/development/classifier-agreement-benchmark-verification.md).

`build.py` constructs 150 observations: 20 training, 10 development and 120 held-out test items.
Training labels are four `alpha` and sixteen `beta`; development/test labels alternate. Each
pair belongs to a distinct split-specific entity/group. Generation seed 47 selects eight of the
54 complete test groups for one second-reviewer disagreement each. The first six test groups
have explicit second-reviewer abstentions: twelve excluded panels and 108 complete panels.
The original labels and supplied review times remain in the input table and report.

The version-1 protocol freezes the task, vocabulary, split, blind-review declarations, operational
gate, bootstrap seed 73 and 10,000 grouped replicates. The generated human kappa is exactly 23/27
and complete-panel coverage is 9/10. Six of eight disagreements are adjudicated after the passed
gate and before declared tool unblinding; twelve abstentions and two remaining disagreements are
unscorable. The reference therefore covers 106 of 120 test items. The majority baseline is `beta`,
selected from the training labels, with vocabulary-order tie breaking.

Three invented output tables use index rules for errors and abstentions. They declare, respectively,
full probability vectors, chosen-label confidence and arbitrary numeric scores. Vector values are
explicit decimal .8/.2 or 1/0; chosen confidence is .5 or .75; arbitrary scores are the row index
modulo 101. These are data-generation rules, not calibration evidence or model performance claims.
Only declared probability/confidence semantics are eligible for calibration summaries. The
`refused/` fixture supplies poor human agreement and no adjudications; it must stop before tool
metrics. All source numbers and dates are invented and specified in `build.py`.

From the checkout or a source tree containing these files:

```sh
python examples/classifier_benchmark/build.py
python scripts/classifier_agreement_benchmark.py --manifest examples/classifier_benchmark/synthetic/manifest.json --output NEW_REPORT_DIRECTORY
python scripts/classifier_agreement_benchmark.py --verify-report NEW_REPORT_DIRECTORY/report.json
```

The output directory must not exist. JSON, human/confusion count CSV and static HTML are local
files. Probability-vector sum validation is exactly zero, without normalization. Counts, kappa,
coverage, confusion metrics and decimal calibration summaries are exact rationals; display values
and linear bootstrap percentile endpoints are binary64. Every undefined replicate refuses the CI.
Real inputs and reports are refused inside the checkout after resolving paths and symlinks.

Current declared limits are 8 MB per input file, 64 MB total inputs, 2,000 items, 20 reviewers,
32 labels and 20 tools; a report larger than 64 MB is refused before anything is written. The
reserved `__abstention__` column cannot be a task label. Strict version-1 manifest and report
schemas are in `docs/schemas/classifier-agreement-*-v1.schema.json`; regenerate them with
`--write-schemas DIRECTORY`. The independent oracles are in
`tests/unit/test_classifier_agreement_benchmark.py`.
