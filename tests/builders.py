"""Small project builders shared by tests (built through the public services API)."""

from mcda_studio.domain.criteria import (
    Direction,
    DirectRatingValueFunction,
    LinearValueFunction,
)
from mcda_studio.domain.project import Project
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.domain.sorting import SortingAudit, SortingModel
from mcda_studio.services import project_service as ps


def tiny_project() -> Project:
    """Two alternatives, two criteria. Hand-checkable:

    weights  cost 2/3, quality 1/3
    a: v_cost = (100-20)/100 = 0.8, v_q = 0.6        -> V = 0.8*2/3 + 0.6/3 = 0.73333
    b: v_cost = (100-60)/100 = 0.4, v_q = 0.9        -> V = 0.4*2/3 + 0.9/3 = 0.56667
    Varying the cost weight t: V_a = 0.6 + 0.2 t,  V_b = 0.9 - 0.5 t  -> cross at t = 3/7.
    """
    p = ps.new_project("Tiny")
    p = ps.add_alternative(p, "A", alt_id="a")
    p = ps.add_alternative(p, "B", alt_id="b")
    p = ps.add_criterion(
        p,
        "Cost",
        crit_id="cost",
        scale=Scale(type=ScaleType.RATIO, lower=0.0, upper=100.0),
        value_function=LinearValueFunction(direction=Direction.DECREASING),
    )
    p = ps.add_criterion(
        p,
        "Quality",
        crit_id="quality",
        scale=Scale(type=ScaleType.INTERVAL, lower=0.0, upper=10.0),
        value_function=LinearValueFunction(),
    )
    for alt, cost, q in (("a", 20.0, 6.0), ("b", 60.0, 9.0)):
        p = ps.set_performance(p, alt, "cost", cost)
        p = ps.set_performance(p, alt, "quality", q)
    p = ps.set_judgement(p, "cost", 100.0)
    p = ps.set_judgement(p, "quality", 50.0)
    return p


def flat_project(values: list[list[float]], ratings: list[float]) -> Project:
    """Alternatives a0.. on flat top-level leaves c0.. whose measurements ARE the partial values
    (direct rating on [0, 1]); ``ratings`` are the swing ratings."""
    n_alt, n_crit = len(values), len(ratings)
    p = ps.new_project("Flat")
    for i in range(n_alt):
        p = ps.add_alternative(p, f"alt {i}", alt_id=f"a{i}")
    for j in range(n_crit):
        p = ps.add_criterion(
            p,
            f"crit {j}",
            crit_id=f"c{j}",
            scale=Scale(type=ScaleType.INTERVAL, lower=0.0, upper=1.0),
            value_function=DirectRatingValueFunction(min_rating=0.0, max_rating=1.0),
        )
    for i in range(n_alt):
        for j in range(n_crit):
            p = ps.set_performance(p, f"a{i}", f"c{j}", values[i][j])
    for j, r in enumerate(ratings):
        p = ps.set_judgement(p, f"c{j}", r)
    return p


def scored_project(values: dict[str, float]) -> Project:
    """One direct-rating criterion on [0, 1], so each overall value is exactly its measurement."""
    p = ps.new_project("Scored").model_copy(update={"id": "scored"})
    for alt in values:
        p = ps.add_alternative(p, alt.upper(), alt_id=alt)
    p = ps.add_criterion(
        p,
        "Score",
        crit_id="score",
        scale=Scale(type=ScaleType.INTERVAL, lower=0.0, upper=1.0),
        value_function=DirectRatingValueFunction(min_rating=0.0, max_rating=1.0),
    )
    for alt, value in values.items():
        p = ps.set_performance(p, alt, "score", value)
    return p


def with_classes(
    project: Project, classes: list[tuple[str, float | None]], audit: SortingAudit | None = None
) -> Project:
    """Classes best first, as (name, lower boundary); ids are derived from the names."""
    model = SortingModel(classes=ps.sorting_classes(classes), audit=audit)
    return ps.set_sorting_model(project, model)


def every_section(project: Project, seed: int = 0) -> Project:
    """``project`` with every method's section stated, deterministically: unknown top-level SMAA
    weights; PROMETHEE II with every leaf maximised at weight 1 under the usual function, labels
    coded by position; consistent AHP judgements from weights cycling through 1, 2, 3 and 6."""
    from itertools import combinations

    from mcda_studio.domain.outranking import PrometheeCriterion, PrometheeModel, UsualFunction
    from mcda_studio.domain.pairwise import (
        AhpModel,
        AlternativeJudgements,
        CriteriaJudgements,
        PairwiseJudgement,
    )
    from mcda_studio.domain.uncertainty import GroupUncertainty, SmaaModel

    tree = project.tree()
    leaves = tree.leaves()
    criteria = []
    for leaf in leaves:
        scale = tree.node(leaf).scale
        labelled = scale is not None and scale.is_labelled
        coding = {label: float(k) for k, label in enumerate(scale.labels)} if labelled else None
        criteria.append(
            PrometheeCriterion(
                criterion_id=leaf,
                direction="maximise",
                weight=1.0,
                function=UsualFunction(),
                coding=coding,
            )
        )

    def consistent(items: list[str], shift: int) -> list[PairwiseJudgement]:
        w = [(1, 2, 3, 6)[(k + shift) % 4] for k in range(len(items))]
        out = []
        for i, j in combinations(range(len(items)), 2):
            hi, lo = (i, j) if w[i] >= w[j] else (j, i)
            out.append(PairwiseJudgement(row=items[hi], column=items[lo], value=w[hi] / w[lo]))
        return out

    parents = [None, *(i for i in tree.all_ids() if not tree.is_leaf(i))]
    ahp = AhpModel(
        criteria=[
            CriteriaJudgements(parent_id=p, judgements=consistent(tree.child_ids(p), seed + k))
            for k, p in enumerate(parents)
            if len(tree.child_ids(p)) >= 2
        ],
        alternatives=[
            AlternativeJudgements(
                criterion_id=leaf, judgements=consistent(project.alternative_ids(), seed + k)
            )
            for k, leaf in enumerate(leaves)
        ],
    )
    project = ps.set_smaa_model(
        project, SmaaModel(groups=[GroupUncertainty(parent_id=None, kind="unknown")])
    )
    project = ps.set_promethee_model(project, PrometheeModel(criteria=criteria))
    return ps.set_ahp_model(project, ahp)
