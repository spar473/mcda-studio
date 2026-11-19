"""Swing cards use scoped engine domains/endpoints without coupling weight readiness to data."""

from pathlib import Path

import pytest

from mcda_studio.domain.criteria import Direction, LinearValueFunction
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.scales import AnchorMode, Scale, ScaleType
from mcda_studio.services import analysis_service as svc
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository

from builders import tiny_project


@pytest.mark.parametrize(
    "direction,worst,best", [(Direction.INCREASING, [0], [100]), (Direction.DECREASING, [100], [0])]
)
def test_fixed_swings_are_engine_endpoints_even_without_measurements(direction, worst, best):
    p = ps.set_value_function(tiny_project(), "cost", LinearValueFunction(direction=direction))
    p.performances = []
    before = p.fingerprint()
    preview = svc.preview_weights(p)
    swing = preview.swing_ranges["cost"]
    assert preview.weights_ready and swing.readiness == "ready"
    assert swing.worst == worst and swing.best == best and swing.domain.source == "fixed"
    assert p.fingerprint() == before


def test_incomplete_local_range_does_not_block_weight_preview_or_impute_anchors():
    p = ps.set_scale(
        tiny_project(), "cost", Scale(type=ScaleType.RATIO, anchor_mode=AnchorMode.LOCAL)
    )
    p.performances = []
    preview = svc.preview_weights(p)
    swing = preview.swing_ranges["cost"]
    assert preview.weights_ready and preview.global_weights
    assert (
        swing.readiness == "incomplete"
        and swing.domain is None
        and not swing.worst
        and not swing.best
    )
    assert "MISSING_MEASUREMENT" in {i.code for i in swing.diagnostics}


def test_invalid_ratings_hide_every_normalised_weight_but_keep_range_information():
    p = tiny_project()
    p.weight_profiles[0].judgements["cost"] = -1
    preview = svc.preview_weights(p)
    assert not preview.weights_ready and preview.local_weights == preview.global_weights == {}
    assert preview.swing_ranges["cost"].readiness == "ready"


def test_reference_ranges_include_effective_scenario_and_unordered_label_endpoints():
    root = Path(__file__).parents[2]
    p = JsonProjectRepository().load(root / "examples/nz_deeptech_vc/project.json")
    base = svc.preview_weights(p)
    linear = svc.preview_weights(p, AnalysisConfiguration(scenario_id="linear_market_size"))
    assert base.swing_ranges["market_size"].domain.source == "control_points"
    assert linear.swing_ranges["market_size"].domain.source == "local"
    assert base.swing_ranges["founder_expertise"].worst == ["Very Low"]
    assert base.swing_ranges["founder_expertise"].best == ["Very High"]
    assert [
        p.weight_profiles[0].judgements[k]
        for k in ["team", "problem_solution", "market", "traction"]
    ] == [100, 90, 80, 70]
    assert len(base.global_weights) == 8 and base.global_weights == linear.global_weights
