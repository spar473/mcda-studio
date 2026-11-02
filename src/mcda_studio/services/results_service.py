"""One completed engine result, contextual explanations and reproducible, read-only downloads."""

import csv
import hashlib
import io
import json
import math
import unicodedata
from collections.abc import Callable, Iterable
from typing import Any, Literal

from mcda_studio.domain.analysis_record import (
    AhpAnalysisRecord,
    AnalysisExportDocument,
    AnalysisExportDocumentV2,
    AnalysisPresentation,
    AnalysisRecord,
    CriterionContext,
    DominanceRelation,
    ExportTable,
    PrometheeAnalysisRecord,
    SmaaAnalysisRecord,
    SortingAnalysisRecord,
)
from mcda_studio.domain.common import Issue, Severity
from mcda_studio.domain.errors import (
    AnalysisExportError,
    AnalysisLimitError,
    McdaError,
    StaleRevisionError,
)
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import (
    CriterionExplanation,
    MavtResult,
    ValueModelResult,
)
from mcda_studio.methods.ahp.engine import run_ahp
from mcda_studio.methods.base import get_method, require_record_v1
from mcda_studio.methods.mavt.aggregation import (
    TIE_TOL,
    PreparedMavt,
    build_mavt_result,
    prepare_mavt,
)
from mcda_studio.methods.mavt.parameters import mavt_parameters
from mcda_studio.methods.mavt.sensitivity import comparison_from_results
from mcda_studio.methods.mavt.weighting import path_shares
from mcda_studio.methods.promethee.engine import run_promethee
from mcda_studio.methods.smaa.engine import run_smaa
from mcda_studio.methods.sorting.classes import build_sorting_result

AnyRecord = (
    AnalysisRecord
    | SortingAnalysisRecord
    | SmaaAnalysisRecord
    | PrometheeAnalysisRecord
    | AhpAnalysisRecord
)

#: The CSV tables each method can fill, in the order a client offers them.
EXPORT_TABLES: dict[str, tuple[ExportTable, ...]] = {
    "mavt": ("ranking", "contributions", "partial_values", "dominance", "comparison"),
    "mavt_sorting": (
        "ranking",
        "classes",
        "contributions",
        "partial_values",
        "dominance",
        "comparison",
    ),
    "smaa2": ("rank_acceptability", "class_acceptability", "inputs_to_check"),
    "promethee2": ("flows", "criterion_flows", "partial_order", "explanation"),
    "ahp": ("priorities", "criterion_priorities", "local_priorities", "consistency"),
}

MAX_ALTERNATIVES = 100
MAX_LEAVES = 100
MAX_NODES = 1000
MAX_CELLS = 10000
MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_EXPORT_BYTES = 16 * 1024 * 1024


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _limits(project: Project, configuration: AnalysisConfiguration) -> None:
    if len(project.alternatives) > MAX_ALTERNATIVES or len(project.criteria) > MAX_NODES:
        raise AnalysisLimitError(
            "Results workspace supports at most 100 alternatives and 1000 nodes."
        )
    leaves = project.tree().leaves()
    if len(leaves) > MAX_LEAVES or len(leaves) * len(project.alternatives) > MAX_CELLS:
        raise AnalysisLimitError(
            "Results workspace supports at most 100 leaves and 10000 data cells."
        )
    if len(project.performances) > MAX_CELLS:
        raise AnalysisLimitError("Too many performance entries for the bounded results workspace.")
    if len(project.model_dump_json().encode("utf-8")) > MAX_REQUEST_BYTES:
        raise AnalysisLimitError("Results project exceeds the 8 MiB request limit.")
    if len(configuration.model_dump_json().encode("utf-8")) > 4000:
        raise AnalysisLimitError("Analysis configuration exceeds the 4000-byte results limit.")
    labels = [project.title] + [a.name for a in project.alternatives]
    labels += [
        text
        for c in project.criteria
        for text in [c.name, c.description, c.scale.unit if c.scale and c.scale.unit else ""]
    ]
    labels += [p.name for p in project.weight_profiles] + [s.name for s in project.scenarios]
    if any(len(text) > 2000 for text in labels):
        raise AnalysisLimitError(
            "Results labels and descriptions must each be at most 2000 characters."
        )


def dominance_relations(
    result: ValueModelResult, ids: list[str], enabled: bool
) -> dict[str, dict[str, DominanceRelation]]:
    """Read the engine's dominance edges. Equality uses its same partial-value tolerance."""
    edges = {(pair.dominator_id, pair.dominated_id) for pair in result.dominance}
    partial = {a.alternative_id: a.partial_values for a in result.alternatives}
    matrix: dict[str, dict[str, DominanceRelation]] = {}
    for a in ids:
        row: dict[str, DominanceRelation] = {}
        for b in ids:
            if a == b:
                relation: DominanceRelation = "same_alternative"
            elif not enabled:
                relation = "not_checked"
            elif (a, b) in edges:
                relation = "dominates"
            elif (b, a) in edges:
                relation = "dominated_by"
            elif all(
                abs(partial[a][leaf] - partial[b][leaf]) <= TIE_TOL for leaf in result.leaf_order
            ):
                relation = "equal"
            else:
                relation = "incomparable"
            row[b] = relation
        matrix[a] = row
    return matrix


def _value_model_context(
    project: Project, cfg: AnalysisConfiguration, prep: PreparedMavt, result: MavtResult
) -> dict[str, Any]:
    """Criterion, weight, dominance and Base-comparison context that value-model records hold."""
    criteria = []
    for leaf in result.leaf_order:
        node = prep.tree.node(leaf)
        vf = (
            prep.scenario.value_function_overrides.get(leaf, node.value_function)
            if prep.scenario
            else node.value_function
        )
        assert node.scale is not None and vf is not None
        path = prep.tree.path(leaf)
        criteria.append(
            CriterionContext(
                criterion_id=leaf,
                name=node.name,
                description=node.description,
                path_ids=path,
                path_names=[prep.tree.node(i).name for i in path],
                scale=node.scale.model_copy(deep=True),
                value_function=vf.model_copy(deep=True),
                function_source="scenario_override"
                if prep.scenario and leaf in prep.scenario.value_function_overrides
                else "base",
                resolved_domain=result.resolved_domains[leaf],
            )
        )
    comparison = None
    comparison_diagnostics = []
    if cfg.scenario_id is not None:
        try:
            base_cfg = cfg.model_copy(update={"scenario_id": None})
            baseline = build_mavt_result(prepare_mavt(project, base_cfg))
            comparison = comparison_from_results(project, cfg, baseline, [result])
        except McdaError as exc:
            comparison_diagnostics.append(
                Issue(
                    severity=Severity.WARNING,
                    code="BASE_COMPARISON_UNAVAILABLE",
                    message=str(exc),
                    path="analysis",
                )
            )
    enabled = mavt_parameters(cfg).dominance_check
    return {
        "project_title": project.title,
        "scenario_name": prep.scenario.name if prep.scenario else "Base model",
        "resolved_profile_name": prep.profile.name,
        "numerical_tolerance": TIE_TOL,
        "alternative_order": [a.id for a in project.alternatives],
        "criteria": criteria,
        "path_shares": path_shares(prep.tree, prep.local),
        "contribution_totals": {
            a.alternative_id: math.fsum(a.weighted_contributions.values())
            for a in result.alternatives
        },
        "dominance_enabled": enabled,
        "dominance_relations": dominance_relations(
            result, [a.id for a in project.alternatives], enabled
        ),
        "comparison": comparison,
        "comparison_diagnostics": comparison_diagnostics,
    }


def _seal[
    R: (
        AnalysisRecord,
        SortingAnalysisRecord,
        SmaaAnalysisRecord,
        PrometheeAnalysisRecord,
        AhpAnalysisRecord,
    )
](record: R) -> R:
    """The digest is SHA-256 of the record's canonical JSON without the digest itself."""
    body = canonical_json(record.model_dump(mode="json", exclude={"record_digest"})).encode("utf-8")
    if len(body) > MAX_EXPORT_BYTES:
        raise AnalysisLimitError("Completed analysis exceeds the 16 MiB record limit.")
    record.record_digest = hashlib.sha256(body).hexdigest()
    return record


def _sorting_record(project: Project, cfg: AnalysisConfiguration) -> SortingAnalysisRecord:
    _limits(project, cfg)
    prep = prepare_mavt(project, cfg)  # validates through the sorting method
    base = build_mavt_result(prep)
    assert project.sorting is not None  # guaranteed by validation (NO_SORTING_MODEL)
    return _seal(
        SortingAnalysisRecord(
            record_digest="",
            method_label=get_method(cfg.method).label,
            configuration=cfg,
            result=build_sorting_result(base, project.sorting),
            **_value_model_context(project, cfg, prep, base),
        )
    )


def _smaa_record(project: Project, cfg: AnalysisConfiguration) -> SmaaAnalysisRecord:
    _limits(project, cfg)
    result = run_smaa(project, cfg)  # validates through the SMAA-2 method
    scenario = project.resolve_scenario(cfg)
    profile = project.resolve_profile(cfg)
    assert profile is not None  # guaranteed by validation (NO_WEIGHT_PROFILE)
    return _seal(
        SmaaAnalysisRecord(
            record_digest="",
            method_label=get_method(cfg.method).label,
            numerical_tolerance=TIE_TOL,
            project_title=project.title,
            scenario_name=scenario.name if scenario else "Base model",
            resolved_profile_name=profile.name,
            alternative_order=[a.id for a in project.alternatives],
            configuration=cfg,
            result=result,
        )
    )


def _promethee_record(project: Project, cfg: AnalysisConfiguration) -> PrometheeAnalysisRecord:
    _limits(project, cfg)
    result = run_promethee(project, cfg)  # validates through the PROMETHEE II method
    scenario = next((s for s in project.scenarios if s.id == result.scenario_id), None)
    profile = next((p for p in project.weight_profiles if p.id == result.weight_profile_id), None)
    return _seal(
        PrometheeAnalysisRecord(
            record_digest="",
            method_label=get_method(cfg.method).label,
            numerical_tolerance=TIE_TOL,
            project_title=project.title,
            scenario_name=scenario.name if scenario else "Base model",
            resolved_profile_name=profile.name if profile else "",
            alternative_order=[a.id for a in project.alternatives],
            configuration=cfg,
            result=result,
        )
    )


def _ahp_record(project: Project, cfg: AnalysisConfiguration) -> AhpAnalysisRecord:
    _limits(project, cfg)
    result = run_ahp(project, cfg)  # validates through the AHP method
    return _seal(
        AhpAnalysisRecord(
            record_digest="",
            method_label=get_method(cfg.method).label,
            numerical_tolerance=TIE_TOL,
            project_title=project.title,
            scenario_name="",  # AHP reads no scenario or weight profile
            resolved_profile_name="",
            alternative_order=[a.id for a in project.alternatives],
            configuration=cfg,
            result=result,
        )
    )


#: Methods whose completed analysis is a version-2 record, by name.
VERSION_2_RECORDS: dict[str, Callable[[Project, AnalysisConfiguration], AnyRecord]] = {
    "mavt_sorting": _sorting_record,
    "smaa2": _smaa_record,
    "promethee2": _promethee_record,
    "ahp": _ahp_record,
}


def analysis_record(
    project: Project, configuration: AnalysisConfiguration | None = None
) -> AnyRecord:
    cfg = (configuration or project.analysis).model_copy(deep=True)
    build_v2 = VERSION_2_RECORDS.get(cfg.method)
    if build_v2 is not None:
        return build_v2(project, cfg)
    require_record_v1(cfg)
    _limits(project, cfg)
    prep = prepare_mavt(project, cfg)
    result = build_mavt_result(prep)
    return _seal(
        AnalysisRecord(
            record_digest="", result=result, **_value_model_context(project, cfg, prep, result)
        )
    )


def safe_csv_text(value: str) -> str:
    """Visible control escapes and a durable literal prefix for non-alphanumeric-leading text.

    Quoting alone is not a formula defence. Never rewrite the stored string; JSON retains it.
    NFKC catches full-width formula prefixes. Prefix whitespace, quote and control-leading text too.
    """
    escaped = "".join(
        f"\\u{ord(c):04x}" if unicodedata.category(c).startswith("C") else c for c in value
    )
    normalized = unicodedata.normalize("NFKC", value)
    unsafe = bool(normalized) and not (normalized[0].isalnum() or normalized[0] == "_")
    return "TEXT:" + escaped if unsafe else escaped


def _cell(value: str | int | float | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return safe_csv_text(value)
    return str(value)  # trusted engine numbers retain Python's full round-trip precision


class _BoundedBuffer(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.byte_count = 0

    def write(self, value: str) -> int:
        self.byte_count += len(value.encode("utf-8"))
        if self.byte_count > MAX_EXPORT_BYTES:
            raise AnalysisLimitError("CSV export exceeds the 16 MiB download limit.")
        return super().write(value)


def _sorting_rows(
    record: SortingAnalysisRecord, table: ExportTable, order: list[str]
) -> tuple[list[str], Iterable[list[str | int | float | None]]]:
    """Sorting's own tables: the ranking with class columns, and one row per class."""
    result = record.result
    details = {a.alternative_id: a for a in result.alternatives}
    assigned = {a.alternative_id: a for a in result.assignments}
    names = {c.class_id: c.name for c in result.classes}
    sampled = set(result.audit_sample.alternative_ids) if result.audit_sample else set()
    if table == "ranking":
        return [
            "alternative_id",
            "alternative_name",
            "rank",
            "overall_value",
            "class_id",
            "class_name",
            "class_rank",
            "on_boundary",
            "nearest_boundary_class_id",
            "distance_to_nearest_boundary",
            "in_audit_sample",
        ], (
            [
                i,
                details[i].name,
                details[i].rank,
                details[i].overall_value,
                assigned[i].class_id,
                names[assigned[i].class_id],
                assigned[i].class_rank,
                str(assigned[i].on_boundary).lower(),
                assigned[i].nearest_boundary_class_id,
                assigned[i].distance_to_nearest_boundary,
                str(i in sampled).lower(),
            ]
            for i in order
        )
    audit = result.audit_sample
    cutoff = next(
        (c.rank for c in result.classes if audit and c.class_id == audit.below_class_id), None
    )
    return [
        "class_id",
        "class_name",
        "class_rank",
        "lower_boundary",
        "upper_boundary",
        "member_count",
        "member_ids",
        "in_audit_pool",
    ], (
        [
            c.class_id,
            c.name,
            c.rank,
            c.lower_boundary,
            c.upper_boundary,
            len(c.alternative_ids),
            canonical_json(c.alternative_ids),
            str(cutoff is not None and c.rank > cutoff).lower(),
        ]
        for c in result.classes
    )


def _smaa_rows(
    record: SmaaAnalysisRecord, table: ExportTable, order: list[str]
) -> tuple[list[str], Iterable[list[str | int | float | None]]]:
    """SMAA-2's tables. Every row carries the run's label through the context columns."""
    result = record.result
    rows = {a.alternative_id: a for a in result.acceptability}
    estimate = ["count", "frequency", "lower", "upper"]
    if table == "rank_acceptability":
        return ["alternative_id", "alternative_name", "event", "rank", *estimate], (
            [i, rows[i].name, event, rank, e.count, e.frequency, e.lower, e.upper]
            for i in order
            for event, rank, e in [
                *(("rank", r + 1, e) for r, e in enumerate(rows[i].ranks)),
                ("sole_first", 1, rows[i].sole_first),
                ("tied_first", 1, rows[i].tied_first),
            ]
        )
    if table == "class_acceptability":
        if not result.classes:
            raise AnalysisExportError("This analysis has no classes to export.")
        return ["alternative_id", "alternative_name", "class_id", "class_name", *estimate], (
            [i, rows[i].name, c.class_id, c.name, e.count, e.frequency, e.lower, e.upper]
            for i in order
            for c in result.classes
            for e in [rows[i].classes[c.class_id]]
        )
    return [
        "position",
        "input",
        "path",
        "leader_id",
        "leader_rank1_upper_half",
        "leader_rank1_lower_half",
        "difference",
        "label",
    ], (
        [
            k + 1,
            x.input,
            x.path,
            result.leader_id,
            x.leader_rank1_upper_half,
            x.leader_rank1_lower_half,
            x.difference,
            result.inputs_to_check_label,
        ]
        for k, x in enumerate(result.inputs_to_check)
    )


def _explanation_cells(row: CriterionExplanation) -> list[str | int | float | None]:
    return [
        row.criterion_id,
        row.name,
        row.difference,
        row.favours,
        row.zone,
        row.preference_degree,
        str(row.capped).lower(),
        row.q,
        row.p,
        row.promethee_contribution,
        row.promethee_head_to_head,
        row.mavt_contribution,
    ]


def _promethee_rows(
    record: PrometheeAnalysisRecord, table: ExportTable, order: list[str]
) -> tuple[list[str], Iterable[list[str | int | float | None]]]:
    """PROMETHEE II's tables. Every row carries the flow label; none has a value column."""
    result = record.result
    label = result.label
    flows = {f.alternative_id: f for f in result.flows}
    names = {f.alternative_id: f.name for f in result.flows}
    if table == "flows":
        return [
            "alternative_id",
            "alternative_name",
            "promethee_rank",
            "positive_flow",
            "negative_flow",
            "net_flow",
            "label",
        ], (
            [
                i,
                names[i],
                flows[i].rank,
                flows[i].positive_flow,
                flows[i].negative_flow,
                flows[i].net_flow,
                label,
            ]
            for i in order
        )
    if table == "criterion_flows":
        return [
            "alternative_id",
            "alternative_name",
            "criterion_id",
            "criterion_name",
            "unit",
            "direction",
            "weight",
            "normalised_weight",
            "preference_function",
            "coding",
            "criterion_flow",
            "weighted_criterion_flow",
            "label",
        ], (
            [
                i,
                names[i],
                c.criterion_id,
                c.name,
                c.unit,
                c.direction,
                c.weight,
                c.normalised_weight,
                canonical_json(c.function.model_dump(mode="json")),
                None if c.coding is None else canonical_json(c.coding),
                flows[i].criterion_flows[c.criterion_id],
                c.normalised_weight * flows[i].criterion_flows[c.criterion_id],
                label,
            ]
            for i in order
            for c in result.criteria
        )
    if table == "partial_order":
        return [
            "alternative_a_id",
            "alternative_a_name",
            "alternative_b_id",
            "alternative_b_name",
            "relation",
            "tolerance",
            "label",
        ], (
            [
                pair.alternative_a,
                names[pair.alternative_a],
                pair.alternative_b,
                names[pair.alternative_b],
                pair.relation,
                record.numerical_tolerance,
                label,
            ]
            for pair in result.partial_order
        )
    explanation = result.explanation
    if not explanation.available:
        raise AnalysisExportError(
            f"This analysis has no explanation against MAVT: {explanation.unavailable_reason}."
        )
    return [
        "alternative_a_id",
        "alternative_a_name",
        "alternative_b_id",
        "alternative_b_name",
        "mavt_rank_a",
        "mavt_rank_b",
        "promethee_rank_a",
        "promethee_rank_b",
        "value_gap",
        "flow_gap",
        "head_to_head",
        "via_others",
        "detailed",
        "criterion_id",
        "criterion_name",
        "difference",
        "favours",
        "zone",
        "preference_degree",
        "capped",
        "q",
        "p",
        "promethee_contribution",
        "promethee_head_to_head",
        "mavt_contribution",
        "reasons",
        "label",
    ], (
        [
            pair.alternative_a,
            names[pair.alternative_a],
            pair.alternative_b,
            names[pair.alternative_b],
            pair.mavt_rank_a,
            pair.mavt_rank_b,
            pair.promethee_rank_a,
            pair.promethee_rank_b,
            pair.value_gap,
            pair.flow_gap,
            pair.head_to_head,
            pair.via_others,
            str(pair.detailed).lower(),
            *cells,
            canonical_json(pair.reasons),
            label,
        ]
        for pair in explanation.pairs
        for cells in ([_explanation_cells(r) for r in pair.criteria] or [[None] * 12])
    )


def _ahp_rows(
    record: AhpAnalysisRecord, table: ExportTable, order: list[str]
) -> tuple[list[str], Iterable[list[str | int | float | None]]]:
    """AHP's tables. Every row carries the label; none has a value column."""
    result = record.result
    label = result.label
    rows = {a.alternative_id: a for a in result.alternatives}
    if table == "priorities":
        return [
            "alternative_id",
            "alternative_name",
            "ahp_rank",
            "ahp_priority",
            "ideal_score",
            "synthesis",
            "label",
        ], (
            [
                i,
                rows[i].name,
                rows[i].rank,
                rows[i].priority,
                rows[i].ideal_score,
                result.synthesis,
                label,
            ]
            for i in order
        )
    if table == "criterion_priorities":
        parents = {
            item: m.group_id for m in result.matrices if m.kind == "criteria" for item in m.items
        }
        return ["criterion_id", "group_id", "local_priority", "global_priority", "label"], (
            [node, parents.get(node), local, result.global_priorities.get(node), label]
            for node, local in result.local_priorities.items()
        )
    if table == "local_priorities":
        return [
            "alternative_id",
            "alternative_name",
            "criterion_id",
            "local_priority",
            "global_priority",
            "weighted_part",
            "label",
        ], (
            [
                i,
                rows[i].name,
                leaf,
                rows[i].local_priorities[leaf],
                result.global_priorities[leaf],
                rows[i].weighted_parts[leaf],
                label,
            ]
            for i in order
            for leaf in result.leaf_order
        )
    return [
        "kind",
        "group_id",
        "items",
        "n",
        "lambda_max",
        "consistency_index",
        "random_index",
        "random_index_table",
        "consistency_ratio",
        "inconsistent",
        "triad_items",
        "triad_index",
        "triad_consistent_value",
        "label",
    ], (
        [
            m.kind,
            m.group_id,
            canonical_json(m.items),
            len(m.items),
            m.lambda_max,
            m.consistency_index,
            m.random_index,
            result.random_index_table,
            m.consistency_ratio,
            str(m.inconsistent).lower(),
            None if t is None else canonical_json(list(t.items)),
            None if t is None else t.index,
            None if t is None else t.consistent_value,
            label,
        ]
        for m in result.matrices
        for t in [m.most_inconsistent_triad]
    )


def _csv_rows(
    record: AnyRecord, table: ExportTable, presentation: AnalysisPresentation
) -> tuple[list[str], Iterable[list[str | int | float | None]]]:
    if isinstance(record, AhpAnalysisRecord):
        ranked = [a.alternative_id for a in record.result.ranking]
        order = record.alternative_order if presentation.sort == "project" else ranked
        return _ahp_rows(record, table, order)
    if isinstance(record, PrometheeAnalysisRecord):
        ranked = [a.alternative_id for a in record.result.ranking]
        order = record.alternative_order if presentation.sort == "project" else ranked
        return _promethee_rows(record, table, order)
    if isinstance(record, SmaaAnalysisRecord):
        ranked = [a.alternative_id for a in record.result.ranking]
        order = record.alternative_order if presentation.sort == "project" else ranked
        return _smaa_rows(record, table, order)
    result = record.result
    details = {a.alternative_id: a for a in result.alternatives}
    order = (
        record.alternative_order
        if presentation.sort == "project"
        else [a.alternative_id for a in result.ranking]
    )
    criteria = {c.criterion_id: c for c in record.criteria}
    if isinstance(record, SortingAnalysisRecord) and table in {"ranking", "classes"}:
        return _sorting_rows(record, table, order)
    if table == "ranking":
        return ["alternative_id", "alternative_name", "rank", "overall_value"], (
            [i, details[i].name, details[i].rank, details[i].overall_value] for i in order
        )
    if table in {"contributions", "partial_values"}:
        return [
            "alternative_id",
            "alternative_name",
            "criterion_id",
            "criterion_name",
            "criterion_path",
            "criterion_description",
            "raw_measurement",
            "unit",
            "partial_value",
            "global_weight",
            "weighted_contribution",
            "overall_value",
            "rank",
            "function_source",
            "value_function",
            "effective_domain",
        ], (
            [
                i,
                details[i].name,
                leaf,
                criteria[leaf].name,
                " / ".join(criteria[leaf].path_names),
                criteria[leaf].description,
                details[i].raw_measurements[leaf],
                criteria[leaf].scale.unit,
                details[i].partial_values[leaf],
                result.global_weights[leaf],
                details[i].weighted_contributions[leaf],
                details[i].overall_value,
                details[i].rank,
                criteria[leaf].function_source,
                canonical_json(criteria[leaf].value_function.model_dump(mode="json")),
                canonical_json(criteria[leaf].model_dump(mode="json")["resolved_domain"]),
            ]
            for i in order
            for leaf in result.leaf_order
        )
    if table == "dominance":
        return [
            "alternative_id",
            "alternative_name",
            "compared_alternative_id",
            "compared_alternative_name",
            "relationship",
            "tolerance",
        ], (
            [
                a,
                details[a].name,
                b,
                details[b].name,
                record.dominance_relations[a][b],
                record.numerical_tolerance,
            ]
            for a in order
            for b in order
        )
    comparison = record.comparison
    if comparison is None:
        raise AnalysisExportError(
            "Select an evaluable scenario and base to export their comparison."
        )
    scenario = comparison.scenarios[0]
    return [
        "alternative_id",
        "alternative_name",
        "base_value",
        "scenario_value",
        "value_change",
        "base_rank",
        "scenario_rank",
        "base_profile_id",
        "scenario_profile_id",
        "winner_changed",
        "ranking_changed",
        "applied_overrides",
        "base_diagnostics",
        "scenario_diagnostics",
    ], (
        [
            i,
            details[i].name,
            comparison.baseline.values[i],
            scenario.values[i],
            scenario.delta_from_baseline[i],
            comparison.baseline.rank_by_alternative[i],
            scenario.rank_by_alternative[i],
            comparison.baseline.weight_profile_id,
            scenario.weight_profile_id,
            str(scenario.winner_differs_from_baseline).lower(),
            str(scenario.ranking_differs_from_baseline).lower(),
            canonical_json(
                {k: v.model_dump(mode="json") for k, v in scenario.applied_overrides.items()}
            ),
            canonical_json(
                [
                    v.model_dump(mode="json")
                    for v in comparison.baseline.diagnostics
                    if v.severity == Severity.WARNING
                ]
            ),
            canonical_json(
                [
                    v.model_dump(mode="json")
                    for v in scenario.diagnostics
                    if v.severity == Severity.WARNING
                ]
            ),
        ]
        for i in order
    )


def export_analysis(
    project: Project,
    configuration: AnalysisConfiguration | None,
    expected_project_fingerprint: str,
    expected_record_digest: str,
    format_: Literal["json", "csv"],
    table: ExportTable = "ranking",
    presentation: AnalysisPresentation | None = None,
) -> tuple[bytes, str, str, AnyRecord]:
    """Verify one captured project/configuration before downloading its completed record."""
    if project.fingerprint() != expected_project_fingerprint:
        raise StaleRevisionError("Export project does not match the displayed analysis revision.")
    record = analysis_record(project, configuration)
    if record.record_digest != expected_record_digest:
        raise StaleRevisionError(
            "Export analysis does not match the displayed scenario/profile record."
        )
    view = presentation or AnalysisPresentation()
    if set(view.hidden_alternative_ids) - set(record.alternative_order) or set(
        view.hidden_criterion_ids
    ) - set(project.tree().leaves()):
        raise AnalysisExportError(
            "Export visibility refers to an unknown alternative or criterion."
        )
    stem = (
        f"mcda-{project.id}-{record.result.project_fingerprint[:12]}-"
        f"{record.result.scenario_id or 'base'}"
    )
    version_2 = not isinstance(record, AnalysisRecord)
    if format_ == "json":
        source = project.model_copy(deep=True)
        document = (
            AnalysisExportDocument(record=record, source_project=source, presentation=view)
            if isinstance(record, AnalysisRecord)
            else AnalysisExportDocumentV2(record=record, source_project=source, presentation=view)
        )
        data = (
            json.dumps(
                document.model_dump(mode="json"),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        if len(data) > MAX_EXPORT_BYTES:
            raise AnalysisLimitError("JSON export exceeds the 16 MiB download limit.")
        return data, "application/json", stem + ".json", record
    method = record.result.method
    if table not in EXPORT_TABLES.get(method, ()):
        raise AnalysisExportError(f"{get_method(method).label} does not export a {table!r} table.")
    headers, rows = _csv_rows(record, table, view)
    context_headers = [
        "export_version",
        "project_id",
        "project_title",
        "project_fingerprint",
        "record_digest",
        "method",
        "scenario_id",
        "scenario_name",
        "explicit_profile_id",
        "resolved_profile_id",
        "resolved_profile_name",
        "configuration",
        "warnings",
        "calculation_path",
        "csv_text_policy",
        "presentation",
    ]
    context: list[str | int | float | None] = [
        "2" if version_2 else "1",
        project.id,
        project.title,
        record.result.project_fingerprint,
        record.record_digest,
        record.result.method,
        record.result.scenario_id,
        record.scenario_name,
        record.result.configuration.weight_profile_id,
        record.result.weight_profile_id,
        record.resolved_profile_name,
        canonical_json(record.result.configuration.model_dump(mode="json")),
        canonical_json(
            [
                v.model_dump(mode="json")
                for v in record.result.diagnostics
                if v.severity == Severity.WARNING
            ]
        ),
        record.calculation_path,
        record.csv_text_policy,
        canonical_json(view.model_dump(mode="json")),
    ]
    buffer = _BoundedBuffer()
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(context_headers + headers)
    encoded_context = [_cell(value) for value in context]
    for row in rows:
        writer.writerow(encoded_context + [_cell(value) for value in row])
    return buffer.getvalue().encode("utf-8"), "text/csv", stem + f"-{table}.csv", record
