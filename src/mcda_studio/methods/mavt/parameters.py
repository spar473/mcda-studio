"""MAVT's own analysis parameters, parsed from ``AnalysisConfiguration.parameters``."""

from pydantic import BaseModel, ConfigDict, StrictBool

from mcda_studio.domain.preferences import AnalysisConfiguration


class MavtParameters(BaseModel):
    # Unknown keys are reported by validation as UNKNOWN_PARAMETER warnings and ignored here.
    model_config = ConfigDict(extra="ignore", frozen=True)

    #: report pairwise dominance between alternatives (results and analysis records)
    dominance_check: StrictBool = True


def mavt_parameters(configuration: AnalysisConfiguration) -> MavtParameters:
    """Parsed parameters; validation has already refused wrongly typed ones."""
    return MavtParameters.model_validate(configuration.parameters)
