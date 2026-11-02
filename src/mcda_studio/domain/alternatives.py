"""Alternatives (the options being compared)."""

from typing import Any

from pydantic import Field

from mcda_studio.domain.common import DomainModel, Id


class Alternative(DomainModel):
    id: Id
    name: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
