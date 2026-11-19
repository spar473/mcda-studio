"""The interface every MCDA method implements, and a registry to look methods up by name.

Methods own their configuration vocabulary (``AnalysisConfiguration.parameters``), their
validation and their result type; they must not be forced into MAVT's value-function model (AHP
needs pairwise matrices, PROMETHEE needs preference functions and flows). A method declares what
it can do as capabilities, and every route or panel that only makes sense for some methods checks
one (see ``docs/design/method-seam.md``).
"""

from typing import Literal, Protocol, get_args

from pydantic import BaseModel, ValidationError

from mcda_studio.domain.common import Issue, Severity
from mcda_studio.domain.errors import MethodNotSupportedError, UnknownReferenceError
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import AnalysisResult
from mcda_studio.domain.validation import ValidationReport, check_configuration_ids

#: Closed vocabulary of what a route or panel may check, so a typo is a type error.
Capability = Literal[
    "value_functions",
    "swing_weights",
    "value_scores",
    "contributions",
    "weight_sensitivity",
    "scenario_comparison",
    "classes",
    "acceptability",
    "flows",
    "consistency",
]
CAPABILITIES: tuple[Capability, ...] = get_args(Capability)

#: The version-1 analysis record and its exports hold MAVT data; other methods get version 2.
RECORD_V1_METHOD = "mavt"


class Method(Protocol):
    name: str  # stable id, e.g. "mavt"
    label: str  # shown in the interface
    capabilities: frozenset[Capability]

    def validate(self, project: Project, configuration: AnalysisConfiguration) -> list[Issue]: ...

    def evaluate(
        self, project: Project, configuration: AnalysisConfiguration
    ) -> AnalysisResult: ...


_REGISTRY: dict[str, Method] = {}


def register(method: Method) -> None:
    _REGISTRY[method.name] = method


def unregister(name: str) -> None:
    """Remove a method (tests register temporary ones)."""
    _REGISTRY.pop(name, None)


def get_method(name: str) -> Method:
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "none"
        raise UnknownReferenceError(f"unknown MCDA method {name!r} (available: {known})") from None


def available_methods() -> list[str]:
    return sorted(_REGISTRY)


def registered_methods() -> list[str]:
    """Method names in registration order: MAVT first, then each method as it was added."""
    return list(_REGISTRY)


def validate_analysis(project: Project, configuration: AnalysisConfiguration) -> ValidationReport:
    """Method-independent checks, then the configured method's own validation.

    An unregistered method is reported as ``UNKNOWN_METHOD``; nothing else can be checked then.
    """
    issues = check_configuration_ids(project)
    method = _REGISTRY.get(configuration.method)
    if method is None:
        known = ", ".join(sorted(_REGISTRY)) or "none"
        issues.append(
            Issue(
                severity=Severity.ERROR,
                code="UNKNOWN_METHOD",
                message=f"unknown MCDA method {configuration.method!r} (available: {known})",
                path="configuration.method",
            )
        )
        return ValidationReport(issues=issues)
    issues.extend(method.validate(project, configuration))
    return ValidationReport(issues=issues)


def _refuse(method: Method, requirement: str) -> MethodNotSupportedError:
    return MethodNotSupportedError(method.name, requirement, sorted(method.capabilities))


def require_capability(configuration: AnalysisConfiguration, capability: Capability) -> None:
    """Refuse a request the configured method cannot serve.

    An unregistered method passes through, so validation reports it as ``UNKNOWN_METHOD`` exactly
    as it does for evaluation.
    """
    method = _REGISTRY.get(configuration.method)
    if method is not None and capability not in method.capabilities:
        raise _refuse(method, capability)


def require_record_v1(configuration: AnalysisConfiguration) -> None:
    """Version-1 analysis records and their exports hold MAVT data only."""
    method = _REGISTRY.get(configuration.method)
    if method is not None and method.name != RECORD_V1_METHOD:
        raise _refuse(method, "analysis_record")


def check_parameters(model: type[BaseModel], parameters: dict[str, object]) -> list[Issue]:
    """Issues for one method's parameters: unknown keys warn, wrongly typed known keys fail."""
    issues: list[Issue] = []
    for key in sorted(set(parameters) - set(model.model_fields)):
        issues.append(
            Issue(
                severity=Severity.WARNING,
                code="UNKNOWN_PARAMETER",
                message=f"parameter {key!r} is not used by this method and is ignored",
                path=f"configuration.parameters.{key}",
            )
        )
    known = {k: v for k, v in parameters.items() if k in model.model_fields}
    try:
        model.model_validate(known)
    except ValidationError as exc:
        for error in exc.errors():
            key = ".".join(str(p) for p in error["loc"])
            issues.append(
                Issue(
                    severity=Severity.ERROR,
                    code="INVALID_PARAMETER",
                    message=f"parameter {key!r}: {error['msg']}",
                    path=f"configuration.parameters.{key}",
                )
            )
    return issues
