"""Completed records and exports use one engine path and never persist view/explanation data."""

import csv
import hashlib
import io
import json
import math
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mcda_studio.domain.analysis_record import AnalysisPresentation
from mcda_studio.domain.criteria import LinearValueFunction
from mcda_studio.domain.errors import (
    AnalysisExportError,
    AnalysisLimitError,
    StaleRevisionError,
    ValidationFailed,
)
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.services import analysis_service as analysis
from mcda_studio.services import project_service as ps
from mcda_studio.services import results_service as svc
from mcda_studio.storage.json_repository import JsonProjectRepository

from builders import flat_project, tiny_project

ROOT = Path(__file__).parents[2]


def reference(name="nz_deeptech_vc"):
    return JsonProjectRepository().load(ROOT / "examples" / name / "project.json")


def exported(p, record=None, fmt="json", table="ranking", view=None):
    record = record or svc.analysis_record(p)
    return svc.export_analysis(
        p, record.result.configuration, p.fingerprint(), record.record_digest, fmt, table, view
    )


def rows(data):
    return list(csv.DictReader(io.StringIO(data.decode("utf-8"))))


def test_record_is_one_existing_engine_result_with_full_context_and_authoritative_path_shares():
    p = reference()
    before = p.fingerprint()
    record = svc.analysis_record(p)
    assert record.result == analysis.evaluate_project(p)
    assert record.result.configuration == p.analysis
    assert record.path_shares == analysis.preview_weights(p).path_shares
    assert record.calculation_path == "mavt.math_fsum.v1"
    assert len(record.criteria) == 8
    market = next(c for c in record.criteria if c.criterion_id == "market_size")
    assert market.path_ids == ["market", "market_size"] and market.scale.unit == "US$ bn"
    assert market.value_function == p.tree().node("market_size").value_function
    assert market.function_source == "base" and market.resolved_domain.source == "control_points"
    for alt in record.result.alternatives:
        assert record.contribution_totals[alt.alternative_id] == alt.overall_value
    digest = hashlib.sha256(
        svc.canonical_json(record.model_dump(mode="json", exclude={"record_digest"})).encode()
    ).hexdigest()
    assert digest == record.record_digest and p.fingerprint() == before
    assert svc.analysis_record(p) == record


def test_selected_result_is_not_evaluated_again_for_comparison():
    p = reference()
    cfg = AnalysisConfiguration(scenario_id="linear_market_size")
    with patch.object(svc, "build_mavt_result", wraps=svc.build_mavt_result) as engine:
        record = svc.analysis_record(p, cfg)
        assert engine.call_count == 2  # one selected, one explicit Base
    assert record.comparison == analysis.compare_scenarios(p, ["linear_market_size"], cfg)
    outcome = record.comparison.scenarios[0]
    assert {r.alternative_id: r.value for r in record.result.ranking} == outcome.values
    assert {r.alternative_id: r.rank for r in record.result.ranking} == outcome.rank_by_alternative
    assert (
        next(c for c in record.criteria if c.criterion_id == "market_size").function_source
        == "scenario_override"
    )


def test_valid_selected_override_can_export_when_base_comparison_is_unavailable():
    p = ps.create_scenario(tiny_project(), "Repair", "repair")
    p = ps.set_scenario_override(p, "repair", "cost", LinearValueFunction())
    p.tree().node("cost").value_function = None
    record = svc.analysis_record(p, AnalysisConfiguration(scenario_id="repair"))
    assert record.comparison is None
    assert record.comparison_diagnostics[0].code == "BASE_COMPARISON_UNAVAILABLE"
    assert exported(p, record)[1] == "application/json"
    with pytest.raises(AnalysisExportError):
        exported(p, record, "csv", "comparison")


@pytest.mark.parametrize(
    "values,expected",
    [
        ([[0.8, 0.2], [0.2, 0.8]], "incomparable"),
        ([[0.8, 0.8], [0.2, 0.2]], "dominates"),
        ([[0.2, 0.2], [0.8, 0.8]], "dominated_by"),
        ([[0.4, 0.6], [0.4, 0.6]], "equal"),
        ([[0.4, 0.6], [0.4 + 5e-13, 0.6]], "equal"),
    ],
)
def test_dominance_uses_partial_values_and_engine_edges_with_existing_tolerance(values, expected):
    record = svc.analysis_record(flat_project(values, [1, 1]))
    assert record.dominance_relations["a0"]["a1"] == expected
    assert record.dominance_relations["a0"]["a0"] == "same_alternative"


def test_zero_weight_improvements_can_dominate_despite_equal_overall_scores():
    record = svc.analysis_record(flat_project([[0.5, 0.9], [0.5, 0.1]], [1, 0]))
    assert [r.rank for r in record.result.ranking] == [1, 1]
    assert record.dominance_relations["a0"]["a1"] == "dominates"
    p = flat_project([[0.5, 0.9], [0.5, 0.1]], [1, 0])
    disabled = svc.analysis_record(p, AnalysisConfiguration(parameters={"dominance_check": False}))
    assert disabled.dominance_relations["a0"]["a1"] == "not_checked"
    assert not disabled.dominance_enabled and disabled.result.dominance == []


def test_full_precision_json_is_standalone_reproducible_and_view_filters_do_not_change_results():
    p = reference()
    record = svc.analysis_record(p)
    view = AnalysisPresentation(
        hidden_alternative_ids=["hyades"], hidden_criterion_ids=["market_size"]
    )
    data, mime, filename, same = exported(p, record, view=view)
    document = json.loads(data)
    assert mime == "application/json" and filename.endswith("-base.json")
    assert b"0.7226678550207962" in data
    assert document["record"] == record.model_dump(mode="json") and same == record
    assert document["source_project"] == p.model_dump(mode="json")
    reloaded = type(p).model_validate(document["source_project"])
    assert analysis.evaluate_project(reloaded, record.result.configuration) == record.result
    assert document["presentation"]["hidden_criterion_ids"] == ["market_size"]
    assert exported(p, record, view=view)[0] == data  # deterministic bytes, no timestamps


@pytest.mark.parametrize(
    "table", ["ranking", "contributions", "partial_values", "comparison", "dominance"]
)
def test_all_csv_tables_preserve_ids_context_and_full_precision(table):
    p = reference()
    record = svc.analysis_record(p, AnalysisConfiguration(scenario_id="linear_market_size"))
    data, mime, filename, _ = exported(p, record, "csv", table)
    values = rows(data)
    assert values and mime == "text/csv" and filename.endswith(f"-{table}.csv")
    for row in values:
        assert row["project_fingerprint"] == p.fingerprint()
        assert row["record_digest"] == record.record_digest
        assert (
            row["scenario_id"] == "linear_market_size" and row["resolved_profile_id"] == "default"
        )
    if table == "ranking":
        assert [float(r["overall_value"]) for r in values] == [
            r.value for r in record.result.ranking
        ]
        assert [int(r["rank"]) for r in values] == [r.rank for r in record.result.ranking]
    if table in {"contributions", "partial_values"}:
        assert len(values) == 32
        for alt in record.result.alternatives:
            selected = [r for r in values if r["alternative_id"] == alt.alternative_id]
            assert [r["criterion_id"] for r in selected] == record.result.leaf_order
            assert (
                math.fsum(float(r["weighted_contribution"]) for r in selected) == alt.overall_value
            )
    if table == "comparison":
        outcome = record.comparison.scenarios[0]
        assert {
            r["alternative_id"]: float(r["value_change"]) for r in values
        } == outcome.delta_from_baseline
    assert exported(p, record, "csv", table)[0] == data


@pytest.mark.parametrize(
    "value",
    [
        "=1+1",
        "+cmd|x",
        "-1+2",
        "@SUM(1)",
        " \t=1",
        "\r\n=1",
        "\x00=1",
        "\ufeff=1",
        "＝1",
        "＋1",
        "－1",
        "＠x",
        "'=@x",
        '";=1',
        '=1,"\n@evil',
        "\u200b=1",
    ],
)
def test_adversarial_csv_text_has_a_durable_literal_prefix_and_no_control_characters(value):
    safe = svc.safe_csv_text(value)
    assert safe.startswith("TEXT:")
    assert not any(ord(c) < 32 for c in safe)


def test_csv_quoting_does_not_split_attack_strings_and_does_not_change_source_data():
    p = tiny_project()
    attack = '=HYPERLINK("https://invalid.test");\r\n@SUM(1,2)'
    p.alternatives[0].name = attack
    p.criteria[0].name = " ＝1+1"
    p.criteria[0].description = "\t=2"
    before = p.fingerprint()
    record = svc.analysis_record(p)
    data = exported(p, record, "csv", "partial_values")[0]
    values = rows(data)
    assert len(values) == 4
    assert values[0]["alternative_name"].startswith("TEXT:=HYPERLINK")
    assert values[0]["criterion_name"].startswith("TEXT:")
    assert values[0]["criterion_description"].startswith("TEXT:\\u0009")
    assert p.alternatives[0].name == attack and p.fingerprint() == before
    assert json.loads(exported(p, record)[0])["source_project"]["alternatives"][0]["name"] == attack


def test_export_refuses_cross_revision_cross_configuration_and_unknown_visibility():
    p = reference()
    record = svc.analysis_record(p)
    with pytest.raises(StaleRevisionError):
        svc.export_analysis(p, p.analysis, "0" * 64, record.record_digest, "json")
    with pytest.raises(StaleRevisionError):
        svc.export_analysis(
            p,
            AnalysisConfiguration(scenario_id="linear_market_size"),
            p.fingerprint(),
            record.record_digest,
            "json",
        )
    with pytest.raises(AnalysisExportError):
        exported(p, record, view=AnalysisPresentation(hidden_criterion_ids=["unknown"]))


def test_incomplete_models_and_bounded_requests_never_export_fabricated_data(monkeypatch):
    p = ps.clear_performance(tiny_project(), "a", "cost")
    before = p.fingerprint()
    with pytest.raises(ValidationFailed):
        svc.analysis_record(p)
    assert p.fingerprint() == before
    monkeypatch.setattr(svc, "MAX_ALTERNATIVES", 1)
    with pytest.raises(AnalysisLimitError):
        svc.analysis_record(tiny_project())


def test_project_sort_and_filters_preserve_engine_totals_and_complete_export_rows():
    p = reference()
    record = svc.analysis_record(p)
    view = AnalysisPresentation(
        sort="project", hidden_alternative_ids=["hyades"], hidden_criterion_ids=["market_size"]
    )
    data = exported(p, record, "csv", "ranking", view)[0]
    values = rows(data)
    assert [r["alternative_id"] for r in values] == record.alternative_order
    assert {r["alternative_id"]: float(r["overall_value"]) for r in values} == {
        r.alternative_id: r.value for r in record.result.ranking
    }


@settings(max_examples=40, deadline=None)
@given(
    st.lists(
        st.lists(st.floats(0, 1, allow_nan=False, allow_infinity=False), min_size=3, max_size=3),
        min_size=1,
        max_size=8,
    ),
    st.lists(st.integers(1, 10000), min_size=3, max_size=3),
)
def test_generated_contributions_exports_and_dominance_preserve_engine_precision(values, ratings):
    p = flat_project(values, ratings)
    record = svc.analysis_record(p)
    data = exported(p, record, "csv", "contributions")[0]
    for alt in record.result.alternatives:
        assert math.fsum(alt.weighted_contributions.values()) == alt.overall_value
        assert record.contribution_totals[alt.alternative_id] == alt.overall_value
    for row in rows(data):
        alt = next(
            a for a in record.result.alternatives if a.alternative_id == row["alternative_id"]
        )
        assert (
            float(row["weighted_contribution"]) == alt.weighted_contributions[row["criterion_id"]]
        )


def test_csv_retains_validation_warnings_without_repeating_every_dominance_info_message():
    p = flat_project([[i / 20, i / 20] for i in range(20)], [1, 1])
    record = svc.analysis_record(p)
    assert len(record.result.dominance) == 190
    data = exported(p, record, "csv", "contributions")[0]
    assert len(data) < 100000
    assert all("DOMINANCE" not in row["warnings"] for row in rows(data))
    assert len(json.loads(exported(p, record)[0])["record"]["result"]["dominance"]) == 190


def test_json_reproduction_uses_explicit_view_configuration_even_when_saved_defaults_differ():
    p = reference()
    p.analysis.scenario_id = "linear_market_size"
    record = svc.analysis_record(p, AnalysisConfiguration())
    document = json.loads(exported(p, record)[0])
    restored = type(p).model_validate(document["source_project"])
    cfg = AnalysisConfiguration.model_validate(document["record"]["result"]["configuration"])
    assert restored.analysis.scenario_id == "linear_market_size" and cfg.scenario_id is None
    assert analysis.evaluate_project(restored, cfg) == record.result
    assert analysis.evaluate_project(restored).ranking != record.result.ranking
