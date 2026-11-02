"""Additive MAVT:  V(a) = sum_j w_j * v_j(z_j(a))."""

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from mcda_studio.domain.common import Issue, Severity
from mcda_studio.domain.criteria import CriterionTree
from mcda_studio.domain.errors import ValidationFailed
from mcda_studio.domain.measurements import Domain, Measurement, effective_domain
from mcda_studio.domain.preferences import AnalysisConfiguration, Scenario, WeightProfile
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import (
    AlternativeDetail,
    DominancePair,
    MavtResult,
    RankedAlternative,
)
from mcda_studio.domain.scales import AnchorMode
from mcda_studio.methods.base import validate_analysis
from mcda_studio.methods.mavt.parameters import mavt_parameters
from mcda_studio.methods.mavt.value_functions import build_evaluator
from mcda_studio.methods.mavt.weighting import WEIGHT_BASIS, compute_weights

TIE_TOL = 1e-12

ASSUMPTIONS = [
    "Additive aggregation: a poor score on one criterion can be fully compensated by a good "
    "score on another (compensatory model).",
    "Preferential independence: preferences on one criterion do not depend on the levels of "
    "the others, so an additive form is appropriate.",
    "Partial values are normalised to [0, 1] over the stated scale range; weights are swing "
    "weights over those same ranges.",
    "Missing measurements are not imputed; the model must be complete to be evaluated.",
]


@dataclass(frozen=True)
class PreparedMavt:
    """Everything derived from the project before the final weighted sum."""

    project: Project
    configuration: AnalysisConfiguration
    profile: WeightProfile
    scenario: Scenario | None
    tree: CriterionTree
    alt_ids: list[str]
    leaf_ids: list[str]
    partial: NDArray[np.float64]  # shape (alternatives, leaves)
    raw: dict[tuple[str, str], Measurement]
    local: dict[str, float]
    global_: dict[str, float]
    domains: dict[str, Domain | None]
    clamped: set[tuple[str, str]]
    warnings: list[Issue]

    def global_vector(self) -> NDArray[np.float64]:
        return np.array([self.global_[leaf] for leaf in self.leaf_ids], dtype=float)


def rank_values(values: list[float], tol: float = TIE_TOL) -> list[int]:
    """Competition ranking (1 = best); values within ``tol`` share a rank."""
    return [1 + sum(1 for other in values if other > v + tol) for v in values]


def ordered_indices(values: list[float]) -> list[int]:
    """Indices best-first; ties keep the project's alternative order (stable)."""
    return sorted(range(len(values)), key=lambda i: (-values[i], i))


def overall_values(partial: NDArray[np.float64], weights: NDArray[np.float64]) -> list[float]:
    return [
        math.fsum(float(w) * float(v) for w, v in zip(weights, row, strict=True)) for row in partial
    ]


def prepare_mavt(project: Project, configuration: AnalysisConfiguration) -> PreparedMavt:
    report = validate_analysis(project, configuration)
    if not report.ok:
        raise ValidationFailed(report)
    profile = project.resolve_profile(configuration)
    assert profile is not None  # guaranteed by validation (NO_WEIGHT_PROFILE)
    scenario = project.resolve_scenario(configuration)
    tree = project.tree()
    weights = compute_weights(tree, profile.judgements)
    alt_ids = project.alternative_ids()
    leaf_ids = tree.leaves()
    raw = project.performance_index()

    partial = np.zeros((len(alt_ids), len(leaf_ids)), dtype=float)
    domains: dict[str, Domain | None] = {}
    clamped: set[tuple[str, str]] = set()
    for j, leaf in enumerate(leaf_ids):
        node = tree.node(leaf)
        assert node.scale is not None
        vf = (
            scenario.value_function_overrides.get(leaf, node.value_function)
            if scenario
            else node.value_function
        )
        assert vf is not None  # effective-model validation includes the selected override
        observed = (
            [float(raw[(a, leaf)]) for a in alt_ids]
            if node.scale.is_numeric and node.scale.anchor_mode is AnchorMode.LOCAL
            else []
        )
        domain = effective_domain(node.scale, vf, observed)
        domains[leaf] = domain
        evaluator = build_evaluator(vf, domain)
        for i, alt in enumerate(alt_ids):
            value, was_clamped = evaluator(raw[(alt, leaf)])
            partial[i, j] = value
            if was_clamped:
                clamped.add((alt, leaf))
    return PreparedMavt(
        project=project,
        configuration=configuration,
        profile=profile,
        scenario=scenario,
        tree=tree,
        alt_ids=alt_ids,
        leaf_ids=leaf_ids,
        partial=partial,
        raw=raw,
        local=weights.local,
        global_=weights.global_,
        domains=domains,
        clamped=clamped,
        warnings=report.warnings,
    )


def _dominance(prep: PreparedMavt) -> list[DominancePair]:
    out: list[DominancePair] = []
    p = prep.partial
    for i, a in enumerate(prep.alt_ids):
        for k, b in enumerate(prep.alt_ids):
            if i != k and np.all(p[i] >= p[k] - TIE_TOL) and np.any(p[i] > p[k] + TIE_TOL):
                out.append(DominancePair(dominator_id=a, dominated_id=b))
    return out


def build_mavt_result(prep: PreparedMavt) -> MavtResult:
    project = prep.project
    names = {a.id: a.name for a in project.alternatives}
    w = prep.global_vector()
    values = overall_values(prep.partial, w)
    ranks = rank_values(values)
    order = ordered_indices(values)

    diagnostics: list[Issue] = list(prep.warnings)
    for alt, leaf in sorted(prep.clamped):
        diagnostics.append(
            Issue(
                severity=Severity.WARNING,
                code="CLAMPED_MEASUREMENT",
                message=f"{alt!r} on {leaf!r} was clamped to the domain",
                path=f"performances[{alt},{leaf}]",
            )
        )
    tied = sorted({ranks[i] for i in range(len(ranks)) if ranks.count(ranks[i]) > 1})
    for r in tied:
        members = [names[prep.alt_ids[i]] for i in range(len(ranks)) if ranks[i] == r]
        diagnostics.append(
            Issue(
                severity=Severity.INFO,
                code="TIED_ALTERNATIVES",
                message=f"alternatives tied at rank {r}: {', '.join(members)}",
            )
        )
    dominance = _dominance(prep) if mavt_parameters(prep.configuration).dominance_check else []
    for d in dominance:
        diagnostics.append(
            Issue(
                severity=Severity.INFO,
                code="DOMINANCE",
                message=f"{names[d.dominator_id]} dominates {names[d.dominated_id]} "
                "(at least as good on every criterion, better on one)",
            )
        )

    details: list[AlternativeDetail] = []
    for i in order:
        alt = prep.alt_ids[i]
        details.append(
            AlternativeDetail(
                alternative_id=alt,
                name=names[alt],
                rank=ranks[i],
                overall_value=values[i],
                raw_measurements={leaf: prep.raw[(alt, leaf)] for leaf in prep.leaf_ids},
                partial_values={
                    leaf: float(prep.partial[i, j]) for j, leaf in enumerate(prep.leaf_ids)
                },
                weighted_contributions={
                    leaf: float(w[j]) * float(prep.partial[i, j])
                    for j, leaf in enumerate(prep.leaf_ids)
                },
                clamped_criteria=[leaf for leaf in prep.leaf_ids if (alt, leaf) in prep.clamped],
            )
        )
    return MavtResult(
        schema_version=project.required_schema_version(),
        project_id=project.id,
        project_fingerprint=project.fingerprint(),
        configuration=prep.configuration,
        weight_profile_id=prep.profile.id,
        scenario_id=prep.scenario.id if prep.scenario else None,
        ranking=[
            RankedAlternative(
                alternative_id=prep.alt_ids[i],
                name=names[prep.alt_ids[i]],
                value=values[i],
                rank=ranks[i],
            )
            for i in order
        ],
        diagnostics=diagnostics,
        assumptions=list(ASSUMPTIONS),
        leaf_order=prep.leaf_ids,
        local_weights=prep.local,
        global_weights=prep.global_,
        resolved_domains=prep.domains,
        weight_basis=WEIGHT_BASIS,
        alternatives=details,
        dominance=dominance,
    )


def evaluate_mavt(
    project: Project, configuration: AnalysisConfiguration | None = None
) -> MavtResult:
    """One call: validate, weight, score, rank, and return the full inspectable record."""
    return build_mavt_result(prepare_mavt(project, configuration or project.analysis))
