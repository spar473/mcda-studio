"""Failure tests: every malformed or incomplete model is reported with a specific code."""

from typing import Any

import pytest

from mcda_studio.domain.criteria import (
    ControlPoint,
    Direction,
    LinearValueFunction,
    PiecewiseLinearValueFunction,
    QualitativeValueFunction,
)
from mcda_studio.domain.preferences import AnalysisConfiguration, Scenario, WeightProfile
from mcda_studio.domain.project import Project
from mcda_studio.domain.scales import AnchorMode, Scale, ScaleType
from mcda_studio.domain.validation import validate_project
from mcda_studio.services import project_service as ps

from builders import tiny_project


def codes(project: Project, cfg: AnalysisConfiguration | None = None) -> set[str]:
    return {i.code for i in validate_project(project, cfg).issues}


def raw(project: Project) -> dict[str, Any]:
    return project.model_dump(mode="json")


def reload(d: dict[str, Any]) -> Project:
    return Project.model_validate(d)


def test_valid_project_has_no_errors() -> None:
    assert validate_project(tiny_project()).ok


def test_blank_project_is_reported_incomplete_but_loadable() -> None:
    assert {"NO_ALTERNATIVES", "NO_CRITERIA"} <= codes(ps.new_project("blank"))


def test_missing_measurement() -> None:
    d = raw(tiny_project())
    d["performances"] = d["performances"][:-1]
    assert "MISSING_MEASUREMENT" in codes(reload(d))


def test_wrong_measurement_type_and_unknown_label() -> None:
    p = ps.set_performance(tiny_project(), "a", "cost", "cheap")
    assert "INVALID_MEASUREMENT_TYPE" in codes(p)
    p = ps.set_scale(tiny_project(), "cost", Scale(type=ScaleType.ORDINAL, labels=["l", "h"]))
    p = ps.set_value_function(p, "cost", QualitativeValueFunction(mapping={"l": 0.0, "h": 1.0}))
    assert "INVALID_LABEL" in codes(p)  # numeric measurements on a labelled scale


def test_negative_ratio_value() -> None:
    assert "NEGATIVE_RATIO_VALUE" in codes(ps.set_performance(tiny_project(), "a", "cost", -1.0))


@pytest.mark.parametrize("lo,hi", [(10.0, 10.0), (50.0, 5.0)])
def test_reversed_or_equal_bounds(lo: float, hi: float) -> None:
    p = ps.set_scale(tiny_project(), "quality", Scale(type=ScaleType.INTERVAL, lower=lo, upper=hi))
    assert "REVERSED_BOUNDS" in codes(p)


def test_fixed_linear_scale_without_anchors() -> None:
    p = ps.set_scale(tiny_project(), "quality", Scale(type=ScaleType.INTERVAL))
    assert "MISSING_ANCHORS" in codes(p)


def test_local_anchors_with_identical_min_and_max() -> None:
    p = ps.set_scale(
        tiny_project(), "cost", Scale(type=ScaleType.RATIO, anchor_mode=AnchorMode.LOCAL)
    )
    p = ps.set_performance(p, "b", "cost", 20.0)
    assert "DEGENERATE_LOCAL_ANCHORS" in codes(p)


def test_out_of_domain_is_an_error_by_default_and_a_warning_when_clamping() -> None:
    p = ps.set_performance(tiny_project(), "a", "cost", 150.0)
    assert "OUT_OF_DOMAIN" in codes(p)
    p = ps.set_value_function(p, "cost", LinearValueFunction(out_of_domain="clamp"))
    c = codes(p)
    assert "OUT_OF_DOMAIN" not in c and "CLAMPED_MEASUREMENT" in c


def _pw(*pts: tuple[float, float]) -> PiecewiseLinearValueFunction:
    return PiecewiseLinearValueFunction(points=[ControlPoint(x=x, value=v) for x, v in pts])


@pytest.mark.parametrize(
    "fn,code",
    [
        (_pw((0, 0)), "TOO_FEW_CONTROL_POINTS"),
        (_pw((0, 0), (5, 0.5), (3, 1)), "CONTROL_POINTS_NOT_ORDERED"),
        (_pw((0, 0), (5, 0.5), (5, 1)), "CONTROL_POINTS_NOT_ORDERED"),
        (_pw((0, 0), (5, 1.5)), "CONTROL_VALUE_RANGE"),
        (_pw((0, 0), (5, 0.8), (8, 0.4), (10, 1)), "NON_MONOTONE_VALUE_FUNCTION"),
        (_pw((0, 0.2), (10, 1)), "ENDPOINT_CONVENTION"),
        (_pw((0, 0), (10, 0.9)), "ENDPOINT_CONVENTION"),
    ],
)
def test_invalid_piecewise_functions(fn: PiecewiseLinearValueFunction, code: str) -> None:
    p = ps.set_scale(tiny_project(), "quality", Scale(type=ScaleType.INTERVAL, lower=0, upper=10))
    p = ps.set_value_function(p, "quality", fn)
    assert code in codes(p)


def test_valid_decreasing_piecewise_function_accepted() -> None:
    p = ps.set_value_function(tiny_project(), "cost", _pw((0, 1), (50, 0.4), (100, 0)))
    assert validate_project(p).ok


def test_qualitative_mapping_errors() -> None:
    base = ps.set_scale(
        tiny_project(), "quality", Scale(type=ScaleType.ORDINAL, labels=["lo", "mid", "hi"])
    )
    base = ps.set_performance(ps.set_performance(base, "a", "quality", "lo"), "b", "quality", "hi")

    def with_map(m: dict[str, float]) -> set[str]:
        return codes(ps.set_value_function(base, "quality", QualitativeValueFunction(mapping=m)))

    assert "MAPPING_LABEL_MISMATCH" in with_map({"lo": 0.0, "hi": 1.0})
    assert "MAPPING_VALUE_RANGE" in with_map({"lo": 0.0, "mid": 0.5, "hi": 2.0})
    assert "ENDPOINT_CONVENTION" in with_map({"lo": 0.1, "mid": 0.5, "hi": 1.0})
    assert "ORDINAL_ORDER_VIOLATED" in with_map({"lo": 0.0, "mid": 1.0, "hi": 0.6})
    assert with_map({"lo": 0.0, "mid": 0.2, "hi": 1.0}) == set()  # a valid mapping is accepted


def test_ordinal_scale_is_not_assumed_equally_spaced() -> None:
    """A 1-5 ordinal scale may map to unequal preference values; 0.1 steps are fine."""
    p = ps.set_scale(
        tiny_project(), "quality", Scale(type=ScaleType.ORDINAL, labels=["1", "2", "3", "4", "5"])
    )
    p = ps.set_value_function(
        p,
        "quality",
        QualitativeValueFunction(mapping={"1": 0.0, "2": 0.05, "3": 0.1, "4": 0.5, "5": 1.0}),
    )
    p = ps.set_performance(ps.set_performance(p, "a", "quality", "2"), "b", "quality", "5")
    assert validate_project(p).ok


def test_incompatible_value_function_for_scale_type() -> None:
    p = ps.set_scale(tiny_project(), "quality", Scale(type=ScaleType.ORDINAL, labels=["lo", "hi"]))
    p = ps.set_value_function(p, "quality", LinearValueFunction())
    assert "INCOMPATIBLE_VALUE_FUNCTION" in codes(p)


def test_labelled_scale_needs_two_unique_labels() -> None:
    p = ps.set_scale(tiny_project(), "quality", Scale(type=ScaleType.CATEGORICAL, labels=["x"]))
    assert "TOO_FEW_LABELS" in codes(p)
    p = ps.set_scale(
        tiny_project(), "quality", Scale(type=ScaleType.CATEGORICAL, labels=["x", "x"])
    )
    assert "DUPLICATE_LABEL" in codes(p)


def test_missing_scale_and_value_function() -> None:
    d = raw(tiny_project())
    d["criteria"][0]["scale"] = None
    d["criteria"][1]["value_function"] = None
    assert {"MISSING_SCALE", "MISSING_VALUE_FUNCTION"} <= codes(reload(d))


def test_leaf_data_on_a_parent_node() -> None:
    d = raw(tiny_project())
    d["criteria"].append({"id": "sub", "name": "Sub", "parent_id": "cost", "order": 0})
    assert "LEAF_DATA_ON_PARENT" in codes(reload(d))


def test_measurement_on_non_leaf_and_unknown_references() -> None:
    d = raw(tiny_project())
    d["criteria"].append({"id": "sub", "name": "Sub", "parent_id": "cost", "order": 0})
    d["performances"] += [
        {"alternative_id": "a", "criterion_id": "cost", "value": 1.0},
        {"alternative_id": "ghost", "criterion_id": "quality", "value": 1.0},
        {"alternative_id": "a", "criterion_id": "nope", "value": 1.0},
    ]
    c = codes(reload(d))
    assert {
        "MEASUREMENT_ON_NON_LEAF",
        "UNKNOWN_ALTERNATIVE",
        "UNKNOWN_CRITERION",
        "DUPLICATE_MEASUREMENT",
    } <= c


def test_structural_errors() -> None:
    d = raw(tiny_project())
    d["criteria"][0]["parent_id"] = "quality"
    d["criteria"][1]["parent_id"] = "cost"
    assert "INVALID_TREE" in codes(reload(d))
    d = raw(tiny_project())
    d["criteria"][0]["parent_id"] = "ghost"
    assert "INVALID_TREE" in codes(reload(d))
    d = raw(tiny_project())
    d["criteria"][1]["id"] = "cost"
    assert "INVALID_TREE" in codes(reload(d))


def test_duplicate_ids_and_names() -> None:
    d = raw(tiny_project())
    d["alternatives"][1]["id"] = "a"
    d["alternatives"][1]["name"] = "a"
    d["weight_profiles"].append(d["weight_profiles"][0])
    d["scenarios"] = [{"id": "s", "name": "s"}, {"id": "s", "name": "s2"}]
    c = codes(reload(d))
    assert {"DUPLICATE_ALTERNATIVE_ID", "DUPLICATE_PROFILE_ID", "DUPLICATE_SCENARIO_ID"} <= c
    assert "DUPLICATE_ALTERNATIVE_NAME" not in codes(tiny_project())


def test_weight_judgement_errors() -> None:
    d = raw(tiny_project())
    d["weight_profiles"][0]["judgements"] = {"cost": 100.0}
    assert "MISSING_JUDGEMENT" in codes(reload(d))
    d["weight_profiles"][0]["judgements"] = {"cost": -5.0, "quality": 10.0}
    assert "INVALID_JUDGEMENT" in codes(reload(d))
    d["weight_profiles"][0]["judgements"] = {"cost": 0.0, "quality": 0.0}
    assert "ZERO_SUM_JUDGEMENTS" in codes(reload(d))
    d["weight_profiles"][0]["judgements"] = {"cost": 1.0, "quality": 1.0, "ghost": 1.0}
    assert "UNKNOWN_JUDGEMENT_NODE" in codes(reload(d))


def test_no_weight_profile_and_unsupported_method() -> None:
    d = raw(tiny_project())
    d["weight_profiles"] = []
    assert "NO_WEIGHT_PROFILE" in codes(reload(d))
    d = raw(tiny_project())
    d["weight_profiles"][0]["method"] = "ahp"
    assert "UNSUPPORTED_WEIGHT_METHOD" in codes(reload(d))


def test_bad_references_in_scenarios_and_configuration() -> None:
    p = tiny_project()
    p = ps.add_scenario(p, Scenario(id="s1", name="s1", weight_profile_id="nope"))
    assert "UNKNOWN_PROFILE" in codes(p)
    assert "UNKNOWN_PROFILE" in codes(tiny_project(), AnalysisConfiguration(weight_profile_id="x"))
    assert "UNKNOWN_SCENARIO" in codes(tiny_project(), AnalysisConfiguration(scenario_id="x"))


def test_scenario_override_problems_are_found_at_validation_time() -> None:
    p = tiny_project()
    p = ps.add_scenario(
        p,
        Scenario(
            id="s",
            name="s",
            value_function_overrides={
                "ghost": LinearValueFunction(),
                "quality": QualitativeValueFunction(mapping={"a": 0.0, "b": 1.0}),
                "cost": LinearValueFunction(direction=Direction.DECREASING),
            },
        ),
    )
    c = codes(p)
    assert {"UNKNOWN_OVERRIDE_TARGET", "INCOMPATIBLE_VALUE_FUNCTION"} <= c


def test_unknown_fields_and_bad_ids_are_rejected_at_the_model_boundary() -> None:
    from pydantic import ValidationError

    d = raw(tiny_project())
    d["surprise"] = 1
    with pytest.raises(ValidationError):
        reload(d)
    d = raw(tiny_project())
    d["alternatives"][0]["id"] = "has space"
    with pytest.raises(ValidationError):
        reload(d)
    d = raw(tiny_project())
    d["performances"][0]["value"] = None
    with pytest.raises(ValidationError):
        reload(d)


def test_non_finite_numbers_are_rejected_at_the_model_boundary() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WeightProfile(id="p", name="p", judgements={"a": float("nan")})
    with pytest.raises(ValidationError):
        Scale(type=ScaleType.RATIO, lower=float("inf"))


def test_single_alternative_is_only_a_warning() -> None:
    p = ps.remove_alternative(tiny_project(), "b")
    r = validate_project(p)
    assert r.ok and "SINGLE_ALTERNATIVE" in {i.code for i in r.warnings}


def test_scenario_override_that_introduces_local_anchors_is_warned_about() -> None:
    """Regression: a scenario that swaps a piecewise function for a linear one on a LOCAL scale
    makes that criterion depend on the alternative set, so it must warn (found by the reference
    study's linear Market Size scenario); the warning points at the scenario, not the criterion."""
    p = ps.set_scale(
        tiny_project(),
        "cost",
        Scale(type=ScaleType.RATIO, unit="NZD", anchor_mode=AnchorMode.LOCAL),
    )
    p = ps.set_value_function(
        p,
        "cost",
        PiecewiseLinearValueFunction(
            points=[
                ControlPoint(x=20.0, value=0.0),
                ControlPoint(x=30.0, value=0.8),
                ControlPoint(x=60.0, value=1.0),
            ]
        ),
    )
    assert "LOCAL_ANCHORS" not in codes(p)  # piecewise is not alternative-dependent
    p = ps.add_scenario(
        p, Scenario(id="lin", name="lin", value_function_overrides={"cost": LinearValueFunction()})
    )
    local = [i for i in validate_project(p).issues if i.code == "LOCAL_ANCHORS"]
    assert [i.path for i in local] == ["scenarios[lin].value_function_overrides[cost]"]


def _local_two_alternatives(a: float, b: float) -> Project:
    p = ps.new_project("t")
    p = ps.add_alternative(p, "A", alt_id="a")
    p = ps.add_alternative(p, "B", alt_id="b")
    p = ps.add_criterion(
        p,
        "X",
        crit_id="x",
        scale=Scale(type=ScaleType.RATIO, anchor_mode=AnchorMode.LOCAL),
        value_function=LinearValueFunction(),
    )
    p = ps.set_performance(p, "a", "x", a)
    p = ps.set_performance(p, "b", "x", b)
    return ps.set_judgement(p, "x", 100.0)


def test_local_anchors_spread_at_floating_point_noise_level_are_flagged() -> None:
    """A spread of 1e-13 around 1.0 would be stretched over the full 0-1 range: warn."""
    assert "NEAR_DEGENERATE_LOCAL_ANCHORS" in codes(_local_two_alternatives(1.0, 1.0 + 1e-13))


def test_ordinary_local_anchor_spreads_are_not_flagged_as_near_degenerate() -> None:
    assert "NEAR_DEGENERATE_LOCAL_ANCHORS" not in codes(_local_two_alternatives(1.0, 1.001))
    assert "NEAR_DEGENERATE_LOCAL_ANCHORS" not in codes(_local_two_alternatives(0.0, 1e-12))
    # exactly equal stays the existing hard error, not the new warning
    equal = codes(_local_two_alternatives(2.0, 2.0))
    assert "DEGENERATE_LOCAL_ANCHORS" in equal and "NEAR_DEGENERATE_LOCAL_ANCHORS" not in equal
