"""Independent reference/oracle checks and larger-model service timings; no library writes.

    python scripts/acceptance_evidence.py [OUTPUT_DIR]

Checks the VC reference study's exact crossovers against the independent oracle, that results
reconcile with their contributions, that the performance fixture is reproducible, and times the
main services on the 50-alternative fixture. Writes ``numerical-performance.json`` to OUTPUT_DIR.
"""

import hashlib
import json
import math
import runpy
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.services import analysis_service as service
from mcda_studio.services.results_service import analysis_record, export_analysis
from mcda_studio.storage.json_repository import JsonProjectRepository

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/mcda-acceptance-evidence")
    output.mkdir(parents=True, exist_ok=True)
    repository = JsonProjectRepository()
    project = repository.load(ROOT / "examples/nz_deeptech_vc/project.json")
    reference = runpy.run_path(str(ROOT / "tests/regression/test_nz_deeptech_vc_reference.py"))
    oracle = reference["ORACLE"]
    crossovers = []
    fingerprint = project.fingerprint()
    for node in ["team", "market", "market_size"]:
        sweep = service.sensitivity(project, node)
        crossing = sweep.first_winner_change_up
        assert crossing is not None
        lines = oracle.affine_size() if node == "market_size" else oracle.affine_parent(node)
        baseline = 100 / 180 if node == "market_size" else oracle.parent_weights()[node]
        expected = oracle.first_crossover_up(lines, baseline)
        assert expected is not None and abs(crossing.weight - expected[1]) < 1e-9
        probe = service.sensitivity_probe(project, node, crossing.weight)
        assert [row.rank for row in probe.alternatives] == [1, 1, 3, 4]
        assert probe.ranking_differs_from_baseline and probe.winner_differs_from_baseline
        crossovers.append(
            {
                "node": node,
                "weight": crossing.weight,
                "oracle_weight": expected[1],
                "error": crossing.weight - expected[1],
                "ranks": [row.rank for row in probe.alternatives],
                "winners": [row.alternative_id for row in probe.alternatives if row.rank == 1],
            }
        )
    assert project.fingerprint() == fingerprint
    record = analysis_record(project)
    for alt in record.result.alternatives:
        assert math.fsum(alt.weighted_contributions.values()) == alt.overall_value
    fixture = ROOT / "tests/fixtures/performance_project.json"
    large = repository.load(fixture)
    generated = runpy.run_path(str(ROOT / "scripts/build_results_performance_fixture.py"))
    assert large == generated["build_project"](), "performance fixture is not reproducible"
    operations: dict[str, Any] = {
        "project_load": lambda: repository.load(fixture),
        "tree": large.tree,
        "weight_preview": lambda: service.preview_weights(large),
        "evaluation": lambda: service.evaluate_project(large),
        "sensitivity_101_and_exact_crossovers": lambda: service.sensitivity(large, "objective_0"),
        "sensitivity_probe": lambda: service.sensitivity_probe(large, "objective_0", 0.37),
        "scenario_record": lambda: analysis_record(
            large, AnalysisConfiguration(scenario_id="different_profile")
        ),
        "results_record": lambda: analysis_record(large),
    }
    result = analysis_record(large)
    operations["contribution_csv"] = lambda: export_analysis(
        large, large.analysis, large.fingerprint(), result.record_digest, "csv", "contributions"
    )
    timings = {}
    large_before = large.fingerprint()
    for name, operation in operations.items():
        samples = []
        for iteration in range(6):
            start = time.perf_counter()
            operation()
            if iteration:
                samples.append((time.perf_counter() - start) * 1000)
        timings[name] = {"samples_ms": samples, "median_ms": statistics.median(samples)}
    assert large.fingerprint() == large_before
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "reopened.json"
        repository.save(large, path)
        reopened = repository.load(path)
        assert reopened == large and analysis_record(reopened) == result
    fixtures = {}
    for name in [
        "nz_deeptech_vc",
        "supplier_selection",
        "supplier_qualification",
        "infrastructure_procurement",
    ]:
        path = f"examples/{name}/project.json"
        fixtures[path] = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    evidence = {
        "crossovers": crossovers,
        "reference_base_ranking": [row.model_dump(mode="json") for row in record.result.ranking],
        "global_weights": record.result.global_weights,
        "parent_ratings": {
            n: project.weight_profiles[0].judgements[n]
            for n in ["team", "problem_solution", "market", "traction"]
        },
        "fixture_sha256": fixtures,
        "large_fixture": {
            "alternatives": 50,
            "leaves": 40,
            "nodes": 52,
            "depth": 3,
            "measurements": 2000,
        },
        "timings": timings,
        "save_reopen_exact": True,
        "mathematical_state_unchanged": True,
        "precision": "Evaluation/probe math.fsum path; sweep plotting can differ by one ULP.",
    }
    (output / "numerical-performance.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({name: values["median_ms"] for name, values in timings.items()}, indent=2))


if __name__ == "__main__":
    main()
