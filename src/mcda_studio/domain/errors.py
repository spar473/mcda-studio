"""Exception hierarchy. Every error raised deliberately by the library derives from McdaError."""

from typing import Any


class McdaError(Exception):
    """Base class for all MCDA Studio errors."""


class ModelStructureError(McdaError):
    """The criteria tree (or another structural invariant) is malformed."""


class ModelEditError(McdaError):
    """An editing operation would corrupt the model or silently discard data."""


class UnknownReferenceError(McdaError):
    """An id (alternative, criterion, weight profile, scenario) does not exist."""


class DomainError(McdaError):
    """A measurement lies outside the domain of its value function (no silent extrapolation)."""


class WeightError(McdaError):
    """Weighting judgements are invalid (negative, non-finite, missing or all zero)."""


class SensitivityError(McdaError):
    """A sensitivity analysis is mathematically undefined for the requested parameter."""


class ProjectLoadError(McdaError):
    """A project file cannot be read, parsed, migrated or schema-validated."""


class ProjectNotFoundError(McdaError):
    """No stored project has the requested id."""


class ProjectExistsError(McdaError):
    """A stored project with this id already exists (it is never overwritten implicitly)."""


class StaleRevisionError(McdaError):
    """The stored project changed since the revision the caller based its edit on."""


class ValidationFailed(McdaError):  # noqa: N818 - reads better than ValidationFailedError
    """The project has validation errors, so it cannot be evaluated."""

    def __init__(self, report: Any) -> None:
        self.report = report
        errors = getattr(report, "errors", [])
        lines = [f"[{e.code}] {e.path + ': ' if e.path else ''}{e.message}" for e in errors[:10]]
        more = f"\n... and {len(errors) - 10} more" if len(errors) > 10 else ""
        super().__init__(
            f"project has {len(errors)} validation error(s):\n" + "\n".join(lines) + more
        )


class MethodNotSupportedError(McdaError):
    """The configured method does not offer what the request needs (a capability or record)."""

    def __init__(self, method: str, requirement: str, capabilities: list[str]) -> None:
        self.method = method
        self.requirement = requirement
        self.capabilities = capabilities
        super().__init__(f"method {method!r} does not support {requirement!r}")


class AnalysisLimitError(McdaError):
    """A bounded analytical workspace request or export is too large."""


class AnalysisExportError(McdaError):
    """A completed analysis cannot supply the requested export."""


class ConvergenceError(McdaError):
    """An iterative calculation did not converge; no partial result is reported."""
