# Method seam

**Status:** accepted design, 28 October 2026; **implemented in full**. The backend contract (§1,
§2, §4 and §8) on 28 October 2026 ([check record](../development/method-seam-verification.md));
the result union, version-2 records, the schema-version rule and the frontend method view (§3,
§5, §6, §7) with [value-based sorting](value-based-sorting.md) on 29 October 2026
([check record](../development/value-based-sorting-verification.md)). See the
[implementation notes](#implementation-notes). The owner accepted all four
[decisions](#decisions) on 28 October 2026.

The method seam is the first development of the method track (see the roadmap's owner decisions of
28 October 2026). It lets more than one decision method run on the same project without changing
anything MAVT does today. It adds no method of its own: value-based sorting, SMAA-2, PROMETHEE II
and AHP each come later through it. The detailed earlier proposal is in
plan §5.1 (historical record, not included); this note decides it for the new order, in which
**value-based sorting**, not AHP, is the first method to use the seam.

## What exists today

A partial seam is already in the code:

- `methods/base.py` defines a `Method` protocol (`name`, `evaluate`) and a registry. Only
  `MavtMethod` is registered.
- `AnalysisResult` is a method-independent base (method, fingerprint, configuration, ranking,
  diagnostics, assumptions). `MavtResult` extends it.
- `AnalysisConfiguration` already carries `method` (default `"mavt"`) and a free-form `parameters`
  dictionary.

MAVT is still hard-wired in five places:

| Place | Today |
| --- | --- |
| Validation | `validate_analysis` reports `UNSUPPORTED_METHOD` for anything but `mavt`, and all MAVT checks (scales, value functions, swing judgements) run for every project |
| API | `/evaluate` returns `MavtResult`; a non-MAVT result raises 501 behind `pragma: no cover`. Sensitivity, probes, previews and scenario comparison assume MAVT without checking |
| Analysis records and exports | `AnalysisRecord` embeds `MavtResult`, contributions, path shares and dominance; CSV and SVG exports read them directly |
| Frontend | The Results workspace, charts, tables and the record hook read `MavtResult` fields directly |
| Project file | No place for method-specific inputs (class boundaries, preference thresholds, pairwise judgements, uncertainty ranges) |

## Goals and non-goals

**Goals:**

- A second method can be added by registering it, declaring what it can do and providing its
  result type, panels and validation, without touching MAVT code paths.
- **MAVT is byte-identical:** for an MAVT-only project, results, analysis records, exports, project
  files and fingerprints are unchanged. The three bundled examples keep their pinned hashes.
- Every route and panel that only makes sense for some methods checks a declared capability and
  fails with a typed error, never a 500 or a silently wrong panel.
- The rules of cross-method verification hold by construction: results are never averaged, and one
  method's inputs are never reused as another's.

**Non-goals (excluded):**

- any new method, schema field or calculation (each comes with its own development);
- a plugin system, dynamic loading or a generic editor framework;
- the method comparison view (a later development that reads results through this seam).

## Design

### 1. Methods declare capabilities and own their validation

The `Method` protocol gains three members:

```python
class Method(Protocol):
    name: str                                  # stable id, e.g. "mavt"
    label: str                                 # shown in the interface, e.g. "MAVT (additive value)"
    capabilities: frozenset[Capability]
    def validate(self, project: Project, configuration: AnalysisConfiguration) -> list[Issue]: ...
    def evaluate(self, project: Project, configuration: AnalysisConfiguration) -> AnalysisResult: ...
```

`Capability` is a closed `Literal` of names that a route or panel actually checks, so a typo is a
type error. Only names needed by MAVT and the planned methods are listed:

| Capability | Checked by | MAVT | Sorting | SMAA-2 | PROMETHEE II | AHP |
| --- | --- | --- | --- | --- | --- | --- |
| `value_functions` | value-function preview and editor | ✓ | ✓ | ✓ | | |
| `swing_weights` | weight preview, Weights screen, profiles | ✓ | ✓ | ✓ | | (elicitation form only) |
| `value_scores` | overall-value chart on a 0–1 axis | ✓ | ✓ | | | |
| `contributions` | contributions, partial values, dominance | ✓ | ✓ | | | |
| `weight_sensitivity` | `/sensitivity`, `/sensitivity/probe` | ✓ | ✓ | | | |
| `scenario_comparison` | `/scenarios/compare` | ✓ | ✓ | later | | |
| `classes` | class panel, class column | | ✓ | | | |
| `acceptability` | rank-acceptability panel | | | ✓ | | |
| `flows` | flows panel | | | | ✓ | |
| `consistency` | consistency panel | | | | | ✓ |

The table's later columns are the plan, not a commitment; each method's own design note confirms
its row.

**Validation moves behind the method.** `validate_analysis` keeps the method-independent checks
(structure, IDs, alternatives, measurements against scales, configuration references) and then
calls `get_method(cfg.method).validate(...)`. The current MAVT checks (value functions, swing
judgements, local anchors) move into `MavtMethod.validate` unchanged, in the same order, so every
issue code, path and message stays identical. An unregistered method becomes `UNKNOWN_METHOD`
(replacing `UNSUPPORTED_METHOD`, whose only trigger was "not MAVT").

### 2. Method-owned parameters

`AnalysisConfiguration.parameters` stays a dictionary in the project file, but each method parses
it with its own Pydantic model (for example SMAA's sample count and seed). MAVT's model declares
the one parameter it reads today, `dominance_check` (default true). Unknown keys are ignored today;
under the seam they produce an `UNKNOWN_PARAMETER` **warning**, not an error, so no existing
project stops evaluating (the bundled examples have none). A wrongly typed known parameter is an
error. Parameters are part of the configuration, so they already flow into fingerprints of results,
analysis records and request keys.

### 3. A discriminated result union

```python
AnalysisResultUnion = Annotated[MavtResult | MavtSortingResult | ..., Field(discriminator="method")]
```

The union is introduced together with the first second method (sorting), as the plan requires: no
one-member union. `/evaluate` returns the union. The OpenAPI document and generated TypeScript
types gain a tagged union, and the frontend narrows by `result.method`. For MAVT the JSON body is
unchanged.

### 4. Routes check capabilities

Routes that need a capability look up the configuration's method first. A missing capability
returns **422** with code `METHOD_NOT_SUPPORTED` and details naming the method, the capability and
the method's declared capabilities. That replaces the uncovered 501. The routes and their
capabilities:

- `/sensitivity`, `/sensitivity/probe`: `weight_sensitivity`;
- `/scenarios/compare`: `scenario_comparison`;
- `/value-functions/preview`: `value_functions`;
- `/weights/preview`: `swing_weights`;
- `/analysis/record` and exports: any method, using the record envelope below.

`/api/meta` lists each method's `name`, `label` and capabilities, so the frontend never hard-codes
them.

### 5. Analysis records: keep version 1 for MAVT, add version 2 for everything else

The version-1 `AnalysisRecord` is MAVT-specific (calculation path `mavt.math_fsum.v1`,
contributions, path shares, dominance). Rather than generalise it and change MAVT bytes:

- **MAVT records stay version 1**, byte for byte, with their current digest rules.
- **Every other method produces a version-2 record:** a small common envelope (record version,
  digest, method, method label, calculation path, numerical tolerance, project title, scenario and
  profile names where they apply, alternative order, configuration) plus the method's own result
  and the method-specific context it needs. A version-2 record never contains MAVT contributions or
  dominance unless the method declares `contributions`.
- **The export document** accepts either record version. CSV tables are declared per method; a
  method only exports tables it can fill. SVG charts follow the same rule.
- **Old exports stay readable:** a version-1 export is always read as MAVT.

### 6. Project files: write the lowest sufficient schema version

Each method that needs stored inputs adds one optional, typed section to `Project` with its own
schema bump and migration (sorting first: `sorting`). To keep MAVT byte-identical and older
installations useful:

- **Absent method sections are omitted** from the saved file and from the canonical JSON used for
  fingerprints. They are never written as `null`.
- **A file is written with the lowest schema version that can represent it.** An MAVT-only project
  is still written as schema version 1, so its bytes and fingerprint do not change, and an older
  MCDA Studio still opens it. A project that uses class boundaries is written as version 2, which an
  older installation refuses with its existing "newer than this program" message.
- **Loading** accepts every version up to the current one, as today.

This refines plan §16, which expected every re-save to change bytes after a migration. Under this
rule only projects that actually use a new section change.

### 7. Frontend dispatch and method selection

- **Panels by method.** A small registry maps each method to its Results panels. The current MAVT
  panels become the `mavt` entry, unchanged. A panel whose capability is missing is not shown; the
  tab list explains in one line which views the method does not offer.
- **Method selection works like scenario and profile selection.** Choosing a method in the
  Results header is a transient *view*: it creates no edit and no unsaved change, and it is part of
  the analysis context, so request keys and stale-response protection already cover it. **Use
  viewed method as saved default** writes `project.analysis.method` through the normal undoable
  edit, as the profile control does today.
- **Editors stay where they are.** The Weights screen, value-function editor and Measurements are
  unchanged. Method-specific editors (class boundaries, preference thresholds, pairwise matrices)
  arrive with their methods and appear only when the viewed method uses them.

### 8. The cross-method rules, enforced

- Each result names its own method, inputs, parameters and calculation path; there is no shared
  "score" field across methods.
- No route or type combines the numbers of two methods. The comparison view (decided 31 October
  2026) runs each method separately and lays the results side by side; it reads separate
  results side by side. The feasibility check (31 October 2026) is not a method and reads no
  method's results or inputs; it is shown beside each ranking and never changes one.
- A method's stored inputs belong to that method's section. No method reads another method's
  section (for example, PROMETHEE II never reads swing profiles, and AHP priorities are never used
  as MAVT weights).

## Verification plan

- **MAVT unchanged:** the full existing suite, regression oracles, the contract baseline (schemas
  and example hashes), and byte comparisons of MAVT results, version-1 records and every export
  format for the three examples, before and after.
- **A test-only fake method,** registered only in tests, with a minimal result type and a chosen
  set of capabilities. It proves:
  - each capability-gated route returns 422 `METHOD_NOT_SUPPORTED` with the right details;
  - `/api/meta` lists it;
  - validation dispatches to it, and `UNKNOWN_METHOD` covers unregistered names;
  - a version-2 record and export round-trip for it.
- **A contract test:** for every registered method, the routes it may call match its declared
  capabilities.
- **Schema writing:** an MAVT-only project saves as version 1 with identical bytes; a project with
  a (test-only) method section saves as version 2; both reload.
- **Frontend:** the panel registry hides unsupported panels; viewing a method creates no edit;
  "use as saved default" is one undo step.
- **Mutants:** a capability check removed from a route; validation not dispatched to the method;
  a version-1 MAVT record written as version 2; an absent method section written as `null`; the
  lowest-sufficient-version rule replaced by "always the newest".

## Acceptance

- MAVT results, version-1 records, exports, project bytes and fingerprints are byte-identical for
  all three examples, and every existing test passes unchanged.
- Each capability-gated route returns a typed 422 for a method without that capability.
- Validation issue codes, paths and messages for MAVT projects are unchanged.
- The fake method round-trips through evaluate, record and export without touching MAVT code.
- The full gate is green and all new mutants are killed.

## Decisions

Accepted by the owner on 28 October 2026, as recommended:

1. **Lowest sufficient schema version.** MAVT-only projects stay version 1 and byte-identical,
   and older installations keep opening them. The cost is a little serialisation logic and its
   tests. Rejected alternative: always write the newest version, as plan §16 assumed, which
   changes every project's bytes on its next save.
2. **Method selection is a transient view** with a separate "use as saved default", like
   scenarios and profiles; it suits cross-method checking. Rejected alternative: switching method
   is always an edit.
3. **Sorting is its own method (`mavt_sorting`)** whose result extends `MavtResult` with classes,
   as plan §8.3 proposed; it keeps every MAVT panel available for sorting. Rejected alternative: a
   class layer applied on top of any method with value scores.
4. **An unsupported capability returns 422 `METHOD_NOT_SUPPORTED`:** the request is well formed
   but cannot be served for that method. Rejected alternative: the current 501.

## Implementation notes

Implemented 28 October 2026, MAVT byte-identical (see the
[check record](../development/method-seam-verification.md)).

**Delivered now (the backend contract):**

- `methods/base.py`: the closed `Capability` vocabulary, the extended `Method` protocol,
  `validate_analysis` (method-independent checks, then the method's `validate`; `UNKNOWN_METHOD`
  for an unregistered name), `require_capability`, `require_record_v1` and `check_parameters`.
- MAVT declares its label and six capabilities. Its checks moved behind `MavtMethod.validate` as a
  whole and in the same order (`validate_value_model`), so every MAVT issue code, path and message
  is unchanged. The method-independent part is, for now, only the duplicate profile and scenario
  ID checks; more checks move out when a method that does not use value functions needs them.
- `MavtParameters` parses `dominance_check` as a strict boolean.
- The service layer checks capabilities, so the CLI and the API refuse the same requests. An
  unregistered method is let through to validation, as evaluation always has.
- Version-1 analysis records and exports are refused for any method but MAVT, because they hold
  MAVT data. `/evaluate` refuses a result without an API model with 422, replacing the 501.
- `/api/meta` lists each method's name, label and capabilities.

**Found during implementation:** a sixth hard-wired place. The read-only previews refused any
method but `mavt` themselves; they now look the method up and rely on the capability check.

**Deferred to value-based sorting,** because each needs a real second result type or stored
section to be meaningful and testable without dead code:

- the discriminated result union (§3), already planned to arrive with sorting;
- the version-2 record envelope and per-method export tables (§5);
- omitting absent method sections and writing the lowest sufficient schema version (§6);
- the frontend panel registry and the transient method view with "use as saved default" (§7).

The verification items for those parts (a version-2 round trip, the schema-writing tests and their
mutants) move with them.


**Completed with value-based sorting** (29 October 2026; see its
[design note](value-based-sorting.md) and
[check record](../development/value-based-sorting-verification.md)):

- **§3** `AnalysisResultUnion` (`MavtResult | MavtSortingResult`, tagged by `method`) on
  `/evaluate`. MAVT's fields moved, unchanged and in order, into a shared `ValueModelResult` base,
  so each result keeps its own tag and the `MavtResult` schema is identical. The sensitivity and
  probe routes return `SortingSensitivityResult | SensitivityResult`; an MAVT body gains no key.
- **§5** `RecordEnvelopeV2` and `SortingAnalysisRecord`; `/analysis/record` was discriminated by
  `record_version`, and since SMAA-2 by a tagged callable discriminator (version 1, or the
  version-2 method), which publishes a plain `oneOf`. Version 1 is unchanged and MAVT only. CSV tables are declared per method
  (`EXPORT_TABLES`, also listed in `/api/meta` as `export_tables`); a JSON export of a version-2
  record has `export_version: "2"`. The version-2 round trip is verified with the real sorting
  method; the fake method keeps proving refusals.
- **§6** `schema_version` 2 with the identity migration; `Project.required_schema_version()` and
  a field serializer write the lowest sufficient version, and absent sections are omitted
  (`exclude_if`). The in-memory version is normalised on load and by the section edits, so a
  loaded project equals a freshly built one. `PUT` accepts any version from what the content needs
  up to the newest. All 410 MAVT outputs of the byte-identity script are unchanged.
- **§7** `results/panels.ts` (panels by method, filtered by capability, with a one-line list of
  views not offered); a Method select in the analysis header (a transient `AnalysisSelection.method`
  that survives undo); **Use viewed method as saved default** (`set_analysis_method`, one undo
  step); method-specific editors shown only when the viewed method uses them.
- **Decision 5 of the sorting note** settles parameters across methods: a viewed method other than
  the saved one runs with its own defaults, and changing the saved method clears the saved
  parameters.
- **Also found:** swing-review identity included the whole configuration, so viewing another method
  would have asked for a swing review. It now uses only the scenario and profile.

**Extended with PROMETHEE II** (31 October 2026; see its [design note](promethee-ii.md) and
[check record](../development/promethee-ii-verification.md)), the first method that does not read
the MAVT model:

- `validate_measurements` gives the method-independent checks (alternatives, tree, performance
  table, scales and measurements) without value functions, profiles or scenarios; MAVT's own
  report is unchanged, issue for issue.
- The frontend requests the MAVT editors' previews for `mavt`, with the same profile and scenario,
  while a method outside the MAVT family is viewed; the preview routes still refuse that method.

**Extended with AHP** (31 October 2026; see its [design note](ahp.md) and
[check record](../development/ahp-verification.md)), the first method that reads no measurements:

- `validate_structure` gives the alternative and tree checks alone; `validate_measurements` now
  begins with the same helper, and PROMETHEE II's report is unchanged, issue for issue.
- A method-specific read-only route, `POST /api/ahp/preview`, serves the editor's live
  consistency preview without a project or a capability check.
- A result may name no weight profile or scenario (`null`) when the method reads neither; the
  frontend's record check expects that for AHP.
