"""Independent rational/bounded pair reconstruction and exact engine-to-engine checks."""

from fractions import Fraction

import pytest

from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.services import proxy_criterion_service as proxy
from proxy_builders import inputs, request, with_factors
from regression.proxy_oracle import classes, projects, values


@pytest.mark.parametrize("profile", ["balanced", "quality_led"])
@pytest.mark.parametrize("method", ["mavt", "mavt_sorting"])
def test_independent_dyadic_values_weights_and_classes_are_exact(profile, method):
    value = inputs()
    value.configuration = AnalysisConfiguration(method=method, weight_profile_id=profile)
    bundle = proxy.run_pair(request(value))
    for half, declared in zip(
        [bundle.without_proxy, bundle.with_proxy],
        projects(value.model_dump(mode="json")),
        strict=True,
    ):
        materialized = half.project.model_dump(mode="json")
        for field in ["criteria", "weight_profiles", "performances"]:
            assert materialized[field] == declared[field]
        expected = values(declared, profile)
        assert {r.alternative_id: Fraction.from_float(r.value) for r in half.result.ranking} == {
            id: bounded.exact for id, bounded in expected.items()
        }
        if method == "mavt_sorting":
            bands = [c.model_dump(mode="json") for c in half.project.sorting.classes]
            assert {a.alternative_id: a.class_id for a in half.result.assignments} == classes(
                {id: v.exact for id, v in expected.items()}, bands
            )


def test_decimal_values_use_independently_derived_rounding_bounds():
    def change(p):
        p.performances[0].value = 0.1
        p.performances[1].value = 0.2
        p.weight_profiles[0].judgements = {"quality": 0.1, "capacity": 0.3}

    value = inputs(project_change=change)
    bundle = proxy.run_pair(request(value))
    for half, declared in zip(
        [bundle.without_proxy, bundle.with_proxy],
        projects(value.model_dump(mode="json")),
        strict=True,
    ):
        expected = values(declared, "balanced")
        assert all(expected[row.alternative_id].contains(row.value) for row in half.result.ranking)
        assert not expected["a"].contains(
            next(r.value for r in half.result.ranking if r.alternative_id == "a") * 1.01
        )


def test_sampled_and_enumerated_fixed_proxy_scores_reduce_to_the_same_exact_support():
    value = with_factors(inputs())
    sampled = proxy.run_pair(request(value))
    value.factor_parameters.evaluation = "exact_enumeration"
    exact = proxy.run_pair(request(value))
    for name in ["without_proxy", "with_proxy"]:
        samples = getattr(sampled, name).factor_run.result.trace
        support = getattr(exact, name).factor_run.result.trace
        expected = {
            (
                tuple(sorted(t.factors.items())),
                tuple(sorted(t.values.items())),
                tuple(sorted(t.ranks.items())),
            )
            for t in support
        }
        assert len(expected) == 2
        for trace in samples:
            assert (
                tuple(sorted(trace.factors.items())),
                tuple(sorted(trace.values.items())),
                tuple(sorted(trace.ranks.items())),
            ) in expected
            project = projects(value.model_dump(mode="json"))[0 if name == "without_proxy" else 1]
            for performance in project["performances"]:
                if (
                    performance["alternative_id"] == "a"
                    and performance["criterion_id"] == "quality"
                ):
                    performance["value"] = trace.factors["quality_a"]
            oracle = values(project, "balanced")
            assert all(
                Fraction.from_float(trace.values[id]) == result.exact
                for id, result in oracle.items()
            )


def test_proxy_under_an_existing_group_preserves_siblings_and_exact_path_shares():
    from mcda_studio.domain.criteria import CriterionNode

    def group(project):
        for node in project.criteria:
            node.parent_id = "overall"
        project.criteria.insert(0, CriterionNode(id="overall", name="Overall"))

    value = inputs(
        project_change=group,
        state_change=lambda state: setattr(state.criterion, "parent_id", "overall"),
    )
    bundle = proxy.run_pair(request(value))
    for half, declared in zip(
        [bundle.without_proxy, bundle.with_proxy],
        projects(value.model_dump(mode="json")),
        strict=True,
    ):
        expected = values(declared, "balanced")
        assert {r.alternative_id: Fraction.from_float(r.value) for r in half.result.ranking} == {
            id: v.exact for id, v in expected.items()
        }
    assert bundle.with_proxy.project.weight_profiles[0].judgements["quality"] == 1.0
    assert bundle.with_proxy.project.weight_profiles[0].judgements["capacity"] == 1.0


@pytest.mark.parametrize("perturbation", [0.0, 2e-13])
def test_scenario_precedence_and_existing_sorting_boundary_tolerance_are_preserved(perturbation):
    from mcda_studio.domain.preferences import Scenario

    def scenario(project):
        project.scenarios = [
            Scenario(
                id="alternative", name="Alternative philosophy", weight_profile_id="quality_led"
            )
        ]
        for performance in project.performances:
            performance.value = 0.5
        project.performances[0].value += perturbation

    value = inputs(project_change=scenario)
    value.configuration = AnalysisConfiguration(method="mavt_sorting", scenario_id="alternative")
    bundle = proxy.run_pair(request(value))
    assert bundle.without_proxy.result.weight_profile_id == "quality_led"
    assert [r.rank for r in bundle.without_proxy.result.ranking] == [1, 1]
    assert all(
        a.on_boundary and a.class_id == "high" for a in bundle.without_proxy.result.assignments
    )
    assert (
        bundle.without_proxy.result.boundary_tolerance
        == bundle.with_proxy.result.boundary_tolerance
        == 1e-12
    )
    expected = values(projects(value.model_dump(mode="json"))[1], "quality_led")
    assert all(
        expected[r.alternative_id].contains(r.value) for r in bundle.with_proxy.result.ranking
    )
    if perturbation == 0:
        assert all(
            Fraction.from_float(r.value) == expected[r.alternative_id].exact
            for r in bundle.with_proxy.result.ranking
        )
