"""Shared building blocks: id type, strict base model, diagnostics."""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

#: Stable internal identifier. Never derived from a display name, so renaming is safe.
Id = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$")]

#: A float that rejects NaN and +/-inf at the model boundary.
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class DomainModel(BaseModel):
    """Strict base: unknown fields are rejected and assignments are re-validated."""

    # Defaults are real values in anything the server *sends*, so the API schema marks them
    # required in responses (clients then never see `undefined` for e.g. `alternatives`).
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, json_schema_serialization_defaults_required=True
    )


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Issue(DomainModel):
    """A validation finding or an analysis diagnostic."""

    severity: Severity
    code: str
    message: str
    path: str = ""
