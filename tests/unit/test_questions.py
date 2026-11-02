"""The first research-question slice never treats missing measurements as zero."""

import json
from pathlib import Path

from typer.testing import CliRunner

from mcda_studio.cli import app
from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.requirements import BoundRequirement
from mcda_studio.domain.results import SmaaResult, SortingSensitivityResult
from mcda_studio.services import analysis_service, project_service, questions_service
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text

from builders import every_section

ROOT = Path(__file__).parents[2]


def test_missing_measurement_and_unknown_requirement_preserve_project():
    p = JsonProjectRepository().load(ROOT / "examples/supplier_qualification/project.json")
    p = project_service.set_requirements(
        p,
        [
            BoundRequirement(
                id="cap", name="Price cap", criterion_id="unit_price", unit="NZD", maximum=45
            )
        ],
    )
    p.performances = [
        m for m in p.performances if (m.alternative_id, m.criterion_id) != ("apex", "unit_price")
    ]
    before = to_json_text(p)
    result = questions_service.open_questions(p)
    assert [(q.code, q.alternative_id, q.criterion_id) for q in result.questions] == [
        ("MISSING_MEASUREMENT", "apex", "unit_price"),
        ("UNKNOWN_REQUIREMENT", "apex", "unit_price"),
    ]
    assert result.questions[1].requirement_id == "cap"
    assert result.project_fingerprint == p.fingerprint() and to_json_text(p) == before
    assert "not global robustness" in result.limitations[0]


def test_zero_is_present_and_cli_exposes_limits():
    p = JsonProjectRepository().load(ROOT / "examples/supplier_qualification/project.json")
    p = project_service.set_performance(p, "apex", "unit_price", 0.0)
    assert not any(
        q.code == "MISSING_MEASUREMENT" for q in questions_service.open_questions(p).questions
    )
    result = CliRunner().invoke(
        app, ["open-questions", str(ROOT / "examples/supplier_qualification/project.json")]
    )
    assert result.exit_code == 0 and "not global robustness" in result.stdout


def test_weight_question_matches_existing_vc_reference():
    p = JsonProjectRepository().load(ROOT / "examples/nz_deeptech_vc/project.json")
    result = questions_service.open_questions(p)
    team = next(q for q in result.questions if q.criterion_id == "team")
    assert team.code == "WEIGHT_WINNER_CHANGE"
    sweep = analysis_service.sensitivity(p, "team", AnalysisConfiguration(method="mavt"), 2)
    assert any(
        repr(c.weight) in team.why
        for c in (sweep.first_winner_change_down, sweep.first_winner_change_up)
        if c is not None
    )
    assert team.alternative_id in {"forever_harvest", "outlier_space"}
    assert "One-way MAVT weight sensitivity" in result.coverage


def test_method_disagreement_names_each_methods_own_leaders():
    p = JsonProjectRepository().load(ROOT / "examples/supplier_qualification/project.json")
    result = questions_service.open_questions(every_section(p, 1))
    question = next(q for q in result.questions if q.code == "METHOD_LEADER_DISAGREEMENT")
    assert "MAVT (additive value): Apex Components" in question.why
    assert "AHP (pairwise priorities): Delta Parts" in question.why
    assert any("not independent validation" in note for note in result.limitations)


def test_class_questions_reuse_boundary_engine_and_keep_project_unchanged():
    p = JsonProjectRepository().load(ROOT / "examples/supplier_qualification/project.json")
    before = to_json_text(p)
    result = questions_service.open_questions(p)
    questions = [q for q in result.questions if q.code == "WEIGHT_CLASS_CHANGE"]
    assert questions
    sources = analysis_service.sensitivity_all(p, AnalysisConfiguration(method="mavt_sorting"), 2)
    for question in questions:
        sweep = next(s for s in sources if s.node_id == question.criterion_id)
        assert isinstance(sweep, SortingSensitivityResult)
        row = next(r for r in sweep.class_changes if r.alternative_id == question.alternative_id)
        assert any(
            repr(c.weight) in question.why
            for c in (row.first_change_down, row.first_change_up)
            if c
        )
        assert "higher class applies" in question.why
    assert to_json_text(p) == before


def test_smaa_questions_reuse_the_heuristic_and_exact_run_settings():
    p = every_section(
        JsonProjectRepository().load(ROOT / "examples/supplier_qualification/project.json"), 1
    )
    cfg = AnalysisConfiguration(method="smaa2", parameters={"samples": 1000, "seed": 19})
    source = analysis_service.evaluate_project(p, cfg)
    assert isinstance(source, SmaaResult)
    result = questions_service.open_questions(p, cfg)
    questions = [q for q in result.questions if q.code == "SMAA_INPUT_TO_CHECK"]
    assert len(questions) == len(source.inputs_to_check) > 0
    for question, item in zip(questions, source.inputs_to_check, strict=True):
        assert source.inputs_to_check_label in question.why
        assert item.path in question.why and repr(item.difference) in question.why
        assert "1000 draws, seed 19" in question.why


def test_dossier_questions_keep_provenance_and_reject_stale_dossiers():
    p = JsonProjectRepository().load(ROOT / "examples/nz_deeptech_vc/project.json")
    dossier = EvidenceDossier.model_validate_json(
        (ROOT / "examples/evidence_demo/vc.json").read_text(encoding="utf-8")
    )
    before = to_json_text(p)
    result = questions_service.open_questions(p, dossier=dossier)
    evidence = [q for q in result.questions if q.group == "evidence_quality"]
    assert {q.code for q in evidence} == {
        "UNREVIEWED_CLAIM",
        "OUTDATED_CLAIM",
        "CONFLICTING_CLAIMS",
        "MEASUREMENT_WITHOUT_ACCEPTED_SUPPORT",
    }
    claim_questions = [q for q in evidence if q.code != "MEASUREMENT_WITHOUT_ACCEPTED_SUPPORT"]
    assert all(
        q.alternative_id == "hyades" and q.criterion_id == "market_size" for q in claim_questions
    )
    support = [q for q in evidence if q.code == "MEASUREMENT_WITHOUT_ACCEPTED_SUPPORT"]
    assert len(support) == len(p.alternatives) * len(p.tree().leaves())
    assert all("not a finding that the value is invalid" in q.why for q in support)
    assert "Example analyst" in next(q.why for q in evidence if q.code == "UNREVIEWED_CLAIM")
    assert to_json_text(p) == before
    p.title = "Changed"
    stale = questions_service.open_questions(p, dossier=dossier)
    assert not any(q.group == "evidence_quality" for q in stale.questions)
    assert any("EVIDENCE_STALE_PROJECT" in note for note in stale.limitations)


def test_only_a_reviewed_range_matching_the_entered_value_is_screened(tmp_path):
    p = JsonProjectRepository().load(ROOT / "examples/supplier_qualification/project.json")
    dossier = EvidenceDossier.model_validate_json(
        (ROOT / "examples/evidence_demo/supplier.json").read_text(encoding="utf-8")
    )
    # The example's accepted claim is 40, but the project still contains 42.
    result = questions_service.open_questions(p, dossier=dossier)
    assert not any(q.code == "MEASUREMENT_RANGE_CHANGE" for q in result.questions)
    assert any("not the entered measurement" in note for note in result.limitations)
    claim = dossier.claims[0]
    claim.value = 42.0
    claim.uncertainty_lower = 20.0
    claim.uncertainty_upper = 60.0
    result = questions_service.open_questions(p, dossier=dossier)
    assert "Single-measurement fixed-anchor range screening" in result.coverage
    assert any("not treated as a probability" in note for note in result.limitations)
    question = next(q for q in result.questions if q.code == "MEASUREMENT_RANGE_CHANGE")
    assert question.alternative_id == "apex" and question.criterion_id == "unit_price"
    assert "rank and class" in question.why
    assert question.measurement_range is not None
    assert {c.kind for c in question.measurement_range.boundary_contacts} == {"rank", "class"}
    dossier_file = tmp_path / "range.json"
    dossier_file.write_text(dossier.model_dump_json(), encoding="utf-8")
    cli_result = CliRunner().invoke(
        app,
        [
            "open-questions",
            str(ROOT / "examples/supplier_qualification/project.json"),
            "--evidence-file",
            str(dossier_file),
        ],
    )
    assert cli_result.exit_code == 0
    cli_screen = next(
        q["measurement_range"]
        for q in json.loads(cli_result.stdout)["questions"]
        if q["code"] == "MEASUREMENT_RANGE_CHANGE"
    )
    assert cli_screen == question.measurement_range.model_dump(mode="json")
    claim.review = None
    pending = questions_service.open_questions(p, dossier=dossier)
    assert not any(q.code == "MEASUREMENT_RANGE_CHANGE" for q in pending.questions)
