"""Checks of the typed-proposal runner (``scripts/typed_proposal_runner.py``).

Everything runs on an invented study and a local HTTP server on 127.0.0.1: no real page, no model
and no remote service is contacted, and a guard fails the test if anything tries. The integration
test imports the runner's exported proposals for the real venture study's project with the
application's own commands, with invented page text, to prove the contract needs no app change.
"""

import csv
import hashlib
import importlib.util
import io
import json
import math
import os
import subprocess
import sys
import threading
import time
import types
import urllib.parse
import urllib.request
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from synthetic_study import CANARIES, COMPANIES, FIVE_LEAVES, FOUR_LEAVES, invented_study

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load("typed_proposal_runner")
kit = _load("rater_kit")
bench = _load("classifier_agreement_benchmark")


@pytest.fixture(autouse=True)
def only_localhost(monkeypatch):
    """The gate has no network: any request to another host fails the test."""
    real = urllib.request.urlopen

    def guarded(request, *args, **kwargs):
        url = request if isinstance(request, str) else request.full_url
        host = urllib.parse.urlsplit(url).hostname
        assert host in {"127.0.0.1", "localhost"}, f"network request to {host}"
        return real(request, *args, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", guarded)
    monkeypatch.setattr(runner, "MIN_INTERVAL", 0.02)


# --- a local site ---------------------------------------------------------------------------------


class Site:
    """Serves ``pages`` (path -> (status, content type, body)) and records every request."""

    def __init__(self, pages, robots=None):
        self.pages, self.robots, self.hits = pages, robots, []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                site.hits.append((self.path, self.headers.get("User-Agent"), time.monotonic()))
                if self.path == "/robots.txt":
                    if site.robots is None:
                        self.send_response(404)
                        self.end_headers()
                        return
                    status, ctype, body = 200, "text/plain", site.robots.encode()
                else:
                    status, ctype, body = site.pages.get(self.path, (404, "text/plain", b"no"))
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def count(self, path):
        return sum(1 for hit in self.hits if hit[0] == path)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def page(text, extra=""):
    markup = (
        f"<html><head><title>Title of the page</title><style>.x{{color:red}}</style>"
        f"<script>var leak = 'SCRIPT-TEXT';</script></head><body>"
        f"<nav>NAVIGATION-TEXT <a href='/x'>menu</a></nav><div role='navigation'>ROLE-NAV</div>"
        f"<h1>Heading</h1><p>{text}</p>{extra}</body></html>"
    )
    return 200, "text/html; charset=utf-8", markup.encode()


@pytest.fixture
def site():
    pages = {}
    for alt, name in COMPANIES:
        for index in (0, 1):
            pages[f"/{alt}/{index}"] = page(
                f"{name} builds machines. Page {index}. " + "Filler sentence number one. " * 40
            )
    pages["/market-report"] = page("A market report about everything.")
    s = Site(pages)
    yield s
    s.close()


@pytest.fixture
def study(tmp_path, site):
    directory = tmp_path / "inputs"
    directory.mkdir()
    return invented_study(directory, site.url)


def run(argv):
    return runner.main([str(a) for a in argv])


def snapshot(study, out, refresh=False):
    args = ["snapshot", "--evidence", study["evidence"], "--out", out]
    return run(args + (["--refresh"] if refresh else []))


def questions(study, snaps, out, *extra, backend="replay"):
    return run(
        [
            "questions", "--project", study["project"], "--rubrics", study["rubrics"],
            "--evidence", study["evidence"], "--snapshots", snaps, "--backend", backend,
            "--out", out, *extra,
        ]
    )  # fmt: skip


def weights_for(question, index, top=8):
    options = question["options"]
    return {o: float(top if i == index else 1) for i, o in enumerate(options)}


def replay_file(path: Path, doc, choose=None):
    choose = choose or (lambda q: int(q["digest"][:4], 16) % len(q["labels"]))
    responses = {q["digest"]: weights_for(q, choose(q)) for q in doc["questions"]}
    path.write_text(json.dumps({"responses": responses}))
    return path


@pytest.fixture
def pipeline(tmp_path, study, site):
    snaps = tmp_path / "snaps"
    assert snapshot(study, snaps) == 0
    qpath = tmp_path / "questions.json"
    assert questions(study, snaps, qpath) == 0
    doc = json.loads(qpath.read_text())
    replay = replay_file(tmp_path / "replay.json", doc)
    out = tmp_path / "run"
    assert (
        run(["run", "--questions", qpath, "--backend", "replay", "--replay", replay, "--out", out])
        == 0
    )
    return {"snaps": snaps, "questions": qpath, "doc": doc, "replay": replay, "run": out}


# --- snapshot -------------------------------------------------------------------------------------


def test_snapshot_saves_pages_with_hashes_text_and_the_generic_client_name(tmp_path, study, site):
    assert snapshot(study, tmp_path / "s") == 0
    data = json.loads((tmp_path / "s" / "snapshots.json").read_text())
    assert data["licence"] == "unknown — private research copy, not for redistribution"
    assert "4 November 2026" in data["note"] and "later" in data["note"]
    rows = {row["url"]: row for row in data["snapshots"]}
    assert len(rows) == len(COMPANIES) * 2 + 1  # both pages per company and the market report
    for row in rows.values():
        assert row["outcome"] == "saved" and row["status"] == 200
        raw = (tmp_path / "s" / row["raw_file"]).read_bytes()
        text = (tmp_path / "s" / row["text_file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["raw_sha256"]
        assert hashlib.sha256(text).hexdigest() == row["text_sha256"]
        assert row["final_url"] == row["url"] and row["retrieved_at"].endswith("Z")
    text = (tmp_path / "s" / rows[f"{site.url}/co0/0"]["text_file"]).read_text()
    assert "Company A builds machines" in text and "Title of the page" in text
    for dropped in ("SCRIPT-TEXT", "NAVIGATION-TEXT", "ROLE-NAV", "color:red"):
        assert dropped not in text
    assert {hit[1] for hit in site.hits} == {"mcda-studio-research/0.1"}


def test_snapshot_is_polite_it_waits_between_requests_and_reads_robots_txt_first(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(runner, "MIN_INTERVAL", 0.15)
    s = Site(
        {"/a": page("one"), "/b": page("two"), "/c": page("three")},
        robots="User-agent: *\nDisallow: /b\n",
    )
    try:
        evidence = tmp_path / "e.json"
        claims = [
            {"alternative_id": "x", "criterion_id": "y", "source": {"reference": f"{s.url}{p}"}}
            for p in ("/a", "/b", "/c")
        ]
        evidence.write_text(json.dumps({"claims": claims}))
        assert run(["snapshot", "--evidence", evidence, "--out", tmp_path / "s"]) == 0
        paths = [hit[0] for hit in s.hits]
        assert paths[0] == "/robots.txt" and "/b" not in paths and paths.count("/robots.txt") == 1
        times = [hit[2] for hit in s.hits]
        assert all(
            later - earlier >= 0.14 for earlier, later in zip(times, times[1:], strict=False)
        )
        rows = {
            r["url"].rsplit("/", 1)[1]: r
            for r in json.loads((tmp_path / "s" / "snapshots.json").read_text())["snapshots"]
        }
        assert rows["b"]["outcome"] == "blocked_by_robots" and rows["b"]["raw_file"] is None
        assert rows["a"]["outcome"] == rows["c"]["outcome"] == "saved"
    finally:
        s.close()


def test_snapshot_skips_login_and_paywall_pages_and_records_errors_and_other_types(tmp_path):
    s = Site(
        {
            "/login": (401, "text/html", b"sign in"),
            "/paywall": (403, "text/html", b"subscribe"),
            "/gone": (404, "text/html", b"missing"),
            "/file.pdf": (200, "application/pdf", b"%PDF-1.4"),
            "/plain": (200, "text/plain", b"Plain text body"),
        }
    )
    try:
        evidence = tmp_path / "e.json"
        names = ("login", "paywall", "gone", "file.pdf", "plain")
        evidence.write_text(
            json.dumps(
                {
                    "claims": [
                        {
                            "alternative_id": "x",
                            "criterion_id": "y",
                            "source": {"reference": f"{s.url}/{n}"},
                        }
                        for n in names
                    ]
                }
            )
        )
        assert run(["snapshot", "--evidence", evidence, "--out", tmp_path / "s"]) == 0
        rows = {
            r["url"].rsplit("/", 1)[1]: r
            for r in json.loads((tmp_path / "s" / "snapshots.json").read_text())["snapshots"]
        }
        assert rows["login"]["outcome"] == rows["paywall"]["outcome"] == "skipped_login_or_paywall"
        assert rows["login"]["status"] == 401 and rows["paywall"]["raw_file"] is None
        assert rows["gone"]["outcome"] == "error" and rows["gone"]["status"] == 404
        assert (
            rows["file.pdf"]["outcome"] == "unsupported_content_type"
            and rows["file.pdf"]["text_file"] is None
        )
        assert rows["plain"]["outcome"] == "saved"
        assert (tmp_path / "s" / rows["plain"]["text_file"]).read_text() == "Plain text body"
    finally:
        s.close()


def test_snapshot_never_refetches_without_refresh(tmp_path, study, site):
    assert snapshot(study, tmp_path / "s") == 0
    first = len(site.hits)
    assert snapshot(study, tmp_path / "s") == 0
    assert len(site.hits) == first
    assert snapshot(study, tmp_path / "s", refresh=True) == 0
    assert len(site.hits) > first


def test_snapshot_is_refused_inside_the_repository(tmp_path, study, monkeypatch):
    fake = tmp_path / "fake-repo"
    fake.mkdir()
    monkeypatch.setattr(runner, "ROOT", fake.resolve())
    assert snapshot(study, fake / "s") == 2
    assert not (fake / "s").exists()


# --- questions ------------------------------------------------------------------------------------


def test_one_choice_question_per_company_and_criterion_with_all_cited_sources(pipeline):
    doc = pipeline["doc"]
    assert len(doc["questions"]) == len(COMPANIES) * (len(FIVE_LEAVES) + len(FOUR_LEAVES))
    q = next(x for x in doc["questions"] if x["question_id"] == "co3__f2")
    assert q["options"][-1] == "cannot tell" and q["options"][:-1] == q["labels"]
    assert "best-supported level" in q["rubric"] and "do not guess" in q["instruction"].lower()
    state = doc["states"]["co3"]
    assert [s["url"].rsplit("/", 2)[1:] for s in state["sources"]] == [["co3", "0"], ["co3", "1"]]
    assert (
        "Page 0" in state["state_text"] and "Page 1" in state["state_text"]
    )  # both pages, not one
    assert (
        "market report" not in state["state_text"].lower()
    )  # numeric-criterion pages are not cited
    assert doc["template_version"] == "typed-proposal-prompt.v1"
    for question in doc["questions"]:
        body = {k: v for k, v in question.items() if k != "digest"}
        assert question["digest"] == runner.digest(body)
    assert doc["digest"] == runner.digest({k: v for k, v in doc.items() if k != "digest"})


def test_nothing_the_author_wrote_reaches_the_questions(pipeline):
    text = pipeline["questions"].read_text()
    for canary in CANARIES:
        assert canary not in text
    assert "performances" not in text and "Strong" in text  # labels are offered, ratings are not


def test_the_budget_truncates_and_records_it(tmp_path, study, pipeline):
    out = tmp_path / "small.json"
    assert questions(study, pipeline["snaps"], out, "--budget-chars", "300") == 0
    doc = json.loads(out.read_text())
    assert doc["budget_chars"] == 300 and doc["truncations"]
    for state in doc["states"].values():
        assert all(s["chars_used"] <= 150 for s in state["sources"])
        assert all(s["truncated"] for s in state["sources"])
    full = pipeline["doc"]
    assert full["truncations"] == [] and doc["digest"] != full["digest"]


def test_redaction_replaces_listed_names_with_neutral_tokens(tmp_path, study, pipeline):
    names = tmp_path / "names.txt"
    names.write_text("Company A\ncompany b\n")
    out = tmp_path / "red.json"
    assert questions(study, pipeline["snaps"], out, "--redact", names) == 0
    doc = json.loads(out.read_text())
    text = doc["states"]["co0"]["state_text"]
    assert "Company A" not in text and "[NAME-1]" in text
    assert doc["states"]["co0"]["name"] == "[NAME-1]" and doc["states"]["co1"]["name"] == "[NAME-2]"
    assert doc["redaction"] == {"names": 2}


def test_questions_are_deterministic(tmp_path, study, pipeline):
    again = tmp_path / "again.json"
    assert questions(study, pipeline["snaps"], again) == 0
    assert again.read_bytes() == pipeline["questions"].read_bytes()


def test_a_snapshot_changed_on_disk_is_refused(tmp_path, study, pipeline):
    # A page the questions read: a company's own page, never the market report they skip. The
    # first file a directory lists depends on the filesystem, so it is not used to choose.
    rows = json.loads((pipeline["snaps"] / "snapshots.json").read_text())["snapshots"]
    row = min((r for r in rows if "/co0/" in r["url"]), key=lambda r: r["url"])
    first = pipeline["snaps"] / row["text_file"]
    first.write_text(first.read_text() + " tampered")
    assert questions(study, pipeline["snaps"], tmp_path / "x.json") == 2


# --- probabilities --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "weights",
    [
        {"a": 1.0, "b": 1.0, "c": 1.0},
        {"a": 0.1, "b": 0.2, "c": 0.7},
        {"a": 1e-9, "b": 3.0, "c": 2.0, "d": 0.5},
        {"a": 1.0, "b": 0.0},
        {"a": 0.333333333, "b": 0.333333333, "c": 0.333333334},
    ],
)
def test_probabilities_are_exact_decimals_that_sum_to_exactly_one(weights):
    order = list(weights)
    result = runner.quantize(weights, order)
    assert sum(result.values()) == Decimal(1)
    assert all(v >= 0 and v.as_tuple().exponent >= -runner.PLACES for v in result.values())
    total = sum(weights.values())
    for key, value in result.items():  # within one unit of the true share
        assert abs(float(value) - weights[key] / total) <= 1.5e-6


def test_quantisation_is_stable_and_breaks_ties_by_option_order():
    weights = {"a": 1.0, "b": 1.0, "c": 1.0}
    result = runner.quantize(weights, ["a", "b", "c"])
    assert [str(result[k]) for k in "abc"] == ["0.333334", "0.333333", "0.333333"]
    assert runner.quantize(weights, ["a", "b", "c"]) == result


def test_an_exact_tie_at_the_top_has_no_winner():
    probabilities = {"a": Decimal("0.4"), "b": Decimal("0.4"), "c": Decimal("0.2")}
    assert runner.top_option(probabilities, ["a", "b", "c"]) == (None, True)
    assert runner.top_option(
        {"a": Decimal("0.5"), "b": Decimal("0.3"), "c": Decimal("0.2")}, ["a", "b", "c"]
    ) == ("a", False)


def test_negative_and_zero_scores_are_refused():
    with pytest.raises(runner.RunnerError):
        runner.quantize({"a": -1.0, "b": 2.0}, ["a", "b"])
    with pytest.raises(runner.RunnerError):
        runner.quantize({"a": 0.0, "b": 0.0}, ["a", "b"])


# --- run (replay) ---------------------------------------------------------------------------------


def test_replay_run_writes_responses_probabilities_and_a_complete_manifest(pipeline):
    out = pipeline["run"]
    manifest = json.loads((out / "run-manifest.json").read_text())
    for key in (
        "backend",
        "model",
        "template_version",
        "parameters",
        "started_at",
        "finished_at",
        "environment",
        "questions_digest",
        "raw_responses_sha256",
        "probabilities_sha256",
    ):
        assert key in manifest
    assert manifest["backend"] == "replay" and manifest["question_count"] == 60
    assert (
        hashlib.sha256((out / "probabilities.json").read_bytes()).hexdigest()
        == manifest["probabilities_sha256"]
    )
    rows = json.loads((out / "probabilities.json").read_text(), parse_float=Decimal)["rows"]
    assert len(rows) == 60
    for row in rows.values():
        assert sum(row["probabilities"].values()) == Decimal(1)
    lines = (out / "raw_responses.jsonl").read_text().splitlines()
    assert len(lines) == 60 and json.loads(lines[0])["backend"] == "replay"


def test_a_run_needs_a_new_directory_its_recording_and_an_intact_question_file(tmp_path, pipeline):
    args = [
        "run",
        "--questions",
        pipeline["questions"],
        "--backend",
        "replay",
        "--replay",
        pipeline["replay"],
    ]
    assert run([*args, "--out", pipeline["run"]]) == 2  # not empty
    assert (
        run(
            [
                "run",
                "--questions",
                pipeline["questions"],
                "--backend",
                "replay",
                "--out",
                tmp_path / "r2",
            ]
        )
        == 2
    )  # no --replay
    short = tmp_path / "short.json"
    responses = json.loads(pipeline["replay"].read_text())["responses"]
    responses.pop(next(iter(responses)))
    short.write_text(json.dumps({"responses": responses}))
    assert (
        run(
            [
                "run",
                "--questions",
                pipeline["questions"],
                "--backend",
                "replay",
                "--replay",
                short,
                "--out",
                tmp_path / "r3",
            ]
        )
        == 2
    )
    tampered = json.loads(pipeline["questions"].read_text())
    tampered["questions"][0]["rubric"] = "something else"
    # keep the file's own digest valid, so only the per-question digest can notice the change
    tampered["digest"] = runner.digest({k: v for k, v in tampered.items() if k != "digest"})
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(tampered))
    assert (
        run(
            [
                "run",
                "--questions",
                path,
                "--backend",
                "replay",
                "--replay",
                pipeline["replay"],
                "--out",
                tmp_path / "r4",
            ]
        )
        == 2
    )


def test_a_run_inside_the_repository_is_refused(tmp_path, pipeline, monkeypatch):
    fake = tmp_path / "fake-repo"
    fake.mkdir()
    monkeypatch.setattr(runner, "ROOT", fake.resolve())
    args = [
        "run",
        "--questions",
        pipeline["questions"],
        "--backend",
        "replay",
        "--replay",
        pipeline["replay"],
    ]
    assert run([*args, "--out", fake / "run"]) == 2
    assert not (fake / "run").exists()


def test_the_prompt_holds_only_rubric_labels_names_and_source_text(pipeline):
    doc = pipeline["doc"]
    q = doc["questions"][0]
    system, user, letters = runner.build_prompt(q, doc["states"][q["alternative_id"]])
    assert letters == [chr(65 + i) for i in range(len(q["options"]))]
    assert q["rubric"] in user and q["criterion_name"] in user and "cannot tell" in user
    for canary in CANARIES:
        assert canary not in system + user


# --- jev (a local mock of the documented endpoint) --------------------------------------------


class MockJev:
    def __init__(self, behaviour):
        self.requests, self.behaviour = [], behaviour
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                mock.requests.append((self.path, dict(self.headers), body))
                status, payload = mock.behaviour(len(mock.requests), body)
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1/systemone"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def good_answer(count, body):
    criteria = list(body["questions"]["answer"]["criteria"])
    probabilities = {
        name: (0.7 if i == 1 else 0.3 / (len(criteria) - 1)) for i, name in enumerate(criteria)
    }
    return 200, {
        "model": body["model"],
        "answers": {
            "answer": {
                "type": "choice",
                "choice": criteria[1],
                "confidence": 0.7,
                "probabilities": probabilities,
            }
        },
        "usage": {"input_tokens": 10, "output_tokens": 1},
    }


@pytest.fixture
def jev_questions(tmp_path, study, pipeline):
    out = tmp_path / "jev-questions.json"
    assert questions(study, pipeline["snaps"], out, backend="jev") == 0
    return out


def jev_run(questions_path, out, url, *flags):
    return run(
        [
            "run",
            "--questions",
            questions_path,
            "--backend",
            "jev",
            "--endpoint",
            url,
            "--limit",
            "3",
            "--out",
            out,
            *flags,
        ]
    )


def test_jev_client_sends_the_documented_request_with_a_bearer_key(
    tmp_path, jev_questions, monkeypatch
):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key-123")
    mock = MockJev(good_answer)
    try:
        assert jev_run(jev_questions, tmp_path / "j", mock.url, "--allow-network") == 0
        path, headers, body = mock.requests[0]
        assert path == "/v1/systemone"
        assert headers["Authorization"] == "Bearer test-key-123"
        assert headers["User-Agent"] == "mcda-studio-research/0.1"
        assert set(body) == {"model", "state", "questions"} and body["model"] == "jev-1.13.0"
        question = body["questions"]["answer"]
        assert question["type"] == "choice" and set(question) == {
            "type",
            "instructions",
            "criteria",
        }
        doc = json.loads(jev_questions.read_text())
        assert list(question["criteria"]) == doc["questions"][0]["options"]
        assert "Text about" in body["state"]
        for _, _, sent in mock.requests:  # the leakage canary, on every request body
            for canary in CANARIES:
                assert canary not in json.dumps(sent)
        manifest = json.loads((tmp_path / "j" / "run-manifest.json").read_text())
        assert manifest["backend"] == "jev" and manifest["model"]["id"] == "jev-1.13.0"
        assert (
            "test-key-123"
            not in json.dumps(manifest) + (tmp_path / "j" / "raw_responses.jsonl").read_text()
        )
    finally:
        mock.close()


def test_jev_refuses_without_allow_network_or_a_key_and_sends_nothing(
    tmp_path, jev_questions, monkeypatch
):
    mock = MockJev(good_answer)
    try:
        monkeypatch.setenv("TYPESAFE_API_KEY", "k")
        assert jev_run(jev_questions, tmp_path / "a", mock.url) == 2
        monkeypatch.delenv("TYPESAFE_API_KEY")
        assert jev_run(jev_questions, tmp_path / "b", mock.url, "--allow-network") == 2
        assert mock.requests == []
    finally:
        mock.close()


def test_jev_retries_a_server_error_and_refuses_bad_answers(tmp_path, jev_questions, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(runner.JevBackend, "__init__", _fast_init(runner.JevBackend.__init__))
    flaky = MockJev(lambda n, body: (500, {}) if n == 1 else good_answer(n, body))
    try:
        assert (
            jev_run(
                jev_questions, tmp_path / "ok", flaky.url, "--allow-network",
                "--order-averaging", "none",
            )
            == 0
        )  # fmt: skip
        assert len(flaky.requests) == 4  # one retry, then three questions in one order each
    finally:
        flaky.close()
    for index, behaviour in enumerate(
        [
            lambda n, b: (401, {}),
            lambda n, b: (200, {"answers": {}}),
            lambda n, b: (
                200,
                {"answers": {"answer": {"type": "choice", "probabilities": {"x": 1.0}}}},
            ),
            lambda n, b: (
                200,
                {
                    "answers": {
                        "answer": {
                            "type": "choice",
                            "probabilities": {k: 0.9 for k in b["questions"]["answer"]["criteria"]},
                        }
                    }
                },
            ),
            lambda n, b: (
                200,
                {
                    "answers": {
                        "answer": {
                            "type": "choice",
                            "probabilities": {
                                k: -0.1 if i == 0 else 0.5
                                for i, k in enumerate(b["questions"]["answer"]["criteria"])
                            },
                        }
                    }
                },
            ),
        ]
    ):
        mock = MockJev(behaviour)
        try:
            assert (
                jev_run(jev_questions, tmp_path / f"bad{index}", mock.url, "--allow-network") == 2
            ), index
        finally:
            mock.close()
    always_down = MockJev(lambda n, b: (503, {}))
    try:
        assert jev_run(jev_questions, tmp_path / "down", always_down.url, "--allow-network") == 2
    finally:
        always_down.close()


def _fast_init(original):
    def init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.delay = 0.0

    return init


def test_jev_will_not_use_a_plain_http_endpoint_on_another_host():
    with pytest.raises(runner.RunnerError):
        runner.JevBackend("http://example.org/v1/systemone", "m", "k")
    with pytest.raises(runner.RunnerError):
        runner.JevBackend("ftp://127.0.0.1/x", "m", "k")


def test_local_hf_and_laya_refuse_without_their_prerequisites(tmp_path, pipeline):
    base = ["run", "--questions", pipeline["questions"], "--out", tmp_path / "x"]
    assert run([*base, "--backend", "local-hf", "--model-path", tmp_path / "no-model"]) == 2
    assert run([*base, "--backend", "local-hf"]) == 2
    assert run([*base, "--backend", "laya"]) == 2


def test_the_model_download_needs_its_flag_and_only_the_named_model(tmp_path, monkeypatch):
    monkeypatch.delenv("MCDA_ALLOW_MODEL_DOWNLOAD", raising=False)
    assert run(["fetch-model", "--out", tmp_path / "m"]) == 2
    monkeypatch.setenv("MCDA_ALLOW_MODEL_DOWNLOAD", "1")
    assert run(["fetch-model", "--repo", "someone/else", "--out", tmp_path / "m"]) == 2
    assert not (tmp_path / "m").exists()


# --- export ---------------------------------------------------------------------------------------


def export(pipeline, out, project, threshold="0.5"):
    return run(
        [
            "export",
            "--run",
            pipeline["run"],
            "--project",
            project,
            "--threshold",
            threshold,
            "--out",
            out,
        ]
    )


def test_export_writes_the_published_csv_with_metadata_only_confidence(tmp_path, study, pipeline):
    out = tmp_path / "export"
    assert export(pipeline, out, study["project"]) == 0
    rows = list(csv.DictReader((out / "proposals.csv").open(newline="")))
    assert list(rows[0]) == runner.CSV_HEADER
    registries = json.loads((out / "registries.json").read_text())
    probabilities = json.loads(
        (pipeline["run"] / "probabilities.json").read_text(), parse_float=Decimal
    )["rows"]
    fingerprint = runner.project_fingerprint(study["project"])
    card_digest = hashlib.sha256((out / "model-card.json").read_bytes()).hexdigest()
    assert len(rows) == 60  # top weight 8 of at most 8+... always above 0.5 here
    for row in rows:
        assert (
            row["schema_version"] == "1"
            and row["proposal_version"] == "1"
            and row["kind"] == "categorical_cell"
        )
        assert row["project_fingerprint"] == fingerprint == registries["project_fingerprint"]
        payload = json.loads(row["payload_json"])
        assert payload["kind"] == "categorical_cell" and payload["unit"] is None
        confidence = json.loads(row["confidence_json"])
        assert confidence["scale"] == "unit_interval" and 0.5 <= confidence["value"] <= 1
        qid = row["proposal_id"].removeprefix("typed__")
        chosen = probabilities[qid]["probabilities"][payload["value"]]
        assert confidence["value"] == float(chosen)  # the model's own number, never rounded up
        assert payload["value"] == probabilities[qid]["top"]
        assert (
            confidence["meaning"]
            == "Tool-reported probability of the selected label; uncalibrated; metadata only"
        )
        assert (
            row["model_card_id"] in registries["model_cards"]
            and row["model_card_digest"] == card_digest
        )
        ids = json.loads(row["source_ids_json"])
        assert ids and all(i in registries["sources"] for i in ids)
        assert row["replaces_proposal_id"] == ""
    card = registries["model_cards"]["runner_model_card"]
    assert runner.digest(card) == card_digest  # the file's SHA-256 is the contract's digest
    for field in (
        "training_data_period",
        "population",
        "base_rate",
        "known_biases",
        "calibration",
        "licence",
        "source_references",
    ):
        assert field in card["details"]
    assert card["details"]["training_data_period"].startswith("unknown")


def test_cannot_tell_ties_and_low_confidence_make_no_proposal_and_are_listed(
    tmp_path, study, pipeline
):
    doc = pipeline["doc"]
    cannot = doc["questions"][0]
    tied = doc["questions"][1]
    weak = doc["questions"][2]
    responses = {}
    for q in doc["questions"]:
        responses[q["digest"]] = weights_for(q, 1)
    responses[cannot["digest"]] = {
        o: (9.0 if o == "cannot tell" else 1.0) for o in cannot["options"]
    }
    responses[tied["digest"]] = {
        o: (5.0 if i in (0, 1) else 1.0) for i, o in enumerate(tied["options"])
    }
    responses[weak["digest"]] = {o: 1.0 for o in weak["options"]} | {weak["options"][2]: 1.2}
    path = tmp_path / "mixed.json"
    path.write_text(json.dumps({"responses": responses}))
    assert (
        run(
            [
                "run",
                "--questions",
                pipeline["questions"],
                "--backend",
                "replay",
                "--replay",
                path,
                "--out",
                tmp_path / "r",
            ]
        )
        == 0
    )
    mixed = {**pipeline, "run": tmp_path / "r"}
    assert export(mixed, tmp_path / "e", study["project"]) == 0
    report = json.loads((tmp_path / "e" / "run-report.json").read_text())
    reasons = {a["question_id"]: a["reason"] for a in report["abstention_list"]}
    assert reasons[cannot["question_id"]] == "cannot tell"
    assert reasons[tied["question_id"]] == "tie"
    assert reasons[weak["question_id"]] == "below threshold"
    assert report["proposals"] == 60 - 3 and report["abstentions"] == 3
    assert "Nothing here compares the tool with any rating" in report["note"]
    proposed = {
        r["proposal_id"]
        for r in csv.DictReader((tmp_path / "e" / "proposals.csv").open(newline=""))
    }
    assert not any(f"typed__{q['question_id']}" in proposed for q in (cannot, tied, weak))
    per_leaf = report["per_criterion"]["f1"]
    assert per_leaf["questions"] == 10 and sum(per_leaf["labels"].values()) == per_leaf["proposed"]


def test_a_probability_exactly_at_the_threshold_still_proposes(tmp_path, study, pipeline):
    doc = pipeline["doc"]
    responses = {
        q["digest"]: {o: (1.0 if i == 0 else 0.0) for i, o in enumerate(q["options"])}
        for q in doc["questions"]
    }
    path = tmp_path / "sure.json"
    path.write_text(json.dumps({"responses": responses}))
    assert (
        run(
            [
                "run",
                "--questions",
                pipeline["questions"],
                "--backend",
                "replay",
                "--replay",
                path,
                "--out",
                tmp_path / "r",
            ]
        )
        == 0
    )
    sure = {**pipeline, "run": tmp_path / "r"}
    assert export(sure, tmp_path / "e", study["project"], threshold="1") == 0
    assert json.loads((tmp_path / "e" / "run-report.json").read_text())["proposals"] == 60


def test_export_writes_benchmark_tables_in_the_shape_the_benchmark_validates(
    tmp_path, study, pipeline
):
    out = tmp_path / "export"
    assert export(pipeline, out, study["project"]) == 0
    assert {p.name for p in out.glob("tool_outputs.*.json")} == {
        "tool_outputs.invented-4-level.json",
        "tool_outputs.invented-5-level.json",
    }
    rows = json.loads((out / "tool_outputs.invented-5-level.json").read_text(), parse_float=Decimal)
    assert len(rows) == 40
    card_digest = hashlib.sha256((out / "model-card.json").read_bytes()).hexdigest()
    proposed = {
        r["proposal_id"].removeprefix("typed__"): json.loads(r["payload_json"])["value"]
        for r in csv.DictReader((out / "proposals.csv").open(newline=""))
    }
    labels_of = {q["question_id"]: q["labels"] for q in pipeline["doc"]["questions"]}
    for row in rows:
        assert row["model_card_digest"] == card_digest and row["score"] is None
        assert row["label"] in {f"level_{i}" for i in range(1, 6)}
        qid = row["item_id"]  # the same cell, the same label, as a position
        assert row["label"] == f"level_{labels_of[qid].index(proposed[qid]) + 1}"
        assert list(row["probabilities"]) == [f"level_{i}" for i in range(1, 6)]
        assert sum(row["probabilities"].values()) == Decimal(1)  # exactly one, no tolerance


def test_the_exported_tables_run_through_the_benchmark_with_the_rater_kit(
    tmp_path, study, pipeline
):
    out = tmp_path / "export"
    assert export(pipeline, out, study["project"]) == 0
    kit_dir = tmp_path / "kit"
    assert (
        kit.main(
            [
                "make",
                "--project",
                str(study["project"]),
                "--rubrics",
                str(study["rubrics"]),
                "--evidence",
                str(study["evidence"]),
                "--seed",
                "3",
                "--out",
                str(kit_dir),
            ]
        )
        == 0
    )
    assert (
        kit.main(
            [
                "author-labels",
                "--project",
                str(study["project"]),
                "--items",
                str(kit_dir / "items.json"),
                "--reviewed-at",
                "2026-01-01T00:00:00Z",
                "--out",
                str(tmp_path / "r1"),
            ]
        )
        == 0
    )
    assert (
        kit.main(
            [
                "manifest",
                "--items",
                str(kit_dir / "items.json"),
                "--project",
                str(study["project"]),
                "--rubrics",
                str(study["rubrics"]),
                "--evidence",
                str(study["evidence"]),
                "--frozen-at",
                "2026-01-01T00:00:00Z",
                "--out",
                str(tmp_path / "bm"),
            ]
        )
        == 0
    )
    task = "invented-5-level"
    final = tmp_path / "final"
    assert (
        kit.main(
            [
                "finalize",
                "--protocol",
                str(tmp_path / "bm" / task / "frozen-protocol.json"),
                "--human-labels",
                str(tmp_path / "r1" / f"human_labels.{task}.R1.json"),
                "--tool-outputs",
                str(out / f"tool_outputs.{task}.json"),
                "--tool-card",
                str(out / "model-card.json"),
                "--tool-id",
                "typed-proposal-runner:replay",
                "--tool-version",
                "0.1+typed-proposal-prompt.v1",
                "--out",
                str(final),
            ]
        )
        == 0
    )
    items, human, outputs = bench.validate_tables(*_manifest_tables(final))
    assert len(outputs["typed-proposal-runner:replay"]) == 40


def _manifest_tables(final):
    manifest, data, _ = bench.load(final / "manifest.json")
    return manifest, data


def test_export_refuses_labels_that_are_not_the_projects_scale_and_in_repo_outputs(
    tmp_path, study, pipeline, monkeypatch
):
    project = json.loads(Path(study["project"]).read_text())
    project["criteria"][0]["scale"]["labels"] = ["A", "B", "C", "D", "E"]
    other = tmp_path / "other-project.json"
    other.write_text(json.dumps(project))
    assert export(pipeline, tmp_path / "e1", other) == 2
    assert not (tmp_path / "e1").exists()
    fake = tmp_path / "fake-repo"
    fake.mkdir()
    monkeypatch.setattr(runner, "ROOT", fake.resolve())
    assert export(pipeline, fake / "e2", study["project"]) == 2


def test_the_project_fingerprint_is_the_applications_own(study):
    from mcda_studio.storage.json_repository import JsonProjectRepository

    path = ROOT / "examples" / "nz_venture_screening" / "project.json"
    assert runner.project_fingerprint(path) == JsonProjectRepository().load(path).fingerprint()


# --- the contract needs no application change -------------------------------------------------


def test_the_real_study_proposals_import_and_preview_with_the_existing_commands(tmp_path):
    study_dir = ROOT / "examples" / "nz_venture_screening"
    rubrics = runner.load_rubrics(study_dir / "rubrics.json")
    snaps = tmp_path / "snaps"
    (snaps / "text").mkdir(parents=True)
    index = []
    for n, url in enumerate(runner.all_references(study_dir / "evidence.json")):
        text = f"Invented page text number {n} for testing only. " * 20
        name = hashlib.sha256(url.encode()).hexdigest()[:16]
        (snaps / "text" / f"{name}.txt").write_text(text)
        index.append(
            {
                "url": url,
                "outcome": "saved",
                "text_file": f"text/{name}.txt",
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            }
        )
    (snaps / "snapshots.json").write_text(json.dumps({"version": 1, "snapshots": index}))
    qpath = tmp_path / "q.json"
    assert (
        run(
            [
                "questions",
                "--project",
                study_dir / "project.json",
                "--rubrics",
                study_dir / "rubrics.json",
                "--evidence",
                study_dir / "evidence.json",
                "--snapshots",
                snaps,
                "--backend",
                "replay",
                "--out",
                qpath,
            ]
        )
        == 0
    )
    doc = json.loads(qpath.read_text())
    assert len(doc["questions"]) == 112 and len(rubrics["leaves"]) == 14
    replay = replay_file(
        tmp_path / "replay.json", doc, choose=lambda q: int(q["digest"][4:8], 16) % len(q["labels"])
    )
    assert (
        run(
            [
                "run",
                "--questions",
                qpath,
                "--backend",
                "replay",
                "--replay",
                replay,
                "--out",
                tmp_path / "run",
            ]
        )
        == 0
    )
    export_dir = tmp_path / "export"
    assert (
        run(
            [
                "export",
                "--run",
                tmp_path / "run",
                "--project",
                study_dir / "project.json",
                "--out",
                export_dir,
            ]
        )
        == 0
    )
    count = len(list(csv.DictReader((export_dir / "proposals.csv").open(newline=""))))
    assert count > 100
    workspace = tmp_path / "workspace.json"

    def mcda(*args):
        return subprocess.run(
            [sys.executable, "-m", "mcda_studio", "proposals", *args],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
        )

    project = str(study_dir / "project.json")
    imported = mcda(
        "import", project, str(export_dir / "proposals.csv"), "--format", "csv",
        "--registries", str(export_dir / "registries.json"), "--output", str(workspace),
    )  # fmt: skip
    assert imported.returncode == 0, imported.stdout + imported.stderr
    previewed = mcda("preview", project, str(workspace))
    assert previewed.returncode == 0, previewed.stdout + previewed.stderr
    text = previewed.stdout
    assert "typed__" in text and "typed-proposal-runner:replay" in text
    report = json.loads(text)
    print(sorted(report))


# --- name-swap check (paired questions and a run comparison) -----------------------------------


def write_swap(path: Path, rows, header="original,replacement"):
    path.write_text(header + "\n" + "".join(f"{a},{b}\n" for a, b in rows), encoding="utf-8")
    return path


def test_swap_replaces_names_in_the_page_text_and_gives_a_paired_question_set(
    tmp_path, study, pipeline
):
    swap = write_swap(tmp_path / "swap.csv", [("Company A", "Person One"), ("Filler", "Padding")])
    out = tmp_path / "swapped.json"
    assert questions(study, pipeline["snaps"], out, "--swap", swap) == 0
    doc, base = json.loads(out.read_text()), pipeline["doc"]
    text = doc["states"]["co0"]["state_text"]
    assert "Person One builds machines" in text and "Company A" not in text
    assert "Padding sentence" in text and "Filler" not in text
    assert doc["states"]["co0"]["name"] == "Person One"
    assert doc["swap"]["pairs"] == 2 and base["swap"] is None
    # a paired set: the same questions, with different digests only where the text changed
    assert [q["question_id"] for q in doc["questions"]] == [
        q["question_id"] for q in base["questions"]
    ]
    assert all(
        a["digest"] != b["digest"] for a, b in zip(doc["questions"], base["questions"], strict=True)
    )
    assert all(
        a["labels"] == b["labels"] and a["rubric"] == b["rubric"]
        for a, b in zip(doc["questions"], base["questions"], strict=True)
    )


def test_swap_applies_longest_names_first_and_never_chains():
    pairs = [("Ann", "X"), ("Ann Lee", "Y"), ("X", "Z")]
    assert runner.apply_swap("Ann Lee met Ann and X.", pairs) == "Y met X and Z."
    assert runner.apply_swap("unchanged", []) == "unchanged"
    assert runner.apply_swap("ann", [("Ann", "B")]) == "ann"  # exact and case-sensitive


def test_a_swap_file_needs_its_header_and_unique_names(tmp_path, study, pipeline):
    for index, content in enumerate(
        [
            "a,b\nx,y\n",
            "original,replacement\nx,y\nx,z\n",
            "original,replacement\nonly-one\n",
            "original,replacement\n,y\n",
        ]
    ):
        path = tmp_path / f"bad{index}.csv"
        path.write_text(content)
        assert questions(study, pipeline["snaps"], tmp_path / f"o{index}.json", "--swap", path) == 2


def test_the_committed_swap_template_parses_and_names_no_real_person():
    pairs = runner.read_replacements(
        ROOT / "examples" / "nz_venture_screening" / "swap-template.csv", header=True
    )
    assert pairs and all(a.startswith("Example") for a, _ in pairs)


def second_run(tmp_path, pipeline, changes):
    """A replay run whose answers equal the first run's, except where ``changes`` says otherwise."""
    doc = pipeline["doc"]
    responses = json.loads(pipeline["replay"].read_text())["responses"]
    for qid, weights in changes.items():
        digest_ = next(q["digest"] for q in doc["questions"] if q["question_id"] == qid)
        responses[digest_] = weights
    path = tmp_path / "second.json"
    path.write_text(json.dumps({"responses": responses}))
    out = tmp_path / "run2"
    argv = [
        "run",
        "--questions",
        pipeline["questions"],
        "--backend",
        "replay",
        "--replay",
        path,
        "--out",
        out,
    ]
    assert run(argv) == 0
    return out


def compare(a, b, out, *extra):
    return run(["compare-runs", a, b, "--out", out, *extra])


def test_identical_runs_have_no_differences(tmp_path, pipeline):
    same = second_run(tmp_path, pipeline, {})
    assert compare(pipeline["run"], same, tmp_path / "c.json") == 0
    report = json.loads((tmp_path / "c.json").read_text(), parse_float=Decimal)
    assert report["cells"] == 60 and report["top_label_changed"] == 0
    assert all(
        not c["top_changed"] and all(s == 0 for s in c["shifts"].values())
        for c in report["cell_detail"]
    )
    assert all(row["largest_shift"] == 0 for row in report["largest_shifts"])


def test_an_injected_change_is_detected_with_its_exact_shift(tmp_path, pipeline):
    doc = pipeline["doc"]
    target = next(q for q in doc["questions"] if q["question_id"] == "co2__f1")
    original = json.loads(pipeline["replay"].read_text())["responses"][target["digest"]]
    top = max(original, key=original.get)
    other = next(o for o in target["options"] if o != top)
    changed = second_run(
        tmp_path,
        pipeline,
        {"co2__f1": {o: (9.0 if o == other else 1.0) for o in target["options"]}},
    )
    assert compare(pipeline["run"], changed, tmp_path / "c.json", "--top", "3") == 0
    report = json.loads((tmp_path / "c.json").read_text(), parse_float=Decimal)
    assert report["top_label_changed"] == 1 and report["top_label_unchanged"] == 59
    cell = next(c for c in report["cell_detail"] if c["question_id"] == "co2__f1")
    assert cell["top_changed"] and cell["top_a"] == top and cell["top_b"] == other
    assert cell["shifts"][other] > 0 and cell["shifts"][top] < 0  # b minus a
    assert sum(cell["shifts"].values()) == 0  # both vectors sum to exactly one
    assert (
        report["largest_shifts"][0]["question_id"] == "co2__f1"
        and len(report["largest_shifts"]) == 3
    )
    assert report["largest_shifts"][0]["largest_shift"] == cell["largest_shift"]


def test_runs_that_answered_different_questions_are_not_compared(tmp_path, study, pipeline):
    other_q = tmp_path / "other-q.json"
    assert questions(study, pipeline["snaps"], other_q, "--budget-chars", "300") == 0
    other_doc = json.loads(other_q.read_text())
    replay = replay_file(tmp_path / "other-replay.json", other_doc)
    assert (
        run(
            [
                "run",
                "--questions",
                other_q,
                "--backend",
                "replay",
                "--replay",
                replay,
                "--limit",
                "10",
                "--out",
                tmp_path / "r10",
            ]
        )
        == 0
    )
    assert compare(pipeline["run"], tmp_path / "r10", tmp_path / "c.json") == 2


def test_comparison_reports_inside_the_repository_are_refused(tmp_path, pipeline, monkeypatch):
    same = second_run(tmp_path, pipeline, {})
    fake = tmp_path / "fake-repo"
    fake.mkdir()
    monkeypatch.setattr(runner, "ROOT", fake.resolve())
    assert compare(pipeline["run"], same, fake / "c.json") == 2
    assert not (fake / "c.json").exists()


# --- option-order averaging -----------------------------------------------------------------------


def options_for(n):
    return [f"label {i + 1}" for i in range(n - 1)] + ["cannot tell"]


def true_weights(options):
    raw = {o: float(index + 1) for index, o in enumerate(options)}
    total = sum(raw.values())
    return {o: v / total for o, v in raw.items()}


@pytest.mark.parametrize("n", [5, 6])
def test_each_rotations_letters_map_back_to_their_options_for_five_and_six_options(n):
    import math

    options = options_for(n)
    weights = true_weights(options)

    def position_free(order):
        return [math.log(weights[o]) for o in order]

    scores, record = runner.average_over_orders(options, position_free)
    for option in options:  # a model with no position preference is left exactly as it is
        assert scores[option] == pytest.approx(weights[option], abs=1e-12)
    assert [r["shift"] for r in record["orders"]] == list(range(n))
    letters = [chr(ord("A") + i) for i in range(n)]
    for rotation in record["orders"]:
        shift = rotation["shift"]
        by_letter = rotation["options_by_letter"]
        assert list(by_letter) == letters  # letters stay A, B, C... in display order
        assert by_letter["A"] == options[shift]  # the option at index `shift` comes first
        assert by_letter[letters[-1]] == options[shift - 1]  # the one before it comes last
        assert sorted(by_letter.values()) == sorted(options)
        assert list(rotation["log_probabilities"]) == letters
        for letter, option in by_letter.items():
            assert rotation["log_probabilities"][letter] == pytest.approx(math.log(weights[option]))
    assert {r["options_by_letter"]["A"] for r in record["orders"]} == set(options)  # every start
    assert any(r["options_by_letter"]["A"] == "cannot tell" for r in record["orders"])
    assert record["order_top_agreement"] == 1.0 and record["order_max_shift"] == pytest.approx(0.0)


@pytest.mark.parametrize("n", [5, 6])
def test_a_position_biased_model_is_corrected_exactly_by_the_average(n):
    import math

    options = options_for(n)
    true = true_weights(options)
    beta = 0.6  # the model puts this share of its mass on whatever sits under letter A

    def biased(order):
        return [
            math.log((1 - beta) * true[o] + (beta if index == 0 else 0.0))
            for index, o in enumerate(order)
        ]

    # With one order the model simply answers "A": the option shown first, whatever the text says.
    single = runner.single_order_scores(options, biased(options), 10)[0]
    assert runner.first_max(options, single) == options[0] != runner.first_max(options, true)
    scores, record = runner.average_over_orders(options, biased)
    for option in options:  # every option, "cannot tell" included, is the same affine map of truth
        assert scores[option] == pytest.approx((1 - beta) * true[option] + beta / n, abs=1e-12)
    assert runner.first_max(options, scores) == runner.first_max(options, true)
    # Only the rotation that happens to put the true top under A agrees with the average.
    assert record["order_top_agreement"] == pytest.approx(1 / n)
    assert record["order_max_shift"] == pytest.approx(beta)
    quantised = runner.quantize(scores, options)
    assert sum(quantised.values()) == 1 and all(v >= 0 for v in quantised.values())


def test_the_averaged_probabilities_are_exact_decimals_that_sum_to_exactly_one():
    import math

    options = options_for(6)
    odd = [0.3, -1.2, -0.7, -2.9, -0.1, -3.3]

    def lopsided(order):
        return [odd[(index + len(order[0])) % 6] for index in range(6)]

    scores, _ = runner.average_over_orders(options, lopsided)
    exact = runner.quantize(scores, options)
    assert sum(exact.values()) == Decimal(1)
    assert all(exact[o].as_tuple().exponent >= -6 for o in options)
    assert math.isclose(sum(scores.values()), 1.0, abs_tol=1e-12)


def test_rotation_is_cyclic_and_wrong_numbers_of_letters_are_refused():
    assert runner.rotated(["a", "b", "c", "d"], 0) == ["a", "b", "c", "d"]
    assert runner.rotated(["a", "b", "c", "d"], 1) == ["b", "c", "d", "a"]
    assert runner.rotated(["a", "b", "c", "d"], 3) == ["d", "a", "b", "c"]
    with pytest.raises(runner.RunnerError, match="wrong number of letters"):
        runner.average_over_orders(["a", "b", "c"], lambda order: [0.0, 0.0])


def fake_local(order_averaging, log_probabilities):
    """A LocalHfBackend whose model is a function of the display order: no torch, no weights."""
    backend = object.__new__(runner.LocalHfBackend)
    backend.order_averaging = order_averaging
    backend.letter_log_probabilities = lambda question, state, order: (
        log_probabilities(order),
        100 + len(order),
    )
    return backend


QUESTION = {"options": options_for(5), "question_id": "q"}


def test_the_none_path_is_the_previous_single_order_scoring_exactly():
    import math

    chosen = [-0.4, -1.3, -2.2, -0.9, -3.1]
    backend = fake_local("none", lambda order: chosen)
    scores, raw = backend.score(QUESTION, {})
    peak = max(chosen)  # the version-1 arithmetic, written out
    weights = [math.exp(c - peak) for c in chosen]
    total = sum(weights)
    expected = {o: w / total for o, w in zip(QUESTION["options"], weights, strict=True)}
    assert scores == expected  # identical floats, not close ones
    assert raw == {
        "letters": ["A", "B", "C", "D", "E"],
        "log_probabilities": dict(zip("ABCDE", chosen, strict=True)),
        "prompt_tokens": 105,
    }
    assert runner.quantize(scores, QUESTION["options"]) == runner.quantize(
        expected, QUESTION["options"]
    )


def test_the_averaged_path_records_every_rotation_and_the_longest_prompt():
    import math

    options = QUESTION["options"]
    backend = fake_local("rotations", lambda order: [math.log(0.2)] * len(order))
    scores, raw = backend.score(QUESTION, {})
    assert scores == {o: pytest.approx(0.2) for o in options}
    assert raw["order_averaging"] == "rotations" and len(raw["orders"]) == 5
    assert raw["prompt_tokens"] == 105
    assert raw["order_top_agreement"] == 1.0  # ties go to the earlier option, in every rotation
    assert set(raw) == {
        "order_averaging", "orders", "order_top_agreement", "order_max_shift", "prompt_tokens"
    }  # fmt: skip


def test_the_scoring_is_named_in_the_manifest_card_and_options(tmp_path, pipeline):
    manifest = json.loads((pipeline["run"] / "run-manifest.json").read_text())
    assert manifest["scoring_version"] == "backend-probabilities.v1"  # a replay is not rescored
    averaged = runner.SCORING_TEXT_AVERAGED
    assert "first-token letter log-likelihood, averaged over n cyclic option orders" in averaged
    base = {
        "backend": "local-hf",
        "model": {"id": "m", "version": "v"},
        "template_version": "t",
        "runner_version": "0",
    }
    card = runner.model_card({**base, "parameters": {"scoring": averaged}})
    assert "averaged over n cyclic option orders" in card["details"]["scoring"]
    card = runner.model_card({**base, "parameters": {"scoring": runner.SCORING_TEXT_SINGLE}})
    assert "single option order (comparison only)" in card["details"]["scoring"]
    parsed = runner.parser().parse_args(
        ["run", "--questions", "q", "--backend", "local-hf", "--out", "o"]
    )
    assert parsed.order_averaging == "rotations"  # averaging is the default
    parsed = runner.parser().parse_args(
        ["run", "--questions", "q", "--backend", "local-hf", "--out", "o",
         "--order-averaging", "none"]
    )  # fmt: skip
    assert parsed.order_averaging == "none"
    with pytest.raises(runner.RunnerError, match="Unknown --order-averaging"):
        runner.LocalHfBackend(tmp_path, "sometimes")
    assert runner.scoring_for("rotations") == (runner.SCORING_AVERAGED, averaged)
    assert runner.scoring_for("none") == (runner.SCORING_SINGLE, runner.SCORING_TEXT_SINGLE)
    assert runner.SCORING_AVERAGED != runner.SCORING_SINGLE != runner.SCORING_BACKEND
    assert (
        runner.ReplayBackend.scoring_version
        == runner.SCORING_BACKEND
        == (runner.JevBackend.scoring_version)
    )


# --- cleaner page text without re-fetching --------------------------------------------------------


def lines(*items):
    return "\n".join(items)


def test_the_first_occurrence_of_a_repeated_line_is_kept_within_a_page():
    page = lines(
        "Title", "Same long line repeated here", "Body one", "Same long line repeated here"
    )
    out = runner.filter_lines({"u": page}, {"u": "h"})["u"]
    assert out == lines("Title", "Same long line repeated here", "Body one")


def test_short_lines_shared_with_another_page_of_the_same_host_are_dropped():
    a = lines("Home", "About us", "A long enough sentence about page a", "Unique")
    b = lines("Home", "About us", "A long enough sentence about page b")
    out = runner.filter_lines({"a": a, "b": b}, {"a": "x.org", "b": "x.org"})
    assert out["a"] == lines("A long enough sentence about page a", "Unique")
    assert out["b"] == "A long enough sentence about page b"


def test_the_same_short_lines_on_two_different_hosts_are_kept():
    a = lines("Home", "About us", "Sentence of page a is long")
    b = lines("Home", "About us", "Sentence of page b is long")
    out = runner.filter_lines({"a": a, "b": b}, {"a": "x.org", "b": "y.org"})
    assert out == {"a": a, "b": b}  # a menu is shared only within one site


def test_a_line_of_four_words_is_never_dropped_and_one_of_three_words_is():
    three, four = "one two three", "one two three four"
    a, b = lines("Intro text of a page", three, four), lines("Intro of b page", three, four)
    out = runner.filter_lines({"a": a, "b": b}, {"a": "h", "b": "h"})
    assert out["a"] == lines("Intro text of a page", four)
    assert out["b"] == lines("Intro of b page", four)
    assert runner.SHORT_LINE_WORDS == 3


def test_a_short_line_only_this_page_has_is_kept_and_a_page_with_no_repeats_is_unchanged():
    a = lines("Unique head", "A sentence that is long enough here", "Short one")
    b = lines("Other head", "Another sentence that is long enough")
    out = runner.filter_lines({"a": a, "b": b}, {"a": "h", "b": "h"})
    assert out == {"a": a, "b": b}
    assert runner.filter_lines({"a": a}, {"a": "h"}) == {"a": a}


def test_the_result_does_not_depend_on_the_order_pages_are_processed_in():
    pages = {
        "a": lines("Menu", "Body of a is long enough"),
        "b": lines("Menu", "Body of b is long enough"),
        "c": lines("Body of c is long enough"),
    }
    hosts = dict.fromkeys(pages, "h")
    forward = runner.filter_lines(pages, hosts)
    backward = runner.filter_lines(dict(reversed(list(pages.items()))), hosts)
    assert forward == backward and forward["c"] == pages["c"] and "Menu" not in forward["a"]


@pytest.fixture
def menu_site():
    pages = {}
    for alt, name in COMPANIES:
        for index in (0, 1):
            extra = (
                "<div>Home</div><div>About us</div><p>Cookie notice repeated on this page</p>"
                "<p>Cookie notice repeated on this page</p>"
                f"<p>Unique {alt} {index}</p>"
                + ("<p>Cross site link</p>" if index == 0 and alt in ("co0", "co1") else "")
            )
            pages[f"/{alt}/{index}"] = page(f"{name} builds machines. Page {index}.", extra)
    pages["/market-report"] = page("A market report about everything.")
    s = Site(pages)
    yield s
    s.close()


@pytest.fixture
def menu_pipeline(tmp_path, menu_site):
    directory = tmp_path / "inputs"
    directory.mkdir()
    study = invented_study(directory, menu_site.url)
    # co1's pages are cited under another host name for the same local server, so a short line
    # that co0 page 0 and co1 page 0 share is shared across two hosts, not within one.
    evidence = Path(study["evidence"])
    other = menu_site.url.replace("127.0.0.1", "localhost")
    evidence.write_text(
        evidence.read_text().replace(f"{menu_site.url}/co1/", f"{other}/co1/"), encoding="utf-8"
    )
    snaps = tmp_path / "snaps"
    assert snapshot(study, snaps) == 0
    return {"study": study, "snaps": snaps, "site": menu_site}


def test_reextract_writes_a_new_index_and_text_and_never_touches_version_one(
    tmp_path, menu_pipeline, monkeypatch
):
    snaps, site = menu_pipeline["snaps"], menu_pipeline["site"]
    before = {p: p.read_bytes() for p in snaps.rglob("*") if p.is_file()}
    hits = len(site.hits)

    def no_network(*args, **kwargs):
        raise AssertionError("reextract must not fetch")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    assert run(["reextract", "--snapshots", snaps]) == 0
    assert len(site.hits) == hits  # no request was made
    for path, data in before.items():  # version 1 is byte-for-byte what it was
        assert path.read_bytes() == data
    index = json.loads((snaps / "snapshots.v2.json").read_text())
    old = json.loads((snaps / "snapshots.json").read_text())
    assert index["version"] == 2 and index["extractor_version"] == 2
    assert (
        index["source_index_sha256"]
        == hashlib.sha256((snaps / "snapshots.json").read_bytes()).hexdigest()
    )
    assert len(index["snapshots"]) == len(old["snapshots"])
    for row, original in zip(index["snapshots"], old["snapshots"], strict=True):
        assert row["raw_sha256"] == original["raw_sha256"] and row["url"] == original["url"]
        assert row["text_file"].startswith("text.v2/") and original["text_file"].startswith("text/")
        text = (snaps / row["text_file"]).read_text()
        assert hashlib.sha256(text.encode()).hexdigest() == row["text_sha256"]
        assert row["extractor_version"] == 2 and row["v1_text_rebuilt_identically"] is True
        assert row["chars_before"] == len((snaps / original["text_file"]).read_text()) and row[
            "chars_after"
        ] == len(text)
        assert row["v1_text_sha256"] == original["text_sha256"]
    page_row = next(r for r in index["snapshots"] if r["url"].endswith("/co0/0"))
    text = (snaps / page_row["text_file"]).read_text()
    assert (
        text.count("Cookie notice repeated on this page") == 1
    )  # a repeat within the page, kept once
    assert "Home" not in text and "About us" not in text  # short lines every page of the site has
    assert "Unique co0 0" in text and "Company A builds machines" in text
    assert "Cross site link" in text  # shared with a page of another host: not a menu of this one
    other_host = next(
        r for r in index["snapshots"] if "localhost" in r["url"] and "co1/0" in r["url"]
    )
    assert "Cross site link" in (snaps / other_host["text_file"]).read_text()
    assert "About us" not in (snaps / other_host["text_file"]).read_text()  # its own host's menu
    assert page_row["chars_after"] < page_row["chars_before"]
    market = next(r for r in index["snapshots"] if r["url"].endswith("/market-report"))
    assert "Home" not in (snaps / market["text_file"]).read_text()


def test_reextract_refuses_to_overwrite_a_changed_page_and_the_repository(
    tmp_path, menu_pipeline, monkeypatch
):
    snaps = menu_pipeline["snaps"]
    assert run(["reextract", "--snapshots", snaps]) == 0
    assert run(["reextract", "--snapshots", snaps]) == 2  # version 2 exists: never overwritten
    other = tmp_path / "copy"
    import shutil

    shutil.copytree(snaps, other, ignore=shutil.ignore_patterns("snapshots.v2.json", "text.v2"))
    first = next((other / "raw").iterdir())
    first.write_bytes(first.read_bytes() + b" tampered")
    assert run(["reextract", "--snapshots", other]) == 2
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    assert run(["reextract", "--snapshots", snaps]) == 2  # a directory inside the checkout


def test_questions_take_either_index_and_the_version_one_questions_are_unchanged(
    tmp_path, menu_pipeline
):
    study, snaps = menu_pipeline["study"], menu_pipeline["snaps"]
    one = tmp_path / "q1.json"
    assert questions(study, snaps, one) == 0
    assert run(["reextract", "--snapshots", snaps]) == 0
    two, two_again = tmp_path / "q2.json", tmp_path / "q2b.json"
    assert questions(study, snaps, two, "--extractor", "2") == 0
    assert questions(study, snaps, two_again, "--extractor", "2") == 0
    assert two.read_bytes() == two_again.read_bytes()  # deterministic
    first, second = json.loads(one.read_text()), json.loads(two.read_text())
    assert "snapshot_index" not in first["inputs"]
    assert second["inputs"]["snapshot_index"] == "snapshots.v2.json"
    assert second["inputs"]["snapshots_sha256"] != first["inputs"]["snapshots_sha256"]
    twice = "Cookie notice repeated on this page\nCookie notice repeated on this page"
    assert twice in first["states"]["co0"]["state_text"]
    assert twice not in second["states"]["co0"]["state_text"]
    assert "Cookie notice repeated on this page" in second["states"]["co0"]["state_text"]
    assert "About us" in first["states"]["co0"]["state_text"]
    assert "About us" not in second["states"]["co0"]["state_text"]
    assert second["digest"] != first["digest"]
    assert [q["criterion_id"] for q in first["questions"]] == [
        q["criterion_id"] for q in second["questions"]
    ]
    assert questions(study, snaps, tmp_path / "q3.json", "--extractor", "1") == 0
    assert (tmp_path / "q3.json").read_bytes() == one.read_bytes()  # explicit 1 is the default


# --- the laya backend (a fake laya module: no download, no torch, no network) ---------------------


def words(text):
    """The fake tokenizer's count: one token per whitespace-separated word."""
    return len(text.split())


class FakeTokenizer:
    def __call__(self, text, add_special_tokens=False):
        assert add_special_tokens is False
        return {"input_ids": list(range(words(text)))}


def fake_build_head(tok, q, head_max_len=192, option_order=None):
    """laya.common.build_head's shape: [CLS] instructions [SEP] ([MASK] option)... [SEP].

    Options never shrink here; the instructions are cut to what the options leave, as laya does.
    """
    instruction_tokens = words(f"{q['t']} question: {q['ins']}")
    option_tokens = [1 + words(str(k)) for k in q["crit"]]
    kept = min(instruction_tokens, max(8, head_max_len - sum(option_tokens)))
    ids = [0] * (1 + kept + 1 + sum(option_tokens) + 1)
    return ids, [], {"options": len(option_tokens)}


def fake_state_room(tok, q, max_len=512, head_max_len=192):
    head, _, _ = fake_build_head(tok, q, head_max_len)
    return max(0, max_len - len(head) - 1)


class FakeAgent:
    def __init__(self, max_len, head_max_len, behaviour):
        self.cfg = {"max_len": max_len, "head_max_len": head_max_len}
        self.tok = FakeTokenizer()
        self.device = "cpu"
        self.behaviour = behaviour
        self.calls = []

    def predict(self, state, questions):
        asked = questions["answer"]
        order = list(asked["criteria"])
        self.calls.append((state, asked))
        values = self.behaviour(state, order)
        best = max(range(len(order)), key=lambda i: values[i])
        return {
            "answers": {
                "answer": {
                    "type": "choice",
                    "choice": order[best],
                    # keyed by option, in display order, rounded to four places as laya does
                    "probabilities": {o: round(v, 4) for o, v in zip(order, values, strict=True)},
                }
            }
        }


def uniform(state, order):
    return [1 / len(order)] * len(order)


@pytest.fixture
def fake_laya(monkeypatch):
    """Install a fake ``laya`` package; ``configure`` sets the checkpoint's window and model."""
    settings = {"max_len": 512, "head_max_len": 192, "behaviour": uniform}
    loaded = {}
    module = types.ModuleType("laya")
    common = types.ModuleType("laya.common")
    common.build_head = fake_build_head
    common.state_room = fake_state_room
    module.common = common
    module.__version__ = "0.4.32"

    def load(path, **kwargs):
        assert kwargs == {} and Path(path).is_dir()  # a local checkpoint directory, nothing else
        agent = FakeAgent(settings["max_len"], settings["head_max_len"], settings["behaviour"])
        loaded.update(path=path, agent=agent)
        return agent

    def forbidden(*args, **kwargs):
        raise AssertionError("laya.Agent and laya.Router are never used")

    module.load, module.Agent, module.Router = load, forbidden, forbidden
    monkeypatch.setitem(sys.modules, "laya", module)
    monkeypatch.setitem(sys.modules, "laya.common", common)
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")  # restored after the test; the backend sets "1"
    settings["loaded"] = loaded
    return settings


def checkpoint(tmp_path, repo="convaiinnovations/laya", name="laya"):
    directory = tmp_path / "models" / name
    directory.mkdir(parents=True)
    (directory / "mcda-model-revision.json").write_text(
        json.dumps({"repo_id": repo, "revision": f"rev-{name}", "route": "own repository"})
    )
    return directory


LAYA_QUESTION = {
    "question_id": "q",
    "criterion_name": "Team",
    "rubric": "How strong the team is.",
    "instruction": "Choose one.",
    "options": ["Weak", "Fair", "Good", "Strong", "cannot tell"],
}


def test_chunks_fit_one_under_exactly_at_and_one_over_the_budget():
    four = "a b c d"
    for second, expected in ((5, 1), (6, 1), (7, 2)):  # 9, exactly 10 and 11 tokens joined
        text = four + "\n\n" + " ".join("x" * second)
        chunks = runner.chunk_text(text, 10, words)
        assert len(chunks) == expected, second
        assert all(c["tokens"] <= 10 and c["rule"] == "paragraph" for c in chunks)
    exact = runner.chunk_text(" ".join("y" * 10), 10, words)  # a paragraph exactly at the budget
    assert [(c["tokens"], c["rule"]) for c in exact] == [(10, "paragraph")]
    joined = runner.chunk_text("a b c d\n\ne f g h i j", 10, words)[0]
    assert joined["text"] == "a b c d\n\ne f g h i j"  # paragraphs stay apart inside a chunk
    assert joined["sha256"] == hashlib.sha256(joined["text"].encode()).hexdigest()


def test_an_over_long_paragraph_splits_on_sentences_then_by_tokens():
    paragraph = "One two three four. Five six seven eight. Nine ten eleven twelve."
    chunks = runner.chunk_text(paragraph, 10, words)
    assert [c["text"] for c in chunks] == [
        "One two three four. Five six seven eight.",
        "Nine ten eleven twelve.",
    ]
    assert [c["rule"] for c in chunks] == ["sentence", "sentence"]
    run_on = " ".join(f"w{i}" for i in range(25))  # one sentence of 25 tokens, no punctuation
    pieces = runner.chunk_text(run_on, 10, words)
    assert [c["tokens"] for c in pieces] == [10, 10, 5]
    assert {c["rule"] for c in pieces} == {"tokens"}
    assert " ".join(c["text"] for c in pieces) == run_on  # nothing lost or repeated
    by_characters = runner.chunk_text("abcdefghijkl", 5, len)  # one "word" longer than the budget
    assert [c["text"] for c in by_characters] == ["abcde", "fghij", "kl"]
    assert runner.chunk_text("", 10, words) == [
        {"text": "", "tokens": 0, "sha256": hashlib.sha256(b"").hexdigest(), "rule": "empty"}
    ]


@pytest.mark.parametrize("window", [512, 1024])
def test_the_window_is_read_from_the_checkpoint_and_every_chunk_fits_it(
    tmp_path, fake_laya, window
):
    fake_laya["max_len"] = window
    backend = runner.LayaBackend(checkpoint(tmp_path), "none")
    assert backend.parameters()["window_tokens"] == window
    assert backend.parameters()["head_max_tokens"] == 192
    state = {"name": "Company A", "state_text": "\n\n".join([" ".join(["word"] * 150)] * 12)}
    _, raw = backend.score(LAYA_QUESTION, state)
    internal = {
        "t": "choice",
        "ins": backend.instructions(LAYA_QUESTION),
        "crit": dict.fromkeys(LAYA_QUESTION["options"]),
    }
    budget = fake_state_room(None, internal, window, 192) - runner.LAYA_MARGIN
    assert raw["window_tokens"] == window and raw["state_budget_tokens"] == budget
    assert all(c["tokens"] <= budget for c in raw["chunks"])  # the prefix is counted too
    calls = fake_laya["loaded"]["agent"].calls
    assert len(calls) == raw["chunk_count"]
    assert all(words(state_text) <= budget for state_text, _ in calls)
    assert all(state_text.startswith("Text about Company A:\n") for state_text, _ in calls)
    per_chunk = (budget - words("Text about Company A:\n")) // 150  # whole paragraphs packed
    assert raw["chunk_count"] == math.ceil(12 / per_chunk)
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert Path(fake_laya["loaded"]["path"]) == checkpoint_path(tmp_path)


def checkpoint_path(tmp_path):
    return (tmp_path / "models" / "laya").resolve()


def test_a_question_the_package_would_cut_or_leave_no_room_is_refused(tmp_path, fake_laya):
    fake_laya["head_max_len"] = 20  # the rubric and options no longer fit the question budget
    backend = runner.LayaBackend(checkpoint(tmp_path), "none")
    with pytest.raises(runner.QuestionRefusedError, match="would cut them"):
        backend.score(LAYA_QUESTION, {"name": "A", "state_text": "text"})
    fake_laya["head_max_len"], fake_laya["max_len"] = 192, 90  # fits, but leaves under 64 tokens
    backend = runner.LayaBackend(checkpoint(tmp_path / "b"), "none")
    with pytest.raises(runner.QuestionRefusedError, match="state tokens fit"):
        backend.score(LAYA_QUESTION, {"name": "A", "state_text": "text"})
    fake_laya["max_len"] = 512
    backend = runner.LayaBackend(checkpoint(tmp_path / "c"), "none")
    long_option = {**LAYA_QUESTION, "options": ["w " * 60, "Fair", "cannot tell"]}
    with pytest.raises(runner.QuestionRefusedError, match="longer than 48 tokens"):
        backend.score(long_option, {"name": "A", "state_text": "text"})
    assert fake_laya["loaded"]["agent"].calls == []  # nothing was asked of the model


def test_chunk_vectors_are_averaged_by_the_arithmetic_mean(tmp_path, fake_laya):
    options = LAYA_QUESTION["options"]
    by_marker = {
        "alpha": [0.6, 0.1, 0.1, 0.1, 0.1],
        "beta": [0.1, 0.1, 0.1, 0.1, 0.6],
        "gamma": [0.1, 0.1, 0.4, 0.1, 0.3],
    }

    def by_chunk(state, order):
        marker = next(m for m in by_marker if m in state)
        values = dict(zip(options, by_marker[marker], strict=True))
        return [values[o] for o in order]

    fake_laya["behaviour"] = by_chunk
    backend = runner.LayaBackend(checkpoint(tmp_path), "none")
    filler = " ".join(["filler"] * 300)  # one paragraph per chunk at a 512 window
    state = {"name": "A", "state_text": f"alpha {filler}\n\nbeta {filler}\n\ngamma {filler}"}
    scores, raw = backend.score(LAYA_QUESTION, state)
    assert raw["chunk_count"] == 3
    for index, option in enumerate(options):
        mean = sum(by_marker[m][index] for m in by_marker) / 3
        assert scores[option] == pytest.approx(mean, abs=1e-12)
    assert runner.first_max(options, scores) == "cannot tell"  # (0.1 + 0.6 + 0.3) / 3 is the top
    assert raw["chunk_top_agreement"] == pytest.approx(1 / 3)  # only the "beta" chunk agrees
    assert raw["max_confidence_chunk_top"] == "Weak"  # the first of the two 0.6 chunks
    assert [len(order) for order in raw["chunk_vectors"]] == [3]
    assert sorted(c["rule"] for c in raw["chunks"]) == ["paragraph"] * 3


@pytest.mark.parametrize("n", [5, 6])
def test_a_position_biased_laya_is_corrected_by_rotations_and_mapped_back_by_option(
    tmp_path, fake_laya, n
):
    options = options_for(n)
    true = true_weights(options)
    beta = 0.6  # this share of the mass goes to whatever option is shown first

    def biased(state, order):
        return [(1 - beta) * true[o] + (beta if i == 0 else 0.0) for i, o in enumerate(order)]

    fake_laya["behaviour"] = biased
    backend = runner.LayaBackend(checkpoint(tmp_path), "rotations")
    question = {**LAYA_QUESTION, "options": options}
    scores, raw = backend.score(question, {"name": "A", "state_text": "short text"})
    for option in options:  # the four-place rounding is the only error
        assert scores[option] == pytest.approx((1 - beta) * true[option] + beta / n, abs=2e-4)
    assert runner.first_max(options, scores) == runner.first_max(options, true)
    assert raw["order_top_agreement"] == pytest.approx(1 / n)
    assert raw["order_max_shift"] == pytest.approx(beta, abs=2e-4)
    asked = [call[1]["criteria"] for call in fake_laya["loaded"]["agent"].calls]
    assert asked == [runner.rotated(options, shift) for shift in range(n)]
    for criteria in asked:  # "cannot tell" is asked once, never added a second time
        assert criteria.count("cannot tell") == 1 and sorted(criteria) == sorted(options)
    exact = runner.quantize(scores, options)
    assert sum(exact.values()) == Decimal(1)


def test_laya_refuses_without_the_package_or_a_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "laya", None)  # importing it now fails
    with pytest.raises(runner.RunnerError, match="laya==0.4.32"):
        runner.LayaBackend(checkpoint(tmp_path), "rotations")
    with pytest.raises(runner.RunnerError, match="No model"):
        runner.LayaBackend(tmp_path / "missing", "rotations")


def test_a_laya_run_exports_exact_probabilities_refusals_and_a_card_per_checkpoint(
    tmp_path, study, pipeline, fake_laya
):
    qpath = tmp_path / "laya-questions.json"
    assert questions(study, pipeline["snaps"], qpath, "--budget-chars", "1200", backend="laya") == 0
    cards = {}
    for repo, name, window in (
        ("convaiinnovations/laya", "laya", 512),
        ("convaiinnovations/laya-typed-decisions", "laya-typed-decisions", 1024),
    ):
        fake_laya["max_len"] = window
        model = checkpoint(tmp_path, repo, name)
        out = tmp_path / f"run-{name}"
        args = ["run", "--questions", qpath, "--backend", "laya", "--model-path", model]
        assert run([*args, "--limit", "4", "--out", out]) == 0
        manifest = json.loads((out / "run-manifest.json").read_text())
        assert manifest["backend"] == "laya" and manifest["scoring_version"] == (
            "laya-choice-chunk-mean.v1"
        )
        assert manifest["model"] == {"id": repo, "version": f"rev-{name}"}
        assert manifest["parameters"]["window_tokens"] == window
        assert manifest["parameters"]["checkpoint_route"] == "own repository"
        assert manifest["environment"]["laya"] == "0.4.32"
        assert "refused_questions" not in manifest
        text = (out / "probabilities.json").read_text()
        rows = json.loads(text, parse_float=Decimal)["rows"]
        assert len(rows) == 4
        for row in rows.values():  # exact decimals, read as decimals, sum to exactly one
            assert sum(row["probabilities"].values()) == Decimal(1)
        assert export({"run": out}, tmp_path / f"export-{name}", study["project"]) == 0
        cards[name] = json.loads((tmp_path / f"export-{name}" / "model-card.json").read_text())
    base, tuned = cards["laya"], cards["laya-typed-decisions"]
    assert base["details"]["fine_tuning"] == runner.LAYA_NOTES["convaiinnovations/laya"]
    assert "near-random zero-shot accuracy" in base["limitations"]
    assert tuned["details"]["fine_tuning"] == (
        "fine-tuned on unrelated workflows (customer service, invoices, security, agent traces), "
        "not on startup screening"
    )
    assert base["details"]["window"].startswith("512 tokens")
    assert tuned["details"]["window"].startswith("1024 tokens")
    assert "averaged over n cyclic option orders" in base["details"]["scoring"]
    assert base["details"]["licence"].startswith("Apache-2.0")
    fake_laya["head_max_len"] = 20  # every question is now refused, and the run still completes
    refused_run = tmp_path / "run-refused"
    model = checkpoint(tmp_path, "convaiinnovations/laya", "laya-small")
    args = ["run", "--questions", qpath, "--backend", "laya", "--model-path", model]
    assert run([*args, "--limit", "3", "--out", refused_run]) == 0
    manifest = json.loads((refused_run / "run-manifest.json").read_text())
    assert len(manifest["refused_questions"]) == 3
    lines = (refused_run / "raw_responses.jsonl").read_text().splitlines()
    assert all("would cut them" in json.loads(line)["refused"] for line in lines)
    assert export({"run": refused_run}, tmp_path / "export-refused", study["project"]) == 0
    report = json.loads((tmp_path / "export-refused" / "run-report.json").read_text())
    assert report["proposals"] == 0 and report["abstentions"] == 3
    assert all(a["reason"].startswith("refused: ") for a in report["abstention_list"])


def test_laya_runs_need_questions_built_for_laya(tmp_path, pipeline, fake_laya):
    args = ["run", "--questions", pipeline["questions"], "--backend", "laya"]
    assert run([*args, "--model-path", checkpoint(tmp_path), "--out", tmp_path / "x"]) == 2


class FakeHub:
    """huggingface_hub's two calls, recorded; the download writes an empty directory."""

    def __init__(self):
        self.downloads = []
        hub = self

        class HfApi:
            def model_info(self, repo):
                return types.SimpleNamespace(sha=f"sha-of-{repo.split('/')[1]}")

        def snapshot_download(**kwargs):
            hub.downloads.append(kwargs)
            Path(kwargs["local_dir"]).mkdir(parents=True)

        self.module = types.ModuleType("huggingface_hub")
        self.module.HfApi, self.module.snapshot_download = HfApi, snapshot_download


def test_the_model_allowlist_admits_qwen_and_the_two_laya_checkpoints_only(tmp_path, monkeypatch):
    hub = FakeHub()
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub.module)
    monkeypatch.setenv("MCDA_ALLOW_MODEL_DOWNLOAD", "1")
    for repo in ("convaiinnovations/laya-multilingual", "nandakishorm/vega-U", "someone/else"):
        assert run(["fetch-model", "--repo", repo, "--out", tmp_path / "m"]) == 2
    assert hub.downloads == []
    for repo in runner.LAYA_REPOS:
        assert run(["fetch-model", "--repo", repo, "--out", tmp_path / "m"]) == 0
    assert run(["fetch-model", "--repo", runner.QWEN_REPO, "--out", tmp_path / "m"]) == 0
    base, tuned, qwen = hub.downloads
    assert base["repo_id"] == "convaiinnovations/laya" and base["revision"] == "sha-of-laya"
    assert base["allow_patterns"] == tuned["allow_patterns"] == runner.LAYA_FILES
    assert "allow_patterns" not in qwen  # the Qwen download is exactly as before
    assert tuned["repo_id"] == "convaiinnovations/laya-typed-decisions"
    tuned_dir = tmp_path / "m" / "laya-typed-decisions"
    record = json.loads((tuned_dir / "mcda-model-revision.json").read_text())
    assert record["revision"] == "sha-of-laya-typed-decisions"
    assert record["route"] == "own repository" and record["files"] == runner.LAYA_FILES
    qwen_record = json.loads(
        (tmp_path / "m" / "Qwen2.5-1.5B-Instruct" / "mcda-model-revision.json").read_text()
    )
    assert set(qwen_record) == {"repo_id", "revision", "licence", "retrieved_at"}
    monkeypatch.delenv("MCDA_ALLOW_MODEL_DOWNLOAD")
    assert run(["fetch-model", "--repo", runner.LAYA_REPOS[0], "--out", tmp_path / "n"]) == 2


def biased_jev(count, body):
    """A jev mock that puts 0.6 of its mass on the first option shown, the rest by a true vector."""
    criteria = list(body["questions"]["answer"]["criteria"])
    true = true_weights(sorted(criteria))  # the truth depends on the option, not its position
    probabilities = {
        name: 0.4 * true[name] + (0.6 if i == 0 else 0.0) for i, name in enumerate(criteria)
    }
    return 200, {
        "model": body["model"],
        "answers": {"answer": {"type": "choice", "probabilities": probabilities}},
        "usage": {"input_tokens": 10, "output_tokens": 1},
    }


def test_jev_rotates_the_documented_request_and_maps_each_answer_back_by_option(
    tmp_path, jev_questions, monkeypatch, capsys
):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    mock = MockJev(biased_jev)
    try:
        assert jev_run(jev_questions, tmp_path / "rot", mock.url, "--allow-network") == 0
    finally:
        mock.close()
    doc = json.loads(jev_questions.read_text())
    first_three = doc["questions"][:3]
    assert len(mock.requests) == sum(len(q["options"]) for q in first_three)
    n = len(first_three[0]["options"])
    sent = [list(body["questions"]["answer"]["criteria"]) for _, _, body in mock.requests[:n]]
    assert sent == [runner.rotated(first_three[0]["options"], shift) for shift in range(n)]
    positions = [body["questions"]["answer"]["criteria"] for _, _, body in mock.requests[:n]]
    assert all(list(p.values())[0] == f"Option 1 of {n}" for p in positions)
    manifest = json.loads((tmp_path / "rot" / "run-manifest.json").read_text())
    assert manifest["scoring_version"] == "backend-probabilities-rotations.v1"
    assert manifest["parameters"]["order_averaging"] == "rotations"
    raw = json.loads((tmp_path / "rot" / "raw_responses.jsonl").read_text().splitlines()[0])
    options = first_three[0]["options"]
    true = true_weights(sorted(options))
    for option in options:  # each option's average is the same affine map of its true weight
        assert raw["scores"][option] == pytest.approx(0.4 * true[option] + 0.6 / n, abs=1e-12)
    assert raw["raw"]["order_top_agreement"] == pytest.approx(1 / n)
    assert len(raw["raw"]["responses"]) == n
    probe = runner.JevBackend(mock.url, "jev-1.13.0", "k")
    estimate = 0
    for question in first_three:
        body = json.dumps(probe.request_body(question, doc["states"][question["alternative_id"]]))
        estimate += math.ceil(len(body) / 4) * len(question["options"])
    assert f"jev: about {estimate} input tokens" in capsys.readouterr().out


def test_jev_refuses_a_run_over_its_token_cap_before_any_request(
    tmp_path, jev_questions, monkeypatch
):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    mock = MockJev(good_answer)
    try:
        flags = ("--allow-network", "--max-input-tokens", "10")
        assert jev_run(jev_questions, tmp_path / "capped", mock.url, *flags) == 2
        assert mock.requests == []
    finally:
        mock.close()


# --- the second Laya reading: the most confident chunk ------------------------------------------


def test_the_most_confident_chunk_has_the_highest_top_and_ties_go_to_the_earlier_chunk():
    means = [{"a": 0.5, "b": 0.5}, {"a": 0.7, "b": 0.3}, {"a": 0.3, "b": 0.7}, {"a": 0.6, "b": 0.4}]
    assert runner.most_confident_chunk(means) == 1  # 0.7 twice: the earlier chunk
    assert runner.most_confident_chunk(means[2:]) == 0
    assert runner.most_confident_chunk([{"a": 0.2, "b": 0.8}]) == 0
    with pytest.raises(runner.RunnerError):
        runner.most_confident_chunk([])


def test_the_second_reading_is_the_decisive_chunks_order_averaged_vector(tmp_path, fake_laya):
    options = LAYA_QUESTION["options"]
    by_marker = {
        "alpha": [0.1, 0.1, 0.1, 0.1, 0.6],
        "beta": [0.05, 0.05, 0.1, 0.7, 0.1],
        "gamma": [0.1, 0.1, 0.4, 0.1, 0.3],
    }

    def by_chunk(state, order):
        marker = next(m for m in by_marker if m in state)
        values = dict(zip(options, by_marker[marker], strict=True))
        return [values[o] for o in order]

    fake_laya["behaviour"] = by_chunk
    backend = runner.LayaBackend(checkpoint(tmp_path), "rotations")
    filler = " ".join(["filler"] * 300)
    state = {"name": "A", "state_text": f"alpha {filler}\n\nbeta {filler}\n\ngamma {filler}"}
    scores, raw = backend.score(LAYA_QUESTION, state)
    assert raw["chunk_count"] == 3
    second = raw[runner.MAX_CONFIDENCE_CHUNK]
    assert second["chunk"] == 1 and raw["max_confidence_chunk_top"] == "Strong"
    for index, option in enumerate(options):  # the beta chunk, the same under every rotation
        assert second["probabilities"][option] == pytest.approx(by_marker["beta"][index], abs=1e-12)
        mean = sum(by_marker[m][index] for m in by_marker) / 3  # the mean is still the reading
        assert scores[option] == pytest.approx(mean, abs=1e-12)
    assert runner.first_max(options, scores) == "cannot tell"
    assert backend.parameters()["second_reading"] == runner.READING_MAX_CONFIDENCE_CHUNK


def confident_in_some_chunks(state, order):
    """Confident (0.9 on the alphabetically first option) in about a third of the chunks."""
    if int(hashlib.sha256(state.encode()).hexdigest(), 16) % 3:
        return [1 / len(order)] * len(order)
    first = min(order)
    return [0.9 if o == first else 0.1 / (len(order) - 1) for o in order]


def test_export_can_propose_from_the_recorded_second_reading_and_names_it(
    tmp_path, study, pipeline, fake_laya
):
    qpath = tmp_path / "laya-questions.json"
    assert (
        questions(study, pipeline["snaps"], qpath, "--budget-chars", "12000", backend="laya") == 0
    )
    fake_laya["behaviour"] = confident_in_some_chunks
    fake_laya["max_len"] = 200  # a small window, so the pages fall into several chunks
    out = tmp_path / "run-laya"
    args = ["run", "--questions", qpath, "--backend", "laya", "--model-path", checkpoint(tmp_path)]
    assert run([*args, "--out", out]) == 0
    rows = json.loads((out / "probabilities.json").read_text(), parse_float=Decimal)["rows"]
    raws = {
        json.loads(line)["question_id"]: json.loads(line)["raw"]
        for line in (out / "raw_responses.jsonl").read_text().splitlines()
    }
    options = {q["question_id"]: q["options"] for q in json.loads(qpath.read_text())["questions"]}
    differ = 0
    for qid, row in rows.items():
        reading = row["readings"][runner.MAX_CONFIDENCE_CHUNK]
        assert sum(reading["probabilities"].values()) == Decimal(1)
        expected = runner.quantize(
            raws[qid][runner.MAX_CONFIDENCE_CHUNK]["probabilities"], options[qid]
        )
        assert reading["probabilities"] == expected
        assert (reading["top"], reading["tied"]) == runner.top_option(expected, options[qid])
        differ += reading["probabilities"] != row["probabilities"]
    assert differ > 0  # the two readings really differ somewhere

    def exported(name, *extra):
        target = tmp_path / name
        cmd = ["export", "--run", out, "--project", study["project"], "--out", target, *extra]
        assert run(cmd) == 0
        csv_rows = list(csv.reader(io.StringIO((target / "proposals.csv").read_text())))[1:]
        report = json.loads((target / "run-report.json").read_text())
        card = json.loads((target / "model-card.json").read_text())
        return csv_rows, report, card

    mean_rows, mean_report, mean_card = exported("export-mean")
    second_rows, second_report, second_card = exported(
        "export-second", "--reading", "max-confidence-chunk"
    )
    assert "reading" not in mean_report and "reading" not in mean_card["details"]
    assert second_report["reading"] == runner.READING_MAX_CONFIDENCE_CHUNK
    assert second_card["details"]["reading"] == runner.READING_MAX_CONFIDENCE_CHUNK
    assert all(not r[9].endswith("+max-confidence-chunk") for r in mean_rows)
    assert second_rows and all(r[9].endswith("+max-confidence-chunk") for r in second_rows)
    proposed = {r[2].removeprefix("typed__"): json.loads(r[7])["value"] for r in second_rows}
    for qid, row in rows.items():
        reading = row["readings"][runner.MAX_CONFIDENCE_CHUNK]
        top = reading["top"]
        wanted = (
            top is not None
            and top != "cannot tell"
            and reading["probabilities"][top] >= Decimal("0.5")
        )
        assert (qid in proposed) == wanted
        if wanted:
            assert proposed[qid] == top
    assert len(second_rows) > len(mean_rows)  # here the confident chunks pass the threshold


def test_export_refuses_a_second_reading_the_run_did_not_record(tmp_path, study, pipeline):
    cmd = ["export", "--run", pipeline["run"], "--project", study["project"]]
    assert run([*cmd, "--reading", "max-confidence-chunk", "--out", tmp_path / "x"]) == 2
    assert not (tmp_path / "x").exists()
    assert run([*cmd, "--out", tmp_path / "y"]) == 0


# --- where a local model runs ---------------------------------------------------------------------


def fake_torch(cuda: bool, mps: bool) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: cuda),
        backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: mps)),
        float16="float16",
        float32="float32",
    )


@pytest.mark.parametrize(
    ("cuda", "mps", "chosen"),
    [
        (True, False, ("cuda", "float16")),
        (True, True, ("cuda", "float16")),
        (False, True, ("mps", "float16")),
        (False, False, ("cpu", "float32")),
    ],
)
def test_a_local_model_prefers_cuda_then_mps_then_the_cpu(cuda, mps, chosen):
    assert runner.choose_device(fake_torch(cuda, mps)) == chosen
