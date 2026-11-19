# Flood defence options (an invented feasibility and PROMETHEE II example)

**Every name and figure here is invented.** This is an illustration of two methods, not evidence
about any real town, flood risk, standard, cost or authority, and not engineering or planning
advice.

A small coastal town compares five ways of reducing flood risk: a *Raised sea wall*, *Dune
restoration with pumping*, *Flood gates and raised road*, *Managed retreat of the lowest street* and
*Maintain the existing defences*. The project states three things that are kept apart on purpose:

- **MAVT inputs:** measurements, value functions and two swing-weight profiles, *Safety-first* and
  *Cost-conscious*.
- **Two requirements**, checked outside every score: a protection standard of at least 100 years,
  and a consent pathway that exists.
- **PROMETHEE II inputs:** its own direction, weight and preference function with thresholds for each
  of the seven criteria, and its own numeric code for each label on the two ordinal criteria.

MAVT reads its own ratings, PROMETHEE II reads its own weights and thresholds, and neither is derived
from the other: swing ratings say how much going from worst to best matters, PROMETHEE II weights are
importances applied to preference degrees. The requirements are read by neither.

Open it from **Projects → Examples**, or start from the **Flood defence options** card in the
gallery. It opens on MAVT. Open **Requirements** to see each option's status beside the ranking, and
**Compare** to see MAVT beside PROMETHEE II. Sorting, SMAA-2 and AHP are not stated in this study, so
Compare shows their usual "not set up" messages.

## The model

| Group | Leaf | Scale | Better |
| --- | --- | --- | --- |
| Protection | Flood protection standard | years (return period) | higher |
| Protection | Residual risk if overtopped | high, medium, low | lower risk |
| Cost | Capital cost | NZD m | lower |
| Cost | 50-year maintenance cost | NZD m | lower |
| Environment and community | Habitat disturbed | ha | lower |
| Environment and community | Consent pathway | not consentable, contested, notified, routine | easier |
| Environment and community | Construction disruption | months | lower |

Ordinal labels are listed from the worst to the best, because the engine reads an ordinal scale
low to high and refuses a mapping that decreases along it.

## What the engine reports (read from a run, not assumed)

- **Requirements.** *Maintain the existing defences* is the cheapest option and fails the protection
  standard (25 years against at least 100). *Managed retreat of the lowest street* fails the consent
  requirement ("not consentable"). The other three pass both. *Dune restoration with pumping* has a
  protection standard of exactly 100 years and passes, because the limit is inclusive.
- **Failed options stay in every ranking.** The status sits beside the ranking and changes no
  value: a test removes the requirements and finds every MAVT value and PROMETHEE II flow unchanged.
  *Managed retreat* leads PROMETHEE II and leads MAVT under *Cost-conscious* while failing consent;
  *Maintain the existing defences* is third in PROMETHEE II while failing the protection standard.
  That is why a hard limit is stated as a requirement and not left to a low weight.
- **MAVT under Safety-first** ranks *Flood gates and raised road*, *Managed retreat*, *Raised sea
  wall*, *Dune restoration with pumping* and *Maintain the existing defences*. Under *Cost-conscious*
  it ranks *Managed retreat*, *Flood gates*, *Dune restoration*, *Maintain the existing defences* and
  *Raised sea wall*.
- **PROMETHEE II** ranks *Managed retreat*, *Flood gates*, *Maintain the existing defences*, *Dune
  restoration* and *Raised sea wall*, by net outranking flow.
- **Compare.** Under *Safety-first* the two methods lead differently, and the engine's explanation
  names the four pairs they order differently. Under *Cost-conscious* the MAVT leader is the one that
  leads PROMETHEE II.
- **A large advantage counts only up to full preference.** Against *Maintain the existing defences*,
  the *Raised sea wall* costs 39 NZD m more, but the capital-cost preference threshold is 20, so
  anything beyond 20 counts no further. PROMETHEE II still adds up across criteria, so the ranking
  still compensates: it does not make a requirement unnecessary.
- **A difference exactly at a threshold counts no preference.** *Managed retreat* disturbs 0.8 ha and
  *Dune restoration* 0.4 ha, exactly the 0.4 ha indifference threshold, so neither is preferred on
  habitat.
- The two methods share measurements but not weights, so agreement between them would not be
  independent validation, and their disagreement here is not a defect.

"Unknown" is a third requirement status, for a missing measurement. This study shows none, because
a missing measurement makes a ranking unavailable and the engine never fills it in.

## Where every number comes from

- **Measurements, value functions, ratings, requirements, weights and thresholds** are literal
  values in [`build.py`](build.py). All are invented. PROMETHEE II's inputs read no swing rating and
  no value function.
- **Statuses, values, flows and rankings** are computed by the engine and checked against
  independent oracles in `tests/regression/test_method_exemplars.py` in the source distribution.

Rebuild it in a source checkout (the shipped `project.json` must match the script, and a test
checks that):

```bash
python examples/flood_defence_options/build.py
```

## Limits

- Five options and invented figures: this shows how a requirement and two methods read one model,
  not how to choose flood defences.
- A requirement is tested on the entered measurement, with no allowance for uncertainty.
- PROMETHEE II's thresholds are judgements. Moving one can change its ranking, and the design note
  explains how to read the pair explanation (see the [PROMETHEE II design note](../../docs/design/promethee-ii.md)).
