"""Class assignment is monotone in value and independent of the project's alternative order."""

import random

from hypothesis import given, settings
from hypothesis import strategies as st

from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.results import MavtSortingResult
from mcda_studio.domain.sorting import SortingAudit
from mcda_studio.methods.sorting.classes import class_index
from mcda_studio.services import analysis_service as svc

from builders import scored_project, with_classes

unit = st.floats(0.0, 1.0, allow_nan=False)
boundary_sets = st.lists(st.integers(1, 999), min_size=0, max_size=4, unique=True).map(
    lambda xs: sorted((x / 1000 for x in xs), reverse=True)
)


@settings(max_examples=200, deadline=None)
@given(boundary_sets, unit, unit)
def test_a_higher_value_never_gets_a_worse_class(
    boundaries: list[float], u: float, v: float
) -> None:
    low, high = sorted((u, v))
    assert class_index(high, boundaries) <= class_index(low, boundaries)


@settings(max_examples=200, deadline=None)
@given(boundary_sets, unit)
def test_the_class_is_the_best_one_whose_boundary_the_value_reaches(
    boundaries: list[float], value: float
) -> None:
    reached = [k for k, b in enumerate(boundaries) if value >= b - 1e-12]
    assert class_index(value, boundaries) == (reached[0] if reached else len(boundaries))


@settings(max_examples=40, deadline=None)
@given(
    st.lists(st.integers(0, 1000), min_size=2, max_size=7),
    st.randoms(use_true_random=False),
    st.integers(0, 2**31),
)
def test_classes_and_the_audit_sample_do_not_depend_on_alternative_order(
    scores: list[int], rnd: random.Random, seed: int
) -> None:
    values = {f"a{i}": s / 1000 for i, s in enumerate(scores)}
    shuffled = list(values)
    rnd.shuffle(shuffled)
    audit = SortingAudit(below_class_id="upper", sample_size=2, seed=seed)
    classes = [("Upper", 0.6), ("Middle", 0.3), ("Lower", None)]
    cfg = AnalysisConfiguration(method="mavt_sorting")

    def outcome(order: list[str]) -> tuple[dict[str, str], list[str]]:
        project = with_classes(scored_project({k: values[k] for k in order}), classes, audit)
        result = svc.evaluate_project(project, cfg)
        assert isinstance(result, MavtSortingResult) and result.audit_sample is not None
        return (
            {a.alternative_id: a.class_id for a in result.assignments},
            result.audit_sample.alternative_ids,
        )

    assert outcome(list(values)) == outcome(shuffled)
