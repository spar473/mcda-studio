# Classifier agreement benchmark: verification

2 November 2026. Implements the [accepted design](../design/classifier-agreement-benchmark.md).
The pre-Part-B baseline (historical record, not included) remains the numerical/export reference;
the [disclosed proxy record](disclosed-model-proxy-verification.md) is the preceding development.
The [owner's arithmetic contract](../design/derived-measurements.md#arithmetic-contract) applies.

**Implemented and locally verified**, with the named limitations below. The benchmark is a
standalone script outside the application: it imports no application module, calls no model or
network service, and changes no engine, project, sidecar or result format.

## Implemented boundary

`scripts/classifier_agreement_benchmark.py` reads a version-1 manifest and four local JSON tables,
checks every declared SHA-256, runs the human–human agreement gate (exact Cohen or Fleiss kappa,
complete-panel coverage and a seeded 10,000-replicate joint item/group bootstrap), resolves the
reference only after a passed gate, then reports exact confusion, abstention, training-majority
baseline and conditional calibration summaries. It writes a sealed JSON report, a count CSV and an
escaped static HTML page into a new directory, and reopens a report by digest.

Boundary fixes made during verification, all in new code:

- **Report size.** The reader previously reopened at most 8 MB, but a report embeds the manifest
  and raw human labels and could exceed that at the declared input limits. The writer now refuses,
  before creating the directory, any report above the size the verifier reopens (64 MB), and the
  verifier uses the same limit.
- **Digests.** Declared file, model-card and public-snapshot digests must be lowercase SHA-256.
  A public dataset needs a source, licence and snapshot digest; the snapshot digest is a
  declaration only, because the script never fetches the public source.
- **Schemas.** `--write-schemas DIR` writes strict version-1 JSON Schemas, committed as
  `docs/schemas/classifier-agreement-manifest-v1.schema.json` and
  `docs/schemas/classifier-agreement-report-v1.schema.json`. The script's own validation remains
  the authority for cross-field rules (chronology, digests, split membership, frozen thresholds).
- **Source archive.** The sdist now includes `examples/classifier_benchmark/` and `docs/schemas/`.

## Independent oracles

`tests/unit/test_classifier_agreement_benchmark.py` (41 tests) re-reads the invented tables with
the standard library and recomputes every value without reusing the script's arithmetic:

- **Agreement.** Cohen from matched pairs and Fleiss from per-item agreement, as exact `Fraction`
  values, on 240 seeded random panels of two to five reviewers and a Hypothesis property; kappa is
  invariant to item order, label renaming and reviewer order; constant panels are undefined, never
  zero.
- **Fixture.** Kappa 23/27, coverage 9/10, 120 held-out test items, 106 references (100 unanimous,
  six post-gate adjudications), complete-panel reference coverage 106/108, training-majority `beta`
  from counts 4/16, every input digest, per-class true positives, support with abstentions,
  predictions, precision, recall, accuracy and coverage for all three tools, Brier score and every
  unweighted calibration bin.
- **Bootstrap.** An independent replay draws the whole PCG64 stream in one call and recomputes each
  replicate's kappa from the raw labels of the resampled groups. All 10,000 exact replicate values
  equal the script's (engine-to-engine, exact). Chunk sizes 1, 7, 32, 300 and 1,000 give identical
  values, undefined indices, intervals and sealed digests; a Hypothesis property checks arbitrary
  panels, seeds and chunk sizes. A tiny enumerated case confirms every replicate lies in the
  enumerated support and that constant resamples refuse the interval; a two-group case confirms
  whole groups are resampled jointly.
- **Percentile endpoints.** The binary64 endpoints `0.7592592592592593` and `0.9444444444444444`
  are compared with the exact rational type-7 percentiles at position (R − 1)p, p = 1/40 and 39/40,
  under a forward-error bound derived in the test from the unit roundoff, the rounded virtual index
  and the three interpolation roundings. No fixed tolerance is used.
- **Gate thresholds.** The lower bound is compared with binary64 0.60 (0.5999999999999999 fails);
  coverage is compared with exact 4/5.

Refusal and boundary tests cover the refused cohort (no tools, no baseline, the single truthful
reason "Lower 95% bound is below 0.60"), byte-for-byte replay, overwrite refusal, report
tampering and unknown report versions/algorithms, unknown manifest versions, changed inputs,
thirteen malformed or out-of-protocol manifests (string version, duplicate or reserved labels,
float/boolean seeds, wrong replicate count, changed thresholds, unblinded review, reversed
chronology, missing timezone, malformed digest, overlapping splits, a declared public dataset
inside the checkout), public provenance, real inputs reached through a symlink into the checkout,
real reports inside the checkout, oversized reports, pre-gate adjudication, and CSV formula and
HTML escaping. The committed schemas must equal the script's; both fixture manifests and both
written reports conform to them under an independent validator, and unknown versions, unknown
fields and the reserved label are refused.

## Mutation reachability

Nine new mutants run through `python scripts/mutation_check.py --benchmark-only`; each must reach a
test failure, and a fixture refused by the script's own `BenchmarkError` guard counts only when the
crash is that guard:

| Mutant | Caught by |
| --- | --- |
| Bypass the human agreement gate | refused-cohort test |
| Score training items as held-out test items | stale-gate adjudication guard (the gate digest changes) |
| Choose the majority baseline from test labels | reference and baseline oracle |
| Omit abstentions from recall | confusion oracle |
| Replace an undefined replicate with zero | bootstrap replay property |
| Resample reviewer labels independently of their panels | bootstrap replay property |
| Discard undefined replicates and still report an interval | bootstrap replay property |
| Weight calibration frequencies by reported confidence | calibration oracle |
| Omit an input digest from the sealed report | input-digest oracle |

All nine were caught in a focused run and the unmodified copy passed before and after. No formula
or statistical mutant survived its bound.

## Application gate

The complete gate ran once on the benchmark and the release clean-up together, all ten commands
exiting 0:

| Check | Result |
| --- | --- |
| Python tests | 1,957 passed (1,916 before, plus these 41), 64.45 s |
| Ruff check and format, strict mypy (105 source files), OpenAPI freshness | Passed |
| Acceptance demo and acceptance evidence | Passed |
| Frontend unit tests, lint and production build | 451 passed in 57 files |
| Browser tests | 113 passed, 259.22 s |
| Mutation campaign | 344 of 344 caught (264 backend, 80 frontend), unmodified copy passes, 1,615.32 s |
| Original pre-Part-B outputs | 969 of 969 byte-identical against the original manifest |
| Captured complete factor records | 12 of 12 byte-identical |
| Packaging | Direct and sdist-rebuilt wheels byte-identical; offline isolated install, installed GUI and browser smoke passed; the extracted source archive runs the benchmark, verifies its report and passes these 41 tests |

No old project, sidecar, result or API schema changed; no existing test, tolerance or oracle was
modified. The package was built before the last documentation-only edits, so a final archive
differs from the smoked one only in documentation text.

## Named limitations

- The HTML report was checked for escaping by test but not visually reviewed in a browser.
- The item, reviewer, label, tool and byte limits are enforced but not exercised at their exact
  boundaries by a test.
- Blind review, freeze and timestamps are supplied local attestations, not signatures; a public
  snapshot digest is a declaration, not a fetched check.
- The schemas are a structural contract; cross-field rules live only in the script.
- Agreement does not prove independence, transfer to another population or causal validity, and
  human-reviewed labels are not objective truth or outcome probabilities.
- No hosted CI run is claimed for this development.
