"""Offline human-agreement gate and classifier benchmark; never inference or app import.

Counts, kappa, coverage and calibration use exact rationals. Bootstrap percentile endpoints
and display approximations are binary64. Input probability-vector sum tolerance is zero.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import platform
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np

VERSION = 1
ALGORITHM = "classifier-agreement.v1"
BOOTSTRAP_ALGORITHM = "pcg64-joint-unit-bootstrap.v1"
REPLICATES = 10_000
ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 8_000_000
MAX_TOTAL_BYTES = 64_000_000
# A report embeds the manifest and raw human labels (each at most MAX_BYTES), re-indented, plus
# bounded summaries; the writer refuses anything the reader could not reopen.
MAX_REPORT_BYTES = 64_000_000
MAX_ITEMS = 2000
MAX_REVIEWERS = 20
MAX_LABELS = 32
MAX_TOOLS = 20
BINS = [Fraction(i, 10) for i in range(11)]


class BenchmarkError(ValueError):
    """An entire local batch is refused, without substituting data or writing a report."""


def require(condition: Any, reason: str) -> None:
    if not condition:
        raise BenchmarkError(reason)


def fields(value: Any, required: set[str], optional: set[str] | None = None) -> dict:
    require(isinstance(value, dict), "Expected a JSON object")
    require(
        set(value) >= required and not set(value) - required - (optional or set()),
        f"Missing or unknown fields; required {sorted(required)}",
    )
    return value


def text(value: Any) -> str:
    require(
        isinstance(value, str) and bool(value.strip()) and len(value) <= 4000,
        "Expected explicit nonempty text",
    )
    return value


def integer(value: Any, lower: int, upper: int) -> int:
    require(type(value) is int and lower <= value <= upper, "Integer outside its declared limits")
    return value


def exact(value: Any) -> Fraction:
    require(
        type(value) in {int, Decimal} or isinstance(value, Fraction),
        "Expected a finite JSON number",
    )
    require(not isinstance(value, Decimal) or value.is_finite(), "Nonfinite numeric input")
    require(abs(value) <= Decimal("1e100"), "Numeric input exceeds the finite protocol range")
    if isinstance(value, Decimal):
        require(value.as_tuple().exponent >= -300, "At most 300 fractional decimal places")
    return Fraction(value)


def timestamp(value: Any) -> datetime:
    text(value)
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise BenchmarkError("Use explicit ISO timestamps") from exc
    require(result.utcoffset() is not None, "Timestamps require an explicit timezone")
    return result


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_default(value):
    if isinstance(value, Decimal | Fraction):
        return str(value)
    raise TypeError(type(value).__name__)


def canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=_json_default,
    )


def digest(value: Any) -> str:
    return sha(canonical(value).encode())


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON object key")
        result[key] = value
    return result


def decode(data: bytes) -> Any:
    try:
        return json.loads(
            data,
            parse_float=Decimal,
            object_pairs_hook=_pairs,
            parse_constant=lambda _: require(False, "Nonfinite JSON number"),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BenchmarkError("Invalid UTF-8 JSON") from exc


def read(path: Path, limit: int = MAX_BYTES) -> bytes:
    require(path.is_file() and path.stat().st_size <= limit, "Missing or oversized local file")
    data = path.read_bytes()
    require(len(data) <= limit, f"Local file exceeds {limit // 1_000_000} MB")
    return data


def hex_digest(value: Any) -> str:
    require(
        isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value) is not None,
        "Declare lowercase SHA-256 digests",
    )
    return value


def measure(numerator: int | Fraction, denominator: int | Fraction) -> dict:
    value = Fraction(numerator, denominator) if denominator else None
    return {
        "numerator": str(numerator),
        "denominator": str(denominator),
        "exact": str(value) if value is not None else None,
        "value": float(value) if value is not None else None,
    }


def statistic(value: Fraction | None) -> dict:
    return {
        "exact": str(value) if value is not None else None,
        "value": float(value) if value is not None else None,
    }


def agreement(rows: list[tuple[int, ...]], labels: int, reviewers: int) -> dict:
    """Exact Cohen (two) or Fleiss (fixed larger panel), retaining both marginals."""
    n = len(rows)
    counts = [[0] * labels for _ in range(reviewers)]
    observed = 0
    for row in rows:
        for reviewer, label in enumerate(row):
            counts[reviewer][label] += 1
        if reviewers == 2:
            observed += row[0] == row[1]
        else:
            within = Counter(row)
            observed += sum(count * (count - 1) for count in within.values())
    return agreement_counts(n, observed, counts, labels, reviewers)


def agreement_counts(n, observed, counts, labels, reviewers):
    if not n:
        return {"n": 0, "counts": counts, "observed": None, "chance": None, "kappa": None}
    po = Fraction(observed, n if reviewers == 2 else n * reviewers * (reviewers - 1))
    if reviewers == 2:
        pe = sum(
            (Fraction(counts[0][label] * counts[1][label], n * n) for label in range(labels)),
            Fraction(),
        )
    else:
        pe = sum(
            (
                Fraction(sum(counts[r][label] for r in range(reviewers)), n * reviewers) ** 2
                for label in range(labels)
            ),
            Fraction(),
        )
    kappa = (po - pe) / (1 - pe) if pe != 1 else None
    return {"n": n, "counts": counts, "observed": po, "chance": pe, "kappa": kappa}


def bootstrap(
    panels: dict[str, tuple[int, ...]],
    group_of: dict[str, str],
    labels: int,
    reviewers: int,
    seed: int,
    unit: str,
    *,
    batch_size: int = 32,
    replicates: int = REPLICATES,
) -> dict:
    """Resample complete atomic panels/groups jointly, never individual reviewer labels."""
    ids = sorted(panels)
    if not ids:
        return {
            "status": "unavailable",
            "reason": "No complete panels",
            "attempted": 0,
            "undefined": 0,
            "undefined_indices": [],
            "interval": None,
            "trace": [],
            "replicates_digest": digest([]),
            "exact_values": [],
        }
    rng = np.random.Generator(np.random.PCG64(seed))
    encoded = [panels[id] for id in ids]
    lookup = dict(zip(ids, encoded, strict=True))
    groups = defaultdict(list)
    for id in ids:
        groups[group_of[id] if unit == "group" else id].append(id)
    units = sorted(groups)
    # Integer sufficient statistics preserve exactly the same joint-label resampling.
    summaries = []
    for key in units:
        result = agreement([lookup[id] for id in groups[key]], labels, reviewers)
        counts = [v for row in result["counts"] for v in row]
        within = result["observed"] * (
            result["n"] if reviewers == 2 else result["n"] * reviewers * (reviewers - 1)
        )
        summaries.append([result["n"], int(within), *counts])
    matrix = np.asarray(summaries, dtype=np.int64)
    values: list[Fraction] = []
    undefined = []
    trace = []
    sealed = hashlib.sha256()
    for start in range(0, replicates, batch_size):
        selections = rng.integers(
            0, len(units), size=(min(batch_size, replicates - start), len(units))
        )
        for offset, selection in enumerate(selections):
            index = start + offset
            row = matrix[selection].sum(axis=0)
            counts = [
                [int(row[2 + r * labels + c]) for c in range(labels)] for r in range(reviewers)
            ]
            result = agreement_counts(int(row[0]), int(row[1]), counts, labels, reviewers)
            value = result["kappa"]
            if value is None:
                undefined.append(index)
            else:
                values.append(value)
            sealed.update(
                (
                    canonical({"index": index, "kappa": str(value) if value is not None else None})
                    + "\n"
                ).encode()
            )
            if index < 16:
                trace.append(
                    {
                        "index": index,
                        "unit_ids": [units[int(i)] for i in selection],
                        "kappa": str(value) if value is not None else None,
                    }
                )
    interval = None
    if not undefined:
        endpoints = np.quantile(
            np.asarray([float(v) for v in values]), [0.025, 0.975], method="linear"
        )
        if bool(np.isfinite(endpoints).all()):
            interval = [float(endpoints[0]), float(endpoints[1])]
    return {
        "status": "completed" if interval is not None else "refused",
        "reason": "Undefined replicates refuse the interval" if undefined else "",
        "attempted": replicates,
        "undefined": len(undefined),
        "undefined_indices": undefined,
        "interval": interval,
        "trace": trace,
        "replicates_digest": sealed.hexdigest(),
        "exact_values": values,
    }


def gate_passes(kappa: Fraction | None, interval: list[float] | None, coverage: Fraction) -> bool:
    return bool(
        kappa is not None
        and interval is not None
        and interval[0] >= 0.60
        and coverage >= Fraction(4, 5)
    )


def _table(value: Any) -> list[dict]:
    require(
        isinstance(value, list) and all(isinstance(row, dict) for row in value),
        "Input tables must be JSON arrays of objects",
    )
    return value


def load(manifest_path: Path, output: Path | None = None) -> tuple[dict, dict, dict]:
    raw = read(manifest_path)
    manifest = fields(
        decode(raw),
        {
            "version",
            "data_kind",
            "data_provenance",
            "task",
            "labels",
            "panel",
            "splits",
            "protocol",
            "files",
            "tools",
        },
    )
    require(
        type(manifest["version"]) is int and manifest["version"] == VERSION,
        "Unsupported benchmark version",
    )
    require(manifest["data_kind"] in {"synthetic", "real", "public"}, "Declare the data kind")
    private = manifest["data_kind"] != "synthetic"
    if private:
        require(
            not manifest_path.resolve().is_relative_to(ROOT),
            "Real inputs are refused inside the checkout",
        )
        if output is not None:
            require(
                not output.resolve().is_relative_to(ROOT),
                "Real reports are refused inside the checkout",
            )
    provenance = fields(
        manifest["data_provenance"],
        {"description"},
        {"generation_seed", "source", "licence", "snapshot_sha256"},
    )
    text(provenance["description"])
    if manifest["data_kind"] == "synthetic":
        integer(provenance.get("generation_seed"), 0, 2**63 - 1)
    if manifest["data_kind"] == "public":
        for name in ("source", "licence"):
            text(provenance.get(name))
        # A declaration only: the public source is never fetched (no network).
        hex_digest(provenance.get("snapshot_sha256"))
    task = fields(
        manifest["task"],
        {
            "id",
            "version",
            "instructions",
            "unit",
            "population",
            "observation_cutoff",
            "eligibility",
            "exclusions",
        },
    )
    for value in task.values():
        text(value)
    timestamp(task["observation_cutoff"])
    labels, panel = manifest["labels"], manifest["panel"]
    for values, minimum, maximum in ((labels, 2, MAX_LABELS), (panel, 2, MAX_REVIEWERS)):
        require(
            isinstance(values, list) and minimum <= len(values) <= maximum,
            "Declare a supported vocabulary and fixed reviewer panel",
        )
        require(
            all(isinstance(value, str) and value.strip() for value in values)
            and len(set(values)) == len(values),
            "Unique explicit labels/reviewer tokens are required",
        )
    require("__abstention__" not in labels, "Reserved abstention column is not a task label")
    splits = fields(manifest["splits"], {"train", "development", "test"})
    require(
        all(
            isinstance(ids, list) and all(isinstance(id, str) and id.strip() for id in ids)
            for ids in splits.values()
        ),
        "Explicit split item IDs are required",
    )
    all_ids = [id for ids in splits.values() for id in ids]
    require(
        len(all_ids) == len(set(all_ids)) and bool(splits["test"]),
        "Splits must be disjoint and test cannot be empty",
    )
    protocol = fields(
        manifest["protocol"],
        {
            "frozen_at",
            "gate_confirmed_at",
            "outputs_unblinded_at",
            "independent_blind_reviews",
            "blind_adjudication",
            "reference_policy",
            "confidence",
            "lower_kappa",
            "minimum_coverage",
            "bootstrap",
        },
    )
    require(
        protocol["independent_blind_reviews"] is True and protocol["blind_adjudication"] is True,
        "Independent blind review and adjudication are required",
    )
    require(
        protocol["reference_policy"] == "unanimous-or-post-gate-adjudication.v1",
        "Unsupported reference policy",
    )
    require(
        (protocol["confidence"], protocol["lower_kappa"], protocol["minimum_coverage"])
        == ("0.95", "0.60", "0.80"),
        "The owner-approved thresholds are frozen for version 1",
    )
    frozen, confirmed, unblinded = (
        timestamp(protocol[name])
        for name in ("frozen_at", "gate_confirmed_at", "outputs_unblinded_at")
    )
    require(frozen < confirmed < unblinded, "Invalid frozen/gate/unblinding chronology")
    boot = fields(protocol["bootstrap"], {"replicates", "seed", "unit", "algorithm", "quantile"})
    integer(boot["replicates"], REPLICATES, REPLICATES)
    integer(boot["seed"], 0, 2**63 - 1)
    require(
        boot["unit"] in {"item", "group"}
        and boot["algorithm"] == BOOTSTRAP_ALGORITHM
        and boot["quantile"] == "linear.v1",
        "Unsupported bootstrap design",
    )
    files = fields(manifest["files"], {"items", "human_labels", "tool_outputs", "adjudications"})
    tools = manifest["tools"]
    require(isinstance(tools, list) and 1 <= len(tools) <= MAX_TOOLS, "Declare one to twenty tools")
    seen = set()
    for tool in tools:
        fields(
            tool, {"id", "version", "task_version", "model_card", "score_semantics", "score_bounds"}
        )
        for name in ("id", "version", "task_version"):
            text(tool[name])
        require(
            tool["id"] not in seen and tool["task_version"] == task["version"],
            "Duplicate tool or wrong task version",
        )
        seen.add(tool["id"])
        require(
            tool["score_semantics"]
            in {"none", "arbitrary_score", "chosen_label_confidence", "probability_vector"},
            "Declare score semantics",
        )
        bounds = tool["score_bounds"]
        if tool["score_semantics"] == "arbitrary_score":
            require(
                isinstance(bounds, list)
                and len(bounds) == 2
                and exact(bounds[0]) <= exact(bounds[1]),
                "Arbitrary scores need explicit bounds",
            )
        else:
            require(bounds is None, "Only arbitrary scores have separate bounds")
    data, hashes = {}, {"manifest": sha(raw)}
    total = len(raw)
    for key, declaration in [
        *files.items(),
        *[("card:" + tool["id"], tool["model_card"]) for tool in tools],
    ]:
        fields(declaration, {"path", "sha256"})
        text(declaration["path"])
        hex_digest(declaration["sha256"])
        path = (manifest_path.parent / declaration["path"]).resolve()
        if private:
            require(not path.is_relative_to(ROOT), "Real inputs cannot resolve inside the checkout")
        content = read(path)
        total += len(content)
        require(total <= MAX_TOTAL_BYTES, "At most 64 MB of local inputs")
        require(sha(content) == declaration["sha256"], "Input digest mismatch")
        hashes[key] = sha(content)
        data[key] = decode(content)
    for key in files:
        data[key] = _table(data[key])
    for tool in tools:
        card = data["card:" + tool["id"]]
        require(
            isinstance(card, dict)
            and isinstance(card.get("model_version"), str)
            and card["model_version"].strip(),
            "Model card needs a declared model version",
        )
    return manifest, data, hashes


def validate_tables(manifest: dict, data: dict) -> tuple[dict, dict, dict]:
    labels, panel = manifest["labels"], manifest["panel"]
    task, protocol = manifest["task"], manifest["protocol"]
    cutoff = timestamp(task["observation_cutoff"])
    frozen, confirmed, unblinded = (
        timestamp(protocol[name])
        for name in ("frozen_at", "gate_confirmed_at", "outputs_unblinded_at")
    )
    expected = {id: split for split, ids in manifest["splits"].items() for id in ids}
    require(
        len(data["items"]) <= MAX_ITEMS and len(data["items"]) == len(expected),
        "Item limit or split membership mismatch",
    )
    items = {}
    entity_splits = {}
    group_splits = {}
    entity_groups = {}
    for item in data["items"]:
        fields(
            item,
            {
                "id",
                "entity_id",
                "group_id",
                "split",
                "eligible",
                "exclusion_reason",
                "observed_at",
                "feature_dates",
            },
        )
        id = text(item["id"])
        entity = text(item["entity_id"])
        group = text(item["group_id"])
        require(
            id not in items and expected.get(id) == item["split"], "Duplicate item or wrong split"
        )
        require(
            type(item["eligible"]) is bool and isinstance(item["exclusion_reason"], str),
            "Declare eligibility and exclusions",
        )
        require(
            item["eligible"] or bool(item["exclusion_reason"].strip()),
            "Excluded items need a reason",
        )
        require(
            timestamp(item["observed_at"]) <= cutoff and isinstance(item["feature_dates"], dict),
            "Observation after cutoff or missing feature dates",
        )
        for name, date in item["feature_dates"].items():
            text(name)
            require(timestamp(date) <= cutoff, "Post-cutoff feature leak")
        for key, mapping in ((entity, entity_splits), (group, group_splits)):
            require(
                key not in mapping or mapping[key] == item["split"],
                "Entity/group leakage across splits",
            )
            mapping[key] = item["split"]
        require(
            entity not in entity_groups or entity_groups[entity] == group,
            "An entity must move as one group",
        )
        entity_groups[entity] = group
        items[id] = item
    require(set(items) == set(expected), "Unknown or missing split items")
    human = defaultdict(dict)
    for row in data["human_labels"]:
        fields(row, {"item_id", "reviewer", "label", "reviewed_at", "task_version"})
        id, reviewer = text(row["item_id"]), text(row["reviewer"])
        require(
            id in items and reviewer in panel and reviewer not in human[id],
            "Unknown/duplicate item-reviewer or mixed panel",
        )
        require(row["label"] is None or row["label"] in labels, "Unknown human label; no coercion")
        require(row["task_version"] == task["version"], "Wrong human task version")
        require(
            frozen <= timestamp(row["reviewed_at"]) <= confirmed,
            "Human reviews must precede the declared gate and unblinding",
        )
        human[id][reviewer] = row
    tools = {t["id"]: t for t in manifest["tools"]}
    outputs = defaultdict(dict)
    for row in data["tool_outputs"]:
        fields(
            row,
            {
                "item_id",
                "tool_id",
                "tool_version",
                "task_version",
                "model_card_digest",
                "label",
                "run_at",
                "score",
                "probabilities",
            },
        )
        id, tool_id = text(row["item_id"]), text(row["tool_id"])
        require(
            id in items and tool_id in tools and id not in outputs[tool_id],
            "Unknown/duplicate tool output",
        )
        tool = tools[tool_id]
        require(
            row["tool_version"] == tool["version"]
            and row["task_version"] == task["version"]
            and row["model_card_digest"] == tool["model_card"]["sha256"],
            "Wrong tool/task/card version",
        )
        require(frozen <= timestamp(row["run_at"]), "Tool run precedes the frozen protocol")
        require(row["label"] is None or row["label"] in labels, "Unknown tool label; no coercion")
        semantics = tool["score_semantics"]
        if semantics == "probability_vector":
            require(row["score"] is None, "Vector semantics cannot carry another score")
            vector = row["probabilities"]
            if vector is not None:
                require(
                    isinstance(vector, dict) and set(vector) == set(labels),
                    "Full probability vocabulary required",
                )
                probabilities = [exact(vector[label]) for label in labels]
                require(
                    all(0 <= p <= 1 for p in probabilities) and sum(probabilities) == 1,
                    "Probability vector must sum exactly to one; no normalization",
                )
        else:
            require(row["probabilities"] is None, "Undeclared probability vector")
            if row["score"] is not None:
                score = exact(row["score"])
                require(semantics != "none", "No score semantics were declared")
                if semantics == "chosen_label_confidence":
                    require(
                        row["label"] is not None and 0 <= score <= 1,
                        "Chosen-label confidence requires a label and unit interval",
                    )
                else:
                    lo, hi = map(exact, tool["score_bounds"])
                    require(lo <= score <= hi, "Score is outside its declared scale")
        outputs[tool_id][id] = row
    if manifest["protocol"]["bootstrap"]["unit"] == "item":
        entities = [
            i["entity_id"] for i in items.values() if i["eligible"] and i["split"] == "test"
        ]
        require(len(entities) == len(set(entities)), "Repeated entities require grouped bootstrap")
    return items, human, outputs


def resolve_reference(manifest, items, human, adjudications, passed, gate_digest):
    labels, panel = manifest["labels"], manifest["panel"]
    confirmed = timestamp(manifest["protocol"]["gate_confirmed_at"])
    unblinded = timestamp(manifest["protocol"]["outputs_unblinded_at"])
    require(not adjudications or passed, "Adjudication supplied before a passed human gate")
    resolved = {}
    adjudicated = set()
    for row in adjudications:
        fields(
            row,
            {
                "item_id",
                "reference_label",
                "rationale",
                "reviewers",
                "reviewed_at",
                "gate_digest",
                "task_version",
            },
        )
        id = text(row["item_id"])
        require(
            id in items and items[id]["eligible"] and id not in adjudicated,
            "Unknown/duplicate/ineligible adjudication",
        )
        require(
            row["reference_label"] in labels and row["task_version"] == manifest["task"]["version"],
            "Wrong adjudication task or label",
        )
        text(row["rationale"])
        require(
            isinstance(row["reviewers"], list)
            and len(row["reviewers"]) >= 2
            and all(isinstance(token, str) and token.strip() for token in row["reviewers"])
            and len(set(row["reviewers"])) == len(row["reviewers"])
            and set(row["reviewers"]) <= set(panel),
            "Adjudication needs distinct declared reviewer tokens",
        )
        require(
            confirmed < timestamp(row["reviewed_at"]) < unblinded
            and row["gate_digest"] == gate_digest,
            "Leaked or stale-gate adjudication",
        )
        adjudicated.add(id)
        resolved[id] = row["reference_label"]
    if passed:
        for id, item in items.items():
            values = [human[id].get(reviewer, {}).get("label") for reviewer in panel]
            if item["eligible"] and None not in values and len(set(values)) == 1:
                require(
                    id not in resolved or resolved[id] == values[0],
                    "Adjudication contradicts a unanimous reference",
                )
                resolved[id] = values[0]
    return resolved


def metrics(labels, references, predictions):
    matrix = {label: {**{pred: 0 for pred in labels}, "__abstention__": 0} for label in labels}
    for id, reference in references.items():
        predicted = predictions.get(id)
        matrix[reference][predicted if predicted is not None else "__abstention__"] += 1
    n = len(references)
    per_class = {}
    macro_p = []
    macro_r = []
    macro_f = []
    for label in labels:
        tp = matrix[label][label]
        support = sum(matrix[label].values())
        predicted = sum(matrix[other][label] for other in labels)
        precision = Fraction(tp, predicted) if predicted else None
        recall = Fraction(tp, support) if support else None
        f1 = Fraction(2 * tp, support + predicted) if support + predicted else None
        per_class[label] = {
            "support": support,
            "predicted": predicted,
            "true_positive": tp,
            "precision": measure(tp, predicted),
            "recall": measure(tp, support),
            "f1": measure(2 * tp, support + predicted),
        }
        macro_p.append(precision)
        macro_r.append(recall)
        macro_f.append(f1)
    correct = sum(matrix[label][label] for label in labels)
    predicted = sum(matrix[reference][label] for reference in labels for label in labels)

    def macro(values):
        return statistic(
            sum(values, Fraction()) / len(values) if all(v is not None for v in values) else None
        )

    return {
        "n": n,
        "confusion": matrix,
        "classes": per_class,
        "accuracy": measure(correct, n),
        "coverage": measure(predicted, n),
        "abstention": measure(n - predicted, n),
        "micro_precision": measure(correct, predicted),
        "micro_recall": measure(correct, n),
        "macro_precision": macro(macro_p),
        "macro_recall": macro(macro_r),
        "macro_f1": macro(macro_f),
        "macro_definition": (
            "Unweighted over the frozen vocabulary; null if any component is undefined"
        ),
    }


def calibration(tool, labels, references, outputs, total_test):
    semantics = tool["score_semantics"]
    if semantics not in {"probability_vector", "chosen_label_confidence"}:
        return {
            "status": "not calibration-eligible",
            "semantics": semantics,
            "brier": None,
            "bins": [],
            "score_coverage": measure(0, len(references)),
            "test_score_coverage": measure(0, total_test),
        }
    entries = []
    brier = Fraction()
    scored = []
    for id, reference in references.items():
        row = outputs.get(id)
        if row is None:
            continue
        if semantics == "probability_vector" and row["probabilities"] is not None:
            scored.append(id)
            for label in labels:
                probability = exact(row["probabilities"][label])
                event = int(reference == label)
                brier += (probability - event) ** 2
                entries.append((label, probability, event))
        elif semantics == "chosen_label_confidence" and row["score"] is not None:
            scored.append(id)
            entries.append(
                ("chosen_label_correctness", exact(row["score"]), int(row["label"] == reference))
            )
    bins = []
    for label in labels if semantics == "probability_vector" else ["chosen_label_correctness"]:
        for index in range(10):
            selected = [
                (p, event)
                for key, p, event in entries
                if key == label
                and BINS[index] <= p
                and (p < BINS[index + 1] or index == 9 and p == 1)
            ]
            n = len(selected)
            bins.append(
                {
                    "label": label,
                    "lower": str(BINS[index]),
                    "upper": str(BINS[index + 1]),
                    "upper_inclusive": index == 9,
                    "count": n,
                    "mean_reported": statistic(
                        sum((p for p, _ in selected), Fraction()) / n if n else None
                    ),
                    "empirical_frequency": statistic(
                        Fraction(sum(event for _, event in selected), n) if n else None
                    ),
                }
            )
    return {
        "status": "eligible" if scored else "eligible but no scorable supplied scores",
        "semantics": semantics,
        "scored_ids": sorted(scored),
        "brier": statistic(brier / len(scored))
        if scored and semantics == "probability_vector"
        else None,
        "brier_definition": (
            "Unnormalized multiclass sum of squared class errors, "
            "averaged over scored reference items"
        ),
        "bins": bins,
        "score_coverage": measure(len(scored), len(references)),
        "test_score_coverage": measure(len(scored), total_test),
    }


def evaluate(manifest_path: Path, output: Path | None = None) -> dict:
    manifest, data, hashes = load(manifest_path, output)
    items, human, outputs = validate_tables(manifest, data)
    panel, labels = manifest["panel"], manifest["labels"]
    test_ids = sorted(
        id for id, item in items.items() if item["split"] == "test" and item["eligible"]
    )
    require(test_ids, "No eligible held-out test items")
    complete = {}
    excluded = []
    for id in test_ids:
        missing = [reviewer for reviewer in panel if reviewer not in human[id]]
        abstained = [
            reviewer
            for reviewer in panel
            if reviewer in human[id] and human[id][reviewer]["label"] is None
        ]
        if missing or abstained:
            excluded.append(
                {"item_id": id, "missing_reviewers": missing, "abstaining_reviewers": abstained}
            )
        else:
            complete[id] = tuple(labels.index(human[id][reviewer]["label"]) for reviewer in panel)
    point = agreement(list(complete.values()), len(labels), len(panel))
    boot = manifest["protocol"]["bootstrap"]
    interval = bootstrap(
        complete,
        {id: items[id]["group_id"] for id in complete},
        len(labels),
        len(panel),
        boot["seed"],
        boot["unit"],
    )
    interval.pop("exact_values")
    coverage = Fraction(len(complete), len(test_ids))
    passed = gate_passes(point["kappa"], interval["interval"], coverage)
    gate_input = {
        "protocol": manifest["protocol"],
        "task": manifest["task"],
        "labels": labels,
        "panel": panel,
        "splits": manifest["splits"],
        "items_digest": hashes["items"],
        "human_labels_digest": hashes["human_labels"],
    }
    agreement_report = {
        "statistic": "Cohen" if len(panel) == 2 else "Fleiss",
        "complete_ids": sorted(complete),
        "excluded_panels": excluded,
        "observed": statistic(point["observed"]),
        "chance": statistic(point["chance"]),
        "kappa": statistic(point["kappa"]),
        "reviewer_counts": {
            reviewer: dict(zip(labels, point["counts"][r], strict=True))
            for r, reviewer in enumerate(panel)
        },
        "coverage": measure(len(complete), len(test_ids)),
        "bootstrap": interval,
        "passed": passed,
        "thresholds": {"lower_95_bound_binary64": 0.60, "minimum_complete_coverage_exact": "4/5"},
    }
    class_coverage = {}
    for label in labels:
        observed = [
            id for id in test_ids if any(row["label"] == label for row in human[id].values())
        ]
        class_coverage[label] = {
            "denominator_definition": (
                "Items with at least one human label in this class; classes may overlap"
            ),
            "coverage": measure(sum(id in complete for id in observed), len(observed)),
            "observed_ids": observed,
        }
    agreement_report["observed_class_coverage"] = class_coverage
    agreement_report["refusal_reasons"] = [
        reason
        for condition, reason in [
            (point["kappa"] is None, "Kappa is undefined"),
            (interval["interval"] is None, "The bootstrap interval is unavailable or undefined"),
            (
                interval["interval"] is not None and interval["interval"][0] < 0.60,
                "Lower 95% bound is below 0.60",
            ),
            (coverage < Fraction(4, 5), "Complete-panel coverage is below 80%"),
        ]
        if condition
    ]
    gate_digest = digest({"inputs": gate_input, "agreement": agreement_report})
    references = resolve_reference(
        manifest, items, human, data["adjudications"], passed, gate_digest
    )
    reference = {id: references[id] for id in test_ids if id in references}
    unresolved = [id for id in test_ids if id not in references]
    reports = []
    baseline = None
    if passed:
        training = [
            references[id]
            for id, item in items.items()
            if item["split"] == "train" and item["eligible"] and id in references
        ]
        counts = Counter(training)
        majority = max(labels, key=lambda label: counts[label]) if training else None
        baseline = {
            "status": "available"
            if majority is not None
            else "unavailable: no resolved training labels",
            "label": majority,
            "training_counts": {label: counts[label] for label in labels},
            "tie_rule": "Frozen vocabulary order",
            "metrics": metrics(labels, reference, {id: majority for id in reference})
            if majority is not None and reference
            else None,
        }
        for tool in manifest["tools"]:
            own = outputs[tool["id"]]
            predictions = {id: own[id]["label"] for id in reference if id in own}
            reports.append(
                {
                    "id": tool["id"],
                    "version": tool["version"],
                    "model_card_digest": tool["model_card"]["sha256"],
                    "metrics": metrics(labels, reference, predictions) if reference else None,
                    "metrics_status": "available"
                    if reference
                    else "unavailable: no scorable reference",
                    "calibration": calibration(tool, labels, reference, own, len(test_ids)),
                    "eligible_test_prediction_coverage": measure(
                        sum(id in own and own[id]["label"] is not None for id in test_ids),
                        len(test_ids),
                    ),
                    "missing_output_ids": [id for id in test_ids if id not in own],
                    "unscorable_test_ids": unresolved,
                    "unused_non_test_output_ids": sorted(
                        id for id in own if items[id]["split"] != "test"
                    ),
                }
            )
    report = {
        "version": VERSION,
        "algorithm": ALGORITHM,
        "status": ("reference accepted" if reference else "reference unresolved")
        if passed
        else "reference refused",
        "input_digests": hashes,
        "raw_human_labels": data["human_labels"],
        "manifest": manifest,
        "agreement": agreement_report,
        "gate_digest": gate_digest,
        "reference": {
            "labels": reference,
            "unresolved_ids": unresolved,
            "coverage": measure(len(reference), len(test_ids)),
            "complete_panel_reference_coverage": measure(
                sum(id in complete for id in reference), len(complete)
            ),
        },
        "eligibility": {
            "test_ids": test_ids,
            "excluded": [
                {"item_id": id, "reason": item["exclusion_reason"]}
                for id, item in sorted(items.items())
                if not item["eligible"]
            ],
        },
        "tools": reports if passed else None,
        "majority_baseline": baseline,
        "arithmetic": {
            "exact": (
                "counts, agreement/kappa, coverage, confusion metrics "
                "and decimal calibration fractions"
            ),
            "binary64": (
                "display approximations and linear bootstrap percentile endpoints; "
                "gate lower-bound comparison"
            ),
            "probability_sum_tolerance": "0; no renormalization",
            "bins": "[0,.1), ..., [.9,1]",
        },
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "platform": platform.system() + " " + platform.machine(),
        },
        "script_digest": sha(Path(__file__).read_bytes()),
        "limitations": [
            "Human-reviewed task labels are not objective truth or outcome probabilities.",
            (
                "Agreement does not prove independence, transfer to another population "
                "or causal validity."
            ),
            "Blind review, freeze and timestamps are supplied local attestations, not signatures.",
            "Macro summaries are undefined if any frozen-vocabulary component is undefined.",
            (
                "Only complete fixed panels contribute to the agreement interval; "
                "coverage remains separate."
            ),
        ],
        "digest": "",
    }
    report["digest"] = digest({key: value for key, value in report.items() if key != "digest"})
    return report


def csv_text(report: dict) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["table", "tool_or_reviewer", "reference_label", "predicted_label", "count"])

    def safe(value):
        if isinstance(value, str) and (
            value.startswith(("\t", "\r", "\n"))
            or value.lstrip("\ufeff \t\r\n\v\f").startswith(("=", "+", "-", "@"))
        ):
            return "'" + value
        return value

    labels = report["manifest"]["labels"]
    for reviewer in report["manifest"]["panel"]:
        for label in labels:
            writer.writerow(
                [
                    "human_label_marginal",
                    safe(reviewer),
                    safe(label),
                    "",
                    report["agreement"]["reviewer_counts"][reviewer][label],
                ]
            )
    for tool in report["tools"] or []:
        if tool["metrics"] is None:
            continue
        for reference in labels:
            for predicted in [*labels, "__abstention__"]:
                writer.writerow(
                    [
                        "tool_confusion",
                        safe(tool["id"]),
                        safe(reference),
                        safe(predicted),
                        tool["metrics"]["confusion"][reference][predicted],
                    ]
                )
    return buffer.getvalue()


def html_text(report: dict) -> str:
    def escaped(value):
        return html.escape(str(value), quote=True)

    gate = report["agreement"]
    parts = [
        """<!doctype html><html lang="en"><meta charset="utf-8">
<title>Classifier agreement benchmark</title><style>
body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem}
table{border-collapse:collapse;margin:1rem 0}
th,td{padding:.5rem;border:1px solid #ccc;text-align:left}
pre{white-space:pre-wrap;overflow-wrap:anywhere}.gate{padding:1rem;border:3px solid #444}
h2{margin-top:2rem}</style><main><h1>Classifier agreement benchmark</h1>""",
        '<section class="gate"><h2>'
        + escaped(report["status"])
        + "</h2><p>Human agreement: "
        + escaped(gate["statistic"])
        + " kappa "
        + escaped(gate["kappa"])
        + "</p><p>95% bootstrap interval: "
        + escaped(gate["bootstrap"]["interval"])
        + " · complete-panel coverage: "
        + escaped(gate["coverage"])
        + (
            "</p><p>Frozen gate: lower bound ≥ 0.60 and coverage ≥ 80%. "
            "Every undefined replicate refuses the interval.</p></section>"
        ),
        (
            "<p>Human-reviewed task labels; agreement is not proof of truth or generalization. "
            "This report does not run a model or predict an outcome.</p>"
        ),
    ]
    for tool in report["tools"] or []:
        if tool["metrics"] is None:
            parts.append(
                "<h2>"
                + escaped(tool["id"])
                + "</h2><p>Metrics unavailable: no scorable reference.</p>"
            )
            continue
        parts.append(
            "<section><h2>"
            + escaped(tool["id"])
            + "</h2><p>"
            + escaped(tool["calibration"]["status"])
            + (
                "</p><table><caption>Full confusion counts, including abstentions</caption>"
                "<thead><tr><th>Reference</th>"
            )
            + "".join(
                "<th>" + escaped(label) + "</th>"
                for label in [*report["manifest"]["labels"], "__abstention__"]
            )
            + "</tr></thead><tbody>"
        )
        for label in report["manifest"]["labels"]:
            columns = tool["metrics"]["confusion"][label]
            parts.append(
                "<tr><th>"
                + escaped(label)
                + "</th>"
                + "".join(
                    "<td>" + str(count) + "</td>"
                    for count in (
                        columns[key] for key in [*report["manifest"]["labels"], "__abstention__"]
                    )
                )
                + "</tr>"
            )
        parts.append(
            (
                "</tbody></table><details><summary>Metrics, denominators "
                "and calibration bins</summary><pre>"
            )
            + escaped(json.dumps(tool, indent=2, default=_json_default))
            + "</pre></details></section>"
        )
    parts.append(
        "<h2>Reference coverage and unresolved items</h2><pre>"
        + escaped(json.dumps(report["reference"], indent=2, default=_json_default))
        + "</pre><h2>Arithmetic, baseline and provenance</h2><pre>"
        + escaped(
            json.dumps(
                {
                    key: report[key]
                    for key in (
                        "arithmetic",
                        "majority_baseline",
                        "input_digests",
                        "environment",
                        "limitations",
                        "digest",
                    )
                },
                indent=2,
                default=_json_default,
            )
        )
        + "</pre></main></html>\n"
    )
    return "".join(parts)


def write_report(report: dict, output: Path) -> None:
    # All validation and rendering finish before exclusive directory creation.
    documents = {
        "report.json": json.dumps(
            report,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            default=_json_default,
        )
        + "\n",
        "confusion.csv": csv_text(report),
        "report.html": html_text(report),
    }
    require(
        len(documents["report.json"].encode()) <= MAX_REPORT_BYTES,
        "Report would exceed the size the verifier reopens",
    )
    output.mkdir(parents=False, exist_ok=False)
    created = []
    try:
        for name, content in documents.items():
            with (output / name).open("x", encoding="utf-8", newline="") as handle:
                handle.write(content)
            created.append(output / name)
    except OSError:
        for file in created:
            file.unlink()
        output.rmdir()
        raise


def verify_report(path: Path) -> dict:
    document = json.loads(read(path, MAX_REPORT_BYTES), object_pairs_hook=_pairs)
    require(
        isinstance(document, dict)
        and type(document.get("version")) is int
        and document["version"] == VERSION
        and document.get("algorithm") == ALGORITHM,
        "Unsupported benchmark report version",
    )
    expected = digest({key: value for key, value in document.items() if key != "digest"})
    require(document.get("digest") == expected, "Report digest mismatch")
    if document["manifest"]["data_kind"] != "synthetic":
        require(not path.resolve().is_relative_to(ROOT), "Real reports are refused in the checkout")
    return document


def _object(properties: dict, optional: set[str] = frozenset()) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(set(properties) - set(optional)),
        "properties": properties,
    }


def schemas() -> dict[str, dict]:
    """Strict version-1 JSON Schemas (draft 2020-12) for the manifest and the sealed report.

    The schemas are a published structural contract; the script's own validation remains the
    authority for cross-field rules (chronology, digests, split membership, frozen thresholds).
    """
    text_ = {"type": "string", "minLength": 1, "maxLength": 4000}
    digest_ = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    time_ = {"type": "string", "minLength": 1, "maxLength": 4000}
    ids = {"type": "array", "items": text_}
    file_ = _object({"path": text_, "sha256": digest_})
    manifest = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "classifier-agreement-manifest-v1.schema.json",
        "title": "Classifier agreement benchmark manifest, version 1",
        **_object(
            {
                "version": {"const": VERSION},
                "data_kind": {"enum": ["synthetic", "real", "public"]},
                "data_provenance": _object(
                    {
                        "description": text_,
                        "generation_seed": {"type": "integer", "minimum": 0},
                        "source": text_,
                        "licence": text_,
                        "snapshot_sha256": digest_,
                    },
                    {"generation_seed", "source", "licence", "snapshot_sha256"},
                ),
                "task": _object(
                    {
                        name: text_
                        for name in (
                            "id",
                            "version",
                            "instructions",
                            "unit",
                            "population",
                            "observation_cutoff",
                            "eligibility",
                            "exclusions",
                        )
                    }
                ),
                "labels": {
                    "type": "array",
                    "items": {**text_, "not": {"const": "__abstention__"}},
                    "minItems": 2,
                    "maxItems": MAX_LABELS,
                    "uniqueItems": True,
                },
                "panel": {
                    "type": "array",
                    "items": text_,
                    "minItems": 2,
                    "maxItems": MAX_REVIEWERS,
                    "uniqueItems": True,
                },
                "splits": _object(
                    {"train": ids, "development": ids, "test": {**ids, "minItems": 1}}
                ),
                "protocol": _object(
                    {
                        "frozen_at": time_,
                        "gate_confirmed_at": time_,
                        "outputs_unblinded_at": time_,
                        "independent_blind_reviews": {"const": True},
                        "blind_adjudication": {"const": True},
                        "reference_policy": {"const": "unanimous-or-post-gate-adjudication.v1"},
                        "confidence": {"const": "0.95"},
                        "lower_kappa": {"const": "0.60"},
                        "minimum_coverage": {"const": "0.80"},
                        "bootstrap": _object(
                            {
                                "replicates": {"const": REPLICATES},
                                "seed": {"type": "integer", "minimum": 0},
                                "unit": {"enum": ["item", "group"]},
                                "algorithm": {"const": BOOTSTRAP_ALGORITHM},
                                "quantile": {"const": "linear.v1"},
                            }
                        ),
                    }
                ),
                "files": _object(
                    {
                        name: file_
                        for name in ("items", "human_labels", "tool_outputs", "adjudications")
                    }
                ),
                "tools": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": MAX_TOOLS,
                    "items": _object(
                        {
                            "id": text_,
                            "version": text_,
                            "task_version": text_,
                            "model_card": file_,
                            "score_semantics": {
                                "enum": [
                                    "none",
                                    "arbitrary_score",
                                    "chosen_label_confidence",
                                    "probability_vector",
                                ]
                            },
                            "score_bounds": {
                                "anyOf": [
                                    {"type": "null"},
                                    {
                                        "type": "array",
                                        "items": {"type": "number"},
                                        "minItems": 2,
                                        "maxItems": 2,
                                    },
                                ]
                            },
                        }
                    ),
                },
            }
        ),
    }
    nullable = {"anyOf": [{"type": "object"}, {"type": "null"}]}
    report = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "classifier-agreement-report-v1.schema.json",
        "title": "Classifier agreement benchmark sealed report, version 1",
        **_object(
            {
                "version": {"const": VERSION},
                "algorithm": {"const": ALGORITHM},
                "status": {
                    "enum": ["reference accepted", "reference unresolved", "reference refused"]
                },
                "input_digests": {
                    "type": "object",
                    "required": [
                        "manifest",
                        "items",
                        "human_labels",
                        "tool_outputs",
                        "adjudications",
                    ],
                    "additionalProperties": digest_,
                },
                "raw_human_labels": {"type": "array", "items": {"type": "object"}},
                "manifest": {"$ref": "classifier-agreement-manifest-v1.schema.json"},
                "agreement": {
                    "type": "object",
                    "required": [
                        "statistic",
                        "kappa",
                        "coverage",
                        "bootstrap",
                        "passed",
                        "refusal_reasons",
                    ],
                },
                "gate_digest": digest_,
                "reference": _object(
                    {
                        "labels": {"type": "object", "additionalProperties": text_},
                        "unresolved_ids": ids,
                        "coverage": {"type": "object"},
                        "complete_panel_reference_coverage": {"type": "object"},
                    }
                ),
                "eligibility": _object(
                    {"test_ids": ids, "excluded": {"type": "array", "items": {"type": "object"}}}
                ),
                "tools": {
                    "anyOf": [{"type": "array", "items": {"type": "object"}}, {"type": "null"}]
                },
                "majority_baseline": nullable,
                "arithmetic": {"type": "object"},
                "environment": {"type": "object"},
                "script_digest": digest_,
                "limitations": {"type": "array", "items": text_},
                "digest": digest_,
            }
        ),
    }
    return {
        "classifier-agreement-manifest-v1.schema.json": manifest,
        "classifier-agreement-report-v1.schema.json": report,
    }


def schema_text(schema: dict) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    parser.add_argument(
        "--write-schemas", type=Path, help="Write the version-1 JSON Schemas to this directory"
    )
    args = parser.parse_args()
    try:
        if args.write_schemas is not None:
            for name, schema in schemas().items():
                (args.write_schemas / name).write_text(schema_text(schema), encoding="utf-8")
            print("Version-1 manifest and report schemas written")
            return 0
        if args.verify_report is not None:
            require(
                args.manifest is None and args.output is None, "Choose verification or evaluation"
            )
            verify_report(args.verify_report)
            print("Sealed version-1 report digest verified; provenance is not a signature")
            return 0
        require(
            args.manifest is not None and args.output is not None,
            "Evaluation requires --manifest and --output",
        )
        report = evaluate(args.manifest, args.output)
        write_report(report, args.output)
    except (BenchmarkError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(report["status"] + "; local JSON/CSV/HTML written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
