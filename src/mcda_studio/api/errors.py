"""One error shape for the whole API:  {"error": {"code", "message", "details": [...]}}.

``details`` is a list of ``{"path", "message"}`` (and, for validation failures, the full issue
records). Codes are stable identifiers a client can switch on; messages are for people.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from mcda_studio.domain.errors import (
    AnalysisExportError,
    AnalysisLimitError,
    ConvergenceError,
    DomainError,
    McdaError,
    MethodNotSupportedError,
    ModelEditError,
    ModelStructureError,
    ProjectExistsError,
    ProjectLoadError,
    ProjectNotFoundError,
    SensitivityError,
    StaleRevisionError,
    UnknownReferenceError,
    ValidationFailed,
    WeightError,
)
from mcda_studio.services.factor_uncertainty_service import DrawError
from mcda_studio.storage.library_lock import LibraryBusyError, LibraryLockError
from mcda_studio.storage.project_store import (
    InvalidProjectIdError,
    InvalidTrashEntryError,
    RestoreError,
    UnreadableTrashEntryError,
)

#: exception class -> (HTTP status, stable code); first isinstance match wins
_MAPPING: list[tuple[type[McdaError], int, str]] = [
    (LibraryBusyError, 409, "LIBRARY_BUSY"),
    (LibraryLockError, 422, "LIBRARY_LOCK_UNAVAILABLE"),
    (InvalidTrashEntryError, 422, "TRASH_ENTRY_INVALID"),
    (UnreadableTrashEntryError, 422, "TRASH_ENTRY_UNREADABLE"),
    (RestoreError, 500, "RESTORE_FAILED"),
    (AnalysisLimitError, 413, "ANALYSIS_LIMIT"),
    (AnalysisExportError, 422, "EXPORT_UNAVAILABLE"),
    (ConvergenceError, 422, "AHP_NO_CONVERGENCE"),
    (MethodNotSupportedError, 422, "METHOD_NOT_SUPPORTED"),
    (ProjectNotFoundError, 404, "PROJECT_NOT_FOUND"),
    (ProjectExistsError, 409, "PROJECT_EXISTS"),
    (StaleRevisionError, 412, "STALE_REVISION"),
    (InvalidProjectIdError, 422, "INVALID_PROJECT_ID"),
    (UnknownReferenceError, 422, "UNKNOWN_REFERENCE"),
    (ModelEditError, 409, "EDIT_REFUSED"),
    (ModelStructureError, 422, "MODEL_STRUCTURE"),
    (ValidationFailed, 422, "VALIDATION_FAILED"),
    (SensitivityError, 422, "SENSITIVITY_UNDEFINED"),
    (DrawError, 422, "INVALID_FACTOR_DRAW"),
    (DomainError, 422, "OUT_OF_DOMAIN"),
    (WeightError, 422, "INVALID_WEIGHTS"),
    (ProjectLoadError, 500, "STORED_PROJECT_UNREADABLE"),
    (McdaError, 400, "MCDA_ERROR"),
]


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or []
        self.headers = headers


def from_mcda_error(exc: McdaError, path: str = "") -> ApiError:
    for cls, status, code in _MAPPING:
        if isinstance(exc, cls):
            details: list[dict[str, Any]] = []
            if isinstance(exc, ValidationFailed):
                details = [i.model_dump(mode="json") for i in exc.report.errors]
            elif isinstance(exc, DrawError):
                details = [
                    {
                        "path": f"formulas[{exc.formula_id}]",
                        "message": str(exc),
                        "draw": exc.draw,
                        "formula_id": exc.formula_id,
                        "factor_ids": exc.factor_ids,
                    }
                ]
            elif isinstance(exc, MethodNotSupportedError):
                details = [
                    {
                        "path": "configuration.method",
                        "message": str(exc),
                        "method": exc.method,
                        "requirement": exc.requirement,
                        "capabilities": exc.capabilities,
                    }
                ]
            elif path:
                details = [{"path": path, "message": str(exc)}]
            return ApiError(status, code, str(exc).splitlines()[0], details)
    return ApiError(400, "MCDA_ERROR", str(exc))  # unreachable: McdaError is in the table


def body(code: str, message: str, details: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or []}}


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            body(exc.code, exc.message, exc.details), status_code=exc.status, headers=exc.headers
        )

    @app.exception_handler(McdaError)
    async def _mcda_error(_: Request, exc: McdaError) -> JSONResponse:
        api = from_mcda_error(exc)
        return JSONResponse(body(api.code, api.message, api.details), status_code=api.status)

    @app.exception_handler(RequestValidationError)
    async def _request_invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"path": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()
        ]
        first = details[0]["message"] if details else "invalid request"
        return JSONResponse(
            body("INVALID_REQUEST", f"the request body is invalid: {first}", details),
            status_code=422,
        )
