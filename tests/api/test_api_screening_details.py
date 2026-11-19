"""Details are read-only joins of existing engine records, not a new scoring path."""

from conftest import EXAMPLES, dump, import_file, repo
from fastapi.testclient import TestClient

from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.results import MavtResult
from mcda_studio.services import analysis_service, feasibility_service, questions_service
from mcda_studio.services.screening_details_service import screening_details
from mcda_studio.services.screening_summary_service import screening_summary

STUDY = EXAMPLES / "nz_venture_screening"


def test_details_equal_existing_engines_and_preserve_every_scored_leaf() -> None:
    project = repo.load(STUDY / "project.json")
    dossier = EvidenceDossier.model_validate_json((STUDY / "evidence.json").read_text())
    before = project.model_dump_json()
    for profile in ("technical_ip", "commercial_traction"):
        for scenario in (None, "linear_market_size"):
            cfg = AnalysisConfiguration(
                method="mavt_sorting", weight_profile_id=profile, scenario_id=scenario
            )
            summary = screening_summary(project, cfg, dossier)
            record = analysis_service.evaluate_project(
                project, cfg.model_copy(update={"method": "mavt", "parameters": {}})
            )
            assert isinstance(record, MavtResult)
            feasibility = feasibility_service.check_feasibility(project)
            questions = questions_service.open_questions(project, cfg, dossier)
            for row in summary.rows:
                response = screening_details(project, cfg, dossier, row.alternative_id)
                detail = response.alternative
                assert detail is not None and detail.row == row
                assert response.project_fingerprint == project.fingerprint()
                assert response.configuration == cfg
                assert (response.weight_profile_id, response.scenario_id) == (profile, scenario)
                engine = next(
                    a for a in record.alternatives if a.alternative_id == row.alternative_id
                )
                scored = [n for n in record.leaf_order if record.global_weights[n] > 0]
                assert len(detail.contributions) == len(detail.ratings) == len(scored) == 16
                assert [c.criterion_id for c in detail.contributions] == sorted(
                    scored, key=lambda n: -engine.weighted_contributions[n]
                )
                assert {c.criterion_id: c.contribution for c in detail.contributions} == {
                    n: engine.weighted_contributions[n] for n in scored
                }
                assert detail.requirements == next(
                    a for a in feasibility.alternatives if a.alternative_id == row.alternative_id
                )
                assert detail.questions == [
                    q for q in questions.questions if q.alternative_id == row.alternative_id
                ]
                assert {f.criterion_id for f in detail.header_facts} == {
                    r.criterion_id for r in project.requirements or []
                }
                for rating in detail.ratings:
                    assert (
                        rating.measurement
                        == project.performance_index()[row.alternative_id, rating.criterion_id]
                    )
                    assert rating.rubric_text == (
                        rating.measurement
                        if isinstance(rating.measurement, str)
                        else project.tree().node(rating.criterion_id).description
                    )
                    assert rating.claim_ids == [
                        c.id
                        for c in dossier.claims
                        if c.alternative_id == row.alternative_id
                        and c.criterion_id == rating.criterion_id
                    ]
                assert response.sensitivity is not None
                leader = summary.rows[0].fragility
                if leader and leader.criterion_id:
                    assert response.sensitivity.suggested_criterion_id == leader.criterion_id
                assert all(
                    c.unweighted
                    for c in response.sensitivity.criteria
                    if c.criterion_id in {"mandate", "hq_country", "stage", "sector"}
                )
    assert project.model_dump_json() == before


def test_route_is_read_only_and_unavailable_is_honest(client: TestClient) -> None:
    project = repo.load(STUDY / "project.json")
    project_id = import_file(client, STUDY / "project.json")["project"]["id"]
    before = client.get(f"/api/projects/{project_id}")
    body = {"project": dump(project), "alternative_id": "hnry"}
    response = client.post("/api/screening-details", json=body)
    assert response.status_code == 200, response.text
    assert response.json() == screening_details(project, alternative_id="hnry").model_dump(
        mode="json"
    )
    assert response.json()["alternative"]["requirements"]["status"] == "fail"
    after = client.get(f"/api/projects/{project_id}")
    assert before.content == after.content and before.headers["etag"] == after.headers["etag"]
    assert (
        client.post("/api/screening-details", json={**body, "alternative_id": "nope"}).status_code
        == 422
    )
    broken = dump(project)
    broken["performances"] = broken["performances"][1:]
    unavailable = client.post("/api/screening-details", json={"project": broken}).json()
    assert unavailable["status"] == "unavailable"
    assert unavailable["alternative"] is None and unavailable["sensitivity"] is None


def test_stale_dossier_cannot_supply_sources() -> None:
    project = repo.load(STUDY / "project.json")
    dossier = EvidenceDossier.model_validate_json((STUDY / "evidence.json").read_text())
    dossier.project_fingerprint = "0" * 64
    response = screening_details(project, dossier=dossier, alternative_id="upstock")
    assert response.alternative is not None
    assert all(r.claim_ids == [] for r in response.alternative.ratings)


def test_metadata_fallback_uses_the_highest_weight_objective_in_tree_order(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from mcda_studio.services import screening_details_service as details

    project = repo.load(STUDY / "project.json")
    summary = screening_summary(project)
    for row in summary.rows:
        row.fragility = None
    monkeypatch.setattr(details, "screening_summary", lambda *_args: summary)
    response = details.screening_details(project)
    assert response.alternative is None
    assert response.sensitivity is not None
    # Accepted Technical/IP raw root ratings are 0, 90, 100, 60, 50.
    assert response.sensitivity.suggested_criterion_id == "problem_solution"
    assert {
        c.criterion_id: c.global_weight
        for c in response.sensitivity.criteria
        if c.parent_id is None
    } == {
        "mandate": 0,
        "team": 90 / 300,
        "problem_solution": 100 / 300,
        "market": 60 / 300,
        "traction": 50 / 300,
    }
