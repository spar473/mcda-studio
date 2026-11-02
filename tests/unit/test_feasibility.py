"""The feasibility check: unknowns, independence from every method and preference input, schema
version 6 and the section edits (design note ``docs/design/feasibility-check.md``)."""

import csv
import io
import json
from pathlib import Path
from typing import Any

import pytest

from mcda_studio.domain.criteria import Direction
from mcda_studio.domain.errors import ProjectLoadError, StaleRevisionError, ValidationFailed
from mcda_studio.domain.preferences import WeightProfile
from mcda_studio.domain.project import Project
from mcda_studio.domain.requirements import BoundRequirement, LabelsRequirement
from mcda_studio.services import comparison_service as cs
from mcda_studio.services import feasibility_service as fs
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text

from builders import every_section

ROOT = Path(__file__).parents[2]
repo = JsonProjectRepository()

PRICE = BoundRequirement(
    id="price_cap", name="Within budget", criterion_id="unit_price", unit="NZD", maximum=45
)
CERTIFIED = LabelsRequirement(
    id="certified",
    name="Certified",
    criterion_id="certification",
    allowed=["iso9001", "iso9001_14001"],
)


def supplier() -> Project:
    return repo.load(ROOT / "examples" / "supplier_qualification" / "project.json")


def with_requirements(project: Project | None = None) -> Project:
    return ps.set_requirements(project or supplier(), [PRICE, CERTIFIED])


def statuses(project: Project) -> dict[str, list[str]]:
    result = fs.check_feasibility(project)
    return {
        a.alternative_id: [a.status, *(c.status for c in a.checks)] for a in result.alternatives
    }


def test_the_supplier_example_passes_fails_and_names_what_breaks() -> None:
    result = fs.check_feasibility(with_requirements())
    by_id = {a.alternative_id: a for a in result.alternatives}
    assert by_id["delta"].status == "fail" and by_id["delta"].failed == ["price_cap"]
    assert by_id["delta"].checks[0].reason == "51 NZD is above the maximum 45 NZD"
    assert by_id["cobalt"].failed == ["certified"]
    assert by_id["apex"].status == "pass"
    assert result.label == (
        "feasibility: each requirement is tested on its own measurement; no score offsets a failure"
    )
    assert [s.requirement_id for s in result.summary] == ["price_cap", "certified"]


def test_a_missing_measurement_is_unknown_and_never_outranks_a_failure() -> None:
    p = with_requirements()
    p.performances = [
        m for m in p.performances if (m.alternative_id, m.criterion_id) != ("apex", "unit_price")
    ]
    p.performances = [
        m
        for m in p.performances
        if (m.alternative_id, m.criterion_id) != ("delta", "certification")
    ]
    s = statuses(p)
    assert s["apex"] == ["unknown", "unknown", "pass"]  # one unknown, no failure: unknown
    assert s["delta"] == ["fail", "fail", "unknown"]  # a failure wins over an unknown
    result = fs.check_feasibility(p)
    apex = next(a for a in result.alternatives if a.alternative_id == "apex")
    assert apex.unknown == ["price_cap"] and apex.checks[0].measurement is None
    assert apex.checks[0].reason == "no measurement"


def test_duplicate_measurements_are_unknown_regardless_of_order() -> None:
    p = with_requirements()
    original = next(
        m for m in p.performances if (m.alternative_id, m.criterion_id) == ("apex", "unit_price")
    )
    conflicting = original.model_copy(update={"value": 100.0})
    for entries in ([original, conflicting], [conflicting, original], [original, original]):
        p.performances = [
            m
            for m in p.performances
            if (m.alternative_id, m.criterion_id) != ("apex", "unit_price")
        ] + entries
        apex = next(a for a in fs.check_feasibility(p).alternatives if a.alternative_id == "apex")
        assert apex.status == "unknown"
        assert apex.checks[0].measurement is None
        assert apex.checks[0].reason == "multiple measurements for this alternative and criterion"


@pytest.mark.parametrize(
    ("statuses_", "expected"),
    [
        ([], "pass"),
        (["pass", "pass"], "pass"),
        (["pass", "unknown"], "unknown"),
        (["unknown", "fail"], "fail"),
        (["fail", "pass", "pass", "pass"], "fail"),
    ],
)
def test_overall_is_fail_then_unknown_then_pass(statuses_: list[Any], expected: str) -> None:
    assert fs.overall(statuses_) == expected


def test_limits_are_shown_at_full_precision() -> None:
    assert fs.number(45.0) == "45" and fs.number(0.1) == "0.1"
    assert fs.number(44.99999999999999) == "44.99999999999999"


def test_no_preference_input_or_method_section_changes_the_result() -> None:
    p = with_requirements()
    before = fs.check_feasibility(p).model_dump(exclude={"project_fingerprint"})
    changed = every_section(p, 3)
    changed = ps.add_weight_profile(
        changed,
        WeightProfile(id="other", name="Other", judgements={"unit_price": 1.0}),
    )
    leaf = changed.tree().node("unit_price")
    assert leaf.value_function is not None
    changed = ps.set_value_function(
        changed,
        "unit_price",
        leaf.value_function.model_copy(update={"direction": Direction.INCREASING}),
    )
    changed = ps.set_judgement(changed, "unit_price", 1.0)
    assert changed.fingerprint() != p.fingerprint()
    assert fs.check_feasibility(changed).model_dump(exclude={"project_fingerprint"}) == before


def test_a_failing_alternative_keeps_its_place_in_every_method() -> None:
    bare = every_section(supplier(), 1)
    stated = ps.set_requirements(bare, [PRICE, CERTIFIED])

    def cells(project: Project) -> list[Any]:
        comparison = cs.compare_methods(project, project.analysis)
        return [(c.method, c.status, [x.model_dump() for x in c.cells]) for c in comparison.columns]

    assert cells(stated) == cells(bare)
    assert "delta" in [
        c.alternative_id for c in cs.compare_methods(stated, stated.analysis).columns[0].cells
    ]


def test_requirement_errors_block_only_the_feasibility_result() -> None:
    p = ps.set_requirements(supplier(), [PRICE.model_copy(update={"unit": "USD"})])
    with pytest.raises(ValidationFailed) as caught:
        fs.check_feasibility(p)
    assert [i.code for i in caught.value.report.issues] == ["REQUIREMENT_UNIT_MISMATCH"]
    assert caught.value.report.issues[0].path == "requirements[price_cap].unit"
    assert cs.compare_methods(p, p.analysis).columns[0].status == "ok"


def test_a_project_without_requirements_has_no_feasibility_result() -> None:
    with pytest.raises(ValidationFailed) as caught:
        fs.check_feasibility(supplier())
    assert [i.code for i in caught.value.report.issues] == ["NO_REQUIREMENTS"]


# ---- schema version 6 and edits ---------------------------------------------------------------
def test_the_section_needs_version_6_and_clearing_restores_the_bytes() -> None:
    start = supplier()
    text = to_json_text(with_requirements(start))
    assert json.loads(text)["schema_version"] == 6 and '"requirements"' in text
    cleared = ps.clear_requirements(with_requirements(start))
    assert to_json_text(cleared) == to_json_text(start)
    assert '"requirements"' not in to_json_text(start) and start.required_schema_version() == 2
    raw = json.loads(text)
    raw["schema_version"] = 5
    with pytest.raises(ProjectLoadError, match="schema version 5 cannot contain 'requirements'"):
        repo.from_dict(raw)
    assert repo.from_dict(json.loads(text)).requirements == [PRICE, CERTIFIED]


def test_an_empty_list_is_never_written() -> None:
    p = ps.set_requirements(supplier(), [])
    assert p.requirements is None and '"requirements"' not in to_json_text(p)
    removed = ps.set_requirements(with_requirements(), [])
    assert to_json_text(removed) == to_json_text(supplier())


def test_removing_a_criterion_removes_its_requirements() -> None:
    p = ps.remove_criterion(with_requirements(), "unit_price")
    assert [r.id for r in p.requirements or []] == ["certified"]
    p = ps.remove_criterion(p, "certification")
    assert p.requirements is None and '"requirements"' not in to_json_text(p)


def test_removing_a_label_is_reported_not_repaired() -> None:
    p = with_requirements()
    leaf = p.tree().node("certification")
    assert leaf.scale is not None
    shorter = leaf.scale.model_copy(update={"labels": ["none", "iso9001"]})
    p.criteria = [
        c.model_copy(update={"scale": shorter}) if c.id == "certification" else c
        for c in p.criteria
    ]
    assert p.requirements is not None and p.requirements[1].allowed == ["iso9001", "iso9001_14001"]
    codes = [i.code for i in fs.check_requirements(p)]
    assert codes == ["UNKNOWN_REQUIRED_LABEL"]


def test_an_allow_everything_requirement_warns_but_still_checks() -> None:
    every = LabelsRequirement(
        id="any", name="Any", criterion_id="region", allowed=["overseas", "regional", "domestic"]
    )
    result = fs.check_feasibility(ps.set_requirements(supplier(), [every]))
    assert [i.code for i in result.diagnostics] == ["REQUIREMENT_ALWAYS_PASSES"]
    assert {a.status for a in result.alternatives} == {"pass"}


# ---- exports ------------------------------------------------------------------------------------
def test_the_exports_carry_every_check_and_refuse_a_stale_project() -> None:
    p = with_requirements()
    data, media, filename, result = fs.export_feasibility(p, p.fingerprint(), "json")
    assert media == "application/json" and filename.endswith("-feasibility.json")
    assert json.loads(data) == result.model_dump(mode="json")
    data, media, filename, _ = fs.export_feasibility(p, p.fingerprint(), "csv")
    rows = list(csv.DictReader(io.StringIO(data.decode())))
    assert media == "text/csv" and len(rows) == len(p.alternatives) * 2
    delta = [r for r in rows if r["alternative_id"] == "delta"]
    assert [(r["requirement_id"], r["status"], r["overall_status"]) for r in delta] == [
        ("price_cap", "fail", "fail"),
        ("certified", "pass", "fail"),
    ]
    assert delta[0]["measurement"] == "51.0" and delta[0]["label"] == result.label
    with pytest.raises(StaleRevisionError):
        fs.export_feasibility(p, "0" * 64, "json")
