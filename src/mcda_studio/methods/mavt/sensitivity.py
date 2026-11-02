"""One-way weight sensitivity and scenario comparison for additive MAVT.

Key fact used for exact crossovers
----------------------------------
Replace the local weight of node k (among its siblings) by t and rescale the other siblings
proportionally:  lambda_i(t) = (1 - t)/(1 - lambda_k) * lambda_i.  Every global leaf weight is a
product of local weights along a path, and each path contains *at most one* sibling of the
affected group, so each global weight is an affine function of t. Partial values do not depend
on t, hence every overall value V_a(t) is affine in t, and the difference of two alternatives,
D_ab(t) = V_a(t) - V_b(t), is affine too. Its root is therefore known in closed form from the
endpoints t=0 and t=1; no grid search or iteration is needed (tests cross-check with brentq).
"""

import math

import numpy as np
from numpy.typing import NDArray

from mcda_studio.domain.common import Issue, Severity
from mcda_studio.domain.errors import ModelStructureError, SensitivityError
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.previews import AlternativeProbe, SensitivityProbe
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import (
    Crossover,
    MavtResult,
    ScenarioComparison,
    ScenarioOutcome,
    SensitivityResult,
    WinnerChange,
)
from mcda_studio.methods.mavt.aggregation import (
    PreparedMavt,
    build_mavt_result,
    ordered_indices,
    overall_values,
    prepare_mavt,
    rank_values,
)
from mcda_studio.methods.mavt.weighting import global_weights, path_shares

_EPS = 1e-12


def _varied_local(prep: PreparedMavt, node_id: str, t: float) -> dict[str, float]:
    """Local weights with ``node_id`` set to ``t`` and its siblings rescaled proportionally.

    The one implementation of the redistribution rule: the sweep, the exact crossovers and the
    probe all read it, so the numbers the GUI shows are the ones the scores were computed from.

    The rest of the group is *summed*, not computed as ``1 - wk``: when wk is close to 1 that
    subtraction cancels catastrophically (wk = 0.99997 loses ~4 digits and the weights summed to
    1 + 1e-12). Summing keeps  t + (1 - t) * sum(siblings) / rest  equal to 1 to rounding error.
    """
    parent = prep.tree.node(node_id).parent_id
    siblings = [s for s in prep.tree.child_ids(parent) if s != node_id]
    rest = math.fsum(prep.local[s] for s in siblings)
    local = dict(prep.local)
    local[node_id] = t
    for sib in siblings:
        local[sib] = (1.0 - t) * prep.local[sib] / rest
    return local


def _global_with(prep: PreparedMavt, node_id: str, t: float) -> NDArray[np.float64]:
    g = global_weights(prep.tree, _varied_local(prep, node_id, t))
    return np.array([g[leaf] for leaf in prep.leaf_ids], dtype=float)


def endpoint_values(
    prep: PreparedMavt, node_id: str
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Overall values at t = 0 and t = 1; every V_a(t) is the affine line between them."""
    return prep.partial @ _global_with(prep, node_id, 0.0), prep.partial @ _global_with(
        prep, node_id, 1.0
    )


def _dedupe(points: list[float]) -> list[float]:
    out: list[float] = []
    for p in sorted(points):
        if not out or p - out[-1] > _EPS:
            out.append(p)
    return out


def weight_sensitivity(
    project: Project,
    configuration: AnalysisConfiguration | None,
    node_id: str,
    steps: int = 101,
) -> SensitivityResult:
    """Vary the local weight of ``node_id`` over [0, 1]; report values, rankings and crossovers.

    Works for a parent node (parent-weight sensitivity) and for a leaf (local-weight
    sensitivity) alike. Raises SensitivityError if the proportional redistribution is undefined.
    """
    if steps < 2:
        raise SensitivityError("steps must be at least 2")
    prep = prepare_mavt(project, configuration or project.analysis)
    base = _check_variable(prep, node_id)

    alts = prep.alt_ids
    n = len(alts)
    p = prep.partial
    w_base = prep.global_vector()
    v_base = overall_values(p, w_base)
    baseline_order = ordered_indices(v_base)
    baseline_ranking = [alts[i] for i in baseline_order]

    # Keep the exact baseline even when tolerance-deduplication coalesces a nearby grid point.
    grid = sorted(set(_dedupe([i / (steps - 1) for i in range(steps)]) + [base]))
    values = np.zeros((n, len(grid)))
    rankings: list[list[str]] = []
    for g, t in enumerate(grid):
        v = p @ _global_with(prep, node_id, t)
        values[:, g] = v
        rankings.append([alts[i] for i in ordered_indices(list(v))])

    # exact endpoint values -> affine V_a(t) = V0_a + t (V1_a - V0_a)
    v0, v1 = endpoint_values(prep, node_id)

    crossovers: list[Crossover] = []
    for i in range(n):
        for k in range(i + 1, n):
            d0 = float(v0[i] - v0[k])
            d1 = float(v1[i] - v1[k])
            if (d0 > _EPS and d1 < -_EPS) or (d0 < -_EPS and d1 > _EPS):
                t_star = d0 / (d0 - d1)
                if _EPS < t_star < 1.0 - _EPS:
                    before, after = (alts[i], alts[k]) if d0 > 0 else (alts[k], alts[i])
                    crossovers.append(
                        Crossover(
                            alternative_a=alts[i],
                            alternative_b=alts[k],
                            weight=t_star,
                            leader_before=before,
                            leader_after=after,
                        )
                    )
    crossovers.sort(key=lambda c: c.weight)
    breakpoints = _dedupe([c.weight for c in crossovers])

    # winner of each interval between breakpoints (rankings are constant inside an interval)
    edges = [0.0, *breakpoints, 1.0]
    intervals = list(zip(edges[:-1], edges[1:], strict=True))
    rank_pos = {a: r for r, a in enumerate(baseline_ranking)}

    def leader(t: float) -> str:
        v = v0 + t * (v1 - v0)
        best = max(v)
        tied = [alts[i] for i in range(n) if v[i] >= best - _EPS]
        return min(tied, key=lambda a: rank_pos[a])

    leaders = [leader((lo + hi) / 2) for lo, hi in intervals]
    base_winner = baseline_ranking[0]

    up: WinnerChange | None = None
    for (lo, _hi), who in zip(intervals, leaders, strict=True):
        if lo >= base - _EPS and who != base_winner:
            up = WinnerChange(weight=lo, from_winner=base_winner, to_winner=who)
            break
    down: WinnerChange | None = None
    for (_lo, hi), who in reversed(list(zip(intervals, leaders, strict=True))):
        if hi <= base + _EPS and who != base_winner:
            down = WinnerChange(weight=hi, from_winner=base_winner, to_winner=who)
            break

    on_breakpoint = any(abs(b - base) <= _EPS for b in breakpoints)
    below = [b for b in breakpoints if b < base - _EPS]
    above = [b for b in breakpoints if b > base + _EPS]
    stable = (base, base) if on_breakpoint else (max(below, default=0.0), min(above, default=1.0))
    winner_stable = (down.weight if down else 0.0, up.weight if up else 1.0)

    diagnostics: list[Issue] = []
    if on_breakpoint:
        diagnostics.append(
            Issue(
                severity=Severity.WARNING,
                code="BASELINE_ON_CROSSOVER",
                message="baseline weight is exactly at a crossover: alternatives are tied there",
            )
        )
    return SensitivityResult(
        node_id=node_id,
        node_name=prep.tree.node(node_id).name,
        base_weight=base,
        baseline_ranking=baseline_ranking,
        baseline_values={a: v_base[i] for i, a in enumerate(alts)},
        grid=grid,
        values={a: [float(x) for x in values[i]] for i, a in enumerate(alts)},
        rankings=rankings,
        crossovers=crossovers,
        rank_change_points=breakpoints,
        first_winner_change_up=up,
        first_winner_change_down=down,
        ranking_stable_range=stable,
        winner_stable_range=winner_stable,
        diagnostics=diagnostics,
    )


def _check_variable(prep: PreparedMavt, node_id: str) -> float:
    """Shared eligibility rules, so the probe and the sweep can never disagree."""
    if node_id not in prep.tree:
        raise SensitivityError(f"unknown criterion {node_id!r}")
    parent = prep.tree.node(node_id).parent_id
    if len(prep.tree.child_ids(parent)) < 2:
        raise SensitivityError(
            f"{node_id!r} has no siblings, so its local weight is fixed at 1 and cannot vary"
        )
    base = prep.local[node_id]
    if base >= 1.0 - _EPS:
        raise SensitivityError(
            f"{node_id!r} already has local weight 1 (all sibling ratings are zero), so the "
            "proportional redistribution of the others is undefined"
        )
    return float(base)


def sensitivity_probe(
    project: Project,
    configuration: AnalysisConfiguration | None,
    node_id: str,
    weight: float,
) -> SensitivityProbe:
    """Exact scores and competition ranks at one arbitrary local weight in [0, 1].

    This is the read-only companion to ``weight_sensitivity``: it answers "what would the model
    say at exactly this weight", including at a crossover, without the caller interpolating
    between grid points or deriving ranks from sort positions. It never touches the project.
    """
    if not math.isfinite(weight) or not 0.0 <= weight <= 1.0:
        raise SensitivityError(f"weight {weight!r} must be a finite number in [0, 1]")
    cfg = configuration or project.analysis
    prep = prepare_mavt(project, cfg)
    base = _check_variable(prep, node_id)

    alts = prep.alt_ids
    v_base = overall_values(prep.partial, prep.global_vector())
    base_ranks = rank_values(v_base)
    values = overall_values(prep.partial, _global_with(prep, node_id, weight))
    ranks = rank_values(values)
    order = ordered_indices(values)
    ranking = [alts[i] for i in order]
    baseline_ranking = [alts[i] for i in ordered_indices(v_base)]

    local = _varied_local(prep, node_id, weight)
    g = global_weights(prep.tree, local)
    names = {a.id: a.name for a in project.alternatives}

    diagnostics: list[Issue] = []
    if any(ranks.count(r) > 1 for r in ranks):
        diagnostics.append(
            Issue(
                severity=Severity.INFO,
                code="TIED_ALTERNATIVES",
                message=(
                    "alternatives are tied at this weight within the engine's ranking tolerance; "
                    "tied alternatives share a competition rank"
                ),
            )
        )
    if abs(weight - base) <= _EPS:
        diagnostics.append(
            Issue(
                severity=Severity.INFO,
                code="PROBE_AT_BASELINE",
                message="the probed weight is the criterion's current local weight",
            )
        )
    return SensitivityProbe(
        project_fingerprint=project.fingerprint(),
        configuration=cfg,
        weight_profile_id=prep.profile.id,
        scenario_id=prep.scenario.id if prep.scenario else None,
        node_id=node_id,
        node_name=prep.tree.node(node_id).name,
        node_path=prep.tree.path(node_id),
        weight=float(weight),
        base_weight=base,
        local_weights={s: local[s] for s in prep.tree.child_ids(prep.tree.node(node_id).parent_id)},
        global_weights=g,
        path_shares=path_shares(prep.tree, local),
        alternatives=[
            AlternativeProbe(
                alternative_id=alts[i],
                name=names.get(alts[i], alts[i]),
                value=values[i],
                rank=ranks[i],
                baseline_value=v_base[i],
                baseline_rank=base_ranks[i],
            )
            for i in order
        ],
        ranking=ranking,
        baseline_ranking=baseline_ranking,
        ranking_differs_from_baseline=ranks != base_ranks,
        winner_differs_from_baseline={alts[i] for i, rank in enumerate(ranks) if rank == 1}
        != {alts[i] for i, rank in enumerate(base_ranks) if rank == 1},
        diagnostics=diagnostics,
    )


def sensitivity_all(
    project: Project, configuration: AnalysisConfiguration | None = None, steps: int = 101
) -> list[SensitivityResult]:
    """Sensitivity for every node that has at least one sibling with a non-degenerate weight."""
    prep = prepare_mavt(project, configuration or project.analysis)
    out: list[SensitivityResult] = []
    for node_id in prep.tree.all_ids():
        parent = prep.tree.node(node_id).parent_id
        if len(prep.tree.child_ids(parent)) >= 2 and prep.local[node_id] < 1.0 - _EPS:
            out.append(weight_sensitivity(project, configuration, node_id, steps))
    return out


def comparison_from_results(
    project: Project,
    configuration: AnalysisConfiguration,
    baseline_result: MavtResult,
    scenario_results: list[MavtResult],
) -> ScenarioComparison:
    """Assemble the existing comparison contract from completed, context-checked evaluations."""
    base_cfg = configuration.model_copy(update={"scenario_id": None})
    fingerprint = project.fingerprint()

    def outcome(result: MavtResult, ref: ScenarioOutcome | None) -> ScenarioOutcome:
        cfg = result.configuration
        expected = base_cfg.model_copy(update={"scenario_id": result.scenario_id})
        if result.project_fingerprint != fingerprint or cfg != expected:
            raise ModelStructureError("comparison results belong to different model contexts")
        values = {a.alternative_id: a.value for a in result.ranking}
        ranks = {a.alternative_id: a.rank for a in result.ranking}
        scenario = project.resolve_scenario(cfg)
        winners = {a for a, rank in ranks.items() if rank == 1}
        reference_winners = (
            {a for a, rank in ref.rank_by_alternative.items() if rank == 1} if ref else winners
        )
        return ScenarioOutcome(
            scenario_id=cfg.scenario_id,
            scenario_name=scenario.name if scenario else "baseline",
            configuration=cfg.model_copy(deep=True),
            weight_profile_id=result.weight_profile_id,
            applied_overrides={
                k: v.model_copy(deep=True) for k, v in scenario.value_function_overrides.items()
            }
            if scenario
            else {},
            resolved_domains=result.resolved_domains,
            diagnostics=result.diagnostics,
            ranking=[a.alternative_id for a in result.ranking],
            values=values,
            rank_by_alternative=ranks,
            delta_from_baseline={
                a: value - ref.values[a] if ref else 0.0 for a, value in values.items()
            },
            ranking_differs_from_baseline=ref is not None and ranks != ref.rank_by_alternative,
            winner_differs_from_baseline=ref is not None and winners != reference_winners,
        )

    if baseline_result.scenario_id is not None:
        raise ModelStructureError("comparison baseline must explicitly clear the scenario")
    baseline = outcome(baseline_result, None)
    results = [outcome(result, baseline) for result in scenario_results]
    return ScenarioComparison(
        project_fingerprint=fingerprint,
        configuration=configuration.model_copy(deep=True),
        scenario_ids=[result.scenario_id for result in scenario_results if result.scenario_id],
        baseline=baseline,
        scenarios=results,
    )


def compare_scenarios(
    project: Project,
    scenario_ids: list[str] | None = None,
    configuration: AnalysisConfiguration | None = None,
) -> ScenarioComparison:
    """Evaluate the baseline and each scenario; report where the ranking or winner changes."""
    cfg = configuration or project.analysis
    base_cfg = cfg.model_copy(update={"scenario_id": None})
    ids = scenario_ids if scenario_ids is not None else [s.id for s in project.scenarios]
    baseline = build_mavt_result(prepare_mavt(project, base_cfg))
    results = []
    for sid in ids:
        if not any(s.id == sid for s in project.scenarios):
            raise SensitivityError(f"unknown scenario {sid!r}")
        results.append(
            build_mavt_result(
                prepare_mavt(project, base_cfg.model_copy(update={"scenario_id": sid}))
            )
        )
    return comparison_from_results(project, cfg, baseline, results)
