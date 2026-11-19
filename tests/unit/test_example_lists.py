"""The hand-kept lists of bundled examples (docs/design/method-exemplars.md, section 4).

Three release scripts each keep their own tuple or set of example names. They are read here as
source, without importing them, so that a new example cannot be added to one list only.
`build_release.py` has always omitted `nz_venture_screening`; that is recorded, not changed here.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
PATHS = {
    "hatch_build": ROOT / "hatch_build.py",
    "build_release": ROOT / "scripts" / "build_release.py",
    "smoke_install": ROOT / "scripts" / "smoke_install.py",
}

#: Methods-exemplar studies that every list must carry (extended as each study lands).
EXEMPLARS = ["clinic_site_selection", "flood_defence_options", "engineering_trade_study"]


def names(script: str) -> list[str]:
    tree = ast.parse(PATHS[script].read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "EXAMPLES" for t in node.targets
        ):
            value = ast.literal_eval(node.value)
            return sorted(value)
    raise AssertionError(f"no EXAMPLES in {PATHS[script]}")


@pytest.mark.parametrize("script", PATHS)
@pytest.mark.parametrize("example", EXEMPLARS)
def test_every_list_carries_each_exemplar(script: str, example: str) -> None:
    assert example in names(script)


def test_the_smoke_list_equals_the_wheel_list() -> None:
    assert names("smoke_install") == names("hatch_build")


def test_the_release_check_list_is_inside_the_wheel_list() -> None:
    assert set(names("build_release")) <= set(names("hatch_build"))


@pytest.mark.parametrize("script", PATHS)
def test_every_listed_example_has_a_project_and_a_readme(script: str) -> None:
    for name in names(script):
        assert (ROOT / "examples" / name / "project.json").is_file(), name
        assert (ROOT / "examples" / name / "README.md").is_file(), name
