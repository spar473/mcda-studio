from conftest import VC_FILE, import_file


def test_restore_endpoints_conflict_copy_and_reopen(client):
    original = import_file(client, VC_FILE)
    pid = original["project"]["id"]
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    rows = client.get("/api/trash").json()
    assert len(rows) == 1 and rows[0]["readable"] and not rows[0]["conflict"]
    route = f"/api/trash/{rows[0]['entry']}/restore"
    restored = client.post(route, json={})
    assert restored.status_code == 201
    assert restored.json()["fingerprint"] == original["fingerprint"]
    assert client.get(f"/api/projects/{pid}").json()["project"] == original["project"]
    assert client.post(route, json={}).status_code == 409
    copied = client.post(route, json={"as_copy": True})
    assert copied.status_code == 201 and copied.json()["project"]["id"] != pid
    assert copied.json()["fingerprint"] != original["fingerprint"]
    assert client.get("/api/trash").json()[0]["conflict"]


def test_unreadable_entry_visible_without_mutation(client, store_dir):
    trash = store_dir / ".trash"
    trash.mkdir(parents=True)
    entry = trash / "bad.20261026T000000000000Z.json"
    entry.write_text("malformed")
    rows = client.get("/api/trash").json()
    assert not rows[0]["readable"] and rows[0]["error"]
    response = client.post(f"/api/trash/{entry.name}/restore", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TRASH_ENTRY_UNREADABLE"
    assert entry.read_text() == "malformed"
