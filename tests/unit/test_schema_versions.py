"""Project files are written with the lowest schema version that can represent them.

An MAVT-only project stays version 1, byte for byte and fingerprint for fingerprint, so older
installations keep opening it; a project with classes is version 2. See the method seam design
note §6 and the value-based sorting design note §7.
"""

import hashlib
import json
from pathlib import Path

import pytest

from mcda_studio.domain.errors import ProjectLoadError
from mcda_studio.domain.project import SCHEMA_VERSION
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps
from mcda_studio.storage import json_repository as jr
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text

from builders import with_classes

ROOT = Path(__file__).parents[2]
MAVT_EXAMPLES = ["nz_deeptech_vc", "supplier_selection", "infrastructure_procurement"]
repo = JsonProjectRepository()
CLASSES = [("Go", 0.6), ("Stop", None)]


def canonical_sha(raw: dict[str, object]) -> str:
    text = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("name", MAVT_EXAMPLES)
def test_an_mavt_only_project_migrates_and_saves_as_version_1_with_identical_bytes(
    name: str, tmp_path: Path
) -> None:
    source = ROOT / "examples" / name / "project.json"
    raw = json.loads(source.read_text())
    assert raw["schema_version"] == 1 and SCHEMA_VERSION > 1
    project = repo.load(source)  # migrated 1 -> 2 in memory
    assert project.schema_version == project.required_schema_version() == 1
    assert repo.save(project, tmp_path / "p.json").read_bytes() == source.read_bytes()
    # the migration changes nothing: the fingerprint is still that of the file's own content
    assert project.fingerprint() == canonical_sha(raw)
    assert "sorting" not in project.model_dump(mode="json")  # absent, never null


def test_a_project_with_classes_is_version_2_and_clearing_them_restores_version_1_bytes(
    tmp_path: Path,
) -> None:
    source = ROOT / "examples" / "supplier_selection" / "project.json"
    project = repo.load(source)
    sorted_ = with_classes(project, CLASSES)
    path = repo.save(sorted_, tmp_path / "sorted.json")
    raw = json.loads(path.read_text())
    assert raw["schema_version"] == 2 and raw["sorting"]["classes"][0]["id"] == "go"
    reloaded = repo.load(path)
    assert reloaded == sorted_ and reloaded.schema_version == 2
    assert reloaded.fingerprint() == sorted_.fingerprint() != project.fingerprint()
    cleared = ps.clear_sorting_model(reloaded)
    assert to_json_text(cleared) == source.read_text()
    assert cleared.fingerprint() == project.fingerprint()


def test_results_report_the_version_the_project_needs() -> None:
    project = repo.load(ROOT / "examples" / "supplier_selection" / "project.json")
    assert svc.evaluate_project(project).schema_version == 1
    assert svc.evaluate_project(with_classes(project, CLASSES)).schema_version == 2


def test_a_version_1_file_cannot_hold_a_version_2_section() -> None:
    raw = with_classes(
        repo.load(ROOT / "examples" / "supplier_selection" / "project.json"), CLASSES
    ).model_dump(mode="json")
    raw["schema_version"] = 1
    with pytest.raises(ProjectLoadError, match="schema version 1 cannot contain 'sorting'"):
        repo.from_dict(raw)


def test_an_older_program_refuses_a_version_2_file_with_its_existing_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = json.loads((ROOT / "examples" / "supplier_qualification" / "project.json").read_text())
    assert raw["schema_version"] == 2
    monkeypatch.setattr(jr, "SCHEMA_VERSION", 1)
    with pytest.raises(ProjectLoadError, match="newer than this program supports"):
        repo.from_dict(raw)


def test_a_declared_version_above_what_the_content_needs_is_written_lower() -> None:
    raw = repo.load(ROOT / "examples" / "supplier_selection" / "project.json").model_dump(
        mode="json"
    )
    raw["schema_version"] = 2  # a hand-edited file: version 2 but no version-2 section
    project = repo.from_dict(raw)
    assert project.schema_version == 1 and project.model_dump(mode="json")["schema_version"] == 1
