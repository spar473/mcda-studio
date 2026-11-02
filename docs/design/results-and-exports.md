# Results, dominance and reproducible exports

Open **Results**. The view-jump buttons focus Overall values, Contributions, Partial values,
Dominance, Scenario comparison or Linked inspection. All views use one completed Python analysis
record. Its project ID, fingerprint, complete configuration, effective scenario, explicit/resolved
profile, warnings, calculation path and digest accompany the data. No chart has an independent
mathematical implementation or numerical result store.

Overall bars share a fixed 0–1 preference axis and display engine competition ranks. Ranking and
contribution tables retain every alternative, including ties and dominated alternatives. Choose
Full precision to inspect very small differences without hovering. Project-order sorting changes
presentation, not ranks. Scores are compensatory preferences, not probabilities or financial returns.

Contribution bars use the engine's weighted leaf contributions in its leaf order. The legend identifies
criteria by name and stable ID; it is also included in SVG downloads. Hidden leaves become labelled
hatched gaps; remaining segments are never renormalised. Hidden alternative bars are named explicitly.
Tables and the partial-value heatmap retain complete data. Selecting a segment, bar, row or heatmap
cell links alternative/criterion inspection, including hierarchy, description, raw measurement/unit,
effective value function/domain, anchor source, global weight and authoritative engine path shares.

The heatmap colours partial preference values in [0,1], with visible numerical/raw values. It does not
put unlike physical units on a shared raw-measurement scale. Heatmap and dominance cells support arrow
keys; buttons, selectors, tables and jump controls support keyboard interaction. Wide regions scroll
inside the editor rather than moving the whole page. Dark-mode, narrow-pane and zoom checks are
recorded, without claiming formal accessibility certification.

Dominance reads the engine's existing partial-value edges, never overall scores. Python additionally
labels equal partial vectors under the same 1e-12 tolerance, incomparable pairs and disabled checks.
Select a matrix/list pair to inspect all supporting partial values. Zero-weight criteria still count
in the diagnostic. Dominance is relative to these criteria and preference functions; it is distinct
from the overall weighted ranking and never removes alternatives.

A selected scenario is compared only with Base. Base explicitly clears the scenario and retains an
explicit profile. Under Automatic, the scenario may resolve a different profile from Base; both IDs
are shown and changes are attributed to functions, weights or both (see [scenarios](scenarios.md)).
A valid selected analysis can be inspected/exported even if Base comparison is unavailable; that
comparison has an explicit diagnostic and no substituted result.

## Numerical and chart downloads

JSON includes the full completed record and unchanged source project, export/record version 1,
complete analysis configuration, raw measurements, effective definitions, partial values, weights,
contributions, ranks, dominance, warnings and presentation metadata. Values retain full available
precision. CSV offers ranking, contributions, partial values, comparison and dominance tables. Rows
carry provenance, stable IDs, units where applicable, configuration and selected-analysis warnings.
CSV ordering follows the chosen rank/project order; numerical downloads always contain complete data.
All result diagnostics remain in JSON; CSV does not repeat every informational dominance message in
its provenance on every row.

A download captures one source/configuration/view snapshot. The server re-evaluates that snapshot and
checks its expected project fingerprint and completed-record digest before returning a file. Changes
to project/scenario/profile cancel and suppress obsolete downloads. There is no persistent export
cache. This deliberate verification evaluation is separate from ordinary chart exploration, which
requires no additional mathematical evaluation.

SVG downloads cover ranking, contributions and comparison, with titles, common axes, dimensionless
preference units, project/revision/profile/scenario context and explicit hidden-series information.
Contribution SVGs include a criterion legend. Display formatting may round labels; SVG metadata and
JSON/CSV retain numerical data. The heatmap has numerical CSV/JSON exports; there is no heatmap
SVG and no PNG/PDF export yet.

Reproduce any JSON export with its explicit configuration, including Base views that override a
saved scenario default:

```python
import json
from mcda_studio.domain.project import Project
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.services.analysis_service import evaluate_project

with open("analysis.json", encoding="utf-8") as stream:
    exported = json.load(stream)
project = Project.model_validate(exported["source_project"])
configuration = AnalysisConfiguration.model_validate(exported["record"]["result"]["configuration"])
assert evaluate_project(project, configuration).model_dump(mode="json") == exported["record"]["result"]
```

Omitting configuration uses saved defaults, which may differ from a transient Base/Automatic view.
For the VC and infrastructure examples, exports were also checked against CLI evaluations in fresh
Python processes. Results, comparison and exports use the evaluation `math.fsum` path. The
sensitivity sweep's plotting accumulation can differ in the last binary place, so it is never mixed
into these records. The VC example's Market Size control points stay exactly as printed in the
source study; no unrounded vendor inputs are invented.

## CSV text policy

Policy `text-prefix-controls-v1` quotes every field, doubles embedded quotes and represents Unicode
control/format characters visibly as `\uXXXX`. Untrusted text whose first character after NFKC
normalisation is neither a letter/digit nor underscore receives a literal `TEXT:` prefix. This
includes leading whitespace/controls/quotes and ordinary/full-width `=`, `+`, `-`, `@` prefixes.
Trusted numerical values remain full-precision numbers. Names, descriptions, units and raw text
measurements use this encoding; stored data is never rewritten. Use JSON for exact original text.
CSV encoding is a defined application policy rather than a universal spreadsheet certification;
[OWASP describes the consumer-specific formula-injection problem](https://community.owasp.org/attacks/CSV_Injection).

## Bounds and scope

The analytical workspace supports up to 100 alternatives, 100 leaves, 1000 total criterion nodes and
10000 measurement entries/data cells; project JSON is limited to 8 MiB, configuration to 4000 bytes,
and labels/descriptions to 2000 characters each. Records/downloads are capped at 16 MiB. Exceeding
bounds gives a structured error. These bounds apply to the results workspace and export services,
not to library or CLI evaluation. The reproducible
benchmark (`tests/fixtures/performance_project.json`) has 50 alternatives, 40 leaves, 52 nodes and
three hierarchy levels; measured timings are in [validation](../development/validation.md).

Not implemented: comparing several scenarios at once, other MCDA methods, and cloud collaboration.
