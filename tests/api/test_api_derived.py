from pathlib import Path

from mcda_studio.domain.derived import DerivedModel
from mcda_studio.services import derived_service
from mcda_studio.storage.json_repository import JsonProjectRepository

EXAMPLE = Path(__file__).parents[2] / "examples/derived_measurements"


def test_derived_preview_matches_service_without_editing_project(client):
    p = JsonProjectRepository().load(EXAMPLE / "supplier-project.json")
    model = DerivedModel.model_validate_json((EXAMPLE / "supplier-model.json").read_text())
    before = p.model_dump_json()
    response = client.post(
        "/api/derived/preview",
        json={"project": p.model_dump(mode="json"), "model": model.model_dump(mode="json")},
    )
    assert response.status_code == 200
    assert response.json() == derived_service.preview(p, model).model_dump(mode="json")
    assert p.model_dump_json() == before
    model.sources[0].review = None
    response = client.post(
        "/api/derived/preview",
        json={"project": p.model_dump(mode="json"), "model": model.model_dump(mode="json")},
    )
    assert any(i["code"] == "DERIVED_UNREVIEWED_SOURCE" for i in response.json()["issues"])


def test_compilation_is_stateless_digest_guarded_and_bundle_can_be_reopened(client):
    p = JsonProjectRepository().load(EXAMPLE / "supplier-project.json")
    model = DerivedModel.model_validate_json((EXAMPLE / "supplier-model.json").read_text())
    project = p.model_dump(mode="json")
    assert client.post("/api/projects/import", json=project).status_code == 201
    before = client.get(f"/api/projects/{p.id}").json()
    report = derived_service.preview(p, model)
    body = {
        "project": project,
        "model": model.model_dump(mode="json"),
        "expected_review_digest": report.review_digest,
    }
    response = client.post("/api/derived/compile", json=body)
    assert response.status_code == 200
    bundle = response.json()
    assert bundle == derived_service.compilation_bundle(p, model, report.review_digest).model_dump(
        mode="json"
    )
    reopened = client.post("/api/derived/preview", json={"project": project, "model": bundle})
    assert reopened.status_code == 200 and reopened.json() == report.model_dump(mode="json")
    body["expected_review_digest"] = "different"
    assert client.post("/api/derived/compile", json=body).status_code == 412
    bundle["digest"] = "changed"
    assert (
        client.post("/api/derived/preview", json={"project": project, "model": bundle}).status_code
        == 409
    )
    assert client.get(f"/api/projects/{p.id}").json() == before
