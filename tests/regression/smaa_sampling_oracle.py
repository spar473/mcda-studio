"""Independent plain-Python sampling oracle for SMAA-2. It never imports mcda_studio.

For stated uncertainty too large to enumerate, this draws its own samples with Python's
``random`` module (not NumPy, not the engine's PCG64 stream) and counts competition ranks of the
additive values computed by ``sorting_oracle``. Its frequencies are estimates with their own
sampling error, so tests compare them with the engine's within a stated statistical bound; they
are a bounded check, not an exact one.

Runs follow the specification: ``performance`` varies only stated cells, ``preference`` only
stated weight groups, ``combined`` both. Cells are drawn independently (no shared draws).
"""

import math
import random
from typing import Any

import sorting_oracle as values_oracle

TOL = 1e-12
Project = dict[str, Any]


def _draw(rng: random.Random, distribution: dict[str, Any], labels: list[str]) -> Any:
    kind = distribution["kind"]
    if kind == "uniform":
        return rng.uniform(distribution["lower"], distribution["upper"])
    if kind == "categorical":
        given = dict(zip(distribution["labels"], distribution["probabilities"], strict=True))
        ordered = [label for label in labels if label in given]
        u, total = rng.random(), 0.0
        for label in ordered:
            total += given[label]
            if u < total:
                return label
        return ordered[-1]
    raise ValueError(f"the sampling oracle does not cover {kind!r} distributions")


def rank_acceptability(
    project: Project, run: str, draws: int, seed: int, profile_id: str | None = None
) -> dict[str, list[float]]:
    """{alternative: [share of draws at rank 1, rank 2, ...]} under competition ranks."""
    rng = random.Random(seed)
    nodes = {n["id"]: n for n in project["criteria"]}
    alts = [a["id"] for a in project["alternatives"]]
    base_judgements = values_oracle._profile(project, None, profile_id)
    measured = {
        (p["alternative_id"], p["criterion_id"]): p["value"] for p in project["performances"]
    }
    smaa = project["smaa"]
    cells = smaa["cells"] if run in ("performance", "combined") else []
    groups = smaa["groups"] if run in ("preference", "combined") else []
    fixed_weights = values_oracle.global_weights(
        project, values_oracle.local_weights(project, base_judgements)
    )
    counts = {a: [0] * len(alts) for a in alts}
    for _ in range(draws):
        cell_values = dict(measured)
        for cell in cells:
            leaf = nodes[cell["criterion_id"]]
            key = (cell["alternative_id"], cell["criterion_id"])
            cell_values[key] = _draw(rng, cell["distribution"], leaf["scale"].get("labels", []))
        if groups:
            judgements = dict(base_judgements)
            for group in groups:
                if group["kind"] != "rating_intervals":
                    raise ValueError("the sampling oracle covers rating intervals only")
                for child, (lower, upper) in group["intervals"].items():
                    judgements[child] = rng.uniform(lower, upper)
            weights = values_oracle.global_weights(
                project, values_oracle.local_weights(project, judgements)
            )
        else:
            weights = fixed_weights
        values = {}
        for alt in alts:
            terms = []
            for leaf_id, weight in weights.items():
                node = nodes[leaf_id]
                value = values_oracle.partial_value(
                    node["value_function"], node["scale"], cell_values[(alt, leaf_id)]
                )
                terms.append(weight * value)
            values[alt] = math.fsum(terms)
        for alt, value in values.items():
            rank = 1 + sum(1 for other in values.values() if other > value + TOL)
            counts[alt][rank - 1] += 1
    return {alt: [c / draws for c in row] for alt, row in counts.items()}
