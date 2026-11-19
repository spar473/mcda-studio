# Name-swap check

**Accepted by the owner through the overnight prompt, 7 November 2026** (ROADMAP row 12h). Part of
the external [typed-proposal runner](typed-proposal-runner.md); the application is unchanged.

## Purpose

A language model reading about a company may be moved by the name rather than the text: a famous
founder, a recognisable brand. The check asks a plain question of a classifier: if the names in the
source text are swapped for others, do its answers change? It is a diagnostic for a person, not a
score, and it says nothing about whether either set of answers is correct.

## How it works

- `questions --swap swap.csv` takes a CSV with the header `original,replacement`. Each original
  string in the saved page text (and in the company name shown to the model) is replaced, exactly
  and case-sensitively, longest first and in one pass so replacements never chain. The result is a
  **paired question set**: the same questions in the same order, with the same labels and rubrics,
  whose state text and digests differ where a name changed. The file records the number of pairs
  and their digest. `--swap` can be combined with `--redact`; the swap applies first.
- `compare-runs RUN_A RUN_B --out report.json` compares two runs of the same question IDs (it
  refuses runs that answered different questions or offered different options). For each cell it
  reports whether the top label changed and the probability shift per option (B minus A, exact
  decimals), then the number of cells whose top label changed and unchanged, and the largest
  shifts. The report is written under `$MCDA_DATA`; a path inside the repository is refused.

## What is committed and what is not

Only a template `examples/nz_venture_screening/swap-template.csv` (header and two invented rows)
and synthetic tests are committed. The owner writes the real list. The runner does not extract
founder or company names from the snapshots, so no real person's name is chosen by a tool.

## Verification

Identical runs give zero differences; an injected change to one cell is detected with its exact
shift; the swap replaces longest names first without chaining and is case-sensitive; the file's
header and uniqueness are enforced; different question sets and in-repository reports are refused;
and the group's mutants.
