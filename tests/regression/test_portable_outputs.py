"""Pinned bits of the outputs that used to differ between platforms.

One-way sensitivity and SMAA-2 differed between a Mac and Linux in their last bits (a BLAS product,
the C maths library, vector-instruction reductions; see ``docs/design/portable-outputs.md``). These
hashes are the bodies ``scripts/byte_identity.py --portable`` hashes, with the recorded machine held
fixed; Linux x86_64 and native Windows x86_64 produced them identically on 16 November 2026. Every
platform that runs this file must reproduce them. Never update a hash to make a platform pass: a
mismatch means that platform computes different numbers.
"""

import hashlib
import importlib.util
import json
import platform
from pathlib import Path

import pytest

from mcda_studio.domain.uncertainty import GroupUncertainty, SmaaModel
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text

ROOT = Path(__file__).resolve().parents[2]
#: The machine ``byte_identity.py --portable`` reports: Python version, system, processor.
PORTABLE_MACHINE = ("3.12", "Portable", "machine")

PINNED = {
    "infrastructure_procurement/base/sensitivity-all": (
        "acb8409c393e8c22945ca660b7549488a15e6959d534df34a3e47d218d14ae96"
    ),
    "infrastructure_procurement/smaa2-base/evaluate": (
        "0c0bb63faaef831c1fd8cb03fa04436f481ea6898e1b97c7f40315bea0ef0408"
    ),
    "nz_deeptech_vc/base/sensitivity-all": (
        "d392f012125788185d34c2619781a2ae439cce3e87ce60b8cdfda9dba1c6538c"
    ),
    "nz_deeptech_vc/smaa2-base/evaluate": (
        "1fcf195c1be2c4b76369a47f407defbd5c9dfbdf3b2537b03a628bcf5c733a41"
    ),
    "supplier_qualification/base/sensitivity-all": (
        "83ac74434245479f4c7156513e4e0cc72ff0383e5c4f02ad63e9b68417c96132"
    ),
    "supplier_qualification/smaa2-base/evaluate": (
        "e59782b41c6f2a6b3ac64694b7f5143481effe0c424c2ffd40b12b74ede976de"
    ),
    "supplier_selection/base/sensitivity-all": (
        "afb4c0f313f4b14a7954832cb9133977e7a5a1a345f9fbe47b7449d3549b16e1"
    ),
    "supplier_selection/smaa2-base/evaluate": (
        "3e3effc2c2cdcff9b2b8f819b40aed835300b7486d4a252cc38fc58a757604d1"
    ),
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def fixed_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    version, system, machine = PORTABLE_MACHINE
    monkeypatch.setattr(platform, "python_version", lambda: version)
    monkeypatch.setattr(platform, "system", lambda: system)
    monkeypatch.setattr(platform, "machine", lambda: machine)


@pytest.mark.parametrize("key", sorted(PINNED))
def test_the_output_has_the_pinned_bits(key: str, fixed_machine: None) -> None:
    name, context, output = key.split("/")
    project = JsonProjectRepository().load(ROOT / "examples" / name / "project.json")
    base = project.analysis.model_copy(update={"scenario_id": None})
    if output == "sensitivity-all":
        body = json.dumps(
            [r.model_dump(mode="json") for r in svc.sensitivity_all(project, base)], indent=2
        )
    else:
        assert context == "smaa2-base"
        stated = ps.set_smaa_model(
            project, SmaaModel(groups=[GroupUncertainty(parent_id=None, kind="unknown")])
        )
        cfg = stated.analysis.model_copy(
            update={"scenario_id": None, "method": "smaa2", "parameters": {}}
        )
        body = to_json_text(svc.evaluate_project(stated, cfg))
    assert _sha(body) == PINNED[key]


def test_the_machine_is_still_recorded_outside_the_portable_check() -> None:
    """Holding the machine fixed is a test device only: real results still say where they ran."""
    project = JsonProjectRepository().load(
        ROOT / "examples" / "supplier_selection" / "project.json"
    )
    stated = ps.set_smaa_model(
        project, SmaaModel(groups=[GroupUncertainty(parent_id=None, kind="unknown")])
    )
    cfg = stated.analysis.model_copy(update={"method": "smaa2", "parameters": {}})
    result = svc.evaluate_project(stated, cfg)
    assert result.environment == {  # type: ignore[union-attr]
        "python": platform.python_version(),
        "numpy": result.environment["numpy"],  # type: ignore[union-attr]
        "system": f"{platform.system()} {platform.machine()}",
    }


def test_byte_identity_portable_mode_reports_the_same_machine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``byte_identity.py --portable`` holds the machine this file's hashes were made with."""
    spec = importlib.util.spec_from_file_location(
        "byte_identity_script", ROOT / "scripts" / "byte_identity.py"
    )
    assert spec is not None and spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    for name in ("python_version", "system", "machine"):
        monkeypatch.setattr(platform, name, getattr(platform, name))  # restored afterwards
    assert script.PORTABLE_MACHINE == PORTABLE_MACHINE
    script.hold_machine_fixed()
    assert (platform.python_version(), platform.system(), platform.machine()) == PORTABLE_MACHINE
