"""First-round build guards, source windows, the owner's gap rule and the ranked look-back.

This replaces the removed two-current-company draft's coverage and strengthens it for the
five-company retrospective. Source dates and expected market values are checked independently.
On 14 November 2026 the owner chose the venture study's convention for the 39 formerly missing
cells (each claim states its basis) and one window exception (Argo Navis's stage).
"""

import importlib.util
import subprocess
import sys
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path
from types import ModuleType

import pytest
from first_round_market_oracle import medians

from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.reference_cases import ReferenceCases
from mcda_studio.services import reference_case_service as svc
from mcda_studio.services import screening_summary_service as screening
from mcda_studio.storage.json_repository import JsonProjectRepository

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples" / "nz_first_round_retrospective"
STUDY = ROOT / "examples" / "nz_venture_screening"
FILES = ("project.json", "evidence.json", "reference-cases.json", "rubrics.json", "README.md")
ANCHORS = {
    "vertus_energy": date(2021, 10, 27),
    "croptide": date(2021, 12, 14),
    "rosterlab": date(2021, 12, 17),
    "argo_navis": date(2020, 9, 21),
    "helico": date(2022, 5, 9),
}
STARTS = {key: d.replace(year=d.year - 1) for key, d in ANCHORS.items()}
EXCEPTION_CELL = ("argo_navis", "stage")
BASIS_PREFIX = {
    "absence": "Absence rule (owner decision, 14 Nov 2026; the venture study's convention): ",
    "sector": "Sector judgement (owner decision, 14 Nov 2026; the venture study's convention): ",
    "exception": "Window exception (owner decision, 14 Nov 2026): ",
}
# Engine ranks under each profile, recorded from this build (14 November 2026).
EXPECTED_ORDER = ["vertus_energy", "croptide", "argo_navis", "rosterlab", "helico"]
repo = JsonProjectRepository()


def module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("first_round_build", EXAMPLE / "build.py")
    assert spec is not None and spec.loader is not None
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    return build


def test_two_builds_are_byte_identical_and_match_shipped_files(tmp_path: Path) -> None:
    build = module()
    build.build(tmp_path / "one")
    build.build(tmp_path / "two")
    for name in FILES:
        data = (tmp_path / "one" / name).read_bytes()
        assert data == (tmp_path / "two" / name).read_bytes(), name
        assert data == (EXAMPLE / name).read_bytes(), f"stale {name}: run build.py"


def test_criteria_profiles_classes_mandate_and_rubrics_equal_the_venture_study() -> None:
    project, study = repo.load(EXAMPLE / "project.json"), repo.load(STUDY / "project.json")
    assert project.criteria == study.criteria
    assert project.weight_profiles == study.weight_profiles
    assert project.sorting == study.sorting
    assert project.requirements == study.requirements
    assert (EXAMPLE / "rubrics.json").read_bytes() == (STUDY / "rubrics.json").read_bytes()
    assert project.alternative_ids() == list(ANCHORS)
    assert project.analysis.method == "mavt_sorting"
    assert project.scenarios == [] and project.smaa is None and project.promethee is None
    assert not (ROOT / "examples" / "nz_preseed_reference_cases").exists()


def test_inheritance_is_read_at_build_time(monkeypatch: pytest.MonkeyPatch) -> None:
    build = module()
    study = repo.load(STUDY / "project.json").model_copy(deep=True)
    study.criteria[0].description = "inheritance canary"
    study.weight_profiles[0].name = "changed profile canary"
    assert study.sorting is not None and study.requirements is not None
    study.sorting.classes[0].description = "class canary"
    study.requirements[0].rationale = "mandate canary"
    monkeypatch.setattr(JsonProjectRepository, "load", lambda *_: study)
    project = build.build_project()
    assert project.criteria == study.criteria
    assert project.weight_profiles == study.weight_profiles
    assert project.sorting == study.sorting
    assert project.requirements == study.requirements


def test_one_unreviewed_dated_evidence_claim_per_performance() -> None:
    project = repo.load(EXAMPLE / "project.json")
    dossier = EvidenceDossier.model_validate_json((EXAMPLE / "evidence.json").read_text())
    assert dossier.project_fingerprint == project.fingerprint()
    cells = {(p.alternative_id, p.criterion_id): p.value for p in project.performances}
    assert len(cells) == 95  # every cell rated: 56 drafted before 14 Nov, 39 under the gap rule
    assert len(dossier.claims) == len(cells)
    assert {(c.alternative_id, c.criterion_id): c.value for c in dossier.claims} == cells
    for claim in dossier.claims:
        if (claim.alternative_id, claim.criterion_id) == EXCEPTION_CELL:
            assert claim.source.date == date(2023, 3, 13)
            assert claim.source.description.startswith("Judgement: " + BASIS_PREFIX["exception"])
            continue
        start = STARTS[claim.alternative_id]
        assert start <= claim.source.date <= ANCHORS[claim.alternative_id] + timedelta(days=180)
        assert claim.review is None and claim.origin.tool_id == "claude-code"
        assert "draft; author review pending" in claim.origin.proposed_by
        assert "Draft; author review pending" in claim.source.description


def test_sidecar_snapshot_dates_rating_parity_and_outcomes() -> None:
    project = repo.load(EXAMPLE / "project.json")
    reference = ReferenceCases.model_validate_json((EXAMPLE / "reference-cases.json").read_text())
    report = svc.validate(project, reference)
    assert report.valid, report.issues
    assert report.case_count == 5
    assert reference.criteria_from == project.id
    cells = project.performance_index()
    for case in reference.cases:
        assert case.snapshot_date == ANCHORS[case.id] + timedelta(days=180)
        assert any(c.value == ANCHORS[case.id].isoformat() for c in case.context)
        expected = {
            leaf: value
            for (alt, leaf), value in cells.items()
            if alt == case.id and isinstance(value, str) and (alt, leaf) != EXCEPTION_CELL
        }
        assert {r.criterion_id: r.label for r in case.ratings} == expected
        claims = {c.id: c for c in case.claims}
        for rating in case.ratings:
            assert rating.note
            for claim_id in rating.claim_ids:
                assert (
                    STARTS[case.id]
                    <= reference.sources[claims[claim_id].source].date
                    <= case.snapshot_date
                )
        assert case.outcome.claim_ids and case.outcome.as_of > case.snapshot_date


@pytest.mark.parametrize("days", [-366, 181])
def test_build_refuses_a_rating_outside_window_before_writing(tmp_path: Path, days: int) -> None:
    build = module()
    key = "vertus_scoop"
    entry = build.SOURCES[key]
    build.SOURCES[key] = (
        *entry[:2],
        (ANCHORS["vertus_energy"] + timedelta(days=days)).isoformat(),
        entry[3],
    )
    with pytest.raises(ValueError, match="outside the permitted window"):
        build.build(tmp_path / "refused")
    assert not (tmp_path / "refused").exists()


@pytest.mark.parametrize("days", [-365, 180])
def test_build_accepts_both_source_window_boundaries(days: int) -> None:
    build = module()
    key = "vertus_scoop"
    entry = build.SOURCES[key]
    build.SOURCES[key] = (
        *entry[:2],
        (ANCHORS["vertus_energy"] + timedelta(days=days)).isoformat(),
        entry[3],
    )
    build.check_date("vertus_energy", key)


def test_earlier_company_site_is_allowed_but_other_company_site_is_not() -> None:
    build = module()
    build.check_date("helico", "helico_early_site")
    with pytest.raises(ValueError, match="outside the permitted window"):
        build.check_date("croptide", "argo_site")
    entry = build.SOURCES["helico_early_site"]
    build.SOURCES["helico_early_site"] = (*entry[:2], "2022-11-06", entry[3])
    with pytest.raises(ValueError, match="outside the permitted window"):
        build.check_date("helico", "helico_early_site")


@pytest.mark.parametrize("days", [-366, 181])
def test_market_window_has_no_earlier_capture_exception(days: int) -> None:
    build = module()
    entry = build.MARKETS["vertus_energy"][0]
    build.MARKETS["vertus_energy"][0] = (
        *entry[:2],
        (ANCHORS["vertus_energy"] + timedelta(days=days)).isoformat(),
        *entry[3:],
    )
    with pytest.raises(ValueError, match="market capture outside window"):
        build.market_values("vertus_energy")


def test_future_year_and_duplicate_publishers_are_refused() -> None:
    build = module()
    entry = build.MARKETS["vertus_energy"][0]
    build.MARKETS["vertus_energy"][0] = (*entry[:3], 2022, *entry[4:])
    with pytest.raises(ValueError, match="year after anchor"):
        build.market_values("vertus_energy")
    build.MARKETS["vertus_energy"] = [entry, entry]
    with pytest.raises(ValueError, match="distinct publishers"):
        build.market_values("vertus_energy")


def test_market_medians_match_exact_publisher_inputs() -> None:
    # Exact rational calculations from the source figures, independent of application math.
    expected = {
        "vertus_energy": (
            (Fraction("60.06") + Fraction("25.61")) / 2,
            (Fraction("4.4") + Fraction("5.4")) / 2,
        ),
        "croptide": (
            (Fraction("1.2") + Fraction("1.44")) / 2,
            (Fraction("14.9") + Fraction("13.9")) / 2,
        ),
        "rosterlab": (
            (Fraction("6.67") + Fraction("6.0")) / 2,
            (Fraction("10.5") + Fraction("9.3")) / 2,
        ),
        "argo_navis": (Fraction("6.7"), Fraction("16.2")),
        "helico": (Fraction("0.0194"), Fraction("3.4")),
    }
    build = module()
    for alt, pair in expected.items():
        assert medians(build.MARKETS[alt]) == pair
        assert build.market_values(alt) == tuple(map(float, pair))
    entry = build.MARKETS["vertus_energy"][0]
    build.MARKETS["vertus_energy"] = [
        ("C", *entry[1:4], "100", "30", *entry[6:]),
        ("A", *entry[1:4], "2", "4", *entry[6:]),
        ("B", *entry[1:4], "6", "8", *entry[6:]),
    ]
    assert build.market_values("vertus_energy") == (6.0, 8.0)


def test_invalid_sidecar_is_refused_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build = module()
    make = build.build_reference_set

    def invalid(project):  # type: ignore[no-untyped-def]
        raw = make(project)
        raw["criteria_from"] = "wrong_project"
        return raw

    monkeypatch.setattr(build, "build_reference_set", invalid)
    with pytest.raises(ValueError, match="Invalid reference cases"):
        build.build(tmp_path / "refused")
    assert not (tmp_path / "refused").exists()


def test_outcome_changes_cannot_change_project_or_dossier() -> None:
    build = module()
    project = build.build_project()
    dossier = build.build_dossier(project)
    build.OUTCOMES = {alt: ("canary outcome", *entry[1:]) for alt, entry in build.OUTCOMES.items()}
    assert build.build_project() == project
    assert build.build_dossier(project) == dossier
    for name in ("project.json", "evidence.json", "rubrics.json"):
        text = (EXAMPLE / name).read_text().lower()
        assert "liquidator" not in text and "larger follow-on round" not in text
    reference = build.build_reference_set(project)
    assert all(case["outcome"]["label"] == "canary outcome" for case in reference["cases"])


@pytest.mark.parametrize("profile", ["technical_ip", "commercial_traction"])
def test_both_profiles_rank_every_company_without_mutating(profile: str) -> None:
    project = repo.load(EXAMPLE / "project.json")
    before = project.model_dump_json()
    cfg = AnalysisConfiguration(method="mavt_sorting", weight_profile_id=profile)
    result = screening.screening_summary(project, cfg)
    assert result.status == "available", result.reason
    assert [row.alternative_id for row in sorted(result.rows, key=lambda r: r.rank or 0)] == (
        EXPECTED_ORDER
    )
    assert all(row.requirements.status == "pass" for row in result.rows)
    assert project.model_dump_json() == before
    text = (EXAMPLE / "README.md").read_text()
    for row in result.rows:
        assert f"| {row.rank} ({row.value:.4f}, {row.class_name})" in text


def test_each_market_row_in_the_readme_names_its_own_company() -> None:
    # Each company's row carries that company's medians, computed independently from its sources.
    build = module()
    readme = (EXAMPLE / "README.md").read_text()
    for alt, name, _ in build.COMPANIES:
        size, growth = medians(build.MARKETS[alt])
        row = f"| {name} | {float(size)} | {float(growth)} | {len(build.MARKETS[alt])} |"
        assert readme.count(row) == 1, row
    section = readme.split("## Market estimates", 1)[1].split("\n\n**", 1)[0]
    firsts = [line.split(" | ")[0][2:] for line in section.splitlines() if line.startswith("| ")]
    assert sorted(firsts[2:]) == sorted(name for _, name, _ in build.COMPANIES)


def test_every_gap_rule_claim_states_its_basis_and_the_counts_match_the_readme() -> None:
    build = module()
    dossier = EvidenceDossier.model_validate_json((EXAMPLE / "evidence.json").read_text())
    descriptions = {
        (c.alternative_id, c.criterion_id): c.source.description for c in dossier.claims
    }
    assert len(build.BASIS) == 39
    counts: dict[str, dict[str, int]] = {alt: {} for alt in ANCHORS}
    for (alt, leaf), basis in build.BASIS.items():
        counts[alt][basis] = counts[alt].get(basis, 0) + 1
        if basis != "observed":
            assert descriptions[(alt, leaf)].startswith("Judgement: " + BASIS_PREFIX[basis])
    for (alt, leaf), text in descriptions.items():
        if (alt, leaf) not in build.BASIS:
            assert not any(text.startswith("Judgement: " + p) for p in BASIS_PREFIX.values())
    assert {alt: c.get("absence", 0) for alt, c in counts.items()} == {
        "vertus_energy": 2,
        "croptide": 5,
        "rosterlab": 5,
        "argo_navis": 7,
        "helico": 3,
    }
    assert all(c.get("sector") == 1 for c in counts.values())
    assert [key for key, basis in build.BASIS.items() if basis == "exception"] == [EXCEPTION_CELL]
    readme = (EXAMPLE / "README.md").read_text()
    assert "| Argo Navis Aerospace | 10 | 7 | 1 | 1 | 19 |" in readme
    assert "| Vertus Energy | 16 | 2 | 1 | 0 | 19 |" in readme


def test_the_window_exception_covers_only_argo_navis_stage(tmp_path: Path) -> None:
    build = module()
    build.check_date("argo_navis", "argo_satnews", "stage")
    for alt, leaf in (
        ("argo_navis", "readiness"),
        ("argo_navis", None),
        ("vertus_energy", "stage"),
    ):
        with pytest.raises(ValueError, match="outside the permitted window"):
            build.check_date(alt, "argo_satnews", leaf)
    raw = build.build_reference_set(build.build_project())
    argo = next(case for case in raw["cases"] if case["id"] == "argo_navis")
    assert "stage" not in {r["criterion_id"] for r in argo["ratings"]}
    assert "argo_satnews" not in raw["sources"]


def test_build_refuses_a_gap_rule_cell_that_overwrites_a_drafted_rating(tmp_path: Path) -> None:
    build = module()
    for alt, cells in build.GAP_RULE_CELLS.items():
        for leaf in cells:
            assert build.CELLS[alt][leaf][2].endswith(cells[leaf][3])
    text = (EXAMPLE / "build.py").read_text()
    marker = '    "vertus_energy": {\n        "board_advisors": ('
    assert text.count(marker) == 1
    duplicate = (
        '    "vertus_energy": {\n        "stage": ("Pre-seed", "vertus_scoop", "observed", "x"),\n'
    )
    copy = tmp_path / "build.py"
    copy.write_text(text.replace(marker, duplicate + '        "board_advisors": ('))
    spec = importlib.util.spec_from_file_location("first_round_duplicate", copy)
    assert spec is not None and spec.loader is not None
    with pytest.raises(ValueError, match="gap-rule cell already rated"):
        spec.loader.exec_module(importlib.util.module_from_spec(spec))


def test_build_refuses_to_write_while_any_cell_is_missing(tmp_path: Path) -> None:
    build = module()
    del build.CELLS["helico"]["milestone_delivery"]
    with pytest.raises(ValueError, match="every cell needs a rating"):
        build.build(tmp_path / "refused")
    assert not (tmp_path / "refused").exists()


def test_outcomes_switch_changes_only_outcomes_and_leaving_out_the_own_case() -> None:
    project = repo.load(EXAMPLE / "project.json")
    reference = ReferenceCases.model_validate_json((EXAMPLE / "reference-cases.json").read_text())
    before = project.fingerprint()
    off = svc.reference_cases(project, reference, project.analysis, alternative_id="vertus_energy")
    on = svc.reference_cases(
        project, reference, project.analysis, alternative_id="vertus_energy", include_outcomes=True
    )
    off_raw, on_raw = off.model_dump(mode="json"), on.model_dump(mode="json")
    assert off_raw != on_raw
    assert off_raw["include_outcomes"] is False
    assert on_raw["include_outcomes"] is True
    assert [c["case_id"] for c in off_raw["alternatives"][0]["cases"]][0] == "vertus_energy"
    assert all(c["outcome"] is None for c in off_raw["alternatives"][0]["cases"])
    assert all(c["outcome"] is not None for c in on_raw["alternatives"][0]["cases"])
    for result in (off_raw, on_raw):
        result["include_outcomes"] = False
        for alt in result["alternatives"]:
            for case in alt["cases"]:
                case["outcome"] = None
    assert off_raw == on_raw
    left = svc.reference_cases(
        project, reference, project.analysis, alternative_id="vertus_energy", exclude_same_id=True
    )
    row = left.alternatives[0]
    assert row.excluded_case_ids == ["vertus_energy"]
    assert "vertus_energy" not in [c.case_id for c in row.cases]
    assert len(row.cases) == 3 and row.not_comparable == []
    assert project.fingerprint() == before
    text = (EXAMPLE / "README.md").read_text()
    for phrase in (
        "Not investment advice. Not a prediction.",
        "Companies neither contacted nor affiliated.",
        "say nothing about the people involved",
        "draft; author review",
        "knew each company's outcome",
        "Survivorship",
        "**seed**",
        "self-match",
        "Leave out this alternative's own case",
        "This rule penalises a thin public record.",
        "Five companies cannot show whether",
    ):
        assert phrase in text


def test_market_oracle_never_imports_the_application() -> None:
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import first_round_market_o"
        "racle; assert not any(m.split('.')[0] == 'mcda_studio' for m in sys.modu"
        "les)"
    )
    subprocess.run([sys.executable, "-I", "-c", code, str(Path(__file__).parent)], check=True)
