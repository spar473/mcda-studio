"""The explanation against MAVT (design note §4): the criteria and thresholds behind each pair that
PROMETHEE II and MAVT order differently.

MAVT's side is the unchanged MAVT engine under the configuration's profile and scenario. The only
cross-method operation is comparing orders: each gap stays in its own method's units, and no
number adds, averages or subtracts a value and a flow.
"""

from typing import Literal

from mcda_studio.domain.common import Id, Issue, Severity
from mcda_studio.domain.errors import McdaError, UnknownReferenceError, ValidationFailed
from mcda_studio.domain.outranking import UShapeFunction, UsualFunction, thresholds
from mcda_studio.domain.results import (
    CriterionExplanation,
    MavtResult,
    OutrankingExplanation,
    PairExplanation,
    RankComparison,
)
from mcda_studio.methods.mavt.aggregation import TIE_TOL, build_mavt_result, prepare_mavt
from mcda_studio.methods.promethee.flows import Flows, PreparedPromethee, preference_degree

DETAIL_LIMIT = 50
MAX_REASONS = 3


def _sign(x: int) -> int:
    return (x > 0) - (x < 0)


def _mavt_side(prep: PreparedPromethee) -> tuple[MavtResult | None, str | None, list[str]]:
    configuration = prep.configuration.model_copy(update={"method": "mavt", "parameters": {}})
    try:
        return build_mavt_result(prepare_mavt(prep.project, configuration)), None, []
    except ValidationFailed as exc:
        codes = sorted({i.code for i in exc.report.errors})
        return (
            None,
            "MAVT's model is not valid under this weight profile and scenario, so the explanation "
            "against MAVT is omitted; PROMETHEE II's flows do not depend on it",
            codes,
        )
    except McdaError as exc:
        return None, f"MAVT could not be evaluated: {exc}", []


def _zone(degree: float) -> Literal["no_preference", "partial", "full"]:
    return "no_preference" if degree == 0.0 else "full" if degree == 1.0 else "partial"


class _Pair:
    """Phrases for one oriented pair (a, b)."""

    def __init__(self, prep: PreparedPromethee, a: int, b: int) -> None:
        self.prep, self.a, self.b = prep, a, b
        self.names = [prep.names[i] for i in prep.alt_ids]

    def difference(self, j: int, d: float, tol: float) -> str:
        prep, a, b = self.prep, self.a, self.b
        if abs(d) <= tol:
            return f"{self.names[a]} and {self.names[b]} measure the same"
        ahead, behind = (a, b) if d > 0 else (b, a)
        entry = prep.criteria[j]
        leaf = prep.leaf_ids[j]
        if entry.coding is not None:
            raw = prep.project.performance_index()
            label_ahead = raw[(prep.alt_ids[ahead], leaf)]
            label_behind = raw[(prep.alt_ids[behind], leaf)]
            return (
                f"{self.names[ahead]} is {label_ahead} and {self.names[behind]} is "
                f"{label_behind}, {abs(d):.6g} apart in codes"
            )
        scale = prep.project.tree().node(leaf).scale
        unit = f" {scale.unit}" if scale is not None and scale.unit else ""
        more = "higher" if entry.direction == "maximise" else "lower"
        return f"{self.names[ahead]} is {abs(d):.6g}{unit} {more}"


def _zone_phrase(row: CriterionExplanation, function: object) -> str:
    q, p = row.q, row.p
    if row.zone == "no_preference":
        return f"within q = {q:.6g}, so PROMETHEE counts no preference" if q else "no preference"
    if row.zone == "partial":
        return (
            f"between q = {q or 0:.6g} and p = {p:.6g}, so PROMETHEE counts "
            f"{row.preference_degree:.3g} of full preference"
        )
    if isinstance(function, UsualFunction):
        return "and the usual function counts any difference as full preference"
    if isinstance(function, UShapeFunction):
        return f"beyond q = {q:.6g}, so PROMETHEE counts full preference and no more"
    if row.capped:
        return f"beyond p = {p:.6g}, so PROMETHEE counts full preference and no more"
    return f"at p = {p:.6g}, so PROMETHEE counts full preference"


def _reasons(
    prep: PreparedPromethee, phrases: _Pair, rows: list[CriterionExplanation], texts: list[str]
) -> list[str]:
    """At most three: the criteria that favour b most in PROMETHEE, interleaved with those where
    a's MAVT advantage is reduced because the difference lies within q or beyond full preference."""
    a_name, b_name = phrases.names[phrases.a], phrases.names[phrases.b]
    a_id = prep.alt_ids[phrases.a]
    against = sorted(
        (j for j, r in enumerate(rows) if r.promethee_contribution < -TIE_TOL),
        key=lambda j: (rows[j].promethee_contribution, j),
    )
    reduced = sorted(
        (
            j
            for j, r in enumerate(rows)
            if r.mavt_contribution > TIE_TOL
            and r.favours == a_id
            and (r.zone == "no_preference" or r.capped)
        ),
        key=lambda j: (-rows[j].mavt_contribution, j),
    )
    candidates: list[tuple[int, str]] = []
    for k in range(max(len(against), len(reduced))):
        if k < len(against):
            j = against[k]
            r = rows[j]
            candidates.append(
                (
                    j,
                    f"{r.name}: favours {b_name} in PROMETHEE "
                    f"({r.promethee_contribution:+.3g} of the flow gap); {texts[j]}.",
                )
            )
        if k < len(reduced):
            j = reduced[k]
            r = rows[j]
            candidates.append(
                (
                    j,
                    f"{r.name}: MAVT's advantage for {a_name} ({r.mavt_contribution:+.3g} value) "
                    f"is reduced; {texts[j]}.",
                )
            )
    seen: set[int] = set()
    out: list[str] = []
    for j, text in candidates:
        if j not in seen and len(out) < MAX_REASONS:
            seen.add(j)
            out.append(text)
    return out


def _criteria(
    prep: PreparedPromethee, flows: Flows, mavt: MavtResult, a: int, b: int
) -> tuple[list[CriterionExplanation], list[str]]:
    others = len(prep.alt_ids) - 1
    a_id, b_id = prep.alt_ids[a], prep.alt_ids[b]
    contributions = {d.alternative_id: d.weighted_contributions for d in mavt.alternatives}
    phrases = _Pair(prep, a, b)
    rows: list[CriterionExplanation] = []
    texts: list[str] = []
    for j, leaf in enumerate(prep.leaf_ids):
        function = prep.criteria[j].function
        d = prep.difference(j, a, b)
        tol = prep.tolerance(j, a, b)
        degree = preference_degree(function, abs(d), tol)
        zone = _zone(degree)
        q, p = thresholds(function)
        w = prep.weights[j]
        degrees = prep.degrees[j]
        row = CriterionExplanation(
            criterion_id=leaf,
            name=prep.project.tree().node(leaf).name,
            difference=d,
            favours=a_id if d > tol else b_id if d < -tol else None,
            zone=zone,
            preference_degree=degree,
            capped=zone == "full" and (p is None or abs(d) > p + tol),
            q=q,
            p=p,
            promethee_contribution=w * (flows.criterion[j][a] - flows.criterion[j][b]),
            promethee_head_to_head=w * 2 * (degrees[a][b] - degrees[b][a]) / others,
            mavt_contribution=contributions[a_id][leaf] - contributions[b_id][leaf],
        )
        rows.append(row)
        texts.append(f"{phrases.difference(j, d, tol)}, {_zone_phrase(row, function)}")
    return rows, _reasons(prep, phrases, rows, texts)


def explain(
    prep: PreparedPromethee, flows: Flows
) -> tuple[OutrankingExplanation, Id | None, Id | None, list[Issue]]:
    """The explanation, the MAVT side's profile and scenario ids, and diagnostics."""
    project, configuration = prep.project, prep.configuration
    try:
        scenario = project.resolve_scenario(configuration)
        profile = project.resolve_profile(configuration)
    except UnknownReferenceError:
        scenario, profile = None, None
    scenario_id = scenario.id if scenario else None
    profile_id = profile.id if profile else None
    mavt, reason, codes = _mavt_side(prep)
    if mavt is None:
        note = Issue(
            severity=Severity.INFO,
            code="EXPLANATION_UNAVAILABLE",
            message=f"{reason}" + (f" ({', '.join(codes)})" if codes else ""),
            path="explanation",
        )
        return (
            OutrankingExplanation(
                available=False,
                unavailable_reason=reason,
                unavailable_codes=codes,
                detail_limit=DETAIL_LIMIT,
                ranks=[],
                pairs=[],
            ),
            profile_id,
            scenario_id,
            [note],
        )
    ids = prep.alt_ids
    n = len(ids)
    others = n - 1
    by_id = {d.alternative_id: d for d in mavt.alternatives}
    mavt_rank = [by_id[i].rank for i in ids]
    value = [by_id[i].overall_value for i in ids]
    rank = flows.ranks
    oriented: list[tuple[int, int]] = []
    for i in range(n):
        for k in range(i + 1, n):
            by_value, by_flow = _sign(mavt_rank[k] - mavt_rank[i]), _sign(rank[k] - rank[i])
            if by_value == by_flow:
                continue
            ahead = by_value > 0 or (by_value == 0 and by_flow < 0)
            oriented.append((i, k) if ahead else (k, i))

    def change(x: int) -> int:
        return abs(rank[x] - mavt_rank[x])

    oriented.sort(
        key=lambda p: (-max(change(p[0]), change(p[1])), mavt_rank[p[0]], mavt_rank[p[1]], p)
    )
    pairs: list[PairExplanation] = []
    for position, (a, b) in enumerate(oriented):
        detailed = position < DETAIL_LIMIT
        flow_gap = flows.net[a] - flows.net[b]
        head_to_head = 2 * (flows.preference[a][b] - flows.preference[b][a]) / others
        rows, reasons = _criteria(prep, flows, mavt, a, b) if detailed else ([], [])
        pairs.append(
            PairExplanation(
                alternative_a=ids[a],
                alternative_b=ids[b],
                mavt_rank_a=mavt_rank[a],
                mavt_rank_b=mavt_rank[b],
                promethee_rank_a=rank[a],
                promethee_rank_b=rank[b],
                value_gap=value[a] - value[b],
                flow_gap=flow_gap,
                head_to_head=head_to_head,
                via_others=flow_gap - head_to_head,
                detailed=detailed,
                criteria=rows,
                reasons=reasons,
            )
        )
    notes: list[Issue] = []
    if len(pairs) > DETAIL_LIMIT:
        notes.append(
            Issue(
                severity=Severity.INFO,
                code="EXPLANATION_LIMITED",
                message=f"{len(pairs)} pairs are ordered differently; criterion detail and "
                f"reasons are given for the first {DETAIL_LIMIT}, the others list their gaps only",
                path="explanation",
            )
        )
    order = sorted(range(n), key=lambda i: (-flows.net[i], i))
    ranks = [
        RankComparison(
            alternative_id=ids[i],
            name=prep.names[ids[i]],
            mavt_rank=mavt_rank[i],
            promethee_rank=rank[i],
        )
        for i in order
    ]
    explanation = OutrankingExplanation(
        available=True,
        unavailable_reason=None,
        unavailable_codes=[],
        detail_limit=DETAIL_LIMIT,
        ranks=ranks,
        pairs=pairs,
    )
    return explanation, profile_id, scenario_id, notes
