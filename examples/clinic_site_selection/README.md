# Clinic site selection (an invented AHP example)

**Every name and figure here is invented.** This is an illustration of the AHP method, not
evidence about any real town, site, clinic or authority, and not advice.

A small authority chooses a site for a community health clinic from four candidate sites. The
project states two things that are kept apart on purpose:

- **MAVT inputs:** measurements, value functions and two swing-weight profiles, *Access-led* and
  *Cost-led*.
- **AHP judgements:** 42 pairwise answers (6 for the three groups and their leaves, 36 for the
  four sites on each of the six leaves), stated on the 1 to 9 scale.

AHP reads only its own judgements. MAVT reads only its own measurements and ratings. The two ask the
author different questions ("how much more important?" against "how much does going from worst to
best matter?"), so neither is derived from the other and the engine never reconciles them. Where
they lead differently, that is two readings of one model, not an error.

Open it from **Projects → Examples**, or start from the **Clinic site selection** card in the
gallery. Its saved method is *AHP (pairwise priorities)*, so Results shows the priorities and the
consistency of every matrix first. Use **Compare** to see MAVT beside it. Sorting, SMAA-2 and
PROMETHEE II are not stated in this study, so Compare shows their usual "not stated" messages.

## The model

| Group | Leaf | Scale | Better |
| --- | --- | --- | --- |
| Access | Median travel time for the people served | minutes | lower |
| Access | Bus services per hour at the site | services/h | higher |
| Cost | Land and build cost | NZD m | lower |
| Cost | Annual running cost | NZD k/year | lower |
| Fit | Room to expand | none, limited, ample | more |
| Fit | Community support | low, medium, high | more |

The four sites are the *Town centre site*, *Beside the hospital*, the *Edge-of-town site* and the
*Shared school site*. Numeric value functions are linear with fixed anchors just outside the
observed range; the two ordinal leaves use the stated label values.

## What the engine reports (read from a run, not assumed)

- **AHP** puts the *Town centre site* first, then the *Shared school site*, *Beside the hospital* and
  the *Edge-of-town site*, under both the distributive and the ideal synthesis.
- **MAVT** puts the *Shared school site* first under both profiles; the *Town centre site* is second
  under *Access-led* and third under *Cost-led*.
- **One matrix is flagged.** The judgements on *Community support* disagree with themselves: its
  consistency ratio is about 0.16, above the 0.10 threshold, so Results shows the
  `AHP_INCONSISTENT` warning, lists that matrix first in the Consistency panel and names its most
  inconsistent triad. Every other matrix is at or below about 0.03. The engine changes nothing
  because of the flag; it is a hint to revisit those judgements.
- The two methods share a model but not their weights, so agreement between them would not be
  independent validation, and their disagreement here is not a defect.

## Where every number comes from

- **Measurements, value functions, ratings and judgements** are literal values in
  [`build.py`](build.py). All are invented. The AHP judgements are the author's own pairwise
  answers and read no measurement or swing rating.
- **The priorities, consistency ratios and rankings** are computed by the engine. They are checked
  against an independent oracle in `tests/regression/test_method_exemplars.py` in the source
  distribution.

Rebuild it in a source checkout (the shipped `project.json` must match the script, and a test
checks that):

```bash
python examples/clinic_site_selection/build.py
```

## Limits

- Four sites and one judge: this shows how AHP works, not how a real siting decision should be
  made. AHP is single-judge here; group aggregation is not provided.
- A low consistency ratio does not show that judgements are right, and a high one does not show they
  are wrong.
- The distributive synthesis can reverse the order of two alternatives when a copy of one is added;
  the ideal synthesis does not. Both are shown (see the [AHP design note](../../docs/design/ahp.md)).
