# Blind rater kit and a frozen benchmark protocol

**Accepted by the owner through the overnight prompt, 7 November 2026** (ROADMAP row 12e,
the roadmap (not included), item 4).
Implemented as `scripts/rater_kit.py`, outside the application. No stored project, evidence,
proposal or result format changes, and the classifier agreement benchmark is unchanged.

## Problem

The [classifier agreement benchmark](classifier-agreement-benchmark.md) refuses to compare any
tool with a reference until two people have labelled the same items independently and their
agreement passes a frozen gate. The venture-screening study has one rater, its author. Without a
second, blind rater no classifier result can be read honestly. This kit lets a second person rate
the study's cells from the cited pages and the written rubrics alone, and prepares the benchmark
protocol so it is frozen before any tool output exists.

## What is rated

The cells are the 14 rubric leaves with labelled levels by the 8 companies: **112 cells**. The two
numeric market leaves (market size and growth) and the three mandate leaves (HQ country, stage and
sector, which are screened and rated 0) are excluded.

`examples/nz_venture_screening/build.py` also writes `rubrics.json`: for each scored leaf its ID,
name, parent objective, scale type, labels worst to best, rubric text and whether it is numeric,
and the mandate leaves listed as screened and excluded. The five existing written files stay
byte-identical and two builds stay identical. `rubrics.json` is not part of the starter manifest.

## Subcommands

| Command | Does |
| --- | --- |
| `make` | Writes `rater-packet.html`, `rater-form.csv` and `items.json` |
| `convert` | A rater's answers (the packet's JSON or the form's CSV) to benchmark `human_labels` rows for reviewer `R2` |
| `author-labels` | The study author's existing ratings as reviewer `R1` rows (the human side, so project measurements may be read) |
| `manifest` | Drafts and **freezes** one benchmark protocol per task, with a digest |
| `finalize` | After labels, tool outputs and a tool card exist, assembles a valid benchmark manifest from a frozen protocol, refusing any change to the frozen part |

### The packet

`rater-packet.html` is self-contained. It has no network request, storage, server or external
asset; inline JavaScript only collects form values and offers a "Save answers" download. It gives
instructions, then for each company (in seeded random order) its name and the **links** to the
sources cited for it, then for each rubric leaf (in seeded random order) the rubric text, the
labels as radio buttons, a "cannot tell" option and a free-text note. `rater-form.csv` carries the
same content for a spreadsheet; its cells are protected from being read as formulas.

The packet shows, for each company, only the links of the sources cited for that company's rubric
cells. It never shows any value, description, review, note, outdated flag, uncertainty field,
measurement, class, rank or rating. The order is a hash of the seed, so the same seed gives
byte-identical files.

### Tasks and labels

The benchmark takes one task with one ordered label vocabulary per manifest. The 14 leaves have
five levels (nine leaves, 72 items) or four (five leaves, 40 items), so the kit writes **two
tasks** with positional labels `level_1` (worst for the fund) to `level_n` (best). Each frozen
protocol records the mapping from each level to the criterion's own wording. Treating position as
the label across criteria is a simplification: unweighted kappa treats the ordered levels as
nominal, so it is conservative for ordinal labels, and the manifest says so. A task with fewer than
30 items would be marked underpowered in its description; neither is.

### The frozen protocol

The benchmark manifest embeds the SHA-256 of its item, label, tool-output, card and adjudication
files, so a complete manifest cannot exist before tool output does. The kit therefore freezes the
**manifest core**: everything the benchmark's protocol fixes (task, labels, panel, split,
thresholds, bootstrap design, chronology, data provenance) plus the digest of the items table. The
digest of that object is recorded. `finalize` refuses to assemble a manifest from a core whose
digest differs from the recorded one. This freezes the protocol before any tool output exists, which
is what the benchmark's rule requires, without changing the benchmark.

- Every item is in the test split (zero-shot; nothing is trained); the train and development lists
  are empty, so the majority baseline is reported as unavailable.
- The entity and the bootstrap group are the company, so the 14 cells of a company move together.
  Eight groups give wide bootstrap intervals; the gate may well refuse. That is the benchmark
  working as designed.
- The gate is the design's recommendation: lower 95% bound of 0.60 and 80% complete-label
  coverage. The bootstrap seed is fixed in the script.
- `data_kind` is `public`, with source, licence ("unknown - private research copy, not for
  redistribution") and a snapshot digest. The digest is that of the cited-source identity list
  (URL, name and date of each source), because page snapshots are taken later by the typed-proposal
  runner and digested in its run manifests.
- Chronology: `frozen_at` is the time of freezing. The benchmark requires human review times to
  lie between `frozen_at` and the gate confirmation, but the author rated on 4 November 2026,
  before the freeze. `author-labels` therefore stamps the R1 rows with the freeze time, and the
  description records the real date. This is a limitation of the benchmark's chronology check,
  reported to the owner rather than worked around by moving the freeze date. The gate-confirmation
  and unblinding dates are declared deadlines (31 March and 30 April 2027).

## Leakage rules

From the evidence dossier the packet and the later classifier may use only source identity: name,
URL and publication date. The kit reads each claim's alternative, criterion and source reference
and nothing else. Project measurements are read only by `author-labels`. A canary test plants
unique strings in evidence values, descriptions and in project measurements and asserts none
reaches the packet, the form or the item table.

## Privacy and refusal

Every output path, and the answers file, is resolved through symlinks and refused inside the
repository. Files are created exclusively; nothing is overwritten. The packet, the rater's answers,
the labels and the manifests are real data and live under `$MCDA_DATA`.

## Verification

A synthetic study fixture (invented companies, rubrics and sources); the canary test; byte-identical
output for the same seed; a round trip from the converter into the benchmark's own validation and
evaluation on synthetic two-rater labels; refusal of inside-repository outputs; and mutants.

## Out of scope

Any tool output, any comparison of a tool with the author's ratings, adjudication, and a hosted
rating service. The second rater's recruitment is the owner's task.
