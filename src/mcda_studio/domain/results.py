"""Analysis outputs. Results are plain data: serialisable, comparable, inspectable."""

from typing import Annotated, Literal

from pydantic import Field

from mcda_studio.domain.common import DomainModel, Id, Issue
from mcda_studio.domain.criteria import ValueFunctionSpec
from mcda_studio.domain.measurements import Domain, Measurement
from mcda_studio.domain.outranking import PreferenceFunction
from mcda_studio.domain.pairwise import PairwiseJudgement
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.uncertainty import SmaaModel


class RankedAlternative(DomainModel):
    alternative_id: Id
    name: str
    value: float
    rank: int  # competition ranking: ties share a rank (1, 1, 3, ...)


class AnalysisResult(DomainModel):
    """Method-independent part of every result."""

    method: str
    schema_version: int
    project_id: Id
    project_fingerprint: str  # sha256 of the canonical project JSON that was evaluated
    configuration: AnalysisConfiguration
    weight_profile_id: Id | None
    scenario_id: Id | None
    ranking: list[RankedAlternative]
    diagnostics: list[Issue] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class AlternativeDetail(DomainModel):
    alternative_id: Id
    name: str
    rank: int
    overall_value: float
    raw_measurements: dict[Id, Measurement]
    partial_values: dict[Id, float]
    weighted_contributions: dict[Id, float]
    clamped_criteria: list[Id] = Field(default_factory=list)


class DominancePair(DomainModel):
    dominator_id: Id
    dominated_id: Id


class ValueModelResult(AnalysisResult):
    """Everything an additive value model reports; each method built on it adds its own tag."""

    leaf_order: list[Id]
    local_weights: dict[Id, float]  # every node, relative to its siblings
    global_weights: dict[Id, float]  # leaves only; sum to 1
    resolved_domains: dict[Id, Domain | None]
    weight_basis: str
    alternatives: list[AlternativeDetail]  # in rank order
    dominance: list[DominancePair] = Field(default_factory=list)


class MavtResult(ValueModelResult):
    method: Literal["mavt"] = "mavt"


class ClassBand(DomainModel):
    """One ordered class as a band on the overall value scale."""

    class_id: Id
    name: str
    rank: int  # 1 = best
    lower_boundary: float | None  # None for the lowest class
    upper_boundary: float | None  # the next better class's lower boundary; None for the best


class ClassSummary(ClassBand):
    alternative_ids: list[Id]  # in rank order; empty classes are listed too


class ClassAssignment(DomainModel):
    alternative_id: Id
    class_id: Id
    class_rank: int
    on_boundary: bool  # within the boundary tolerance of a boundary (and given the higher class)
    nearest_boundary_class_id: Id | None  # the class whose lower boundary is nearest
    distance_to_nearest_boundary: float | None  # None when there is only one class


class AuditSample(DomainModel):
    """Alternatives sorted below a cut-off, chosen for manual review of possible false negatives.

    It estimates nothing and never changes a class.
    """

    below_class_id: Id
    seed: int
    requested_size: int
    pool_size: int
    alternative_ids: list[Id]  # in selection order
    selection_rule: Literal["sha256(seed:alternative_id) ascending, then id"] = (
        "sha256(seed:alternative_id) ascending, then id"
    )


class MavtSortingResult(ValueModelResult):
    """MAVT values sorted into ordered classes by fixed numeric boundaries."""

    method: Literal["mavt_sorting"] = "mavt_sorting"
    boundary_tolerance: float
    classes: list[ClassSummary]  # best first
    assignments: list[ClassAssignment]  # in rank order, one per alternative
    audit_sample: AuditSample | None = None


SmaaLabel = Literal["sampled acceptability under these assumptions"]
HeuristicLabel = Literal[
    "heuristic: association in these draws, not causation or value of information"
]
SMAA_LABEL: SmaaLabel = "sampled acceptability under these assumptions"
HEURISTIC_LABEL: HeuristicLabel = (
    "heuristic: association in these draws, not causation or value of information"
)


class AcceptabilityEstimate(DomainModel):
    """How often an event occurred in the draws, with its exact (Clopper-Pearson) interval; or,
    under exact enumeration, its probability with no count and no interval."""

    count: int | None
    frequency: float
    lower: float | None
    upper: float | None


class AlternativeAcceptability(DomainModel):
    alternative_id: Id
    name: str
    ranks: list[AcceptabilityEstimate]  # index r - 1 is competition rank r
    sole_first: AcceptabilityEstimate  # rank 1 with no other alternative at rank 1
    tied_first: AcceptabilityEstimate  # rank 1 shared with at least one other alternative
    classes: dict[Id, AcceptabilityEstimate] = Field(default_factory=dict)  # empty without classes


class InputToCheck(DomainModel):
    """The leading alternative's rank-1 frequency with one input in its upper and lower half."""

    input: str
    path: str
    leader_rank1_upper_half: float
    leader_rank1_lower_half: float
    difference: float


class SmaaResult(AnalysisResult):
    """SMAA-2 acceptabilities. ``ranking`` is MAVT's reference ranking at the entered values and
    the profile's ratings; the acceptabilities never enter it."""

    method: Literal["smaa2"] = "smaa2"
    label: SmaaLabel = SMAA_LABEL
    run: Literal["performance", "preference", "combined"]
    evaluation: Literal["sampled", "exact_enumeration"]
    samples: int | None
    outcomes: int | None
    seed: int
    algorithm: Literal["smaa2.pcg64.v1"] = "smaa2.pcg64.v1"
    confidence: float
    interval_method: Literal["clopper-pearson"] = "clopper-pearson"
    dependence: str
    uncertainty: SmaaModel
    environment: dict[str, str]
    classes: list[ClassBand]  # best first; empty without classes
    leader_id: Id  # highest rank-1 acceptability; the project's order breaks ties
    acceptability: list[AlternativeAcceptability]  # in the project's alternative order
    inputs_to_check: list[InputToCheck]
    inputs_to_check_label: HeuristicLabel = HEURISTIC_LABEL


FlowLabel = Literal[
    "net outranking flows: these compare the alternatives with one another and are not "
    "preference values"
]
FLOW_LABEL: FlowLabel = (
    "net outranking flows: these compare the alternatives with one another and are not "
    "preference values"
)


class PrometheeCriterionUsed(DomainModel):
    """One leaf's PROMETHEE inputs as used: the stated weight and its normalised share."""

    criterion_id: Id
    name: str
    unit: str | None  # the scale's unit; None on a labelled leaf, whose units are its codes
    direction: Literal["maximise", "minimise"]
    weight: float
    normalised_weight: float
    function: PreferenceFunction
    coding: dict[str, float] | None


class AlternativeFlows(DomainModel):
    """One alternative's outranking flows, each normalised by n - 1."""

    alternative_id: Id
    name: str
    rank: int  # PROMETHEE II competition rank on the net flow
    positive_flow: float  # how strongly it outranks the others, in [0, 1]
    negative_flow: float  # how strongly the others outrank it, in [0, 1]
    net_flow: float  # positive minus negative, in [-1, 1]
    criterion_flows: dict[Id, float]  # single-criterion net flows; net = sum(w_j * flow_j)


class PartialOrderPair(DomainModel):
    """One unordered pair under PROMETHEE I. For a preference, ``alternative_a`` is preferred."""

    alternative_a: Id
    alternative_b: Id
    relation: Literal["preferred", "indifferent", "incomparable"]


class RankComparison(DomainModel):
    """Ranks only: a value and a flow never share a column."""

    alternative_id: Id
    name: str
    mavt_rank: int
    promethee_rank: int


class CriterionExplanation(DomainModel):
    """One criterion's part in a pair ordered differently, in each method's own units."""

    criterion_id: Id
    name: str
    difference: float  # d = s (x_a - x_b) in the criterion's (coded) units; positive favours a
    favours: Id | None  # the alternative the difference favours; None when they measure the same
    zone: Literal["no_preference", "partial", "full"]
    preference_degree: float  # the preference function at |d|
    capped: bool  # full preference reached before |d|: any further difference counts the same
    q: float | None
    p: float | None
    promethee_contribution: float  # w_j [flow_j(a) - flow_j(b)]; these sum to the flow gap
    promethee_head_to_head: float  # w_j (2 / (n - 1)) [P_j(a, b) - P_j(b, a)]
    mavt_contribution: float  # MAVT's weighted partial-value difference; these sum to the value gap


class PairExplanation(DomainModel):
    """A pair the two methods order differently. ``alternative_a`` is the one MAVT places higher
    (or, when MAVT ties them, the one PROMETHEE II places lower)."""

    alternative_a: Id
    alternative_b: Id
    mavt_rank_a: int
    mavt_rank_b: int
    promethee_rank_a: int
    promethee_rank_b: int
    value_gap: float  # V(a) - V(b), MAVT units
    flow_gap: float  # net flow(a) - net flow(b)
    head_to_head: float  # (2 / (n - 1)) [pi(a, b) - pi(b, a)]
    via_others: float  # flow_gap - head_to_head: how a and b each fare against the others
    detailed: bool  # False beyond the detail limit: gaps only
    criteria: list[CriterionExplanation]  # in leaf order; empty when not detailed
    reasons: list[str]  # at most three; empty when not detailed


class OutrankingExplanation(DomainModel):
    """Why PROMETHEE II and MAVT order alternatives differently. The only cross-method operation
    is comparing orders; no number adds, averages or subtracts a value and a flow."""

    available: bool  # MAVT's side uses the result's weight profile and scenario
    unavailable_reason: str | None  # why MAVT's side could not be computed
    unavailable_codes: list[str]  # MAVT's error codes when unavailable
    detail_limit: int
    ranks: list[RankComparison]  # in PROMETHEE II order; empty when unavailable
    pairs: list[PairExplanation]  # every pair ordered differently, detailed ones first


class PrometheeResult(AnalysisResult):
    """PROMETHEE II net flows and the PROMETHEE I partial order. ``ranking`` holds the PROMETHEE II
    order and its ``value`` is the net flow, never a preference value. ``weight_profile_id`` and
    ``scenario_id`` are those of the explanation's MAVT side; PROMETHEE's inputs ignore them."""

    method: Literal["promethee2"] = "promethee2"
    label: FlowLabel = FLOW_LABEL
    threshold_tolerance: Literal["1e-12 * max(1, |x_a|, |x_b|)"] = "1e-12 * max(1, |x_a|, |x_b|)"
    leaf_order: list[Id]
    criteria: list[PrometheeCriterionUsed]  # in leaf order
    flows: list[AlternativeFlows]  # in PROMETHEE II order
    preference_matrix: dict[Id, dict[Id, float]]  # pi(a, b); the diagonal is 0
    partial_order: list[PartialOrderPair]  # every unordered pair, in project order
    explanation: OutrankingExplanation


AhpLabel = Literal[
    "AHP priorities under these pairwise judgements: shares of the goal that sum to one, not MAVT "
    "values or swing weights"
]
AHP_LABEL: AhpLabel = (
    "AHP priorities under these pairwise judgements: shares of the goal that sum to one, not MAVT "
    "values or swing weights"
)


class AhpTriad(DomainModel):
    """The most inconsistent triple of a matrix by Koczkodaj's index; a hint, never applied."""

    items: tuple[Id, Id, Id]  # i, j, k in matrix order
    judgements: tuple[float, float, float]  # M[i][j], M[j][k], M[i][k]
    index: float
    consistent_value: float  # M[i][j] * M[j][k]: the M[i][k] that would make the triad consistent


class AhpMatrixAnalysis(DomainModel):
    """Priorities and consistency of one complete pairwise matrix."""

    items: list[Id]
    priorities: dict[Id, float]  # sum to 1
    lambda_max: float
    consistency_index: float
    random_index: float
    consistency_ratio: float
    inconsistent: bool  # consistency_ratio above the threshold: a warning, never an error
    most_inconsistent_triad: AhpTriad | None  # None below three items
    iterations: int  # power-iteration steps; 0 for one or two items


class AhpMatrixResult(AhpMatrixAnalysis):
    kind: Literal["criteria", "alternatives"]
    group_id: Id | None  # the parent (None: the top level) or the leaf
    judgements: list[PairwiseJudgement]  # as stated, each pair once


class AhpMatrixPreview(DomainModel):
    """A read-only analysis of one drafted matrix; ``analysis`` is None until it is complete."""

    random_index_table: Literal["saaty-tran-2007"] = "saaty-tran-2007"
    consistency_threshold: float
    ready: bool
    issues: list[Issue]
    analysis: AhpMatrixAnalysis | None


class AhpAlternativePriority(DomainModel):
    alternative_id: Id
    name: str
    rank: int
    priority: float  # the overall priority; priorities sum to 1
    ideal_score: float | None  # ideal mode only: the unnormalised score, at most 1
    local_priorities: dict[Id, float]  # per leaf
    weighted_parts: dict[Id, float]  # per leaf: g_j p_j(a), or g_j r_j(a) in ideal mode


class AhpResult(AnalysisResult):
    """AHP priorities from pairwise judgements. ``ranking`` holds the overall priorities;
    ``weight_profile_id`` and ``scenario_id`` are None, because AHP reads neither."""

    method: Literal["ahp"] = "ahp"
    label: AhpLabel = AHP_LABEL
    synthesis: Literal["distributive", "ideal"]
    random_index_table: Literal["saaty-tran-2007"] = "saaty-tran-2007"
    random_indices: list[float]  # for 1 to 15 items
    consistency_threshold: float
    tolerance: float
    max_iterations: int
    leaf_order: list[Id]
    local_priorities: dict[Id, float]  # every criterion, relative to its siblings
    global_priorities: dict[Id, float]  # leaves only; sum to 1
    matrices: list[AhpMatrixResult]  # criteria groups in tree order, then one per leaf
    alternatives: list[AhpAlternativePriority]  # in rank order


#: The result of any registered method that has an API model, tagged by ``method``.
AnalysisResultUnion = Annotated[
    MavtResult | MavtSortingResult | SmaaResult | PrometheeResult | AhpResult,
    Field(discriminator="method"),
]


class Crossover(DomainModel):
    """Two alternatives swap order when the varied weight reaches ``weight``."""

    alternative_a: Id
    alternative_b: Id
    weight: float
    leader_before: Id  # leader at weights just below ``weight``
    leader_after: Id


class WinnerChange(DomainModel):
    weight: float
    from_winner: Id
    to_winner: Id


class SensitivityResult(DomainModel):
    """One-way sensitivity of the ranking to the local weight of one criterion node."""

    node_id: Id
    node_name: str
    base_weight: float
    baseline_ranking: list[Id]
    baseline_values: dict[Id, float]
    grid: list[float]
    values: dict[Id, list[float]]  # per alternative, aligned with ``grid``
    rankings: list[list[Id]]  # per grid point, best first
    crossovers: list[Crossover]  # exact, sorted by weight
    rank_change_points: list[float]
    first_winner_change_up: WinnerChange | None
    first_winner_change_down: WinnerChange | None
    ranking_stable_range: tuple[float, float]  # weights over which the full ranking is unchanged
    winner_stable_range: tuple[float, float]
    diagnostics: list[Issue] = Field(default_factory=list)


class ClassChange(DomainModel):
    """An alternative's class changes at ``weight``, where it crosses one class's lower boundary.

    At ``weight`` itself the alternative is in the higher of the two classes.
    """

    weight: float
    boundary_class_id: Id
    class_before: Id  # class at weights just below ``weight``
    class_after: Id  # class at weights just above ``weight``


class AlternativeClassChanges(DomainModel):
    alternative_id: Id
    base_class_id: Id
    change_points: list[ClassChange]  # sorted by weight
    first_change_up: ClassChange | None
    first_change_down: ClassChange | None
    class_stable_range: tuple[float, float]


class SortingSensitivityResult(SensitivityResult):
    """One-way sensitivity for value-based sorting: the MAVT sweep plus exact class changes."""

    method: Literal["mavt_sorting"] = "mavt_sorting"
    boundary_tolerance: float
    classes: list[ClassBand]  # best first
    class_changes: list[AlternativeClassChanges]  # in baseline ranking order


class ScenarioOutcome(DomainModel):
    scenario_id: Id | None  # None = baseline
    scenario_name: str
    configuration: AnalysisConfiguration
    weight_profile_id: Id | None
    applied_overrides: dict[Id, ValueFunctionSpec] = Field(default_factory=dict)
    resolved_domains: dict[Id, Domain | None] = Field(default_factory=dict)
    diagnostics: list[Issue] = Field(default_factory=list)
    delta_from_baseline: dict[Id, float] = Field(default_factory=dict)
    ranking: list[Id]
    values: dict[Id, float]
    rank_by_alternative: dict[Id, int]
    ranking_differs_from_baseline: bool
    winner_differs_from_baseline: bool


class ScenarioComparison(DomainModel):
    project_fingerprint: str
    configuration: AnalysisConfiguration
    scenario_ids: list[Id]
    baseline: ScenarioOutcome
    scenarios: list[ScenarioOutcome]
