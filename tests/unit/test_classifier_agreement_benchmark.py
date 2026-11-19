"""Independent checks of the standalone classifier agreement benchmark script.

The oracles below never import the application or reuse the script's arithmetic. They re-read the
invented input tables with the standard library, recompute every exact count, kappa, reference,
confusion and calibration value with `Fraction`, and replay the seeded bootstrap draws directly
from the documented PCG64 stream. Engine-to-engine claims (replay, chunking) use exact equality;
the binary64 percentile endpoints are compared with exact rational endpoints under a bound
derived below, never a fixed tolerance.
"""

import hashlib
import importlib.util
import itertools
import json
import random
import re
from collections import Counter
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "classifier_agreement_benchmark.py"
FIXTURE = ROOT / "examples" / "classifier_benchmark" / "synthetic"
MANIFEST = FIXTURE / "manifest.json"
REFUSED = FIXTURE / "refused" / "manifest.json"

_spec = importlib.util.spec_from_file_location("classifier_agreement_benchmark", SCRIPT)
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)

U = Fraction(1, 2**53)  # unit roundoff of binary64 round-to-nearest


# --- independent oracles ----------------------------------------------------------------------


def oracle_cohen(rows):
    n = len(rows)
    if not n:
        return None
    po = Fraction(sum(1 for a, b in rows if a == b), n)
    first, second = Counter(a for a, _ in rows), Counter(b for _, b in rows)
    pe = sum((Fraction(first[k], n) * Fraction(second[k], n) for k in first), Fraction())
    return None if pe == 1 else (po - pe) / (1 - pe)


def oracle_fleiss(rows):
    n, m = len(rows), len(rows[0])
    per_item = [
        Fraction(sum(c * c for c in Counter(row).values()) - m, m * (m - 1)) for row in rows
    ]
    p_bar = sum(per_item, Fraction()) / n
    totals = Counter(label for row in rows for label in row)
    pe = sum((Fraction(c, n * m) ** 2 for c in totals.values()), Fraction())
    return None if pe == 1 else (p_bar - pe) / (1 - pe)


def oracle_kappa(rows):
    return oracle_cohen(rows) if len(rows[0]) == 2 else oracle_fleiss(rows)


def load_tables(manifest_path):
    def parse(path):
        return json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)

    manifest = parse(manifest_path)
    tables = {key: parse(manifest_path.parent / d["path"]) for key, d in manifest["files"].items()}
    return manifest, tables


def oracle_inputs(manifest_path):
    manifest, tables = load_tables(manifest_path)
    panel, labels = manifest["panel"], manifest["labels"]
    items = {row["id"]: row for row in tables["items"]}
    human = {}
    for row in tables["human_labels"]:
        human.setdefault(row["item_id"], {})[row["reviewer"]] = row["label"]
    test_ids = sorted(i for i, r in items.items() if r["split"] == "test" and r["eligible"])
    complete = {
        i: tuple(human[i][r] for r in panel)
        for i in test_ids
        if all(human.get(i, {}).get(r) is not None for r in panel)
    }
    return manifest, tables, panel, labels, items, human, test_ids, complete


def oracle_references(manifest, tables, items, human, panel):
    refs = {}
    for i, row in items.items():
        values = [human.get(i, {}).get(r) for r in panel]
        if row["eligible"] and None not in values and len(set(values)) == 1:
            refs[i] = values[0]
    for row in tables["adjudications"]:
        refs.setdefault(row["item_id"], row["reference_label"])
    return refs


def oracle_confusion(labels, references, predictions):
    out = {}
    n = len(references)
    for label in labels:
        support = sum(1 for r in references.values() if r == label)
        predicted = sum(1 for i in references if predictions.get(i) == label)
        tp = sum(1 for i, r in references.items() if r == label and predictions.get(i) == label)
        out[label] = (tp, support, predicted)
    answered = sum(1 for i in references if predictions.get(i) is not None)
    correct = sum(1 for i, r in references.items() if predictions.get(i) == r)
    return out, Fraction(correct, n), Fraction(answered, n)


def exact_percentile(sorted_values, p):
    """Linear (type 7) percentile at exact position h = (R - 1) p."""
    h = (len(sorted_values) - 1) * p
    lo = int(h)
    frac = h - lo
    a = sorted_values[lo]
    b = sorted_values[min(lo + 1, len(sorted_values) - 1)]
    return a + (b - a) * frac, a, b


def percentile_bound(a, b, replicates, p):
    """Rigorous forward-error bound for numpy's binary64 linear percentile.

    Each value enters as float(v): |fl(v) - v| <= u|v|. The virtual index is computed as
    fl(fl(p)(R - 1)); with |fl(p) - p| <= u p and one rounded product its fractional weight t
    differs from the exact weight by at most dt = (R - 1) p (2u + u^2) + u (R - 1) p (1 + u)^2,
    the floor subtraction being exact. The interpolation fl(a + fl(fl(b - a) t)) or the mirrored
    form adds three further roundings, each at most u times a magnitude <= |a| + 2|b - a| + 2u.
    Summing, with generous constant factors that cover second-order terms:
        |result - exact| <= 2u(|a| + |b|) + dt |b - a| + dt * 2u(|a| + |b|)
                            + 4u(|a| + 2|b - a| + 1) .
    """
    span = abs(b - a)
    dt = (replicates - 1) * p * (3 * U + 4 * U * U)
    mags = abs(a) + abs(b)
    return 2 * U * mags + dt * span + dt * 2 * U * mags + 4 * U * (abs(a) + 2 * span + 1)


def oracle_bootstrap(panels, group_of, seed, replicates):
    """Independent replay: one draw call, kappa recomputed from the raw labels of each replicate."""
    units = sorted({group_of[i] for i in panels})
    members = {u: [panels[i] for i in sorted(panels) if group_of[i] == u] for u in units}
    draws = np.random.Generator(np.random.PCG64(seed)).integers(
        0, len(units), size=(replicates, len(units))
    )
    values, undefined = [], []
    for index, selection in enumerate(draws):
        rows = [row for k in selection for row in members[units[int(k)]]]
        value = oracle_kappa(rows)
        (undefined.append(index) if value is None else values.append(value))
    return values, undefined


# --- shared evaluations -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def passing():
    return bench.evaluate(MANIFEST)


@pytest.fixture(scope="module")
def refused():
    return bench.evaluate(REFUSED)


@pytest.fixture(scope="module")
def inputs():
    return oracle_inputs(MANIFEST)


# --- agreement statistics ---------------------------------------------------------------------


def test_cohen_and_fleiss_match_independent_oracles_on_random_panels():
    rng = random.Random(20261102)
    checked = 0
    for reviewers in (2, 3, 4, 5):
        for _ in range(60):
            labels = rng.randint(1, 4)
            rows = [
                tuple(rng.randrange(labels) for _ in range(reviewers))
                for _ in range(rng.randint(1, 25))
            ]
            assert bench.agreement(rows, labels, reviewers)["kappa"] == oracle_kappa(rows)
            checked += 1
    assert checked == 240


def test_kappa_is_invariant_to_item_order_label_renaming_and_reviewer_order():
    rng = random.Random(7)
    for reviewers in (2, 3):
        for _ in range(40):
            rows = [tuple(rng.randrange(3) for _ in range(reviewers)) for _ in range(12)]
            base = bench.agreement(rows, 3, reviewers)["kappa"]
            shuffled = rows[:]
            rng.shuffle(shuffled)
            renamed = [tuple((v + 1) % 3 for v in row) for row in rows]
            swapped = [tuple(reversed(row)) for row in rows]
            assert bench.agreement(shuffled, 3, reviewers)["kappa"] == base
            assert bench.agreement(renamed, 3, reviewers)["kappa"] == base
            assert bench.agreement(swapped, 3, reviewers)["kappa"] == base


@settings(max_examples=60, deadline=None)
@given(
    st.integers(2, 4).flatmap(
        lambda reviewers: st.lists(
            st.tuples(*[st.integers(0, 2)] * reviewers), min_size=1, max_size=30
        )
    )
)
def test_property_kappa_equals_oracle_for_any_fixed_panel(rows):
    assert bench.agreement(rows, 3, len(rows[0]))["kappa"] == oracle_kappa(rows)


@settings(max_examples=20, deadline=None)
@given(
    st.lists(st.tuples(st.integers(0, 1), st.integers(0, 1)), min_size=2, max_size=12),
    st.integers(0, 2**32),
    st.integers(1, 40),
)
def test_property_bootstrap_equals_independent_replay_for_any_chunking(rows, seed, batch):
    panels = {f"i{n:02}": row for n, row in enumerate(rows)}
    group_of = {i: f"g{int(i[1:]) // 2}" for i in panels}
    result = bench.bootstrap(panels, group_of, 2, 2, seed, "group", batch_size=batch, replicates=50)
    values, undefined = oracle_bootstrap(panels, group_of, seed, 50)
    assert result["exact_values"] == values
    assert result["undefined_indices"] == undefined
    assert (result["interval"] is None) == bool(undefined)


def test_constant_panels_have_undefined_kappa_not_zero():
    assert bench.agreement([(0, 0), (0, 0)], 2, 2)["kappa"] is None
    assert bench.agreement([(1, 1, 1)] * 3, 2, 3)["kappa"] is None


def test_gate_thresholds_compare_binary64_lower_bound_and_exact_coverage():
    assert bench.gate_passes(Fraction(1), [0.60, 0.9], Fraction(4, 5))
    assert not bench.gate_passes(Fraction(1), [0.5999999999999999, 0.9], Fraction(4, 5))
    assert not bench.gate_passes(Fraction(1), [0.7, 0.9], Fraction(4, 5) - Fraction(1, 10**12))
    assert not bench.gate_passes(None, [0.7, 0.9], Fraction(1))
    assert not bench.gate_passes(Fraction(1), None, Fraction(1))


# --- bootstrap --------------------------------------------------------------------------------


def test_full_bootstrap_matches_independent_replay_and_bounded_endpoints(inputs):
    manifest, tables, panel, labels, items, human, test_ids, complete = inputs
    encoded = {i: tuple(labels.index(v) for v in row) for i, row in complete.items()}
    group_of = {i: items[i]["group_id"] for i in complete}
    seed = manifest["protocol"]["bootstrap"]["seed"]
    replicates = manifest["protocol"]["bootstrap"]["replicates"]
    values, undefined = oracle_bootstrap(encoded, group_of, seed, replicates)
    result = bench.bootstrap(encoded, group_of, len(labels), len(panel), seed, "group")
    assert undefined == [] and result["undefined"] == 0
    assert result["exact_values"] == values
    assert result["attempted"] == replicates == 10_000
    ordered = sorted(values)
    for p, endpoint in zip((Fraction(1, 40), Fraction(39, 40)), result["interval"], strict=True):
        exact, a, b = exact_percentile(ordered, p)
        assert abs(Fraction(endpoint) - exact) <= percentile_bound(a, b, replicates, p)
    assert result["interval"] == [0.7592592592592593, 0.9444444444444444]


def test_bootstrap_chunking_and_replay_are_exactly_identical():
    rng = random.Random(3)
    panels = {f"i{n:02}": (rng.randrange(2), rng.randrange(2)) for n in range(30)}
    group_of = {i: f"g{int(i[1:]) // 3}" for i in panels}
    runs = [
        bench.bootstrap(panels, group_of, 2, 2, 11, "group", batch_size=size, replicates=300)
        for size in (1, 7, 32, 300, 1000)
    ]
    first = runs[0]
    for run in runs[1:]:
        assert run["replicates_digest"] == first["replicates_digest"]
        assert run["exact_values"] == first["exact_values"]
        assert run["undefined_indices"] == first["undefined_indices"]
        assert run["interval"] == first["interval"]


def test_tiny_enumerated_bootstrap_support_and_undefined_refusal():
    # Three single-item units; any resample drawing one unit three times is constant (pe = 1).
    panels = {"a": (0, 0), "b": (1, 1), "c": (0, 1)}
    group_of = {i: i for i in panels}
    support = {
        oracle_kappa([panels[k] for k in combo])
        for combo in itertools.product(sorted(panels), repeat=3)
    }
    result = bench.bootstrap(panels, group_of, 2, 2, 5, "item", replicates=200)
    values, undefined = oracle_bootstrap(panels, group_of, 5, 200)
    assert result["exact_values"] == values
    assert result["undefined_indices"] == undefined
    assert undefined  # constant resamples really occur in this draw stream
    assert set(result["exact_values"]) <= support - {None}
    assert result["interval"] is None
    assert result["status"] == "refused"
    assert result["undefined"] == len(undefined)


def test_bootstrap_resamples_whole_groups_jointly():
    panels = {"a1": (0, 0), "a2": (1, 1), "b1": (0, 1), "b2": (1, 0)}
    group_of = {"a1": "A", "a2": "A", "b1": "B", "b2": "B"}
    result = bench.bootstrap(panels, group_of, 2, 2, 9, "group", replicates=64)
    values, undefined = oracle_bootstrap(panels, group_of, 9, 64)
    assert result["exact_values"] == values and result["undefined_indices"] == undefined
    for entry in result["trace"]:
        assert set(entry["unit_ids"]) <= {"A", "B"}
    # Group A alone has kappa 1, group B alone -1, both together 0: nothing else is possible.
    assert set(values) <= {Fraction(1), Fraction(-1), Fraction(0)}


# --- full fixture against the oracles ---------------------------------------------------------


def test_passing_fixture_agreement_and_coverage_match_oracles(passing, inputs):
    manifest, tables, panel, labels, items, human, test_ids, complete = inputs
    agreement = passing["agreement"]
    assert passing["status"] == "reference accepted"
    assert agreement["passed"] is True
    assert passing["eligibility"]["test_ids"] == test_ids
    assert len(test_ids) == 120
    assert agreement["complete_ids"] == sorted(complete)
    expected = oracle_kappa(list(complete.values()))
    assert Fraction(agreement["kappa"]["exact"]) == expected == Fraction(23, 27)
    assert Fraction(agreement["coverage"]["exact"]) == Fraction(len(complete), len(test_ids))
    assert Fraction(agreement["coverage"]["exact"]) == Fraction(9, 10)
    assert {e["item_id"] for e in agreement["excluded_panels"]} == set(test_ids) - set(complete)
    encoded = {i: tuple(labels.index(v) for v in row) for i, row in complete.items()}
    boot = manifest["protocol"]["bootstrap"]
    replay = bench.bootstrap(
        encoded, {i: items[i]["group_id"] for i in complete}, 2, 2, boot["seed"], "group"
    )
    assert agreement["bootstrap"]["replicates_digest"] == replay["replicates_digest"]
    assert agreement["bootstrap"]["interval"] == replay["interval"]


def test_input_digests_cover_the_manifest_every_table_and_every_card(passing):
    manifest, _ = load_tables(MANIFEST)
    expected = {"manifest": hashlib.sha256(MANIFEST.read_bytes()).hexdigest()}
    for key, declaration in manifest["files"].items():
        expected[key] = hashlib.sha256((FIXTURE / declaration["path"]).read_bytes()).hexdigest()
    for tool in manifest["tools"]:
        path = FIXTURE / tool["model_card"]["path"]
        expected["card:" + tool["id"]] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert passing["input_digests"] == expected


def test_reference_and_majority_baseline_use_only_permitted_labels(passing, inputs):
    manifest, tables, panel, labels, items, human, test_ids, complete = inputs
    refs = oracle_references(manifest, tables, items, human, panel)
    test_refs = {i: refs[i] for i in test_ids if i in refs}
    assert passing["reference"]["labels"] == test_refs
    assert len(test_refs) == 106
    training = Counter(
        refs[i] for i, r in items.items() if r["split"] == "train" and r["eligible"] and i in refs
    )
    baseline = passing["majority_baseline"]
    assert baseline["training_counts"] == {label: training[label] for label in labels}
    assert baseline["training_counts"] == {"alpha": 4, "beta": 16}
    assert baseline["label"] == "beta"


def test_tool_confusion_metrics_match_oracle_including_abstentions(passing, inputs):
    manifest, tables, panel, labels, items, human, test_ids, complete = inputs
    refs = passing["reference"]["labels"]
    outputs = {}
    for row in tables["tool_outputs"]:
        outputs.setdefault(row["tool_id"], {})[row["item_id"]] = row
    assert [t["id"] for t in passing["tools"]] == [t["id"] for t in manifest["tools"]]
    abstentions_seen = 0
    for tool in passing["tools"]:
        predictions = {i: outputs[tool["id"]][i]["label"] for i in refs if i in outputs[tool["id"]]}
        classes, accuracy, coverage = oracle_confusion(labels, refs, predictions)
        metrics = tool["metrics"]
        assert metrics["n"] == len(refs)
        assert Fraction(metrics["accuracy"]["exact"]) == accuracy
        assert Fraction(metrics["coverage"]["exact"]) == coverage
        abstentions_seen += sum(metrics["confusion"][label]["__abstention__"] for label in labels)
        for label, (tp, support, predicted) in classes.items():
            row = metrics["classes"][label]
            assert (row["true_positive"], row["support"], row["predicted"]) == (
                tp,
                support,
                predicted,
            )
            assert row["recall"]["exact"] == (str(Fraction(tp, support)) if support else None)
            assert row["precision"]["exact"] == (
                str(Fraction(tp, predicted)) if predicted else None
            )
        assert tool["unused_non_test_output_ids"] == sorted(
            i for i in outputs[tool["id"]] if items[i]["split"] != "test"
        )
    assert abstentions_seen > 0  # the fixture really exercises abstentions in recall


def test_calibration_matches_oracle_brier_and_unweighted_bins(passing, inputs):
    manifest, tables, panel, labels, items, human, test_ids, complete = inputs
    refs = passing["reference"]["labels"]
    outputs = {}
    for row in tables["tool_outputs"]:
        outputs.setdefault(row["tool_id"], {})[row["item_id"]] = row
    semantics = {t["id"]: t["score_semantics"] for t in manifest["tools"]}
    checked = set()
    for tool in passing["tools"]:
        own, calibration = outputs[tool["id"]], tool["calibration"]
        kind = semantics[tool["id"]]
        entries = []
        if kind == "probability_vector":
            scored = [i for i in refs if i in own and own[i]["probabilities"] is not None]
            brier = Fraction()
            for i in scored:
                for label in labels:
                    p = Fraction(own[i]["probabilities"][label])
                    brier += (p - (refs[i] == label)) ** 2
                    entries.append((label, p, refs[i] == label))
            assert Fraction(calibration["brier"]["exact"]) == brier / len(scored)
            keys = labels
        elif kind == "chosen_label_confidence":
            scored = [i for i in refs if i in own and own[i]["score"] is not None]
            for i in scored:
                entries.append(
                    (
                        "chosen_label_correctness",
                        Fraction(own[i]["score"]),
                        own[i]["label"] == refs[i],
                    )
                )
            assert calibration["brier"] is None
            keys = ["chosen_label_correctness"]
        else:
            assert calibration["status"] == "not calibration-eligible"
            assert calibration["bins"] == []
            checked.add(kind)
            continue
        assert calibration["scored_ids"] == sorted(scored)
        bins = iter(calibration["bins"])
        for key in keys:
            for index in range(10):
                lower, upper = Fraction(index, 10), Fraction(index + 1, 10)
                selected = [
                    (p, e)
                    for k, p, e in entries
                    if k == key and lower <= p and (p < upper or (index == 9 and p == 1))
                ]
                row = next(bins)
                assert (row["label"], Fraction(row["lower"]), row["count"]) == (
                    key,
                    lower,
                    len(selected),
                )
                frequency = (
                    Fraction(sum(e for _, e in selected), len(selected)) if selected else None
                )
                mean = (
                    sum((p for p, _ in selected), Fraction()) / len(selected) if selected else None
                )
                assert row["empirical_frequency"]["exact"] == (
                    None if frequency is None else str(frequency)
                )
                assert row["mean_reported"]["exact"] == (None if mean is None else str(mean))
        assert next(bins, None) is None
        checked.add(kind)
    assert checked == {"probability_vector", "chosen_label_confidence", "arbitrary_score"}


# --- refusal, reports and replay --------------------------------------------------------------


def test_refused_human_gate_stops_before_tools_and_baseline(refused):
    assert refused["status"] == "reference refused"
    assert refused["agreement"]["passed"] is False
    assert Fraction(refused["agreement"]["kappa"]["exact"]) == 0
    assert refused["tools"] is None
    assert refused["majority_baseline"] is None
    assert "Lower 95% bound is below 0.60" in refused["agreement"]["refusal_reasons"]


def test_report_replays_byte_for_byte_and_refuses_overwrite(passing, tmp_path):
    again = bench.evaluate(MANIFEST)
    assert bench.canonical(again) == bench.canonical(passing)
    out = tmp_path / "report"
    bench.write_report(passing, out)
    assert sorted(p.name for p in out.iterdir()) == ["confusion.csv", "report.html", "report.json"]
    assert bench.verify_report(out / "report.json")["digest"] == passing["digest"]
    with pytest.raises(FileExistsError):
        bench.write_report(passing, out)


def test_unknown_report_version_and_tampering_are_refused(passing, tmp_path):
    out = tmp_path / "report"
    bench.write_report(passing, out)
    document = json.loads((out / "report.json").read_text())
    for change in ({"version": 2}, {"algorithm": "classifier-agreement.v2"}):
        changed = {**document, **change}
        changed["digest"] = bench.digest({k: v for k, v in changed.items() if k != "digest"})
        path = tmp_path / f"changed-{len(change)}-{next(iter(change))}.json"
        path.write_text(json.dumps(changed))
        with pytest.raises(bench.BenchmarkError, match="Unsupported"):
            bench.verify_report(path)
    tampered = {**document, "status": "reference accepted (edited)"}
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(tampered))
    with pytest.raises(bench.BenchmarkError, match="digest mismatch"):
        bench.verify_report(path)


def test_manifest_with_unknown_version_or_changed_input_is_refused(tmp_path):
    for name in [p.name for p in FIXTURE.iterdir() if p.is_file()]:
        (tmp_path / name).write_bytes((FIXTURE / name).read_bytes())
    manifest = json.loads(MANIFEST.read_text())
    (tmp_path / "manifest.json").write_text(json.dumps({**manifest, "version": 2}))
    with pytest.raises(bench.BenchmarkError):
        bench.evaluate(tmp_path / "manifest.json")
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "items.json").write_text((FIXTURE / "items.json").read_text() + "\n")
    with pytest.raises(bench.BenchmarkError, match="Input digest mismatch"):
        bench.evaluate(tmp_path / "manifest.json")


def test_html_and_csv_escape_supplied_text(passing):
    report = json.loads(json.dumps(passing, default=str))
    report["status"] = "<script>x</script>"
    report["tools"][0]["id"] = "=HYPERLINK(1)"
    page = bench.html_text(report)
    assert "<script>x" not in page and "&lt;script&gt;x" in page
    rows = bench.csv_text(report).splitlines()
    assert any("HYPERLINK" in row for row in rows)
    assert not any(cell.startswith(("=", "+", "-", "@")) for row in rows for cell in row.split(","))


# --- published schemas ------------------------------------------------------------------------

SCHEMAS = ROOT / "docs" / "schemas"


def conforms(value, schema, registry):
    """Independent subset validator for the keywords these two schemas use."""
    if "$ref" in schema:
        return conforms(value, registry[schema["$ref"]], registry)
    if "const" in schema and (value != schema["const"] or type(value) is not type(schema["const"])):
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if "anyOf" in schema and not any(conforms(value, s, registry) for s in schema["anyOf"]):
        return False
    if "not" in schema and conforms(value, schema["not"], registry):
        return False
    kinds = {
        "object": dict,
        "array": list,
        "string": str,
        "null": type(None),
        "boolean": bool,
    }
    kind = schema.get("type")
    if kind == "integer" and type(value) is not int:
        return False
    if kind == "number" and not (type(value) in (int, float) or isinstance(value, Decimal)):
        return False
    if kind in kinds and not isinstance(value, kinds[kind]):
        return False
    if isinstance(value, str):
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 10**9):
            return False
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            return False
    if isinstance(value, int) and "minimum" in schema and value < schema["minimum"]:
        return False
    if isinstance(value, list):
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 10**9):
            return False
        if schema.get("uniqueItems") and len({json.dumps(v) for v in value}) != len(value):
            return False
        if "items" in schema and not all(conforms(v, schema["items"], registry) for v in value):
            return False
    if isinstance(value, dict) and kind == "object":
        if not set(schema.get("required", [])) <= set(value):
            return False
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties:
                if not conforms(item, properties[key], registry):
                    return False
            elif extra is False or (
                isinstance(extra, dict) and not conforms(item, extra, registry)
            ):
                return False
    return True


@pytest.fixture(scope="module")
def registry():
    return {
        name: json.loads((SCHEMAS / name).read_text())
        for name in (
            "classifier-agreement-manifest-v1.schema.json",
            "classifier-agreement-report-v1.schema.json",
        )
    }


def test_committed_schemas_are_exactly_the_script_schemas(registry):
    for name, schema in bench.schemas().items():
        assert (SCHEMAS / name).read_text() == bench.schema_text(schema)


def test_fixture_manifests_and_sealed_reports_round_trip_through_the_schemas(
    registry, passing, refused, tmp_path
):
    manifest_schema = registry["classifier-agreement-manifest-v1.schema.json"]
    report_schema = registry["classifier-agreement-report-v1.schema.json"]
    for path in (MANIFEST, REFUSED):
        assert conforms(json.loads(path.read_text()), manifest_schema, registry)
    for name, report in (("pass", passing), ("refused", refused)):
        out = tmp_path / name
        bench.write_report(report, out)
        reopened = json.loads((out / "report.json").read_text())
        assert conforms(reopened, report_schema, registry)
        assert bench.verify_report(out / "report.json")["digest"] == report["digest"]


def test_schemas_refuse_unknown_versions_fields_and_reserved_labels(registry):
    schema = registry["classifier-agreement-manifest-v1.schema.json"]
    manifest = json.loads(MANIFEST.read_text())
    assert not conforms({**manifest, "version": 2}, schema, registry)
    assert not conforms({**manifest, "version": True}, schema, registry)
    assert not conforms({**manifest, "unexpected": 1}, schema, registry)
    assert not conforms({**manifest, "labels": ["alpha", "__abstention__"]}, schema, registry)
    report_schema = registry["classifier-agreement-report-v1.schema.json"]
    assert not conforms({"version": 2}, report_schema, registry)


# --- boundary audit ---------------------------------------------------------------------------


def copy_fixture(tmp_path, change=None):
    for path in FIXTURE.iterdir():
        if path.is_file():
            (tmp_path / path.name).write_bytes(path.read_bytes())
    manifest = json.loads(MANIFEST.read_text())
    if change:
        change(manifest)
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path / "manifest.json"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda m: m.update(version="1"), "Unsupported benchmark version"),
        (lambda m: m.update(labels=["alpha", "alpha"]), "Unique explicit"),
        (lambda m: m.update(labels=["alpha", "__abstention__"]), "Reserved abstention"),
        (lambda m: m["protocol"]["bootstrap"].update(seed=1.5), "Integer outside"),
        (lambda m: m["protocol"]["bootstrap"].update(seed=True), "Integer outside"),
        (lambda m: m["protocol"]["bootstrap"].update(replicates=9999), "Integer outside"),
        (lambda m: m["protocol"].update(lower_kappa="0.50"), "thresholds are frozen"),
        (lambda m: m["protocol"].update(independent_blind_reviews=False), "blind review"),
        (
            lambda m: m["protocol"].update(gate_confirmed_at="2025-01-01T00:00:00Z"),
            "chronology",
        ),
        (lambda m: m["protocol"].update(frozen_at="2026-01-01T00:00:00"), "timezone"),
        (lambda m: m["files"]["items"].update(sha256="ABC"), "SHA-256"),
        (lambda m: m["splits"]["train"].append(m["splits"]["test"][0]), "disjoint"),
        (lambda m: m.update(data_kind="public"), "Real inputs are refused inside"),
    ],
)
def test_malformed_or_out_of_protocol_manifests_are_refused_truthfully(tmp_path, change, reason):
    path = copy_fixture(tmp_path, change)
    if "inside" not in reason:
        with pytest.raises(bench.BenchmarkError, match=reason):
            bench.evaluate(path)
    else:
        # A copy outside the checkout is allowed through the location rule, so prove the rule on
        # the in-checkout fixture itself by loading it as a declared public dataset.
        manifest = json.loads(MANIFEST.read_text())
        manifest["data_kind"] = "public"
        inside = FIXTURE / "public-refusal-probe.json"
        assert not inside.exists()
        inside.write_text(json.dumps(manifest))
        try:
            with pytest.raises(bench.BenchmarkError, match=reason):
                bench.evaluate(inside)
        finally:
            inside.unlink()


def test_public_data_needs_source_licence_and_snapshot_digest(tmp_path):
    def public(m, snapshot):
        m["data_kind"] = "public"
        m["data_provenance"] = {
            "description": "Declared local snapshot",
            "source": "A public archive",
            "licence": "Open licence",
            "snapshot_sha256": snapshot,
        }

    with pytest.raises(bench.BenchmarkError, match="SHA-256"):
        bench.evaluate(copy_fixture(tmp_path, lambda m: public(m, "not-a-digest")))
    report = bench.evaluate(copy_fixture(tmp_path, lambda m: public(m, "0" * 64)))
    assert report["status"] == "reference accepted"


def test_real_inputs_reached_through_a_symlink_into_the_checkout_are_refused(tmp_path):
    path = copy_fixture(tmp_path, lambda m: m.update(data_kind="real"))
    (tmp_path / "items.json").unlink()
    (tmp_path / "items.json").symlink_to(FIXTURE / "items.json")
    with pytest.raises(bench.BenchmarkError, match="cannot resolve inside the checkout"):
        bench.evaluate(path)
    with pytest.raises(bench.BenchmarkError, match="Real reports are refused"):
        bench.evaluate(path, ROOT / "never-created-report")
    assert not (ROOT / "never-created-report").exists()


def test_oversized_report_is_refused_before_any_file_is_written(passing, tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "MAX_REPORT_BYTES", 1000)
    with pytest.raises(bench.BenchmarkError, match="exceed"):
        bench.write_report(passing, tmp_path / "report")
    assert not (tmp_path / "report").exists()


def test_reference_coverage_and_refusal_reasons_are_exact(passing, refused, inputs):
    manifest, tables, panel, labels, items, human, test_ids, complete = inputs
    refs = passing["reference"]["labels"]
    assert Fraction(passing["reference"]["coverage"]["exact"]) == Fraction(len(refs), 120)
    in_complete = sum(1 for i in refs if i in complete)
    assert Fraction(passing["reference"]["complete_panel_reference_coverage"]["exact"]) == Fraction(
        in_complete, len(complete)
    )
    assert passing["reference"]["unresolved_ids"] == [i for i in test_ids if i not in refs]
    assert passing["agreement"]["refusal_reasons"] == []
    assert refused["agreement"]["refusal_reasons"] == ["Lower 95% bound is below 0.60"]


def test_adjudication_before_the_gate_is_refused(tmp_path):
    path = copy_fixture(tmp_path)
    rows = json.loads((tmp_path / "adjudications.json").read_text())
    rows[0]["reviewed_at"] = "2026-10-01T00:00:00Z"
    data = json.dumps(rows, indent=2).encode()
    (tmp_path / "adjudications.json").write_bytes(data)
    manifest = json.loads(path.read_text())
    manifest["files"]["adjudications"]["sha256"] = hashlib.sha256(data).hexdigest()
    path.write_text(json.dumps(manifest))
    with pytest.raises(bench.BenchmarkError, match="Leaked or stale-gate adjudication"):
        bench.evaluate(path)
