"""Preview -> atomic Apply -> preview is bit-identical and only explicit Save writes."""

import pytest
from conftest import SUPPLIER_FILE, VC_FILE, dump, repo


@pytest.mark.parametrize(
    "file,criterion",
    [
        (VC_FILE, "market_size"),
        (SUPPLIER_FILE, "unit_price"),
        (SUPPLIER_FILE, "financial_stability"),
    ],
)
def test_editor_candidate_atomic_apply_and_save_reopen(client, file, criterion):
    p = repo.load(file)
    imported = client.post("/api/projects/import", json=dump(p))
    assert imported.status_code == 201
    before = client.get(f"/api/projects/{p.id}/file").content
    node = next(c for c in p.criteria if c.id == criterion)
    scale = node.scale.model_dump(mode="json")
    scale["unit"] = "explicit edited unit"
    vf = node.value_function.model_dump(mode="json")
    if vf["kind"] == "piecewise_linear":
        vf["points"][1]["value"] = 0.3
    elif vf["kind"] == "linear":
        vf["direction"] = "increasing"
    else:
        vf["max_rating"] = 120
    candidate = {"scale": scale, "value_function": vf}
    preview = client.post(
        "/api/value-functions/preview",
        json={"project": dump(p), "criterion_id": criterion, "candidate": candidate},
    ).json()
    assert preview["readiness"] == "ready"
    applied = client.post(
        "/api/edit",
        json={
            "project": dump(p),
            "operations": [
                {"op": "set_scale", "criterion_id": criterion, "scale": scale},
                {"op": "set_value_function", "criterion_id": criterion, "value_function": vf},
            ],
        },
    )
    assert applied.status_code == 200
    assert client.get(f"/api/projects/{p.id}/file").content == before
    project = applied.json()["project"]
    current = client.post(
        "/api/value-functions/preview", json={"project": project, "criterion_id": criterion}
    ).json()
    assert current["samples"] == preview["samples"] and current["markers"] == preview["markers"]
    saved = client.put(
        f"/api/projects/{p.id}", json=project, headers={"If-Match": imported.headers["etag"]}
    )
    assert saved.status_code == 200
    assert client.get(f"/api/projects/{p.id}").json()["project"] == project
    assert p.fingerprint() == imported.json()["fingerprint"]
