# Typed-proposal runner: how to use it

`scripts/typed_proposal_runner.py` classifies the pages a study cites into **External Proposals**
that a person then reviews in the application. It is a separate script: the application never calls
a model, and the script never imports the application. The design and its limits are in the
[design note](design/typed-proposal-runner.md). Model output is only ever a proposal. Confidence is
metadata. It predicts no company's success and recommends no investment.

Real data (pages, answers, model outputs) goes under `$MCDA_DATA` (default `$HOME/mcda-data`;
earlier records name `$HOME/Documents/mcda-data`, its place until 8 November 2026), never inside
the checkout; the script refuses any such path inside it.

## Set up the free local model once

The local model runs from a separate virtualenv, never the project's hash-locked one:

```sh
python3.12 -m venv "$MCDA_DATA/venv-classifier"
"$MCDA_DATA/venv-classifier/bin/python" -m pip install torch transformers
```

Downloading the model is explicit. `Qwen/Qwen2.5-1.5B-Instruct` is Apache 2.0, needs no account
and is about 3 GB:

```sh
MCDA_ALLOW_MODEL_DOWNLOAD=1 "$MCDA_DATA/venv-classifier/bin/python" scripts/typed_proposal_runner.py \
  fetch-model --out "$MCDA_DATA/models"
```

## The steps

```sh
RUN=scripts/typed_proposal_runner.py
E=examples/nz_venture_screening
D="$MCDA_DATA/nz-venture-2026-11-04"
PY="$MCDA_DATA/venv-classifier/bin/python"

python $RUN snapshot --evidence $E/evidence.json --out "$D/snapshots"
python $RUN reextract --snapshots "$D/snapshots"        # optional: cleaner text, no re-fetching
python $RUN questions --project $E/project.json --rubrics $E/rubrics.json --evidence $E/evidence.json \
  --snapshots "$D/snapshots" --extractor 2 --out "$D/questions.json"
$PY $RUN run --questions "$D/questions.json" --backend local-hf \
  --model-path "$MCDA_DATA/models/Qwen2.5-1.5B-Instruct" --out "$D/run-local-hf"
python $RUN export --run "$D/run-local-hf" --project $E/project.json --threshold 0.5 --out "$D/export-local-hf"
```

Then, with the application, import and review:

```sh
mcda proposals import $E/project.json "$D/export-local-hf/proposals.csv" --format csv \
  --registries "$D/export-local-hf/registries.json" --output "$D/workspace.json"
mcda proposals preview $E/project.json "$D/workspace.json"
```

`--extractor 1` (the default) reads `snapshots.json`, the text as first extracted; `--extractor 2`
reads `snapshots.v2.json`, written by `reextract`.

By default `run --backend local-hf` scores every question under **every cyclic order of its
options** ("cannot tell" included) and averages the options' probabilities, so a preference for a
letter position cancels in the average. Each question's raw record keeps every rotation's letter
log-probabilities and the option under each letter, plus `order_top_agreement` (the share of
rotations whose top option is the averaged top option) and `order_max_shift` (the largest change in
any option's probability across rotations). `--order-averaging none` scores one order, for
comparison only. The run manifest and the model card say which was used ("first-token letter
log-likelihood, averaged over n cyclic option orders"). Averaging removes position bias from the
average; it does not make the probabilities calibrated.

The `run-report.json` beside the export lists counts only: proposals, abstentions with their
reasons, and the label distribution per criterion. Do not compare the tool with the study author's
ratings before a second human rater has labelled the same cells and the benchmark's agreement gate
has passed (see the [rater kit](design/blind-rater-kit.md)).

## Cleaner page text (`reextract`)

`reextract --snapshots DIR` rebuilds each saved page's text from its raw bytes (never re-fetching)
and writes `snapshots.v2.json` and `text.v2/` beside the version-1 files, which stay untouched. The
version-2 filter keeps only the first occurrence of each exact repeated line within a page, drops
lines of three words or fewer that also appear in at least one other saved page from the same host
(menus, cookie notices, footers), and keeps everything else in order. Each page records the
characters before and after and the extractor version. It refuses to overwrite an existing
version-2 index, a page whose raw bytes no longer match their hash, and any directory inside the
checkout.

## Other backends

- `--backend replay --replay FILE` re-scores recorded responses offline (used by the tests).
- `--backend jev --allow-network` calls TypeSafe's System One endpoint with the key in
  `TYPESAFE_API_KEY`, using the pinned default model `jev-1.13.0`. Nothing is sent without both.
  Like `local-hf`, it asks every question once per cyclic option order by default (about n times
  the tokens of one order), and `--order-averaging none` asks once. It prints its estimated input
  tokens before any request; `--max-input-tokens N` refuses a run whose estimate is over N. Run it
  as a separate run and export it separately.
- `--backend laya --model-path DIR` runs a [Laya](https://pypi.org/project/laya/) checkpoint from a
  local directory, with the Hub offline. Laya is free and Apache 2.0. Install the pinned package
  into the classifier virtualenv (it adds `vegaml` and `cryptography`; check that `torch` and
  `transformers` did not move), then download the two named checkpoints:

  ```sh
  "$MCDA_DATA/venv-classifier/bin/python" -m pip install laya==0.4.32
  MCDA_ALLOW_MODEL_DOWNLOAD=1 "$PY" $RUN fetch-model --repo convaiinnovations/laya --out "$MCDA_DATA/models"
  MCDA_ALLOW_MODEL_DOWNLOAD=1 "$PY" $RUN fetch-model --repo convaiinnovations/laya-typed-decisions \
    --out "$MCDA_DATA/models"
  ```

  `fetch-model` accepts only Qwen and these two repositories. Build Laya's own question file
  (`questions --backend laya`; `--budget-chars 12000` matches the `local-hf` text). Each question
  is asked as a Laya `choice` over its options; the page text is split into paragraph chunks that
  fit the checkpoint's window (512 tokens for the base model, 1,024 for typed-decisions, read from
  the checkpoint), every chunk is scored under every option order, and the probabilities are
  averaged, over chunks and then over orders. A question whose rubric the package would cut is
  refused and listed in the run manifest and the export's `run-report.json`. Each raw record keeps
  the chunks' digests, `chunk_top_agreement` and, for comparison only, `max_confidence_chunk_top`.
  The base checkpoint is not fine-tuned for this task (its vendor reports near-random zero-shot
  accuracy); typed-decisions is fine-tuned on unrelated workflows, not on startup screening.

  Since 16 November 2026 a Laya run also records a **second reading**: the vector of the most
  confident chunk (the package's own long-text rule), beside the mean, which stays the reading.
  `export --reading max-confidence-chunk` proposes from it, and its proposals and model card say so;
  plain `export` is unchanged. A run made before then has no second reading and is refused; run it
  again. Neither reading is claimed to agree better with a person.

## Name-swap check

`questions --swap swap.csv` (columns `original,replacement`) replaces names in the page text and
gives a paired question set; `compare-runs RUN_A RUN_B --out report.json` then lists which cells'
top label changed and how far each option's probability moved. See `swap-template.csv` in
`examples/nz_venture_screening/`; you write the real list.
