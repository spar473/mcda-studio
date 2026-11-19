"""Every method's reading of one model, side by side (``docs/design/method-comparison.md``).

Each column is one method's own result, unchanged, or its typed error. No field holds a number
computed from two methods: agreement is about orders and classes only, and every reason is taken
from the method's own result. There is no consensus score.
"""

from typing import Literal

from pydantic import Field

from mcda_studio.domain.common import DomainModel, Id
from mcda_studio.domain.preferences import AnalysisConfiguration

ComparisonContext = Literal[
    "Agreement between methods that share inputs is not independent validation."
]
COMPARISON_CONTEXT: ComparisonContext = (
    "Agreement between methods that share inputs is not independent validation."
)


class ColumnError(DomainModel):
    """A method that cannot read the model: its error exactly as ``/evaluate`` would return it."""

    status: int
    code: str
    message: str
    issue_codes: list[str]  # for VALIDATION_FAILED, the error codes; otherwise empty


class ComparisonCell(DomainModel):
    """One method's own reading of one alternative."""

    alternative_id: Id
    rank: int  # the method's own competition rank
    quantity: float  # the method's own number, named by its column
    interval: tuple[float, float] | None  # SMAA-2 sampled runs: the rank-1 interval
    class_id: Id | None  # sorting's class, or SMAA-2's most frequent class
    class_share: float | None  # SMAA-2: how often the alternative took that class
    notes: list[str]  # at most two method-specific facts


class ComparisonColumn(DomainModel):
    method: str
    method_label: str
    status: Literal["ok", "failed"]
    configuration: AnalysisConfiguration  # what this column ran with
    inputs: list[str]  # the sections, profile and scenario it read
    calculation_path: str | None
    record_digest: str | None  # the method's own record, so the column can be reproduced
    label: str | None  # the method's own label, if it has one
    quantity_name: str | None  # e.g. "overall value"
    quantity_range: str | None  # e.g. "0 to 1"
    leaders: list[Id]  # the method's rank-1 alternatives (SMAA-2: its leader)
    cells: list[ComparisonCell]  # in the project's alternative order; empty when failed
    error: ColumnError | None


class LeaderGroup(DomainModel):
    leaders: list[Id]
    methods: list[str]


class ClassAgreement(DomainModel):
    alternative_id: Id
    sorting_class_id: Id
    smaa_class_id: Id
    smaa_class_share: float
    agree: bool


class ColumnReason(DomainModel):
    """Why one method's leaders differ from MAVT's, from that method's own result."""

    method: str
    leaders: list[Id]
    mavt_leaders: list[Id]
    reasons: list[str]


class Agreement(DomainModel):
    leaders_agree: bool | None  # None when fewer than two columns ran
    leader_groups: list[LeaderGroup]  # columns grouped by their leaders, in column order
    classes: list[ClassAgreement]  # empty unless sorting and SMAA-2 with classes both ran
    reasons: list[ColumnReason]
    context: ComparisonContext = COMPARISON_CONTEXT


class MethodComparison(DomainModel):
    project_id: Id
    project_fingerprint: str
    configuration: AnalysisConfiguration  # the selected profile and scenario
    methods: list[str]  # the methods requested, in registry order
    alternative_order: list[Id]
    alternative_names: dict[Id, str]
    columns: list[ComparisonColumn] = Field(default_factory=list)
    agreement: Agreement
