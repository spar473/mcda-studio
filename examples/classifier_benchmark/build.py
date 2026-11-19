"""Build invented, anonymous benchmark inputs under a frozen protocol; no model execution."""

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "agreement_benchmark", ROOT / "scripts/classifier_agreement_benchmark.py"
)
benchmark = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return {"path": path.name, "sha256": benchmark.sha(path.read_bytes())}


def build(destination=None):
    target = Path(destination) if destination else Path(__file__).resolve().parent / "synthetic"
    target.mkdir(parents=True, exist_ok=True)
    labels = ["alpha", "beta"]
    panel = ["reviewer_1", "reviewer_2"]
    rng = np.random.Generator(np.random.PCG64(47))
    disagreement_groups = sorted(
        int(n) for n in rng.choice(np.arange(6, 60), size=8, replace=False)
    )
    items = []
    human = []
    truth = {}
    splits = {}
    tools = []
    outputs = []
    for split, n in [("train", 20), ("development", 10), ("test", 120)]:
        splits[split] = []
        for index in range(n):
            id = f"{split}_{index:03}"
            splits[split].append(id)
            label = ("alpha" if index < 4 else "beta") if split == "train" else labels[index % 2]
            truth[id] = label
            group = f"{split}_group_{index // 2:03}"
            items.append(
                {
                    "id": id,
                    "entity_id": group,
                    "group_id": group,
                    "split": split,
                    "eligible": True,
                    "exclusion_reason": "",
                    "observed_at": "2026-09-01T00:00:00Z",
                    "feature_dates": {"invented_input": "2026-09-01T00:00:00Z"},
                }
            )
            for reviewer in panel:
                supplied = label
                if split == "test" and reviewer == "reviewer_2":
                    if index // 2 < 6:
                        supplied = None
                    elif index // 2 in disagreement_groups and index % 2 == 1:
                        supplied = "alpha"
                human.append(
                    {
                        "item_id": id,
                        "reviewer": reviewer,
                        "label": supplied,
                        "reviewed_at": "2026-10-01T00:00:00Z",
                        "task_version": "1",
                    }
                )
    for tool_id, semantics in [
        ("classifier_a", "probability_vector"),
        ("classifier_b", "chosen_label_confidence"),
        ("classifier_c", "arbitrary_score"),
    ]:
        card = {
            "version": 1,
            "model_version": "model-1",
            "purpose": "Invented nominal-label fixture",
            "limitations": "Synthetic inputs and outputs; no model was executed",
        }
        declaration = write(target / (tool_id + "-card.json"), card)
        tools.append(
            {
                "id": tool_id,
                "version": "wrapper-1",
                "task_version": "1",
                "model_card": declaration,
                "score_semantics": semantics,
                "score_bounds": [0, 100] if semantics == "arbitrary_score" else None,
            }
        )
        for index, item in enumerate(items):
            label = truth[item["id"]]
            if item["split"] == "test" and index % 7 == 0:
                label = labels[1 - labels.index(label)]
            abstain = item["split"] == "test" and index % 11 == 0
            score = None
            vector = None
            if semantics == "probability_vector":
                p = 1.0 if index % 10 == 0 else 0.8
                vector = {
                    labels[0]: p if label == labels[0] else 1 - p,
                    labels[1]: p if label == labels[1] else 1 - p,
                }
                # Declare exact decimal probabilities rather than binary subtraction artifacts.
                vector = {key: round(value, 1) for key, value in vector.items()}
            elif semantics == "chosen_label_confidence":
                score = None if abstain else (0.5 if index % 2 else 0.75)
            else:
                score = index % 101
            outputs.append(
                {
                    "item_id": item["id"],
                    "tool_id": tool_id,
                    "tool_version": "wrapper-1",
                    "task_version": "1",
                    "model_card_digest": declaration["sha256"],
                    "label": None if abstain else label,
                    "run_at": "2026-10-04T00:00:00Z",
                    "score": score,
                    "probabilities": vector,
                }
            )
    manifest = {
        "version": 1,
        "data_kind": "synthetic",
        "data_provenance": {
            "description": "Invented alternating held-out labels; generation seed 47 selects eight "
            "disagreement groups. First six held-out groups abstain; "
            "index rules declare tool errors/scores.",
            "generation_seed": 47,
        },
        "task": {
            "id": "invented_nominal_task",
            "version": "1",
            "instructions": "Distinguish the two invented nominal conditions "
            "using the declared generation rule.",
            "unit": "One invented observation",
            "population": "Synthetic paired entities only",
            "observation_cutoff": "2026-09-30T23:59:59Z",
            "eligibility": "All constructed observations",
            "exclusions": "None",
        },
        "labels": labels,
        "panel": panel,
        "splits": splits,
        "protocol": {
            "frozen_at": "2026-01-01T00:00:00Z",
            "gate_confirmed_at": "2026-10-02T00:00:00Z",
            "outputs_unblinded_at": "2026-10-05T00:00:00Z",
            "independent_blind_reviews": True,
            "blind_adjudication": True,
            "reference_policy": "unanimous-or-post-gate-adjudication.v1",
            "confidence": "0.95",
            "lower_kappa": "0.60",
            "minimum_coverage": "0.80",
            "bootstrap": {
                "replicates": 10000,
                "seed": 73,
                "unit": "group",
                "algorithm": benchmark.BOOTSTRAP_ALGORITHM,
                "quantile": "linear.v1",
            },
        },
        "files": {},
        "tools": tools,
    }
    for key, value in [
        ("items", items),
        ("human_labels", human),
        ("tool_outputs", outputs),
        ("adjudications", []),
    ]:
        manifest["files"][key] = write(target / (key + ".json"), value)
    path = target / "manifest.json"
    write(path, manifest)
    initial = benchmark.evaluate(path)
    assert initial["agreement"]["passed"]
    adjudications = [
        {
            "item_id": f"test_{2 * group + 1:03}",
            "reference_label": "beta",
            "rationale": "Reviewed the invented generation rule after the human-agreement gate",
            "reviewers": panel,
            "reviewed_at": "2026-10-03T00:00:00Z",
            "gate_digest": initial["gate_digest"],
            "task_version": "1",
        }
        for group in disagreement_groups[:6]
    ]
    manifest["files"]["adjudications"] = write(target / "adjudications.json", adjudications)
    write(path, manifest)
    complete = benchmark.evaluate(path)
    assert (
        complete["status"] == "reference accepted"
        and len(complete["reference"]["unresolved_ids"]) == 14
    )
    # A separate frozen synthetic poor-agreement example; no adjudication is attempted.
    refused = target / "refused"
    refused.mkdir(exist_ok=True)
    rejected = json.loads(json.dumps(manifest))
    rejected["data_provenance"]["description"] = (
        "Invented disagreement fixture; alternate second-reviewer labels independently of the first"
    )
    poor = []
    for row in human:
        row = dict(row)
        if row["item_id"].startswith("test_") and row["reviewer"] == "reviewer_2":
            row["label"] = labels[(int(row["item_id"][-3:]) // 2) % 2]
        poor.append(row)
    for key, value in [
        ("items", items),
        ("human_labels", poor),
        ("tool_outputs", outputs),
        ("adjudications", []),
    ]:
        rejected["files"][key] = write(refused / (key + ".json"), value)
    for tool in rejected["tools"]:
        original = target / tool["model_card"]["path"]
        tool["model_card"] = write(refused / original.name, json.loads(original.read_text()))
    write(refused / "manifest.json", rejected)
    assert benchmark.evaluate(refused / "manifest.json")["status"] == "reference refused"
    return path


if __name__ == "__main__":
    print(build())
