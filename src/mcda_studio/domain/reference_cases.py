"""The ``reference-cases`` sidecar, version 1 (``docs/design/reference-cases.md``).

A reference set holds past alternatives, each rated on the labelled criteria of one project as of
a dated snapshot, with the claims and sources behind every rating and a recorded outcome. It is a
separate local file: nothing here is stored in a project, and nothing here is a decision input.
The structural rules live in these models; the rules that need the project (criterion ids, scale
labels) and the snapshot guard live in ``services/reference_case_service.py``.
"""

import datetime as dt
import re
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, ConfigDict, Field, model_validator

from mcda_studio.domain.common import Id
from mcda_studio.domain.errors import ValidationFailed
from mcda_studio.domain.evidence import Origin, Source
from mcda_studio.domain.sidecar_common import SidecarModel

KIND = "reference-cases"
VERSION = 1

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _iso_date(value: Any) -> Any:
    """Accept a calendar date or an explicit ``YYYY-MM-DD`` string, nothing looser."""
    if isinstance(value, dt.datetime):
        raise ValueError("dates must be calendar dates (YYYY-MM-DD), not date-times")
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str) and _ISO_DATE.match(value):
        return dt.date.fromisoformat(value)
    raise ValueError("dates must be explicit ISO calendar dates (YYYY-MM-DD)")


IsoDate = Annotated[dt.date, BeforeValidator(_iso_date)]
Text = Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S")]
ShortText = Annotated[str, Field(min_length=1, max_length=300, pattern=r"\S")]
Note = Annotated[str, Field(max_length=1000)]


class ReferenceSource(Source):
    """The evidence ``Source``, except that its date may be unknown.

    ``date`` is the day the source was published or, for an archived capture, captured. An undated
    source may support an outcome but never a rating (the snapshot guard).
    """

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_assignment=True,
        json_schema_serialization_defaults_required=True,
    )

    date: IsoDate | None = None  # type: ignore[assignment]


class ContextRow(SidecarModel):
    """One row of context, shown exactly as written."""

    label: ShortText
    value: Text


class ReferenceClaim(SidecarModel):
    """One statement in the author's own words, with the source it rests on."""

    id: Id
    text: Text
    source: Id  # a key of ``ReferenceCases.sources``
    origin: Origin


class ReferenceRating(SidecarModel):
    """A scale label for one leaf criterion as of the case's snapshot."""

    criterion_id: Id
    label: Annotated[str, Field(min_length=1, max_length=300)]
    claim_ids: Annotated[list[Id], Field(min_length=1, max_length=50)]
    note: Note = ""


class ReferenceOutcome(SidecarModel):
    """What the reference set's author recorded as happening after the snapshot."""

    label: ShortText
    as_of: IsoDate
    note: Note = ""
    claim_ids: Annotated[list[Id], Field(max_length=50)] = []


class ReferenceCase(SidecarModel):
    id: Id
    name: ShortText
    snapshot_date: IsoDate
    context: Annotated[list[ContextRow], Field(max_length=50)] = []
    claims: Annotated[list[ReferenceClaim], Field(max_length=500)] = []
    ratings: Annotated[list[ReferenceRating], Field(max_length=500)] = []
    outcome: ReferenceOutcome


class ReferenceCases(SidecarModel):
    """A reference set: past alternatives rated on one project's labelled criteria."""

    kind: Literal["reference-cases"]
    version: Literal[1]
    id: Id
    title: ShortText
    description: Annotated[str, Field(max_length=4000)] = ""
    criteria_from: Id  # the id of the project whose criteria tree the labels use
    cases: Annotated[list[ReferenceCase], Field(max_length=500)] = []
    sources: Annotated[dict[Id, ReferenceSource], Field(max_length=5000)] = {}

    @model_validator(mode="before")
    @classmethod
    def known_kind_and_version(cls, value: Any) -> Any:
        if isinstance(value, dict):
            if "kind" in value and value["kind"] != KIND:
                raise ValueError(f"this is not a reference set (kind must be {KIND!r})")
            version = value.get("version")
            if type(version) is int and version != VERSION:
                raise ValueError(
                    f"reference-cases version {version} is not supported; this build reads "
                    f"version {VERSION} only"
                )
        return value


class ReferenceCasesInvalid(ValidationFailed):
    """The reference set does not fit the project, or a rating breaks the snapshot guard."""

    def __init__(self, report: Any) -> None:
        self.report = report
        errors = getattr(report, "errors", [])
        lines = [f"[{e.code}] {e.path + ': ' if e.path else ''}{e.message}" for e in errors[:10]]
        more = f"\n... and {len(errors) - 10} more" if len(errors) > 10 else ""
        Exception.__init__(
            self,
            f"reference set has {len(errors)} validation error(s):\n" + "\n".join(lines) + more,
        )
