"""Tests for backend/src/types/exceptions.py (E1-S3)."""

import pytest
from src.types.exceptions import (
    EXCEPTION_STATUS_MAP,
    ConfigError,
    DuplicateClaimException,
    InvalidClaimStateException,
    PolicyNotActiveException,
    UnknownClaimTypeError,
    ValidationError,
)


def test_policy_not_active_exception_carries_policy_number_and_incident_date() -> None:
    # F011 / E1-S3 AC2
    exc = PolicyNotActiveException(policy_number="POL-MOTOR-0001", incident_date="2026-03-10")
    assert exc.policy_number == "POL-MOTOR-0001"
    assert exc.incident_date == "2026-03-10"
    assert "POL-MOTOR-0001" in str(exc)
    assert "2026-03-10" in str(exc)


def test_duplicate_claim_exception_carries_policy_number_and_incident_date() -> None:
    # F012 / E1-S3 AC3
    exc = DuplicateClaimException(policy_number="POL-MOTOR-0001", incident_date="2026-03-10")
    assert exc.policy_number == "POL-MOTOR-0001"
    assert exc.incident_date == "2026-03-10"


def test_policy_not_active_exception_is_raisable_and_catchable() -> None:
    with pytest.raises(PolicyNotActiveException) as excinfo:
        raise PolicyNotActiveException(policy_number="POL-1", incident_date="2026-01-01")
    assert excinfo.value.policy_number == "POL-1"


def test_duplicate_claim_exception_is_raisable_and_catchable() -> None:
    with pytest.raises(DuplicateClaimException) as excinfo:
        raise DuplicateClaimException(policy_number="POL-2", incident_date="2026-02-02")
    assert excinfo.value.incident_date == "2026-02-02"


def test_invalid_claim_state_exception_is_raisable_with_message() -> None:
    with pytest.raises(InvalidClaimStateException) as excinfo:
        raise InvalidClaimStateException("no such transition")
    assert "no such transition" in str(excinfo.value)


def test_exception_types_map_to_exactly_one_http_status_code_each() -> None:
    # F013 / E1-S3 AC4
    assert PolicyNotActiveException.http_status_code == 422
    assert DuplicateClaimException.http_status_code == 409
    assert InvalidClaimStateException.http_status_code == 409


def test_exception_status_map_is_consistent_with_class_attributes() -> None:
    assert EXCEPTION_STATUS_MAP[PolicyNotActiveException] == 422
    assert EXCEPTION_STATUS_MAP[DuplicateClaimException] == 409
    assert EXCEPTION_STATUS_MAP[InvalidClaimStateException] == 409
    assert len(EXCEPTION_STATUS_MAP) == 3


def test_unknown_claim_type_error_carries_offending_claim_type() -> None:
    exc = UnknownClaimTypeError("BOAT")
    assert exc.claim_type == "BOAT"
    assert "BOAT" in str(exc)


def test_config_error_and_validation_error_are_raisable() -> None:
    with pytest.raises(ConfigError):
        raise ConfigError("missing fraud-rules.json")
    with pytest.raises(ValidationError):
        raise ValidationError("reason_code is required")


def test_all_domain_exceptions_are_exception_subclasses() -> None:
    for exc_cls in (
        PolicyNotActiveException,
        DuplicateClaimException,
        InvalidClaimStateException,
        UnknownClaimTypeError,
        ConfigError,
        ValidationError,
    ):
        assert issubclass(exc_cls, Exception)
