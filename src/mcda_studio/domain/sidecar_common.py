"""Strict boundary for new sidecars; existing versioned formats keep their own validators."""

from typing import Any, Literal, get_args, get_origin

from pydantic import ConfigDict, model_validator

from mcda_studio.domain.common import DomainModel


class SidecarModel(DomainModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_assignment=True,
        json_schema_serialization_defaults_required=True,
    )

    @model_validator(mode="before")
    @classmethod
    def integer_versions(cls, value: Any) -> Any:
        if isinstance(value, dict):
            for key in ("schema_version", "version"):
                field = cls.model_fields.get(key)
                annotation = field.annotation if field else None
                integer_version = annotation is int or (
                    get_origin(annotation) is Literal
                    and all(type(item) is int for item in get_args(annotation))
                )
                if integer_version and key in value and type(value[key]) is not int:
                    raise ValueError("sidecar versions must be explicit integers")
        return value
