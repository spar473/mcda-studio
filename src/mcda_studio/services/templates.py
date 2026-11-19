"""Legacy structure-only templates, loaded from local data without template-name dispatch."""

import json
from collections.abc import Callable
from importlib import resources
from typing import Any

from mcda_studio.domain.criteria import CriterionNode
from mcda_studio.domain.errors import UnknownReferenceError
from mcda_studio.domain.project import Project
from mcda_studio.runtime import source_checkout
from mcda_studio.services import project_service as ps


def _definitions() -> dict[str, dict[str, object]]:
    # Structure definitions are immutable application data, independent of the user's examples.
    checkout = source_checkout()
    text = (
        (checkout / "examples/starter_templates/legacy.json").read_text(encoding="utf-8")
        if checkout is not None
        else resources.files("mcda_studio")
        .joinpath("_examples/starter_templates/legacy.json")
        .read_text(encoding="utf-8")
    )
    data: dict[str, dict[str, object]] = json.loads(text)
    return data


def _factory(description: str, criteria: Any) -> Callable[[str], Project]:
    def create(title: str) -> Project:
        project = ps.new_project(title, description=description)
        project.criteria = [CriterionNode.model_validate(node) for node in criteria]
        return project

    return create


TEMPLATES = {
    name: _factory(str(definition["description"]), definition["criteria"])
    for name, definition in _definitions().items()
}


def from_template(name: str, title: str) -> Project:
    try:
        return TEMPLATES[name](title)
    except KeyError:
        raise UnknownReferenceError(
            f"unknown template {name!r} (available: {', '.join(sorted(TEMPLATES))})"
        ) from None
