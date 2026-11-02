"""Keyed GUI/API/CLI materialization parity and unchanged ordinary result contracts."""

import json

import pytest
from typer.testing import CliRunner

from mcda_studio.cli import app
from mcda_studio.domain.starter_templates import StarterInstantiationRequest
from mcda_studio.services import checked_factor_service as checked
from mcda_studio.services import factor_analysis_service as factors
from mcda_studio.services import model_comparison_service as comparisons
from mcda_studio.services import starter_template_service as starters
from model_builders import REVIEW, inputs


@pytest.mark.parametrize(
    "id", ["blank", "supplier_selection", "infrastructure_procurement", "venture_screening"]
)
def test_keyed_starter_api_cli_and_service_are_identical_and_do_not_save(client, tmp_path, id):
    request = StarterInstantiationRequest(
        template_id=id, project_id=f"new_{id}", title="My reviewed decision"
    )
    expected = starters.instantiate(request)
    response = client.post(
        "/api/starter-templates/instantiate", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    assert response.json() == expected.model_dump(mode="json")
    path, output = tmp_path / "request.json", tmp_path / "materials.json"
    path.write_text(request.model_dump_json())
    command = ["starter-templates", "instantiate", str(path), "-o", str(output)]
    result = CliRunner().invoke(app, command)
    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text()) == response.json()
    verified = client.post("/api/starter-templates/verify", json=response.json())
    assert verified.status_code == 200 and verified.json() == response.json()
    archive = client.post("/api/starter-templates/archive", json=response.json())
    assert archive.content == starters.archive(expected)
    repeated = CliRunner().invoke(app, command)
    assert repeated.exit_code == 1
    assert client.get("/api/projects").json()["projects"] == []


def test_model_selection_http_cli_and_questions_reproduce_without_project_mutation(
    client, tmp_path
):
    p, _, _, _, comparison = inputs()
    client.post("/api/projects/import", json=p.model_dump(mode="json"))
    before = client.get(f"/api/projects/{p.id}/file").content
    body = {"project": p.model_dump(mode="json"), "comparison": comparison.model_dump(mode="json")}
    response = client.post("/api/model-comparisons/inspect", json=body)
    expected = comparisons.inspect(p, comparison)
    assert response.status_code == 200 and response.json() == expected.model_dump(mode="json")
    selection = comparisons.ModelTargetSelection(
        side="right",
        alternative_id="a",
        criterion_id="annual",
        target_scope=comparison.right.scope,
        review=REVIEW,
    )
    compiled = client.post(
        "/api/model-comparisons/compile",
        json={
            **body,
            "selection": selection.model_dump(mode="json"),
            "expected_review_digest": expected.review_digest,
        },
    )
    bundle = comparisons.compile_selection(p, comparison, selection, expected.review_digest)
    assert compiled.status_code == 200 and compiled.json() == bundle.model_dump(mode="json")
    verified = client.post("/api/model-comparisons/verify", json={"document": compiled.json()})
    assert verified.status_code == 200 and verified.json() == compiled.json()
    paths = [
        tmp_path / name
        for name in ("project.json", "comparison.json", "selection.json", "bundle.json")
    ]
    for path, document in zip(paths, (p, comparison, selection), strict=False):
        path.write_text(document.model_dump_json())
    result = CliRunner().invoke(
        app,
        [
            "model-comparisons",
            "compile",
            *[str(path) for path in paths[:3]],
            expected.review_digest,
            "-o",
            str(paths[3]),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(paths[3].read_text()) == compiled.json()
    questions = client.post(
        "/api/open-questions",
        json={"project": body["project"], "model_comparison": body["comparison"]},
    )
    assert questions.status_code == 200, questions.text
    assert any(q["code"] == "MODEL_DISAGREEMENT" for q in questions.json()["questions"])
    assert client.get(f"/api/projects/{p.id}/file").content == before
    stale = client.post(
        "/api/model-comparisons/compile",
        json={
            **body,
            "selection": selection.model_dump(mode="json"),
            "expected_review_digest": "0" * 64,
        },
    )
    assert stale.status_code == 412
    assert stale.json()["error"]["code"] == "STALE_REVISION"


def test_checked_run_and_output_verify_retain_unmodified_inner_record(client, tmp_path):
    p, model, spec, declaration, comparison = inputs()
    parameters = factors.FactorRunParameters(run="mavt", draws=12, seed=19)
    response = client.post(
        "/api/checked-factor-runs/run",
        json={
            "project": p.model_dump(mode="json"),
            "model": model.model_dump(mode="json"),
            "uncertainty": spec.model_dump(mode="json"),
            "checks": declaration.model_dump(mode="json"),
            "parameters": parameters.model_dump(mode="json"),
        },
    )
    assert response.status_code == 200, response.text
    assert response.json() == checked.run(p, model, spec, declaration, parameters).model_dump(
        mode="json"
    )
    paths = [
        tmp_path / name
        for name in (
            "project.json",
            "model.json",
            "uncertainty.json",
            "checks.json",
            "parameters.json",
        )
    ]
    for path, value in zip(paths, (p, model, spec, declaration, parameters), strict=True):
        path.write_text(value.model_dump_json())
    exported = tmp_path / "checked.json"
    result = CliRunner().invoke(
        app,
        ["model-comparisons", "run-checked", *[str(path) for path in paths], "-o", str(exported)],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(exported.read_text()) == response.json()
    assert (
        CliRunner().invoke(app, ["model-comparisons", "verify-checked", str(exported)]).exit_code
        == 0
    )
    verified = client.post("/api/checked-factor-runs/verify", json={"document": response.json()})
    assert verified.status_code == 200 and verified.json() == response.json()
    output = client.post(
        "/api/model-outputs/run",
        json={
            "project": p.model_dump(mode="json"),
            "specification": comparison.right.model_dump(mode="json"),
        },
    )
    assert output.status_code == 200, output.text
    assert output.json()["draw_count"] == 0
    assert client.post("/api/model-outputs/verify", json=output.json()).json() == output.json()
