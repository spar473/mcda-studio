"""The venture screening study against independent oracles.

``sorting_oracle`` (MAVT values and classes), ``feasibility_oracle``, ``promethee_oracle`` and
``smaa_sampling_oracle`` read the project file as JSON and never import ``mcda_studio`` (checked
below in a clean interpreter); only this comparison module calls the engine. SMAA-2 is checked
two ways: exactly where the stated uncertainty allows it (the preference run, by its weight-box
vertices) and within a stated statistical bound against an independent sampler elsewhere.
"""

import importlib.util
import itertools
import json
import math
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import feasibility_oracle
import promethee_oracle
import pytest
import smaa_sampling_oracle
import sorting_oracle as oracle

from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.results import MavtSortingResult, PrometheeResult, SmaaResult
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import decision_record_service as decisions
from mcda_studio.services import evidence_service as evidence
from mcda_studio.services import feasibility_service as feasibility
from mcda_studio.services import starter_template_service as starters
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples" / "nz_venture_screening"
FILE = EXAMPLE / "project.json"
STARTER = ROOT / "examples" / "starter_templates" / "venture_screening_study"
PROFILES = ["technical_ip", "commercial_traction"]
CONTEXTS = [
    (profile, scenario) for profile in PROFILES for scenario in (None, "linear_market_size")
]


def _build_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("venture_study_build", EXAMPLE / "build.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _project():  # type: ignore[no-untyped-def]
    return JsonProjectRepository().load(FILE)


def _sorting(profile: str, scenario: str | None) -> MavtSortingResult:
    cfg = AnalysisConfiguration(
        method="mavt_sorting", weight_profile_id=profile, scenario_id=scenario
    )
    result = svc.evaluate_project(_project(), cfg)
    assert isinstance(result, MavtSortingResult)
    return result


def _smaa(run: str) -> SmaaResult:
    cfg = AnalysisConfiguration(method="smaa2", parameters={"uncertainty": run, "seed": 2026})
    result = svc.evaluate_project(_project(), cfg)
    assert isinstance(result, SmaaResult)
    return result


@pytest.mark.parametrize(
    "module", ["sorting_oracle", "feasibility_oracle", "promethee_oracle", "smaa_sampling_oracle"]
)
def test_the_oracles_import_nothing_from_mcda_studio(module: str) -> None:
    code = (
        f"import sys; sys.path.insert(0, sys.argv[1]); import {module}; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] == 'mcda_studio'))"
    )
    run = subprocess.run(
        [sys.executable, "-I", "-c", code, str(Path(__file__).parent)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert run.stdout.strip() == "[]"


def test_the_shipped_files_match_the_build_script() -> None:
    build = _build_module()
    project = build.build_project()
    assert to_json_text(project) == FILE.read_text(encoding="utf-8")
    dossier = build.build_dossier(project)
    shipped = (EXAMPLE / "evidence.json").read_bytes()
    assert build._canonical(dossier.model_dump(mode="json")) == shipped
    assert (STARTER / "project.json").read_bytes() == FILE.read_bytes()
    assert (STARTER / "evidence.json").read_bytes() == shipped


def test_the_gallery_card_opens_the_study_with_its_dossier() -> None:
    template = next(t for t in starters.list_templates() if t.id == "venture_screening_study")
    assert template.title == "Venture screening"
    assert {a.kind for a in template.artifacts} == {"project", "evidence_dossier"}
    request = starters.StarterInstantiationRequest(
        template_id="venture_screening_study", mode="worked_example"
    )
    worked = starters.instantiate(request)
    assert worked.project.fingerprint() == _project().fingerprint()
    assert worked.artifacts["evidence"].value["project_fingerprint"] == _project().fingerprint()
    invented = next(t for t in starters.list_templates() if t.id == "venture_screening")
    assert invented.title == "Venture screening: evidence and model workflows (invented data)"


def test_the_mandate_branch_is_screened_not_scored() -> None:
    raw = oracle.load(FILE)
    for profile in PROFILES:
        weights = oracle.global_weights(
            raw, oracle.local_weights(raw, oracle._profile(raw, None, profile))
        )
        assert [weights[leaf] for leaf in ("hq_country", "stage", "sector")] == [0.0, 0.0, 0.0]
        assert math.fsum(weights.values()) == pytest.approx(1.0, abs=1e-12)
        result = _sorting(profile, None)
        assert [result.global_weights[leaf] for leaf in ("hq_country", "stage", "sector")] == [
            0.0
        ] * 3
        for row in result.alternatives:
            assert all(
                row.weighted_contributions[leaf] == 0.0
                for leaf in ("hq_country", "stage", "sector")
            )


@pytest.mark.parametrize(("profile", "scenario"), CONTEXTS)
def test_values_ranks_classes_and_margins_match_the_oracle(
    profile: str, scenario: str | None
) -> None:
    raw = oracle.load(FILE)
    values = oracle.overall_values(raw, scenario, profile)
    result = _sorting(profile, scenario)
    for row in result.ranking:
        assert row.value == pytest.approx(values[row.alternative_id], abs=1e-12)
        expected_rank = 1 + sum(
            1 for v in values.values() if v > values[row.alternative_id] + 1e-12
        )
        assert row.rank == expected_rank
    for a in result.assignments:
        assert a.class_id == oracle.class_of(values[a.alternative_id], raw)
        nearest = oracle.nearest_boundary(values[a.alternative_id], raw)
        assert nearest is not None and a.nearest_boundary_class_id == nearest[0]
        assert a.distance_to_nearest_boundary == pytest.approx(nearest[1], abs=1e-12)
    assert result.audit_sample is not None
    assert result.audit_sample.alternative_ids == oracle.audit_sample(values, raw)


def test_the_documented_reading_holds() -> None:
    """The README's summary of the built study; a changed rating must update both."""
    technical = {a.alternative_id: a.class_id for a in _sorting("technical_ip", None).assignments}
    commercial = _sorting("commercial_traction", None)
    assert technical["upstock"] == "prioritise_for_diligence"
    assert technical["kea_aerospace"] == "not_now"
    assert commercial.ranking[0].alternative_id == "upstock"
    hectre = next(a for a in commercial.assignments if a.alternative_id == "hectre")
    assert hectre.class_id == "monitor" and hectre.distance_to_nearest_boundary < 0.001


def test_requirements_match_the_oracle_and_only_hnry_fails() -> None:
    raw = oracle.load(FILE)
    expected = feasibility_oracle.evaluate(raw)
    result = feasibility.check_feasibility(_project())
    assert {a.alternative_id: a.status for a in result.alternatives} == {
        a: e["status"] for a, e in expected.items()
    }
    assert [a for a, e in expected.items() if e["status"] == "fail"] == ["hnry"]
    # The failing company keeps its place in every ranking.
    for profile in PROFILES:
        assert "hnry" in [r.alternative_id for r in _sorting(profile, None).ranking]


def test_promethee_flows_match_the_exact_oracle() -> None:
    raw = oracle.load(FILE)
    exact = promethee_oracle.flows(raw)
    result = svc.evaluate_project(_project(), AnalysisConfiguration(method="promethee2"))
    assert isinstance(result, PrometheeResult)
    assert sum(exact["net"].values()) == 0
    for row in result.ranking:
        assert row.value == pytest.approx(float(exact["net"][row.alternative_id]), abs=1e-12)
    codes = [d.code for d in result.diagnostics]
    assert codes.count("PROMETHEE_CRITERION_INERT") == 3  # the three mandate leaves


def test_preference_acceptability_is_exact_at_the_weight_box_vertices() -> None:
    """With only the top-level ratings uncertain, each pairwise difference is a ratio whose
    numerator is linear in the ratings, so its sign over the box is settled at the vertices."""
    raw = oracle.load(FILE)
    group = next(g for g in raw["smaa"]["groups"] if g["parent_id"] is None)
    leaders = set()
    for corner in itertools.product(*group["intervals"].values()):
        judgements = dict(oracle._profile(raw, None, None))
        judgements.update(dict(zip(group["intervals"], corner, strict=True)))
        if sum(corner) == 0:
            continue
        values = oracle.overall_values(raw, local=oracle.local_weights(raw, judgements))
        top = max(values.values())
        leaders |= {a for a, v in values.items() if v > top - 1e-12}
    result = _smaa("preference")
    rank1 = {row.alternative_id: row.ranks[0].frequency for row in result.acceptability}
    assert leaders == {"upstock"}
    assert rank1["upstock"] == 1.0
    assert all(f == 0.0 for a, f in rank1.items() if a != "upstock")


@pytest.mark.parametrize("run", ["performance", "combined"])
def test_sampled_acceptability_agrees_with_an_independent_sampler(run: str) -> None:
    """A bounded statistical check: two independent estimates of each rank-1 share must agree
    within four standard errors of their difference (plus 0.002 for rounding of ties)."""
    raw = oracle.load(FILE)
    draws = 10_000
    independent = smaa_sampling_oracle.rank_acceptability(raw, run, draws, seed=7)
    result = _smaa(run)
    assert result.samples == draws
    for row in result.acceptability:
        mine = independent[row.alternative_id][0]
        engine = row.ranks[0].frequency
        pooled = (mine + engine) / 2
        bound = 4 * math.sqrt(max(pooled * (1 - pooled), 1e-4) * 2 / draws) + 0.002
        assert abs(mine - engine) <= bound, (row.alternative_id, mine, engine, bound)
    assert result.leader_id == "upstock"


def test_the_dossier_binds_and_supports_every_entered_measurement() -> None:
    project = _project()
    dossier = EvidenceDossier.model_validate_json((EXAMPLE / "evidence.json").read_text())
    assert dossier.project_fingerprint == project.fingerprint()
    preview = evidence.preview(project, dossier)
    assert preview.issues == [] and preview.missing_measurements == []
    assert len(preview.conflicting_cells) == 2 and len(preview.unreviewed_claims) == 2
    accepted = {(c.alternative_id, c.criterion_id): c for c in dossier.claims if c.review}
    entered = {(p.alternative_id, p.criterion_id): p.value for p in project.performances}
    assert set(accepted) == set(entered)
    assert all(accepted[key].value == value for key, value in entered.items())
    for claim in dossier.claims:
        assert claim.source.reference.startswith(("https://", "examples/nz_venture_screening/"))
        assert "Retrieved 4 November 2026." in claim.source.description
        assert claim.source.description.startswith(("Observed", "Judgement:", "Proxy:"))
        assert claim.outdated == (
            (project_date := claim.source.date) < _build_module().OUTDATED_BEFORE
        )
        assert project_date <= _build_module().AS_OF


def test_market_cells_are_the_median_of_the_listed_estimates() -> None:
    build = _build_module()
    project = _project()
    entered = {(p.alternative_id, p.criterion_id): p.value for p in project.performances}
    for alt, (_, estimates) in build.MARKETS.items():
        sizes = sorted(e[3] for e in estimates)
        half = len(sizes) // 2
        median = sizes[half] if len(sizes) % 2 else (sizes[half - 1] + sizes[half]) / 2
        assert entered[(alt, "market_size")] == median
        cells = {
            c.criterion_id: c.distribution
            for c in project.smaa.cells  # type: ignore[union-attr]
            if c.alternative_id == alt and c.criterion_id in ("market_size", "market_growth")
        }
        assert (cells["market_size"].lower, cells["market_size"].upper) == (sizes[0], sizes[-1])  # type: ignore[union-attr]


def test_the_decision_record_verifies_and_is_marked_illustrative() -> None:
    record = decisions.DecisionRecordV2.model_validate_json((EXAMPLE / "decision.json").read_text())
    decisions.verify(record)
    assert record.project_fingerprint == _project().fingerprint()
    assert record.decision.selected_alternative_id == "upstock"
    assert all(s.status == "completed" for s in record.analyses)
    texts = [
        record.decision.rationale,
        *record.decision.unresolved_assumptions,
        *record.decision.review_triggers,
    ]
    assert all(text.startswith("Illustrative:") for text in texts)
    selected = next(
        a
        for a in feasibility.check_feasibility(_project()).alternatives
        if a.alternative_id == "upstock"
    )
    assert selected.status == "pass"


def test_the_starter_manifest_lists_hash_checked_files() -> None:
    manifest = json.loads((STARTER / "manifest.json").read_text())
    assert manifest["source_example"] == "examples/nz_venture_screening"
    assert [a["path"] for a in manifest["artifacts"]] == ["project.json", "evidence.json"]


def test_each_claim_records_its_kind_and_judgements_drive_the_stated_uncertainty() -> None:
    """A judgement must never read as observed: the dossier, the build table and SMAA-2 agree."""
    build = _build_module()
    project = _project()
    dossier = EvidenceDossier.model_validate_json((EXAMPLE / "evidence.json").read_text())
    varied = {
        (c.alternative_id, c.criterion_id)
        for c in project.smaa.cells  # type: ignore[union-attr]
        if c.distribution.kind == "categorical"
    }
    for alt, cells in build.CELLS.items():
        for leaf, (_, _, _, _, kind) in cells.items():
            claim = next(c for c in dossier.claims if c.id == f"{alt}__{leaf}")
            assert claim.source.description.startswith(f"{kind.capitalize()}:")
            scored = build.LEAF[leaf].parent != "mandate"
            assert ((alt, leaf) in varied) == (kind == "judgement" and scored), (alt, leaf)
