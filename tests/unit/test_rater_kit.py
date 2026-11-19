"""Checks of the blind rater kit (``scripts/rater_kit.py``) on an invented study.

Nothing here reads the venture-screening study's ratings. The fixture invents companies, rubrics,
sources and ratings, writes them to a temporary directory, and drives the script's command line.
The round trip runs the classifier agreement benchmark itself on two-rater labels converted by the
kit, so the output is proved to be what the benchmark accepts.
"""

import csv
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kit = _load("rater_kit")
bench = _load("classifier_agreement_benchmark")

CANARIES = [
    "CANARY-VALUE-7f3a",
    "CANARY-DESCRIPTION-91bc",
    "CANARY-MEASUREMENT-5d20",
    "CANARY-NOTE",
]
FIVE = ["Weak", "Fair", "Good", "Strong", "Excellent"]
FOUR = ["None", "Some", "Most", "All"]
COMPANIES = [(f"co{i}", f"Company {chr(65 + i)}") for i in range(10)]
FIVE_LEAVES = ["f1", "f2", "f3", "f4"]
FOUR_LEAVES = ["g1", "g2"]


def invented_study(directory: Path) -> dict[str, Path]:
    leaves = [
        {
            "id": leaf,
            "name": f"Criterion {leaf}",
            "parent_id": "team",
            "parent_name": "Team",
            "scale_type": "ordinal",
            "labels": FIVE if leaf in FIVE_LEAVES else FOUR,
            "rubric": f"Rubric text for {leaf}: choose the best-supported level.",
            "numeric": False,
        }
        for leaf in FIVE_LEAVES + FOUR_LEAVES
    ]
    leaves.append(
        {
            "id": "size",
            "name": "Market size",
            "parent_id": "market",
            "parent_name": "Market",
            "scale_type": "ratio",
            "labels": [],
            "rubric": "Billions.",
            "numeric": True,
        }
    )
    rubrics = {
        "version": 1,
        "study": "invented",
        "as_of": "2026-01-01",
        "scored_leaves": leaves,
        "screened_excluded": [{"id": "hq", "name": "HQ", "parent_id": "mandate"}],
    }
    performances, claims = [], []
    for c, (alt, _) in enumerate(COMPANIES):
        for k, leaf in enumerate(FIVE_LEAVES + FOUR_LEAVES):
            labels = FIVE if leaf in FIVE_LEAVES else FOUR
            performances.append(
                {
                    "alternative_id": alt,
                    "criterion_id": leaf,
                    "value": labels[(c + k) % len(labels)],
                }
            )
            claims.append(
                {
                    "id": f"{alt}__{leaf}",
                    "alternative_id": alt,
                    "criterion_id": leaf,
                    "value": CANARIES[0],
                    "source": {
                        "name": "Name",
                        "reference": f"https://example.org/{alt}/{k % 2}",
                        "description": CANARIES[1],
                        "date": "2026-01-01",
                    },
                    "review": {"note": CANARIES[3]},
                }
            )
        performances.append({"alternative_id": alt, "criterion_id": "size", "value": 3.5})
        claims.append(
            {
                "id": f"{alt}__size",
                "alternative_id": alt,
                "criterion_id": "size",
                "value": 3.5,
                "source": {"name": "Report", "reference": "https://reports.example/size"},
            }
        )
    performances.append(
        {"alternative_id": COMPANIES[0][0], "criterion_id": "hq", "value": CANARIES[2]}
    )
    project = {
        "alternatives": [{"id": a, "name": n, "metadata": {}} for a, n in COMPANIES],
        "criteria": [],
        "performances": performances,
        "description": CANARIES[2],
    }
    paths = {
        "project": directory / "project.json",
        "rubrics": directory / "rubrics.json",
        "evidence": directory / "evidence.json",
    }
    paths["project"].write_text(json.dumps(project), encoding="utf-8")
    paths["rubrics"].write_text(json.dumps(rubrics), encoding="utf-8")
    paths["evidence"].write_text(json.dumps({"claims": claims}), encoding="utf-8")
    return paths


@pytest.fixture
def study(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    return invented_study(inputs)


def make(study, out, seed=7):
    code = kit.main(
        [
            "make",
            "--project",
            str(study["project"]),
            "--rubrics",
            str(study["rubrics"]),
            "--evidence",
            str(study["evidence"]),
            "--seed",
            str(seed),
            "--out",
            str(out),
        ]
    )
    assert code == 0


def tree_bytes(directory: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(directory)): p.read_bytes()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


# --- the packet ---------------------------------------------------------------------------------


def test_cells_are_the_labelled_leaves_by_the_companies_and_nothing_else(study, tmp_path):
    make(study, tmp_path / "kit")
    items = json.loads((tmp_path / "kit" / "items.json").read_text())
    assert len(items["cells"]) == len(COMPANIES) * (len(FIVE_LEAVES) + len(FOUR_LEAVES))
    assert {c["criterion_id"] for c in items["cells"]} == set(FIVE_LEAVES + FOUR_LEAVES)
    assert "size" in items["excluded_leaf_ids"] and "hq" in items["excluded_leaf_ids"]
    assert [t["levels"] for t in items["tasks"]] == [4, 5]
    packet = (tmp_path / "kit" / "rater-packet.html").read_text()
    assert packet.count('class="cell"') == len(items["cells"])
    assert "Cannot tell" in packet and "Save answers" in packet


def test_the_packet_is_self_contained_and_uses_no_network_storage_or_server(study, tmp_path):
    make(study, tmp_path / "kit")
    packet = (tmp_path / "kit" / "rater-packet.html").read_text()
    script = packet.split("<script>")[1].split("</script>")[0]
    for forbidden in (
        "fetch(",
        "XMLHttpRequest",
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "WebSocket",
        "import(",
    ):
        assert forbidden not in script
    assert not re.search(r"<(link|img|iframe|object|embed)\b", packet)
    assert not re.search(r"<script[^>]+src=", packet)
    assert "@import" not in packet and "url(" not in packet
    hrefs = re.findall(r'href="([^"]+)"', packet)
    assert hrefs and all(h.startswith("https://example.org/") for h in hrefs)
    # the numeric market source is not a cited page for a rated cell
    assert "reports.example" not in packet


def test_nothing_the_author_wrote_reaches_any_output_file(study, tmp_path):
    make(study, tmp_path / "kit")
    for name, data in tree_bytes(tmp_path / "kit").items():
        for canary in CANARIES:
            assert canary.encode() not in data, (name, canary)
    # nor any rating label of the author: the packet offers every label to every cell
    for name in ("rater-packet.html", "rater-form.csv", "items.json"):
        assert b"performances" not in (tmp_path / "kit" / name).read_bytes()


def test_the_same_seed_gives_identical_bytes_and_another_seed_a_new_order(study, tmp_path):
    make(study, tmp_path / "a", seed=7)
    make(study, tmp_path / "b", seed=7)
    make(study, tmp_path / "c", seed=8)
    assert tree_bytes(tmp_path / "a") == tree_bytes(tmp_path / "b")
    first = json.loads((tmp_path / "a" / "items.json").read_text())
    other = json.loads((tmp_path / "c" / "items.json").read_text())
    assert first["company_order"] != other["company_order"]
    assert first["leaf_order"] != other["leaf_order"]
    assert sorted(first["company_order"]) == sorted(other["company_order"])


def test_the_form_has_the_same_cells_and_neutralises_spreadsheet_formulas(study, tmp_path):
    make(study, tmp_path / "kit")
    rows = list(csv.DictReader((tmp_path / "kit" / "rater-form.csv").open(newline="")))
    items = json.loads((tmp_path / "kit" / "items.json").read_text())
    assert [r["item_id"] for r in rows] == [c["item_id"] for c in items["cells"]]
    assert all(r["answer"] == "" and r["note"] == "" for r in rows)
    assert kit.spreadsheet_safe("=1+1") == "'=1+1"
    assert kit.spreadsheet_safe("@x") == "'@x" and kit.spreadsheet_safe("-1") == "'-1"
    assert kit.spreadsheet_safe("plain") == "plain"


# --- refusals -----------------------------------------------------------------------------------


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    """A stand-in checkout in a temporary directory, so refusals never touch the real one."""
    root = tmp_path / "fake-repo"
    root.mkdir()
    monkeypatch.setattr(kit, "ROOT", root.resolve())
    return root


def make_args(study, out, seed="1"):
    return [
        "make",
        "--project",
        str(study["project"]),
        "--rubrics",
        str(study["rubrics"]),
        "--evidence",
        str(study["evidence"]),
        "--seed",
        seed,
        "--out",
        str(out),
    ]


def test_outputs_inside_the_repository_are_refused_even_through_a_symlink(
    study, tmp_path, fake_repo
):
    inside = fake_repo / "rater-kit"
    assert kit.main(make_args(study, inside)) == 2
    assert not inside.exists()
    link = tmp_path / "link"
    link.symlink_to(fake_repo)
    assert kit.main(make_args(study, link / "x")) == 2
    assert not (fake_repo / "x").exists()
    assert kit.main(make_args(study, tmp_path / "outside")) == 0  # the same call, outside, works


def test_rater_answers_inside_the_repository_are_refused(study, tmp_path, fake_repo):
    make(study, tmp_path / "kit")
    inside = fake_repo / "rater-answers.json"
    inside.write_text("{}", encoding="utf-8")
    code = kit.main(
        [
            "convert",
            "--answers",
            str(inside),
            "--items",
            str(tmp_path / "kit" / "items.json"),
            "--reviewer-token",
            "R2",
            "--reviewed-at",
            "2026-11-08T00:00:00Z",
            "--out",
            str(tmp_path / "o"),
        ]
    )
    assert code == 2 and not (tmp_path / "o").exists()


def test_nothing_is_overwritten(study, tmp_path):
    make(study, tmp_path / "kit")
    before = tree_bytes(tmp_path / "kit")
    code = kit.main(
        [
            "make",
            "--project",
            str(study["project"]),
            "--rubrics",
            str(study["rubrics"]),
            "--evidence",
            str(study["evidence"]),
            "--seed",
            "99",
            "--out",
            str(tmp_path / "kit"),
        ]
    )
    assert code == 2
    assert tree_bytes(tmp_path / "kit") == before


# --- answers to labels --------------------------------------------------------------------------


def answers_json(kit_dir: Path, choose, saved_at="2026-11-09T10:00:00.000Z") -> Path:
    items = json.loads((kit_dir / "items.json").read_text())
    answers = [
        {"item_id": c["item_id"], "answer": choose(c) or "", "note": ""} for c in items["cells"]
    ]
    path = kit_dir.parent / "rater-answers.json"
    path.write_text(
        json.dumps(
            {
                "kit_version": 1,
                "kit_digest": items["kit_digest"],
                "saved_at": saved_at,
                "answers": answers,
            }
        ),
        encoding="utf-8",
    )
    return path


def convert(kit_dir, answers, token="R2", out=None, reviewed_at=None):
    out = out or kit_dir.parent / f"labels-{token}"
    args = [
        "convert",
        "--answers",
        str(answers),
        "--items",
        str(kit_dir / "items.json"),
        "--reviewer-token",
        token,
        "--out",
        str(out),
    ]
    if reviewed_at:
        args += ["--reviewed-at", reviewed_at]
    code = kit.main(args)
    return code, out


def test_convert_maps_labels_to_positional_levels_and_cannot_tell_to_an_abstention(study, tmp_path):
    make(study, tmp_path / "kit")

    def choose(cell):
        if cell["item_id"].endswith("__f1") and cell["alternative_id"] == "co0":
            return "cannot tell"
        if cell["item_id"].endswith("__f2") and cell["alternative_id"] == "co0":
            return None  # unanswered
        return cell["labels"][1]  # the second label of its own vocabulary

    code, out = convert(tmp_path / "kit", answers_json(tmp_path / "kit", choose))
    assert code == 0
    five = json.loads((out / "human_labels.invented-5-level.R2.json").read_text())
    four = json.loads((out / "human_labels.invented-4-level.R2.json").read_text())
    by_id = {r["item_id"]: r for r in five + four}
    assert by_id["co0__f1"]["label"] is None  # an abstention, not a nominal class
    assert "co0__f2" not in by_id  # unanswered rows are absent, not guessed
    assert by_id["co1__f1"]["label"] == "level_2" and by_id["co1__g1"]["label"] == "level_2"
    assert {r["reviewer"] for r in five + four} == {"R2"}
    assert all(r["reviewed_at"] == "2026-11-09T10:00:00Z" for r in five + four)
    assert len(five) + len(four) == len(COMPANIES) * 6 - 1


def test_convert_accepts_a_number_and_the_csv_and_refuses_nonsense(study, tmp_path):
    make(study, tmp_path / "kit")
    form = tmp_path / "kit" / "rater-form.csv"
    rows = list(csv.DictReader(form.open(newline="")))
    rows[0]["answer"] = "3"
    rows[1]["answer"] = rows[1]["labels"].split(" | ")[0].split(") ", 1)[1]
    rows[2]["answer"] = "Cannot Tell"
    filled = tmp_path / "filled.csv"
    with filled.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=kit.CSV_HEADER)
        writer.writeheader()
        writer.writerows(rows)
    code, out = convert(tmp_path / "kit", filled, reviewed_at="2026-11-09T00:00:00+13:00")
    assert code == 0
    labelled = {
        r["item_id"]: r for f in out.glob("human_labels.*.json") for r in json.loads(f.read_text())
    }
    assert labelled[rows[0]["item_id"]]["label"] == "level_3"
    assert labelled[rows[1]["item_id"]]["label"] == "level_1"
    assert labelled[rows[2]["item_id"]]["label"] is None
    assert labelled[rows[0]["item_id"]]["reviewed_at"] == "2026-11-08T11:00:00Z"
    rows[3]["answer"] = "nonsense"
    bad = tmp_path / "bad.csv"
    with bad.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=kit.CSV_HEADER)
        writer.writeheader()
        writer.writerows(rows)
    assert convert(tmp_path / "kit", bad, token="R3", reviewed_at="2026-11-09T00:00:00Z")[0] == 2


def test_answers_from_another_packet_a_duplicate_or_a_missing_time_are_refused(study, tmp_path):
    make(study, tmp_path / "kit")
    path = answers_json(tmp_path / "kit", lambda c: c["labels"][0])
    data = json.loads(path.read_text())
    data["kit_digest"] = "0" * 64
    path.write_text(json.dumps(data))
    assert convert(tmp_path / "kit", path, token="R3")[0] == 2
    data["kit_digest"] = json.loads((tmp_path / "kit" / "items.json").read_text())["kit_digest"]
    data["answers"].append(data["answers"][0])
    path.write_text(json.dumps(data))
    assert convert(tmp_path / "kit", path, token="R4")[0] == 2
    del data["answers"][-1]
    del data["saved_at"]
    path.write_text(json.dumps(data))
    assert convert(tmp_path / "kit", path, token="R5")[0] == 2  # no time anywhere


def author(kit_dir, project, reviewed_at="2026-11-07T12:00:00Z", token="R1"):
    out = kit_dir.parent / f"labels-{token}"
    code = kit.main(
        [
            "author-labels",
            "--project",
            str(project),
            "--items",
            str(kit_dir / "items.json"),
            "--reviewer-token",
            token,
            "--reviewed-at",
            reviewed_at,
            "--out",
            str(out),
        ]
    )
    return code, out


def test_author_labels_are_the_projects_ratings_as_positional_levels(study, tmp_path):
    make(study, tmp_path / "kit")
    code, out = author(tmp_path / "kit", study["project"])
    assert code == 0
    rows = {
        r["item_id"]: r["label"]
        for f in out.glob("human_labels.*.json")
        for r in json.loads(f.read_text())
    }
    project = json.loads(study["project"].read_text())
    for p in project["performances"]:
        item = f"{p['alternative_id']}__{p['criterion_id']}"
        if p["criterion_id"] in FIVE_LEAVES:
            assert rows[item] == f"level_{FIVE.index(p['value']) + 1}"
        elif p["criterion_id"] in FOUR_LEAVES:
            assert rows[item] == f"level_{FOUR.index(p['value']) + 1}"
        else:
            assert item not in rows  # numeric and mandate cells are not rated


# --- the frozen protocol and the benchmark round trip -------------------------------------------


def freeze(kit_dir, study, frozen_at="2026-11-07T12:00:00Z", out=None, **extra):
    out = out or kit_dir.parent / "benchmark"
    args = [
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
        frozen_at,
        "--out",
        str(out),
    ]
    for key, value in extra.items():
        args += [f"--{key.replace('_', '-')}", value]
    return kit.main(args), out


def test_the_frozen_protocol_has_one_task_per_vocabulary_and_records_its_mapping(study, tmp_path):
    make(study, tmp_path / "kit")
    code, out = freeze(tmp_path / "kit", study)
    assert code == 0
    digests = json.loads((out / "frozen-digests.json").read_text())
    assert set(digests) == {"invented-4-level", "invented-5-level"}
    five = json.loads((out / "invented-5-level" / "frozen-protocol.json").read_text())
    core = five["core"]
    assert core["labels"] == [f"level_{i}" for i in range(1, 6)]
    assert core["panel"] == ["R1", "R2"] and core["data_kind"] == "public"
    assert (
        core["protocol"]["lower_kappa"] == "0.60" and core["protocol"]["minimum_coverage"] == "0.80"
    )
    assert core["splits"]["train"] == [] and len(core["splits"]["test"]) == 40
    assert five["label_mapping"]["f1"]["levels"]["level_5"] == "Excellent"
    assert "conservative" in core["data_provenance"]["description"]
    assert (
        "UNDERPOWERED"
        in json.loads((out / "invented-4-level" / "frozen-protocol.json").read_text())["core"][
            "data_provenance"
        ]["description"]
    )
    assert "UNDERPOWERED" not in core["data_provenance"]["description"]
    assert digests["invented-5-level"] == five["digest"]
    again = freeze(tmp_path / "kit", study, out=tmp_path / "again")[1]
    assert tree_bytes(out) == tree_bytes(again)


def test_a_frozen_protocol_needs_an_ordered_chronology_and_a_timezone(study, tmp_path):
    make(study, tmp_path / "kit")
    assert (
        freeze(
            tmp_path / "kit", study, out=tmp_path / "x1", gate_confirmed_at="2026-11-01T00:00:00Z"
        )[0]
        == 2
    )
    assert (
        freeze(tmp_path / "kit", study, frozen_at="2026-11-07T12:00:00", out=tmp_path / "x2")[0]
        == 2
    )
    assert not (tmp_path / "x1").exists() and not (tmp_path / "x2").exists()


def tool_files(
    directory: Path, task_id: str, ids: list[str], labels: list[str]
) -> tuple[Path, Path]:
    half = [f"{2 ** -(i + 1)}" for i in range(len(labels))]
    half[-1] = f"{2 ** -(len(labels) - 1)}"
    card = directory / "card.json"
    card.write_text(
        json.dumps({"model_version": "m-1", "purpose": "invented", "limitations": "none"})
    )
    digest = hashlib.sha256(card.read_bytes()).hexdigest()
    rows = []
    for item in ids:
        vector = dict(zip(labels, half, strict=True))
        rows.append(
            {
                "item_id": item,
                "tool_id": "tool",
                "tool_version": "1",
                "task_version": "1",
                "model_card_digest": digest,
                "label": labels[0],
                "run_at": "2026-11-08T00:00:00Z",
                "score": None,
                "probabilities": json.loads(json.dumps(vector), parse_float=str),
            }
        )
    outputs = directory / "tool_outputs.json"
    text = json.dumps(rows)
    # decimals as numbers (the benchmark parses exact decimals from the text)
    for value in set(half):
        text = text.replace(f'"{value}"', value)
    outputs.write_text(text)
    return outputs, card


@pytest.mark.parametrize(
    "task_id,leaves,labels",
    [("invented-5-level", FIVE_LEAVES, 5), ("invented-4-level", FOUR_LEAVES, 4)],
)
def test_converted_two_rater_labels_run_through_the_benchmark_itself(
    study, tmp_path, task_id, leaves, labels
):
    make(study, tmp_path / "kit")
    _, r1 = author(tmp_path / "kit", study["project"])
    # the second rater agrees with the author except on three cells
    flip = {"co0__" + leaves[0], "co3__" + leaves[0], "co5__" + leaves[-1]}
    project = json.loads(study["project"].read_text())
    truth = {
        f"{p['alternative_id']}__{p['criterion_id']}": p["value"] for p in project["performances"]
    }

    def choose(cell):
        labels_ = cell["labels"]
        index = labels_.index(truth[cell["item_id"]])
        return labels_[(index + 1) % len(labels_)] if cell["item_id"] in flip else labels_[index]

    _, r2 = convert(tmp_path / "kit", answers_json(tmp_path / "kit", choose))
    code, bench_dir = freeze(tmp_path / "kit", study)
    assert code == 0
    task = bench_dir / task_id
    ids = [i["id"] for i in json.loads((task / "items.json").read_text())]
    outputs, card = tool_files(tmp_path, task_id, ids, [f"level_{i}" for i in range(1, labels + 1)])
    final = tmp_path / f"final-{task_id}"
    assert (
        kit.main(
            [
                "finalize",
                "--protocol",
                str(task / "frozen-protocol.json"),
                "--human-labels",
                str(r1 / f"human_labels.{task_id}.R1.json"),
                str(r2 / f"human_labels.{task_id}.R2.json"),
                "--tool-outputs",
                str(outputs),
                "--tool-card",
                str(card),
                "--tool-id",
                "tool",
                "--tool-version",
                "1",
                "--out",
                str(final),
            ]
        )
        == 0
    )
    report = bench.evaluate(final / "manifest.json")
    assert report["status"] in {"reference accepted", "reference unresolved", "reference refused"}
    agreement = report["agreement"]
    assert agreement["coverage"]["numerator"] == str(len(ids))  # both reviewers on every item
    assert agreement["coverage"]["denominator"] == str(len(ids))
    assert agreement["statistic"] == "Cohen"
    assert report["manifest"]["task"]["id"] == task_id
    # the benchmark read every kit row: both reviewers on every test item
    assert len(report["raw_human_labels"]) == 2 * len(ids)


def test_finalize_refuses_a_protocol_changed_after_it_was_frozen(study, tmp_path):
    make(study, tmp_path / "kit")
    _, r1 = author(tmp_path / "kit", study["project"])
    code, bench_dir = freeze(tmp_path / "kit", study)
    task = bench_dir / "invented-5-level"
    protocol = json.loads((task / "frozen-protocol.json").read_text())
    protocol["core"]["protocol"]["lower_kappa"] = "0.10"  # a quietly relaxed gate
    (task / "frozen-protocol.json").write_text(json.dumps(protocol))
    ids = [i["id"] for i in json.loads((task / "items.json").read_text())]
    outputs, card = tool_files(tmp_path, "t", ids, [f"level_{i}" for i in range(1, 6)])
    assert (
        kit.main(
            [
                "finalize",
                "--protocol",
                str(task / "frozen-protocol.json"),
                "--human-labels",
                str(r1 / "human_labels.invented-5-level.R1.json"),
                "--tool-outputs",
                str(outputs),
                "--tool-card",
                str(card),
                "--tool-id",
                "tool",
                "--tool-version",
                "1",
                "--out",
                str(tmp_path / "f"),
            ]
        )
        == 2
    )
    assert not (tmp_path / "f").exists()


def test_real_manifests_are_refused_inside_the_repository(study, tmp_path, fake_repo):
    make(study, tmp_path / "kit")
    assert freeze(tmp_path / "kit", study, out=fake_repo / "benchmark")[0] == 2
    assert not (fake_repo / "benchmark").exists()
