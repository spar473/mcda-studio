"""Blind rater kit for the venture-screening study (``docs/design/blind-rater-kit.md``).

A second person rates the study's rubric cells from the cited pages and the written rubrics only,
so the classifier agreement benchmark's human-agreement gate can run before any tool is compared
with the study author's ratings. This script is outside the application: it uses only the standard
library and never imports ``mcda_studio`` or the benchmark.

Subcommands: ``make`` (rater packet, form and item table), ``convert`` (a rater's answers to
benchmark ``human_labels`` rows), ``author-labels`` (the study author's own ratings as reviewer
rows), ``manifest`` (draft and freeze the benchmark protocol, one task per label vocabulary) and
``finalize`` (assemble a benchmark manifest once labels, tool outputs and a tool card exist).

Real answers, labels, manifests and packets live outside the checkout. Every output path and every
real-data input path inside the repository is refused after resolving symlinks.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
KIT_VERSION = 1
CANNOT_TELL = "cannot tell"
MIN_POWERED_ITEMS = 30
PANEL = ["R1", "R2"]
BOOTSTRAP_SEED = 20261107
DEFAULT_GATE_CONFIRMED_AT = "2027-03-31T00:00:00Z"
DEFAULT_UNBLINDED_AT = "2027-04-30T00:00:00Z"
OBSERVATION_CUTOFF = "2026-11-04T00:00:00Z"
CSV_HEADER = ["item_id", "company", "criterion", "sources", "rubric", "labels", "answer", "note"]
MAX_BYTES = 8_000_000


class KitError(ValueError):
    """A refusal with a plain reason."""


def require(condition: object, reason: str) -> None:
    if not condition:
        raise KitError(reason)


# ----------------------------------------------------------------------------- files and paths


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(value: Any) -> str:
    return sha(canonical(value).encode("utf-8"))


def pretty(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def outside_repo(path: Path, what: str) -> Path:
    """Resolve symlinks first, then refuse anything inside the checkout."""
    resolved = path.expanduser().resolve()
    require(
        not resolved.is_relative_to(ROOT),
        f"{what} is refused inside the repository; use a directory outside it, for example "
        "$MCDA_DATA",
    )
    return resolved


def read_bytes(path: Path) -> bytes:
    require(path.is_file(), f"Not a file: {path.name}")
    require(path.stat().st_size <= MAX_BYTES, f"{path.name} is larger than 8 MB")
    return path.read_bytes()


def read_json(path: Path) -> Any:
    try:
        return json.loads(read_bytes(path).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KitError(f"{path.name} is not valid UTF-8 JSON: {exc}") from exc


def write_files(out: Path, files: dict[str, str]) -> list[Path]:
    """Create new files only, after every name has been checked; nothing is overwritten."""
    target = outside_repo(out, "Output")
    paths = {name: target / name for name in files}
    for name, path in paths.items():
        require(not path.exists(), f"Refusing to overwrite {name}")
    target.mkdir(parents=True, exist_ok=True)
    for name, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(files[name])
    return list(paths.values())


def stamp(value: str, what: str) -> str:
    """A timezone-aware ISO time, normalised to UTC with a trailing Z."""
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise KitError(f"{what} is not an ISO 8601 time") from exc
    require(parsed.tzinfo is not None, f"{what} must carry a timezone")
    return parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ----------------------------------------------------------------------------- study inputs


def load_study(project_path: Path, rubrics_path: Path, evidence_path: Path) -> dict[str, Any]:
    """Read only what the packet may show: names, rubrics and source links.

    The project is read for alternative and criterion identity; evidence for each claim's
    alternative, criterion and source reference. Ratings, values, descriptions, reviews, notes and
    measurements are never read here.
    """
    project = read_json(project_path)
    rubrics = read_json(rubrics_path)
    evidence = read_json(evidence_path)
    require(
        isinstance(project, dict) and isinstance(project.get("alternatives"), list), "Bad project"
    )
    require(isinstance(rubrics, dict) and rubrics.get("version") == 1, "Unsupported rubrics file")
    require(isinstance(evidence, dict) and isinstance(evidence.get("claims"), list), "Bad evidence")
    companies = [(str(a["id"]), str(a["name"])) for a in project["alternatives"]]
    require(len({c for c, _ in companies}) == len(companies), "Duplicate company IDs")
    leaves = []
    for leaf in rubrics["scored_leaves"]:
        if leaf["numeric"]:
            continue
        labels = list(leaf["labels"])
        require(len(labels) >= 2 and len(set(labels)) == len(labels), f"Bad labels: {leaf['id']}")
        leaves.append(
            {
                "id": str(leaf["id"]),
                "name": str(leaf["name"]),
                "parent_id": str(leaf["parent_id"]),
                "parent_name": str(leaf["parent_name"]),
                "labels": labels,
                "rubric": str(leaf["rubric"]),
            }
        )
    require(bool(leaves), "No rateable rubric leaves")
    leaf_ids = {leaf["id"] for leaf in leaves}
    links: dict[str, set[str]] = {company: set() for company, _ in companies}
    for claim in evidence["claims"]:
        alternative, criterion = claim.get("alternative_id"), claim.get("criterion_id")
        if alternative in links and criterion in leaf_ids:
            reference = (claim.get("source") or {}).get("reference")
            if isinstance(reference, str) and reference.startswith(("http://", "https://")):
                links[alternative].add(reference)
    return {
        "study": str(rubrics["study"]),
        "companies": companies,
        "leaves": leaves,
        "links": {company: sorted(urls) for company, urls in links.items()},
        "excluded": [str(leaf["id"]) for leaf in rubrics.get("screened_excluded", [])]
        + [str(leaf["id"]) for leaf in rubrics["scored_leaves"] if leaf["numeric"]],
    }


def order_by_seed(keys: list[str], seed: int, scope: str) -> list[str]:
    """A seeded, platform-independent shuffle: sort by a hash of the seed, scope and key."""
    return sorted(keys, key=lambda key: sha(f"{seed}|{scope}|{key}".encode()))


def build_kit(study: dict[str, Any], seed: int) -> dict[str, Any]:
    """The item table: tasks by label-vocabulary size and one cell per company and leaf."""
    sizes = sorted({len(leaf["labels"]) for leaf in study["leaves"]})
    tasks = []
    task_of: dict[str, str] = {}
    for size in sizes:
        task_id = f"{study['study']}-{size}-level"
        members = [leaf["id"] for leaf in study["leaves"] if len(leaf["labels"]) == size]
        tasks.append(
            {
                "id": task_id,
                "levels": size,
                "labels": [f"level_{i}" for i in range(1, size + 1)],
                "leaf_ids": members,
            }
        )
        for member in members:
            task_of[member] = task_id
    names = dict(study["companies"])
    leaf_by_id = {leaf["id"]: leaf for leaf in study["leaves"]}
    company_order = order_by_seed([c for c, _ in study["companies"]], seed, "company")
    leaf_order = order_by_seed(list(leaf_by_id), seed, "leaf")
    cells = []
    for company in company_order:
        for leaf_id in leaf_order:
            leaf = leaf_by_id[leaf_id]
            cells.append(
                {
                    "item_id": f"{company}__{leaf_id}",
                    "alternative_id": company,
                    "company": names[company],
                    "criterion_id": leaf_id,
                    "criterion": leaf["name"],
                    "task_id": task_of[leaf_id],
                    "labels": leaf["labels"],
                }
            )
    kit = {
        "kit_version": KIT_VERSION,
        "seed": seed,
        "study": study["study"],
        "tasks": tasks,
        "company_order": company_order,
        "leaf_order": leaf_order,
        "cells": cells,
        "excluded_leaf_ids": sorted(study["excluded"]),
        "cannot_tell": CANNOT_TELL,
    }
    kit["kit_digest"] = digest({k: v for k, v in kit.items() if k != "kit_digest"})
    return kit


def load_kit(path: Path) -> dict[str, Any]:
    kit: dict[str, Any] = read_json(path)
    require(isinstance(kit, dict) and kit.get("kit_version") == KIT_VERSION, "Unsupported kit")
    require(
        kit.get("kit_digest") == digest({k: v for k, v in kit.items() if k != "kit_digest"}),
        "The item table does not match its digest",
    )
    return kit


# ----------------------------------------------------------------------------- packet and form


INSTRUCTIONS = [
    "You are the second, independent rater. Rate each cell below from the cited public pages and "
    "the written rubric only.",
    "Do not look at any other rating of these companies, the study that this comes from, or any "
    "automated tool's output. Do not discuss your answers with the first rater until you have "
    "sent yours back.",
    "For each company, open the cited pages. Then, for each criterion, choose the one label that "
    "the pages best support under the rubric. Choose “cannot tell” when the pages do not let you "
    "decide; do not guess. A note is optional.",
    "Press “Save answers” when you finish (you can press it earlier and again later). It downloads "
    "a small file, rater-answers.json, to your computer. Nothing is sent anywhere. Return that "
    "file.",
    "This is a screening exercise on public information. It is not investment advice and says "
    "nothing about any company's prospects.",
]

SCRIPT = """
(function () {
  var KIT = %s;
  function collect() {
    var answers = [];
    document.querySelectorAll("section.cell").forEach(function (cell) {
      var chosen = cell.querySelector("input[type=radio]:checked");
      var note = cell.querySelector("textarea");
      answers.push({
        item_id: cell.getAttribute("data-item"),
        answer: chosen ? chosen.value : "",
        note: note ? note.value : ""
      });
    });
    return {kit_version: 1, kit_digest: KIT, saved_at: new Date().toISOString(), answers: answers};
  }
  document.getElementById("save").addEventListener("click", function () {
    var blob = new Blob([JSON.stringify(collect(), null, 2)], {type: "application/json"});
    var link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "rater-answers.json";
    document.body.appendChild(link);
    link.click();
    link.remove();
  });
})();
"""

STYLE = """
body{font:16px/1.5 system-ui,sans-serif;max-width:56rem;margin:0 auto;padding:1rem}
h1{font-size:1.5rem}h2{font-size:1.25rem;border-top:2px solid #444;padding-top:1rem}
section.cell{border:1px solid #bbb;border-radius:6px;padding:.75rem;margin:.75rem 0}
.rubric{color:#333;font-size:.9rem}label{display:block;margin:.15rem 0}
textarea{width:100%;min-height:2.5rem}button{font-size:1rem;padding:.5rem 1rem}
"""


def render_packet(kit: dict[str, Any], study: dict[str, Any]) -> str:
    leaf_by_id = {leaf["id"]: leaf for leaf in study["leaves"]}
    by_company: dict[str, list[dict[str, Any]]] = {}
    for cell in kit["cells"]:
        by_company.setdefault(cell["alternative_id"], []).append(cell)
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Rater packet</title>",
        f"<style>{STYLE}</style></head><body>",
        "<h1>Rater packet</h1>",
        "<h2>Instructions</h2>",
        "<ol>" + "".join(f"<li>{html.escape(line)}</li>" for line in INSTRUCTIONS) + "</ol>",
        f"<p>{len(kit['cells'])} cells to rate. "
        '<button id="save" type="button">Save answers</button></p>',
    ]
    for company in kit["company_order"]:
        cells = by_company[company]
        parts.append(f"<h2>{html.escape(cells[0]['company'])}</h2>")
        urls = study["links"].get(company, [])
        if urls:
            parts.append("<p>Cited pages:</p><ul>")
            parts += [
                f'<li><a href="{html.escape(url, quote=True)}" rel="noopener noreferrer" '
                f'target="_blank">{html.escape(url)}</a></li>'
                for url in urls
            ]
            parts.append("</ul>")
        else:
            parts.append("<p>No cited pages are available for this company.</p>")
        for cell in cells:
            leaf = leaf_by_id[cell["criterion_id"]]
            item = html.escape(cell["item_id"], quote=True)
            parts.append(f'<section class="cell" data-item="{item}">')
            parts.append(f"<h3>{html.escape(leaf['name'])}</h3>")
            parts.append(f'<p class="rubric">{html.escape(leaf["rubric"])}</p>')
            for position, label in enumerate(cell["labels"], start=1):
                parts.append(
                    f'<label><input type="radio" name="{item}" '
                    f'value="{html.escape(label, quote=True)}"> '
                    f"{position}. {html.escape(label)}</label>"
                )
            parts.append(
                f'<label><input type="radio" name="{item}" value="{CANNOT_TELL}"> '
                f"Cannot tell from the pages</label>"
            )
            parts.append(
                f'<label>Note (optional)<textarea aria-label="Note for {item}"></textarea></label>'
            )
            parts.append("</section>")
    parts.append(f"<script>{SCRIPT % json.dumps(kit['kit_digest'])}</script>")
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


def spreadsheet_safe(value: str) -> str:
    """Keep a cell from being read as a formula by a spreadsheet."""
    return "'" + value if value[:1] in {"=", "+", "-", "@", "\t", "\r"} else value


def render_form(kit: dict[str, Any], study: dict[str, Any]) -> str:
    leaf_by_id = {leaf["id"]: leaf for leaf in study["leaves"]}
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for cell in kit["cells"]:
        leaf = leaf_by_id[cell["criterion_id"]]
        labels = " | ".join(f"{i}) {label}" for i, label in enumerate(cell["labels"], start=1))
        writer.writerow(
            [
                spreadsheet_safe(value)
                for value in (
                    cell["item_id"],
                    cell["company"],
                    cell["criterion"],
                    " ".join(study["links"].get(cell["alternative_id"], [])),
                    leaf["rubric"],
                    labels + f" | or write: {CANNOT_TELL}",
                    "",
                    "",
                )
            ]
        )
    return buffer.getvalue()


def command_make(args: argparse.Namespace) -> int:
    study = load_study(Path(args.project), Path(args.rubrics), Path(args.evidence))
    kit = build_kit(study, args.seed)
    files = {
        "rater-packet.html": render_packet(kit, study),
        "rater-form.csv": render_form(kit, study),
        "items.json": pretty(kit),
    }
    for path in write_files(Path(args.out), files):
        print(f"wrote {path}")
    print(f"kit digest {kit['kit_digest']}; {len(kit['cells'])} cells")
    return 0


# ----------------------------------------------------------------------------- labels


def parse_answers(path: Path) -> tuple[dict[str, dict[str, str]], str | None, str | None]:
    """Answers by item from the packet's JSON or the form's CSV: (rows, digest, saved time)."""
    raw = read_bytes(path)
    if path.suffix.lower() == ".csv":
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        require(reader.fieldnames == CSV_HEADER, "The CSV header was changed; use rater-form.csv")
        rows = {}
        for number, row in enumerate(reader, start=2):
            item = (row["item_id"] or "").strip().lstrip("'")
            require(item and item not in rows, f"Missing or duplicate item_id on line {number}")
            rows[item] = {"answer": (row["answer"] or "").strip(), "note": row["note"] or ""}
        return rows, None, None
    data = json.loads(raw.decode("utf-8"))
    require(isinstance(data, dict) and isinstance(data.get("answers"), list), "Bad answers file")
    rows = {}
    for entry in data["answers"]:
        require(isinstance(entry, dict), "Bad answer entry")
        item = entry.get("item_id")
        require(isinstance(item, str) and item not in rows, "Missing or duplicate item_id")
        answer, note = entry.get("answer", ""), entry.get("note", "")
        require(isinstance(answer, str) and isinstance(note, str), "Answers must be text")
        rows[item] = {"answer": answer.strip(), "note": note}
    return rows, data.get("kit_digest"), data.get("saved_at")


def resolve_answer(answer: str, labels: list[str]) -> int | None:
    """The 0-based label index, ``-1`` for cannot tell and ``None`` for unanswered."""
    if not answer:
        return None
    lowered = answer.casefold()
    if lowered == CANNOT_TELL:
        return -1
    for index, label in enumerate(labels):
        if lowered == label.casefold():
            return index
    if answer.isdigit() and 1 <= int(answer) <= len(labels):
        return int(answer) - 1
    raise KitError(
        f"Unrecognised answer {answer!r}; use a listed label, its number or 'cannot tell'"
    )


def label_rows(
    kit: dict[str, Any],
    answers: dict[str, int | None],
    reviewer: str,
    reviewed_at: str,
) -> dict[str, list[dict[str, Any]]]:
    """Benchmark ``human_labels`` rows per task (a null label abstains; unanswered are absent)."""
    cells = {cell["item_id"]: cell for cell in kit["cells"]}
    tasks = {task["id"]: task for task in kit["tasks"]}
    out: dict[str, list[dict[str, Any]]] = {task_id: [] for task_id in tasks}
    for item_id in sorted(answers):
        index = answers[item_id]
        if index is None:
            continue
        cell = cells[item_id]
        labels = tasks[cell["task_id"]]["labels"]
        out[cell["task_id"]].append(
            {
                "item_id": item_id,
                "label": None if index < 0 else labels[index],
                "reviewed_at": reviewed_at,
                "reviewer": reviewer,
                "task_version": "1",
            }
        )
    return out


def write_label_files(
    out: Path, rows: dict[str, list[dict[str, Any]]], reviewer: str, extra: dict[str, str]
) -> None:
    files = {f"human_labels.{task_id}.{reviewer}.json": pretty(rs) for task_id, rs in rows.items()}
    files.update(extra)
    for path in write_files(out, files):
        print(f"wrote {path}")


def command_convert(args: argparse.Namespace) -> int:
    answers_path = outside_repo(Path(args.answers), "Rater answers")
    kit = load_kit(Path(args.items))
    rows, seen_digest, saved_at = parse_answers(answers_path)
    require(
        seen_digest is None or seen_digest == kit["kit_digest"],
        "These answers were saved from a different packet",
    )
    cells = {cell["item_id"]: cell for cell in kit["cells"]}
    unknown = sorted(set(rows) - set(cells))
    require(not unknown, f"Unknown items: {', '.join(unknown[:5])}")
    reviewed_at = stamp(args.reviewed_at or saved_at or "", "reviewed-at")
    resolved = {item: resolve_answer(rows[item]["answer"], cells[item]["labels"]) for item in rows}
    labelled = label_rows(kit, resolved, args.reviewer_token, reviewed_at)
    notes = {item: row["note"] for item, row in sorted(rows.items()) if row["note"].strip()}
    unanswered = sorted(item for item in cells if resolved.get(item) is None)
    write_label_files(
        Path(args.out),
        labelled,
        args.reviewer_token,
        {f"notes.{args.reviewer_token}.json": pretty(notes)},
    )
    abstained = sum(1 for index in resolved.values() if index is not None and index < 0)
    print(
        f"{sum(1 for i in resolved.values() if i is not None)} answered, {abstained} cannot tell, "
        f"{len(unanswered)} unanswered"
    )
    return 0


def command_author_labels(args: argparse.Namespace) -> int:
    kit = load_kit(Path(args.items))
    project = read_json(Path(args.project))
    require(isinstance(project, dict), "Bad project")
    cells = {cell["item_id"]: cell for cell in kit["cells"]}
    resolved: dict[str, int | None] = {}
    for performance in project["performances"]:  # the human side: measurements are allowed here
        item = f"{performance['alternative_id']}__{performance['criterion_id']}"
        if item in cells:
            labels = cells[item]["labels"]
            value = performance["value"]
            require(value in labels, f"{item}: {value!r} is not one of the scale's labels")
            resolved[item] = labels.index(value)
    missing = sorted(set(cells) - set(resolved))
    require(not missing, f"No author rating for {', '.join(missing[:5])}")
    reviewed_at = stamp(args.reviewed_at, "reviewed-at")
    labelled = label_rows(kit, resolved, args.reviewer_token, reviewed_at)
    write_label_files(Path(args.out), labelled, args.reviewer_token, {})
    print(f"{len(resolved)} author ratings written as reviewer {args.reviewer_token}")
    return 0


# ----------------------------------------------------------------------------- manifests


def source_list_digest(evidence_path: Path, leaf_ids: set[str]) -> str:
    """A digest of the cited-source identity list (URLs, names and dates), not of any rating."""
    evidence = read_json(evidence_path)
    identities = set()
    for claim in evidence["claims"]:
        if claim.get("criterion_id") in leaf_ids:
            source = claim.get("source") or {}
            identities.add(
                (str(source.get("reference")), str(source.get("name")), str(source.get("date")))
            )
    return digest(sorted(identities))


def task_description(task: dict[str, Any], count: int, groups: int, mapping: dict[str, Any]) -> str:
    text = (
        f"Rate one company's rubric criterion (cell) on a {task['levels']}-level ordered scale. "
        f"Labels are positional: level_1 is the worst for the fund, level_{task['levels']} "
        "the best. "
        f"Criteria in this task: {', '.join(task['leaf_ids'])}. Each criterion's own wording per "
        "level is in the frozen protocol's label_mapping. "
        f"{count} items from {groups} companies (entity = company; bootstrap unit = company). "
        "Unweighted kappa treats the ordered levels as nominal, so it is conservative for ordinal "
        "labels. The gate is the design's recommendation: lower 95% bound of at least 0.60 and "
        "80% complete-label coverage. Every item is test (zero-shot: nothing is trained). "
    )
    if count < MIN_POWERED_ITEMS:
        text += f"UNDERPOWERED: fewer than {MIN_POWERED_ITEMS} items. "
    text += (
        "Reviewer R1 is the study author's existing ratings, made on 4 November 2026 before this "
        "protocol was frozen and stamped with the freeze time because the benchmark requires "
        "human review times inside the frozen window. R2 rates blind from the cited pages."
    )
    del mapping
    return text


def build_protocol(
    kit: dict[str, Any],
    study_leaves: dict[str, dict[str, Any]],
    source_digest: str,
    frozen_at: str,
    gate_confirmed_at: str,
    unblinded_at: str,
) -> dict[str, dict[str, Any]]:
    chronology = [frozen_at, gate_confirmed_at, unblinded_at]
    require(chronology == sorted(set(chronology)), "Need frozen < gate-confirmed < unblinded")
    out = {}
    for task in kit["tasks"]:
        cells = [cell for cell in kit["cells"] if cell["task_id"] == task["id"]]
        items = [
            {
                "id": cell["item_id"],
                "entity_id": cell["alternative_id"],
                "group_id": cell["alternative_id"],
                "split": "test",
                "eligible": True,
                "exclusion_reason": "",
                "observed_at": OBSERVATION_CUTOFF,
                "feature_dates": {"cited_pages": OBSERVATION_CUTOFF},
            }
            for cell in sorted(cells, key=lambda c: c["item_id"])
        ]
        items_text = pretty(items)
        mapping = {
            leaf_id: {
                "name": study_leaves[leaf_id]["name"],
                "levels": dict(zip(task["labels"], study_leaves[leaf_id]["labels"], strict=True)),
            }
            for leaf_id in task["leaf_ids"]
        }
        core = {
            "version": 1,
            "data_kind": "public",
            "data_provenance": {
                "description": task_description(
                    task, len(items), len({i["group_id"] for i in items}), mapping
                ),
                "source": "Public web pages cited in the venture-screening study",
                "licence": "unknown - private research copy, not for redistribution",
                "snapshot_sha256": source_digest,
            },
            "task": {
                "id": task["id"],
                "version": "1",
                "instructions": (
                    "Choose the one level that the cited public pages best support under the "
                    "criterion's written rubric; abstain when the pages do not let you decide."
                ),
                "unit": "one company and one rubric criterion",
                "population": "Eight New Zealand startups named in the venture-screening study",
                "observation_cutoff": OBSERVATION_CUTOFF,
                "eligibility": "Every rubric criterion with labelled levels of this size",
                "exclusions": "Mandate criteria (screened) and the two numeric market criteria",
            },
            "labels": task["labels"],
            "panel": PANEL,
            "splits": {"train": [], "development": [], "test": [i["id"] for i in items]},
            "protocol": {
                "frozen_at": frozen_at,
                "gate_confirmed_at": gate_confirmed_at,
                "outputs_unblinded_at": unblinded_at,
                "independent_blind_reviews": True,
                "blind_adjudication": True,
                "reference_policy": "unanimous-or-post-gate-adjudication.v1",
                "confidence": "0.95",
                "lower_kappa": "0.60",
                "minimum_coverage": "0.80",
                "bootstrap": {
                    "replicates": 10000,
                    "seed": BOOTSTRAP_SEED,
                    "unit": "group",
                    "algorithm": "pcg64-joint-unit-bootstrap.v1",
                    "quantile": "linear.v1",
                },
            },
        }
        frozen = {
            "kit_version": KIT_VERSION,
            "kind": "frozen benchmark protocol (the manifest without its file and tool entries)",
            "core": core,
            "items_sha256": sha(items_text.encode("utf-8")),
            "label_mapping": mapping,
        }
        frozen["digest"] = digest(frozen)
        out[task["id"]] = {"frozen": frozen, "items_text": items_text}
    return out


def command_manifest(args: argparse.Namespace) -> int:
    kit = load_kit(Path(args.items))
    study = load_study(Path(args.project), Path(args.rubrics), Path(args.evidence))
    leaf_ids = {leaf["id"] for leaf in study["leaves"]}
    protocols = build_protocol(
        kit,
        {leaf["id"]: leaf for leaf in study["leaves"]},
        source_list_digest(Path(args.evidence), leaf_ids),
        stamp(args.frozen_at, "frozen-at"),
        stamp(args.gate_confirmed_at, "gate-confirmed-at"),
        stamp(args.unblinded_at, "unblinded-at"),
    )
    files = {}
    summary = {}
    for task_id, built in protocols.items():
        files[f"{task_id}/items.json"] = built["items_text"]
        files[f"{task_id}/frozen-protocol.json"] = pretty(built["frozen"])
        summary[task_id] = built["frozen"]["digest"]
    files["frozen-digests.json"] = pretty(summary)
    for path in write_files(Path(args.out), files):
        print(f"wrote {path}")
    for task_id, value in summary.items():
        print(f"frozen digest {task_id}: {value}")
    return 0


def command_finalize(args: argparse.Namespace) -> int:
    protocol_path = outside_repo(Path(args.protocol), "Frozen protocol")
    frozen = read_json(protocol_path)
    require(
        frozen.get("digest") == digest({k: v for k, v in frozen.items() if k != "digest"}),
        "The frozen protocol was changed after it was frozen",
    )
    items_path = protocol_path.parent / "items.json"
    items_bytes = read_bytes(items_path)
    require(sha(items_bytes) == frozen["items_sha256"], "The items table does not match the freeze")
    task_id = frozen["core"]["task"]["id"]
    labels = frozen["core"]["labels"]
    items = {item["id"] for item in json.loads(items_bytes)}
    merged: list[dict[str, Any]] = []
    for name in args.human_labels:
        rows = read_json(outside_repo(Path(name), "Human labels"))
        merged += rows
    for row in merged:
        require(row["item_id"] in items, f"Label for unknown item {row['item_id']}")
        require(row["label"] is None or row["label"] in labels, "Label outside the vocabulary")
    merged.sort(key=lambda r: (r["item_id"], r["reviewer"]))
    tool_outputs = read_bytes(Path(args.tool_outputs))
    card = read_bytes(Path(args.tool_card))
    adjudications = pretty([]) if args.adjudications is None else None
    adjudications_bytes = (
        adjudications.encode("utf-8")
        if adjudications is not None
        else read_bytes(Path(args.adjudications))
    )
    human_text = pretty(merged)
    files = {
        "items.json": items_bytes.decode("utf-8"),
        "human_labels.json": human_text,
        "tool_outputs.json": tool_outputs.decode("utf-8"),
        "adjudications.json": adjudications_bytes.decode("utf-8"),
        "tool-card.json": card.decode("utf-8"),
    }
    manifest = dict(frozen["core"])
    manifest["files"] = {
        key: {"path": f"{key}.json", "sha256": sha(files[f"{key}.json"].encode("utf-8"))}
        for key in ("items", "human_labels", "tool_outputs", "adjudications")
    }
    manifest["tools"] = [
        {
            "id": args.tool_id,
            "version": args.tool_version,
            "task_version": manifest["task"]["version"],
            "model_card": {"path": "tool-card.json", "sha256": sha(card)},
            "score_semantics": args.score_semantics,
            "score_bounds": None,
        }
    ]
    files["manifest.json"] = pretty(manifest)
    for path in write_files(Path(args.out), files):
        print(f"wrote {path}")
    print(f"manifest for {task_id} assembled from frozen digest {frozen['digest']}")
    return 0


# ----------------------------------------------------------------------------- command line


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = top.add_subparsers(dest="command", required=True)

    make = sub.add_parser("make", help="write the rater packet, form and item table")
    make.add_argument("--project", required=True)
    make.add_argument("--rubrics", required=True)
    make.add_argument("--evidence", required=True)
    make.add_argument("--seed", type=int, required=True)
    make.add_argument("--out", required=True)
    make.set_defaults(run=command_make)

    convert = sub.add_parser("convert", help="a rater's answers to benchmark human_labels rows")
    convert.add_argument("--answers", required=True)
    convert.add_argument("--items", required=True)
    convert.add_argument("--reviewer-token", required=True)
    convert.add_argument("--reviewed-at")
    convert.add_argument("--out", required=True)
    convert.set_defaults(run=command_convert)

    author = sub.add_parser("author-labels", help="the study author's ratings as reviewer rows")
    author.add_argument("--project", required=True)
    author.add_argument("--items", required=True)
    author.add_argument("--reviewer-token", default="R1")
    author.add_argument("--reviewed-at", required=True)
    author.add_argument("--out", required=True)
    author.set_defaults(run=command_author_labels)

    manifest = sub.add_parser("manifest", help="draft and freeze the benchmark protocol per task")
    manifest.add_argument("--items", required=True)
    manifest.add_argument("--project", required=True)
    manifest.add_argument("--rubrics", required=True)
    manifest.add_argument("--evidence", required=True)
    manifest.add_argument("--frozen-at", required=True)
    manifest.add_argument("--gate-confirmed-at", default=DEFAULT_GATE_CONFIRMED_AT)
    manifest.add_argument("--unblinded-at", default=DEFAULT_UNBLINDED_AT)
    manifest.add_argument("--out", required=True)
    manifest.set_defaults(run=command_manifest)

    final = sub.add_parser("finalize", help="assemble a benchmark manifest from a frozen protocol")
    final.add_argument("--protocol", required=True)
    final.add_argument("--human-labels", nargs="+", required=True)
    final.add_argument("--tool-outputs", required=True)
    final.add_argument("--tool-card", required=True)
    final.add_argument("--tool-id", required=True)
    final.add_argument("--tool-version", required=True)
    final.add_argument("--score-semantics", default="probability_vector")
    final.add_argument("--adjudications")
    final.add_argument("--out", required=True)
    final.set_defaults(run=command_finalize)
    return top


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.run(args))
    except KitError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
