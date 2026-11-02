"""Local, stateless factor runs share one service with the CLI and leave library bytes alone."""

import json
from pathlib import Path

from typer.testing import CliRunner

from mcda_studio.cli import app
from mcda_studio.domain.derived import DerivedModel
from mcda_studio.domain.factor_uncertainty import FactorDistribution, FactorUncertaintyModel
from mcda_studio.domain.uncertainty import DiscreteDistribution
from mcda_studio.services import derived_service
from mcda_studio.services import factor_analysis_service as service
from mcda_studio.storage.json_repository import JsonProjectRepository

ROOT = Path(__file__).parents[2]


def inputs():
    root = ROOT / "examples/derived_measurements"
    project = JsonProjectRepository().load(root / "supplier-project.json")
    model = DerivedModel.model_validate_json((root / "supplier-model.json").read_text())
    source = next(s for s in model.sources if s.id == "annual_units")
    uncertainty = FactorUncertaintyModel(
        project_fingerprint=project.fingerprint(),
        model_digest=derived_service.preview(project, model).model_digest,
        distributions=[
            FactorDistribution(
                factor_id=source.id,
                distribution=DiscreteDistribution(values=[900, 1100], probabilities=[0.5, 0.5]),
                origin=source.origin,
                review=source.review,
            )
        ],
    )
    return project, model, uncertainty


def test_api_cli_service_are_identical_and_do_not_write_project(client, tmp_path):
    p, model, spec = inputs()
    saved = client.post("/api/projects/import", json=p.model_dump(mode="json"))
    assert saved.status_code == 201
    before = client.get(f"/api/projects/{p.id}/file").content
    params = service.FactorRunParameters(draws=24)
    body = {
        "project": p.model_dump(mode="json"),
        "model": model.model_dump(mode="json"),
        "uncertainty": spec.model_dump(mode="json"),
        "parameters": params.model_dump(mode="json"),
    }
    response = client.post("/api/factor-uncertainty/run", json=body)
    assert response.status_code == 200, response.text
    expected = service.run(p, model, spec, params).model_dump(mode="json")
    assert response.json() == expected
    questions = client.post(
        "/api/open-questions",
        json={"project": p.model_dump(mode="json"), "factor_record": expected},
    )
    assert questions.status_code == 200
    assert any(q["code"] == "DERIVED_FACTOR_ASSUMPTION" for q in questions.json()["questions"])
    assert (
        client.post(
            "/api/factor-uncertainty/verify", json={"record": expected, "replay": True}
        ).json()
        == expected
    )
    files = []
    for name, value in [("project", p), ("model", model), ("uncertainty", spec)]:
        path = tmp_path / f"{name}.json"
        path.write_text(value.model_dump_json())
        files.append(str(path))
    output = tmp_path / "run.json"
    result = CliRunner().invoke(
        app,
        [
            "derived",
            "uncertainty-run",
            *files,
            "--draws",
            "24",
            "--seed",
            "7",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text()) == expected
    verified = CliRunner().invoke(app, ["derived", "verify-uncertainty", str(output), "--replay"])
    assert verified.exit_code == 0, verified.output
    again = CliRunner().invoke(
        app, ["derived", "uncertainty-run", *files, "--draws", "24", "--output", str(output)]
    )
    assert again.exit_code == 1
    assert json.loads(output.read_text()) == expected
    assert client.get(f"/api/projects/{p.id}/file").content == before


def test_inspection_keeps_pending_reviews_and_classified_dependency_questions(client):
    p, model, spec = inputs()
    spec.distributions[0].review = None
    body = {
        "project": p.model_dump(mode="json"),
        "model": model.model_dump(mode="json"),
        "uncertainty": spec.model_dump(mode="json"),
    }
    response = client.post("/api/factor-uncertainty/inspect", json=body)
    assert response.status_code == 200
    assert response.json()["uncertainty"]["distributions"][0]["review"] is None
    assert "UNCERTAINTY_UNREVIEWED" in {i["code"] for i in response.json()["issues"]}
    assert len(response.json()["questions"]) == 10
    pending = [q for q in response.json()["questions"] if "factor annual_units " in q["question"]]
    assert len(pending) == 2 and all("pending review" in q["why"] for q in pending)
    response = client.post("/api/factor-uncertainty/run", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    body["uncertainty"]["schema_version"] = 2
    assert client.post("/api/factor-uncertainty/inspect", json=body).status_code == 422


def test_malformed_records_and_bad_draws_are_typed_not_server_errors(client, monkeypatch):
    p, model, spec = inputs()
    from mcda_studio.services import factor_uncertainty_service as factors

    original = factors._marginal

    def marginal(d):
        m = original(d)

        def quantile(u):
            values = m.quantile(u)
            values[17] = 1e20
            return values

        return factors._Marginal(quantile, m.support, m.atoms)

    monkeypatch.setattr(factors, "_marginal", marginal)
    response = client.post(
        "/api/factor-uncertainty/run",
        json={
            "project": p.model_dump(mode="json"),
            "model": model.model_dump(mode="json"),
            "uncertainty": spec.model_dump(mode="json"),
            "parameters": {"draws": 24},
        },
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "INVALID_FACTOR_DRAW"
    assert error["details"][0]["draw"] == 17
    assert error["details"][0]["formula_id"]
    for malformed in ({}, {"version": 2}, {"digest": "wrong"}):
        response = client.post("/api/factor-uncertainty/verify", json={"record": malformed})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "EDIT_REFUSED"
