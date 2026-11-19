# Screening summary: one row per alternative at the top of Results

**Status:** accepted by the owner as proposed, 4 November 2026 (all five recommended decisions);
built 5 November 2026 (development record, not included). It is
ROADMAP development 12b, following the [venture screening study](vc-screening-study.md).

The summary answers, in one table, the questions an investor asks first: who leads, in which
class, does each company meet the mandate, what drives its value, how close it is to changing
place, and how much is still open about it. Every number is computed in Python by existing
engines; React only lays the table out. It is **read-only**: it never edits, saves or changes the
project, and adds no project, sidecar or result schema. It is domain-neutral: the column names say
"alternative", "requirements" and "class", and the venture study only supplies the data.

## What exists today

- `POST /evaluate` (MAVT and sorting) returns values, competition ranks, weighted contributions per
  leaf and, with sorting, each class and `distance_to_nearest_boundary`.
- `POST /feasibility` returns pass, fail or unknown per alternative.
- Exact one-way sensitivity (specification §5) gives every crossover `t*` for a node, and
  `class_changes` in the sorting engine gives every class change and the first change up and down.
- `POST /open-questions` returns questions, each with an optional `alternative_id`.
- The Results tab opens with the project ID, revision, the resolved profile line and the
  capability line, with the ranking chart below the fold at 1440 × 900 (cleanup item 2 moves those
  lines into Details).

## Design

### 1. Route and request

`POST /screening-summary` (draft project in the body) and `POST
/projects/{project_id}/screening-summary` (stored project), following the feasibility and
open-questions pattern. Request: `project` (draft route only), `configuration` (profile and
scenario, resolved by the existing precedence rule) and an optional `dossier`, passed through to
Open Questions exactly as the Open Questions tab passes it.

### 2. Response

`ScreeningSummary`:

| Field | Content |
| --- | --- |
| `project_fingerprint`, `configuration` | The exact project and the resolved profile and scenario |
| `status` | `available` or `unavailable` |
| `reason`, `issues` | When unavailable: one plain sentence and the validation issue codes |
| `label` | "Overall value is a preference value under this profile and scenario, not a probability or a prediction." |
| `rows` | One per alternative, in MAVT rank order, ties in project order |
| `columns` | Which optional columns are present and, for each absent one, why (for example "no classes are set up") |
| `fragility_definition` | The sentence in §4, so exports and screens carry the definition with the number |
| `limitations` | For example "one weight at a time; other weights move proportionally" |

Each row:

| Field | Source | When absent |
| --- | --- | --- |
| `alternative_id`, `rank`, `value` | MAVT result | never (the summary is unavailable instead) |
| `class_id`, `class_name`, `margin` | sorting result (`distance_to_nearest_boundary`) | no sorting section |
| `requirements` | feasibility overall status, with the failing requirement IDs | no requirements |
| `drivers` | the two largest weighted contributions `w_j · v_j(a)`: leaf ID, name, amount | — (fewer than two when fewer leaves have a positive contribution) |
| `fragility` | §4 | per-row reason, or a column reason when skipped for size |
| `open_questions` | count of Open Questions items with this `alternative_id` | Open Questions unavailable (reason given) |

Project-level open questions (no `alternative_id`) are counted once in a separate
`project_open_questions` field, never spread across rows.

### 3. Drivers

Leaf contributions from the MAVT result, sorted by amount descending, ties broken by the tree's
depth-first order. Zero contributions are never listed as drivers. Amounts are shown as value
points ("0.12 of 1") with the leaf's name; the column header says "largest weighted
contributions", not "strengths".

### 4. Fragility

**Definition.** For alternative *a* under the selected profile and scenario, consider every
criterion node *k* that one-way sensitivity accepts (it has a sibling and local weight below 1) and
whose baseline **global** weight is positive. Vary *k*'s local weight from its baseline λ_k with
the others in its group rescaled proportionally (specification §5). Let *t* be the first local
weight, moving away from λ_k in either direction, at which

- *a*'s competition rank changes (an exact crossover between *a* and some *b*, taken from the
  existing closed-form root), or
- *a*'s class changes (the sorting engine's `class_changes`, when classes exist).

The change is measured as the change in *k*'s **global** weight, `|t − λ_k| · W_parent(k)`, where
`W_parent(k)` is the product of the local weights above *k*; this makes changes at different
depths comparable as shares of the total weight. Fragility is the smallest such change over all
*k*. The row reports that amount, the node *k*, the direction (raise or lower), the local weight
`t` at which it happens, and what happens: "swaps with *b*" or "moves to class *C*". If no node
changes *a*'s rank or class anywhere in [0, 1], fragility is "no one-way change in [0, 1]".

**Ties.** An alternative currently tied with another (within 1e-12) reports fragility "tied now"
with the tied alternatives, because any change to a weight that separates them changes the rank.
A crossover exactly at the baseline is a tie and is reported the same way.

**Excluded nodes.** Nodes with zero baseline global weight are excluded: varying a branch rated 0
on purpose (the venture study's Mandate) would turn a screen into a score. Excluded nodes are
listed in the response.

**Computation.** Python only, reusing `endpoint_values` and the crossover rule from
`methods/mavt/sensitivity.py` and `class_changes` from `methods/sorting/sensitivity.py`; no grid
and no new root finding. One pass per eligible node costs O(n²) for crossovers and O(n·q) for
classes.

**Size limit.** Fragility is computed for at most 50 criterion nodes, the same bound Open Questions
uses for weight sensitivity; above it the column reads "not computed: more than 50 criterion
nodes" and every other column is still returned. The summary as a whole follows the existing
results limits (100 alternatives, 1,000 nodes).

### 5. Context and staleness

The response echoes the fingerprint and resolved configuration. The frontend drops any response
whose fingerprint, profile or scenario differs from the current context, exactly as Results does,
and issues the request with the same debounce and Retry. Switching profile or scenario re-requests;
it never edits the project.

### 6. Missing and invalid inputs

If MAVT cannot evaluate (for example a missing measurement), the whole summary is `unavailable`
with the reason "Ranking unavailable: N measurements are missing" and the issue codes. No row is
returned with zeros, and no column is computed from a partial model. A failing optional source
(sorting invalid, Open Questions failing) blanks only its column with its reason.

### 7. Where it appears

- **Top of Results**, above the ranking chart, for MAVT and value-based sorting. For SMAA-2,
  PROMETHEE II and AHP the Results view keeps its method panel and shows the summary collapsed
  under "MAVT screening summary", labelled as MAVT's reading so it is never mistaken for that
  method's.
- **Presentation view**, as a read-only table under the tree. This changes the presentation view's
  stated contract ("nothing here … evaluates the project"); see decision 3.
- **Exports:** none in this development. A CSV/JSON export would be a new export body and is left
  for a later decision.

### 8. Wording

- Column headers: Rank · Alternative · Overall value · Class (margin) · Requirements · Largest
  contributions · Closest change · Open questions.
- "Closest change" cell: "+0.031 weight on Traction → swaps with Hectre". The header's tooltip
  carries the definition sentence.
- Requirements: "Meets all", "Fails: Stage at most Series A", "Unknown: no measurement".
- Never "probability", "risk score", "confidence" or "robust".

## Verification plan

- **Independent oracle** (`tests/regression/screening_summary_oracle.py`, plain Python, no
  `mcda_studio` import): weights, values, ranks, contributions, classes and margins from the project
  JSON; fragility by brute force over every eligible node using its own affine endpoint evaluation
  and its own root formula; requirements from the feasibility oracle's rules. Compared field by
  field on the venture study, the supplier qualification example and generated models.
- **Property tests:** fragility is never larger than any single crossover the oracle finds; raising
  or lowering the reported node by the reported amount (plus or minus a small step) changes rank or
  class and stopping just short does not; drivers sum to at most the value; open-question counts sum
  with the project-level count to the Open Questions total; looking never changes project bytes,
  ETag or undo history.
- **Mutants:** contributions with the wrong sign; fragility taking the largest change instead of
  the smallest; ties ignored (a tied pair reported with positive fragility); the wrong profile
  (scenario profile ignored); zero-weight nodes included; local instead of global weight change;
  a missing measurement returning zeros instead of unavailable; frontend showing a stale response
  after a profile switch.
- **Vitest:** rendering of every column, absent-column reasons, unavailable state, stale drop.
- **Playwright** on the venture study: summary visible above the fold at 1440 × 900; Hnry's
  requirement failure beside its rank; switching to the Commercial/traction profile changes the
  rows; the fragility of the leader matches the Sensitivity tab's crossover for that node.
- **Byte identity:** all 969 original output bodies and twelve factor records unchanged; OpenAPI
  regenerated with only the two new routes and their models added.

## Decisions

1. **Fragility measure.** *Recommended:* the change in the varied node's global weight, so nodes at
   different depths compare fairly. *Alternative:* the change in local weight, which matches the
   Sensitivity tab's x-axis but overstates how fragile a deep leaf looks.
2. **Zero-weight nodes.** *Recommended:* excluded and listed. *Alternative:* included, which in the
   venture study would report "give the mandate a score" as the closest change.
3. **Presentation view.** *Recommended:* show the summary there, amending the view's contract to
   "nothing here edits or saves the project; it reads the same read-only summary as Results".
   *Alternative:* Results only, keeping the presentation view evaluation-free.
4. **Other methods.** *Recommended:* collapsed and labelled as MAVT's reading under SMAA-2,
   PROMETHEE II and AHP. *Alternative:* shown only for MAVT and sorting.
5. **Export.** *Recommended:* none now. *Alternative:* a JSON/CSV export, as a new export body.
