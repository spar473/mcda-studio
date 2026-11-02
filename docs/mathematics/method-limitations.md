# Method limitations: additive MAVT

Cases where this model may be inappropriate, or where a result needs care.

1. **Full compensation.** A very poor score on one criterion can be offset by good scores
   elsewhere. If a criterion is a hard requirement (a legal minimum, a safety threshold), state it
   in the feasibility check, which tests it outside the score, rather than relying on a low weight.
   The ranking itself still compensates; read the feasibility status beside it.
2. **Preferential independence.** The additive form is only valid if preferences on one criterion
   do not depend on the levels of another. The software cannot test this; it is a modelling
   judgement. Interacting criteria need a different aggregation.
3. **Weights are tied to ranges.** Swing weights mean "importance of going worst → best over *this*
   range". Re-defining a scale's anchors without revisiting the ratings silently changes the
   meaning of the weights.
4. **Local anchors make scores depend on the alternative set.** Adding or removing an alternative
   can change every score on that criterion (and even the ranking: rank reversal). Prefer `fixed`
   anchors when the set of alternatives may change; `local` always warns.
5. **Ordinal and categorical mappings are judgements.** `1–5` is *not* assumed equally spaced;
   the mapping values you choose are part of the model and deserve their own sensitivity check.
6. **Sensitivity is one-way and proportional.** It varies one local weight at a time and rescales
   its siblings in proportion. It does not explore simultaneous changes, nor other redistribution
   rules, nor value-function or measurement uncertainty (only the scenario comparison touches the
   value functions). Stable one-way results do not prove robustness.
7. **No uncertainty model.** Scores are preference values, **not** probabilities of success. Do not
   read 0.72 as a 72% chance of anything.
8. **No imputation.** Missing measurements make the model invalid; the engine will not guess.
9. **Ties** within 1e‑12 share a rank; very small genuine differences are not flagged as
   significant. A numerical lead is not a decisive one.
10. **Small alternative sets** (e.g. four) demonstrate a method but cannot evaluate a decision
    process's predictive quality.
11. **Not a replacement for DECERNS.** No DECERNS behaviour has been observed or compared. Reproducing the printed results
    of the VC reference study shows agreement with that report, not with every DECERNS setting.
12. **Sensitivity cannot vary a node that has no siblings**, or that already carries the whole local
    weight (siblings rated 0): the proportional redistribution is undefined. `sensitivity --all`
    lists such nodes as "not analysed".
13. **Piecewise and qualitative value functions must end at 0 and 1.** A function whose worst and best
    ends have other values cannot be represented; rescale it so the ends are 0 and 1.
14. **Reference data is only as precise as it is printed.** Where a published study rounds its inputs
    (the VC study's Market Size control points), recomputed outputs agree to the rounding, not
    beyond it.
