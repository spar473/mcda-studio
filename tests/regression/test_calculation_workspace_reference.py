"""Edit → recalculate → review → apply → evaluate → reopen, against independent rational answers."""

import json
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path

import pytest
from calculation_workspace_oracle import replay
from derived_oracle import answers

from mcda_studio.domain.calculation_workspace import CalculationWorkspace, DefineSource, ReviewEntry
from mcda_studio.domain.derived import DerivedModel, SourceFactor
from mcda_studio.domain.evidence import Origin, Review
from mcda_studio.methods.mavt.aggregation import evaluate_mavt
from mcda_studio.services import calculation_workspace_service as cw
from mcda_studio.services import derived_service as derived
from mcda_studio.services import provenance_service as provenance
from mcda_studio.storage.json_repository import JsonProjectRepository

EXAMPLE = Path(__file__).parents[2] / "examples/derived_measurements"
WHEN = datetime(2026, 11, 1, 9, tzinfo=UTC)
# A revised value, then a correction, chosen so the leading alternative changes in both domains.
EDITS = {
    "venture": [("adoption_a", "revise", 0.07), ("annual_price_b", "correct", 820.0)],
    "supplier": [("annual_units", "revise", 1200.0), ("price_a", "correct", 47.0)],
}


def accept(factor_id: str, corrected: float | None = None) -> ReviewEntry:
    review = Review(
        status="accepted" if corrected is None else "corrected",
        reviewer="Analyst",
        reviewed_at=WHEN,
        corrected_value=corrected,
    )
    return ReviewEntry(entry="source", id=factor_id, review=review)


def leader(name: str, project_raw: dict, values: dict[str, Fraction]) -> str:
    (criterion,) = project_raw["criteria"]
    targets = {"a": values[f"{'market' if name == 'venture' else 'tco'}_a"]}
    targets["b"] = values[f"{'market' if name == 'venture' else 'tco'}_b"]
    best = max if criterion["value_function"]["direction"] == "increasing" else min
    return best(targets, key=lambda alt: targets[alt])


@pytest.mark.parametrize("name", ["venture", "supplier"])
def test_edited_factors_recalculate_apply_and_reproduce(name, tmp_path):
    repo = JsonProjectRepository()
    project = repo.load(EXAMPLE / f"{name}-project.json")
    project_raw = json.loads((EXAMPLE / f"{name}-project.json").read_text())
    model = DerivedModel.model_validate_json((EXAMPLE / f"{name}-model.json").read_text())
    current = cw.inspect(project, model)
    first = cw.apply(project, current.workspace, current.preview.review_digest, "Analyst", WHEN)
    project = first.bundle.project
    current = first.inspection
    for factor_id, how, value in EDITS[name]:
        if how == "revise":
            factor = next(s for s in current.model.sources if s.id == factor_id)
            revised = SourceFactor.model_validate(
                {
                    **factor.model_dump(),
                    "value": value,
                    "review": None,
                    "origin": Origin(kind="human", proposed_by="Analyst").model_dump(),
                }
            )
            current = cw.propose(
                project,
                current.workspace,
                DefineSource(factor=revised, recorded_at=WHEN),
                current.preview.review_digest,
            )
            assert not current.applicable  # pending review blocks recalculated values
            event = accept(factor_id)
        else:
            event = accept(factor_id, value)
        current = cw.propose(project, current.workspace, event, current.preview.review_digest)
    expected = answers(name, replay(current.workspace.model_dump(mode="json")))
    calculated = {c.formula_id: c.after for c in current.changes}
    assert set(calculated) == set(expected) - {"purchase_volume"}
    for key, value in calculated.items():
        # Exact rational answer vs binary floating point: every input and operation is one
        # rounding of at most u = 2^-53, all terms are positive and there are at most 16
        # roundings, so the relative error is below 16u (Higham 2002, section 3.1).
        assert abs(Fraction(value) - expected[key]) <= Fraction(16, 2**53) * expected[key], key
    applied = cw.apply(project, current.workspace, current.preview.review_digest, "Analyst", WHEN)
    # Applying is exactly the separate compiled copy, and its bundle relates by fingerprint only.
    assert applied.bundle.project == derived.compile_copy(
        project, current.model, current.preview.review_digest
    )
    assert provenance.bind(applied.bundle.project, applied.bundle).relationship == "compiled"
    stored = tmp_path / "project.json"
    repo.save(applied.bundle.project, stored)
    (tmp_path / "workspace.json").write_text(applied.inspection.workspace.model_dump_json())
    reopened_project = repo.load(stored)
    reopened = cw.inspect(
        reopened_project,
        CalculationWorkspace.model_validate_json((tmp_path / "workspace.json").read_text()),
    )
    assert reopened.relationship == "bound" and not any(c.changed for c in reopened.changes)
    assert len(reopened.bindings) == 3
    ranking = evaluate_mavt(reopened_project).ranking
    assert ranking[0].alternative_id == leader(name, project_raw, expected)
    # The original example leader differs, so recalculation is decision-relevant here.
    original = answers(name, json.loads((EXAMPLE / f"{name}-model.json").read_text()))
    assert leader(name, project_raw, original) != ranking[0].alternative_id
