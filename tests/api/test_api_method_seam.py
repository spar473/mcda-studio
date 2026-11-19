"""The method seam: declared capabilities, method-owned validation and parameters, typed refusals.

A test-only fake method is registered for the duration of a test. It proves that every
capability-gated route refuses a method without that capability (422 METHOD_NOT_SUPPORTED), that
validation is dispatched to the configured method, and that MAVT-only records are never produced
for another method. MAVT itself is covered unchanged by the rest of the suite.
"""

from collections.abc import Callable, Iterator
from typing import Any, Literal

import pytest
from conftest import SUPPLIER_FILE, VC_FILE, dump, errors, repo
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from mcda_studio.cli import app as cli_app
from mcda_studio.domain.common import Issue, Severity
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import AnalysisResult, MavtResult
from mcda_studio.methods.base import (
    CAPABILITIES,
    available_methods,
    get_method,
    register,
    unregister,
    validate_analysis,
)
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import results_service as results

VC = repo.load(VC_FILE)
SUPPLIER = repo.load(SUPPLIER_FILE)
FAKE = "test_fake"
LEAF = VC.tree().leaves()[0]


class FakeResult(AnalysisResult):
    method: Literal["test_fake"] = "test_fake"


class FakeMethod:
    name = FAKE
    label = "Test-only fake"

    def __init__(self, capabilities: frozenset[Any], issues: list[Issue]) -> None:
        self.capabilities = capabilities
        self.issues = issues

    def validate(self, project: Project, configuration: AnalysisConfiguration) -> list[Issue]:
        return list(self.issues)

    def evaluate(self, project: Project, configuration: AnalysisConfiguration) -> FakeResult:
        return FakeResult(
            schema_version=project.schema_version,
            project_id=project.id,
            project_fingerprint=project.fingerprint(),
            configuration=configuration,
            weight_profile_id=None,
            scenario_id=None,
            ranking=[],
        )


Make = Callable[..., FakeMethod]


@pytest.fixture
def fake() -> Iterator[Make]:
    def make(*capabilities: str, issues: list[Issue] | None = None) -> FakeMethod:
        method = FakeMethod(frozenset(capabilities), issues or [])
        register(method)
        return method

    yield make
    unregister(FAKE)


def config(method: str = FAKE, **parameters: Any) -> dict[str, Any]:
    return {"method": method, "parameters": parameters}


def post(client: TestClient, route: str, extra: dict[str, Any], method: str) -> Any:
    body = {"project": dump(VC), "configuration": config(method), **extra}
    return client.post(route, json=body)


#: every route gated by a capability, with the extra body it needs
GATED: list[tuple[str, dict[str, Any], str]] = [
    ("/api/sensitivity", {"node_id": "market"}, "weight_sensitivity"),
    ("/api/sensitivity/probe", {"node_id": "market", "weight": 0.5}, "weight_sensitivity"),
    ("/api/scenarios/compare", {}, "scenario_comparison"),
    ("/api/value-functions/preview", {"criterion_id": LEAF}, "value_functions"),
    ("/api/weights/preview", {}, "swing_weights"),
]
GATED_IDS = [route for route, _, _ in GATED]


def refusal(resp: Any, requirement: str, capabilities: list[str]) -> None:
    assert resp.status_code == 422, resp.text
    err = errors(resp)
    assert err["code"] == "METHOD_NOT_SUPPORTED"
    assert err["details"] == [
        {
            "path": "configuration.method",
            "message": f"method {FAKE!r} does not support {requirement!r}",
            "method": FAKE,
            "requirement": requirement,
            "capabilities": capabilities,
        }
    ]


# ---- declarations ------------------------------------------------------------------------------
def test_mavt_declares_its_label_and_exactly_its_capabilities() -> None:
    mavt = get_method("mavt")
    assert available_methods() == ["ahp", "mavt", "mavt_sorting", "promethee2", "smaa2"]
    assert mavt.label == "MAVT (additive value)"
    assert mavt.capabilities == {
        "value_functions",
        "swing_weights",
        "value_scores",
        "contributions",
        "weight_sensitivity",
        "scenario_comparison",
    }
    assert mavt.capabilities <= set(CAPABILITIES)


def test_meta_lists_every_registered_method_with_its_capabilities(
    client: TestClient, fake: Make
) -> None:
    ahp, mavt, sorting, promethee, smaa = (
        {
            "name": name,
            "label": label,
            "capabilities": sorted(get_method(name).capabilities),
            "export_tables": tables,
        }
        for name, label, tables in [
            (
                "ahp",
                "AHP (pairwise priorities)",
                ["priorities", "criterion_priorities", "local_priorities", "consistency"],
            ),
            (
                "mavt",
                "MAVT (additive value)",
                ["ranking", "contributions", "partial_values", "dominance", "comparison"],
            ),
            (
                "mavt_sorting",
                "Value-based sorting (MAVT)",
                [
                    "ranking",
                    "classes",
                    "contributions",
                    "partial_values",
                    "dominance",
                    "comparison",
                ],
            ),
            (
                "promethee2",
                "PROMETHEE II (outranking flows)",
                ["flows", "criterion_flows", "partial_order", "explanation"],
            ),
            (
                "smaa2",
                "SMAA-2 (sampled acceptability)",
                ["rank_acceptability", "class_acceptability", "inputs_to_check"],
            ),
        ]
    )
    assert client.get("/api/meta").json()["methods"] == [ahp, mavt, sorting, promethee, smaa]
    fake("flows", "classes")
    listed = client.get("/api/meta").json()["methods"]
    assert listed == [
        ahp,
        mavt,
        sorting,
        promethee,
        smaa,
        {
            "name": FAKE,
            "label": "Test-only fake",
            "capabilities": ["classes", "flows"],
            "export_tables": [],
        },
    ]


# ---- capability-gated routes -------------------------------------------------------------------
@pytest.mark.parametrize(("route", "extra", "capability"), GATED, ids=GATED_IDS)
def test_a_gated_route_refuses_a_method_without_its_capability(
    client: TestClient, fake: Make, route: str, extra: dict[str, Any], capability: str
) -> None:
    others = [c for c in CAPABILITIES if c != capability]
    fake(*others)
    refusal(post(client, route, extra, FAKE), capability, sorted(others))


@pytest.mark.parametrize(("route", "extra", "capability"), GATED, ids=GATED_IDS)
def test_a_gated_route_serves_a_method_that_declares_its_capability(
    client: TestClient, fake: Make, route: str, extra: dict[str, Any], capability: str
) -> None:
    fake(capability)
    assert post(client, route, extra, FAKE).status_code == 200


@pytest.mark.parametrize(("route", "extra", "capability"), GATED, ids=GATED_IDS)
def test_mavt_is_served_by_every_gated_route(
    client: TestClient, route: str, extra: dict[str, Any], capability: str
) -> None:
    assert capability in get_method("mavt").capabilities
    assert post(client, route, extra, "mavt").status_code == 200


def test_a_method_without_an_api_result_model_is_refused_not_a_server_error(
    client: TestClient, fake: Make
) -> None:
    fake(*CAPABILITIES)
    refusal(post(client, "/api/evaluate", {}, FAKE), "evaluate", sorted(CAPABILITIES))


def test_version_1_records_and_exports_are_never_built_for_another_method(
    client: TestClient, fake: Make
) -> None:
    fake(*CAPABILITIES)
    refusal(post(client, "/api/analysis/record", {}, FAKE), "analysis_record", sorted(CAPABILITIES))
    digest = {"expected_project_fingerprint": VC.fingerprint(), "expected_record_digest": "0" * 64}
    refusal(
        post(client, "/api/analysis/export", digest, FAKE), "analysis_record", sorted(CAPABILITIES)
    )


def test_the_cli_refuses_a_capability_the_saved_method_lacks(fake: Make, tmp_path: Any) -> None:
    fake()
    project = VC.model_copy(deep=True)
    project.analysis = AnalysisConfiguration(method=FAKE)
    path = tmp_path / "fake.json"
    repo.save(project, path)
    out = CliRunner().invoke(cli_app, ["sensitivity", str(path), "--all"])
    assert out.exit_code == 1
    assert "does not support 'weight_sensitivity'" in " ".join(out.output.split())


# ---- validation dispatch -----------------------------------------------------------------------
def test_validation_is_dispatched_to_the_configured_method(fake: Make) -> None:
    own = Issue(severity=Severity.ERROR, code="FAKE_ISSUE", message="fake", path="fake")
    fake(issues=[own])
    incomplete = VC.model_copy(deep=True)
    incomplete.performances = incomplete.performances[1:]  # MAVT would report a measurement
    assert validate_analysis(incomplete, AnalysisConfiguration(method=FAKE)).issues == [own]
    mavt = validate_analysis(incomplete, AnalysisConfiguration()).errors
    assert [i.code for i in mavt] == ["MISSING_MEASUREMENT"]


def test_method_independent_checks_run_before_the_method(fake: Make) -> None:
    fake()
    project = VC.model_copy(deep=True)
    project.weight_profiles = [*project.weight_profiles, project.weight_profiles[0]]
    codes = [i.code for i in validate_analysis(project, AnalysisConfiguration(method=FAKE)).issues]
    assert codes == ["DUPLICATE_PROFILE_ID"]


def test_an_unregistered_method_is_reported_as_unknown(client: TestClient) -> None:
    body = {"project": dump(VC), "configuration": config("nope")}
    report = client.post("/api/analysis/validate", json=body).json()["validation"]
    assert report["issues"] == [
        {
            "severity": "error",
            "code": "UNKNOWN_METHOD",
            "message": "unknown MCDA method 'nope' "
            "(available: ahp, mavt, mavt_sorting, promethee2, smaa2)",
            "path": "configuration.method",
        }
    ]
    # Gated routes let an unknown method through to validation, as evaluation always has.
    sensitivity = post(client, "/api/sensitivity", {"node_id": "market"}, "nope")
    err = errors(sensitivity)
    assert err["code"] == "VALIDATION_FAILED"
    assert [d["code"] for d in err["details"]] == ["UNKNOWN_METHOD"]
    assert errors(post(client, "/api/evaluate", {}, "nope"))["code"] == "UNKNOWN_REFERENCE"


# ---- method-owned parameters -------------------------------------------------------------------
def test_an_unknown_parameter_warns_and_is_ignored() -> None:
    cfg = AnalysisConfiguration(parameters={"colour": "blue"})
    report = validate_analysis(VC, cfg)
    baseline = validate_analysis(VC, AnalysisConfiguration())
    assert report.ok
    assert report.issues[: len(baseline.issues)] == baseline.issues
    assert [(i.severity, i.code, i.path) for i in report.issues[len(baseline.issues) :]] == [
        (Severity.WARNING, "UNKNOWN_PARAMETER", "configuration.parameters.colour")
    ]
    result = svc.evaluate_project(VC, cfg)
    plain = svc.evaluate_project(VC, AnalysisConfiguration())
    assert isinstance(result, MavtResult) and isinstance(plain, MavtResult)
    assert result.ranking == plain.ranking
    assert "UNKNOWN_PARAMETER" in [d.code for d in result.diagnostics]


@pytest.mark.parametrize("bad", ["no", 0, 1, None, [True]])
def test_a_wrongly_typed_known_parameter_is_an_error(client: TestClient, bad: Any) -> None:
    body = {"project": dump(VC), "configuration": config("mavt", dominance_check=bad)}
    err = errors(client.post("/api/evaluate", json=body))
    assert err["code"] == "VALIDATION_FAILED"
    assert [(d["code"], d["path"]) for d in err["details"]] == [
        ("INVALID_PARAMETER", "configuration.parameters.dominance_check")
    ]


@pytest.mark.parametrize("project", [VC, SUPPLIER], ids=["vc", "supplier"])
def test_dominance_check_parameter_is_read_through_the_method_model(project: Project) -> None:
    def record(**parameters: Any) -> Any:
        return results.analysis_record(project, AnalysisConfiguration(parameters=parameters))

    default, on, off = record(), record(dominance_check=True), record(dominance_check=False)
    assert default.result.dominance == on.result.dominance
    assert default.dominance_enabled and not off.dominance_enabled
    assert off.result.dominance == []
