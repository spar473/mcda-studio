import json
from pathlib import Path

import pytest
from derived_oracle import answers

from mcda_studio.domain.derived import DerivedModel
from mcda_studio.methods.mavt.aggregation import evaluate_mavt
from mcda_studio.services import derived_service as derived
from mcda_studio.storage.json_repository import JsonProjectRepository

EXAMPLE = Path(__file__).parents[2] / "examples/derived_measurements"


@pytest.mark.parametrize("name", ["venture", "supplier"])
def test_demo_calculations_compile_reopen_and_rank_against_rational_oracle(name, tmp_path):
    raw = json.loads((EXAMPLE / f"{name}-model.json").read_text())
    model = DerivedModel.model_validate(raw)
    repo = JsonProjectRepository()
    p = repo.load(EXAMPLE / f"{name}-project.json")
    report = derived.preview(p, model)
    assert not report.issues
    assert {c.id: c.value for c in report.calculations} == {
        key: float(v) for key, v in answers(name, raw).items()
    }
    compiled = derived.compile_copy(p, model, report.review_digest)
    repo.save(compiled, tmp_path / "copy.json")
    reopened = repo.load(tmp_path / "copy.json")
    assert evaluate_mavt(compiled).model_dump_json() == evaluate_mavt(reopened).model_dump_json()
    assert evaluate_mavt(reopened).ranking[0].alternative_id == ("b" if name == "venture" else "a")
