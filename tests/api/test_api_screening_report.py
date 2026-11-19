"""The screening report over HTTP and from the command line: the route returns the service's own
bytes as an attachment, a stale or invalid request is never substituted, nothing is written to the
library, and the command refuses to overwrite and rejects bad options."""

from datetime import date
from pathlib import Path

from conftest import EXAMPLES, dump, import_file, repo
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from mcda_studio.cli import app as cli_app
from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.services import screening_report_service as report

STUDY = EXAMPLES / "nz_venture_screening"


def dossier() -> EvidenceDossier:
    return EvidenceDossier.model_validate_json((STUDY / "evidence.json").read_text())


def test_the_route_returns_the_services_report_as_an_html_attachment(client: TestClient) -> None:
    project = repo.load(STUDY / "project.json")
    expected = report.screening_report(project, None, dossier(), None, date(2026, 11, 7))
    response = client.post(
        "/api/screening-report",
        json={
            "project": dump(project),
            "dossier": dossier().model_dump(mode="json"),
            "generated_on": "2026-11-07",
        },
    )
    assert response.status_code == 200, response.text
    assert response.text == expected
    assert response.headers["content-type"].startswith("text/html")
    assert 'filename="screening-report.html"' in response.headers["content-disposition"]
    assert response.headers["x-project-fingerprint"] == project.fingerprint()
    assert response.headers["cache-control"] == "no-store"


def test_a_chosen_profile_and_scenario_reach_the_report(client: TestClient) -> None:
    project = repo.load(STUDY / "project.json")
    body = {
        "project": dump(project),
        "profile_ids": ["commercial_traction"],
        "configuration": {"method": "mavt", "scenario_id": "linear_market_size"},
    }
    text = client.post("/api/screening-report", json=body).text
    assert "Commercial/traction-led" in text and "Technical/IP-led (" not in text
    assert "linear_market_size" in text
    assert (
        client.post("/api/screening-report", json={**body, "profile_ids": ["nope"]}).status_code
        == 422
    )


def test_an_unknown_scenario_or_bad_date_is_an_error_and_nothing_is_stored(
    client: TestClient,
) -> None:
    project = dump(repo.load(STUDY / "project.json"))
    before = client.get("/api/projects").json()
    assert (
        client.post(
            "/api/screening-report", json={"project": project, "generated_on": "nonsense"}
        ).status_code
        == 422
    )
    bad = {"project": project, "configuration": {"method": "mavt", "scenario_id": "missing"}}
    assert client.post("/api/screening-report", json=bad).status_code == 422
    assert client.get("/api/projects").json() == before


def test_a_report_for_a_stored_project_leaves_it_untouched(client: TestClient) -> None:
    stored_id = import_file(client, STUDY / "project.json")["project"]["id"]
    before = client.get(f"/api/projects/{stored_id}").json()
    project = client.get(f"/api/projects/{stored_id}").json()["project"]
    assert client.post("/api/screening-report", json={"project": project}).status_code == 200
    assert client.get(f"/api/projects/{stored_id}").json() == before


def run(*args: str):
    return CliRunner().invoke(cli_app, ["report", "screening", *args])


def test_the_command_writes_a_new_file_or_standard_output_and_never_overwrites(
    tmp_path: Path,
) -> None:
    project = STUDY / "project.json"
    target = tmp_path / "report.html"
    first = run(
        str(project),
        "--evidence",
        str(STUDY / "evidence.json"),
        "--generated-on",
        "2026-11-07",
        "--out",
        str(target),
    )
    assert first.exit_code == 0, first.output
    expected = report.screening_report(repo.load(project), None, dossier(), None, date(2026, 11, 7))
    assert target.read_text(encoding="utf-8") == expected
    again = run(str(project), "--out", str(target))
    assert again.exit_code != 0 and target.read_text(encoding="utf-8") == expected
    printed = run(str(project), "--profile", "technical_ip", "--scenario", "linear_market_size")
    assert printed.exit_code == 0 and printed.stdout.startswith("<!doctype html>")
    assert "Generated on" not in printed.stdout
    assert "<h3>Commercial/traction-led</h3>" not in printed.stdout


def test_the_command_rejects_a_bad_date_profile_or_evidence_file(tmp_path: Path) -> None:
    project = str(STUDY / "project.json")
    assert run(project, "--generated-on", "7 November").exit_code != 0
    assert run(project, "--profile", "nope").exit_code != 0
    assert run(project, "--scenario", "missing").exit_code != 0
    broken = tmp_path / "e.json"
    broken.write_text("{}")
    assert run(project, "--evidence", str(broken)).exit_code != 0
    assert run(str(tmp_path / "missing.json")).exit_code != 0


def test_notes_reach_the_report_through_the_route_and_the_limits_are_422s(
    client: TestClient,
) -> None:
    project = dump(repo.load(STUDY / "project.json"))
    ok = client.post(
        "/api/screening-report", json={"project": project, "notes": ["A <b>note</b>.", "n" * 300]}
    )
    assert ok.status_code == 200 and "<li>A &lt;b&gt;note&lt;/b&gt;.</li>" in ok.text
    assert "<li>" + "n" * 300 + "</li>" in ok.text
    for bad in (["n" * 301], ["x"] * 21, [""], ["   "]):
        response = client.post("/api/screening-report", json={"project": project, "notes": bad})
        assert response.status_code == 422, bad
    twenty = client.post("/api/screening-report", json={"project": project, "notes": ["x"] * 20})
    assert twenty.status_code == 200
    without = client.post("/api/screening-report", json={"project": project})
    assert "<li>x</li>" not in without.text


def test_the_command_reads_a_note_file_one_statement_per_line(tmp_path: Path) -> None:
    project = str(STUDY / "project.json")
    notes = tmp_path / "notes.txt"
    notes.write_text("First & <i>second</i>.\n\n  Third.  \r\n", encoding="utf-8")
    result = run(project, "--note-file", str(notes))
    assert result.exit_code == 0, result.output
    assert "<li>First &amp; &lt;i&gt;second&lt;/i&gt;.</li><li>Third.</li></ul>" in result.stdout
    notes.write_text("\n".join(f"line {i}" for i in range(20)) + "\n", encoding="utf-8")
    assert run(project, "--note-file", str(notes)).exit_code == 0
    notes.write_text("\n".join(f"line {i}" for i in range(21)) + "\n", encoding="utf-8")
    refused = run(project, "--note-file", str(notes))
    assert refused.exit_code != 0 and "at most 20 notes" in refused.output
    notes.write_text("a" * 301, encoding="utf-8")
    assert run(project, "--note-file", str(notes)).exit_code != 0
    notes.write_bytes(b"\xff\xfe not text")
    assert run(project, "--note-file", str(notes)).exit_code != 0
    assert run(project, "--note-file", str(tmp_path / "missing.txt")).exit_code != 0


def test_the_published_contract_states_the_note_limits(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()["components"]["schemas"]["ScreeningReportRequest"]
    notes = next(
        option for option in schema["properties"]["notes"]["anyOf"] if option.get("type") == "array"
    )
    assert notes["maxItems"] == 20
    assert notes["items"]["maxLength"] == 300 and notes["items"]["minLength"] == 1
    assert "notes" not in schema.get("required", [])
