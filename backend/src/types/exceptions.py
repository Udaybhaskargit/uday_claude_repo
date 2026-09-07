"""Typed domain exceptions (E1-S3).

Every exception here carries enough context to build a useful API error
response without inspecting a stack trace, and (per E1-S3 AC4) maps to exactly
one HTTP status code via a class attribute plus the module-level
`EXCEPTION_STATUS_MAP`. A future `backend/src/api/error_handlers.py` (built in
a later group) consumes this map -- it is not created here, since `src/api/`
is out of scope for the Types layer.
"""

from typing import ClassVar


class DomainException(Exception):
    """Base class for every typed exception raised by the ClaimFlow domain."""

    http_status_code: ClassVar[int] = 500


class PolicyNotActiveException(DomainException):
    """Raised when a claim references a policy that is not active on the
    incident date (E4-S2). Maps to HTTP 422 (E1-S3 AC4)."""

    http_status_code: ClassVar[int] = 422

    def __init__(self, policy_number: str, incident_date: str) -> None:
        self.policy_number = policy_number
        self.incident_date = incident_date
        super().__init__(
            f"Policy {policy_number} is not active on {incident_date}."
        )


class DuplicateClaimException(DomainException):
    """Raised when a second FNOL is submitted for the same (policy, incident
    date) pair (E4-S3). Maps to HTTP 409 (E1-S3 AC4)."""

    http_status_code: ClassVar[int] = 409

    def __init__(self, policy_number: str, incident_date: str) -> None:
        self.policy_number = policy_number
        self.incident_date = incident_date
        super().__init__(
            f"A claim already exists for policy {policy_number} on {incident_date}."
        )


class InvalidClaimStateException(DomainException):
    """Raised by state_machine.transition() when the event has no entry in the
    claim's current state (E1-S2 AC2). Maps to HTTP 409 (E1-S3 AC4)."""

    http_status_code: ClassVar[int] = 409

    def __init__(self, message: str = "Invalid claim state transition.") -> None:
        super().__init__(message)


class UnknownClaimTypeError(DomainException):
    """Raised when a claim_type outside {MOTOR, HEALTH, LIFE} is requested.

    Maps to HTTP 422 (api-contracts.md sec "Claims API" error table: "422 |
    VALIDATION_ERROR | Missing/malformed field, unknown claim_type"). Not
    added to `EXCEPTION_STATUS_MAP` -- that dict's length is pinned to
    exactly 3 by E1-S3's own test (`test_exception_status_map_is_consistent
    _with_class_attributes`), covering only the 3 exceptions F013's AC text
    names explicitly. `error_handlers.py` (E9-S4) reads `http_status_code`
    directly off every `DomainException` subclass instead of consulting that
    map, so this ClassVar override is sufficient on its own.
    """

    http_status_code: ClassVar[int] = 422

    def __init__(self, claim_type: str) -> None:
        self.claim_type = claim_type
        super().__init__(f"Unknown claim type: {claim_type}")


class ConfigError(DomainException):
    """Raised when declarative config (fraud-rules.json, etc.) is missing or
    malformed at startup, rather than silently falling back to defaults.

    `variable_name` is optional context naming the specific config key or
    environment variable that caused the failure (e.g. E2-S3 AC3: a missing
    required environment variable must be named in the raised error), so
    callers that don't have a single named variable (e.g. a malformed JSON
    file) can omit it.
    """

    def __init__(self, message: str, *, variable_name: str | None = None) -> None:
        self.variable_name = variable_name
        super().__init__(message)


class ValidationError(DomainException):
    """Raised for domain validation failures that are not one of the more
    specific typed exceptions above (e.g. a missing mandatory reason_code).

    Maps to HTTP 422 (api-contracts.md: every `VALIDATION_ERROR` response
    across the API is a 422). See `UnknownClaimTypeError`'s docstring above
    for why this is a plain ClassVar override rather than an
    `EXCEPTION_STATUS_MAP` addition.
    """

    http_status_code: ClassVar[int] = 422


EXCEPTION_STATUS_MAP: dict[type[Exception], int] = {
    PolicyNotActiveException: PolicyNotActiveException.http_status_code,
    DuplicateClaimException: DuplicateClaimException.http_status_code,
    InvalidClaimStateException: InvalidClaimStateException.http_status_code,
}
