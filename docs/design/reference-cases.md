# Reference cases

**Accepted by the owner through the reference cases prompt, 12 November 2026**
(`docs/development/reference-cases-2026-11-12-prompt.md`). The prompt approves exactly one new
stored format, the `reference-cases` sidecar version 1, as specified below. It is opt-in and
read-only: it changes no existing schema, mathematics, fixture or pinned output, and no score,
rank, class or stored project byte.

**Owner amendment, 14 November 2026 (chat):** add an opt-in **leave-one-out** option,
`exclude_same_id` (default false). When true, a case whose id equals the alternative's id is left
out of that alternative's comparison before anything is computed, so it is neither ranked nor
listed as not comparable, and its id is reported in that alternative's `excluded_case_ids`. The
result echoes `exclude_same_id`. Similarities, order and grouping of every other case are
unchanged; with the option off, every result has the same values, order and groups as before
(the response gains the echoed `exclude_same_id: false` and an empty `excluded_case_ids` per
alternative). It exists for sets whose cases are the project's own alternatives, such as the
first-round retrospective, where a company otherwise matches itself exactly.

## Purpose

For an alternative in the open project, show the most similar **reference cases**: past
alternatives rated on the same labelled criteria as of a dated **snapshot**. The analysis gives the
criteria that matched, the ones that differed and, only on request, each case's recorded
**outcome**. It predicts nothing. Similarity is a description of how alike two sets of ratings
are, not a forecast.

## Wording

Engine code and engine-generated text use only *reference case*, *snapshot*, *outcome*,
*context*, *similarity*, *criterion* and *label*. Domain words (stage names, funding words, success
or failure) appear only in example data and the example's README. A unit test checks the fixed
label and limitations for them.

## The `reference-cases` sidecar, version 1

A separate local JSON file. It reuses the evidence models where they fit and adds only what they
cannot express.

- **Envelope:** `kind: "reference-cases"`, `version: 1`, `id`, `title`, `description`,
  `criteria_from` (the id of the project whose criteria tree the labels use), `cases` and
  `sources`. The strict sidecar conventions of the External Proposals format apply: unknown fields
  are refused, versions must be explicit integers, and any version other than 1 is refused with a
  message naming the supported version. `sources` is a map from a source key to a source, as in
  the proposals intake.
- **Source:** the evidence `Source` (`name`, `reference`, `location`, `date`, `description`,
  `classification`) except that `date` may be absent. The date is the day the source was published
  or, for an archived capture, captured. Dates are explicit `YYYY-MM-DD` strings; numbers and other
  formats are refused.
- **Case:** `id`, `name`, `snapshot_date` (required), `context` (an ordered list of
  `{label, value}` strings shown exactly as written), `claims`, `ratings` and `outcome` (required;
  "outcome not found" is itself a label an author can record).
- **Claim:** `id`, `text` (the author's own words), `source` (a source key) and `origin`, the
  evidence `Origin` (`kind` human or tool, `proposed_by`, optional tool identity). The cell-specific
  fields of the evidence `Claim` (alternative, criterion, value, unit, review) do not apply to a
  statement about a past case, so the claim is its own small model; `Source` and `Origin` are
  reused unchanged in meaning. Claims live inside their case, and a rating or outcome may cite only
  its own case's claims.
- **Rating:** `criterion_id`, `label` (exactly one of that leaf's scale labels), `claim_ids` (one
  or more) and an optional `note`. A leaf with no rating is **missing, not zero**.
- **Outcome:** `label` (free text from the data), `as_of`, `note` and `claim_ids` (may be empty).

### Validation (refused with a precise path)

| Code | Path | Rule |
| --- | --- | --- |
| `REFERENCE_PROJECT_MISMATCH` | `criteria_from` | must equal the project's id |
| `REFERENCE_DUPLICATE_CASE` | `cases[i].id` | case ids are unique |
| `REFERENCE_DUPLICATE_CLAIM` | `cases[i].claims[j].id` | claim ids are unique in a case; the first stands |
| `REFERENCE_UNKNOWN_SOURCE` | `cases[i].claims[j].source` | the source key exists |
| `REFERENCE_UNKNOWN_CRITERION` | `cases[i].ratings[j].criterion_id` | a leaf criterion of the project |
| `REFERENCE_NUMERIC_CRITERION` | same | version 1 rates labelled criteria only, and says so |
| `REFERENCE_UNKNOWN_LABEL` | `cases[i].ratings[j].label` | one of that leaf's labels, exactly |
| `REFERENCE_DUPLICATE_RATING` | `cases[i].ratings[j].criterion_id` | one rating per leaf per case |
| `REFERENCE_UNKNOWN_CLAIM` | `...claim_ids[k]` | the cited claim exists in this case |
| `REFERENCE_OUTCOME_BEFORE_SNAPSHOT` | `cases[i].outcome.as_of` | on or after the snapshot date |
| `REFERENCE_UNDATED_SOURCE` | `cases[i].ratings[j].claim_ids[k]` | the snapshot guard, below |
| `REFERENCE_SOURCE_AFTER_SNAPSHOT` | same | the snapshot guard, below |

**The snapshot guard (the hindsight rule).** Every claim cited by a *rating* must rest on a source
dated **on or before** that case's snapshot date. An undated source cannot support a rating; a
dated archived capture can. Outcome claims may be dated after the snapshot, and may be undated.
The guard is enforced in the service, so no analysis runs on a set that breaks it. It checks dates,
not whether a claim was knowable at the time.

## The computation (Python only)

Inputs: the project, the analysis configuration (for the active weight profile), the reference
set, an optional `alternative_id` (default every alternative), `k` (default 3, 1 to 20),
`weighting` (`"equal"`, the default, or `"profile"`), `min_shared_fraction` (default `"1/2"`, a
fraction or decimal string greater than 0 and at most 1), `include_outcomes` (default false) and
`exclude_same_id` (default false; amendment of 14 November 2026).

- **Compared criteria L:** leaves with an ordinal or categorical scale whose global weight in the
  active profile is positive, from the engine's own `compute_weights` (never re-implemented).
  Zero-weight leaves and numeric leaves are not compared and are not listed.
- **Per-leaf gap**, with `fractions.Fraction` throughout: ordinal `|i − j| / (n − 1)` over the label
  positions and the scale length (a one-label scale has gap 0); categorical 0 if equal, else 1.
- **Shared leaves S:** leaves in L rated on both sides. If S is empty, or `|S| / |L|` is below the
  threshold, the case is **not comparable**: it is listed with both counts and its fraction, and
  never ranked. Exactly at the threshold is comparable.
- **Distance:** `"equal"` is the arithmetic mean of the gaps over S; `"profile"` weights each gap
  by the leaf's global weight (the float converted exactly to a fraction), renormalised over S.
  Similarity is `1 − distance`.
- **Order:** similarity descending, then `|S|` descending, then case id ascending, comparing exact
  fractions. The top `k` are returned with the count of the remaining comparable cases.
- **Each returned case** gives its context, similarity, shared and compared counts and the leaves
  of L in four groups: **same** label; **one step** apart (an ordinal gap of exactly one
  position); **further** apart (more than one step, or a categorical mismatch); and **not
  compared**, each saying whether the alternative, the reference case or both lack a rating. Every
  row gives both labels, the steps apart on an ordered scale (none on a categorical scale or where
  a side is missing), the exact gap and the case's rating note.
- **Numbers** leave the engine as in decision impact: a float (`similarity`), plus the exact value
  as a `"p/q"` string (`similarity_exact`, `gap`, `shared_fraction`, `min_shared_fraction`).
- **Outcomes** are in the result only when `include_outcomes` is true.
- **The fixed label**, in every result: similarity is measured only on the rated criteria as each
  case stood at its snapshot; it says nothing about how the alternative will turn out; outcomes are
  context chosen by the reference set's author; a small set is not representative and public
  sources under-report cases that closed.
- **Limitations**, in every result: numeric criteria are not compared in version 1; every compared
  criterion counts equally unless profile weighting is chosen; the snapshot guard checks dates, not
  knowability; the set's author knew the outcomes when rating.

Refusals: an invalid reference set raises a validation failure with every issue (HTTP 422,
`VALIDATION_FAILED`, each issue's path in the details); an unknown alternative is
`UNKNOWN_REFERENCE`; `k`, `weighting` and the threshold out of range are refused. A configuration
whose weight profile cannot be resolved or weighted gives `status: "unavailable"` with the reason,
as decision impact does. An alternative's own label that is not on its scale is a model error. The
project's measurements need not be complete: missing cells are simply not shared.

## Surfaces

- **CLI:** `mcda reference-cases PROJECT --reference-cases FILE [--alternative ID] [--k N]
  [--weighting equal|profile] [--min-shared-fraction F] [--include-outcomes] [--exclude-same-id]
  [--profile ID] [--scenario ID]`, printing JSON (the same command is also `mcda reference-cases run`), and
  `mcda reference-cases validate FILE --project PROJECT`, printing the validation JSON and exiting 1
  when the set is invalid.
- **API:** `POST /api/reference-cases` and `POST /api/reference-cases/validate`, tag `analysis`,
  stateless: the request carries the project and the sidecar.
- **Interface:** a Reference cases panel in the Analyst view (a later development in the same run).
  Since 14 November 2026 it also has **Leave out this alternative's own case**, off by default,
  which re-requests with `exclude_same_id` and states when the engine left a case out.

## Excluded from version 1

Numeric leaves; combining several reference sets; storing a reference set inside a project; any
use of outcomes in a score, weight, rank or class; any learning from outcomes; editing a reference
set in the application.

## Verification

- Unit tests for every validation error and its path, the snapshot guard (one day after refused,
  the same day accepted, undated refused for a rating and accepted for an outcome), ordinal gaps at
  both ends of four- and five-label scales, a categorical mismatch, missing on either side, the
  threshold exactly at one half and just under, a hand-computed example under both weightings, the
  tie-break order including an exact tie that floats reverse, `k` bounds, outcomes absent by
  default, zero-weight leaves, and unchanged project bytes, fingerprint and ETag.
- An independent oracle (`tests/regression/reference_cases_oracle.py`) that never imports the
  application derives the weights from the raw swing ratings and recomputes every similarity,
  order, group and not-comparable case; the service agrees exactly on hand-built and generated
  sets.
- API and CLI tests like decision impact's.
- A new mutant group, `reference_cases`, in `scripts/mutation_check.py`.
