"""PROMETHEE II over raw measurements: the result with its flows, the PROMETHEE I partial order
and the explanation against MAVT (design note §3)."""

from mcda_studio.domain.common import Issue, Severity
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import (
    AlternativeFlows,
    PrometheeCriterionUsed,
    PrometheeResult,
    RankedAlternative,
)
from mcda_studio.methods.mavt.aggregation import ordered_indices
from mcda_studio.methods.promethee.explanation import explain
from mcda_studio.methods.promethee.flows import compute_flows, partial_order, prepare_promethee

PROMETHEE_ASSUMPTIONS = [
    "Net outranking flows compare the alternatives with one another: adding or removing an "
    "alternative can change every flow, and the order of two others. They are not preference "
    "values.",
    "Each criterion compares the measurements of every pair through its stated preference "
    "function; a difference at or beyond the full-preference point counts the same however large "
    "it is, so a large advantage on one criterion offsets others only up to that point.",
    "Weights are PROMETHEE's own importances, normalised by their sum; they are not swing "
    "weights, and value functions are not read.",
    "A labelled criterion is compared on its stated codes; its differences and thresholds are in "
    "coded units.",
    "Missing measurements are not imputed; the model must be complete to be evaluated.",
]


def run_promethee(project: Project, configuration: AnalysisConfiguration) -> PrometheeResult:
    prep = prepare_promethee(project, configuration)
    flows = compute_flows(prep)
    pairs = partial_order(prep, flows)
    order = ordered_indices(flows.net)
    names = prep.names
    diagnostics: list[Issue] = list(prep.warnings)
    tied = sorted({r for r in flows.ranks if flows.ranks.count(r) > 1})
    for r in tied:
        members = [names[prep.alt_ids[i]] for i, x in enumerate(flows.ranks) if x == r]
        diagnostics.append(
            Issue(
                severity=Severity.INFO,
                code="TIED_ALTERNATIVES",
                message=f"alternatives tied on net flow at rank {r}: {', '.join(members)}",
            )
        )
    incomparable = sum(1 for p in pairs if p.relation == "incomparable")
    if incomparable:
        diagnostics.append(
            Issue(
                severity=Severity.INFO,
                code="INCOMPARABLE_PAIRS",
                message=f"PROMETHEE I finds {incomparable} incomparable pair(s): the positive and "
                "negative flows disagree on their order, which the net flow hides",
            )
        )
    explanation, profile_id, scenario_id, notes = explain(prep, flows)
    diagnostics.extend(notes)
    leaf_names = {leaf: prep.project.tree().node(leaf).name for leaf in prep.leaf_ids}
    scales = {leaf: prep.project.tree().node(leaf).scale for leaf in prep.leaf_ids}
    return PrometheeResult(
        schema_version=project.required_schema_version(),
        project_id=project.id,
        project_fingerprint=project.fingerprint(),
        configuration=configuration,
        weight_profile_id=profile_id,
        scenario_id=scenario_id,
        ranking=[
            RankedAlternative(
                alternative_id=prep.alt_ids[i],
                name=names[prep.alt_ids[i]],
                value=flows.net[i],
                rank=flows.ranks[i],
            )
            for i in order
        ],
        diagnostics=diagnostics,
        assumptions=list(PROMETHEE_ASSUMPTIONS),
        leaf_order=prep.leaf_ids,
        criteria=[
            PrometheeCriterionUsed(
                criterion_id=leaf,
                name=leaf_names[leaf],
                unit=scale.unit if scale is not None and scale.is_numeric else None,
                direction=entry.direction,
                weight=entry.weight,
                normalised_weight=prep.weights[j],
                function=entry.function.model_copy(deep=True),
                coding=dict(entry.coding) if entry.coding is not None else None,
            )
            for j, (leaf, entry) in enumerate(zip(prep.leaf_ids, prep.criteria, strict=True))
            for scale in [scales[leaf]]
        ],
        flows=[
            AlternativeFlows(
                alternative_id=prep.alt_ids[i],
                name=names[prep.alt_ids[i]],
                rank=flows.ranks[i],
                positive_flow=flows.positive[i],
                negative_flow=flows.negative[i],
                net_flow=flows.net[i],
                criterion_flows={
                    leaf: flows.criterion[j][i] for j, leaf in enumerate(prep.leaf_ids)
                },
            )
            for i in order
        ],
        preference_matrix={
            a: {b: flows.preference[i][k] for k, b in enumerate(prep.alt_ids)}
            for i, a in enumerate(prep.alt_ids)
        },
        partial_order=pairs,
        explanation=explanation,
    )
