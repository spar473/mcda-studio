"""The method comparison view: every method's own reading of one model, side by side.

Each method runs through its own record builder, unchanged, with the selected profile and scenario
and its own parameters (its saved ones only when it is the saved method). A method that cannot
read the model becomes a failed column carrying its typed error. Agreement compares orders and
classes only, and every reason is taken from the method's own result: no number here combines two
methods. See ``docs/design/method-comparison.md``.
"""

import csv
import json
from collections.abc import Sequence
from typing import Literal

from mcda_studio.domain.analysis_record import (
    AhpAnalysisRecord,
    PrometheeAnalysisRecord,
    SmaaAnalysisRecord,
    SortingAnalysisRecord,
)
from mcda_studio.domain.comparison import (
    Agreement,
    ClassAgreement,
    ColumnError,
    ColumnReason,
    ComparisonCell,
    ComparisonColumn,
    LeaderGroup,
    MethodComparison,
)
from mcda_studio.domain.errors import AnalysisLimitError, McdaError, StaleRevisionError
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.methods.base import get_method, registered_methods
from mcda_studio.methods.mavt.aggregation import TIE_TOL, rank_values
from mcda_studio.services import results_service as results

AnyRecord = results.AnyRecord
MAX_NOTES = 2
#: The name and range of each method's own ranking quantity.
QUANTITIES = {
    "mavt": ("overall value", "0 to 1"),
    "mavt_sorting": ("overall value", "0 to 1"),
    "smaa2": ("rank-1 acceptability", "share of draws, 0 to 1"),
    "promethee2": ("net flow", "-1 to 1"),
    "ahp": ("AHP priority", "share of the goal, 0 to 1"),
}


def _column_error(exc: McdaError) -> ColumnError:
    # The API's own mapping, so a column's error is exactly what /evaluate would return.
    from mcda_studio.api.errors import from_mcda_error

    api = from_mcda_error(exc)
    codes = [str(d["code"]) for d in api.details if "code" in d]
    return ColumnError(status=api.status, code=api.code, message=api.message, issue_codes=codes)


def _inputs(project: Project, cfg: AnalysisConfiguration) -> list[str]:
    """What the method reads, named for its column."""
    try:
        profile = project.resolve_profile(cfg)
        scenario = project.resolve_scenario(cfg)
        profile_name = profile.name if profile else "none"
        scenario_name = scenario.name if scenario else "Base model"
    except McdaError:
        profile_name, scenario_name = str(cfg.weight_profile_id), str(cfg.scenario_id)
    value_model = ["value functions", f"weight profile {profile_name}", f"scenario {scenario_name}"]
    return {
        "mavt": value_model,
        "mavt_sorting": [*value_model, "classes (sorting)"],
        "smaa2": [
            *value_model,
            "stated uncertainty (smaa)",
            *(["classes (sorting)"] if project.sorting else []),
        ],
        "promethee2": [
            "measurements",
            "PROMETHEE inputs (promethee)",
            f"weight profile {profile_name} and scenario {scenario_name}, for the explanation",
        ],
        "ahp": ["pairwise judgements (ahp)"],
    }.get(cfg.method, [])


def _cells(record: AnyRecord, names: dict[str, str]) -> tuple[list[ComparisonCell], list[str]]:
    """Cells in the project's order and the column's leaders, from the method's own result."""
    order = record.alternative_order
    if isinstance(record, SmaaAnalysisRecord):
        smaa = record.result
        rows = {a.alternative_id: a for a in smaa.acceptability}
        firsts = [rows[i].ranks[0].frequency for i in order]
        ranks = rank_values(firsts, TIE_TOL)
        cells = []
        for k, i in enumerate(order):
            row = rows[i]
            first = row.ranks[0]
            interval = (
                (first.lower, first.upper)
                if first.lower is not None and first.upper is not None
                else None
            )
            modal = max(
                smaa.classes,
                key=lambda c: (row.classes[c.class_id].frequency, -c.rank),
                default=None,
            )
            notes = []
            if row.tied_first.frequency > 0:
                notes.append(f"tied for first in {row.tied_first.frequency:.1%} of draws")
            cells.append(
                ComparisonCell(
                    alternative_id=i,
                    rank=ranks[k],
                    quantity=first.frequency,
                    interval=interval,
                    class_id=modal.class_id if modal else None,
                    class_share=row.classes[modal.class_id].frequency if modal else None,
                    notes=notes,
                )
            )
        return cells, [smaa.leader_id]
    leaders = [r.alternative_id for r in record.result.ranking if r.rank == 1]
    if isinstance(record, PrometheeAnalysisRecord):
        flows = {f.alternative_id: f for f in record.result.flows}
        partners: dict[str, list[str]] = {i: [] for i in order}
        for pair in record.result.partial_order:
            if pair.relation == "incomparable":
                partners[pair.alternative_a].append(pair.alternative_b)
                partners[pair.alternative_b].append(pair.alternative_a)
        return [
            ComparisonCell(
                alternative_id=i,
                rank=flows[i].rank,
                quantity=flows[i].net_flow,
                interval=None,
                class_id=None,
                class_share=None,
                notes=[f"incomparable with {names[j]} under PROMETHEE I" for j in partners[i]][
                    :MAX_NOTES
                ],
            )
            for i in order
        ], leaders
    if isinstance(record, AhpAnalysisRecord):
        rows_ahp = {a.alternative_id: a for a in record.result.alternatives}
        return [
            ComparisonCell(
                alternative_id=i,
                rank=rows_ahp[i].rank,
                quantity=rows_ahp[i].priority,
                interval=None,
                class_id=None,
                class_share=None,
                notes=[]
                if rows_ahp[i].ideal_score is None
                else [f"ideal score {rows_ahp[i].ideal_score:.4f}"],
            )
            for i in order
        ], leaders
    value = record.result
    details = {a.alternative_id: a for a in value.alternatives}
    dominated: dict[str, list[str]] = {i: [] for i in order}
    for d in value.dominance:
        dominated[d.dominated_id].append(d.dominator_id)
    assigned = (
        {a.alternative_id: a for a in record.result.assignments}
        if isinstance(record, SortingAnalysisRecord)
        else {}
    )
    cells = []
    for i in order:
        notes = []
        if i in assigned and assigned[i].on_boundary:
            notes.append("on the lower boundary of its class")
        notes += [f"dominated by {names[j]}" for j in dominated[i]]
        cells.append(
            ComparisonCell(
                alternative_id=i,
                rank=details[i].rank,
                quantity=details[i].overall_value,
                interval=None,
                class_id=assigned[i].class_id if i in assigned else None,
                class_share=None,
                notes=notes[:MAX_NOTES],
            )
        )
    return cells, leaders


def _reasons(
    method: str, record: AnyRecord, leaders: list[str], mavt: list[str], names: dict[str, str]
) -> list[str]:
    """Why ``method``'s leaders differ from MAVT's, taken from its own result."""
    if isinstance(record, SmaaAnalysisRecord):
        row = next(a for a in record.result.acceptability if a.alternative_id == leaders[0])
        first = row.ranks[0]
        interval = (
            f" ({first.lower:.1%} to {first.upper:.1%})"
            if first.lower is not None and first.upper is not None
            else ""
        )
        out = [f"{names[leaders[0]]} takes rank 1 in {first.frequency:.1%} of draws{interval}"]
        if first.frequency < 0.5:
            out.append("no alternative takes rank 1 in half of the draws")
        return out
    if isinstance(record, PrometheeAnalysisRecord):
        result = record.result
        if len(leaders) != 1 or len(mavt) != 1:
            tied = ", ".join(names[i] for i in leaders)
            theirs = ", ".join(names[i] for i in mavt)
            return [f"PROMETHEE II's first place is {tied}; MAVT's is {theirs}"]
        a, b = mavt[0], leaders[0]
        out = []
        if not result.explanation.available:
            reason = result.explanation.unavailable_reason
            out.append(f"the explanation against MAVT is unavailable: {reason}")
        else:
            pairs = result.explanation.pairs
            pair = next((p for p in pairs if {p.alternative_a, p.alternative_b} == {a, b}), None)
            if pair is None or not pair.detailed:
                out.append("the explanation gives no criterion detail for this pair")
            else:
                out.extend(pair.reasons)
        if any(
            p.relation == "incomparable" and {p.alternative_a, p.alternative_b} == {a, b}
            for p in result.partial_order
        ):
            out.append(f"PROMETHEE I finds {names[a]} and {names[b]} incomparable")
        return out
    if isinstance(record, AhpAnalysisRecord):
        out = [
            "AHP reads its own pairwise judgements, not the measurements, value functions or "
            "weights"
        ]
        for m in record.result.matrices:
            if m.inconsistent:
                where = (
                    f"the alternatives on {m.group_id}"
                    if m.kind == "alternatives"
                    else "the top-level criteria"
                    if m.group_id is None
                    else f"the criteria under {m.group_id}"
                )
                out.append(f"{where}: consistency ratio {m.consistency_ratio:.3f} is above 0.10")
        return out
    if isinstance(record, SortingAnalysisRecord):
        return ["sorting shares MAVT's values, so its first place can differ only through ties"]
    return [f"{method} reads different inputs from MAVT"]


def _agreement(columns: list[ComparisonColumn], records: dict[str, AnyRecord]) -> Agreement:
    ok = [c for c in columns if c.status == "ok"]
    names = {}
    for record in records.values():
        names.update({r.alternative_id: r.name for r in record.result.ranking})
    agree = (
        None
        if len(ok) < 2
        else all(len(c.leaders) == 1 and set(c.leaders) == set(ok[0].leaders) for c in ok)
    )
    groups: dict[tuple[str, ...], list[str]] = {}
    for c in ok:
        groups.setdefault(tuple(sorted(c.leaders)), []).append(c.method)
    classes: list[ClassAgreement] = []
    by_method = {c.method: c for c in ok}
    sorting, smaa = by_method.get("mavt_sorting"), by_method.get("smaa2")
    if sorting and smaa and all(cell.class_id is not None for cell in smaa.cells):
        smaa_cells = {cell.alternative_id: cell for cell in smaa.cells}
        for cell in sorting.cells:
            other = smaa_cells[cell.alternative_id]
            assert cell.class_id is not None and other.class_id is not None
            classes.append(
                ClassAgreement(
                    alternative_id=cell.alternative_id,
                    sorting_class_id=cell.class_id,
                    smaa_class_id=other.class_id,
                    smaa_class_share=other.class_share or 0.0,
                    agree=cell.class_id == other.class_id,
                )
            )
    reasons = []
    mavt = by_method.get("mavt")
    if mavt is not None:
        for c in ok:
            if c.method != "mavt" and set(c.leaders) != set(mavt.leaders):
                reasons.append(
                    ColumnReason(
                        method=c.method,
                        leaders=c.leaders,
                        mavt_leaders=mavt.leaders,
                        reasons=_reasons(
                            c.method, records[c.method], c.leaders, mavt.leaders, names
                        ),
                    )
                )
    return Agreement(
        leaders_agree=agree,
        leader_groups=[LeaderGroup(leaders=list(k), methods=v) for k, v in groups.items()],
        classes=classes,
        reasons=reasons,
    )


def compare_methods(
    project: Project,
    configuration: AnalysisConfiguration | None = None,
    methods: Sequence[str] | None = None,
) -> MethodComparison:
    """Each requested method's own reading of the model under the selected profile and scenario.
    An unregistered method name is an error; a method that cannot read the model is a column."""
    base = configuration or project.analysis
    order = registered_methods()
    for name in methods or []:
        get_method(name)  # UnknownReferenceError for an unregistered method
    wanted = [m for m in order if methods is None or m in methods]
    names = {a.id: a.name for a in project.alternatives}
    columns: list[ComparisonColumn] = []
    records: dict[str, AnyRecord] = {}
    for name in wanted:
        method = get_method(name)
        saved = name == project.analysis.method
        cfg = AnalysisConfiguration(
            method=name,
            weight_profile_id=base.weight_profile_id,
            scenario_id=base.scenario_id,
            parameters=dict(project.analysis.parameters) if saved else {},
        )
        quantity = QUANTITIES.get(name, (None, None))
        try:
            record = results.analysis_record(project, cfg)
        except McdaError as exc:
            columns.append(
                ComparisonColumn(
                    method=name,
                    method_label=method.label,
                    status="failed",
                    configuration=cfg,
                    inputs=_inputs(project, cfg),
                    calculation_path=None,
                    record_digest=None,
                    label=None,
                    quantity_name=quantity[0],
                    quantity_range=quantity[1],
                    leaders=[],
                    cells=[],
                    error=_column_error(exc),
                )
            )
            continue
        records[name] = record
        cells, leaders = _cells(record, names)
        label = getattr(record.result, "label", None)
        columns.append(
            ComparisonColumn(
                method=name,
                method_label=method.label,
                status="ok",
                configuration=cfg,
                inputs=_inputs(project, cfg),
                calculation_path=record.calculation_path,
                record_digest=record.record_digest,
                label=label if isinstance(label, str) else None,
                quantity_name=quantity[0],
                quantity_range=quantity[1],
                leaders=leaders,
                cells=cells,
                error=None,
            )
        )
    return MethodComparison(
        project_id=project.id,
        project_fingerprint=project.fingerprint(),
        configuration=base.model_copy(deep=True),
        methods=wanted,
        alternative_order=[a.id for a in project.alternatives],
        alternative_names=names,
        columns=columns,
        agreement=_agreement(columns, records),
    )


def _cell(value: str | int | float | None) -> str:
    if value is None:
        return ""
    return results.safe_csv_text(value) if isinstance(value, str) else str(value)


def export_comparison(
    project: Project,
    configuration: AnalysisConfiguration | None,
    methods: Sequence[str] | None,
    expected_project_fingerprint: str,
    format_: Literal["json", "csv"],
) -> tuple[bytes, str, str, MethodComparison]:
    """The comparison as JSON, or as a long CSV with one row per alternative and method (a failed
    method has one row with its error). No row puts two methods' quantities side by side."""
    if project.fingerprint() != expected_project_fingerprint:
        raise StaleRevisionError("Export project does not match the displayed comparison revision.")
    comparison = compare_methods(project, configuration, methods)
    stem = f"mcda-{project.id}-{comparison.project_fingerprint[:12]}-methods"
    if format_ == "json":
        text = json.dumps(
            comparison.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False
        )
        data = (text + "\n").encode("utf-8")
    else:
        buffer = results._BoundedBuffer()
        writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        writer.writerow(
            [
                "project_id",
                "project_fingerprint",
                "method",
                "method_label",
                "status",
                "configuration",
                "inputs",
                "record_digest",
                "label",
                "alternative_id",
                "alternative_name",
                "rank",
                "quantity_name",
                "quantity",
                "interval_lower",
                "interval_upper",
                "class_id",
                "class_share",
                "notes",
                "error_code",
                "error_message",
                "context",
            ]
        )
        for column in comparison.columns:
            head = [
                project.id,
                comparison.project_fingerprint,
                column.method,
                column.method_label,
                column.status,
                results.canonical_json(column.configuration.model_dump(mode="json")),
                results.canonical_json(column.inputs),
                column.record_digest,
                column.label,
            ]
            tail = [
                column.error.code if column.error else None,
                column.error.message if column.error else None,
                comparison.agreement.context,
            ]
            if column.error is not None:
                writer.writerow([_cell(v) for v in [*head, *([None] * 10), *tail]])
            for c in column.cells:
                low, high = c.interval if c.interval else (None, None)
                body: list[str | int | float | None] = [
                    c.alternative_id,
                    comparison.alternative_names[c.alternative_id],
                    c.rank,
                    column.quantity_name,
                    c.quantity,
                    low,
                    high,
                    c.class_id,
                    c.class_share,
                    results.canonical_json(c.notes),
                ]
                writer.writerow([_cell(v) for v in [*head, *body, *tail]])
        data = buffer.getvalue().encode("utf-8")
    if len(data) > results.MAX_EXPORT_BYTES:
        raise AnalysisLimitError("Comparison export exceeds the 16 MiB download limit.")
    media = "application/json" if format_ == "json" else "text/csv"
    return data, media, f"{stem}.{format_}", comparison
