# Method comparison view: every method's reading of one model, side by side

**Status:** implemented and verified, 31 October 2026, with all six recommended
[decisions](#decisions) accepted by the owner. See the
[check record](../development/method-comparison-verification.md).

One project can now be read by five methods: MAVT, value-based sorting, SMAA-2, PROMETHEE II and
AHP. This view shows their readings side by side, one column per method. It marks where they agree
on the leading alternative and on classes, and where they differ, with each method's own reason. It
never averages, aggregates or reconciles them: there is no consensus score. It is the last method
development in the owner's order of 28 October 2026, after the [method seam](method-seam.md) and
the four methods that came through it. The roadmap section "Method comparison view" sets the scope;
where they differ, this note wins.

## What exists today

- **Five registered methods**, each with its own result type in the `/evaluate` union, its own
  version-2 record (version 1 for MAVT), its own label and its own ranking quantity:

  | Method | Ranking quantity | Its own label | Classes |
  | --- | --- | --- | --- |
  | `mavt` | overall value, 0–1 | none (MAVT values) | — |
  | `mavt_sorting` | overall value, 0–1 | none | each alternative's class |
  | `smaa2` | rank-1 acceptability, a share of draws | "sampled acceptability under these assumptions" | class acceptability, when classes are stated |
  | `promethee2` | net outranking flow, −1 to 1 | "net outranking flows: … not preference values" | — |
  | `ahp` | AHP priority, a share of the goal | "AHP priorities under these pairwise judgements: …" | — |

  SMAA-2's shared `ranking` is MAVT's reference ranking, not its own reading: its own is the
  acceptabilities and `leader_id`.
- **Inputs differ by method.** MAVT, sorting and SMAA-2 read value functions and a swing profile
  (and a scenario); SMAA-2 also reads `smaa`, and sorting reads `sorting`. PROMETHEE II reads
  measurements and `promethee`, and uses MAVT only for its explanation. AHP reads only `ahp`.
- **A method that cannot read the model fails with a typed error:** 422 `VALIDATION_FAILED` with
  its issue codes (for example `PROMETHEE_NOT_STATED`), `ANALYSIS_LIMIT` (413), or
  `AHP_NO_CONVERGENCE`.
- **The seam's rule** (§8): "No route or type combines results from two methods. The later
  comparison view reads separate results side by side." Decision 1 settles what that means here.
- **The bundled examples** state few method sections: only the supplier-qualification example has
  classes. Today's examples therefore show mostly typed errors; the venture-screening study
  (development 8) will state every section.

## Goals and non-goals

**Goals:**

- One column per registered method, each naming its method, the inputs it read (sections, profile,
  scenario) and its parameters, or showing its typed error.
- Per alternative and column, the method's own rank and its own quantity under its own name and
  unit.
- Agreement marks on the leading alternative and on classes, and for each disagreement the
  method-specific reason, generated in Python from that method's own result.
- **Every earlier output byte-identical**: MAVT, sorting, SMAA-2, PROMETHEE II and AHP.

**Non-goals (excluded):**

- Consensus or averaged scores, rank aggregation (Borda, Copeland, Kemeny or any other), and
  "number of methods that agree" as a score.
- Reusing one method's weights or inputs in another.
- Any new number about the alternatives; every number shown is the method's own.
- Treating agreement on shared measurements as independent validation.
- Sensitivity of the comparison, and comparison across scenarios or profiles (the header selects
  one of each).

## Design

### 1. A read-only comparison route

`POST /api/methods/compare` (and `/api/projects/{id}/methods/compare`) takes the project, the
analysis configuration (profile and scenario) and, optionally, the methods to include (decision
2). It runs each method through its own `evaluate`, unchanged, and returns a `MethodComparison`
(decision 1):

- **one column per method**, in registry order, each either:
  - **ok:** the method's name and label, its calculation path, the configuration it ran with, the
    inputs it read, its label, and one cell per alternative (§2); or
  - **failed:** the method's name and label and its typed error (`code`, `message` and, for
    `VALIDATION_FAILED`, the issue codes), exactly as `/evaluate` would return it;
- **agreement** (§3) over the columns that ran;
- the project fingerprint and the configuration.

The route never fails because one method fails. It is 422 only when the request names a method that
is not registered (`UNKNOWN_REFERENCE`). Nothing is saved.

### 2. A column and its cells

Each column states what it read (decision 3):

| Method | Inputs named in its column | Parameters |
| --- | --- | --- |
| `mavt` | value functions, profile, scenario | its saved parameters when it is the saved method, else its defaults |
| `mavt_sorting` | value functions, profile, scenario, `sorting` | as above |
| `smaa2` | value functions, profile, scenario, `smaa` (and `sorting`) | as above; by default 10 000 draws at seed 0 |
| `promethee2` | measurements and `promethee`; profile and scenario for the explanation only | none |
| `ahp` | `ahp` only | `synthesis` as above |

A cell holds the method's own reading of one alternative, under its own name (decision 4):

- **rank:** the method's own competition rank (SMAA-2: the rank by rank-1 acceptability, with the
  project's order breaking ties as for `leader_id`);
- **quantity:** the method's own number with its name and unit: "overall value" (0–1), "rank-1
  acceptability" (a share of draws, with its interval), "net flow" (−1 to 1) or "AHP priority" (a
  share of the goal);
- **class:** sorting's class; SMAA-2's most frequent class with its frequency;
- **notes:** at most two short method-specific facts about that alternative (for example
  "incomparable with Beta under PROMETHEE I", or "on a class boundary").

No cell or column holds a number computed from two methods.

### 3. Agreement marks and reasons

Computed in Python over the columns that ran, and only from orders and classes (decision 5):

- **Leading alternative:** each column's leaders (its rank-1 alternatives; SMAA-2: `leader_id`).
  "All agree" when every column that ran has the same single leader; otherwise the columns are
  grouped by leader.
- **Classes:** when sorting ran, each alternative's class beside SMAA-2's most frequent class, when
  SMAA-2 ran with classes. "Agree" or "differ" per alternative.
- **Reasons, for each column whose leader differs from MAVT's,** taken from that method's own
  result, never invented:
  - **SMAA-2:** the leader's rank-1 acceptability and its interval, and "no alternative leads in
    half the draws" when the largest is below one half;
  - **PROMETHEE II:** the explanation's reasons for the pair formed by the two leaders (its
    criteria, zones and thresholds), or that the explanation is unavailable and why; and whether
    the two are incomparable under PROMETHEE I;
  - **AHP:** that AHP reads its own pairwise judgements, not the measurements, and any of its
    matrices whose CR is above 0.10;
  - **sorting:** none needed; it shares MAVT's values, so its leader can differ only through ties.
- **Context, always shown:** "Agreement between methods that share inputs is not independent
  validation." MAVT, sorting and SMAA-2 share value functions and weights; PROMETHEE II shares the
  measurements; AHP shares nothing but the alternatives and the tree.

No mark counts methods, scores agreement, or ranks alternatives by how many methods favour them.

### 4. Frontend

- **A Compare tab,** beside Results, for the selected profile and scenario:
  - one column per method, with its label, inputs, parameters and its own label underneath, or its
    typed error and the issue codes, linking to the editor tab that fixes them (as issues do
    elsewhere);
  - rows in project order, sortable by any one column's own rank (never by a combination);
  - the agreement marks and the reasons above the table, and the context sentence;
  - each column's quantity drawn on its own axis in its own units, never on a shared axis.
- **Downloads** (decision 6): the comparison as JSON and a long CSV (one row per alternative and
  method).
- Python computes every number and every reason; the browser only draws them.

### 5. Bounds and cost

The comparison runs every method once: the sum of their costs, dominated by SMAA-2 (about 0.3 s at
10 000 draws on the 50 × 40 performance fixture). The results limits apply to each method, and a
method over its limit shows `ANALYSIS_LIMIT` in its column. No new stored data; no schema change.

## Verification plan

- **The oracle is each method itself:** every ok column's ranks, quantities and classes equal that
  method's own `/evaluate` result for the same configuration, number for number; a failed column's
  error equals what `/evaluate` returns for that method.
- **Agreement:** a plain-Python check, without `mcda_studio`, recomputes leaders, class agreement and
  which columns need reasons from the separate `/evaluate` bodies.
- **Cases:**
  - the supplier-qualification example (MAVT and sorting run; three columns show typed errors);
  - generated projects with every section stated (as in `scripts/byte_identity.py`), with leaders
    that agree and that differ, a PROMETHEE II leader change explained, an SMAA-2 leader below one
    half, an inconsistent AHP matrix, and a sorting–SMAA-2 class disagreement;
  - a subset request, an unknown method (422), and a method over its limit.
- **No combination:** a schema check that no comparison field holds a number not found in some
  method's own result.
- **Byte identity:** every MAVT, sorting, SMAA-2, PROMETHEE II and AHP output, with
  `scripts/byte_identity.py` gaining AHP with a fixed stated section.
- **Frontend and browser:** the Compare tab's columns, labels, errors, marks and reasons; a GUI
  case on a project with every section stated, including a failing column fixed from its link.
- **Mutants** (`--comparison-only`):
  - a method silently dropped from the columns;
  - a column labelled with another method's name or label;
  - a failed column omitted instead of shown;
  - SMAA-2's leader taken from MAVT's reference ranking;
  - agreement declared when one column has a tied leader;
  - a reason taken from the wrong pair;
  - frontend: two columns drawn on a shared axis;
  - frontend: a column header without its method and inputs.

## Acceptance

- No averaged, consensus or aggregated score anywhere.
- Every column names its method, inputs and parameters; a method that cannot read the model shows
  its typed error.
- Every number in the view is one method's own, equal to its `/evaluate` result.
- Every earlier output is byte-identical.
- A GUI case passes; the full gate is green, and every new mutant is killed.

## Decisions

1. **Where the comparison is assembled.** *Recommended:* the read-only route of §1, which runs each
   method through its unchanged `evaluate` and lays the results side by side. Python then decides
   agreement and writes every reason, in one request with one fingerprint, and the seam's rule is
   read as "no route or type combines the numbers of two methods", which the route keeps.
   *Alternative:* the browser requests each method's record separately and assembles the view. That
   keeps the seam's sentence literally, but the browser would then decide agreement and pick
   reasons, and five requests can come from five different revisions.
2. **Which methods appear.** *Recommended:* every registered method, each with its reading or its
   typed error, with an optional subset in the request. A missing section is then visible as a
   failed column, not a silent absence. *Alternative:* only methods whose sections are stated,
   which hides why a method is missing.
3. **Configuration per column.** *Recommended:* the header's profile and scenario for the methods
   that read them; each method's saved parameters only when it is the saved method, otherwise its
   defaults (SMAA-2 at 10 000 draws, seed 0), as the method view already does. Every column states
   what it used. *Alternative:* a parameter editor per column, which turns the view into a second
   place to configure every method.
4. **What a cell shows.** *Recommended:* each method's own rank and its own quantity under its own
   name and unit, SMAA-2 ranked by rank-1 acceptability and not by its MAVT reference ranking.
   *Alternative:* ranks only, which is simpler but hides how close an order is in each method's
   own terms.
5. **What agreement means.** *Recommended:* the leading alternative and classes only, with
   method-specific reasons for each column whose leader differs from MAVT's, taken from that
   method's result. *Alternative:* full rank agreement (for example Kendall's τ between columns),
   which is a number that combines two methods and invites reading it as validation.
6. **Downloads.** *Recommended:* the comparison as JSON (with each column's configuration and, for
   ok columns, the method's own record digest so each can be reproduced) and a long CSV, one row per
   alternative and method, every row naming its method and quantity. *Alternative:* no download, so
   each method's own export stays the only record; or a wide CSV, which puts different quantities
   in one row and invites combining them.
