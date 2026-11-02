# Infrastructure procurement example

A generic capital-works choice: four delivery options for a water-treatment upgrade, scored against
four objectives. It exists to show that hierarchical swing weighting and preference profiles work on
an ordinary decision problem, independently of the NZ deep-tech venture-capital regression.

Rebuild it (the shipped `project.json` must match the script, and a test checks that):

```bash
python examples/infrastructure_procurement/build.py
```

## Why this shape

Each feature below is here because the weighting engine has to handle it, so the fixture cannot be
simplified without weakening the acceptance case. `test_infrastructure_procurement.py` asserts the
shape itself.

| Feature | Where |
| --- | --- |
| Four parent objectives | Lifecycle cost, Service performance, Consent and community, Delivery capability |
| Different numbers of children | three, two, two and one |
| An only child (local weight 1, no invented rating) | Delivery capability → Contractor track record |
| A three-level branch | Service performance → Reliability → two leaves |
| Quantitative scales | ratio costs, margin and outage hours; an interval direct rating |
| Qualitative scales | ordinal compliance and acceptance; unordered categorical footprint |
| A locally anchored range | Operating cost (depends on the current alternative set) |
| A zero-rated criterion in a valid group | Ecological footprint, rated 0 in "Balanced" |
| Two preference profiles | "Balanced" and "Consent led" |
| A scenario naming a profile | "Consent review" → `consent_led`, plus a value-function override |

The two profiles deliberately **disagree** about the ranking, so profile isolation is observable
rather than assumed: swapping profiles has to change the answer.

## The numbers

Global leaf weights under "Balanced" (derived from the raw swings; they sum to one):

| Leaf | Global weight |
| --- | --- |
| Capital cost | 0.166667 |
| Operating cost | 0.116667 |
| Funding risk premium | 0.050000 |
| Design capacity margin | 0.064189 |
| Unplanned outage hours | 0.106982 |
| Water quality compliance | 0.145495 |
| Community acceptance | 0.200000 |
| Ecological footprint | 0.000000 |
| Contractor track record | 0.150000 |

Ecological footprint carries exactly zero weight because its swing was rated 0, which is a real
judgement — not a missing one. Clearing that rating instead makes the group incomplete and the
whole weight set unavailable.

Rankings:

| Profile | Order |
| --- | --- |
| Balanced | Alliance 0.6829, Modular 0.6798, Design-build 0.5366, Regional 0.4307 |
| Consent led | Alliance 0.7573, Modular 0.6411, Regional 0.4873, Design-build 0.4270 |

`validate_project` reports one warning, `LOCAL_ANCHORS` on Operating cost: its range is derived from
the current alternatives, so adding or removing an option changes what its swing rating means.
That is the intended behaviour, and the application raises a swing review when it happens.

Every number above is checked against a plain-Python oracle written separately from the engine in
[`tests/regression/test_infrastructure_procurement.py`](../../tests/regression/test_infrastructure_procurement.py).
