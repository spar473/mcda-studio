"""Typed-proposal runner: classify cited source text into External Proposals, outside the app.

``docs/design/typed-proposal-runner.md`` is the design. This script is the only place a model is
ever run. It never imports ``mcda_studio`` and the application never imports it: the contract
between them is the published External Proposals files (``docs/schemas/external-proposals-csv.md``).

Import time needs only the standard library. A backend that needs more (``transformers``,
``torch``) imports it when it is used.

Subcommands
-----------
``snapshot``       fetch the evidence dossier's cited public pages politely and keep private copies
``questions``      one Choice question per company and rubric criterion, from source text only
``fetch-model``    download an allowlisted model (Qwen, two Laya checkpoints) with the env flag
``run``            answer the questions with a backend (replay, jev, local-hf, laya)
``export``         write External Proposals files and the benchmark's tool tables from a run
``compare-runs``   how two runs differ cell by cell (used with ``questions --swap``)

Real data (fetched pages, answers, model outputs) lives outside the checkout: every output path is
resolved through symlinks and refused inside the repository. Model output is only ever a proposal
for a person to review; confidence is metadata. Nothing here compares a tool with any rating.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNNER_VERSION = "0.1"
TEMPLATE_VERSION = "typed-proposal-prompt.v1"
CLIENT = "mcda-studio-research/0.1"
CANNOT_TELL = "cannot tell"
SNAPSHOT_LICENCE = "unknown — private research copy, not for redistribution"
STUDY_AS_OF = "2026-11-04"
MIN_INTERVAL = 1.0  # seconds between requests (the floor; tests lower it on a local server)
TIMEOUT = 20
MAX_PAGE_BYTES = 8_000_000
PLACES = 6  # probabilities are exact decimals with this many places
EXTRACTOR_VERSION = 2  # 1: visible text as fetched; 2: repeated and shared short lines dropped
SHORT_LINE_WORDS = 3  # a line of this many words or fewer is "short" (extractor version 2)
ORDER_AVERAGING = ("rotations", "none")
SCORING_AVERAGED = "first-token-letter-logprob.v2"
SCORING_SINGLE = "first-token-letter-logprob.v1"
SCORING_BACKEND = "backend-probabilities.v1"
SCORING_TEXT_AVERAGED = (
    "first-token letter log-likelihood, averaged over n cyclic option orders "
    "(n = the question's number of options, cannot tell included)"
)
SCORING_TEXT_SINGLE = "first-token letter log-likelihood, single option order (comparison only)"
DEFAULT_BUDGETS = {"local-hf": 12_000, "jev": 24_000, "laya": 4_000, "replay": 12_000}
JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-1.13.0"
QWEN_REPO = "Qwen/Qwen2.5-1.5B-Instruct"
LAYA_REPOS = ("convaiinnovations/laya", "convaiinnovations/laya-typed-decisions")
MODEL_ALLOWLIST = (QWEN_REPO, *LAYA_REPOS)
# A Laya checkpoint directory: the files `laya.Agent` reads. The base repository also bundles other
# checkpoints in subfolders, which these patterns never fetch.
LAYA_FILES = ["rl_agent_config.json", "model.safetensors", "tokenizer/*", "encoder/*"]
LAYA_NOTES = {
    "convaiinnovations/laya": (
        "Laya base: not fine-tuned for this task; the vendor reports near-random zero-shot accuracy"
    ),
    "convaiinnovations/laya-typed-decisions": (
        "fine-tuned on unrelated workflows (customer service, invoices, security, agent traces), "
        "not on startup screening"
    ),
}
LAYA_MARGIN = 8  # tokens kept free below the room the question leaves for the state
LAYA_MIN_BUDGET = 64  # a question leaving fewer state tokens than this is refused
LAYA_OPTION_TOKENS = 48  # laya 0.4.32 `common.build_head` silently caps each option at this
SCORING_KEYED_AVERAGED = "backend-probabilities-rotations.v1"
SCORING_TEXT_KEYED_AVERAGED = (
    "probabilities reported by the backend for each option, averaged over n cyclic option orders "
    "(n = the question's number of options, cannot tell included)"
)
SCORING_LAYA_AVERAGED = "laya-choice-chunk-mean.v1"
SCORING_LAYA_SINGLE = "laya-choice-chunk-mean-single-order.v1"
#: The second Laya reading, recorded beside the mean (never instead of it).
MAX_CONFIDENCE_CHUNK = "max_confidence_chunk"
READING_MAX_CONFIDENCE_CHUNK = (
    "max_confidence_chunk: the order-averaged vector of the chunk whose largest probability is "
    "highest decides (the package's own long-text rule; ties go to the earlier chunk); recorded "
    "beside the mean over chunks, which stays the reading"
)
READINGS = {"mean": None, "max-confidence-chunk": MAX_CONFIDENCE_CHUNK}
SCORING_TEXT_LAYA = (
    "Laya choice probabilities (reported to four decimals by the package, renormalised), the "
    "arithmetic mean over paragraph chunks of the state that each fit the checkpoint's window"
)
CSV_HEADER = [
    "schema_version",
    "project_fingerprint",
    "proposal_id",
    "proposal_version",
    "kind",
    "alternative_id",
    "criterion_id",
    "payload_json",
    "tool_id",
    "tool_version",
    "model_card_id",
    "model_card_digest",
    "run_at",
    "confidence_json",
    "source_ids_json",
    "replaces_proposal_id",
]
CONFIDENCE_MEANING = "Tool-reported probability of the selected label; uncalibrated; metadata only"
INSTRUCTION = (
    "Choose the one option best supported by the text above, judged against the rubric. If the "
    "text does not let you decide, choose the 'cannot tell' option. Do not guess."
)


class RunnerError(ValueError):
    """A refusal with a plain reason."""


def require(condition: object, reason: str) -> None:
    if not condition:
        raise RunnerError(reason)


# ----------------------------------------------------------------------------- files and paths


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(value: Any) -> str:
    return sha(canonical(value).encode("utf-8"))


def pretty(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def outside_repo(path: Path, what: str) -> Path:
    """Resolve symlinks first, then refuse anything inside the checkout."""
    resolved = path.expanduser().resolve()
    require(
        not resolved.is_relative_to(ROOT),
        f"{what} is refused inside the repository; use a directory outside it, for example "
        "$MCDA_DATA",
    )
    return resolved


def read_bytes(path: Path, limit: int = 64_000_000) -> bytes:
    require(path.is_file(), f"Not a file: {path.name}")
    require(path.stat().st_size <= limit, f"{path.name} is too large")
    return path.read_bytes()


def read_json(path: Path) -> Any:
    try:
        return json.loads(read_bytes(path).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunnerError(f"{path.name} is not valid UTF-8 JSON: {exc}") from exc


def write_new(out: Path, files: dict[str, str | bytes]) -> list[Path]:
    """Create new files only, after every name has been checked; nothing is overwritten."""
    target = outside_repo(out, "Output")
    paths = {name: target / name for name in files}
    for name, path in paths.items():
        require(not path.exists(), f"Refusing to overwrite {name}")
    for name, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        data = files[name]
        with path.open("xb") as handle:
            handle.write(data if isinstance(data, bytes) else data.encode("utf-8"))
    return list(paths.values())


def decimal_json(value: Any) -> str:
    """JSON in which ``Decimal`` values are written as exact number literals."""
    marker = "\u0000dec:"

    def prepare(item: Any) -> Any:
        if isinstance(item, Decimal):
            return f"{marker}{item}"
        if isinstance(item, dict):
            return {key: prepare(inner) for key, inner in item.items()}
        if isinstance(item, list):
            return [prepare(inner) for inner in item]
        return item

    text = json.dumps(prepare(value), indent=2, sort_keys=True, ensure_ascii=False)
    return re.sub(r'"\\u0000dec:(-?[0-9.]+)"', r"\1", text) + "\n"


# ----------------------------------------------------------------------------- study inputs


def load_rubrics(path: Path) -> dict[str, Any]:
    data = read_json(path)
    require(isinstance(data, dict) and data.get("version") == 1, "Unsupported rubrics file")
    leaves = {}
    for leaf in data["scored_leaves"]:
        if leaf["numeric"]:
            continue
        labels = list(leaf["labels"])
        require(
            2 <= len(labels) <= 8 and len(set(labels)) == len(labels), f"Bad labels: {leaf['id']}"
        )
        require(
            CANNOT_TELL not in [x.casefold() for x in labels], "A label may not be 'cannot tell'"
        )
        leaves[str(leaf["id"])] = {
            "id": str(leaf["id"]),
            "name": str(leaf["name"]),
            "rubric": str(leaf["rubric"]),
            "labels": labels,
        }
    require(bool(leaves), "No rateable rubric leaves")
    return {"study": str(data["study"]), "leaves": leaves}


def load_companies(project_path: Path) -> list[tuple[str, str]]:
    """Alternative IDs and names only: the classifier never sees ratings, classes or ranks."""
    project = read_json(project_path)
    require(
        isinstance(project, dict) and isinstance(project.get("alternatives"), list), "Bad project"
    )
    return [(str(a["id"]), str(a["name"])) for a in project["alternatives"]]


def project_fingerprint(project_path: Path) -> str:
    """The application's own definition: SHA-256 of the canonical project JSON."""
    project = read_json(project_path)
    text = json.dumps(project, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha(text.encode("utf-8"))


def source_identity(
    evidence_path: Path, leaf_ids: set[str]
) -> dict[str, dict[str, dict[str, str]]]:
    """Per company, the cited pages of its rubric cells: name, URL and date. Nothing else."""
    evidence = read_json(evidence_path)
    require(isinstance(evidence, dict) and isinstance(evidence.get("claims"), list), "Bad evidence")
    out: dict[str, dict[str, dict[str, str]]] = {}
    for claim in evidence["claims"]:
        if claim.get("criterion_id") not in leaf_ids:
            continue
        source = claim.get("source") or {}
        url = source.get("reference")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            out.setdefault(str(claim["alternative_id"]), {}).setdefault(
                url,
                {
                    "name": str(source.get("name", "")),
                    "url": url,
                    "date": str(source.get("date", "")),
                },
            )
    return out


def all_references(evidence_path: Path) -> list[str]:
    evidence = read_json(evidence_path)
    require(isinstance(evidence, dict) and isinstance(evidence.get("claims"), list), "Bad evidence")
    urls = {(claim.get("source") or {}).get("reference") for claim in evidence["claims"]}
    return sorted(u for u in urls if isinstance(u, str) and u.startswith(("http://", "https://")))


# ----------------------------------------------------------------------------- snapshot


class _TextExtractor(HTMLParser):
    """Visible text: script, style, navigation and head content dropped; the title is kept."""

    SKIP = {"script", "style", "noscript", "template", "nav", "svg", "iframe", "head", "footer"}
    BLOCK = {
        "p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table",
        "section", "article", "blockquote", "pre", "dt", "dd", "figcaption", "main", "aside",
    }  # fmt: skip

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title: list[str] = []
        self._skip: tuple[str, int] | None = None
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        role = dict(attrs).get("role")
        if tag == "title" and (self._skip is None or self._skip[0] == "head"):
            self._in_title = True  # the title lives in the head, which is otherwise dropped
            return
        if self._skip is not None:
            if tag == self._skip[0]:
                self._skip = (tag, self._skip[1] + 1)
            return
        if tag in self.SKIP or role == "navigation":
            self._skip = (tag, 1)
            return
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._in_title:
            self._in_title = False
            return
        if self._skip is not None:
            if tag == self._skip[0]:
                depth = self._skip[1] - 1
                self._skip = (tag, depth) if depth else None
            return
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title.append(data)
        elif self._skip is None:
            self.parts.append(data)


def extract_text(markup: str) -> str:
    parser = _TextExtractor()
    parser.feed(markup)
    parser.close()
    body = "".join(parser.parts)
    lines = [re.sub(r"[ \t\r\f\v ]+", " ", line).strip() for line in body.split("\n")]
    text = "\n".join(line for line in lines if line)
    title = re.sub(r"\s+", " ", "".join(parser.title)).strip()
    return (title + "\n" + text).strip() if title else text


def decode_page(raw: bytes, content_type: str) -> str:
    match = re.search(r"charset=([\w\-]+)", content_type, re.I)
    if not match:
        meta = re.search(rb"<meta[^>]+charset=[\"']?([\w\-]+)", raw[:4096], re.I)
        charset = meta.group(1).decode("ascii") if meta else "utf-8"
    else:
        charset = match.group(1)
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


class Fetcher:
    """Polite fetching: one request at a time, a minimum interval, a timeout, robots.txt."""

    def __init__(self, interval: float | None = None) -> None:
        self.interval = MIN_INTERVAL if interval is None else interval
        self._last = 0.0
        self._robots: dict[str, urllib.robotparser.RobotFileParser | bool] = {}

    def _wait(self) -> None:
        pause = self.interval - (time.monotonic() - self._last)
        if pause > 0:
            time.sleep(pause)
        self._last = time.monotonic()

    def get(self, url: str) -> tuple[int | None, str, bytes, str, str]:
        """(status, final url, body, content type, error). A status is None on a transport error."""
        self._wait()
        request = urllib.request.Request(
            url, headers={"User-Agent": CLIENT, "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1"}
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
                body = response.read(MAX_PAGE_BYTES + 1)
                return (
                    response.status,
                    response.geturl(),
                    body[:MAX_PAGE_BYTES],
                    response.headers.get("Content-Type", ""),
                    "page larger than 8 MB, cut" if len(body) > MAX_PAGE_BYTES else "",
                )
        except urllib.error.HTTPError as exc:
            return (
                exc.code,
                url,
                b"",
                exc.headers.get("Content-Type", "") if exc.headers else "",
                "",
            )
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            return None, url, b"", "", f"{type(exc).__name__}: {exc}"

    def allowed(self, url: str) -> tuple[bool, str]:
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self._robots:
            policy = self._robots[origin]
            note = "robots.txt cached"
        else:
            status, _, body, _, error = self.get(origin + "/robots.txt")
            policy = False  # unreachable or a server error: do not assume permission
            if status == 200:
                policy = urllib.robotparser.RobotFileParser()
                policy.parse(body.decode("utf-8", errors="replace").splitlines())
            elif status is not None and 400 <= status < 500 and status not in (401, 403):
                policy = True  # no robots.txt: everything is allowed
            self._robots[origin] = policy
            note = f"robots.txt status {status}" + (f" ({error})" if error else "")
        if isinstance(policy, bool):
            return policy, note
        return policy.can_fetch(CLIENT, url), note


def command_snapshot(args: argparse.Namespace) -> int:
    out = outside_repo(Path(args.out), "Snapshot directory")
    urls = all_references(Path(args.evidence))
    require(bool(urls), "The evidence cites no http(s) page")
    out.mkdir(parents=True, exist_ok=True)
    index_path = out / "snapshots.json"
    kept: dict[str, dict[str, Any]] = {}
    if index_path.exists():
        previous = read_json(index_path)
        kept = {row["url"]: row for row in previous.get("snapshots", [])}
    fetcher = Fetcher()
    saved = skipped = 0
    for url in urls:
        if url in kept and not args.refresh:
            continue
        name = sha(url.encode())[:16]
        row: dict[str, Any] = {
            "url": url,
            "final_url": url,
            "status": None,
            "retrieved_at": now(),
            "content_type": "",
            "bytes": 0,
            "raw_sha256": None,
            "text_sha256": None,
            "raw_file": None,
            "text_file": None,
            "outcome": "error",
            "detail": "",
        }
        permitted, note = fetcher.allowed(url)
        if not permitted:
            row.update(outcome="blocked_by_robots", detail=note)
        else:
            status, final, body, content_type, error = fetcher.get(url)
            row.update(status=status, final_url=final, content_type=content_type, detail=error)
            if status in (401, 403):
                row["outcome"] = "skipped_login_or_paywall"
            elif status is None or status >= 400:
                row["outcome"] = "error"
            else:
                row["bytes"] = len(body)
                row["raw_sha256"] = sha(body)
                kind = content_type.split(";")[0].strip().lower()
                (out / "raw").mkdir(exist_ok=True)
                (out / "raw" / f"{name}.bin").write_bytes(body)
                row["raw_file"] = f"raw/{name}.bin"
                if kind in ("text/html", "application/xhtml+xml", "") or kind.startswith("text/"):
                    markup = decode_page(body, content_type)
                    text = extract_text(markup) if "html" in kind or not kind else markup.strip()
                    (out / "text").mkdir(exist_ok=True)
                    encoded = text.encode("utf-8")
                    (out / "text" / f"{name}.txt").write_bytes(encoded)
                    row.update(
                        text_file=f"text/{name}.txt", text_sha256=sha(encoded), outcome="saved"
                    )
                    saved += 1
                else:
                    row["outcome"] = "unsupported_content_type"
        if row["outcome"] != "saved":
            skipped += 1
        kept[url] = row
        document = {
            "version": 1,
            "client": CLIENT,
            "licence": SNAPSHOT_LICENCE,
            "note": (
                f"The study's as-of date is {STUDY_AS_OF[8:].lstrip('0')} November 2026 and these "
                "copies were retrieved later; a page may have changed."
            ),
            "snapshots": [kept[u] for u in sorted(kept)],
        }
        tmp = out / "snapshots.json.tmp"
        tmp.write_text(pretty(document), encoding="utf-8")
        tmp.replace(index_path)
    print(f"{saved} pages saved, {skipped} not saved, {len(kept)} recorded in {index_path}")
    return 0


def host_of(row: dict[str, Any]) -> str:
    return (urllib.parse.urlsplit(row.get("final_url") or row["url"]).hostname or "").lower()


def filter_lines(pages: dict[str, str], hosts: dict[str, str]) -> dict[str, str]:
    """Extractor version 2, applied to version-1 text (``url`` -> text), in order, per page:

    1. keep only the first occurrence of each exact repeated line within the page;
    2. drop a line of ``SHORT_LINE_WORDS`` words or fewer that also appears, exactly, in at
       least one other saved page from the same host (compared on the other page's version-1
       lines, so the result does not depend on the order pages are processed in);
    3. keep everything else, in order.
    """
    lines = {url: text.split("\n") for url, text in pages.items()}
    by_host: dict[str, dict[str, set[str]]] = {}
    for url, page_lines in lines.items():
        for line in set(page_lines):
            by_host.setdefault(hosts[url], {}).setdefault(line, set()).add(url)
    result = {}
    for url, page_lines in lines.items():
        seen: set[str] = set()
        kept = []
        for line in page_lines:
            if line in seen:
                continue
            seen.add(line)
            elsewhere = by_host[hosts[url]][line] - {url}
            if len(line.split()) <= SHORT_LINE_WORDS and elsewhere:
                continue
            kept.append(line)
        result[url] = "\n".join(kept)
    return result


def rebuild_text(row: dict[str, Any], raw: bytes) -> str:
    """The version-1 text of a saved page, rebuilt from its raw bytes as the snapshot did."""
    content_type = row.get("content_type", "")
    kind = content_type.split(";")[0].strip().lower()
    markup = decode_page(raw, content_type)
    return extract_text(markup) if "html" in kind or not kind else markup.strip()


def command_reextract(args: argparse.Namespace) -> int:
    directory = outside_repo(Path(args.snapshots), "Snapshot directory")
    index_path = directory / "snapshots.json"
    document = read_json(index_path)
    rows = document["snapshots"]
    texts: dict[str, str] = {}
    hosts: dict[str, str] = {}
    for row in rows:
        if row.get("outcome") != "saved" or not row.get("raw_file"):
            continue
        raw = read_bytes(directory / row["raw_file"])
        require(sha(raw) == row["raw_sha256"], f"A saved page changed on disk: {row['url']}")
        texts[row["url"]] = rebuild_text(row, raw)
        hosts[row["url"]] = host_of(row)
    filtered = filter_lines(texts, hosts)
    files: dict[str, str | bytes] = {}
    out_rows = []
    for row in rows:
        new = dict(row)
        url = row["url"]
        if url in filtered:
            text = filtered[url]
            encoded = text.encode("utf-8")
            name = Path(row["text_file"]).name if row.get("text_file") else sha(url.encode())[:16]
            name = name if name.endswith(".txt") else f"{name}.txt"
            files[f"text.v2/{name}"] = encoded
            new.update(
                text_file=f"text.v2/{name}",
                text_sha256=sha(encoded),
                extractor_version=EXTRACTOR_VERSION,
                chars_before=len(texts[url]),
                chars_after=len(text),
                v1_text_sha256=row.get("text_sha256"),
                v1_text_rebuilt_identically=sha(texts[url].encode("utf-8"))
                == row.get("text_sha256"),
            )
        out_rows.append(new)
    index_bytes = read_bytes(index_path)
    files["snapshots.v2.json"] = pretty(
        {
            "version": 2,
            "extractor_version": EXTRACTOR_VERSION,
            "client": document.get("client", CLIENT),
            "licence": document.get("licence", SNAPSHOT_LICENCE),
            "note": document.get("note", ""),
            "rules": [
                "Keep only the first occurrence of each exact repeated line within a page.",
                f"Drop lines of {SHORT_LINE_WORDS} words or fewer that also appear in at least "
                "one other saved page from the same host.",
                "Keep everything else, in order.",
            ],
            "source_index": "snapshots.json",
            "source_index_sha256": sha(index_bytes),
            "snapshots": out_rows,
        }
    )
    for path in write_new(directory, files):
        print(f"wrote {path}")
    before = sum(len(t) for t in texts.values())
    after = sum(len(t) for t in filtered.values())
    print(f"{len(texts)} pages re-extracted: {before} characters before, {after} after")
    return 0


# ----------------------------------------------------------------------------- questions


def read_replacements(path: Path, header: bool) -> list[tuple[str, str]]:
    rows = list(csv.reader(io.StringIO(read_bytes(path).decode("utf-8-sig"), newline="")))
    if header:
        require(
            rows and rows[0] == ["original", "replacement"],
            "swap.csv needs the header original,replacement",
        )
        rows = rows[1:]
    pairs = []
    for row in rows:
        if not row or not any(cell.strip() for cell in row):
            continue
        require(
            len(row) == 2 and row[0].strip(), "Each replacement is two columns, the first not empty"
        )
        pairs.append((row[0].strip(), row[1].strip()))
    require(len({a for a, _ in pairs}) == len(pairs), "A name is listed twice")
    return pairs


def apply_swap(text: str, pairs: list[tuple[str, str]]) -> str:
    """Exact, case-sensitive replacement, longest first, in one pass so replacements never chain."""
    if not pairs:
        return text
    ordered = sorted(pairs, key=lambda p: (-len(p[0]), p[0]))
    mapping = dict(ordered)
    pattern = re.compile("|".join(re.escape(a) for a, _ in ordered))
    return pattern.sub(lambda m: mapping[m.group(0)], text)


def apply_redaction(text: str, names: list[str]) -> str:
    """Listed names (any case) become neutral tokens, longest first, in one pass."""
    if not names:
        return text
    tokens = {n.casefold(): f"[NAME-{i}]" for i, n in enumerate(names, start=1)}
    ordered = sorted(names, key=lambda n: (-len(n), n))
    pattern = re.compile("|".join(re.escape(n) for n in ordered), re.I)
    return pattern.sub(lambda m: tokens[m.group(0).casefold()], text)


def truncate_at_boundary(text: str, cap: int) -> str:
    if len(text) <= cap:
        return text
    cut = text[:cap]
    boundary = max(cut.rfind("\n"), cut.rfind(". "), cut.rfind(" "))
    return cut[: boundary if boundary > cap // 2 else cap].rstrip()


def build_questions(
    companies: list[tuple[str, str]],
    rubrics: dict[str, Any],
    identity: dict[str, dict[str, dict[str, str]]],
    snapshot_dir: Path,
    snapshot_index: dict[str, dict[str, Any]],
    backend: str,
    budget: int,
    redact: list[str],
    swap: list[tuple[str, str]],
) -> dict[str, Any]:
    states: dict[str, Any] = {}
    truncations = []
    for alt, name in companies:
        cited = sorted(identity.get(alt, {}).values(), key=lambda s: s["url"])
        readable = []
        for source in cited:
            row = snapshot_index.get(source["url"])
            text_file = row.get("text_file") if row and row.get("outcome") == "saved" else None
            readable.append((source, row, text_file))
        usable = [r for r in readable if r[2]]
        cap = budget // max(1, len(usable))
        blocks, records = [], []
        for source, row, text_file in readable:
            record = {
                "name": source["name"],
                "url": source["url"],
                "date": source["date"],
                "available": bool(text_file),
                "text_sha256": row.get("text_sha256") if row else None,
                "chars_total": 0,
                "chars_used": 0,
                "truncated": False,
            }
            if text_file and row:
                text = (snapshot_dir / text_file).read_text(encoding="utf-8")
                require(
                    sha(text.encode("utf-8")) == row["text_sha256"], "A snapshot changed on disk"
                )
                text = apply_redaction(apply_swap(text, swap), redact)
                used = truncate_at_boundary(text, cap)
                record.update(
                    chars_total=len(text), chars_used=len(used), truncated=len(used) < len(text)
                )
                if record["truncated"]:
                    truncations.append(
                        {
                            "alternative_id": alt,
                            "url": source["url"],
                            "chars_total": len(text),
                            "chars_used": len(used),
                        }
                    )
                header = f"Source: {source['name']} ({source['url']}, published {source['date']})"
                blocks.append(f"{header}\n{used}")
            records.append(record)
        state_text = "\n\n".join(blocks)
        display = apply_redaction(apply_swap(name, swap), redact)
        states[alt] = {
            "name": display,
            "sources": records,
            "state_text": state_text,
            "state_digest": sha(state_text.encode("utf-8")),
        }
    questions = []
    for alt, _name in companies:
        for leaf_id, leaf in rubrics["leaves"].items():
            body = {
                "question_id": f"{alt}__{leaf_id}",
                "alternative_id": alt,
                "criterion_id": leaf_id,
                "criterion_name": leaf["name"],
                "rubric": leaf["rubric"],
                "labels": leaf["labels"],
                "options": [*leaf["labels"], CANNOT_TELL],
                "instruction": INSTRUCTION,
                "state_digest": states[alt]["state_digest"],
                "template_version": TEMPLATE_VERSION,
            }
            body["digest"] = digest(body)
            questions.append(body)
    return {"states": states, "questions": questions, "truncations": truncations}


def command_questions(args: argparse.Namespace) -> int:
    rubrics = load_rubrics(Path(args.rubrics))
    companies = load_companies(Path(args.project))
    identity = source_identity(Path(args.evidence), set(rubrics["leaves"]))
    index_name = "snapshots.json" if args.extractor == 1 else "snapshots.v2.json"
    snap_path = Path(args.snapshots) / index_name
    index = {row["url"]: row for row in read_json(snap_path)["snapshots"]}
    backend = args.backend
    budget = args.budget_chars or DEFAULT_BUDGETS[backend]
    redact = (
        [
            line.strip()
            for line in read_bytes(Path(args.redact)).decode("utf-8").splitlines()
            if line.strip()
        ]
        if args.redact
        else []
    )
    swap = read_replacements(Path(args.swap), header=True) if args.swap else []
    built = build_questions(
        companies, rubrics, identity, Path(args.snapshots), index, backend, budget, redact, swap
    )
    document = {
        "version": 1,
        "kind": "typed-proposal-questions",
        "study": rubrics["study"],
        "template_version": TEMPLATE_VERSION,
        "backend": backend,
        "budget_chars": budget,
        "inputs": {
            "rubrics_sha256": sha(read_bytes(Path(args.rubrics))),
            "evidence_sha256": sha(read_bytes(Path(args.evidence))),
            "snapshots_sha256": sha(read_bytes(snap_path)),
            **({"snapshot_index": index_name} if args.extractor != 1 else {}),
        },
        "redaction": {"names": len(redact)},
        "swap": {"pairs": len(swap), "sha256": digest(swap)} if swap else None,
        **built,
    }
    document["digest"] = digest({k: v for k, v in document.items() if k != "digest"})
    for path in write_new(Path(args.out).parent, {Path(args.out).name: pretty(document)}):
        print(f"wrote {path}")
    cut = len(built["truncations"])
    print(
        f"{len(built['questions'])} questions, {cut} truncated sources; digest {document['digest']}"
    )
    return 0


# ----------------------------------------------------------------------------- probabilities


def quantize(weights: dict[str, float], order: list[str]) -> dict[str, Decimal]:
    """Exact decimals, ``PLACES`` places, summing to exactly one.

    Each weight's share is floored to the grid; the units left over go one each to the largest
    fractional remainders, ties to the earlier option. The result depends only on the weights.
    """
    exact = {o: Fraction(weights[o]) for o in order}
    require(all(w >= 0 for w in exact.values()), "A score is negative")
    total = sum(exact.values())
    require(total > 0, "All scores are zero")
    scale = 10**PLACES
    shares = {o: exact[o] / total * scale for o in order}
    units = {o: math.floor(shares[o]) for o in order}
    left = scale - sum(units.values())
    ranked = sorted(order, key=lambda o: (-(shares[o] - units[o]), order.index(o)))
    for o in ranked[:left]:
        units[o] += 1
    result = {o: Decimal(units[o]).scaleb(-PLACES) for o in order}
    assert sum(result.values()) == 1
    return result


def top_option(probabilities: dict[str, Decimal], order: list[str]) -> tuple[str | None, bool]:
    """(option, tied). An exact tie at the top has no winner."""
    best = max(probabilities.values())
    winners = [o for o in order if probabilities[o] == best]
    return (winners[0], False) if len(winners) == 1 else (None, True)


# ----------------------------------------------------------------------------- option orders


def rotated(options: list[str], shift: int) -> list[str]:
    """The display order after ``shift`` cyclic steps: the option at index ``shift`` comes first."""
    return options[shift:] + options[:shift]


def letter_softmax(log_probabilities: list[float]) -> list[float]:
    """Probabilities over the letters from their log-probabilities (the peak is subtracted)."""
    peak = max(log_probabilities)
    weights = [math.exp(c - peak) for c in log_probabilities]
    total = sum(weights)
    return [w / total for w in weights]


def first_max(options: list[str], values: dict[str, float]) -> str:
    return max(options, key=lambda o: (values[o], -options.index(o)))


def average_over_orders(
    options: list[str], letter_log_probabilities: Any
) -> tuple[dict[str, float], dict[str, Any]]:
    """Score ``options`` under every cyclic order and average the options' probabilities.

    ``letter_log_probabilities(order)`` returns the log-probability of each letter A, B, C... when
    the options are displayed in ``order``. Letters stay in display order; only which option sits
    under which letter changes. Each rotation's letter probabilities are mapped back to options, and
    the options' arithmetic means over all rotations are the scores. The record keeps every
    rotation's raw letter log-probabilities and the option under each letter, plus two diagnostics:
    ``order_top_agreement`` (the share of rotations whose top option is the averaged top option)
    and ``order_max_shift`` (the largest change in any option's probability across rotations).
    """
    n = len(options)
    rotations = []
    for shift in range(n):
        order = rotated(options, shift)
        chosen = [float(c) for c in letter_log_probabilities(order)]
        require(len(chosen) == n, "A rotation scored the wrong number of letters")
        letters = [chr(ord("A") + i) for i in range(n)]
        probabilities = dict(zip(order, letter_softmax(chosen), strict=True))
        rotations.append(
            {
                "shift": shift,
                "options_by_letter": dict(zip(letters, order, strict=True)),
                "log_probabilities": dict(zip(letters, chosen, strict=True)),
                "probabilities": probabilities,
            }
        )
    scores = {o: math.fsum(r["probabilities"][o] for r in rotations) / n for o in options}
    top = first_max(options, scores)
    agreement = sum(1 for r in rotations if first_max(options, r["probabilities"]) == top) / n
    spread = max(
        max(r["probabilities"][o] for r in rotations)
        - min(r["probabilities"][o] for r in rotations)
        for o in options
    )
    return scores, {
        "order_averaging": "rotations",
        "orders": rotations,
        "order_top_agreement": agreement,
        "order_max_shift": spread,
    }


def normalised(options: list[str], values: dict[str, float]) -> dict[str, float]:
    """One probability vector over ``options``: finite, non-negative, scaled to sum to one."""
    require(set(values) == set(options), "A backend answered other options than those asked")
    for value in values.values():
        require(math.isfinite(value) and value >= 0, "A probability is not finite and non-negative")
    total = math.fsum(values.values())
    require(total > 0, "All probabilities are zero")
    return {o: values[o] / total for o in options}


def average_keyed_orders(
    options: list[str], probabilities_for: Any
) -> tuple[dict[str, float], dict[str, Any]]:
    """Score ``options`` under every cyclic order when a backend reports a probability per option.

    ``probabilities_for(order)`` shows the options in ``order`` and returns each option's
    probability keyed by option, already mapped back from its display position by the backend.
    Each rotation's vector is normalised and the options' arithmetic means over all rotations are
    the scores, with the same two diagnostics as ``average_over_orders``.
    """
    n = len(options)
    rotations = []
    for shift in range(n):
        order = rotated(options, shift)
        probabilities = normalised(options, probabilities_for(order))
        rotations.append({"shift": shift, "display_order": order, "probabilities": probabilities})
    means = {o: math.fsum(r["probabilities"][o] for r in rotations) / n for o in options}
    winner = first_max(options, means)
    agreeing = sum(1 for r in rotations if first_max(options, r["probabilities"]) == winner)
    spread = max(
        max(r["probabilities"][o] for r in rotations)
        - min(r["probabilities"][o] for r in rotations)
        for o in options
    )
    return means, {
        "order_averaging": "rotations",
        "orders": rotations,
        "order_top_agreement": agreeing / n,
        "order_max_shift": spread,
    }


def mean_over_chunks(options: list[str], vectors: list[dict[str, float]]) -> dict[str, float]:
    """The arithmetic mean of the chunks' probability vectors (the accepted aggregation rule)."""
    require(len(vectors) > 0, "No chunk was scored")
    return {o: math.fsum(v[o] for v in vectors) / len(vectors) for o in options}


def most_confident_chunk(chunk_means: list[dict[str, float]]) -> int:
    """The chunk whose largest probability is highest; a tie goes to the earlier chunk."""
    require(len(chunk_means) > 0, "No chunk was scored")
    return max(range(len(chunk_means)), key=lambda c: (max(chunk_means[c].values()), -c))


# ----------------------------------------------------------------------------- prompt


def choose_device(torch: Any) -> tuple[str, Any]:
    """Where a local model runs, and in which number type: an NVIDIA GPU (CUDA), then Apple's GPU
    (MPS), both in float16, then the CPU in float32. The manifest records both."""
    if torch.cuda.is_available():
        return "cuda", torch.float16
    if torch.backends.mps.is_available():
        return "mps", torch.float16
    return "cpu", torch.float32


def build_prompt(question: dict[str, Any], state: dict[str, Any]) -> tuple[str, str, list[str]]:
    """(system, user, option letters). Only rubric text, labels, names and source text enter."""
    letters = [chr(ord("A") + i) for i in range(len(question["options"]))]
    options = "\n".join(
        f"{letter}. {option}" for letter, option in zip(letters, question["options"], strict=True)
    )
    system = "You label evidence. Use only the text you are given. Reply with one option letter."
    user = (
        f"Text about {state['name']}:\n<<<\n{state['state_text']}\n>>>\n\n"
        f"Criterion: {question['criterion_name']}\n"
        f"Rubric: {question['rubric']}\n\n"
        f"Options:\n{options}\n\n{question['instruction']}"
    )
    return system, user, letters


# ----------------------------------------------------------------------------- backends


class Backend:
    name = ""
    model_id = ""
    model_version = ""
    scoring_version = SCORING_BACKEND

    def parameters(self) -> dict[str, Any]:
        return {}

    def environment(self) -> dict[str, str]:
        return {}

    def score(
        self, question: dict[str, Any], state: dict[str, Any]
    ) -> tuple[dict[str, float], Any]:
        raise NotImplementedError


class ReplayBackend(Backend):
    """Recorded responses by question digest: for tests and offline re-scoring."""

    name = "replay"

    def __init__(self, path: Path) -> None:
        raw = read_bytes(path).decode("utf-8")
        self.responses: dict[str, dict[str, float]] = {}
        if path.suffix == ".jsonl":
            for line in raw.splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.responses[row["digest"]] = row["scores"]
        else:
            self.responses = json.loads(raw)["responses"]
        self.model_id = "replay"
        self.model_version = sha(raw.encode("utf-8"))[:16]
        self.source = path.name

    def parameters(self) -> dict[str, Any]:
        return {"responses_file": self.source, "responses": len(self.responses)}

    def score(
        self, question: dict[str, Any], state: dict[str, Any]
    ) -> tuple[dict[str, float], Any]:
        scores = self.responses.get(question["digest"])
        if scores is None:
            raise RunnerError(f"No recorded response for {question['question_id']}")
        require(
            set(scores) == set(question["options"]), "Recorded options differ from the question"
        )
        return {o: float(scores[o]) for o in question["options"]}, {"replayed": True}


class JevBackend(Backend):
    """TypeSafe's System One endpoint, as documented at docs.typesafe.ai/api/system-one.md.

    POST {model, state, questions: {id: {type: "choice", instructions, criteria}}} with a bearer
    key; the answer's ``probabilities`` map names every criterion. Nothing is sent unless
    ``--allow-network`` and TYPESAFE_API_KEY are both given.
    """

    name = "jev"

    def __init__(self, endpoint: str, model: str, key: str, order_averaging: str = "none") -> None:
        parts = urllib.parse.urlsplit(endpoint)
        local = parts.hostname in {"127.0.0.1", "localhost", "::1"}
        require(
            parts.scheme == "https" or local and parts.scheme == "http", "Use an https endpoint"
        )
        require(order_averaging in ORDER_AVERAGING, "Unknown --order-averaging")
        self.endpoint, self.model_id, self._key = endpoint, model, key
        self.model_version = model
        self.order_averaging = order_averaging
        if order_averaging == "rotations":
            self.scoring_version = SCORING_KEYED_AVERAGED
        self.retries = 3
        self.delay = 2.0

    def parameters(self) -> dict[str, Any]:
        base = {"endpoint": self.endpoint, "model": self.model_id, "attempts": self.retries}
        if self.order_averaging == "rotations":
            return {**base, "order_averaging": "rotations", "scoring": SCORING_TEXT_KEYED_AVERAGED}
        return base  # the single-order run records exactly what it recorded before

    def request_body(self, question: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        position = {
            o: f"Option {i + 1} of {len(question['options'])}"
            for i, o in enumerate(question["options"])
        }
        return {
            "model": self.model_id,
            "state": f"Text about {state['name']}:\n{state['state_text']}",
            "questions": {
                "answer": {
                    "type": "choice",
                    "instructions": (
                        f"Criterion: {question['criterion_name']}. Rubric: {question['rubric']} "
                        f"{question['instruction']}"
                    ),
                    "criteria": position,
                }
            },
        }

    def score(
        self, question: dict[str, Any], state: dict[str, Any]
    ) -> tuple[dict[str, float], Any]:
        """One request in the question's own order, or one per cyclic order, averaged."""
        if self.order_averaging == "none":
            return self.score_order(question, state)
        responses = []

        def scored(order: list[str]) -> dict[str, float]:
            scores, raw = self.score_order({**question, "options": order}, state)
            responses.append(raw)
            return {option: scores[option] for option in question["options"]}

        scores, record = average_keyed_orders(question["options"], scored)
        record["responses"] = responses
        return scores, record

    def score_order(
        self, question: dict[str, Any], state: dict[str, Any]
    ) -> tuple[dict[str, float], Any]:
        """One request, the options shown in ``question["options"]`` order."""
        payload = json.dumps(self.request_body(question, state)).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
                "User-Agent": CLIENT,
            },
        )
        last = ""
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
                    body = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                last = f"HTTP {exc.code}"
                if exc.code not in (429, 500, 502, 503, 504):
                    raise RunnerError(f"The jev endpoint refused the request: {last}") from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = f"{type(exc).__name__}"
            time.sleep(self.delay * (attempt + 1))
        else:
            raise RunnerError(f"The jev endpoint failed after {self.retries} attempts: {last}")
        answer = (body.get("answers") or {}).get("answer")
        if not isinstance(answer, dict) or answer.get("type") != "choice":
            raise RunnerError("Unexpected jev answer")
        probabilities = answer.get("probabilities")
        if not isinstance(probabilities, dict) or set(probabilities) != set(question["options"]):
            raise RunnerError("The jev answer does not name exactly the options asked")
        scores = {}
        for option in question["options"]:
            value = probabilities[option]
            require(
                isinstance(value, int | float)
                and not isinstance(value, bool)
                and math.isfinite(value)
                and value >= 0,
                "A jev probability is not a finite non-negative number",
            )
            scores[option] = float(value)
        require(abs(sum(scores.values()) - 1) < 1e-3, "The jev probabilities do not sum to one")
        return scores, {
            "model": body.get("model"),
            "usage": body.get("usage"),
            "probabilities": probabilities,
        }


def scoring_for(order_averaging: str) -> tuple[str, str]:
    """(scoring version, plain-words description) recorded for a local-hf run."""
    require(order_averaging in ORDER_AVERAGING, "Unknown --order-averaging")
    if order_averaging == "rotations":
        return SCORING_AVERAGED, SCORING_TEXT_AVERAGED
    return SCORING_SINGLE, SCORING_TEXT_SINGLE


class LocalHfBackend(Backend):
    """Conditional log-likelihood of each option letter under a local instruction model.

    The prompt ends where the assistant's reply begins; the score of an option is the log
    probability of its one-token letter as the first reply token, and the options' probabilities
    are a softmax over those scores. No sampling. By default each question is scored under every
    cyclic order of its options and the options' probabilities are averaged, which removes a
    preference for a letter position from the average (it does not calibrate the probabilities);
    ``order_averaging="none"`` keeps the single display order, for comparison only.
    ``transformers`` and ``torch`` are imported here.
    """

    name = "local-hf"

    def __init__(self, model_path: Path, order_averaging: str = "rotations") -> None:
        require(model_path.is_dir(), f"No model at {model_path}; see the fetch-model subcommand")
        self.scoring_version, self.scoring_text = scoring_for(order_averaging)
        self.order_averaging = order_averaging
        try:
            import torch  # type: ignore[import-not-found,unused-ignore]
            import transformers  # type: ignore[import-not-found,unused-ignore]
        except ImportError as exc:  # pragma: no cover - needs the separate environment
            raise RunnerError(
                "local-hf needs torch and transformers; run it from the classifier virtualenv "
                "($MCDA_DATA/venv-classifier)"
            ) from exc
        self.torch = torch
        self.device, dtype = choose_device(torch)
        self.tokenizer = transformers.AutoTokenizer.from_pretrained(str(model_path))
        self.model = transformers.AutoModelForCausalLM.from_pretrained(
            str(model_path), torch_dtype=dtype
        )
        self.model.to(self.device)
        self.model.eval()
        revision_file = model_path / "mcda-model-revision.json"
        revision = read_json(revision_file) if revision_file.exists() else {}
        self.model_id = str(revision.get("repo_id", model_path.name))
        self.model_version = str(revision.get("revision", "unknown (no revision file)"))
        self.dtype = str(dtype)
        self.versions = {"torch": torch.__version__, "transformers": transformers.__version__}

    def parameters(self) -> dict[str, Any]:
        return {
            "device": self.device,
            "dtype": self.dtype,
            "sampling": "none",
            "order_averaging": self.order_averaging,
            "scoring": self.scoring_text,
        }

    def environment(self) -> dict[str, str]:
        return self.versions

    def letter_log_probabilities(
        self, question: dict[str, Any], state: dict[str, Any], order: list[str]
    ) -> tuple[list[float], int]:
        """Log-probability of each letter as the first reply token, options shown in ``order``."""
        system, user, letters = build_prompt({**question, "options": order}, state)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        ids = []
        for letter in letters:
            encoded = self.tokenizer.encode(letter, add_special_tokens=False)
            require(len(encoded) == 1, f"The option letter {letter!r} is not a single token")
            ids.append(encoded[0])
        batch = self.tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to(
            self.device
        )
        with self.torch.no_grad():
            logits = self.model(**batch).logits[0, -1].float()
        logprobs = self.torch.log_softmax(logits, dim=-1)
        return [float(logprobs[i]) for i in ids], int(batch["input_ids"].shape[1])

    def score(
        self, question: dict[str, Any], state: dict[str, Any]
    ) -> tuple[dict[str, float], Any]:
        options = question["options"]
        if self.order_averaging == "none":
            chosen, tokens = self.letter_log_probabilities(question, state, options)
            return single_order_scores(options, chosen, tokens)
        tokens = []

        def scored(order: list[str]) -> list[float]:
            chosen, count = self.letter_log_probabilities(question, state, order)
            tokens.append(count)
            return chosen

        scores, raw = average_over_orders(options, scored)
        raw["prompt_tokens"] = max(tokens)
        return scores, raw


def single_order_scores(
    options: list[str], chosen: list[float], prompt_tokens: int
) -> tuple[dict[str, float], dict[str, Any]]:
    """The version-1 scoring: one display order, a softmax over the letters' log-probabilities."""
    letters = [chr(ord("A") + i) for i in range(len(options))]
    peak = max(chosen)
    weights = [math.exp(c - peak) for c in chosen]
    total = sum(weights)
    scores = {o: w / total for o, w in zip(options, weights, strict=True)}
    return scores, {
        "letters": letters,
        "log_probabilities": dict(zip(letters, chosen, strict=True)),
        "prompt_tokens": prompt_tokens,
    }


class QuestionRefusedError(RunnerError):
    """One question this backend will not answer; the run records it and goes on."""


RULE_RANK = {"empty": 0, "paragraph": 1, "sentence": 2, "tokens": 3}


def split_by_tokens(text: str, budget: int, count: Any) -> list[str]:
    """Greedy word packing under ``budget`` tokens; a single word too long is cut by characters."""
    pieces: list[str] = []
    current = ""
    for word in text.split():
        joined = f"{current} {word}" if current else word
        if count(joined) <= budget:
            current = joined
            continue
        if current:
            pieces.append(current)
        current = word
        while count(current) > budget:
            cut = len(current) - 1
            while cut > 1 and count(current[:cut]) > budget:
                cut -= 1
            pieces.append(current[:cut])
            current = current[cut:]
    if current:
        pieces.append(current)
    return pieces


def chunk_text(text: str, budget: int, count: Any) -> list[dict[str, Any]]:
    """Split ``text`` into chunks of at most ``budget`` tokens, as counted by ``count``.

    Paragraphs (blank-line separated) are packed greedily: one joins the current chunk while the
    joined text still fits, and a chunk exactly at the budget fits. A paragraph alone over the
    budget is split on sentence boundaries, and a sentence alone over it by token count. Each
    chunk records its text, token count, SHA-256 and the finest rule that made it.
    """
    pieces: list[tuple[int, str, str]] = []  # (paragraph index, text, rule)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    for index, paragraph in enumerate(paragraphs):
        if count(paragraph) <= budget:
            pieces.append((index, paragraph, "paragraph"))
            continue
        for sentence in (s for s in re.split(r"(?<=[.!?])\s+", paragraph) if s.strip()):
            if count(sentence) <= budget:
                pieces.append((index, sentence, "sentence"))
            else:
                parts = split_by_tokens(sentence, budget, count)
                pieces.extend((index, part, "tokens") for part in parts)
    chunks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for index, piece, rule in pieces:
        if current is not None:
            glue = " " if index == current["paragraph"] else "\n\n"
            joined = current["text"] + glue + piece
            if count(joined) <= budget:
                current.update(text=joined, paragraph=index)
                current["rule"] = max(current["rule"], rule, key=RULE_RANK.__getitem__)
                continue
            chunks.append(current)
        current = {"text": piece, "paragraph": index, "rule": rule}
    if current is not None:
        chunks.append(current)
    if not chunks:
        chunks = [{"text": "", "paragraph": 0, "rule": "empty"}]
    return [
        {
            "text": c["text"],
            "tokens": count(c["text"]),
            "sha256": sha(c["text"].encode("utf-8")),
            "rule": c["rule"],
        }
        for c in chunks
    ]


class LayaBackend(Backend):
    """Laya's typed `choice` decision, read from the installed `laya` package (0.4.32).

    The checkpoint is loaded from a local directory only, with the Hub offline. Its window
    (``max_len``) and question budget (``head_max_len``) come from the checkpoint. A question whose
    rubric or options the package would cut is refused, not answered. The state text is split into
    paragraph chunks that each fit beside the question, every chunk is scored under every cyclic
    option order (or the question's own order only, for comparison), and the probability vectors
    are averaged: over chunks (arithmetic mean), then over orders. ``laya.Agent(vegaml=...)`` and
    ``laya.Router`` are never used.
    """

    name = "laya"

    def __init__(self, model_path: Path, order_averaging: str = "rotations") -> None:
        require(model_path.is_dir(), f"No model at {model_path}; see the fetch-model subcommand")
        require(order_averaging in ORDER_AVERAGING, "Unknown --order-averaging")
        self.order_averaging = order_averaging
        self.scoring_version = (
            SCORING_LAYA_AVERAGED if order_averaging == "rotations" else SCORING_LAYA_SINGLE
        )
        os.environ["HF_HUB_OFFLINE"] = "1"  # nothing is downloaded during a run
        try:
            import laya  # type: ignore[import-not-found,unused-ignore]
            from laya import common  # type: ignore[import-not-found,unused-ignore]
        except ImportError as exc:
            raise RunnerError(
                "The laya backend needs the laya package: install laya==0.4.32 into the "
                "classifier virtualenv ($MCDA_DATA/venv-classifier) and run from there"
            ) from exc
        self.common = common
        revision_file = model_path / "mcda-model-revision.json"
        revision = read_json(revision_file) if revision_file.exists() else {}
        self.model_id = str(revision.get("repo_id", model_path.name))
        self.model_version = str(revision.get("revision", "unknown (no revision file)"))
        self.route = str(revision.get("route", "unknown (no revision file)"))
        self.agent = laya.load(str(model_path.resolve()))
        config = self.agent.cfg
        require("max_len" in config, "The checkpoint does not state its window (max_len)")
        self.max_len = int(config["max_len"])
        self.head_max_len = int(config.get("head_max_len", 192))  # the package's own default
        self.device = str(getattr(self.agent, "device", "unknown"))
        try:
            self.dtype = str(next(self.agent.model.parameters()).dtype)
        except (AttributeError, StopIteration, TypeError):
            self.dtype = "unknown"
        self.versions = {"laya": str(getattr(laya, "__version__", "unknown"))}
        for package in ("torch", "transformers"):
            try:
                from importlib.metadata import version

                self.versions[package] = version(package)
            except Exception:  # noqa: BLE001 - recorded, never fatal
                self.versions[package] = "not installed"

    def parameters(self) -> dict[str, Any]:
        averaged = self.order_averaging == "rotations"
        return {
            "device": self.device,
            "dtype": self.dtype,
            "sampling": "none",
            "order_averaging": self.order_averaging,
            "window_tokens": self.max_len,
            "head_max_tokens": self.head_max_len,
            "margin_tokens": LAYA_MARGIN,
            "min_state_tokens": LAYA_MIN_BUDGET,
            "checkpoint_route": self.route,
            "aggregation": "arithmetic mean over chunks, then over option orders",
            "second_reading": READING_MAX_CONFIDENCE_CHUNK,
            "scoring": SCORING_TEXT_LAYA
            + ("; averaged over n cyclic option orders" if averaged else "; single option order"),
            "note": LAYA_NOTES.get(self.model_id, "not one of the two named Laya checkpoints"),
        }

    def environment(self) -> dict[str, str]:
        return self.versions

    def count(self, text: str) -> int:
        return len(self.agent.tok(text, add_special_tokens=False)["input_ids"])

    def instructions(self, question: dict[str, Any]) -> str:
        return (
            f"Criterion: {question['criterion_name']}. Rubric: {question['rubric']} "
            f"{question['instruction']}"
        )

    def criteria(self, order: list[str]) -> list[str]:
        """The options as Laya choice criteria, in display order; "cannot tell" is already one."""
        return list(order)

    def plan(self, question: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        """The state budget and chunks for one question; refused if the package would cut it."""
        internal = {
            "t": "choice",
            "ins": self.instructions(question),
            "crit": {o: None for o in self.criteria(question["options"])},
        }
        capped, _, _ = self.common.build_head(self.agent.tok, internal, self.head_max_len)
        whole, _, _ = self.common.build_head(self.agent.tok, internal, 1_000_000)
        if capped != whole:
            raise QuestionRefusedError(
                f"the rubric and options take {len(whole)} tokens; the checkpoint allows "
                f"{self.head_max_len}, so the package would cut them"
            )
        for option in question["options"]:
            if self.count(" " + option) > LAYA_OPTION_TOKENS:
                raise QuestionRefusedError(f"an option is longer than {LAYA_OPTION_TOKENS} tokens")
        room = self.common.state_room(self.agent.tok, internal, self.max_len, self.head_max_len)
        budget = room - LAYA_MARGIN
        if budget < LAYA_MIN_BUDGET:
            raise QuestionRefusedError(f"only {budget} state tokens fit beside the question")
        prefix = f"Text about {state['name']}:\n"
        chunks = chunk_text(state["state_text"], budget, lambda text: self.count(prefix + text))
        return {"head_tokens": len(capped), "budget": budget, "prefix": prefix, "chunks": chunks}

    def predict(self, text: str, question: dict[str, Any], order: list[str]) -> dict[str, float]:
        """Laya's probabilities with the options shown in ``order``, mapped back by option."""
        asked = {
            "answer": {
                "type": "choice",
                "instructions": self.instructions(question),
                "criteria": self.criteria(order),
            }
        }
        answer = (self.agent.predict(text, asked).get("answers") or {}).get("answer")
        if not isinstance(answer, dict) or answer.get("type") != "choice":
            raise RunnerError("Unexpected laya answer")
        probabilities = answer.get("probabilities")
        if not isinstance(probabilities, dict) or set(probabilities) != set(order):
            raise RunnerError("The laya answer does not name exactly the options asked")
        for value in probabilities.values():
            require(
                isinstance(value, int | float) and not isinstance(value, bool),
                "A laya probability is not a number",
            )
        return {o: float(probabilities[o]) for o in question["options"]}

    def score(
        self, question: dict[str, Any], state: dict[str, Any]
    ) -> tuple[dict[str, float], Any]:
        options = question["options"]
        plan = self.plan(question, state)
        texts = [plan["prefix"] + chunk["text"] for chunk in plan["chunks"]]
        per_order: list[list[dict[str, float]]] = []

        def scored(order: list[str]) -> dict[str, float]:
            vectors = [normalised(options, self.predict(t, question, order)) for t in texts]
            per_order.append(vectors)
            return mean_over_chunks(options, vectors)

        if self.order_averaging == "rotations":
            scores, record = average_keyed_orders(options, scored)
        else:
            scores, record = scored(options), {"order_averaging": "none"}
        chunk_means = [
            {o: math.fsum(vectors[c][o] for vectors in per_order) / len(per_order) for o in options}
            for c in range(len(texts))
        ]
        top = first_max(options, scores)
        decisive = most_confident_chunk(chunk_means)
        record.update(
            {
                "window_tokens": self.max_len,
                "head_tokens": plan["head_tokens"],
                "state_budget_tokens": plan["budget"],
                "chunk_count": len(texts),
                "chunks": [{k: c[k] for k in ("sha256", "tokens", "rule")} for c in plan["chunks"]],
                "chunk_vectors": per_order,
                "chunk_top_agreement": sum(
                    1 for vector in chunk_means if first_max(options, vector) == top
                )
                / len(texts),
                "max_confidence_chunk_top": first_max(options, chunk_means[decisive]),
                MAX_CONFIDENCE_CHUNK: {"chunk": decisive, "probabilities": chunk_means[decisive]},
            }
        )
        return scores, record


# ----------------------------------------------------------------------------- run


def command_run(args: argparse.Namespace) -> int:
    questions_path = Path(args.questions)
    questions_bytes = read_bytes(questions_path)
    document = json.loads(questions_bytes.decode("utf-8"))
    require(
        document.get("version") == 1 and document.get("kind") == "typed-proposal-questions",
        "Bad questions file",
    )
    require(
        document["digest"] == digest({k: v for k, v in document.items() if k != "digest"}),
        "The questions file does not match its digest",
    )
    for question in document["questions"]:
        body = {k: v for k, v in question.items() if k != "digest"}
        require(
            question["digest"] == digest(body), f"Question {question['question_id']} was changed"
        )
    out = outside_repo(Path(args.out), "Run directory")
    require(not out.exists() or not any(out.iterdir()), "The run directory must be new or empty")
    if args.backend == "replay":
        require(args.replay is not None, "The replay backend needs --replay FILE")
        backend: Backend = ReplayBackend(Path(args.replay))
    elif args.backend == "jev":
        key = os.environ.get("TYPESAFE_API_KEY", "")
        require(args.allow_network, "The jev backend needs --allow-network")
        require(bool(key), "The jev backend needs TYPESAFE_API_KEY in the environment")
        backend = JevBackend(
            args.endpoint or JEV_ENDPOINT, args.model or JEV_MODEL, key, args.order_averaging
        )
    elif args.backend == "local-hf":
        require(args.model_path is not None, "The local-hf backend needs --model-path")
        backend = LocalHfBackend(Path(args.model_path), args.order_averaging)
    else:
        require(args.model_path is not None, "The laya backend needs --model-path")
        backend = LayaBackend(Path(args.model_path), args.order_averaging)
    require(
        args.backend == document["backend"] or args.backend == "replay",
        f"These questions were built for the {document['backend']} backend's budget; rebuild them",
    )
    questions = document["questions"][: args.limit] if args.limit else document["questions"]
    if isinstance(backend, JevBackend):
        estimate = jev_token_estimate(backend, questions, document["states"])
        print(f"jev: about {estimate} input tokens (request characters / 4), before any request")
        require(
            args.max_input_tokens is None or estimate <= args.max_input_tokens,
            f"The estimate of {estimate} input tokens is over --max-input-tokens",
        )
    started = now()
    raw_lines, rows, refused = [], {}, {}
    for question in questions:
        state = document["states"][question["alternative_id"]]
        try:
            scores, raw = backend.score(question, state)
        except QuestionRefusedError as exc:
            refused[question["question_id"]] = str(exc)
            raw_lines.append(
                json.dumps(
                    {
                        "question_id": question["question_id"],
                        "digest": question["digest"],
                        "backend": backend.name,
                        "refused": str(exc),
                    },
                    sort_keys=True,
                )
            )
            continue
        order = question["options"]
        probabilities = quantize(scores, order)
        top, tied = top_option(probabilities, order)
        raw_lines.append(
            json.dumps(
                {
                    "question_id": question["question_id"],
                    "digest": question["digest"],
                    "backend": backend.name,
                    "scores": scores,
                    "raw": raw,
                },
                sort_keys=True,
            )
        )
        rows[question["question_id"]] = {
            "digest": question["digest"],
            "probabilities": probabilities,
            "top": top,
            "tied": tied,
        }
        if isinstance(raw, dict) and MAX_CONFIDENCE_CHUNK in raw:
            second = quantize(raw[MAX_CONFIDENCE_CHUNK]["probabilities"], order)
            second_top, second_tied = top_option(second, order)
            rows[question["question_id"]]["readings"] = {
                MAX_CONFIDENCE_CHUNK: {
                    "probabilities": second,
                    "top": second_top,
                    "tied": second_tied,
                }
            }
    finished = now()
    probabilities_text = decimal_json({"version": 1, "rows": rows})
    raw_text = "\n".join(raw_lines) + "\n"
    manifest = {
        "version": 1,
        "kind": "typed-proposal-run",
        "runner_version": RUNNER_VERSION,
        "template_version": TEMPLATE_VERSION,
        "backend": backend.name,
        "model": {"id": backend.model_id, "version": backend.model_version},
        "scoring_version": backend.scoring_version,
        "parameters": backend.parameters(),
        "questions_file_sha256": sha(questions_bytes),
        "questions_digest": document["digest"],
        "question_count": len(questions),
        "raw_responses_sha256": sha(raw_text.encode("utf-8")),
        "probabilities_sha256": sha(probabilities_text.encode("utf-8")),
        "probability_places": PLACES,
        "started_at": started,
        "finished_at": finished,
        "environment": {
            "python": sys.version.split()[0],
            "platform": sys.platform,
            **backend.environment(),
        },
        **({"refused_questions": refused} if refused else {}),
    }
    for path in write_new(
        out,
        {
            "questions.json": questions_bytes,
            "raw_responses.jsonl": raw_text,
            "probabilities.json": probabilities_text,
            "run-manifest.json": pretty(manifest),
        },
    ):
        print(f"wrote {path}")
    print(f"{len(rows)} questions answered by {backend.name}")
    if refused:
        print(f"{len(refused)} questions refused by {backend.name}; see run-manifest.json")
    return 0


def jev_token_estimate(
    backend: JevBackend, questions: list[dict[str, Any]], states: dict[str, Any]
) -> int:
    """Input tokens a jev run would send, estimated as request characters over four."""
    total = 0
    for question in questions:
        body = json.dumps(backend.request_body(question, states[question["alternative_id"]]))
        sends = len(question["options"]) if backend.order_averaging == "rotations" else 1
        total += math.ceil(len(body) / 4) * sends
    return total


def command_fetch_model(args: argparse.Namespace) -> int:
    require(
        os.environ.get("MCDA_ALLOW_MODEL_DOWNLOAD") == "1",
        "Set MCDA_ALLOW_MODEL_DOWNLOAD=1 to download the model",
    )
    require(
        args.repo in MODEL_ALLOWLIST,
        "Only these models may be downloaded: " + ", ".join(MODEL_ALLOWLIST),
    )
    out = outside_repo(Path(args.out), "Model directory")
    try:
        from huggingface_hub import (  # type: ignore[import-not-found,unused-ignore]
            HfApi,
            snapshot_download,
        )
    except ImportError as exc:  # pragma: no cover
        raise RunnerError(
            "Run this from the classifier virtualenv (huggingface_hub is needed)"
        ) from exc
    revision = HfApi().model_info(args.repo).sha
    target = out / args.repo.split("/")[1]
    require(not target.exists(), f"{target} already exists")
    is_laya = args.repo in LAYA_REPOS
    limits = {"allow_patterns": LAYA_FILES} if is_laya else {}
    snapshot_download(repo_id=args.repo, revision=revision, local_dir=str(target), **limits)
    record = {
        "repo_id": args.repo,
        "revision": revision,
        "licence": "Apache-2.0",
        "retrieved_at": now(),
    }
    if is_laya:
        record.update(route="own repository", files=LAYA_FILES)
    (target / "mcda-model-revision.json").write_text(pretty(record), encoding="utf-8")
    print(f"model {args.repo} at revision {revision} in {target}")
    return 0


# ----------------------------------------------------------------------------- export


def load_run(directory: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = read_json(directory / "run-manifest.json")
    questions = read_json(directory / "questions.json")
    require(manifest.get("kind") == "typed-proposal-run", "Not a run directory")
    require(
        sha(read_bytes(directory / "questions.json")) == manifest["questions_file_sha256"],
        "The run's questions changed after the run",
    )
    probabilities_bytes = read_bytes(directory / "probabilities.json")
    require(
        sha(probabilities_bytes) == manifest["probabilities_sha256"],
        "The run's probabilities changed",
    )
    probabilities = json.loads(probabilities_bytes.decode("utf-8"), parse_float=Decimal)
    return manifest, questions, probabilities["rows"]


def model_card(manifest: dict[str, Any]) -> dict[str, Any]:
    unknown = "unknown — not stated by the model's publisher in a form this runner can cite"
    model = manifest["model"]
    is_local = manifest["backend"] == "local-hf"
    if manifest["backend"] == "laya":
        return laya_model_card(manifest, unknown)
    return {
        "version": 1,
        "purpose": (
            "Propose, for human review, which written rubric level a company's cited public pages "
            "best support. A proposal is never a measurement, weight, score or recommendation."
        ),
        "limitations": (
            "Reads only the cited page text, cut to a character budget. Zero-shot: no training or "
            "tuning on this task. Probabilities are the model's own, uncalibrated, and are "
            "metadata. "
            "No claim of accuracy is made until a blind second rater and the agreement benchmark "
            "have run. It predicts no company's success."
        ),
        "model_version": f"{model['id']}@{model['version']}",
        "details": {
            "backend": manifest["backend"],
            "prompt_template": manifest["template_version"],
            "runner_version": manifest["runner_version"],
            "scoring": (
                str(manifest["parameters"].get("scoring", SCORING_TEXT_SINGLE))
                + "; softmax over the letters; no sampling"
                if is_local
                else (
                    f"{manifest['parameters']['scoring']}; quantised to six decimals"
                    if "scoring" in manifest["parameters"]
                    else "Probabilities reported by the backend, quantised to six decimals"
                )
            ),
            "training_data_period": unknown,
            "population": unknown,
            "observation_cutoff": "The cited pages as retrieved; see the snapshot record",
            "label_definition": "The written rubric levels of the venture-screening study",
            "base_rate": "unknown — not measured; no labelled population was used",
            "known_biases": "Not assessed. A model may favour loud, well-documented companies; "
            "selection and survivorship bias in the pages are not corrected",
            "calibration": "unknown — no calibration study has been run on this task",
            "licence": "Apache-2.0 for Qwen2.5-1.5B-Instruct; otherwise "
            + (
                "unknown — see the provider's terms"
                if not is_local
                else "as stated by its publisher"
            ),
            "source_references": "Public pages named in the source registry; private copies "
            "are not for redistribution",
            "device": str(manifest["parameters"].get("device", "not applicable")),
        },
    }


def laya_model_card(manifest: dict[str, Any], unknown: str) -> dict[str, Any]:
    """A Laya run's card: what the checkpoint was tuned on, its window, chunking and averaging."""
    model, parameters = manifest["model"], manifest["parameters"]
    note = LAYA_NOTES.get(model["id"], "not one of the two named Laya checkpoints")
    return {
        "version": 1,
        "purpose": (
            "Propose, for human review, which written rubric level a company's cited public pages "
            "best support. A proposal is never a measurement, weight, score or recommendation."
        ),
        "limitations": (
            f"{note}. Reads only the cited page text, cut to a character budget, in chunks that "
            "fit the checkpoint's window; the mean over chunks dilutes a single decisive passage "
            "toward 'cannot tell'. No training or tuning on this task. Probabilities are the "
            "model's own, uncalibrated, and are metadata. No claim of accuracy is made until a "
            "blind second rater and the agreement benchmark have run. It predicts no company's "
            "success."
        ),
        "model_version": f"{model['id']}@{model['version']}",
        "details": {
            "backend": "laya",
            "prompt_template": manifest["template_version"],
            "runner_version": manifest["runner_version"],
            "scoring": f"{parameters['scoring']}; no sampling; quantised to six decimals",
            "fine_tuning": note,
            "window": (
                f"{parameters['window_tokens']} tokens, the question capped at "
                f"{parameters['head_max_tokens']}; a question the package would cut is refused"
            ),
            "chunking": (
                "blank-line paragraphs packed greedily to the state budget (the window less the "
                f"question less {parameters['margin_tokens']} tokens); a paragraph over the budget "
                "split on sentences, a sentence over it by token count"
            ),
            "checkpoint_route": parameters["checkpoint_route"],
            "training_data_period": unknown,
            "population": unknown,
            "observation_cutoff": "The cited pages as retrieved; see the snapshot record",
            "label_definition": "The written rubric levels of the venture-screening study",
            "base_rate": "unknown — not measured; no labelled population was used",
            "known_biases": "Not assessed. A model may favour loud, well-documented companies; "
            "selection and survivorship bias in the pages are not corrected",
            "calibration": "unknown — no calibration study has been run on this task",
            "licence": "Apache-2.0 (the laya package and the convaiinnovations checkpoints)",
            "source_references": "Public pages named in the source registry; private copies "
            "are not for redistribution",
            "device": str(parameters.get("device", "not applicable")),
        },
    }


def card_bytes(card: dict[str, Any]) -> bytes:
    """The card as its canonical JSON, so the file's SHA-256 is also the contract's digest."""
    return canonical(card).encode("utf-8")


def source_id(url: str) -> str:
    return "src_" + sha(url.encode())[:12]


def chosen_reading(rows: dict[str, Any], reading: str) -> dict[str, Any]:
    """The rows of the requested reading: the mean as recorded, or a recorded second reading."""
    require(reading in READINGS, "Unknown --reading")
    key = READINGS[reading]
    if key is None:
        return rows
    missing = [qid for qid, row in rows.items() if key not in row.get("readings", {})]
    require(
        not missing,
        f"This run recorded no {reading} reading (another backend, or a Laya run made before the "
        "reading was recorded); re-run it to get one",
    )
    return {qid: row["readings"][key] for qid, row in rows.items()}


def command_export(args: argparse.Namespace) -> int:
    manifest, document, recorded = load_run(Path(args.run))
    rows = chosen_reading(recorded, args.reading)
    threshold = Decimal(args.threshold)
    require(Decimal(0) <= threshold <= Decimal(1), "The threshold is between 0 and 1")
    fingerprint = project_fingerprint(Path(args.project))
    project = read_json(Path(args.project))
    scales = {c["id"]: (c.get("scale") or {}) for c in project["criteria"]}
    alternatives = {a["id"] for a in project["alternatives"]}
    second = READINGS[args.reading] is not None
    card = model_card(manifest)
    if second:
        card = {**card, "details": {**card["details"], "reading": READING_MAX_CONFIDENCE_CHUNK}}
    card_digest = sha(card_bytes(card))
    tool_id = f"typed-proposal-runner:{manifest['backend']}"
    tool_version = f"{RUNNER_VERSION}+{manifest['template_version']}"
    if second:
        tool_version += f"+{args.reading}"
    run_at = manifest["finished_at"]
    sources: dict[str, Any] = {}
    proposal_rows: list[list[str]] = []
    per_leaf: dict[str, Any] = {}
    abstentions: list[dict[str, str]] = []
    tasks: dict[str, list[dict[str, Any]]] = {}
    refused = manifest.get("refused_questions", {})
    for question in document["questions"]:
        qid = question["question_id"]
        if qid in refused:
            abstentions.append({"question_id": qid, "reason": f"refused: {refused[qid]}"})
            continue
        if qid not in rows:
            continue
        alt, leaf = question["alternative_id"], question["criterion_id"]
        require(alt in alternatives, f"Unknown alternative {alt}")
        require(
            scales.get(leaf, {}).get("labels") == question["labels"],
            f"{leaf}: labels differ from the project's scale",
        )
        row = rows[qid]
        probabilities: dict[str, Decimal] = row["probabilities"]
        top, tied = row["top"], row["tied"]
        top_p = probabilities[top] if top else Decimal(0)
        proposed = top is not None and top != CANNOT_TELL and top_p >= threshold
        if not proposed:
            reason = "tie" if tied else ("cannot tell" if top == CANNOT_TELL else "below threshold")
            abstentions.append({"question_id": qid, "reason": reason})
        stats = per_leaf.setdefault(
            leaf,
            {
                "questions": 0,
                "proposed": 0,
                "abstained": 0,
                "labels": {label: 0 for label in question["labels"]},
            },
        )
        stats["questions"] += 1
        stats["proposed" if proposed else "abstained"] += 1
        if proposed:
            stats["labels"][top] += 1
            ids = []
            for source in document["states"][alt]["sources"]:
                if source["available"]:
                    sid = source_id(source["url"])
                    ids.append(sid)
                    sources[sid] = {
                        "name": source["name"] or source["url"],
                        "reference": source["url"],
                        "location": "",
                        "date": source["date"],
                        "description": "Public page read by the runner; private snapshot "
                        f"text sha256 {source['text_sha256']}.",
                        "classification": "unknown",
                    }
            confidence = {
                "value": float(top_p),
                "scale": "unit_interval",
                "meaning": CONFIDENCE_MEANING,
            }
            proposal_rows.append(
                [
                    "1", fingerprint, f"typed__{qid}", "1", "categorical_cell", alt, leaf,
                    canonical({"kind": "categorical_cell", "unit": None, "value": top}),
                    tool_id, tool_version, "runner_model_card", card_digest, run_at,
                    canonical(confidence), canonical(sorted(set(ids))), "",
                ]
            )  # fmt: skip
        levels = [f"level_{i}" for i in range(1, len(question["labels"]) + 1)]
        task_id = f"{document['study']}-{len(levels)}-level"
        vector = None
        if proposed:
            without = {o: probabilities[o] for o in question["labels"]}
            if sum(without.values()) > 0:
                kept = quantize({o: float(p) for o, p in without.items()}, question["labels"])
                vector = {lv: kept[o] for lv, o in zip(levels, question["labels"], strict=True)}
        tasks.setdefault(task_id, []).append(
            {
                "item_id": qid,
                "tool_id": tool_id,
                "tool_version": tool_version,
                "task_version": "1",
                "model_card_digest": card_digest,
                "label": levels[question["labels"].index(top)] if proposed else None,
                "run_at": run_at,
                "score": None,
                "probabilities": vector if proposed else None,
            }
        )
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    writer.writerows(proposal_rows)
    files: dict[str, str | bytes] = {
        "proposals.csv": buffer.getvalue(),
        "registries.json": pretty(
            {
                "project_fingerprint": fingerprint,
                "sources": sources,
                "model_cards": {"runner_model_card": card},
                "human_dossier": None,
            }
        ),
        "model-card.json": card_bytes(card),
        "run-report.json": pretty(
            {
                "version": 1,
                "kind": "typed-proposal-run-report",
                "note": "Counts only. Nothing here compares the tool with any rating.",
                **({"reading": READING_MAX_CONFIDENCE_CHUNK} if second else {}),
                "threshold": args.threshold,
                "proposals": len(proposal_rows),
                "abstentions": len(abstentions),
                "abstention_list": abstentions,
                "per_criterion": per_leaf,
                "run_manifest_sha256": sha(read_bytes(Path(args.run) / "run-manifest.json")),
            }
        ),
    }
    for task_id, task_rows in tasks.items():
        files[f"tool_outputs.{task_id}.json"] = decimal_json(
            sorted(task_rows, key=lambda r: r["item_id"])
        )
    for path in write_new(Path(args.out), files):
        print(f"wrote {path}")
    print(
        f"{len(proposal_rows)} proposals, {len(abstentions)} abstentions; card digest {card_digest}"
    )
    return 0


# ----------------------------------------------------------------------------- compare-runs


def command_compare_runs(args: argparse.Namespace) -> int:
    _, questions_a, rows_a = load_run(Path(args.run_a))
    _, questions_b, rows_b = load_run(Path(args.run_b))
    require(set(rows_a) == set(rows_b), "The two runs answered different questions")
    options = {q["question_id"]: q["options"] for q in questions_a["questions"]}
    cells, changed = [], 0
    for qid in sorted(rows_a):
        order = options[qid]
        pa, pb = rows_a[qid]["probabilities"], rows_b[qid]["probabilities"]
        require(set(pa) == set(pb) == set(order), f"{qid}: the runs offered different options")
        shifts = {o: pb[o] - pa[o] for o in order}
        flip = rows_a[qid]["top"] != rows_b[qid]["top"]
        changed += flip
        cells.append(
            {
                "question_id": qid,
                "top_a": rows_a[qid]["top"],
                "top_b": rows_b[qid]["top"],
                "top_changed": flip,
                "shifts": shifts,
                "largest_shift": max((abs(s) for s in shifts.values()), default=Decimal(0)),
            }
        )
    largest = sorted(cells, key=lambda c: (-c["largest_shift"], c["question_id"]))[: args.top]
    report = {
        "version": 1,
        "kind": "typed-proposal-run-comparison",
        "run_a": args.run_a_name or "A",
        "run_b": args.run_b_name or "B",
        "questions_a_digest": questions_a["digest"],
        "questions_b_digest": questions_b["digest"],
        "cells": len(cells),
        "top_label_changed": changed,
        "top_label_unchanged": len(cells) - changed,
        "largest_shifts": [
            {
                "question_id": c["question_id"],
                "largest_shift": c["largest_shift"],
                "top_a": c["top_a"],
                "top_b": c["top_b"],
            }
            for c in largest
        ],
        "cell_detail": cells,
    }
    for path in write_new(Path(args.out).parent, {Path(args.out).name: decimal_json(report)}):
        print(f"wrote {path}")
    print(f"{changed} of {len(cells)} top labels changed")
    return 0


# ----------------------------------------------------------------------------- command line


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = top.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("snapshot", help="fetch the cited pages politely")
    snap.add_argument("--evidence", required=True)
    snap.add_argument("--out", required=True)
    snap.add_argument("--refresh", action="store_true")
    snap.set_defaults(handler=command_snapshot)

    ask = sub.add_parser("questions", help="build the question set")
    ask.add_argument("--project", required=True)
    ask.add_argument("--rubrics", required=True)
    ask.add_argument("--evidence", required=True)
    ask.add_argument("--snapshots", required=True)
    ask.add_argument("--redact")
    ask.add_argument("--swap")
    ask.add_argument("--backend", choices=sorted(DEFAULT_BUDGETS), default="local-hf")
    ask.add_argument("--budget-chars", type=int)
    ask.add_argument(
        "--extractor",
        type=int,
        choices=[1, 2],
        default=1,
        help="1: snapshots.json (text as first extracted); 2: snapshots.v2.json (from reextract)",
    )
    ask.add_argument("--out", required=True)
    ask.set_defaults(handler=command_questions)

    again = sub.add_parser(
        "reextract", help="rebuild page text from the saved raw bytes with the version-2 filter"
    )
    again.add_argument("--snapshots", required=True)
    again.set_defaults(handler=command_reextract)

    model = sub.add_parser("fetch-model", help="download the free local model (needs the env flag)")
    model.add_argument("--repo", default=QWEN_REPO)
    model.add_argument("--out", required=True)
    model.set_defaults(handler=command_fetch_model)

    run = sub.add_parser("run", help="answer the questions with a backend")
    run.add_argument("--questions", required=True)
    run.add_argument("--backend", choices=["replay", "jev", "local-hf", "laya"], required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--allow-network", action="store_true")
    run.add_argument("--model-path")
    run.add_argument("--model")
    run.add_argument("--endpoint")
    run.add_argument("--replay")
    run.add_argument("--limit", type=int)
    run.add_argument(
        "--order-averaging",
        choices=list(ORDER_AVERAGING),
        default="rotations",
        help="local-hf, laya and jev: average over every cyclic option order (default) or score "
        "one order (comparison only)",
    )
    run.add_argument(
        "--max-input-tokens",
        type=int,
        help="jev: refuse before any request if the estimated input tokens exceed this",
    )
    run.set_defaults(handler=command_run)

    export = sub.add_parser("export", help="External Proposals files and benchmark tables")
    export.add_argument("--run", required=True)
    export.add_argument("--project", required=True)
    export.add_argument("--threshold", default="0.5")
    export.add_argument(
        "--reading",
        choices=sorted(READINGS),
        default="mean",
        help="mean (the accepted reading) or max-confidence-chunk (Laya's recorded second reading)",
    )
    export.add_argument("--out", required=True)
    export.set_defaults(handler=command_export)

    compare = sub.add_parser("compare-runs", help="how two runs differ, cell by cell")
    compare.add_argument("run_a")
    compare.add_argument("run_b")
    compare.add_argument("--run-a-name")
    compare.add_argument("--run-b-name")
    compare.add_argument("--top", type=int, default=10)
    compare.add_argument("--out", required=True)
    compare.set_defaults(handler=command_compare_runs)
    return top


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except RunnerError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
