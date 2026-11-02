"""SMAA-2 over the MAVT model: seeded sampling, exact enumeration and the counts behind every
acceptability (design note §3 to §5).

Every draw replaces the stated measurements and sibling-group weights, then evaluates the model
exactly as MAVT does: the same value functions, the same global weights, competition ranks with
the same tolerance and classes with the same boundary rule. Values are summed in bulk with NumPy;
any draw in which two alternatives, or an alternative and a class boundary, lie within ``NEAR_TIE``
is summed again with ``math.fsum``, so ranks and classes are exactly those of the reference path.
"""

import itertools
import math
import platform
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from fractions import Fraction

import numpy as np
from numpy.typing import NDArray

from mcda_studio.domain.common import Issue, Severity
from mcda_studio.domain.errors import AnalysisLimitError, WeightError
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import (
    AcceptabilityEstimate,
    AlternativeAcceptability,
    InputToCheck,
    SmaaResult,
)
from mcda_studio.domain.uncertainty import (
    CategoricalDistribution,
    CellUncertainty,
    DiscreteDistribution,
    GroupUncertainty,
    TriangularDistribution,
    UniformDistribution,
)
from mcda_studio.methods.mavt.aggregation import (
    ASSUMPTIONS,
    TIE_TOL,
    PreparedMavt,
    build_mavt_result,
    prepare_mavt,
    rank_values,
)
from mcda_studio.methods.mavt.value_functions import build_evaluator
from mcda_studio.methods.smaa.intervals import clopper_pearson
from mcda_studio.methods.smaa.validation import effective_function, smaa_parameters
from mcda_studio.methods.sorting.classes import class_bands, class_index, lower_boundaries

NEAR_TIE = 1e-9
MAX_OUTCOMES = 100_000
MAX_WORK = 100_000_000  # draws x alternatives x leaves per request
CHUNK_CELLS = 2_000_000  # draws per chunk x alternatives x leaves held in memory at once
INPUTS_TO_CHECK = 5

SMAA_ASSUMPTIONS = [
    "Acceptabilities are the frequencies of ranks and classes in draws from the stated "
    "distributions: sampled acceptability under these assumptions. They are not probabilities of "
    "success, confidence that a choice is right, or a value of information.",
    "Inputs are drawn independently, except cells listed together in a shared draw, which use one "
    "common uniform draw through their own quantile functions.",
    "Every draw is evaluated with the additive MAVT model below; 'ranking' is MAVT's reference "
    "ranking at the entered measurements and the profile's ratings.",
    *ASSUMPTIONS,
]


@dataclass(frozen=True)
class _Cell:
    """One varying measurement: where it sits, how a uniform draw becomes its partial value, and
    (for discrete and categorical distributions) its exact outcomes."""

    alternative: int
    leaf: int
    path: str
    label: str
    partial: Callable[[NDArray[np.float64]], NDArray[np.float64]]
    outcomes: list[tuple[Fraction, float]] | None  # (probability, partial value), quantile order


@dataclass(frozen=True)
class _Group:
    parent_id: str | None
    label: str
    children: list[str]
    spec: GroupUncertainty


def _normalised(probabilities: list[float]) -> list[Fraction]:
    exact = [Fraction(p) for p in probabilities]
    total = sum(exact, Fraction(0))
    return [p / total for p in exact]


def _cell(
    prep: PreparedMavt, project: Project, configuration: AnalysisConfiguration, c: CellUncertainty
) -> _Cell:
    alternative = prep.alt_ids.index(c.alternative_id)
    leaf = prep.leaf_ids.index(c.criterion_id)
    function = effective_function(project, configuration, c.criterion_id)
    assert function is not None  # guaranteed by validation
    evaluator = build_evaluator(function, prep.domains[c.criterion_id])
    names = {a.id: a.name for a in project.alternatives}
    label = f"{names[c.alternative_id]} on {prep.tree.node(c.criterion_id).name}"
    path = f"smaa.cells[{c.alternative_id},{c.criterion_id}]"
    dist = c.distribution

    def partials(xs: list[float] | list[str]) -> list[float]:
        return [evaluator(x)[0] for x in xs]

    if isinstance(dist, DiscreteDistribution | CategoricalDistribution):
        if isinstance(dist, DiscreteDistribution):
            pairs = sorted(zip(dist.values, dist.probabilities, strict=True))
            values: list[float] | list[str] = [v for v, _ in pairs]
            probs = [p for _, p in pairs]
        else:
            node = prep.tree.node(c.criterion_id)
            assert node.scale is not None
            given = dict(zip(dist.labels, dist.probabilities, strict=True))
            values = [x for x in node.scale.labels if x in given]
            probs = [given[x] for x in values]
        exact = _normalised(probs)
        outcome_values = partials(values)
        cumulative = np.cumsum(np.array([float(p) for p in exact]))
        cumulative[-1] = 1.0
        table = np.array(outcome_values, dtype=float)

        def discrete(u: NDArray[np.float64]) -> NDArray[np.float64]:
            index = np.minimum(np.searchsorted(cumulative, u, side="right"), len(table) - 1)
            return table[index]

        return _Cell(
            alternative, leaf, path, label, discrete, list(zip(exact, outcome_values, strict=True))
        )

    if isinstance(dist, UniformDistribution):
        lo, hi = dist.lower, dist.upper

        def quantile(u: NDArray[np.float64]) -> NDArray[np.float64]:
            return lo + u * (hi - lo)

    else:
        assert isinstance(dist, TriangularDistribution)
        a, m, b = dist.lower, dist.mode, dist.upper
        split = (m - a) / (b - a)

        def quantile(u: NDArray[np.float64]) -> NDArray[np.float64]:
            rising = a + np.sqrt(u * (b - a) * (m - a))
            falling = b - np.sqrt((1.0 - u) * (b - a) * (b - m))
            return np.where(u < split, rising, falling)

    def continuous(u: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.array(partials([float(x) for x in quantile(u)]), dtype=float)

    return _Cell(alternative, leaf, path, label, continuous, None)


@dataclass
class _Plan:
    prep: PreparedMavt
    cells: list[_Cell]  # varying cells, alternative then leaf order
    groups: list[_Group]  # varying groups, tree order
    shared: list[tuple[str, list[int]]]  # (shared draw id, indexes into cells)
    boundaries: list[float]
    class_ids: list[str]

    @property
    def independent(self) -> list[int]:
        taken = {i for _, members in self.shared for i in members}
        return [i for i in range(len(self.cells)) if i not in taken]


def _plan(project: Project, configuration: AnalysisConfiguration, run: str) -> _Plan:
    prep = prepare_mavt(project, configuration)  # validates through the SMAA-2 method
    model = project.smaa
    assert model is not None  # guaranteed by validation (NOTHING_UNCERTAIN)
    cells: list[_Cell] = []
    if run in {"performance", "combined"}:
        built = [_cell(prep, project, configuration, c) for c in model.cells]
        cells = sorted(built, key=lambda c: (c.alternative, c.leaf))
    groups: list[_Group] = []
    if run in {"preference", "combined"}:
        by_parent = {g.parent_id: g for g in model.groups}
        order: list[str | None] = [
            None,
            *(i for i in prep.tree.all_ids() if not prep.tree.is_leaf(i)),
        ]
        for parent in order:
            if parent in by_parent:
                label = "the top level" if parent is None else prep.tree.node(parent).name
                groups.append(_Group(parent, label, prep.tree.child_ids(parent), by_parent[parent]))
    index = {c.path: i for i, c in enumerate(cells)}
    shared = [
        (s.id, [index[f"smaa.cells[{r.alternative_id},{r.criterion_id}]"] for r in s.cells])
        for s in model.shared_draws
        if cells
    ]
    sorting = project.sorting
    return _Plan(
        prep=prep,
        cells=cells,
        groups=groups,
        shared=shared,
        boundaries=lower_boundaries(sorting) if sorting else [],
        class_ids=[c.id for c in sorting.classes] if sorting else [],
    )


@dataclass
class _Counts:
    """Draw counts (sampling) or exact probabilities (enumeration) behind every estimate."""

    ranks: NDArray[np.int64] | list[list[Fraction]]
    sole: NDArray[np.int64] | list[Fraction]
    tied: NDArray[np.int64] | list[Fraction]
    classes: NDArray[np.int64] | list[list[Fraction]]
    near_ties: int


def _evaluate(
    plan: _Plan, partial: NDArray[np.float64], weights: NDArray[np.float64]
) -> tuple[NDArray[np.int64], NDArray[np.int64], int]:
    """Competition ranks and class indexes per draw; near-ties re-summed with ``math.fsum``."""
    n, alternatives, _ = partial.shape
    values = np.einsum("nal,nl->na", partial, weights)
    switch = np.array([b - TIE_TOL for b in plan.boundaries], dtype=float)
    near = np.zeros(n, dtype=bool)
    if alternatives > 1:
        near |= (np.diff(np.sort(values, axis=1), axis=1) < NEAR_TIE).any(axis=1)
    if switch.size:
        near |= (np.abs(values[:, :, None] - switch[None, None, :]) < NEAR_TIE).any(axis=(1, 2))
    ranks = np.empty((n, alternatives), dtype=np.int64)
    order = np.argsort(-values, axis=1, kind="stable")
    np.put_along_axis(ranks, order, np.arange(1, alternatives + 1)[None, :].repeat(n, 0), axis=1)
    classes = (values[:, :, None] < switch[None, None, :]).sum(axis=2).astype(np.int64)
    for i in np.flatnonzero(near):
        exact = [
            math.fsum(float(w) * float(p) for w, p in zip(weights[i], row, strict=True))
            for row in partial[i]
        ]
        ranks[i] = rank_values(exact)
        classes[i] = [class_index(v, plan.boundaries) for v in exact]
    return ranks, classes, int(near.sum())


def _weights(plan: _Plan, local: dict[str, NDArray[np.float64]], n: int) -> NDArray[np.float64]:
    """Global leaf weights per draw: products of local weights down each path."""
    prep = plan.prep
    if not plan.groups:
        return np.broadcast_to(prep.global_vector(), (n, len(prep.leaf_ids))).copy()
    columns = []
    for leaf in prep.leaf_ids:
        weight = np.ones(n)
        for node in prep.tree.path(leaf):
            weight = weight * (local[node] if node in local else prep.local[node])
        columns.append(weight)
    return np.stack(columns, axis=1)


def _group_locals(
    plan: _Plan, uniforms: NDArray[np.float64]
) -> tuple[dict[str, NDArray[np.float64]], int]:
    """Local weights of every varying group from its uniform columns; returns columns used."""
    local: dict[str, NDArray[np.float64]] = {}
    column = 0
    for group in plan.groups:
        u = uniforms[:, column : column + len(group.children)]
        column += len(group.children)
        if group.spec.kind == "unknown":
            raw = -np.log1p(-u)  # exponential draws: normalised, they are Dirichlet(1, ..., 1)
        else:
            lo = np.array([group.spec.intervals[c][0] for c in group.children])
            hi = np.array([group.spec.intervals[c][1] for c in group.children])
            raw = lo[None, :] + u * (hi - lo)[None, :]
        total = raw.sum(axis=1)
        if np.any(total <= 0.0):
            raise WeightError(
                f"a draw of the weights under {group.label} summed to zero; it is refused, "
                "not skipped"
            )
        for k, child in enumerate(group.children):
            local[child] = raw[:, k] / total
    return local, column


def _sample(
    plan: _Plan, samples: int, seed: int
) -> tuple[_Counts, NDArray[np.bool_], list[tuple[str, str, NDArray[np.bool_]]]]:
    prep = plan.prep
    alternatives, leaves = len(prep.alt_ids), len(prep.leaf_ids)
    group_columns = sum(len(g.children) for g in plan.groups)
    independent = plan.independent
    width = group_columns + len(independent) + len(plan.shared)
    rng = np.random.Generator(np.random.PCG64(seed))
    chunk = max(1, min(samples, CHUNK_CELLS // max(1, alternatives * leaves)))
    ranks_total = np.zeros((alternatives, alternatives), dtype=np.int64)
    classes_total = np.zeros((alternatives, max(1, len(plan.class_ids))), dtype=np.int64)
    sole = np.zeros(alternatives, dtype=np.int64)
    tied = np.zeros(alternatives, dtype=np.int64)
    first_parts: list[NDArray[np.bool_]] = []
    input_parts: list[list[NDArray[np.float64]]] = []
    near_total = 0
    done = 0
    while done < samples:
        n = min(chunk, samples - done)
        uniforms = rng.random((n, width))
        local, column = _group_locals(plan, uniforms)
        partial = np.broadcast_to(prep.partial, (n, alternatives, leaves)).copy()
        draws: list[NDArray[np.float64]] = []
        for i in independent:
            cell = plan.cells[i]
            partial[:, cell.alternative, cell.leaf] = cell.partial(uniforms[:, column])
            draws.append(uniforms[:, column])
            column += 1
        for _, members in plan.shared:
            for i in members:
                cell = plan.cells[i]
                partial[:, cell.alternative, cell.leaf] = cell.partial(uniforms[:, column])
            draws.append(uniforms[:, column])
            column += 1
        weights = _weights(plan, local, n)
        ranks, classes, near = _evaluate(plan, partial, weights)
        near_total += near
        for a in range(alternatives):
            ranks_total[a] += np.bincount(ranks[:, a] - 1, minlength=alternatives)
            if plan.class_ids:
                classes_total[a] += np.bincount(classes[:, a], minlength=len(plan.class_ids))
        first = ranks == 1
        shared_first = first.sum(axis=1) > 1
        sole += (first & ~shared_first[:, None]).sum(axis=0)
        tied += (first & shared_first[:, None]).sum(axis=0)
        first_parts.append(first)
        # An unknown group's child is judged by its local weight; a rating interval's by its
        # uniform, which orders the rating; a measurement or shared draw by its uniform.
        group_inputs: list[NDArray[np.float64]] = []
        k = 0
        for group in plan.groups:
            for child in group.children:
                unknown = group.spec.kind == "unknown"
                group_inputs.append(local[child] if unknown else uniforms[:, k])
                k += 1
        input_parts.append(group_inputs + draws)
        done += n
    first_all = np.concatenate(first_parts)
    inputs: list[tuple[str, str, NDArray[np.bool_]]] = []
    labels = _input_labels(plan)
    for k, (label, path) in enumerate(labels):
        column_values = np.concatenate([part[k] for part in input_parts])
        threshold = np.median(column_values) if _is_unknown_column(plan, k) else 0.5
        inputs.append((label, path, column_values > threshold))
    counts = _Counts(ranks_total, sole, tied, classes_total, near_total)
    return counts, first_all, inputs


def _is_unknown_column(plan: _Plan, k: int) -> bool:
    """Whether group column ``k`` belongs to an ``unknown`` group (judged by local weight)."""
    for group in plan.groups:
        if k < len(group.children):
            return group.spec.kind == "unknown"
        k -= len(group.children)
    return False


def _input_labels(plan: _Plan) -> list[tuple[str, str]]:
    names = plan.prep.tree
    out: list[tuple[str, str]] = []
    for group in plan.groups:
        key = "top" if group.parent_id is None else group.parent_id
        for child in group.children:
            what = "local weight" if group.spec.kind == "unknown" else "swing rating"
            out.append(
                (
                    f"{what} of {names.node(child).name} under {group.label}",
                    f"smaa.groups[{key}].{child}",
                )
            )
    out += [(plan.cells[i].label, plan.cells[i].path) for i in plan.independent]
    out += [(f"shared draw {sid}", f"smaa.shared_draws[{sid}]") for sid, _ in plan.shared]
    return out


def _enumerable(plan: _Plan) -> int | None:
    """The joint outcome count when every varying input is discrete and few enough, else None."""
    if plan.groups or not plan.cells or any(c.outcomes is None for c in plan.cells):
        return None
    total = 1
    for i in plan.independent:
        outcomes = plan.cells[i].outcomes
        assert outcomes is not None
        total *= len(outcomes)
    for _, members in plan.shared:
        total *= len(_segments(plan, members))
    return total if total <= MAX_OUTCOMES else None


def _segments(plan: _Plan, members: list[int]) -> list[tuple[Fraction, list[float]]]:
    """A shared draw's joint outcomes: [0, 1) cut at every member's cumulative probability."""
    cuts = {Fraction(0), Fraction(1)}
    tables: list[list[tuple[Fraction, float]]] = []
    for i in members:
        outcomes = plan.cells[i].outcomes
        assert outcomes is not None
        tables.append(outcomes)
        running = Fraction(0)
        for probability, _ in outcomes:
            running += probability
            cuts.add(running)
    edges = sorted(cuts)
    segments: list[tuple[Fraction, list[float]]] = []
    for start, end in itertools.pairwise(edges):
        if end <= start:
            continue
        chosen = []
        for table in tables:
            running = Fraction(0)
            for probability, value in table:
                running += probability
                if running > start:
                    chosen.append(value)
                    break
        segments.append((end - start, chosen))
    return segments


def _enumerate(plan: _Plan) -> _Counts:
    prep = plan.prep
    alternatives, leaves = len(prep.alt_ids), len(prep.leaf_ids)
    variables: list[tuple[list[int], list[tuple[Fraction, list[float]]]]] = []
    for i in plan.independent:
        outcomes = plan.cells[i].outcomes
        assert outcomes is not None
        variables.append(([i], [(p, [v]) for p, v in outcomes]))
    for _, members in plan.shared:
        variables.append((members, _segments(plan, members)))
    patterns: dict[tuple[tuple[int, ...], tuple[int, ...]], Fraction] = {}
    weights_row = prep.global_vector()
    chunk = max(1, CHUNK_CELLS // max(1, alternatives * leaves))
    combos: Iterator[tuple[tuple[Fraction, list[float]], ...]] = itertools.product(
        *(outcomes for _, outcomes in variables)
    )
    near_total = 0
    while batch := list(itertools.islice(combos, chunk)):
        partial = np.broadcast_to(prep.partial, (len(batch), alternatives, leaves)).copy()
        for row, combo in enumerate(batch):
            for (members, _), (_, values) in zip(variables, combo, strict=True):
                for i, value in zip(members, values, strict=True):
                    cell = plan.cells[i]
                    partial[row, cell.alternative, cell.leaf] = value
        weights = np.broadcast_to(weights_row, (len(batch), leaves)).copy()
        ranks, classes, near = _evaluate(plan, partial, weights)
        near_total += near
        for row, combo in enumerate(batch):
            probability = math.prod((outcome[0] for outcome in combo), start=Fraction(1))
            key = (tuple(int(r) for r in ranks[row]), tuple(int(c) for c in classes[row]))
            patterns[key] = patterns.get(key, Fraction(0)) + probability
    rank_p = [[Fraction(0)] * alternatives for _ in range(alternatives)]
    class_p = [[Fraction(0)] * max(1, len(plan.class_ids)) for _ in range(alternatives)]
    sole = [Fraction(0)] * alternatives
    tied = [Fraction(0)] * alternatives
    for (ranks_key, classes_key), probability in patterns.items():
        firsts = sum(1 for r in ranks_key if r == 1)
        for a, r in enumerate(ranks_key):
            rank_p[a][r - 1] += probability
            if r == 1:
                if firsts == 1:
                    sole[a] += probability
                else:
                    tied[a] += probability
            if plan.class_ids:
                class_p[a][classes_key[a]] += probability
    return _Counts(rank_p, sole, tied, class_p, near_total)


def _frequency(value: int | Fraction, n: int | None) -> float:
    return float(value) if isinstance(value, Fraction) else int(value) / (n or 1)


def _estimate(value: int | Fraction, n: int | None, confidence: float) -> AcceptabilityEstimate:
    if isinstance(value, Fraction):
        return AcceptabilityEstimate(count=None, frequency=float(value), lower=None, upper=None)
    assert n is not None
    lower, upper = clopper_pearson(int(value), n, confidence)
    return AcceptabilityEstimate(
        count=int(value), frequency=int(value) / n, lower=lower, upper=upper
    )


def run_smaa(project: Project, configuration: AnalysisConfiguration) -> SmaaResult:
    params = smaa_parameters(configuration)
    plan = _plan(project, configuration, params.uncertainty)
    prep = plan.prep
    alternatives, leaves = len(prep.alt_ids), len(prep.leaf_ids)
    outcomes = _enumerable(plan)
    diagnostics: list[Issue] = list(prep.warnings)
    inputs_to_check: list[InputToCheck] = []
    if outcomes is not None:
        counts = _enumerate(plan)
        n: int | None = None
        first_all = np.zeros((0, alternatives), dtype=bool)
        inputs: list[tuple[str, str, NDArray[np.bool_]]] = []
        diagnostics.append(
            Issue(
                severity=Severity.INFO,
                code="EXACT_ENUMERATION",
                message=f"every varying input is discrete: the probabilities are exact over "
                f"{outcomes} joint outcomes, with no sampling and no intervals; inputs to check "
                "are not computed",
            )
        )
    else:
        if params.samples * alternatives * leaves > MAX_WORK:
            raise AnalysisLimitError(
                "SMAA-2 evaluates at most 10^8 draws x alternatives x leaves per request; "
                "reduce the samples."
            )
        counts, first_all, inputs = _sample(plan, params.samples, params.seed)
        n = params.samples
    rank1 = [_frequency(counts.ranks[a][0], n) for a in range(alternatives)]
    leader = max(range(alternatives), key=lambda a: (rank1[a], -a))
    if outcomes is None:
        led = first_all[:, leader]
        scored = []
        for label, path, upper in inputs:
            if upper.all() or not upper.any():
                continue
            hi, lo = float(led[upper].mean()), float(led[~upper].mean())
            scored.append(
                InputToCheck(
                    input=label,
                    path=path,
                    leader_rank1_upper_half=hi,
                    leader_rank1_lower_half=lo,
                    difference=hi - lo,
                )
            )
        scored.sort(key=lambda x: -abs(x.difference))
        inputs_to_check = scored[:INPUTS_TO_CHECK]
    if counts.near_ties:
        diagnostics.append(
            Issue(
                severity=Severity.INFO,
                code="NEAR_TIE_DRAWS",
                message=f"{counts.near_ties} draw(s) had alternatives or a class boundary within "
                f"{NEAR_TIE} and were summed again with math.fsum",
            )
        )
    names = {a.id: a.name for a in project.alternatives}
    acceptability = [
        AlternativeAcceptability(
            alternative_id=alt,
            name=names[alt],
            ranks=[_estimate(v, n, params.confidence) for v in counts.ranks[a]],
            sole_first=_estimate(counts.sole[a], n, params.confidence),
            tied_first=_estimate(counts.tied[a], n, params.confidence),
            classes={
                cid: _estimate(counts.classes[a][k], n, params.confidence)
                for k, cid in enumerate(plan.class_ids)
            },
        )
        for a, alt in enumerate(prep.alt_ids)
    ]
    reference = build_mavt_result(prep)
    assert project.smaa is not None
    return SmaaResult(
        schema_version=project.required_schema_version(),
        project_id=project.id,
        project_fingerprint=project.fingerprint(),
        configuration=configuration,
        weight_profile_id=prep.profile.id,
        scenario_id=prep.scenario.id if prep.scenario else None,
        ranking=reference.ranking,
        diagnostics=diagnostics,
        assumptions=list(SMAA_ASSUMPTIONS),
        run=params.uncertainty,
        evaluation="sampled" if outcomes is None else "exact_enumeration",
        samples=n,
        outcomes=outcomes,
        seed=params.seed,
        confidence=params.confidence,
        dependence=project.smaa.dependence,
        uncertainty=project.smaa.model_copy(deep=True),
        environment={
            "python": platform.python_version(),
            "numpy": np.__version__,
            "system": f"{platform.system()} {platform.machine()}",
        },
        classes=class_bands(project.sorting) if project.sorting else [],
        leader_id=prep.alt_ids[leader],
        acceptability=acceptability,
        inputs_to_check=inputs_to_check,
    )
