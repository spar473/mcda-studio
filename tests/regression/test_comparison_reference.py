"""The method comparison against each method's own result and an independent oracle.

The oracle of every number is the method itself: an ok column's ranks, quantities and classes must
equal that method's own ``/evaluate`` result for the same configuration, and a failed column's
error must equal what ``/evaluate`` returns. ``comparison_oracle`` (plain Python, checked in a clean
interpreter to load no ``mcda_studio`` module) recomputes leaders and agreement from those bodies.
"""

import subprocess
import sys
from pathlib import Path
from typing import Any

import comparison_oracle as oracle
import pytest
from fastapi.testclient import TestClient

from mcda_studio.api import create_app
from mcda_studio.domain.project import Project
from mcda_studio.services import comparison_service as cs
from mcda_studio.storage.json_repository import JsonProjectRepository

from builders import every_section

ROOT = Path(__file__).parents[2]
repo = JsonProjectRepository()


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Any:
    with TestClient(create_app(tmp_path_factory.mktemp("store"), frontend_dir=False)) as c:
        yield c


def projects() -> list[tuple[str, Project, dict[str, Any]]]:
    cases = []
    for name in ("supplier_qualification", "supplier_selection", "nz_deeptech_vc"):
        base = repo.load(ROOT / "examples" / name / "project.json")
        contexts: list[dict[str, Any]] = [{"scenario_id": None}]
        contexts += [{"scenario_id": s.id} for s in base.scenarios]
        contexts += [{"weight_profile_id": p.id} for p in base.weight_profiles]
        for project, label in ((base, "bare"), (every_section(base, 1), "full")):
            for update in contexts:
                cases.append((f"{name}-{label}-{update}", project, update))
    return cases


CASES = projects()


@pytest.mark.parametrize(("case", "project", "update"), CASES, ids=[c[0] for c in CASES])
def test_every_column_is_its_own_method(
    client: TestClient, case: str, project: Project, update: dict[str, Any]
) -> None:
    cfg = project.analysis.model_copy(update={**update, "parameters": {}})
    comparison = cs.compare_methods(project, cfg)
    assert [c.method for c in comparison.columns] == [
        "mavt",
        "mavt_sorting",
        "smaa2",
        "promethee2",
        "ahp",
    ]
    bodies: dict[str, Any] = {}
    for column in comparison.columns:
        response = client.post(
            "/api/evaluate",
            json={
                "project": project.model_dump(mode="json"),
                "configuration": column.configuration.model_dump(mode="json"),
            },
        )
        if column.status == "failed":
            assert response.status_code == column.error.status  # type: ignore[union-attr]
            error = response.json()["error"]
            assert error["code"] == column.error.code  # type: ignore[union-attr]
            assert [d["code"] for d in error["details"] if "code" in d] == column.error.issue_codes  # type: ignore[union-attr]
            assert column.cells == [] and column.leaders == []
            continue
        assert response.status_code == 200
        body = response.json()
        bodies[column.method] = body
        expected = oracle.cells(column.method, body)
        assert [c.alternative_id for c in column.cells] == comparison.alternative_order
        for cell in column.cells:
            own = expected[cell.alternative_id]
            assert (cell.rank, cell.quantity, cell.class_id) == (
                own["rank"],
                own["quantity"],
                own["class"],
            )
        assert column.leaders == oracle.leaders(column.method, body)
    expected_agreement = oracle.agreement(bodies)
    agreement = comparison.agreement
    assert agreement.leaders_agree == expected_agreement["agree"]
    assert {tuple(g.leaders): g.methods for g in agreement.leader_groups} == expected_agreement[
        "groups"
    ]
    assert [(c.alternative_id, c.sorting_class_id, c.smaa_class_id) for c in agreement.classes] == (
        expected_agreement["classes"]
    )
    assert [r.method for r in agreement.reasons] == expected_agreement["reasons"]
    assert all(r.reasons for r in agreement.reasons)


def test_no_field_holds_a_number_from_two_methods() -> None:
    """The comparison's schema: numbers live only in cells, each in one column; agreement holds
    identities, flags, shares already in a cell, and text."""
    project = every_section(
        repo.load(ROOT / "examples" / "supplier_qualification" / "project.json")
    )
    comparison = cs.compare_methods(project)
    smaa = next(c for c in comparison.columns if c.method == "smaa2")
    shares = {cell.alternative_id: cell.class_share for cell in smaa.cells}
    for c in comparison.agreement.classes:
        assert c.smaa_class_share == shares[c.alternative_id]
    dumped = comparison.agreement.model_dump()
    numbers = [v for row in dumped["classes"] for k, v in row.items() if isinstance(v, float)]
    assert numbers == [c.smaa_class_share for c in comparison.agreement.classes]
    assert not any(isinstance(v, float) for v in dumped.values())


def test_the_oracle_imports_nothing_from_mcda_studio() -> None:
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import comparison_oracle; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] == 'mcda_studio'))"
    )
    run = subprocess.run(
        [sys.executable, "-I", "-c", code, str(Path(__file__).parent)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert run.stdout.strip() == "[]"
