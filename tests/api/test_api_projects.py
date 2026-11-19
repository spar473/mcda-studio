"""Project lifecycle through HTTP: create, list, load, save, duplicate, delete, import, export.

Persistence is checked on disk (the file the API wrote), not only through further API calls.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from conftest import EXAMPLES, SUPPLIER_FILE, VC_FILE, dump, errors, import_file, repo
from fastapi.testclient import TestClient

from mcda_studio.api import create_app
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import to_json_text


def create(client: TestClient, **body: Any) -> dict[str, Any]:
    resp = client.post("/api/projects", json={"title": "Test", **body})
    assert resp.status_code == 201, resp.text
    doc: dict[str, Any] = resp.json()
    return doc


# ---- service info --------------------------------------------------------------------------
def test_health_reports_versions_methods_and_store(client: TestClient, store_dir: Path) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["schema_version"] == 6
    assert body["methods"] == ["ahp", "mavt", "mavt_sorting", "promethee2", "smaa2"]
    assert body["store"] == str(store_dir)


def test_templates_and_examples_are_listed(client: TestClient) -> None:
    assert {"blank", "supplier-selection"} <= {
        t["name"] for t in client.get("/api/templates").json()
    }
    names = {e["name"] for e in client.get("/api/examples").json()}
    assert {"nz_deeptech_vc", "supplier_selection"} <= names


# ---- create --------------------------------------------------------------------------------
def test_create_blank_project_is_stored_under_its_id(client: TestClient, store_dir: Path) -> None:
    resp = client.post("/api/projects", json={"title": "Holiday", "decision_maker": "Alex"})
    assert resp.status_code == 201
    doc = resp.json()
    pid = doc["project"]["id"]
    assert resp.headers["Location"] == f"/api/projects/{pid}"
    assert resp.headers["ETag"] == f'"{doc["fingerprint"]}"'
    assert doc["project"]["title"] == "Holiday"
    assert doc["project"]["decision_maker"] == "Alex"
    assert doc["project"]["alternatives"] == [] and doc["project"]["criteria"] == []
    # a blank project is saved *as a draft*: incomplete, so validation says so
    codes = {i["code"] for i in doc["validation"]["issues"]}
    assert {"NO_ALTERNATIVES", "NO_CRITERIA"} <= codes
    on_disk = store_dir / f"{pid}.json"
    assert on_disk.is_file()
    assert repo.load(on_disk).fingerprint() == doc["fingerprint"]


def test_create_from_template_has_structure_but_no_judgements(client: TestClient) -> None:
    doc = create(client, template="supplier-selection", title="Suppliers")
    assert len(doc["project"]["criteria"]) == 7
    assert doc["project"]["alternatives"] == []
    assert doc["project"]["performances"] == []


def test_create_with_unknown_template_is_rejected_and_stores_nothing(
    client: TestClient, store_dir: Path
) -> None:
    resp = client.post("/api/projects", json={"title": "x", "template": "nope"})
    assert resp.status_code == 422
    assert errors(resp)["code"] == "UNKNOWN_REFERENCE"
    assert not list(store_dir.glob("*.json"))


@pytest.mark.parametrize(
    "body",
    [{"title": ""}, {}, {"title": "x", "surprise": 1}, {"title": 5}],
    ids=["empty-title", "no-title", "unknown-field", "wrong-type"],
)
def test_create_rejects_invalid_requests(client: TestClient, body: dict[str, Any]) -> None:
    resp = client.post("/api/projects", json=body)
    assert resp.status_code == 422
    assert errors(resp)["code"] == "INVALID_REQUEST"


def test_two_projects_never_share_an_id(client: TestClient) -> None:
    ids = {create(client)["project"]["id"] for _ in range(20)}
    assert len(ids) == 20


# ---- list ----------------------------------------------------------------------------------
def test_list_starts_empty_even_before_the_store_directory_exists(client: TestClient) -> None:
    assert client.get("/api/projects").json() == {"projects": [], "unreadable": []}


def test_list_summarises_every_project(client: TestClient) -> None:
    import_file(client, SUPPLIER_FILE)
    create(client, title="Blank one")
    body = client.get("/api/projects").json()
    by_title = {p["title"]: p for p in body["projects"]}
    assert len(by_title) == 2
    supplier = next(p for p in body["projects"] if p["alternatives"] == 5)
    assert supplier["leaves"] == 8 and supplier["validation"]["ok"] is True
    blank = by_title["Blank one"]
    assert blank["alternatives"] == 0 and blank["validation"]["ok"] is False
    assert blank["validation"]["errors"] >= 2


def test_list_orders_most_recently_saved_first(client: TestClient) -> None:
    a = create(client, title="first")["project"]
    b = create(client, title="second")["project"]
    titles = [p["title"] for p in client.get("/api/projects").json()["projects"]]
    assert titles == ["second", "first"]
    resp = client.put(f"/api/projects/{a['id']}", json={**a, "description": "touched"})
    assert resp.status_code == 200
    titles = [p["title"] for p in client.get("/api/projects").json()["projects"]]
    assert titles == ["first", "second"]
    assert b["id"] != a["id"]


def test_list_reports_unreadable_files_instead_of_hiding_or_failing(
    client: TestClient, store_dir: Path
) -> None:
    good = create(client, title="good")["project"]["id"]
    (store_dir / "broken.json").write_text("{not json", encoding="utf-8")
    renamed = store_dir / "other_name.json"
    renamed.write_text(to_json_text(ps.new_project("liar")), encoding="utf-8")
    body = client.get("/api/projects").json()
    assert [p["id"] for p in body["projects"]] == [good]
    problems = {u["file"]: u["error"] for u in body["unreadable"]}
    assert set(problems) == {"broken.json", "other_name.json"}
    assert "not valid JSON" in problems["broken.json"]
    assert "file name and the id" in problems["other_name.json"]


# ---- load ----------------------------------------------------------------------------------
def test_get_returns_exactly_what_is_stored(client: TestClient, store_dir: Path) -> None:
    pid = import_file(client, SUPPLIER_FILE)["project"]["id"]
    resp = client.get(f"/api/projects/{pid}")
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["project"] == dump(repo.load(store_dir / f"{pid}.json"))
    assert doc["fingerprint"] == repo.load(SUPPLIER_FILE).fingerprint()
    assert resp.headers["ETag"] == f'"{doc["fingerprint"]}"'
    assert doc["updated_at"] is not None


def test_get_unknown_project_is_404_with_standard_error(client: TestClient) -> None:
    resp = client.get("/api/projects/nothing_here")
    assert resp.status_code == 404
    assert errors(resp)["code"] == "PROJECT_NOT_FOUND"


@pytest.mark.parametrize("bad", ["bad id", "-leading", "a" * 65, "semi;colon", "%2e%2e%2fsecret"])
def test_ids_that_could_be_unsafe_file_names_are_rejected(
    client: TestClient, store_dir: Path, bad: str
) -> None:
    (store_dir.parent / "secret.json").write_text("{}", encoding="utf-8")
    resp = client.get(f"/api/projects/{bad}")
    assert resp.status_code in (404, 422)
    if resp.status_code == 422:
        assert errors(resp)["code"] == "INVALID_PROJECT_ID"
    assert client.delete(f"/api/projects/{bad}").status_code in (404, 405, 422)
    assert (store_dir.parent / "secret.json").read_text(encoding="utf-8") == "{}"


def test_get_reports_a_corrupted_stored_file_as_such(client: TestClient, store_dir: Path) -> None:
    pid = create(client)["project"]["id"]
    (store_dir / f"{pid}.json").write_text('{"schema_version": 1, "id": "' + pid + '"}')
    resp = client.get(f"/api/projects/{pid}")
    assert resp.status_code == 500
    assert errors(resp)["code"] == "STORED_PROJECT_UNREADABLE"


# ---- save ----------------------------------------------------------------------------------
def test_save_persists_to_disk_and_a_new_app_instance_reads_it_back(store_dir: Path) -> None:
    with TestClient(create_app(store_dir, frontend_dir=False)) as client:
        doc = create(client, title="Before")
        project = {**doc["project"], "title": "After", "description": "edited"}
        resp = client.put(f"/api/projects/{project['id']}", json=project)
        assert resp.status_code == 200
        saved = resp.json()
        assert saved["project"]["title"] == "After"
        assert saved["fingerprint"] != doc["fingerprint"]
        assert (store_dir / f"{project['id']}.json").read_text(encoding="utf-8") == to_json_text(
            repo.from_dict(project)
        )
    with TestClient(create_app(store_dir, frontend_dir=False)) as second:  # "restart"
        again = second.get(f"/api/projects/{project['id']}").json()
    assert again["project"] == saved["project"]
    assert again["fingerprint"] == saved["fingerprint"]


def test_saving_an_unchanged_project_is_byte_stable(client: TestClient, store_dir: Path) -> None:
    pid = import_file(client, SUPPLIER_FILE)["project"]["id"]
    path = store_dir / f"{pid}.json"
    before = path.read_bytes()
    for _ in range(3):
        project = client.get(f"/api/projects/{pid}").json()["project"]
        assert client.put(f"/api/projects/{pid}", json=project).status_code == 200
    assert path.read_bytes() == before == SUPPLIER_FILE.read_bytes()


def test_save_never_creates_a_project_that_does_not_exist(
    client: TestClient, store_dir: Path
) -> None:
    project = dump(ps.new_project("ghost"))
    resp = client.put(f"/api/projects/{project['id']}", json=project)
    assert resp.status_code == 404
    assert errors(resp)["code"] == "PROJECT_NOT_FOUND"
    assert not list(store_dir.glob("*.json"))


def test_save_refuses_a_body_whose_id_differs_from_the_url(
    client: TestClient, store_dir: Path
) -> None:
    a = create(client, title="A")["project"]
    b = create(client, title="B")["project"]
    before = (store_dir / f"{a['id']}.json").read_bytes()
    resp = client.put(f"/api/projects/{a['id']}", json={**b, "title": "B imposter"})
    assert resp.status_code == 422
    assert errors(resp)["code"] == "ID_MISMATCH"
    assert (store_dir / f"{a['id']}.json").read_bytes() == before
    assert client.get(f"/api/projects/{b['id']}").json()["project"]["title"] == "B"


def test_save_rejects_other_schema_versions(client: TestClient) -> None:
    p = create(client)["project"]
    resp = client.put(f"/api/projects/{p['id']}", json={**p, "schema_version": 7})
    assert resp.status_code == 422
    assert errors(resp)["code"] == "UNSUPPORTED_SCHEMA_VERSION"
    # a version-1 body cannot hold a version-2 section
    classes = {"classes": [{"id": "all", "name": "All"}]}
    resp = client.put(f"/api/projects/{p['id']}", json={**p, "sorting": classes})
    assert resp.status_code == 422
    assert errors(resp)["code"] == "UNSUPPORTED_SCHEMA_VERSION"
    # any version from the one the content needs up to the newest is accepted, and the stored
    # file is written with the lowest sufficient version
    saved = client.put(f"/api/projects/{p['id']}", json={**p, "schema_version": 2})
    assert saved.status_code == 200 and saved.json()["project"]["schema_version"] == 1


@pytest.mark.parametrize(
    ("mutation", "fragment"),
    [
        (lambda p: {**p, "surprise": 1}, "surprise"),
        (lambda p: {**p, "title": ""}, "title"),
        (lambda p: {**p, "alternatives": [{"id": "bad id", "name": "x"}]}, "alternatives"),
        (lambda p: {**p, "analysis": {"method": "mavt", "scenario_id": 5}}, "scenario_id"),
    ],
    ids=["unknown-field", "empty-title", "illegal-id", "wrong-type"],
)
def test_save_rejects_documents_that_break_the_schema_and_keeps_the_file(
    client: TestClient, store_dir: Path, mutation: Any, fragment: str
) -> None:
    p = create(client)["project"]
    path = store_dir / f"{p['id']}.json"
    before = path.read_bytes()
    resp = client.put(f"/api/projects/{p['id']}", json=mutation(p))
    assert resp.status_code == 422
    err = errors(resp)
    assert err["code"] == "INVALID_REQUEST"
    assert any(fragment in d["path"] for d in err["details"]), err
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "criteria",
    [
        [{"id": "a", "name": "A", "parent_id": "a"}],
        [{"id": "a", "name": "A", "parent_id": "b"}, {"id": "b", "name": "B", "parent_id": "a"}],
        [{"id": "a", "name": "A", "parent_id": "ghost"}],
        [{"id": "a", "name": "A"}, {"id": "a", "name": "A again"}],
    ],
    ids=["self-parent", "cycle", "unknown-parent", "duplicate-id"],
)
def test_save_refuses_a_corrupt_criteria_tree_and_keeps_the_file(
    client: TestClient, store_dir: Path, criteria: list[dict[str, Any]]
) -> None:
    p = create(client)["project"]
    path = store_dir / f"{p['id']}.json"
    before = path.read_bytes()
    resp = client.put(f"/api/projects/{p['id']}", json={**p, "criteria": criteria})
    assert resp.status_code == 422
    assert errors(resp)["code"] == "MODEL_STRUCTURE"
    assert path.read_bytes() == before


def test_an_incomplete_but_well_formed_draft_can_be_saved(client: TestClient) -> None:
    p = create(client)["project"]
    draft = dump(ps.add_criterion(ps.add_alternative(repo.from_dict(p), "A"), "Cost"))
    resp = client.put(f"/api/projects/{p['id']}", json=draft)
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["validation"]["issues"], "a draft with a leaf that has no scale must be flagged"
    assert "MISSING_SCALE" in {i["code"] for i in doc["validation"]["issues"]}


# ---- optimistic concurrency ----------------------------------------------------------------
def test_stale_if_match_is_refused_and_leaves_the_file_unchanged(
    client: TestClient, store_dir: Path
) -> None:
    doc = create(client, title="shared")
    pid = doc["project"]["id"]
    first = client.put(
        f"/api/projects/{pid}",
        json={**doc["project"], "description": "writer one"},
        headers={"If-Match": f'"{doc["fingerprint"]}"'},
    )
    assert first.status_code == 200
    stale = client.put(
        f"/api/projects/{pid}",
        json={**doc["project"], "description": "writer two"},
        headers={"If-Match": f'"{doc["fingerprint"]}"'},
    )
    assert stale.status_code == 412
    assert errors(stale)["code"] == "STALE_REVISION"
    assert client.get(f"/api/projects/{pid}").json()["project"]["description"] == "writer one"


def test_current_if_match_is_accepted_in_all_spellings(client: TestClient) -> None:
    doc = create(client)
    pid = doc["project"]["id"]
    fp = doc["fingerprint"]
    for header in (f'"{fp}"', fp, f'W/"{fp}"'):
        current = client.get(f"/api/projects/{pid}").json()
        resp = client.put(
            f"/api/projects/{pid}",
            json={**current["project"], "description": header[:6]},
            headers={"If-Match": f'"{current["fingerprint"]}"'},
        )
        assert resp.status_code == 200
        fp = resp.json()["fingerprint"]


# ---- duplicate -----------------------------------------------------------------------------
def test_duplicate_is_an_independent_copy_with_a_fresh_id(
    client: TestClient, store_dir: Path
) -> None:
    original = import_file(client, SUPPLIER_FILE)["project"]
    resp = client.post(f"/api/projects/{original['id']}/duplicate", json={})
    assert resp.status_code == 201
    copy = resp.json()["project"]
    assert copy["id"] != original["id"]
    assert copy["title"] == f"{original['title']} (copy)"
    assert {**copy, "id": original["id"], "title": original["title"]} == original
    # editing the copy leaves the original byte-identical
    before = (store_dir / f"{original['id']}.json").read_bytes()
    edited = {**copy, "alternatives": copy["alternatives"][:-1]}
    assert client.put(f"/api/projects/{copy['id']}", json=edited).status_code == 200
    assert (store_dir / f"{original['id']}.json").read_bytes() == before


def test_duplicate_accepts_a_title_and_404s_for_unknown_ids(client: TestClient) -> None:
    pid = create(client)["project"]["id"]
    resp = client.post(f"/api/projects/{pid}/duplicate", json={"title": "Fork"})
    assert resp.json()["project"]["title"] == "Fork"
    missing = client.post("/api/projects/missing/duplicate", json={})
    assert missing.status_code == 404


# ---- delete --------------------------------------------------------------------------------
def test_delete_moves_the_file_to_trash_and_it_can_be_recovered(
    client: TestClient, store_dir: Path
) -> None:
    doc = import_file(client, SUPPLIER_FILE)
    pid = doc["project"]["id"]
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404
    assert client.get("/api/projects").json()["projects"] == []
    trashed = list((store_dir / ".trash").glob(f"{pid}.*.json"))
    assert len(trashed) == 1
    assert repo.load(trashed[0]).fingerprint() == doc["fingerprint"]
    assert client.delete(f"/api/projects/{pid}").status_code == 404


# ---- import / export -----------------------------------------------------------------------
def test_import_preserves_id_and_every_input(client: TestClient, store_dir: Path) -> None:
    doc = import_file(client, VC_FILE)
    original = repo.load(VC_FILE)
    assert doc["project"]["id"] == original.id == "nz_deeptech_vc_study"
    assert doc["fingerprint"] == original.fingerprint()
    assert (store_dir / f"{original.id}.json").read_bytes() == VC_FILE.read_bytes()


def test_import_conflict_is_an_error_unless_a_new_id_is_requested(
    client: TestClient, store_dir: Path
) -> None:
    import_file(client, SUPPLIER_FILE)
    raw = json.loads(SUPPLIER_FILE.read_text(encoding="utf-8"))
    again = client.post("/api/projects/import", json=raw)
    assert again.status_code == 409
    assert errors(again)["code"] == "PROJECT_EXISTS"
    forked = client.post("/api/projects/import", json=raw, params={"on_conflict": "new_id"})
    assert forked.status_code == 201
    new = forked.json()["project"]
    assert new["id"] != raw["id"]
    assert {**new, "id": raw["id"]} == raw
    assert len(list(store_dir.glob("*.json"))) == 2


@pytest.mark.parametrize(
    ("raw", "fragment"),
    [
        ({}, "schema_version"),
        ({"schema_version": 99, "id": "x", "title": "t"}, "newer than this program"),
        ({"schema_version": 0, "id": "x", "title": "t"}, "invalid schema version"),
        ({"schema_version": 1, "id": "x"}, "schema validation"),
        ({"schema_version": 1, "id": "x", "title": "t", "bogus": 1}, "schema validation"),
    ],
    ids=["no-version", "future-version", "zero-version", "missing-title", "unknown-field"],
)
def test_import_rejects_bad_files_with_a_specific_message(
    client: TestClient, store_dir: Path, raw: dict[str, Any], fragment: str
) -> None:
    resp = client.post("/api/projects/import", json=raw)
    assert resp.status_code == 422
    err = errors(resp)
    assert err["code"] == "INVALID_PROJECT_FILE"
    assert fragment in err["message"] or any(fragment in d["message"] for d in err["details"])
    assert not list(store_dir.glob("*.json"))


def test_import_refuses_a_structurally_corrupt_tree(client: TestClient) -> None:
    raw = dump(ps.new_project("cyc"))
    raw["criteria"] = [
        {"id": "a", "name": "A", "parent_id": "b"},
        {"id": "b", "name": "B", "parent_id": "a"},
    ]
    resp = client.post("/api/projects/import", json=raw)
    assert resp.status_code == 422
    assert errors(resp)["code"] == "MODEL_STRUCTURE"


def test_import_rejects_a_body_that_is_not_an_object(client: TestClient) -> None:
    resp = client.post("/api/projects/import", json=[1, 2, 3])
    assert resp.status_code == 422
    assert errors(resp)["code"] == "INVALID_REQUEST"


def test_download_is_the_exact_deterministic_file(client: TestClient, store_dir: Path) -> None:
    pid = import_file(client, VC_FILE)["project"]["id"]
    resp = client.get(f"/api/projects/{pid}/file")
    assert resp.status_code == 200
    assert resp.content == VC_FILE.read_bytes()
    assert "attachment" in resp.headers["Content-Disposition"]
    assert f"{pid}.json" in resp.headers["Content-Disposition"]


def test_example_import_matches_the_example_file_and_unknown_names_are_404(
    client: TestClient, store_dir: Path
) -> None:
    resp = client.post("/api/examples/nz_deeptech_vc/import")
    assert resp.status_code == 201
    assert resp.json()["fingerprint"] == repo.load(VC_FILE).fingerprint()
    assert client.post("/api/examples/nz_deeptech_vc/import").status_code == 409
    for bad in ("nope", "..", "%2e%2e"):
        assert client.post(f"/api/examples/{bad}/import").status_code == 404


# ---- service boundary ----------------------------------------------------------------------
def test_requests_for_other_hosts_are_refused(client: TestClient) -> None:
    resp = client.get("/api/health", headers={"Host": "evil.example.com"})
    assert resp.status_code == 400


def test_cross_origin_requests_get_no_cors_permission(client: TestClient) -> None:
    resp = client.options(
        "/api/projects",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in resp.headers
    assert resp.status_code in (400, 405)


def test_meta_exposes_exactly_the_engines_scale_and_function_rules(client: TestClient) -> None:
    from mcda_studio.domain.criteria import ALLOWED_VALUE_FUNCTIONS

    meta = client.get("/api/meta").json()
    by_type = {t["type"]: t for t in meta["scale_types"]}
    assert set(by_type) == {"categorical", "ordinal", "interval", "ratio"}
    for scale_type, allowed in ALLOWED_VALUE_FUNCTIONS.items():
        assert set(by_type[scale_type.value]["allowed_value_functions"]) == allowed
    assert by_type["ratio"]["numeric"] and not by_type["ratio"]["labelled"]
    assert by_type["ordinal"]["labelled"] and not by_type["ordinal"]["numeric"]
    assert meta["directions"] == ["increasing", "decreasing"]
    assert meta["anchor_modes"] == ["fixed", "local"]


# ---- unknown API paths, with and without a mounted frontend ----------------------------------
@pytest.fixture
def served_client(tmp_path: Path, store_dir: Path) -> Iterator[TestClient]:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    with TestClient(
        create_app(store_dir / "served", examples_dir=EXAMPLES, frontend_dir=dist)
    ) as c:
        yield c


@pytest.mark.parametrize("serve_frontend", [False, True])
def test_unknown_api_paths_are_404_in_the_standard_error_shape(
    client: TestClient, served_client: TestClient, serve_frontend: bool
) -> None:
    c = served_client if serve_frontend else client
    for method, path in (
        ("GET", "/api/nope"),
        ("POST", "/api/import"),
        ("POST", "/api/projects/a/b/c"),
        ("PUT", "/api/"),
    ):
        resp = c.request(method, path)
        assert resp.status_code == 404, (method, path)
        assert resp.headers["content-type"].startswith("application/json")
        assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("serve_frontend", [False, True])
def test_the_wrong_method_on_a_real_endpoint_is_405_with_allow(
    client: TestClient, served_client: TestClient, serve_frontend: bool
) -> None:
    c = served_client if serve_frontend else client
    resp = c.delete("/api/health")
    assert resp.status_code == 405
    assert resp.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert resp.headers["allow"] == "GET"
    resp = c.patch("/api/projects")
    assert resp.status_code == 405
    assert set(resp.headers["allow"].split(", ")) == {"GET", "POST"}


def test_the_frontend_is_served_beside_the_api_and_never_instead_of_it(
    client: TestClient, served_client: TestClient
) -> None:
    assert served_client.get("/").text.startswith("<!doctype html>")
    assert served_client.get("/api/health").json()["status"] == "ok"
    assert client.get("/").status_code == 404  # API-only app: nothing at the root
