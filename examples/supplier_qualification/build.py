"""Builds examples/supplier_qualification/project.json using only the public services API.

A value-based sorting variant of supplier selection: the same five synthetic suppliers, criteria
tree, value functions, profiles and scenario, imported from that example's build script, with
two changes. Logistics cost uses fixed anchors (1.0 to 6.0 NZD/unit, just outside the observed 1.1
to 5.9) because fixed anchors are recommended for sorting. The project adds three ordered classes,
an audit sample and the saved method ``mavt_sorting``. Supplier selection itself is unchanged.

    python examples/supplier_qualification/build.py
"""

import importlib.util
from pathlib import Path
from types import ModuleType

from mcda_studio.domain.project import Project
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.domain.sorting import SortingAudit, SortingModel
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository

HERE = Path(__file__).parent

#: Classes best first: (name, lower boundary on the overall value). Illustrative cut-offs.
CLASSES: list[tuple[str, float | None]] = [
    ("Qualified", 0.70),
    ("Conditional", 0.60),
    ("Not qualified", None),
]
LOGISTICS_RANGE = (1.0, 6.0)  # NZD/unit, fixed anchors
AUDIT = SortingAudit(below_class_id="conditional", sample_size=1, seed=2026)


def _supplier_selection() -> ModuleType:
    path = HERE.parent / "supplier_selection" / "build.py"
    spec = importlib.util.spec_from_file_location("supplier_selection_build", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_project() -> Project:
    p = _supplier_selection().build_project()
    p = p.model_copy(update={"id": "supplier_qualification_example"})  # fixed id: reproducible
    p = ps.update_project_details(
        p,
        "Supplier qualification (example)",
        "Value-based sorting variant of the supplier selection example: five suppliers sorted "
        "into Qualified, Conditional and Not qualified by their overall value.",
        "Procurement team",
    )
    lower, upper = LOGISTICS_RANGE
    p = ps.set_scale(
        p,
        "logistics_cost",
        Scale(type=ScaleType.RATIO, unit="NZD/unit", lower=lower, upper=upper),
    )
    p = ps.set_sorting_model(p, SortingModel(classes=ps.sorting_classes(CLASSES), audit=AUDIT))
    return ps.set_analysis_method(p, "mavt_sorting")


def main() -> None:
    project = build_project()
    JsonProjectRepository().save(project, HERE / "project.json")
    print(f"wrote {HERE / 'project.json'}")


if __name__ == "__main__":
    main()
