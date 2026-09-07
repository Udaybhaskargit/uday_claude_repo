"""Exception -> HTTP status/code mapping (API layer, E1-S3 AC4, E9-S4).

Registers two FastAPI exception handlers on the app: every `DomainException`
subclass (E1-S3) is translated to its own declared `http_status_code` plus
the uniform error envelope api-contracts.md defines (`{"error": {"code",
"message", "details"}}`); a bare `LookupError` -- raised by repository/
service code such as `ClaimRepository.apply_transition()` and
`admin_override_service.override()` when a claim id doesn't exist -- is
translated to 404/`NOT_FOUND`, since no typed "claim not found" domain
exception exists in `src/types/exceptions.py` yet.

`_DOMAIN_EXCEPTION_ERROR_CODES` is a router-local mapping to the JSON `code`
string, deliberately NOT `src.types.exceptions.EXCEPTION_STATUS_MAP` --
that dict's length is pinned to exactly 3 by an existing E1-S3 test
(`test_exception_status_map_is_consistent_with_class_attributes`), covering
only the 3 exceptions F013's AC text names explicitly. The HTTP *status*
for every `DomainException` is instead read directly off `exc.
http_status_code`, which every subclass (including `ValidationError` and
`UnknownClaimTypeError`, added in Group F) already declares correctly --
so this module needs no separate status table at all, only the code-string
lookup for the envelope's `code` field.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.types.enums import ApiErrorCode
from src.types.exceptions import (
    DomainException,
    DuplicateClaimException,
    InvalidClaimStateException,
    PolicyNotActiveException,
    UnknownClaimTypeError,
    ValidationError,
)

_DOMAIN_EXCEPTION_ERROR_CODES: dict[type[DomainException], ApiErrorCode] = {
    PolicyNotActiveException: ApiErrorCode.POLICY_INACTIVE,
    DuplicateClaimException: ApiErrorCode.DUPLICATE_CLAIM,
    InvalidClaimStateException: ApiErrorCode.INVALID_STATE_TRANSITION,
    UnknownClaimTypeError: ApiErrorCode.VALIDATION_ERROR,
    ValidationError: ApiErrorCode.VALIDATION_ERROR,
}


def _error_envelope(code: ApiErrorCode, message: str) -> dict[str, object]:
    return {"error": {"code": code.value, "message": message, "details": {}}}


def register_error_handlers(app: FastAPI) -> None:
    """Attach the domain-exception and not-found handlers to `app`."""

    @app.exception_handler(DomainException)
    async def _handle_domain_exception(request: Request, exc: DomainException) -> JSONResponse:
        code = _DOMAIN_EXCEPTION_ERROR_CODES.get(type(exc), ApiErrorCode.VALIDATION_ERROR)
        return JSONResponse(
            status_code=exc.http_status_code,
            content=_error_envelope(code, str(exc)),
        )

    @app.exception_handler(LookupError)
    async def _handle_lookup_error(request: Request, exc: LookupError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=_error_envelope(ApiErrorCode.NOT_FOUND, str(exc)),
        )
