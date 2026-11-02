"""The feasibility check against an independent oracle, at every exact limit.

For every bundled example, each numeric leaf gets bounds placed exactly at, and one floating-point
step either side of, every alternative's measurement, inclusive and exclusive; each labelled leaf
gets every "at least" and "at most" set (ordinal) or every single label (categorical). Variants add
a missing measurement, a label on a numeric leaf, a number on a labelled leaf and an unknown label.
``feasibility_oracle`` (plain Python, checked in a clean interpreter to load no ``mcda_studio``
module) recomputes every status, reason class and overall status from the project JSON.
"""

import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import feasibility_oracle as oracle
import pytest

from mcda_studio.domain.errors import ValidationFailed
from mcda_studio.domain.project import Project
from mcda_studio.services import feasibility_service as fs

ROOT = Path(__file__).parents[2]
EXAMPLES = (
    "supplier_qualification",
    "supplier_selection",
    "nz_deeptech_vc",
    "infrastructure_procurement",
)

REASON_CLASSES = (
    ("missing", r"^no measurement$"),
    ("label_on_numeric", r"^'.*' is a label, not a number$"),
    ("number_on_labels", r"^\S+ is a number, not a label$"),
    ("unknown_label", r"^'.*' is not one of the scale's labels$"),
    ("below_minimum", r" is below the minimum "),
    ("not_above_minimum", r" is not above the exclusive minimum "),
    ("above_maximum", r" is above the maximum "),
    ("not_below_maximum", r" is not below the exclusive maximum "),
    ("within", r" is within the limits$"),
    ("allowed", r" is allowed$"),
    ("not_allowed", r" is not one of the allowed labels "),
)


def reason_class(reason: str) -> str:
    found = [name for name, pattern in REASON_CLASSES if re.search(pattern, reason)]
    assert len(found) == 1, reason
    return found[0]


def requirements_for(data: dict[str, Any]) -> list[dict[str, Any]]:
    leaves = oracle._leaves(data)
    out: list[dict[str, Any]] = []

    def bound(leaf: dict[str, Any], tag: str, **limits: Any) -> None:
        out.append(
            {
                "kind": "bound",
                "id": f"{leaf['id']}_{len(out)}_{tag}",
                "name": f"{leaf['name']} {tag}",
                "criterion_id": leaf["id"],
                "unit": leaf["scale"].get("unit"),
                **limits,
            }
        )

    for leaf in leaves.values():
        scale = leaf["scale"]
        if scale["type"] in oracle.NUMERIC:
            values = sorted(
                {p["value"] for p in data["performances"] if p["criterion_id"] == leaf["id"]}
            )
            for x in values:
                below, above = math.nextafter(x, -math.inf), math.nextafter(x, math.inf)
                for inclusive in (True, False):
                    for limit in (below, x, above):
                        bound(leaf, "min", minimum=limit, minimum_inclusive=inclusive)
                        bound(leaf, "max", maximum=limit, maximum_inclusive=inclusive)
                bound(leaf, "point", minimum=x, maximum=x)
                bound(
                    leaf,
                    "tight",
                    minimum=below,
                    maximum=above,
                    minimum_inclusive=False,
                    maximum_inclusive=False,
                )
            bound(leaf, "both", minimum=values[0], maximum=values[-1], maximum_inclusive=False)
            continue
        labels = scale["labels"]
        sets = (
            [labels[k:] for k in range(len(labels))] + [labels[: k + 1] for k in range(len(labels))]
            if scale["type"] == "ordinal"
            else [[label] for label in labels]
        )
        for allowed in sets:
            out.append(
                {
                    "kind": "labels",
                    "id": f"{leaf['id']}_{len(out)}_labels",
                    "name": f"{leaf['name']} in {allowed}",
                    "criterion_id": leaf["id"],
                    "allowed": allowed,
                }
            )
    return out


def spoil(data: dict[str, Any]) -> dict[str, Any]:
    """One alternative loses a measurement, and others carry the wrong kind of value."""
    leaves = oracle._leaves(data)
    numeric = [c for c, leaf in leaves.items() if leaf["scale"]["type"] in oracle.NUMERIC]
    labelled = [c for c, leaf in leaves.items() if leaf["scale"]["type"] not in oracle.NUMERIC]
    alts = [a["id"] for a in data["alternatives"]]
    out = json.loads(json.dumps(data))
    out["performances"] = [
        p
        for p in out["performances"]
        if (p["alternative_id"], p["criterion_id"]) != (alts[0], numeric[0])
    ]
    for p in out["performances"]:
        cell = (p["alternative_id"], p["criterion_id"])
        if cell == (alts[1], numeric[-1]):
            p["value"] = leaves[labelled[0]]["scale"]["labels"][0]
        elif cell == (alts[2], labelled[0]):
            p["value"] = 1.0
        elif cell == (alts[3], labelled[-1]):
            p["value"] = "not a label of this scale"
    return out


def cases() -> list[tuple[str, dict[str, Any]]]:
    out = []
    for name in EXAMPLES:
        data = json.loads((ROOT / "examples" / name / "project.json").read_text(encoding="utf-8"))
        data["requirements"] = requirements_for(data)
        out.append((name, data))
        out.append((f"{name}-spoiled", spoil(data)))
    return out


CASES = cases()


@pytest.mark.parametrize(("case", "data"), CASES, ids=[c[0] for c in CASES])
def test_every_status_and_reason_matches_the_oracle(case: str, data: dict[str, Any]) -> None:
    result = fs.check_feasibility(Project.model_validate(data))
    expected = oracle.evaluate(data)
    assert [a.alternative_id for a in result.alternatives] == [
        a["id"] for a in data["alternatives"]
    ]
    for a in result.alternatives:
        mine = [(c.status, reason_class(c.reason)) for c in a.checks]
        assert mine == expected[a.alternative_id]["checks"], a.alternative_id
        assert a.status == expected[a.alternative_id]["status"]
        assert a.failed == [c.requirement_id for c in a.checks if c.status == "fail"]
        assert a.unknown == [c.requirement_id for c in a.checks if c.status == "unknown"]
    for k, s in enumerate(result.summary):
        statuses = [expected[a]["checks"][k][0] for a in expected]
        assert (s.passed, s.failed, s.unknown) == tuple(
            statuses.count(v) for v in ("pass", "fail", "unknown")
        )
    warnings = [i.code for i in result.diagnostics]
    assert warnings == [c for c, sev in oracle.issues(data) if sev == "warning"]


@pytest.mark.parametrize(("case", "data"), CASES, ids=[c[0] for c in CASES])
def test_the_cases_reach_every_outcome(case: str, data: dict[str, Any]) -> None:
    classes = {c for a in oracle.evaluate(data).values() for _, c in a["checks"]}
    numeric_only = {"below_minimum", "not_above_minimum", "above_maximum", "not_below_maximum"}
    assert numeric_only | {"within"} <= classes
    assert {"allowed", "not_allowed"} <= classes
    if case.endswith("spoiled"):
        assert {"missing", "label_on_numeric", "number_on_labels", "unknown_label"} <= classes


def test_an_exact_limit_is_compared_exactly() -> None:
    data = dict(CASES[0][1])
    x = 45.0
    data["performances"] = [
        {**p, "value": x} if p["criterion_id"] == "unit_price" else p for p in data["performances"]
    ]
    data["requirements"] = [
        {
            "kind": "bound",
            "id": "at",
            "name": "at",
            "criterion_id": "unit_price",
            "unit": "NZD",
            "maximum": x,
        },
        {
            "kind": "bound",
            "id": "open",
            "name": "open",
            "criterion_id": "unit_price",
            "unit": "NZD",
            "maximum": x,
            "maximum_inclusive": False,
        },
        {
            "kind": "bound",
            "id": "step",
            "name": "step",
            "criterion_id": "unit_price",
            "unit": "NZD",
            "maximum": math.nextafter(x, -math.inf),
        },
    ]
    result = fs.check_feasibility(Project.model_validate(data))
    assert [c.status for c in result.alternatives[0].checks] == ["pass", "fail", "fail"]
    assert result.alternatives[0].checks[2].reason == (
        f"45 NZD is above the maximum {math.nextafter(x, -math.inf)!r} NZD"
    )


INVALID: list[tuple[str, list[dict[str, Any]]]] = [
    ("none", []),
    (
        "duplicate",
        [
            {
                "kind": "labels",
                "id": "x",
                "name": "x",
                "criterion_id": "region",
                "allowed": ["domestic"],
            }
        ]
        * 2,
    ),
    (
        "unknown leaf",
        [
            {
                "kind": "labels",
                "id": "x",
                "name": "x",
                "criterion_id": "nowhere",
                "allowed": ["domestic"],
            }
        ],
    ),
    (
        "non-leaf",
        [
            {
                "kind": "bound",
                "id": "x",
                "name": "x",
                "criterion_id": "cost",
                "unit": None,
                "maximum": 1,
            }
        ],
    ),
    (
        "bound on labels",
        [
            {
                "kind": "bound",
                "id": "x",
                "name": "x",
                "criterion_id": "region",
                "unit": None,
                "maximum": 1,
            }
        ],
    ),
    (
        "labels on a number",
        [
            {
                "kind": "labels",
                "id": "x",
                "name": "x",
                "criterion_id": "unit_price",
                "allowed": ["domestic"],
            }
        ],
    ),
    (
        "unit",
        [
            {
                "kind": "bound",
                "id": "x",
                "name": "x",
                "criterion_id": "unit_price",
                "unit": "USD",
                "maximum": 45,
            }
        ],
    ),
    (
        "no unit",
        [
            {
                "kind": "bound",
                "id": "x",
                "name": "x",
                "criterion_id": "unit_price",
                "unit": None,
                "maximum": 45,
            }
        ],
    ),
    (
        "empty bound",
        [{"kind": "bound", "id": "x", "name": "x", "criterion_id": "unit_price", "unit": "NZD"}],
    ),
    (
        "empty labels",
        [{"kind": "labels", "id": "x", "name": "x", "criterion_id": "region", "allowed": []}],
    ),
    (
        "crossed",
        [
            {
                "kind": "bound",
                "id": "x",
                "name": "x",
                "criterion_id": "unit_price",
                "unit": "NZD",
                "minimum": 50,
                "maximum": 40,
            }
        ],
    ),
    (
        "open point",
        [
            {
                "kind": "bound",
                "id": "x",
                "name": "x",
                "criterion_id": "unit_price",
                "unit": "NZD",
                "minimum": 45,
                "maximum": 45,
                "minimum_inclusive": False,
            }
        ],
    ),
    (
        "unknown label",
        [
            {
                "kind": "labels",
                "id": "x",
                "name": "x",
                "criterion_id": "region",
                "allowed": ["domestic", "lunar"],
            }
        ],
    ),
]


@pytest.mark.parametrize(("case", "requirements"), INVALID, ids=[c[0] for c in INVALID])
def test_every_validation_code_matches_the_oracle(
    case: str, requirements: list[dict[str, Any]]
) -> None:
    data = json.loads(
        (ROOT / "examples" / "supplier_qualification" / "project.json").read_text(encoding="utf-8")
    )
    data["requirements"] = requirements or None
    project = Project.model_validate(data)
    with pytest.raises(ValidationFailed) as caught:
        fs.check_feasibility(project)
    codes = [(i.code, i.severity.value) for i in caught.value.report.issues]
    assert codes == oracle.issues(data)


def test_the_oracle_imports_nothing_from_mcda_studio() -> None:
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import feasibility_oracle; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] in ('mcda_studio', 'numpy')))"
    )
    run = subprocess.run(
        [sys.executable, "-I", "-c", code, str(Path(__file__).parent)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert run.stdout.strip() == "[]"
