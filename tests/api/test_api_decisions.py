"""Decision record preview/inspect endpoints are stateless and match the service exactly."""

import json
from datetime import date
from pathlib import Path

import pytest
from conftest import errors

from mcda_studio.domain.decision import DecisionDetails
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.services import decision_record_service as svc

ROOT = Path(__file__).parents[2]


def details(**changes):
    return DecisionDetails(
        owner="Owner",
        date=date(2026, 11, 1),
        outcome="selected",
        selected_alternative_id="apex",
        alternatives_considered=["apex", "brightline"],
        rationale="Synthetic illustration",
        configurations=[
            AnalysisConfiguration(method="mavt"),
            AnalysisConfiguration(method="smaa2"),
        ],
        **changes,
    ).model_dump(mode="json")


def test_preview_inspect_and_revise_without_library_writes(client):
    raw = json.loads((ROOT / "examples/supplier_qualification/project.json").read_text())
    imported = client.post("/api/projects/import", json=raw)
    project = imported.json()["project"]
    saved = client.get(f"/api/projects/{project['id']}/file").content
    first = client.post("/api/decisions/preview", json={"project": project, "details": details()})
    assert first.status_code == 200, first.text
    record = first.json()
    expected = svc.create(Project.model_validate(project), DecisionDetails(**details()))
    assert record == expected.model_dump(mode="json")
    assert [a["status"] for a in record["analyses"]] == ["completed", "unavailable"]
    opened = client.post("/api/decisions/inspect", json={"project": project, "record": record})
    assert opened.status_code == 200 and opened.json()["current_project_matches"] is True
    revised = client.post(
        "/api/decisions/preview",
        json={
            "project": project,
            "details": details(unresolved_assumptions=["Changed assumption"]),
            "predecessor": record,
        },
    ).json()
    assert revised["previous_digest"] == record["digest"]
    both = {"project": project, "record": revised, "predecessor": record}
    assert client.post("/api/decisions/inspect", json=both).json()["predecessor_verified"] is True
    assert client.get(f"/api/projects/{project['id']}/file").content == saved
    edited = {**project, "title": "Edited later"}
    historical = client.post("/api/decisions/inspect", json={"project": edited, "record": record})
    assert historical.json()["current_project_matches"] is False


def test_invalid_tampered_and_unrelated_inputs_are_refused(client):
    raw = json.loads((ROOT / "examples/supplier_qualification/project.json").read_text())
    record = client.post(
        "/api/decisions/preview", json={"project": raw, "details": details()}
    ).json()
    malformed = client.post("/api/decisions/inspect", json={"project": raw, "record": {"x": 1}})
    assert errors(malformed)["code"] == "INVALID_DECISION_RECORD"
    record["decision"]["rationale"] = "Rewritten"
    tampered = client.post("/api/decisions/inspect", json={"project": raw, "record": record})
    assert errors(tampered)["code"] == "EDIT_REFUSED"
    assert "DECISION_RECORD_CHANGED" in tampered.json()["error"]["message"]
    unknown = details()
    unknown["alternatives_considered"] = ["apex", "absent"]
    refused = errors(
        client.post("/api/decisions/preview", json={"project": raw, "details": unknown})
    )
    assert refused["code"] == "VALIDATION_FAILED"
    assert [d["code"] for d in refused["details"]] == ["DECISION_UNKNOWN_ALTERNATIVE"]
    inconsistent = details()
    inconsistent["outcome"] = "deferred"
    bad = client.post("/api/decisions/preview", json={"project": raw, "details": inconsistent})
    assert bad.status_code == 422


def resigned(record: dict) -> dict:
    model = svc.DecisionRecordV2.model_validate(record)
    model.digest = svc.digest(model)
    return model.model_dump(mode="json")


@pytest.mark.parametrize("requirements", [False, True])
def test_invalid_references_and_snapshots_are_422_not_server_errors(client, requirements):
    raw = json.loads((ROOT / "examples/supplier_qualification/project.json").read_text())
    if requirements:
        cap = {"kind": "bound", "id": "cap", "name": "Cap", "criterion_id": "unit_price"}
        raw["requirements"] = [{**cap, "unit": "NZD", "maximum": 50}]
    ghost = details()
    ghost["alternatives_considered"] = ["apex", "ghost"]
    ghost["selected_alternative_id"] = "ghost"
    refused = client.post("/api/decisions/preview", json={"project": raw, "details": ghost})
    assert errors(refused)["code"] == "VALIDATION_FAILED"
    assert {d["code"] for d in refused.json()["error"]["details"]} == {
        "DECISION_UNKNOWN_ALTERNATIVE",
        "DECISION_UNKNOWN_SELECTION",
    }
    profiles = [None, raw["weight_profiles"][1]["id"]]
    request = details()
    request["configurations"] = [
        {"method": "mavt", "weight_profile_id": pid, "scenario_id": None, "parameters": {}}
        for pid in profiles
    ]
    record = client.post("/api/decisions/preview", json={"project": raw, "details": request}).json()
    cases = {
        "DECISION_UNKNOWN_SELECTION": lambda r: r["decision"].update(
            alternatives_considered=[*r["decision"]["alternatives_considered"], "ghost"],
            selected_alternative_id="ghost",
        ),
        "DECISION_ANALYSIS_RECORD_MISSING": lambda r: r["analyses"][0].update(record=None),
        "DECISION_ANALYSIS_SUBSTITUTED": lambda r: r["analyses"][0].update(
            record=r["analyses"][1]["record"]
        ),
    }
    for code, tamper in cases.items():
        changed = json.loads(json.dumps(record))
        tamper(changed)
        response = client.post(
            "/api/decisions/inspect", json={"project": raw, "record": resigned(changed)}
        )
        assert errors(response)["code"] == "VALIDATION_FAILED", code
        assert code in {d["code"] for d in response.json()["error"]["details"]}


@pytest.mark.parametrize("value", ["nan", "1e999", "-Infinity"])
@pytest.mark.parametrize("role", ["record", "predecessor"])
def test_nonfinite_numbers_in_supplied_records_are_refused_not_server_errors(client, value, role):
    raw = json.loads((ROOT / "examples/supplier_qualification/project.json").read_text())
    record = client.post(
        "/api/decisions/preview", json={"project": raw, "details": details()}
    ).json()
    later = client.post(
        "/api/decisions/preview", json={"project": raw, "details": details(), "predecessor": record}
    ).json()
    damaged = json.loads(json.dumps(record))
    damaged["analyses"][0]["record"]["path_shares"]["delivery"] = value
    body = (
        {"project": raw, "record": damaged}
        if role == "record"
        else {"project": raw, "record": later, "predecessor": damaged}
    )
    for url in ("/api/decisions/inspect", "/api/decisions/preview"):
        if url.endswith("preview"):
            body = {"project": raw, "details": details(), "predecessor": damaged}
        response = client.post(url, json=body)
        assert errors(response)["code"] == "EDIT_REFUSED", response.text
        assert "DECISION_RECORD_NONFINITE" in response.json()["error"]["message"]


def test_nonfinite_numbers_in_version_one_records_are_refused(client):
    raw = json.loads((ROOT / "examples/supplier_qualification/project.json").read_text())
    from mcda_studio.domain.decision import DecisionDraft
    from mcda_studio.services import decision_service

    p = Project.model_validate(raw)
    draft = DecisionDraft(
        owner="Analyst",
        date=date(2026, 10, 31),
        chosen_alternative_id="apex",
        rationale="Earlier CLI record",
        configurations=[AnalysisConfiguration(method="mavt")],
    )
    v1 = decision_service.create(p, draft).model_dump(mode="json")
    v1["analyses"][0]["result"]["alternatives"][0]["overall_value"] = "nan"
    response = client.post("/api/decisions/inspect", json={"project": raw, "record": v1})
    assert errors(response)["code"] == "EDIT_REFUSED", response.text
    assert "DECISION_RECORD_NONFINITE" in response.json()["error"]["message"]
