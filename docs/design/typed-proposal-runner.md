# Typed-proposal runner (external; the application is unchanged)

**Accepted by the owner through the overnight prompt, 7 November 2026** (ROADMAP row 12g,
the roadmap (not included), items 1–3).
Implemented as `scripts/typed_proposal_runner.py`. Usage is in the [runner README](../typed-proposal-runner.md).

## Purpose

Prove the published [External Proposals contract](external-proposals.md) with a real typed
classifier, safely. A model reads the text of the pages a study cites for a company and proposes,
for each rubric criterion, which written level the text best supports. The proposal enters the
application only through `mcda proposals import`, where a person reviews every one. The
application never calls a model and never uses the network; this script is the only place a
model runs, and it never imports `mcda_studio`.

## What the model may see

Only: the rubric text and labels (from `rubrics.json`), criterion and alternative IDs and names,
each cited source's name, URL and publication date, and the text of the saved page snapshots.
Never the study author's ratings, measurements, classes, ranks, claim values, descriptions, review
notes or uncertainty fields. The unit of text is **all** the pages cited for that company's rubric
criteria, not only the page the author used for one cell. The pages cited for the two numeric
market criteria are not included: they describe markets, not the company, and the second human
rater is shown the same set of pages (see the [rater kit](blind-rater-kit.md)).
`--redact names.txt` replaces listed names (any case, longest first) with neutral tokens.
Leakage is tested with canary strings planted in every field that must not reach a request.

## Subcommands

1. **`snapshot`** fetches each unique `http(s)` source reference once: client name
   `mcda-studio-research/0.1`, at most one request per second (robots.txt fetches included), a
   20-second timeout, and `robots.txt` honoured through `urllib.robotparser` (a missing file allows,
   401/403 or an unreachable file forbids). A 401 or 403 page is recorded as skipped, not saved.
   Saves the raw bytes and the text extracted with the standard library's `html.parser` (script,
   style, navigation, head and footer dropped; the title kept), with SHA-256 of both, the HTTP
   status, the final URL and the retrieval time. `snapshots.json` states the licence ("unknown —
   private research copy, not for redistribution") and that the study's as-of date is 4 November
   2026 and the copies are later. A page is never fetched again unless `--refresh` is given.
2. **`questions`** builds one Choice question per company and rubric criterion (112 for the
   venture study): the criterion, rubric, ordered labels, an always-available "cannot tell"
   option and the instruction to choose the best-supported option. Each carries a prompt-template
   version and a SHA-256 digest, and the file carries the digest of all of it. Text is cut to a
   per-backend character budget (local model 12,000, jev 24,000) shared equally across a company's
   pages; every cut is recorded.
3. **`run`** answers the questions with a backend and writes raw responses, a probability vector
   per question over the labels plus "cannot tell", and a run manifest (input digests, backend,
   model ID and version, template version, parameters, start and end times, environment).
   Backends:
   - **replay**: responses recorded by question digest, for tests and offline re-scoring;
   - **jev**: TypeSafe's System One endpoint as documented at docs.typesafe.ai
     (`POST https://api.typesafe.ai/v1/systemone`, bearer key, body `model`, `state`, `questions`
     with a `choice` question's `instructions` and `criteria`; answer `probabilities` per option;
     the pinned default model is `jev-1.13.0`). It needs `--allow-network` and `TYPESAFE_API_KEY`;
     without either it refuses before sending anything. The format was read from the public
     documentation on 7 November 2026 before the client was written; no real call was made
     tonight because no key was set;
   - **local-hf** (the free default): scores each option, "cannot tell" included, by the
     conditional log-likelihood, under a local instruction model, of its option letter as the first
     token of the reply, then takes a softmax. No sampling. Letters rather than label text are
     scored so that long labels are not penalised and one forward pass answers a question.
     `transformers` and `torch` are imported only when this backend runs, from the separate
     virtualenv `$MCDA_DATA/venv-classifier`, never the project's hash-locked environment. The only
     model it may download is `Qwen/Qwen2.5-1.5B-Instruct` (Apache 2.0, no account), and only with
     `MCDA_ALLOW_MODEL_DOWNLOAD=1` through the `fetch-model` subcommand, which records the
     revision hash;
   - **laya**: refused. No scoring interface for it was confirmed against documentation, and the
     runner never guesses one. Its model card would say "not fine-tuned: expect near-random
     zero-shot accuracy".
4. **`export`** writes the contract's files from a run and a threshold (default 0.5):
   `proposals.csv` (exact header of the published CSV), `registries.json`, `model-card.json`,
   `run-report.json` and, for the benchmark, `tool_outputs.<task>.json` per label vocabulary.

## Exact probabilities

A backend gives non-negative weights (probabilities, or a softmax). The runner turns them into
decimals with six places that sum to **exactly one**: each share is floored to the grid with exact
rational arithmetic, and the units left over go one each to the largest fractional remainders,
ties to the earlier option. The benchmark requires vector sums with zero tolerance, so this is
what it validates. An exact tie at the top has no winner and abstains.

## Proposals and abstentions

A cell is proposed only when its top option is a real label with probability at least the
threshold. "Cannot tell", a tie or a lower probability gives **no proposal**, is listed with its
reason in `run-report.json`, and is an abstention (a null label and null probabilities) in the
benchmark table. A proposal is a `categorical_cell` whose payload is the top label, with the tool
ID and version, a model-card ID and digest, the run time, the confidence object
`{value, scale: "unit_interval", meaning: "Tool-reported probability of the selected label;
uncalibrated; metadata only"}` and source IDs that resolve in `registries.json` (the pages the
model actually read). Confidence is metadata: nothing in the application reads it as a weight,
score or probability.

The benchmark vector of a proposed cell is the label probabilities renormalised without the
"cannot tell" mass (the benchmark's vectors name task labels only), then quantised the same way.
Labels are the positional `level_1` (worst) to `level_n` (best) of the
[frozen protocol](blind-rater-kit.md); the proposal keeps the rubric's own wording.

The model card's digest is the SHA-256 of the card written as canonical JSON, so the one file
serves the proposal contract and the benchmark's tool card. Every field the proposal and proxy
designs ask for is present; facts nobody supplied say "unknown" with the reason.

## Boundaries (binding)

- The app is unchanged; the contract is the published files. The integration test imports the
  runner's proposals for the venture study with the existing `mcda proposals import` and
  `preview` commands.
- Real data (pages, answers, model outputs) stays under `$MCDA_DATA`; every output path is
  resolved through symlinks and refused inside the repository.
- No account, sign-up or paid service. The generic client name is the only identity sent.
- Tonight's run compares nothing with the author's ratings: the second rater comes first.

## Verification

A synthetic study and a local HTTP server (no real page, model or remote service; a guard fails
any test that tries); snapshot politeness, robots, 401/403, hashes and no refetch; question
leakage canaries, truncation and redaction; exact probability sums; a local mock of the jev
endpoint (request shape, bearer header, errors, refusals); export shape, abstentions and
threshold equality; the exported tables through the rater kit into the benchmark's own validator;
the contract through the real CLI; and mutants.

## Amendment: option-order averaging and cleaner page text

**Accepted by the owner through the follow-up prompt, 7 November 2026** (owner decisions 7 and 6 of
the roadmap (not included)).
The application is unchanged; question files and their digests are unchanged by the averaging.

**Option-order averaging for `local-hf`, on by default.** A model that prefers a letter position
would otherwise pass that preference off as an answer. A question with n options ("cannot tell"
included) is scored under all n cyclic rotations of its option list. Letters stay A, B, C... in
display order; only which option sits under which letter changes. Each rotation's letter
probabilities (a softmax over the letters' first-token log-probabilities) are mapped back to
options, and the arithmetic mean of the n per-option probabilities is quantised to exact decimals
that sum to exactly one, as before. The raw record keeps every rotation's letter log-probabilities
and option-at-letter, and two diagnostics: `order_top_agreement` and `order_max_shift`.
`--order-averaging none` keeps the single-order scoring, byte-identical to before, for comparison
only. The run manifest records `scoring_version` (`first-token-letter-logprob.v2` averaged, `.v1`
single order; the other backends keep `backend-probabilities.v1`) and the model card states "first-token
letter log-likelihood, averaged over n cyclic option orders". A fake model that puts 60% of its mass
on letter A is corrected exactly by the average in the tests (each option's average is the same
affine function of its true probability). Averaging removes position bias from the average and
nothing else: the probabilities are not calibrated, and agreement between rotations is not accuracy.

**Extractor version 2 (`reextract`).** The first extractor keeps menus and repeated notices. The
version-2 filter, run from the saved raw bytes without any request, keeps the first occurrence of
each exact repeated line within a page, drops lines of three words or fewer that also appear in at
least one other saved page from the same host (compared on the other page's version-1 lines, so the
order of processing does not matter), and keeps everything else. It writes `snapshots.v2.json`
(with the source index's SHA-256, the rules, and per page the characters before and after, the
extractor version and whether version 1 rebuilds identically) and `text.v2/`; version 1 stays
untouched. `questions --extractor 2` reads it; the questions record which index they used only when
it is the second, so version-1 question files are byte-identical to before.

## Amendment: the Laya backend, a model allowlist and option-order averaging for jev

**Accepted by the owner through the
classifier comparison prompt (development record, not included)
(12 November 2026, amended 16 November 2026) and, in an attended session on 16 November 2026, in
chat.** The application is unchanged. Question files, extractor output and the `local-hf`,
`replay` and single-order (`--order-averaging none`) `jev` outputs are unchanged.

**Interface, read from the installed package (`laya` 0.4.32, PyPI, Apache 2.0) on 16 November
2026,** not from documentation alone:

- `laya.load(path)` treats any argument containing a path separator as a local checkpoint
  directory and passes it to `laya.Agent` unchanged. A checkpoint directory holds
  `rl_agent_config.json`, `model.safetensors`, `tokenizer/` and `encoder/`. The runner loads only
  from `$MCDA_DATA/models/<name>`, with `HF_HUB_OFFLINE=1`.
- `agent.predict(state, questions)` (an alias of `system_one`) takes
  `{qid: {"type": "choice", "instructions": str, "criteria": {key: text, ...}}}`. The per-option
  probability vector is `result["answers"][qid]["probabilities"]`, a mapping from option key to a
  probability **rounded by the package to four decimals**. The runner renormalises it with the
  existing exact quantisation; the rounding is recorded in the model card.
- The window is the checkpoint's `max_len` in `rl_agent_config.json` (expected 512 for
  `convaiinnovations/laya`, 1,024 for `convaiinnovations/laya-typed-decisions`). The question and its
  options (the "head") are capped at the checkpoint's `head_max_len` (default 192 tokens); the
  package cuts a longer head without failing. The state gets what is left,
  `laya.common.state_room(tokenizer, question, max_len, head_max_len)`, and anything past it is
  cut.
- The fine-tuned weights exist both in their own repository and as the `typed-decisions`
  subfolder of `convaiinnovations/laya`. The runner uses the **own repository**, downloaded into its
  own directory, and records that route.
- The package also offers `option_order` (it permutes and un-permutes options itself) and
  `predict_long` (overlapping token windows; for a choice question, the answer of the single most
  confident window). The runner uses neither: it rotates options itself, so the three scoring
  backends share one averaging code path, and it chunks as below, so the rule is the one the owner
  accepted. `laya.Agent(vegaml=True)`, `laya.load(vegaml=...)` and `laya.Router()` are never called.

**`LayaBackend`**, replacing the refusal:

1. **Import.** `laya` is imported only when this backend runs, from `$MCDA_DATA/venv-classifier`.
   If it is missing, the backend refuses with the install instruction, as `local-hf` does. The
   manifest records the `laya`, `torch` and `transformers` versions, the device and dtype, the
   checkpoint directory and its revision from `mcda-model-revision.json`.
2. **Window.** `max_len` and `head_max_len` are read from the loaded checkpoint, never hard-coded,
   and recorded per run.
3. **Head.** Each question is rendered as a `choice` question: the instructions are the criterion,
   rubric and instruction text, as in the jev request; the criteria are the question's options in
   its own order, keyed by option. Every question already carries "cannot tell"; none is added. The
   head is measured with the checkpoint's own tokenizer and `laya.common.build_head`. **A question
   whose head would be cut is refused**, never answered from a shortened rubric. The refusal is
   recorded in the raw responses and the run report.
4. **Chunking.** The state budget is `state_room(...)` minus a margin of 8 tokens. A question whose
   budget is under 64 tokens is refused. The state text is split on blank-line paragraph
   boundaries and packed greedily: a paragraph joins the current chunk if the joined text, counted
   with the checkpoint's tokenizer, still fits; a chunk exactly at the budget fits. A paragraph that
   alone exceeds the budget is split on sentence boundaries, and a sentence that alone exceeds it is
   split by token count. Each chunk records its SHA-256, its token count and the rule that made it
   (`paragraph`, `sentence` or `tokens`), and each question records its chunk count.
5. **Scoring.** Every chunk is scored under every cyclic rotation of the options (`--order-averaging
   rotations`, the default) or in the question's own order only (`none`, for comparison only).
   Probabilities come back keyed by option, so each rotation maps back to the canonical order by
   key.
6. **Aggregation.** For each rotation, the per-option probabilities are averaged over chunks
   (arithmetic mean); the rotation vectors are then averaged with the existing
   `average_over_orders`. Because every chunk is scored under every rotation, this equals the grand
   mean over chunks and rotations. The result is quantised to exact decimals that sum to one.
   **Known weakness:** the mean dilutes a single decisive chunk toward "cannot tell" when most
   chunks are neutral. The package's own long-text rule (the most confident window decides) makes
   the opposite trade-off: one confidently neutral or confidently wrong chunk decides.
7. **Diagnostics.** As for `local-hf`: `order_top_agreement` and `order_max_shift`. New:
   `chunk_top_agreement`, the share of chunks whose top option (after rotation averaging) equals
   the aggregate top; and, recorded only and never used for proposals, `max_confidence_chunk_top`,
   the top option of the chunk with the highest top probability, so the summary can report how
   often the package's rule would have answered differently.
8. **Model card.** Base: "Laya base: not fine-tuned for this task; the vendor reports near-random
   zero-shot accuracy". Typed-decisions: "fine-tuned on unrelated workflows (customer service,
   invoices, security, agent traces), not on startup screening". Both state the chunking rule, the
   window, the four-decimal rounding and the averaging. The scoring version is
   `laya-choice-chunk-mean.v1`.

**Question files.** `run` refuses a question file built for another backend, so Laya runs use a file
built with `questions --backend laya`. The comparison run uses `--budget-chars 12000` instead of
Laya's 4,000 default, so that the state text matches the `local-hf` file; the state digests are
checked before any comparison.

**`fetch-model`** accepts an explicit allowlist: `Qwen/Qwen2.5-1.5B-Instruct`,
`convaiinnovations/laya` and `convaiinnovations/laya-typed-decisions`. Any other repository is
refused. Each still needs `MCDA_ALLOW_MODEL_DOWNLOAD=1` and writes `mcda-model-revision.json` with
the exact commit hash. For `convaiinnovations/laya`, only the root checkpoint files are fetched
(`rl_agent_config.json`, `model.safetensors`, `tokenizer/*`, `encoder/*`), never the bundled
subfolders.

**Option-order averaging for `jev`.** The same cyclic rotations, mapping back by option key, the
same diagnostics and the same `--order-averaging none` comparison mode. A run sends about n times
the single-order token count (n options per question); the runner prints the estimate before any
request, and the session's token cap applies.

**Environment.** Real runs from 16 November 2026 may run on a Windows desktop with an NVIDIA GPU
(CUDA) rather than the Mac (MPS). The manifest records the device; runs on different devices or
library versions are compared only as tool-side facts.

**Verification.** A fake `laya` module (no download, no network): chunking one token under, exactly
at and one over the budget; an over-long paragraph and an over-long sentence; the window read from
the checkpoint (512 and 1,024) and refusal when the head alone would be cut or the budget falls
under 64; the chunk mean; rotation mapping; exact sums; "cannot tell" not duplicated; the model
card fields per checkpoint; refusal when the package is missing; the allowlist, allowed and
refused; and jev rotations against the existing localhost mock. Mutants in the `runner` group:
chunk off-by-one, the mean replaced by the first chunk, "cannot tell" dropped, jev rotation not
mapped back, Laya rotation not mapped back, the window hard-coded to 512, and the allowlist
bypassed.

## Amendment: a second Laya reading, the most confident chunk (16 November 2026)

**Status:** accepted by the owner in chat on 16 November 2026, answering decision 1 of the
classifier comparison report (development record, not included): "keep
the mean, also record a reading where the most confident chunk decides".

**Why.** For the base checkpoint, single chunks are often confident (69 of 112 questions have a chunk
at or above 0.5), and the mean over about nine chunks dilutes them, so the accepted rule made 2
proposals at 0.5. The package's own long-text rule, the most confident window decides, makes the
opposite trade-off. Recording both lets the human-agreement gate, later, say which tracks a person.
Neither reading is claimed to be better; a confident chunk is not a correct one.

**Behaviour.**

1. **The mean stays the reading.** `probabilities.json` rows, `scores`, `compare-runs`, the scoring
   version and the default `export` are unchanged.
2. **The second reading** for each Laya question is the order-averaged probability vector of the
   chunk whose largest probability is highest (ties go to the earlier chunk), the same chunk whose
   top option `max_confidence_chunk_top` already names. The raw record gains `max_confidence_chunk`
   (the chunk's index and its full vector), and each `probabilities.json` row gains `readings` with
   `max_confidence_chunk`: six-place exact probabilities that sum to one, its top option and whether
   that top is tied, quantised exactly as the mean is. The manifest's parameters name the rule
   (`second_reading`). Other backends record no second reading.
3. **`export --reading max-confidence-chunk`** turns that reading into proposals, with the same
   threshold, abstentions and contract as the mean. It refuses a run that recorded no second
   reading (another backend, or a Laya run made before this amendment); it never derives one.
   Its proposals say which reading they come from: the tool version gains `+max-confidence-chunk`,
   and the model card and run report state the reading. `--reading mean` (the default) writes
   exactly what `export` wrote before.
4. Nothing changes in the application: both readings arrive only as External Proposals that a
   person reviews, and confidence stays metadata, never a weight.

**Verification.** With the fake `laya` module: the second reading equals the hand-computed chunk on a
three-chunk case under rotations, ties go to the earlier chunk, the recorded vector sums to one, the
mean is unchanged, `export --reading max-confidence-chunk` proposes from the recorded reading and
names it, the default export names no reading, and a run without the reading (a `replay`
run) is refused. Mutants in the `runner` group: the least confident chunk chosen, a tie going to the
later chunk, the export reading the mean when asked for the second reading, and the reading left
unnamed in the tool version.

## Amendment: `local-hf` on an NVIDIA GPU (16 November 2026)

**Status:** accepted by the owner in chat on 16 November 2026 ("Qwen runs on this GPU"), on the
Windows desktop where the Laya runs already use CUDA.

`local-hf` chose Apple's GPU (MPS) or the CPU. It now chooses an NVIDIA GPU (CUDA) first, then MPS,
then the CPU; both GPUs run in float16, the CPU in float32, as before. The prompt, scoring, rotations
and every output format are unchanged, and a Mac picks MPS exactly as before. The manifest already
records the device and number type, and a run on a different device or library version is compared
only as a tool-side fact.

**Verification.** A fake `torch` covers the four cases (CUDA alone, CUDA with MPS, MPS alone,
neither). Mutants in the `runner` group: CUDA ignored, and CUDA run in float32.
