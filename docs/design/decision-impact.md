# Decision impact for qualitative and ordinal cells

**Accepted by the owner through the overnight prompt, 7 November 2026** (ROADMAP row 12i,
the roadmap (not included), item 6).
It is opt-in and read-only: it adds no stored format, changes no mathematics and leaves the
existing `mcda open-questions` command, the Open Questions route, its exports and every pinned
output unchanged.

## Purpose

Open Questions already says where a *measurement range* could change a rank or class. A venture
study is mostly rubric labels, not ranges, so the useful question there is: if this one rating were
wrong, would the decision change? Decision impact answers that for every scored labelled cell, so
the next diligence question is the one that matters.

## The analysis

For each alternative and each leaf with positive weight whose value function is qualitative (an
ordinal or categorical scale with fixed anchors) and whose measurement is entered, **every other
label of that scale is tried, one cell at a time, with everything else fixed**:

- It uses the engine's own functions, not a copy: the value evaluator `prepare_mavt` built (so a
  selected scenario's override applies), `overall_values` (the same `math.fsum`), `rank_values`
  (competition ranks with the 1e-12 tie tolerance) and `class_index` for classes. Only the changed
  alternative's overall value is recomputed, because no other row can move.
- Per cell it reports: the labels that change **the target's rank**; the labels that change **any
  alternative's rank**; the labels that change **the target's class**; the labels that change **the
  leader** (the set of rank-1 alternatives, so a tie at the top counts); the **smallest change**,
  meaning the nearest labels by steps along the scale's listed order, on both sides, that do any of
  these; and a **can change the decision** flag, true when some label changes the leader or the
  target's class.
- The target is the cell's own alternative. On a categorical (unordered) scale "steps" only follow
  the listed order, and each cell says whether its scale is ordered.
- Cells are ordered: leader or class change first, then rank change only, then none; inside a tier
  by criterion order and then alternative order.
- Each cell carries reasons from existing sources: **judgement only** (every accepted claim's source
  description starts "Judgement"), **disputed** (conflicting or unreviewed claims on the cell),
  **outdated**, **missing** (no accepted claim), and from an optional proposals workspace
  **pending**, **rejected** and **tool and human disagree**. A cell with no reason is still analysed
  and shown as having no open reason. A dossier that is not valid for this project revision gives no
  reasons.

At most 20,000 label trials are run for one request.

## Surfaces (opt-in)

- `mcda decision-impact PROJECT [--evidence FILE] [--proposals FILE] [--profile ID] [--scenario ID]`,
  printing JSON.
- `POST /api/decision-impact` with the project draft, configuration, optional dossier and optional
  proposals workspace.
- A **Sort by decision impact** toggle in the Open Questions view. Off by default; when on it reads
  the new route and shows the cells in that order, with their labels and reasons in plain words,
  above the unchanged question groups.

## Limits

One cell at a time, not combinations: two ratings moving together can do what neither does alone.
It says which uncertain ratings could change the screening result; it does not say they are wrong,
how likely a change is, or what any company will do. Numeric cells are covered by the existing
measurement-range questions.

## Verification

An independent plain-Python brute-force oracle rewrites each cell in the raw project JSON and
recomputes every value, rank, leader and class from scratch; the service agrees to 1e-12 on values
and exactly on everything else on the venture study (both profiles and the scenario), the bundled
examples the oracle covers, and generated trees full of ties, with a check that the corpus really
contains ties, leader, rank and class changes. Mutants skip a label, shift a level, flip the tie
tolerance, swap the class boundary's inclusion and mis-detect the leader.
