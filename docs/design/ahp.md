# AHP: priorities from pairwise judgements

**Status:** implemented and verified, 31 October 2026
([check record](../development/ahp-verification.md)). The owner chose the **full method** (open
decision 5): AHP compares criteria and alternatives in pairs and synthesises its own priorities.
The owner accepted all nine recommended [decisions](#decisions).

The analytic hierarchy process (AHP) asks for judgements of the form "A is v times as important (or
preferred) as B" on Saaty's 1–9 scale. It derives local priorities from each matrix of judgements
as its principal eigenvector, checks each matrix's consistency, and multiplies the priorities down
the criteria tree to give every alternative an overall priority. It is the next method in the
owner's order of 28 October 2026 and comes through the [method seam](method-seam.md), like
[value-based sorting](value-based-sorting.md), [SMAA-2](smaa-2.md) and
[PROMETHEE II](promethee-ii.md). The earlier proposal is plan §6 (historical record, not included),
and the roadmap section "AHP" sets the scope. Where they differ, this note wins.

The oracle came first: the published example below was sourced and reproduced before this note was
written.

## Published examples (the oracle)

Only openly licensed sources are used, so their numbers can enter the tests as data with a
citation.

| Source | Licence | What it supplies | Reproduced |
| --- | --- | --- | --- |
| V. Kampourakis, G. Kavallieratos, G. Spathoulas, V. Gkioulos and S. Katsikas, "LLM-Assisted AHP for Explainable Cyber Range Evaluation", [arXiv:2512.10487](https://arxiv.org/abs/2512.10487), 2025, Equation 7 and Table 2 | CC BY 4.0 | A 10 × 10 reciprocal matrix on Saaty's integer scale and its ten printed eigenvector weights | Nine of ten weights to the printed three decimals. The tenth, C1, is 0.31573: the paper's text gives "≈0.316", while its table prints 0.317, apparently rounded so that the column sums to 1.000. λmax = 10.91953 and CR = 0.0686 are not printed; they are cross-checked with LAPACK |
| S. D. Nguyen, "Evaluating and Ranking Criteria for Mathematics Graduate Education Admissions through the Analytic Hierarchy Process", [arXiv:2011.05376](https://arxiv.org/abs/2011.05376), 2020, Table 12 | CC BY 4.0 | The random-index table for n = 1 to 15, attributed to Saaty and Tran (2007): 0, 0, 0.52, 0.89, 1.11, 1.25, 1.35, 1.40, 1.45, 1.49, 1.52, 1.54, 1.56, 1.58, 1.59 | The table itself (decision 5). The paper's matrices are averages of survey responses printed to three decimals, and its printed priorities differ from the printed matrix by up to 0.4 percentage points, so they are not used as an oracle |

**Definitions** follow T. L. Saaty, *The Analytic Hierarchy Process*, McGraw-Hill, 1980 (the
eigenvector method, CI and CR) and T. L. Saaty and L. T. Tran, "On the invalidity of fuzzifying
numerical judgments in the Analytic Hierarchy Process", *Mathematical and Computer Modelling* 46,
2007 (the random indices). Koczkodaj's triad index is from W. W. Koczkodaj, "A new definition of
consistency of pairwise comparisons", *Mathematical and Computer Modelling* 18(7), 1993.

**Not found, and not used:**

- **No openly licensed published example with alternative matrices and a synthesis** was found.
  The well-known Wikipedia car example is CC BY-SA, with its judgements in images; the R `ahp`
  package that carries it as data is GPL. Neither licence suits this MIT-licensed repository, so
  both are left out (decision 8). Synthesis is verified by exact hand-derived cases instead.
- **A 7 × 7 matrix** in another CC BY paper (arXiv:2402.07404) is not exactly reciprocal as printed
  (entries differ from their reciprocals' inverses by up to 1.2 %), so an engine that derives
  reciprocals cannot reproduce its printed numbers.

**Use of the sources:** the matrix, the weights and the random indices enter the tests as data,
with the citations, under CC BY 4.0. No text, table layout or figure is copied.

## What exists today

- **The method seam.** The `consistency` capability is already in the vocabulary, reserved for AHP;
  the seam's table gives AHP `consistency` and nothing else in its full form. Methods own their
  validation, parameters, result type, version-2 record and CSV tables, and the frontend picks
  panels by method. PROMETHEE II added `validate_measurements` for methods that do not read the
  MAVT model.
- **One criteria tree** shared by every method, with sibling groups and leaves; alternatives in
  project order.
- **Measurements** are not AHP inputs: in the full method, alternatives are compared by judgement
  on each leaf.
- **Swing profiles and scenarios** belong to MAVT. AHP has neither.
- **Schema version 4** (`sorting` 2, `smaa` 3, `promethee` 4), each section written only when used.
- **The shared `ranking`** holds `{alternative_id, name, value, rank}`; for AHP, `value` is the
  overall priority (§3).

## Goals and non-goals

**Goals:**

- Pairwise judgements on Saaty's 1–9 scale for every sibling group of criteria and, per leaf, for
  the alternatives; each pair stored once and its reciprocal derived.
- Local priorities as the principal eigenvector, with a stated tolerance and an explicit failure.
- CI and CR for every matrix against a named random-index table; a CR above 0.10 is a warning, not
  an error; matrices of one and two items defined explicitly.
- The most inconsistent triad of every matrix, named in the editor and the results.
- Distributive synthesis by default and ideal synthesis as a parameter, named in every result.
- A pairwise editor with verbal labels and a live consistency preview computed in Python.
- **MAVT, sorting, SMAA-2 and PROMETHEE II byte-identical** for unchanged inputs.

**Non-goals (excluded):**

- The elicitation-view form (pairwise swings producing a MAVT weight profile). It can come later if
  the fresh-user checkpoint asks for it.
- Using AHP priorities as MAVT weights, or MAVT weights as AHP judgements.
- Ratings mode (scoring alternatives through value functions or measurements).
- Group aggregation of judgements, incomplete-matrix completion, ANP, and the geometric-mean
  method.
- Automatic repair of inconsistency, and treating consistency as proof of validity.
- Sensitivity, scenarios and uncertainty for AHP.

## Design

### 1. Inputs, in AHP's own section

```json
"ahp": {
  "criteria": [
    {"parent_id": null, "judgements": [
      {"row": "cost", "column": "performance", "value": 3},
      {"row": "cost", "column": "risk", "value": 5},
      {"row": "performance", "column": "risk", "value": 2}]},
    {"parent_id": "cost", "judgements": [
      {"row": "unit_price", "column": "logistics_cost", "value": 4}]}
  ],
  "alternatives": [
    {"criterion_id": "unit_price", "judgements": [
      {"row": "apex", "column": "cobalt", "value": 6}, "..."]}
  ]
}
```

- **Criteria:** one entry per sibling group with two or more children (the top level is
  `parent_id: null`), judging the children with respect to their parent.
- **Alternatives:** one entry per leaf, judging the alternatives with respect to that leaf.
- **A judgement** says that `row` is `value` times as important (or preferred) as `column`, with
  1 ≤ `value` ≤ 9; a pair judged equal has `value` 1 in either orientation. Each unordered pair
  appears once; the matrix entry for the other orientation is 1 / `value`, derived and never stored
  (decision 1). Values need not be integers (decision 2).

### 2. Priorities and consistency

For a matrix `M` of `n` items (`M[i][i] = 1`, `M[j][i] = 1 / M[i][j]`):

- **n = 1:** priority 1; λmax = 1; CI = CR = 0.
- **n = 2:** priorities `v / (1 + v)` and `1 / (1 + v)`; λmax = 2; CI = CR = 0 by definition (a 2 × 2
  reciprocal matrix is always consistent; no division by RI = 0).
- **n ≥ 3:** the principal eigenvector by power iteration (decision 4): start at `1/n` each, set
  `w ← Mw / Σ(Mw)` with every sum in `math.fsum`, and stop when the largest change is at most
  `10⁻¹⁴`. At most 10 000 iterations; failing that is an error, `AHP_NO_CONVERGENCE`, never a partial
  result. Then λmax = Σᵢ (Mw)ᵢ, CI = max(0, (λmax − n) / (n − 1)) and CR = CI / RI(n), with RI from
  the named table (decision 5). The number of iterations is reported.
- **Warning:** CR > 0.10 marks the matrix inconsistent (`AHP_INCONSISTENT`, a warning). It is shown,
  never repaired, and never blocks evaluation.
- **The most inconsistent triad** (n ≥ 3, decision 7): for every triple i < j < k, Koczkodaj's index
  `min(|1 − M[i][k] / (M[i][j] M[j][k])|, |1 − M[i][j] M[j][k] / M[i][k]|)`. The largest is reported
  with its three items, its three judgements and the value of `M[i][k]` that would make the triad
  consistent, `M[i][j] × M[j][k]` (which may lie outside 1/9–9). It is a hint; nothing is changed.

### 3. Synthesis and outputs

- **Criterion priorities:** local priorities per sibling group; a leaf's global priority is the
  product of the local priorities on its path, so the leaves' global priorities sum to 1.
- **Alternatives:** `pⱼ(a)`, the local priority of alternative `a` on leaf `j`.
- **Distributive mode** (the default, decision 6): `P(a) = Σⱼ gⱼ pⱼ(a)`, which sums to 1.
- **Ideal mode:** `rⱼ(a) = pⱼ(a) / maxᵦ pⱼ(b)`, `S(a) = Σⱼ gⱼ rⱼ(a)` (the ideal score, at most 1),
  and `P(a) = S(a) / Σᵦ S(b)`. Adding a copy of an alternative leaves every ideal score unchanged;
  in distributive mode it can reverse the order of two alternatives (a known property, stated, not
  hidden).
- **Ranking:** competition ranks on `P` with MAVT's `10⁻¹²` tie tolerance. The shared `ranking`
  holds it, and its `value` is `P(a)`.

`AhpResult` (`method: "ahp"`) contains:

- the synthesis mode, the random-index table's name and values, the tolerance and the iteration
  cap;
- every matrix: its kind (criteria or alternatives), group, items, judgements as used, priorities,
  λmax, CI, RI, CR, the inconsistent flag, the most inconsistent triad and the iterations;
- criterion priorities, local for every node and global for the leaves;
- per alternative: `P(a)`, its rank, its local priority on each leaf, its weighted part on each leaf
  (`gⱼ pⱼ(a)`, or `gⱼ rⱼ(a)` in ideal mode) and, in ideal mode, `S(a)`;
- **the label** "AHP priorities under these pairwise judgements: shares of the goal that sum to one,
  not MAVT values or swing weights", on every table, chart, export and record.

The result names no weight profile or scenario: both are `null`, because AHP reads neither.

### 4. Storage and schema

Under decision 1, an optional `ahp` section joins the project, with `SECTION_VERSIONS["ahp"] = 5`.
A project that holds AHP judgements is written as schema version 5; every other project keeps the
version it has today. Migration 4 → 5 is the identity and refuses a version-4 file holding `ahp`.

**Edits:** `set_ahp_model` and `clear_ahp_model` replace the whole section. Removing an alternative
removes the judgements that name it; removing a criterion removes its group or leaf entry and the
judgements that name it. A new alternative or criterion is never given judgements: validation asks
for them.

### 5. Validation

AHP runs the method-independent structural checks (alternatives, the tree), then its own rules.
Measurements, value functions, profiles and scenarios are not AHP inputs and are not checked.

| Code | Severity | When |
| --- | --- | --- |
| `AHP_NOT_STATED` | error | the method is AHP and the project has no section |
| `AHP_TOO_FEW_ALTERNATIVES` | error | fewer than two alternatives |
| `AHP_TOO_MANY_ITEMS` | error | a matrix of more than 15 items (the random-index table's limit) |
| `UNKNOWN_AHP_GROUP` | error | a criteria entry for a node that is not a parent of two or more children, or an alternatives entry for a node that is not a leaf |
| `DUPLICATE_AHP_GROUP` | error | two entries for one group or leaf |
| `UNKNOWN_AHP_ITEM` | error | a judgement names an item outside its matrix |
| `SELF_JUDGEMENT` | error | a judgement compares an item with itself |
| `DUPLICATE_JUDGEMENT` | error | a pair judged twice, in either orientation |
| `INVALID_JUDGEMENT` | error | a value below 1 or above 9 |
| `AHP_JUDGEMENT_MISSING` | error | a matrix lacks a judgement for a pair (listing the pairs), or a group or leaf has no entry |

AHP has one parameter, `synthesis` (`distributive` or `ideal`); unknown parameters are reported as
`UNKNOWN_PARAMETER` and ignored, as for every method. Inconsistency is not a validation issue: it
is computed with the priorities and reported by the result and the preview.

### 6. Method, records, API and CLI

- **Method** `ahp`, label "AHP (pairwise priorities)", capability `consistency`. Sensitivity,
  probes, scenario comparison and the MAVT previews refuse it with 422 `METHOD_NOT_SUPPORTED`.
- **Record:** `AhpAnalysisRecord`, version 2, calculation path `ahp.eigen_power.v1`. CSV tables:
  `priorities` (per alternative: overall priority, rank, ideal score), `criterion_priorities` (per
  node: local and global), `local_priorities` (per alternative and leaf) and `consistency` (per
  matrix: n, λmax, CI, RI, CR, flag, triad).
- **Preview:** `POST /api/ahp/preview` takes one matrix (`items`, `judgements`) and returns its
  priorities, λmax, CI, RI, CR, flag and triad. It is read-only, needs no project and validates the
  matrix with the same rules; the editor calls it while judgements are drafted.
- **API:** `/evaluate` returns `AhpResult` in the union; edit operations `set_ahp_model` and
  `clear_ahp_model`; `/api/meta` lists the method and its tables.
- **CLI:**
  - `mcda ahp judge FILE --group PARENT|--top|--leaf LEAF ROW COLUMN VALUE` (one judgement; a
    value below 1 is refused with a hint to swap the items), `mcda ahp remove FILE ...` and
    `mcda ahp clear FILE`;
  - `mcda ahp check FILE` prints every matrix's CR and triad;
  - `mcda evaluate --method ahp [--synthesis ideal]` prints the priorities under the label, then
    the consistency table.
- **Bounds:** at most 15 items per matrix, so at most 105 judgements per matrix. Work is trivial
  beside the results limits.

### 7. Frontend

- **A Pairwise tab,** shown when the viewed method is AHP or the project has the section:
  - one matrix per sibling group of criteria, then one per leaf for the alternatives;
  - each upper-triangle cell is a select of Saaty's verbal scale from "row 9× (extreme)" through
    "equal" to "column 9× (extreme)", or "not judged"; a stored non-integer value shows as
    "custom" and is kept unless changed;
  - beside each matrix, the live preview from Python: priorities as bars, λmax, CI, CR with the
    table's name, the warning above 0.10, and the most inconsistent triad's three cells highlighted
    with the consistent value of its third judgement;
  - Apply, Cancel and Remove as in the other method editors.
- **Results:** a **Priorities** panel (overall priorities with ranks, bars on a 0–1 share axis
  titled "AHP priority (shares sum to 1)", criterion priorities and local priorities per leaf) and
  a **Consistency** panel (every matrix's CR, flag and triad, with the inconsistent ones first),
  under the label.
- **The analysis header** says that AHP reads no weight profile or scenario while it is viewed.
- Python computes every number; the browser only draws them.

### 8. The cross-method rules

- AHP never reads swing profiles, value functions or measurements, and nothing in AHP feeds MAVT.
- AHP priorities are never called values or scores, and never share an axis or column with an MAVT
  value or a PROMETHEE flow.
- No field combines AHP with another method; the later comparison view reads each result
  separately.

## Verification plan

- **Published example:** the 10 × 10 matrix of Kampourakis et al.: nine weights to the printed three
  decimals and C1 to the text's 0.316; λmax and every weight against LAPACK to `10⁻¹⁰`.
- **Random-index table:** the engine's table equals Nguyen's printed Table 12, entry by entry.
- **Oracle:** `tests/regression/ahp_oracle.py`, plain Python checked in a clean interpreter to load
  no `mcda_studio` module. It builds reciprocal matrices from the stored judgements, gives exact
  priorities for consistent matrices (exact fractions), CI and CR from a given λmax, the triad
  indices, criterion global priorities and both syntheses in exact fractions, and competition
  ranks.
- **Independent eigensolver:** `numpy.linalg.eig` (LAPACK's QR algorithm, a different algorithm from
  power iteration) against the engine on the published matrix and on generated reciprocal matrices
  of 3 to 15 items, from nearly consistent to CR well above 1, to `10⁻¹⁰` for λmax and every
  priority.
- **Hand-derived cases:**
  - n = 1 and n = 2 (CI and CR 0, no division);
  - consistent 3 × 3 and 5 × 5 matrices (CI 0, priorities exact);
  - the closed form for a 3 × 3 matrix with entries a, b, c: λmax = 1 + t + 1/t with
    t = (ac/b)^⅓;
  - a hierarchy whose global priorities and both syntheses are exact fractions;
  - a copy case: adding a copy of an alternative reverses the order of two alternatives under
    distributive synthesis and leaves the ideal-mode order unchanged;
  - the triad on a matrix with one planted inconsistency.
- **Failure:** a forced iteration cap gives `AHP_NO_CONVERGENCE`, never a partial result.
- **Validation:** every code. **Schema:** version 5 only when used, no `null`, the migration refusal,
  clearing that restores the bytes, and pruning on removal.
- **Byte identity:** MAVT, sorting, SMAA-2 and PROMETHEE II outputs on every example against the
  previous commit; `scripts/byte_identity.py` gains PROMETHEE II with a deterministic stated
  section.
- **Frontend and browser:** the pairwise editor and its live preview, the triad highlight, both
  panels and the label; a GUI case from blank: enter the matrices, see and fix a consistency
  warning, evaluate, save, reopen and export.
- **Mutants** (`--ahp-only`):
  - a wrong reciprocal (the stored value mirrored instead of inverted);
  - an off-by-one random-index lookup;
  - unnormalised priorities;
  - distributive and ideal synthesis swapped;
  - the warning at CR ≥ 0.10 instead of above it;
  - the triad index taking only one of its two ratios;
  - global priorities not multiplied down the tree;
  - the iteration cap ignored, returning a partial vector;
  - an absent section written as `null`;
  - the section written as version 4;
  - frontend: the label dropped;
  - frontend: the triad's cells not highlighted;
  - frontend: the CR warning not shown.

## Acceptance

- The published matrix reproduces its printed weights (nine to the table, C1 to the text) and
  agrees with LAPACK; the random-index table equals the printed one.
- Every result names its random-index table and synthesis mode.
- Matrices of one and two items are defined explicitly; CR above 0.10 warns and never blocks.
- MAVT, sorting, SMAA-2 and PROMETHEE II outputs are byte-identical, and projects are written at
  the lowest sufficient schema version; migrated projects keep every ID, judgement, profile and
  scenario.
- A GUI case from blank: enter the matrices, see and fix a consistency warning, evaluate, save,
  reopen and export.
- The full gate is green, and every new mutant is killed.

## Decisions

1. **How a judgement is stored.** *Recommended:* an optional `ahp` section (schema version 5,
   written only when used), with each pair stored once as the matrix entry that is at least 1:
   `{"row", "column", "value"}`, `row` the favoured item and 1 ≤ `value` ≤ 9. No reciprocal is ever
   written as a decimal such as 0.14285714285714285, and reordering criteria or alternatives never
   changes what a stored judgement means. *Alternative:* the literal upper triangle in tree or
   project order, with values from 1/9 to 9; its reciprocals are stored as long decimals, and a
   reorder turns an upper entry into a lower one.
2. **Judgement values.** *Recommended:* any number from 1 to 9; the editor offers Saaty's verbal
   scale (1 to 9) and keeps an imported non-integer value as "custom". *Alternative:* integers 1–9
   only, which refuses matrices built from averaged judgements.
3. **Hierarchy.** *Recommended:* the project's one criteria tree, with criteria compared within each
   sibling group and alternatives compared on each leaf. *Alternative:* a separate AHP hierarchy,
   which doubles the model to maintain and breaks the shared reading of results across methods.
4. **Eigenvector computation.** *Recommended:* power iteration in plain Python with `math.fsum`, a
   tolerance of 10⁻¹⁴ on the largest change, at most 10 000 iterations and an error on failure; LAPACK
   checks it in the tests. On the published matrix it converges in 24 iterations and agrees with
   LAPACK to 7 × 10⁻¹⁶. *Alternative:* LAPACK in the engine, with power iteration as the oracle;
   that puts the less transparent algorithm in the product.
5. **Random-index table.** *Recommended:* Saaty and Tran (2007) for n = 1 to 15, as printed in the
   openly licensed Nguyen (2020), named `saaty-tran-2007` in every result; matrices are limited to
   15 items. *Alternative:* Saaty (1980) (0.58, 0.90, 1.12, 1.24, 1.32, 1.41, 1.45, 1.49 for n = 3 to
   10), still common in software, which gives CRs a few per cent different and stops at 10 items; or
   a parameter offering both.
6. **Synthesis.** *Recommended:* distributive by default and ideal through the `synthesis`
   parameter; in ideal mode the overall priorities are normalised to sum to 1 and the unnormalised
   ideal score is kept beside them. *Alternative:* report ideal mode unnormalised only, which puts
   the two modes on different scales.
7. **The inconsistency hint.** *Recommended:* Koczkodaj's triad index, naming the most inconsistent
   triad and the value that would make it consistent, without changing anything. *Alternative:*
   Saaty's largest deviation |M[i][j] − wᵢ/wⱼ|, which names one entry but not the judgements it
   conflicts with.
8. **Published examples.** *Recommended:* openly licensed (CC BY) sources only, with synthesis
   verified by exact hand-derived cases, since no openly licensed example with alternative matrices
   was found. *Alternative:* use the Wikipedia car example (CC BY-SA) as test data with
   attribution, which brings a share-alike licence into an MIT-licensed repository.
9. **Profiles and scenarios.** *Recommended:* AHP results name neither (`null`), and the header says
   AHP reads neither while it is viewed. *Alternative:* echo the selected profile and scenario as
   PROMETHEE II does, which suggests they affect AHP when they do not.
