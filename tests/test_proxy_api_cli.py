"""One stateless path through service, HTTP and file CLI; stale input refuses with 412."""

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from mcda_studio.api import create_app
from mcda_studio.cli import app
from mcda_studio.services import proxy_criterion_service as proxy
from proxy_builders import inputs, request


def test_proxy_http_cli_and_full_export_replay_are_bit_identical(tmp_path):
    value = inputs()
    req = request(value)
    expected = proxy.run_pair(req)
    with TestClient(create_app(tmp_path / "library", frontend_dir=False)) as client:
        response = client.post("/api/proxy/preview-pair", json=value.model_dump(mode="json"))
        assert response.status_code == 200
        assert response.json() == proxy.inspect(value).model_dump(mode="json")
        response = client.post("/api/proxy/run-pair", json=req.model_dump(mode="json"))
        assert response.status_code == 200
        assert response.json() == expected.model_dump(mode="json")
        response = client.post("/api/proxy/verify", json={"document": response.json()})
        assert response.status_code == 200
        assert response.json() == expected.model_dump(mode="json")
        changed = req.model_dump(mode="json")
        changed["expected_review_digest"] = "0" * 64
        response = client.post("/api/proxy/run-pair", json=changed)
        assert response.status_code == 412
        assert response.json()["error"]["code"] == "STALE_REVISION"
    source, output = tmp_path / "request.json", tmp_path / "pair.json"
    source.write_text(req.model_dump_json())
    runner = CliRunner()
    result = runner.invoke(app, ["proxy", "run-pair", str(source), "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text()) == expected.model_dump(mode="json")
    result = runner.invoke(app, ["proxy", "verify", str(output)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == expected.model_dump(mode="json")
    result = runner.invoke(app, ["proxy", "run-pair", str(source), "--output", str(output)])
    assert result.exit_code == 1
