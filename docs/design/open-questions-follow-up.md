# Open Questions: next implementation slice

The read-only CLI, API and Open Questions tab report missing measurements, unknown feasibility
checks, existing one-way MAVT winner-change thresholds and leader disagreements between MAVT,
PROMETHEE II and AHP when they run, against a project fingerprint and selected
profile and scenario. Weight sensitivity is skipped above 50 nodes or when validation fails; the
result states why. It holds other inputs fixed and never proves global robustness. Class questions
reuse the sorting engine's first class change in each direction for every eligible weight and
alternative, with its existing boundary rule. SMAA-2 questions retain the original inputs-to-check
order and heuristic label, path, frequency difference, draw count, seed and algorithm. Viewed
SMAA-2 parameters are used when SMAA-2 is selected; otherwise its default parameters are used.
Exact enumeration does not produce that heuristic and is labelled accordingly. No uncertainty
section is inferred from evidence ranges. An optional local dossier produces questions for
unreviewed, outdated and conflicting claims, including their provenance. A stale or invalid dossier
is not used. The dossier is read-only and no claim is automatically accepted. Accepted ranges
whose value matches the entered measurement receive fixed-anchor one-measurement screening: the
engine evaluates interval endpoints and contained control points, and compares the target's rank
and class at the score extrema using its ordinary tolerance rules. This determines whether either
can change within the closed range. Boundary contacts are solved algebraically on each segment
using rational representations of stored floating-point inputs and weights; exact ratios accompany
rounded coordinates. Rank thresholds use the other alternative's evaluated score minus 1e-12;
class thresholds use the class boundary minus 1e-12. Flat solution intervals and endpoint contacts
are retained. A contact need not change the result, so evaluated score-extremum witnesses determine
the change flags using the engine's ordinary floating-point comparisons. Do not infer boundary
membership from a rounded coordinate. The editor shows witnesses separately from contacts. Local linear anchors,
out-of-domain bounds and ranges on a different or corrected claim are refused explicitly. A
current-measurement support audit distinguishes missing, unsupported, unverified and accepted
matching support in the supplied dossier; those statuses do not determine numerical validity.
A verified local factor run can additionally expose each fundamental factor’s source classification,
shared formula uses and distribution assumptions as questions. This does not establish propagated
evidence quality or factual support; those remain unimplemented.
The view lists unavailable methods and does not treat agreement as independent validation.
Group blocking, decision-sensitive and
support-quality questions without a composite score; each question should name its source, affected
IDs, reason and a concrete next action. Report which analyses could not run and why. The dossier
is selected locally for this view and is not stored in the project. Decision snapshots use the Decision workspace; factor-run snapshots are exported separately.

The calculation supports numeric linear, direct-rating and monotone piecewise-linear functions,
including decreasing functions and flat segments. Zero-weight and singleton ranges are valid.
It uses the selected profile and scenario override. Numeric local linear anchors are unsupported
because changing the measurement would move the anchors and other alternatives' scores. Bounds
outside the resolved domain are refused even when the value function's general policy is clamp.
Unreviewed or rejected claims, stale dossiers, corrected values whose original range has not been
reviewed again, and accepted values that differ from the entered cell cannot supply the range.
The range must contain the entered value. The engine never updates measurements during this check.
The independent numerical oracle uses NumPy interpolation and SciPy root finding, without importing
the application. Hand-calculated rational cases and property tests check the analytical contacts,
while fresh engine evaluations check the witnesses and tolerance edges.
