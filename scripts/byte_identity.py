"""Hash every MAVT, sorting, SMAA-2, PROMETHEE II, AHP and method comparison output of the bundled
examples, to prove byte identity.

Run it once against the previous commit's tree and once against the working tree, then compare:

    git archive <commit> | tar -x -C /tmp/old
    python scripts/byte_identity.py --root /tmp/old --out old.json
    python scripts/byte_identity.py --root . --out new.json
    python scripts/byte_identity.py --compare old.json new.json

``--root`` selects the source tree that is imported and the examples that are read, so the script
uses only service and HTTP calls that both versions offer. Each example is evaluated under Base,
every scenario and every explicit profile. SMAA-2 runs at its default seed and sample count, with
unknown top-level weights stated, under Base and every scenario. PROMETHEE II runs with a fixed
stated section (every leaf maximised, weight 1, the usual function, labels coded by their position)
under Base and every scenario, so its explanation against MAVT is covered too. AHP runs with fixed
consistent judgements (weights cycling through 1, 2, 3 and 6). The method comparison runs on each
example bare and with all three sections stated, under Base, every scenario and every profile, by
service and over HTTP, with its JSON and CSV downloads. A method the tree predates is skipped.
The manifest maps an output name to its SHA-256.
"""

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

#: The MAVT examples, then the sorting example (skipped in a tree that predates it).
EXAMPLES = (
    "nz_deeptech_vc",
    "supplier_selection",
    "infrastructure_procurement",
    "supplier_qualification",
)
CSV_TABLES = ("ranking", "contributions", "partial_values", "dominance", "comparison")


def _sha(data: bytes | str) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def manifest(root: Path) -> dict[str, str]:
    sys.path.insert(0, str(root / "src"))
    from fastapi.testclient import TestClient
    from typer.testing import CliRunner

    import mcda_studio
    from mcda_studio.api.app import create_app
    from mcda_studio.cli import app as cli_app
    from mcda_studio.domain.errors import McdaError
    from mcda_studio.services import analysis_service as svc
    from mcda_studio.services import results_service as results
    from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text

    if Path(mcda_studio.__file__).resolve().parents[1] != (root / "src").resolve():
        raise SystemExit(f"imported {mcda_studio.__file__}, not the tree under {root}")
    out: dict[str, str] = {}
    repo = JsonProjectRepository()

    def put(key: str, compute: Any, *args: Any, **kwargs: Any) -> None:
        try:
            value = compute(*args, **kwargs)
        except McdaError as exc:
            value = f"{type(exc).__name__}: {exc}"
        if isinstance(value, list):
            value = json.dumps([v.model_dump(mode="json") for v in value], indent=2)
        elif not isinstance(value, bytes | str):
            value = to_json_text(value)
        out[key] = _sha(value)

    def http(key: str, path: str, payload: dict[str, Any]) -> None:
        response = client.post(f"/api/{path}", json=payload)
        out[key] = _sha(f"{response.status_code} ".encode() + response.content)

    def export(*args: Any, **kwargs: Any) -> bytes:
        return results.export_analysis(*args, **kwargs)[0]

    def exports(key: str, project: Any, cfg: Any, request: dict[str, Any]) -> None:
        """The JSON export and every CSV table the method declares, by service and over HTTP."""
        try:
            record = results.analysis_record(project, cfg)
        except McdaError as exc:
            out[f"{key}/export"] = _sha(f"{type(exc).__name__}: {exc}")
            return
        options = {
            "expected_project_fingerprint": project.fingerprint(),
            "expected_record_digest": record.record_digest,
        }
        tables = getattr(results, "EXPORT_TABLES", {}).get(cfg.method, CSV_TABLES)
        for fmt, table in [("json", "ranking")] + [("csv", t) for t in tables]:
            put(
                f"{key}/export/{fmt}-{table}",
                export,
                project,
                cfg,
                **options,
                format_=fmt,
                table=table,
            )
            http(
                f"{key}/http/export/{fmt}-{table}",
                "analysis/export",
                {**request, **options, "format": fmt, "table": table},
            )

    try:
        from mcda_studio.domain.uncertainty import GroupUncertainty, SmaaModel
        from mcda_studio.services import project_service as ps

        smaa: Any = SmaaModel(groups=[GroupUncertainty(parent_id=None, kind="unknown")])
    except ImportError:  # a tree that predates SMAA-2
        smaa = None
    try:
        from mcda_studio.domain.outranking import PrometheeCriterion, PrometheeModel, UsualFunction
    except ImportError:  # a tree that predates PROMETHEE II
        PrometheeModel = None  # noqa: N806

    def stated_promethee(project: Any) -> Any:
        tree = project.tree()
        criteria = []
        for leaf in tree.leaves():
            scale = tree.node(leaf).scale
            labelled = scale is not None and scale.type.value in ("categorical", "ordinal")
            coding = {label: float(k) for k, label in enumerate(scale.labels)} if labelled else None
            criteria.append(
                PrometheeCriterion(
                    criterion_id=leaf,
                    direction="maximise",
                    weight=1.0,
                    function=UsualFunction(),
                    coding=coding,
                )
            )
        return ps.set_promethee_model(project, PrometheeModel(criteria=criteria))

    try:
        from mcda_studio.domain.pairwise import (
            AhpModel,
            AlternativeJudgements,
            CriteriaJudgements,
            PairwiseJudgement,
        )
    except ImportError:  # a tree that predates AHP
        AhpModel = None  # noqa: N806

    def stated_ahp(project: Any) -> Any:
        tree = project.tree()

        def consistent(items: list[str], shift: int) -> list[Any]:
            w = [(1, 2, 3, 6)[(k + shift) % 4] for k in range(len(items))]
            out = []
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    hi, lo = (i, j) if w[i] >= w[j] else (j, i)
                    out.append(
                        PairwiseJudgement(row=items[hi], column=items[lo], value=w[hi] / w[lo])
                    )
            return out

        parents = [None, *(i for i in tree.all_ids() if not tree.is_leaf(i))]
        model = AhpModel(
            criteria=[
                CriteriaJudgements(parent_id=p, judgements=consistent(tree.child_ids(p), k))
                for k, p in enumerate(parents)
                if len(tree.child_ids(p)) >= 2
            ],
            alternatives=[
                AlternativeJudgements(
                    criterion_id=leaf, judgements=consistent(project.alternative_ids(), k)
                )
                for k, leaf in enumerate(tree.leaves())
            ],
        )
        return ps.set_ahp_model(project, model)

    try:
        from mcda_studio.services import comparison_service as comparisons
    except ImportError:  # a tree that predates the method comparison
        comparisons = None

    def comparison_download(project: Any, cfg: Any, fingerprint: str, fmt: str) -> bytes:
        return comparisons.export_comparison(project, cfg, None, fingerprint, fmt)[0]

    def comparison_runs(name: str, label: str, project: Any, contexts: Any) -> None:
        """The comparison of every method under each context, with both downloads."""
        body = project.model_dump(mode="json")
        fingerprint = project.fingerprint()
        for context, update in contexts:
            cfg = project.analysis.model_copy(update={**update, "parameters": {}})
            key = f"{name}/compare-methods-{label}-{context}"
            request = {"project": body, "configuration": cfg.model_dump(mode="json")}
            put(f"{key}/service", comparisons.compare_methods, project, cfg)
            http(f"{key}/http", "methods/compare", request)
            for fmt in ("json", "csv"):
                put(f"{key}/export-{fmt}", comparison_download, project, cfg, fingerprint, fmt)
                http(
                    f"{key}/http/export-{fmt}",
                    "methods/compare/export",
                    {**request, "expected_project_fingerprint": fingerprint, "format": fmt},
                )

    def method_runs(name: str, method: str, project: Any, contexts: Any) -> None:
        """One method under Base and every scenario: evaluation and every export."""
        body = project.model_dump(mode="json")
        for label, update in contexts:
            if "weight_profile_id" in update:
                continue
            cfg = project.analysis.model_copy(update={**update, "method": method, "parameters": {}})
            key = f"{name}/{method}-{label}"
            request = {"project": body, "configuration": cfg.model_dump(mode="json")}
            put(f"{key}/evaluate", svc.evaluate_project, project, cfg)
            http(f"{key}/http/evaluate", "evaluate", request)
            exports(key, project, cfg, request)

    with tempfile.TemporaryDirectory() as tmp:
        client = TestClient(create_app(Path(tmp) / "store", frontend_dir=False))
        for name in EXAMPLES:
            path = root / "examples" / name / "project.json"
            if not path.is_file():
                continue
            project = repo.load(path)
            body = project.model_dump(mode="json")
            out[f"{name}/file"] = _sha(path.read_bytes())
            put(f"{name}/resaved", to_json_text, project)
            put(f"{name}/fingerprint", project.fingerprint)
            saved = repo.save(project, Path(tmp) / f"{name}.json")
            out[f"{name}/save-bytes"] = _sha(saved.read_bytes())
            put(f"{name}/validate", svc.validate, project)
            http(f"{name}/http/validate", "validate", {"project": body})
            out[f"{name}/cli/evaluate-json"] = _sha(
                CliRunner().invoke(cli_app, ["evaluate", str(path), "--json"]).output
            )
            contexts: list[tuple[str, dict[str, Any]]] = [("base", {"scenario_id": None})]
            contexts += [(f"scenario-{s.id}", {"scenario_id": s.id}) for s in project.scenarios]
            contexts += [
                (f"profile-{p.id}", {"weight_profile_id": p.id, "scenario_id": None})
                for p in project.weight_profiles
            ]
            leaves = project.tree().leaves()
            for label, update in contexts:
                cfg = project.analysis.model_copy(update=update)
                key = f"{name}/{label}"
                request = {"project": body, "configuration": cfg.model_dump(mode="json")}
                put(f"{key}/validate-effective", svc.validate_effective, project, cfg)
                put(f"{key}/evaluate", svc.evaluate_project, project, cfg)
                put(f"{key}/record", results.analysis_record, project, cfg)
                put(f"{key}/sensitivity-all", svc.sensitivity_all, project, cfg)
                put(f"{key}/compare", svc.compare_scenarios, project, None, cfg)
                put(f"{key}/weights", svc.preview_weights, project, cfg)
                for leaf in leaves:
                    put(f"{key}/vf-preview/{leaf}", svc.preview_value_function, project, leaf, cfg)
                node = svc.sensitivity_all(project, cfg)[0].node_id
                put(f"{key}/probe", svc.sensitivity_probe, project, node, 0.3, cfg)
                for route, payload in [
                    ("evaluate", request),
                    ("analysis/record", request),
                    ("analysis/validate", request),
                    ("sensitivity", {**request, "node_id": node}),
                    ("sensitivity/probe", {**request, "node_id": node, "weight": 0.3}),
                    ("scenarios/compare", request),
                    ("weights/preview", request),
                    ("value-functions/preview", {**request, "criterion_id": leaves[0]}),
                ]:
                    http(f"{key}/http/{route}", route, payload)
                exports(key, project, cfg, request)
            if smaa is not None:
                method_runs(name, "smaa2", ps.set_smaa_model(project, smaa), contexts)
            if PrometheeModel is not None:
                method_runs(name, "promethee2", stated_promethee(project), contexts)
            if AhpModel is not None:
                method_runs(name, "ahp", stated_ahp(project), contexts[:1])
            if comparisons is not None:
                full = stated_ahp(stated_promethee(ps.set_smaa_model(project, smaa)))
                comparison_runs(name, "bare", project, contexts)
                comparison_runs(name, "full", full, contexts)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, help="source tree to import and read examples from")
    ap.add_argument("--out", type=Path, help="where to write the manifest")
    ap.add_argument("--compare", nargs=2, type=Path, metavar=("OLD", "NEW"))
    args = ap.parse_args()
    if args.compare:
        old, new = (json.loads(p.read_text()) for p in args.compare)
        changed = sorted(k for k in old.keys() & new.keys() if old[k] != new[k])
        missing = sorted(old.keys() ^ new.keys())
        for key in changed:
            print(f"changed: {key}")
        for key in missing:
            print(f"only in one manifest: {key}")
        same = len(old.keys() & new.keys()) - len(changed)
        print(f"{same} of {len(old.keys() | new.keys())} outputs byte-identical")
        return 1 if changed or missing else 0
    if not args.root or not args.out:
        ap.error("--root and --out are required unless --compare is given")
    data = manifest(args.root.resolve())
    args.out.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(f"{len(data)} outputs hashed from {args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
