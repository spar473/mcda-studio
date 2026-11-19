"""B2 editor samples checked against printed knots and an independent segment oracle."""

from pathlib import Path

import pytest

from mcda_studio.domain.previews import ValueFunctionCandidate
from mcda_studio.methods.mavt.value_functions import piecewise_linear
from mcda_studio.services import analysis_service as svc
from mcda_studio.storage.json_repository import JsonProjectRepository

ROOT = Path(__file__).parents[2]
XS = [1.380, 2.552, 5.077, 10.037, 26.450]
VS = [0, 0.252, 0.5, 0.748, 1]


def test_vc_printed_points_and_segment_midpoints_without_rounding_the_fixture():
    p = JsonProjectRepository().load(ROOT / "examples/nz_deeptech_vc/project.json")
    vf = next(c.value_function for c in p.criteria if c.id == "market_size")
    assert [point.x for point in vf.points] == XS
    assert [point.value for point in vf.points] == VS
    for i, x in enumerate(XS):
        assert piecewise_linear(x, XS, VS) == VS[i]
    for i in range(4):
        assert piecewise_linear((XS[i] + XS[i + 1]) / 2, XS, VS) == pytest.approx(
            (VS[i] + VS[i + 1]) / 2
        )
    before = p.model_dump_json(), p.fingerprint()
    result = svc.preview_value_function(
        p, "market_size", candidate=ValueFunctionCandidate(value_function=vf)
    )
    assert result.resolved_domain.source == "control_points"
    samples = {s.measurement: s.partial_value for s in result.samples}
    assert all(samples[x] == v for x, v in zip(XS, VS, strict=True))
    for sample in result.samples:
        i = next(i for i in range(4) if XS[i] <= sample.measurement <= XS[i + 1])
        expected = VS[i] + (VS[i + 1] - VS[i]) * (sample.measurement - XS[i]) / (XS[i + 1] - XS[i])
        assert sample.partial_value == pytest.approx(expected, abs=1e-15)
    assert (p.model_dump_json(), p.fingerprint()) == before


@pytest.mark.parametrize(
    "criterion", ["unit_price", "defect_rate", "certification", "financial_stability", "region"]
)
def test_unrelated_supplier_candidate_preview_matches_full_engine_without_mutation(criterion):
    p = JsonProjectRepository().load(ROOT / "examples/supplier_selection/project.json")
    node = next(c for c in p.criteria if c.id == criterion)
    before = p.fingerprint()
    result = svc.preview_value_function(
        p,
        criterion,
        candidate=ValueFunctionCandidate(scale=node.scale, value_function=node.value_function),
    )
    full = svc.evaluate_project(p)
    assert result.readiness == result.measurement_readiness == "ready"
    for marker in result.markers:
        value = next(a for a in full.alternatives if a.alternative_id == marker.alternative_id)
        assert marker.partial_value == value.partial_values[criterion]
    assert p.fingerprint() == before
