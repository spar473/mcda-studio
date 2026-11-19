# Engineering trade study (an invented study that states every method)

**Every name and figure here is invented.** This is an illustration of the methods, not evidence
about any real vehicle, supplier, test or cost, and not engineering advice.

A team chooses a concept for an autonomous inspection vehicle that will survey a long service tunnel,
from five concepts: a *Wheeled rover*, a *Tracked crawler*, a *Legged walker*, a *Tethered crawler*
and a *Small aerial drone*. It is the one study here that states **every** method's section, so the
comparison view shows five real columns. The project keeps these apart on purpose:

- **MAVT inputs:** measurements, value functions, two swing-weight profiles (*Performance-led* and
  *Cost-led*) and one scenario (*Diminishing returns on endurance*).
- **Value-based sorting:** three classes, *Shortlist*, *Reserve* and *Drop*, with illustrative
  boundaries on the overall value.
- **SMAA-2:** stated uncertainty: test spreads on endurance, payload and unit cost, one maturity that
  is not settled, and uncertain top-level swing ratings.
- **PROMETHEE II:** its own direction, weight and preference function for each of the seven criteria,
  and its own codes for the three ordinal ones.
- **AHP:** 78 pairwise judgements of the author's own: 8 on the criteria and 70 on the five concepts.
- **Two requirements,** checked outside every score: a payload of at least 2 kg, and a technology at
  least at prototype stage.

Each method reads only its own section, and none is derived from another: swing ratings, PROMETHEE II
weights and AHP judgements ask the author different questions, so differences between them are not
errors to reconcile.

Open it from **Projects → Examples**, or start from the **Engineering trade study** card in the
gallery. It opens on MAVT. Open **Compare** to see the five methods side by side, then switch the
weight profile to *Cost-led* to see where they differ.

## The model

| Group | Leaf | Scale | Better |
| --- | --- | --- | --- |
| Performance | Endurance | min | higher |
| Performance | Payload capacity | kg | higher |
| Performance | Obstacle capability | low, medium, high | higher |
| Cost | Unit cost | NZD k | lower |
| Cost | Annual maintenance cost | NZD k/year | lower |
| Risk | Technology maturity | concept, prototype, proven | higher |
| Risk | Operator skill needed | high, medium, low | less needed |

Ordinal labels are listed from the worst to the best, because the engine reads an ordinal scale low to
high and refuses a mapping that decreases along it.

## What the engine reports (read from a run, not assumed)

- **Requirements.** The *Legged walker*, at concept stage, fails the technology requirement. The
  *Small aerial drone* fails the payload requirement (1.2 kg against at least 2). The *Tethered
  crawler* carries exactly 2.0 kg and passes, because the limit is inclusive. The other two pass
  both. Both failing concepts stay in every ranking and class with the failure beside them. Neither
  scores strongly: the *Legged walker* is last under every method and the *Small aerial drone* is
  fourth, so this study does not show a strong score hiding a failure. The
  [flood defence example](../flood_defence_options/README.md) does.
- **MAVT.** Under *Performance-led*: *Tracked crawler* 0.6845, *Wheeled rover* 0.6219, *Tethered
  crawler* 0.5859, *Small aerial drone* 0.4615, *Legged walker* 0.3322. Under *Cost-led* the *Wheeled
  rover* leads (0.7257) ahead of the *Tracked crawler* (0.7164).
- **Sorting.** Under *Performance-led* the *Tracked crawler* is *Shortlist*, the *Wheeled rover* and
  the *Tethered crawler* are *Reserve*, and the other two are *Drop*. The boundaries (0.65 and 0.50)
  are judgements, and I chose them after the MAVT values were known so that a concept sits close to
  one: the *Wheeled rover* is 0.028 below the *Shortlist* boundary. Under the scenario it rises to
  0.6591 and becomes *Shortlist*.
- **SMAA-2** (the default combined run, under *Performance-led*: 10,000 draws, seed 0; the shares
  depend on the profile). The *Tracked crawler* is first in 99.8% of draws. The *Wheeled rover* is *Shortlist* in 33.0% of draws and *Reserve* in 67.0%, the
  *Tethered crawler* 30.1% and 69.9%, and the *Small aerial drone* is *Drop* in 91.3% and *Reserve* in
  8.7%. These are shares of draws under the stated uncertainty, not probabilities of anything.
- **PROMETHEE II** ranks the *Tracked crawler* (+0.2892), *Wheeled rover* (+0.2460), *Tethered
  crawler* (+0.0586), *Small aerial drone* (−0.1444) and *Legged walker* (−0.4493). Every pair is
  ordered, and MAVT under *Performance-led* orders no pair differently.
- **AHP** gives the *Tracked crawler* 0.2625, *Wheeled rover* 0.2464, *Tethered crawler* 0.2219,
  *Small aerial drone* 0.1527 and *Legged walker* 0.1165. No matrix is flagged; the largest
  consistency ratio is 0.052.
- **Compare.** Under *Performance-led* all five methods put the *Tracked crawler* first. Under
  *Cost-led*, MAVT and sorting lead with the *Wheeled rover*, while SMAA-2, PROMETHEE II and AHP
  still lead with the *Tracked crawler*: PROMETHEE II and AHP read no weight profile, and SMAA-2's
  top-level weights come from its own stated intervals. Agreement between methods that share
  measurements is not independent validation.

## Where every number comes from

- **Measurements, value functions, ratings, boundaries, distributions, weights, thresholds and
  judgements** are literal values in [`build.py`](build.py). All are invented, and each method's
  inputs are the author's own.
- **Values, classes, flows, priorities, statuses and acceptabilities** are computed by the engine
  and checked against independent oracles in `tests/regression/test_method_exemplars.py` in the
  source distribution. SMAA-2 is a sampled run, so its check is a bounded statistical one against an
  independent sampler, not an exact one.

Rebuild it in a source checkout (the shipped `project.json` must match the script, and a test
checks that):

```bash
python examples/engineering_trade_study/build.py
```

## Limits

- Five concepts and invented figures: this shows how every method reads one model, not how to choose
  an inspection vehicle.
- **Feasibility is not probabilistic.** A requirement is tested on the entered value. SMAA-2 draws can
  fall below a limit the entered value meets: the *Tethered crawler's* payload range, 1.8 to 2.2 kg,
  spans its 2.0 kg limit.
- SMAA-2 here uses uniform ranges, one categorical cell and rating intervals. The engine also
  supports triangular and discrete distributions and shared draws; they are not used in this study.
- The sorting boundaries are illustrative. A concept near one, such as the *Wheeled rover*, moves
  class under small changes.
- A single author's judgements stand behind every method; AHP is single-judge here.
