# Project file schema (versions 1 to 6)

Machine-readable JSON Schema: `project_schema.json` (generated from the Pydantic models with
`Project.model_json_schema()`). Files are UTF‑8 JSON, 2‑space indent, trailing newline, stable key
order, so they diff cleanly in Git.

## Versioning

* `schema_version` (integer) is mandatory. This program reads and writes versions **1** to **6**.
* **A file is written with the lowest version that can represent it.** Version 2 adds the optional
  `sorting` section, version 3 the optional `smaa` section, version 4 the optional `promethee`
  section, version 5 the optional `ahp` section and version 6 the optional `requirements` list. A
  project without them is written as version 1, byte for byte as before, so its fingerprint is
  unchanged and older installations still open it; classes make it version 2, stated uncertainty
  version 3, PROMETHEE inputs version 4, AHP judgements version 5 and feasibility requirements
  version 6. Absent method
  sections are omitted, never written as `null`, and an empty requirements list is never written. Clearing a section returns a project to the
  bytes it had before the section was added.
* A file with a **newer** version than the program supports is refused (`ProjectLoadError`).
* Older versions are upgraded by chained migrations `MIGRATIONS[n]: dict → dict` (n → n+1), then
  validated. Migrations 1 → 2 through 5 → 6 change nothing, but refuse a file that holds a section
  its version cannot (`sorting` before 2, `smaa` before 3, `promethee` before 4, `ahp` before 5,
  `requirements` before 6).
  The `schema_version` stored in memory is normalised to what the content needs, and results report
  that version. `PUT /api/projects/{id}` accepts any version from the one the content needs up to
  the newest.
* Unknown fields are rejected everywhere (`extra="forbid"`), as are NaN/±inf numbers.

## Top level

| Field | Type | Notes |
| --- | --- | --- |
| `schema_version` | int | |
| `id` | Id | stable project id |
| `title`, `description`, `decision_maker` | str | |
| `alternatives[]` | `{id, name, metadata{}}` | |
| `criteria[]` | `CriterionNode` | flat list; hierarchy via `parent_id` |
| `performances[]` | `{alternative_id, criterion_id, value}` | value: number or label; leaves only |
| `weight_profiles[]` | `{id, name, method="swing", judgements{node_id: rating}}` | |
| `scenarios[]` | `{id, name, weight_profile_id?, value_function_overrides{leaf_id: spec}}` | |
| `analysis` | `{method, weight_profile_id?, scenario_id?, parameters{}}` | `method` must be registered (`UNKNOWN_METHOD`); the method parses `parameters` |
| `sorting` | `SortingModel`, optional (version 2) | ordered classes for value-based sorting; read by `mavt_sorting`, and by `smaa2` for class acceptability |
| `smaa` | `SmaaModel`, optional (version 3) | stated uncertainty for SMAA-2; read only by `smaa2` |
| `promethee` | `PrometheeModel`, optional (version 4) | PROMETHEE II's own directions, weights, preference functions and codings; read only by `promethee2` |
| `ahp` | `AhpModel`, optional (version 5) | AHP's pairwise judgements for criteria and alternatives; read only by `ahp` |
| `requirements` | `[BoundRequirement \| LabelsRequirement]`, optional (version 6) | mandatory requirements on leaf measurements for the feasibility check; read by no method |

`Id` = `^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$`.

**Analysis parameters** belong to the configured method. MAVT reads one, `dominance_check`
(a JSON boolean, default `true`). A key the method does not use is ignored with an
`UNKNOWN_PARAMETER` warning; a wrongly typed known key (for example `"no"` or `0`) is an
`INVALID_PARAMETER` error.

**Sorting** belongs to the `mavt_sorting` method; MAVT never reads it. Types are checked when a
file is read; the rules are validation issues of the sorting method, so an incomplete draft can be
saved (see the [value-based sorting design note](../design/value-based-sorting.md)).

```json
"sorting": {
  "classes": [
    {"id": "qualified", "name": "Qualified", "description": "", "lower_boundary": 0.7},
    {"id": "conditional", "name": "Conditional", "description": "", "lower_boundary": 0.6},
    {"id": "not_qualified", "name": "Not qualified", "description": "", "lower_boundary": null}
  ],
  "audit": {"below_class_id": "conditional", "sample_size": 1, "seed": 2026}
}
```

`classes` are best first; each but the lowest has a `lower_boundary` in [0, 1], strictly
decreasing and more than 2 × 10⁻¹² apart; the lowest has none. `audit` is optional.

**Stated uncertainty** belongs to the `smaa2` method (see the
[SMAA-2 design note](../design/smaa-2.md)); a distribution replaces a measurement only in SMAA-2
runs and never fills a missing one.

```json
"smaa": {
  "dependence": "independent",
  "cells": [
    {"alternative_id": "apex", "criterion_id": "unit_price",
     "distribution": {"kind": "uniform", "lower": 38.0, "upper": 46.0}},
    {"alternative_id": "delta", "criterion_id": "certification",
     "distribution": {"kind": "categorical", "labels": ["iso9001", "iso9001_14001"],
                      "probabilities": [0.2, 0.8]}}
  ],
  "groups": [{"parent_id": null, "kind": "rating_intervals",
              "intervals": {"cost": [80, 120], "performance": [70, 110], "risk": [40, 60]}}],
  "shared_draws": [{"id": "carrier", "cells": [{"alternative_id": "brightline", "criterion_id": "on_time"},
                                                {"alternative_id": "evergreen", "criterion_id": "on_time"}]}]
}
```

Distribution kinds: `uniform` (`lower`, `upper`), `triangular` (`lower`, `mode`, `upper`), `discrete`
(`values`, `probabilities`) and `categorical` (`labels`, `probabilities`). Group kinds: `unknown`
(no intervals) and `rating_intervals` (one `[lower, upper]` per child); a group without an entry is
fixed. Only `"independent"` dependence is supported.

**PROMETHEE inputs** belong to the `promethee2` method (see the
[PROMETHEE II design note](../design/promethee-ii.md)). They are its own: nothing is read from
swing profiles or value functions, and nothing here changes an MAVT result.

```json
"promethee": {
  "criteria": [
    {"criterion_id": "unit_price", "direction": "minimise", "weight": 3,
     "function": {"kind": "linear", "q": 2, "p": 10}},
    {"criterion_id": "certification", "direction": "maximise", "weight": 1,
     "function": {"kind": "usual"}, "coding": {"none": 0, "iso9001": 1, "iso9001_14001": 2}}
  ]
}
```

One entry per leaf. `direction` is `maximise` or `minimise`; `weight` is any non-negative number,
normalised by the sum. Function kinds: `usual`, `u_shape` (`q`), `v_shape` (`p`) and `linear`
(`q`, `p`, with 0 ≤ q < p), with thresholds in the leaf's units. `coding` gives a number for every
label and is required on a categorical or ordinal leaf, refused on a numeric one, and omitted from
the file when absent; on a labelled leaf, differences and thresholds are in coded units.

**AHP judgements** belong to the `ahp` method (see the [AHP design note](../design/ahp.md)). They
are its own: nothing is read from measurements, swing profiles or value functions.

```json
"ahp": {
  "criteria": [
    {"parent_id": null, "judgements": [{"row": "cost", "column": "performance", "value": 3}]},
    {"parent_id": "cost", "judgements": [{"row": "unit_price", "column": "logistics_cost", "value": 4}]}
  ],
  "alternatives": [
    {"criterion_id": "unit_price", "judgements": [{"row": "apex", "column": "cobalt", "value": 6}]}
  ]
}
```

One `criteria` entry per sibling group with two or more children (`parent_id: null` is the top
level) and one `alternatives` entry per leaf. A judgement says `row` is `value` times as important
or preferred as `column`, with 1 ≤ `value` ≤ 9 (any number in that range); each pair appears once,
and its reciprocal is derived. Every matrix must be complete before evaluation, and holds at most
15 items.

**Feasibility requirements** are read by no method (see the
[feasibility check design note](../design/feasibility-check.md)). They read only measurements:
no weights, profiles, value functions, scenarios or method sections.

```json
"requirements": [
  {"kind": "bound", "id": "price_cap", "name": "Unit price within budget",
   "criterion_id": "unit_price", "unit": "NZD", "minimum": null, "minimum_inclusive": true,
   "maximum": 45, "maximum_inclusive": true, "rationale": "Board-approved budget"},
  {"kind": "labels", "id": "certified", "name": "Certified quality system",
   "criterion_id": "certification", "allowed": ["iso9001", "iso9001_14001"], "rationale": ""}
]
```

A `bound` applies to a numeric (interval or ratio) leaf: `minimum`, `maximum` or both, each
inclusive unless `*_inclusive` is false, and `unit`, which must equal the leaf's unit exactly
(`null` when the leaf has none); nothing is converted. `labels` applies to a categorical or ordinal
leaf and lists the allowed labels; the editor's ordinal "at least" and "at most" write the explicit
set. Types are checked when a file is read; the rules (a known leaf, matching scale kind and unit,
ordered limits, known labels) are validation issues of the feasibility check, so a draft can be
saved incomplete. Removing a criterion removes its requirements.

## CriterionNode

`{id, name, parent_id|null, order, description, scale|null, value_function|null}`.
`order` ranks siblings (ties broken by list position). `scale` and `value_function` are present
only on leaves.

## Scale

`{type: categorical|ordinal|interval|ratio, unit?, lower?, upper?, anchor_mode: fixed|local, labels[]}`

## Value functions (discriminated by `kind`)

| kind | fields |
| --- | --- |
| `linear` | `direction` (`increasing`/`decreasing`), `out_of_domain` |
| `piecewise_linear` | `points[{x, value}]`, `out_of_domain` |
| `qualitative` | `mapping{label: value}` |
| `direct_rating` | `min_rating`, `max_rating`, `out_of_domain` |

## Constraints enforced by `validate_project`

Unique ids; acyclic tree with known parents; leaf-only scale/value function/measurements; a
measurement for every alternative × leaf; type and label checks; ratio values ≥ 0; scale bounds
`lower < upper`; scale/value-function compatibility; piecewise ordering, range, monotonicity and
endpoint convention; qualitative mapping coverage, range, endpoints and ordinal order; no
out-of-domain values (unless `clamp`); ≥ 1 weight profile; per sibling group a rating for every
member (only children excepted), ratings finite and ≥ 0, not all zero; all scenario and
configuration references exist.

Result files (`mcda evaluate -o`) use the same conventions and embed `schema_version` (the
version the project needs), `project_id` and `project_fingerprint`.
