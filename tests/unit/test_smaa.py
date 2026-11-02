"""SMAA-2: validation, runs, reproducibility, distributions, the exactness rule, limits, the
section's schema version, and pruning with removed alternatives and criteria."""

import json
from pathlib import Path

import pytest

from mcda_studio.domain.errors import AnalysisLimitError, ProjectLoadError, ValidationFailed
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import SmaaResult
from mcda_studio.domain.scales import AnchorMode
from mcda_studio.domain.uncertainty import (
    CategoricalDistribution,
    CellRef,
    CellUncertainty,
    DiscreteDistribution,
    GroupUncertainty,
    SharedDraw,
    SmaaModel,
    TriangularDistribution,
    UniformDistribution,
)
from mcda_studio.methods.base import validate_analysis
from mcda_studio.methods.mavt import MavtMethod
from mcda_studio.methods.smaa import SmaaMethod, engine
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository, to_json_text

from builders import scored_project, tiny_project

ROOT = Path(__file__).parents[2]
EXAMPLES = [
    "nz_deeptech_vc",
    "supplier_selection",
    "infrastructure_procurement",
    "supplier_qualification",
]
repo = JsonProjectRepository()


def cfg(**parameters: object) -> AnalysisConfiguration:
    return AnalysisConfiguration(method="smaa2", parameters=parameters)


def smaa(project: Project, **parameters: object) -> SmaaResult:
    result = svc.evaluate_project(
        project, project.analysis.model_copy(update={"method": "smaa2", "parameters": parameters})
    )
    assert isinstance(result, SmaaResult)
    return result


def cell(alt: str, crit: str, dist: object) -> CellUncertainty:
    return CellUncertainty(alternative_id=alt, criterion_id=crit, distribution=dist)  # type: ignore[arg-type]


def stated(project: Project, **model: object) -> Project:
    return ps.set_smaa_model(project, SmaaModel(**model))  # type: ignore[arg-type]


def codes(project: Project, configuration: AnalysisConfiguration | None = None) -> list[str]:
    return [i.code for i in validate_analysis(project, configuration or cfg()).issues]


UNKNOWN_TOP = GroupUncertainty(parent_id=None, kind="unknown")
SUPPLIER = ROOT / "examples" / "supplier_qualification" / "project.json"


# ---- validation ----------------------------------------------------------------------------------
def test_mavt_checks_run_unchanged_and_first() -> None:
    project = stated(repo.load(SUPPLIER), groups=[UNKNOWN_TOP])
    mavt = MavtMethod().validate(project, project.analysis)
    mine = SmaaMethod().validate(project, project.analysis.model_copy(update={"method": "smaa2"}))
    assert mine[: len(mavt)] == mavt


def test_nothing_stated_or_nothing_varying_is_refused() -> None:
    plain = scored_project({"a": 0.5, "b": 0.4})
    assert codes(plain) == ["NOTHING_UNCERTAIN"]
    with pytest.raises(ValidationFailed, match="NOTHING_UNCERTAIN"):
        svc.evaluate_project(plain, cfg())
    weights_only = stated(tiny_project(), groups=[UNKNOWN_TOP])
    assert codes(weights_only, cfg(uncertainty="performance")) == ["NOTHING_UNCERTAIN"]
    assert codes(weights_only, cfg(uncertainty="preference")) == []


@pytest.mark.parametrize(
    ("dist", "expected"),
    [
        (UniformDistribution(lower=0.4, upper=0.4), ["INVALID_DISTRIBUTION"]),
        (TriangularDistribution(lower=0.1, mode=0.9, upper=0.5), ["INVALID_DISTRIBUTION"]),
        (DiscreteDistribution(values=[0.1, 0.2], probabilities=[0.5]), ["INVALID_DISTRIBUTION"]),
        (
            DiscreteDistribution(values=[0.1, 0.1], probabilities=[0.5, 0.5]),
            ["INVALID_DISTRIBUTION"],
        ),
        (
            DiscreteDistribution(values=[0.1, 0.2], probabilities=[0.5, 0.4]),
            ["INVALID_DISTRIBUTION"],
        ),
        (
            DiscreteDistribution(values=[0.1, 0.2], probabilities=[1.2, -0.2]),
            ["INVALID_DISTRIBUTION"],
        ),
        (UniformDistribution(lower=0.5, upper=1.2), ["DISTRIBUTION_OUTSIDE_DOMAIN"]),
        (
            CategoricalDistribution(labels=["x"], probabilities=[1.0]),
            ["DISTRIBUTION_SCALE_MISMATCH"],
        ),
        (UniformDistribution(lower=0.2, upper=0.8), []),
    ],
)
def test_each_distribution_rule_has_its_code(dist: object, expected: list[str]) -> None:
    project = stated(scored_project({"a": 0.5, "b": 0.4}), cells=[cell("a", "score", dist)])
    assert codes(project) == expected


def test_cell_group_and_shared_draw_rules() -> None:
    base = tiny_project()
    u = UniformDistribution(lower=10.0, upper=30.0)
    cases: list[tuple[dict[str, object], list[str]]] = [
        ({"cells": [cell("zz", "cost", u)]}, ["UNKNOWN_UNCERTAIN_CELL"]),
        ({"cells": [cell("a", "cost", u), cell("a", "cost", u)]}, ["DUPLICATE_UNCERTAIN_CELL"]),
        ({"dependence": "gaussian copula", "groups": [UNKNOWN_TOP]}, ["UNSUPPORTED_DEPENDENCE"]),
        (
            {"groups": [GroupUncertainty(parent_id="cost", kind="unknown")]},
            ["UNKNOWN_UNCERTAIN_GROUP"],
        ),
        ({"groups": [UNKNOWN_TOP, UNKNOWN_TOP]}, ["DUPLICATE_UNCERTAIN_GROUP"]),
        (
            {
                "groups": [
                    GroupUncertainty(parent_id=None, kind="unknown", intervals={"cost": (1.0, 2.0)})
                ]
            },
            ["UNEXPECTED_RATING_INTERVALS"],
        ),
        (
            {
                "groups": [
                    GroupUncertainty(
                        parent_id=None, kind="rating_intervals", intervals={"cost": (50.0, 100.0)}
                    )
                ]
            },
            ["MISSING_RATING_INTERVAL"],
        ),
        (
            {
                "groups": [
                    GroupUncertainty(
                        parent_id=None,
                        kind="rating_intervals",
                        intervals={"cost": (90.0, 50.0), "quality": (10.0, 20.0)},
                    )
                ]
            },
            ["INVALID_RATING_INTERVAL"],
        ),
        (
            {
                "groups": [
                    GroupUncertainty(
                        parent_id=None,
                        kind="rating_intervals",
                        intervals={"cost": (1.0, 2.0), "quality": (1.0, 2.0), "x": (1.0, 2.0)},
                    )
                ]
            },
            ["UNKNOWN_RATING_INTERVAL"],
        ),
        (
            {
                "groups": [
                    GroupUncertainty(
                        parent_id=None,
                        kind="rating_intervals",
                        intervals={"cost": (0.0, 0.0), "quality": (0.0, 0.0)},
                    )
                ]
            },
            ["ZERO_RATING_INTERVALS"],
        ),
        (
            {
                "cells": [cell("a", "cost", u)],
                "shared_draws": [
                    SharedDraw(id="s", cells=[CellRef(alternative_id="a", criterion_id="cost")])
                ],
            },
            ["INVALID_SHARED_DRAW"],
        ),
        (
            {
                "cells": [cell("a", "cost", u)],
                "shared_draws": [
                    SharedDraw(
                        id="s",
                        cells=[
                            CellRef(alternative_id="a", criterion_id="cost"),
                            CellRef(alternative_id="b", criterion_id="cost"),
                        ],
                    )
                ],
            },
            ["UNKNOWN_SHARED_CELL"],
        ),
        (
            {
                "cells": [cell("a", "cost", u), cell("b", "cost", u)],
                "shared_draws": [
                    SharedDraw(
                        id="s",
                        cells=[
                            CellRef(alternative_id="a", criterion_id="cost"),
                            CellRef(alternative_id="b", criterion_id="cost"),
                        ],
                    ),
                    SharedDraw(
                        id="t",
                        cells=[
                            CellRef(alternative_id="a", criterion_id="cost"),
                            CellRef(alternative_id="b", criterion_id="cost"),
                        ],
                    ),
                ],
            },
            ["DUPLICATE_SHARED_CELL", "DUPLICATE_SHARED_CELL"],
        ),
    ]
    for model, expected in cases:
        assert codes(stated(base, **model)) == expected, model


def test_a_single_child_group_and_a_repeated_shared_draw_are_refused() -> None:
    one_child = stated(scored_project({"a": 0.5, "b": 0.4}), groups=[UNKNOWN_TOP])
    assert codes(one_child) == ["INVALID_GROUP_UNCERTAINTY"]
    u = UniformDistribution(lower=10.0, upper=30.0)
    pair = [
        CellRef(alternative_id="a", criterion_id="cost"),
        CellRef(alternative_id="b", criterion_id="cost"),
    ]
    twice = stated(
        tiny_project(),
        cells=[cell("a", "cost", u), cell("b", "cost", u)],
        shared_draws=[SharedDraw(id="s", cells=pair), SharedDraw(id="s", cells=pair)],
    )
    assert codes(twice) == [
        "DUPLICATE_SHARED_DRAW",
        "DUPLICATE_SHARED_CELL",
        "DUPLICATE_SHARED_CELL",
    ]


def test_local_anchors_and_missing_measurements_still_block() -> None:
    project = stated(
        tiny_project(), cells=[cell("a", "cost", UniformDistribution(lower=10.0, upper=30.0))]
    )
    local = project.model_copy(deep=True)
    node = next(n for n in local.criteria if n.id == "cost")
    assert node.scale is not None
    node.scale.anchor_mode = AnchorMode.LOCAL
    assert "SMAA_LOCAL_ANCHORS_UNCERTAIN" in codes(local)
    missing = ps.clear_performance(project, "a", "cost")
    assert "MISSING_MEASUREMENT" in codes(missing)  # a distribution never fills a missing value


def test_parameters_are_checked_by_the_method() -> None:
    project = stated(tiny_project(), groups=[UNKNOWN_TOP])
    assert codes(project, cfg(samples=10)) == ["INVALID_PARAMETER"]
    assert codes(project, cfg(seed=-1)) == ["INVALID_PARAMETER"]
    assert codes(project, cfg(uncertainty="both")) == ["INVALID_PARAMETER"]
    assert codes(project, cfg(dominance_check=True)) == ["UNKNOWN_PARAMETER"]


# ---- runs and reproducibility --------------------------------------------------------------------
def test_the_same_seed_gives_identical_bytes_and_another_seed_differs() -> None:
    project = stated(tiny_project(), groups=[UNKNOWN_TOP])
    first, again = smaa(project, seed=11), smaa(project, seed=11)
    assert to_json_text(first) == to_json_text(again)
    other = smaa(project, seed=12)
    assert [e.count for e in other.acceptability[0].ranks] != [
        e.count for e in first.acceptability[0].ranks
    ]


@pytest.mark.parametrize(
    ("dist", "expected"),
    [
        (UniformDistribution(lower=0.0, upper=1.0), 0.5),  # P(x > 0.5)
        (TriangularDistribution(lower=0.0, mode=0.0, upper=1.0), 0.25),  # 1 - F(0.5) = (1 - 0.5)^2
        (TriangularDistribution(lower=0.0, mode=1.0, upper=1.0), 0.75),
        (DiscreteDistribution(values=[0.2, 0.8, 0.9], probabilities=[0.6, 0.1, 0.3]), 0.4),
    ],
)
def test_each_distribution_is_sampled_with_its_own_shape(dist: object, expected: float) -> None:
    """a beats b (fixed at 0.5) exactly when its draw exceeds 0.5."""
    model = [
        cell("a", "score", dist),
        cell("c", "score", UniformDistribution(lower=0.0, upper=0.1)),
    ]
    result = smaa(
        stated(scored_project({"a": 0.6, "b": 0.5, "c": 0.05}), cells=model),
        samples=20000,
        seed=3,
        confidence=0.999,
    )
    first = next(r for r in result.acceptability if r.alternative_id == "a").ranks[0]
    assert first.lower is not None and first.upper is not None
    assert first.lower <= expected <= first.upper


def test_each_run_varies_only_its_own_inputs() -> None:
    both = stated(
        tiny_project(),
        groups=[UNKNOWN_TOP],
        cells=[cell("a", "cost", UniformDistribution(lower=10.0, upper=30.0))],
    )
    weights = stated(tiny_project(), groups=[UNKNOWN_TOP])
    cells = stated(
        tiny_project(), cells=[cell("a", "cost", UniformDistribution(lower=10.0, upper=30.0))]
    )
    counts = lambda r: [[e.count for e in row.ranks] for row in r.acceptability]  # noqa: E731
    assert counts(smaa(both, uncertainty="preference", seed=4)) == counts(smaa(weights, seed=4))
    assert counts(smaa(both, uncertainty="performance", seed=4)) == counts(smaa(cells, seed=4))
    assert smaa(both, uncertainty="performance").run == "performance"


def test_a_shared_draw_moves_its_cells_together() -> None:
    # entered values differ, so only drawing both from one uniform can tie them in every draw
    project = scored_project({"a": 0.2, "b": 0.8, "c": 0.0})
    u = UniformDistribution(lower=0.1, upper=0.9)
    refs = [
        CellRef(alternative_id="a", criterion_id="score"),
        CellRef(alternative_id="b", criterion_id="score"),
    ]
    together = smaa(
        stated(
            project,
            cells=[cell("a", "score", u), cell("b", "score", u)],
            shared_draws=[SharedDraw(id="s", cells=refs)],
        )
    )
    a = next(r for r in together.acceptability if r.alternative_id == "a")
    assert a.tied_first.count == together.samples  # identical quantiles every draw
    apart = smaa(stated(project, cells=[cell("a", "score", u), cell("b", "score", u)]))
    assert next(r for r in apart.acceptability if r.alternative_id == "a").tied_first.count == 0


@pytest.mark.parametrize("name", EXAMPLES)
def test_the_bulk_path_gives_exactly_the_fsum_path_ranks_and_classes(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = repo.load(ROOT / "examples" / name / "project.json")
    leaf = project.tree().leaves()[0]
    node = project.tree().node(leaf)
    model: dict[str, object] = {"groups": [UNKNOWN_TOP]}
    if (
        node.scale is not None
        and node.scale.is_numeric
        and node.scale.anchor_mode is AnchorMode.FIXED
    ):
        lo, hi = node.scale.lower, node.scale.upper
        assert lo is not None and hi is not None
        alt = project.alternatives[0].id
        model["cells"] = [cell(alt, leaf, UniformDistribution(lower=lo, upper=hi))]
    project = stated(project, **model)
    bulk = smaa(project, samples=2000, seed=9)
    monkeypatch.setattr(engine, "NEAR_TIE", float("inf"))  # every draw summed with math.fsum
    exact = smaa(project, samples=2000, seed=9)
    assert bulk.acceptability == exact.acceptability


def test_class_acceptability_rows_cover_every_class() -> None:
    project = stated(repo.load(SUPPLIER), groups=[UNKNOWN_TOP])
    result = smaa(project, samples=2000)
    assert [c.class_id for c in result.classes] == ["qualified", "conditional", "not_qualified"]
    for row in result.acceptability:
        assert sum(e.count or 0 for e in row.classes.values()) == result.samples
        assert sum(e.count or 0 for e in row.ranks) == result.samples


def test_inputs_to_check_are_labelled_and_exact_runs_say_why_they_have_none() -> None:
    sampled = smaa(stated(tiny_project(), groups=[UNKNOWN_TOP]))
    assert sampled.inputs_to_check and sampled.inputs_to_check_label.startswith("heuristic")
    assert sampled.inputs_to_check[0].path.startswith("smaa.groups[top].")
    exact = smaa(
        stated(
            scored_project({"a": 0.5, "b": 0.6}),
            cells=[
                cell(
                    "b", "score", DiscreteDistribution(values=[0.4, 0.7], probabilities=[0.5, 0.5])
                )
            ],
        )
    )
    assert exact.inputs_to_check == [] and "EXACT_ENUMERATION" in [
        d.code for d in exact.diagnostics
    ]
    assert sampled.label == "sampled acceptability under these assumptions"


def test_oversized_requests_are_refused() -> None:
    project = repo.load(ROOT / "tests" / "fixtures" / "performance_project.json")
    leaf = project.tree().leaves()[0]
    alt = project.alternatives[0].id
    node = project.tree().node(leaf)
    assert node.scale is not None and node.scale.lower is not None and node.scale.upper is not None
    project = stated(
        project,
        cells=[
            cell(alt, leaf, UniformDistribution(lower=node.scale.lower, upper=node.scale.upper))
        ],
    )
    with pytest.raises(AnalysisLimitError):
        smaa(project, samples=100_000)


# ---- schema version 3 and pruning ----------------------------------------------------------------
def test_stated_uncertainty_makes_version_3_and_clearing_restores_the_bytes(tmp_path: Path) -> None:
    original = repo.load(SUPPLIER)
    project = stated(original, groups=[UNKNOWN_TOP])
    raw = json.loads(repo.save(project, tmp_path / "p.json").read_text())
    assert raw["schema_version"] == 3 and raw["smaa"]["groups"][0]["kind"] == "unknown"
    assert repo.load(tmp_path / "p.json") == project
    assert to_json_text(ps.clear_smaa_model(project)) == SUPPLIER.read_text()
    raw["schema_version"] = 2
    with pytest.raises(ProjectLoadError, match="schema version 2 cannot contain 'smaa'"):
        repo.from_dict(raw)


def test_removing_an_alternative_or_criterion_removes_its_uncertainty() -> None:
    u = UniformDistribution(lower=10.0, upper=30.0)
    refs = [
        CellRef(alternative_id="a", criterion_id="cost"),
        CellRef(alternative_id="b", criterion_id="cost"),
    ]
    project = stated(
        tiny_project(),
        cells=[cell("a", "cost", u), cell("b", "cost", u)],
        shared_draws=[SharedDraw(id="s", cells=refs)],
        groups=[
            GroupUncertainty(
                parent_id=None,
                kind="rating_intervals",
                intervals={"cost": (50.0, 100.0), "quality": (25.0, 75.0)},
            )
        ],
    )
    without_b = ps.remove_alternative(project, "b")
    assert without_b.smaa is not None
    assert [(c.alternative_id, c.criterion_id) for c in without_b.smaa.cells] == [("a", "cost")]
    assert [r.alternative_id for r in without_b.smaa.shared_draws[0].cells] == ["a"]
    without_quality = ps.remove_criterion(project, "quality")
    assert without_quality.smaa is not None
    assert without_quality.smaa.groups[0].intervals == {"cost": (50.0, 100.0)}
    plain = ps.remove_alternative(tiny_project(), "b")
    assert plain.smaa is None
