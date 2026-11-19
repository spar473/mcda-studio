"""New checked-run envelope around unchanged fundamental-factor result and record formats."""

from typing import Literal

from mcda_studio.domain.decision import DecisionDetails
from mcda_studio.domain.derived import DerivedModel
from mcda_studio.domain.errors import ModelEditError
from mcda_studio.domain.factor_uncertainty import FactorUncertaintyModel
from mcda_studio.domain.model_comparison import (
    EnclosureRange,
    ModelChecks,
    ModelOutputSpec,
    ModelScope,
)
from mcda_studio.domain.project import Project
from mcda_studio.domain.sidecar_common import SidecarModel
from mcda_studio.services import derived_service as derived
from mcda_studio.services import factor_analysis_service as analysis
from mcda_studio.services import model_checks_service as checks


class CheckedFactorRun(SidecarModel):
    artifact_kind: Literal["checked_factor_run"] = "checked_factor_run"
    version: Literal[1] = 1
    source_project: Project
    original_model: DerivedModel
    original_uncertainty: FactorUncertaintyModel
    checks: ModelChecks
    checks_digest: str
    omitted_quantity_ids: list[str]
    record: analysis.FactorRunRecord
    digest: str


def run(
    project: Project,
    model: DerivedModel,
    uncertainty: FactorUncertaintyModel,
    declaration: ModelChecks,
    parameters: analysis.FactorRunParameters,
    decision: DecisionDetails | None = None,
) -> CheckedFactorRun:
    targets = [f.id for f in model.formulas if f.alternative_id is not None]
    if not targets:
        checks.fail("MODEL_ANALYSIS_TARGET", "checked preference runs need a measurement target")
    scoped = checks.scope_model(
        project,
        ModelOutputSpec(
            id="measurement_scope",
            label="All declared measurement targets and quantity checks",
            model=model,
            formula_id=targets[0],
            scope=ModelScope(),
            range=EnclosureRange(),
            uncertainty=uncertainty,
            checks=declaration,
        ),
        targets,
        detach_targets=False,
    )
    result = analysis.execute(
        project,
        scoped.model,
        scoped.uncertainty,
        parameters,
        decision,
        check_plan=lambda plan: checks.preflight(declaration, plan),
        check_draw=lambda values, index: checks.check_values(declaration, values, index),
    )
    envelope = CheckedFactorRun(
        source_project=project.model_copy(deep=True),
        original_model=model.model_copy(deep=True),
        original_uncertainty=uncertainty.model_copy(deep=True),
        checks=declaration.model_copy(deep=True),
        checks_digest=declaration.digest,
        omitted_quantity_ids=scoped.omitted,
        record=result,
        digest="",
    )
    envelope.digest = derived._digest(envelope.model_dump(mode="json", exclude={"digest"}))
    return envelope


def verify(envelope: CheckedFactorRun) -> CheckedFactorRun:
    if envelope.digest != derived._digest(envelope.model_dump(mode="json", exclude={"digest"})):
        raise ModelEditError("MODEL_CHECKED_RUN_CHANGED: envelope digest does not match")
    rebuilt = run(
        envelope.source_project,
        envelope.original_model,
        envelope.original_uncertainty,
        envelope.checks,
        envelope.record.parameters,
        envelope.record.decision.decision if envelope.record.decision else None,
    )
    if rebuilt != envelope:
        raise ModelEditError("MODEL_CHECKED_RUN_MISMATCH: checked run does not reproduce")
    return envelope
