"""Analysis records/downloads are context-checked read-only API operations."""

import csv
import io
import json

import pytest
from conftest import VC_FILE, dump, import_file, repo


def payload(project, record, **updates):
    return {
        "project": project,
        "configuration": record["result"]["configuration"],
        "expected_project_fingerprint": record["result"]["project_fingerprint"],
        "expected_record_digest": record["record_digest"],
        **updates,
    }


def test_record_and_downloads_keep_stored_bytes_etag_and_engine_results(client):
    document = import_file(client, VC_FILE)
    p = document["project"]
    before = client.get(f"/api/projects/{p['id']}/file").content
    etag = client.get(f"/api/projects/{p['id']}").headers["etag"]
    response = client.post("/api/analysis/record", json={"project": p})
    assert response.status_code == 200, response.text
    record = response.json()
    assert record["result"] == client.post("/api/evaluate", json={"project": p}).json()
    for fmt in ["json", "csv"]:
        download = client.post("/api/analysis/export", json=payload(p, record, format=fmt))
        assert download.status_code == 200, download.text
        assert download.headers["content-type"].startswith(
            "application/json" if fmt == "json" else "text/csv"
        )
        assert download.headers["content-disposition"].endswith(f'.{fmt}"')
        assert download.headers["x-analysis-record-digest"] == record["record_digest"]
        assert download.headers["x-project-fingerprint"] == document["fingerprint"]
        if fmt == "json":
            assert download.json()["record"] == record
        else:
            rows = list(csv.DictReader(io.StringIO(download.text)))
            assert [float(r["overall_value"]) for r in rows] == [
                r["value"] for r in record["result"]["ranking"]
            ]
    assert client.get(f"/api/projects/{p['id']}/file").content == before
    assert client.get(f"/api/projects/{p['id']}").headers["etag"] == etag


def test_stored_endpoints_obey_selected_scenario_and_explicit_profile(client):
    p = import_file(client, VC_FILE)["project"]
    configuration = {
        "method": "mavt",
        "scenario_id": "linear_market_size",
        "weight_profile_id": "default",
        "parameters": {},
    }
    record = client.post(
        f"/api/projects/{p['id']}/analysis/record", json={"configuration": configuration}
    ).json()
    assert record["result"]["scenario_id"] == "linear_market_size"
    assert record["comparison"]["baseline"]["configuration"]["scenario_id"] is None
    body = payload(p, record, format="csv", table="comparison")
    body.pop("project")
    response = client.post(f"/api/projects/{p['id']}/analysis/export", json=body)
    assert response.status_code == 200, response.text
    assert all(
        row["base_profile_id"] == row["scenario_profile_id"] == "default"
        for row in csv.DictReader(io.StringIO(response.text))
    )
    changed = {**p, "title": "Saved elsewhere"}
    assert client.put(f"/api/projects/{p['id']}", json=changed).status_code == 200
    assert client.post(f"/api/projects/{p['id']}/analysis/export", json=body).status_code == 412


@pytest.mark.parametrize(
    "update,code",
    [
        ({"expected_project_fingerprint": "0" * 64}, 412),
        ({"expected_record_digest": "0" * 64}, 412),
        ({"configuration": {"method": "mavt", "scenario_id": "linear_market_size"}}, 412),
        ({"expected_record_digest": "bad"}, 422),
        ({"format": "xlsx"}, 422),
        ({"table": "unknown"}, 422),
        ({"presentation": {"hidden_alternative_ids": ["missing"]}}, 422),
    ],
)
def test_export_rejects_bad_context_and_unavailable_formats_without_model_writes(
    client, update, code
):
    p = dump(repo.load(VC_FILE))
    record = client.post("/api/analysis/record", json={"project": p}).json()
    response = client.post("/api/analysis/export", json=payload(p, record, **update))
    assert response.status_code == code, response.text
    assert "error" in response.json()
    assert client.get("/api/projects").json()["projects"] == []


def test_incomplete_invalid_and_oversized_record_requests_have_structured_errors(client):
    p = dump(repo.load(VC_FILE))
    p["performances"].pop()
    response = client.post("/api/analysis/record", json={"project": p})
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_FAILED"
    p = dump(repo.load(VC_FILE))
    p["alternatives"] = [{"id": f"a{i}", "name": f"Alt {i}"} for i in range(101)]
    response = client.post("/api/analysis/record", json={"project": p})
    assert response.status_code == 413 and response.json()["error"]["code"] == "ANALYSIS_LIMIT"


def test_project_schema_and_reference_fixtures_remain_unchanged():
    import hashlib
    from pathlib import Path

    root = Path(__file__).parents[2]
    baseline = json.loads((root / "tests/fixtures/contract_baseline.json").read_text())
    current = json.loads((root / "docs/api/openapi.json").read_text())
    for key, schema in baseline["schemas"].items():
        assert schema == current["components"]["schemas"][key]
    for relative, sha in baseline["sha256"].items():
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == sha
