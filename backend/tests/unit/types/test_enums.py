"""Tests for backend/src/types/enums.py (E1-S1, E1-S3)."""

from src.types.enums import (
    AdminOverrideCommand,
    ApiErrorCode,
    ClaimEvent,
    ClaimStatus,
    ClaimType,
    DecisionOutcome,
    DocumentType,
    PolicyStatus,
    ReasonCode,
    Role,
    VerificationStatus,
)


def test_role_enum_contains_exactly_three_values() -> None:
    # F003 / E1-S1 AC3
    assert {member.value for member in Role} == {"CUSTOMER", "ASSESSOR", "ADMIN"}
    assert len(Role) == 3


def test_claim_type_enum_contains_exactly_three_values() -> None:
    assert {member.value for member in ClaimType} == {"MOTOR", "HEALTH", "LIFE"}
    assert len(ClaimType) == 3


def test_policy_status_enum_contains_expected_values() -> None:
    # F004 / E1-S1 AC4 ("ACTIVE|LAPSED|...")
    assert {member.value for member in PolicyStatus} == {
        "ACTIVE",
        "LAPSED",
        "EXPIRED",
        "CANCELLED",
    }


def test_claim_status_enum_contains_exactly_ten_values_in_order() -> None:
    # F002 / E1-S1 AC2
    expected = [
        "INTAKE",
        "DOCS_PENDING",
        "FRAUD_SCREENING",
        "ASSESSMENT",
        "AUTO_APPROVED",
        "MANUAL_REVIEW",
        "REJECTED",
        "SETTLED",
        "REOPENED",
        "PROCESSING_FAILED",
    ]
    assert [member.value for member in ClaimStatus] == expected
    assert len(ClaimStatus) == 10


def test_document_type_enum_covers_all_checklist_types() -> None:
    assert {member.value for member in DocumentType} == {
        "POLICE_FIR",
        "INVOICE",
        "HOSPITAL_BILL",
        "DISCHARGE_SUMMARY",
        "DEATH_CERTIFICATE",
    }


def test_verification_status_enum_contains_exactly_two_values() -> None:
    assert {member.value for member in VerificationStatus} == {"VERIFIED", "MISSING"}


def test_decision_outcome_enum_contains_exactly_three_values() -> None:
    assert {member.value for member in DecisionOutcome} == {
        "AUTO_APPROVE",
        "MANUAL_REVIEW",
        "REJECT",
    }


def test_reason_code_enum_contains_exactly_six_values() -> None:
    # F010 / E1-S3 AC1
    expected = {
        "POLICY_INACTIVE",
        "ZERO_PAYABLE_AMOUNT",
        "FRAUD_FLAG",
        "AUTO_APPROVED_LOW_RISK",
        "HIGH_VALUE_REVIEW",
        "DOCS_INCOMPLETE",
    }
    assert {member.value for member in ReasonCode} == expected
    assert len(ReasonCode) == 6


def test_api_error_code_enum_is_a_superset_of_reason_code() -> None:
    expected = {
        "POLICY_INACTIVE",
        "DUPLICATE_CLAIM",
        "INVALID_STATE_TRANSITION",
        "VALIDATION_ERROR",
        "UNKNOWN_CLAIM_TYPE",
        "UNAUTHORIZED",
        "FORBIDDEN",
        "NOT_FOUND",
        "PROCESSING_FAILED",
    }
    assert {member.value for member in ApiErrorCode} == expected
    # DUPLICATE_CLAIM is an API-only error code, never a ReasonCode (data-models.md sec 1)
    assert "DUPLICATE_CLAIM" not in {member.value for member in ReasonCode}


def test_admin_override_command_enum_contains_exactly_four_values() -> None:
    assert {member.value for member in AdminOverrideCommand} == {
        "FORCE_APPROVE",
        "FORCE_REJECT",
        "FORCE_MANUAL_REVIEW",
        "FORCE_RETRY",
    }


def test_claim_event_enum_covers_every_transition_table_event() -> None:
    expected = {
        "ATTACH_CHECKLIST",
        "DOCS_VERIFIED",
        "ADMIN_FORCE_REJECT",
        "FRAUD_CLEARED",
        "FRAUD_FLAGGED",
        "PIPELINE_ERROR",
        "DECISION_AUTO_APPROVE",
        "DECISION_MANUAL_REVIEW",
        "DECISION_REJECT",
        "ASSESSOR_APPROVE",
        "ASSESSOR_REJECT",
        "ADMIN_FORCE_APPROVE",
        "ADMIN_FORCE_MANUAL_REVIEW",
        "SETTLE",
        "REOPEN",
        "RETRY_TO_DOCS_PENDING",
        "RETRY_TO_FRAUD_SCREENING",
        "RETRY_TO_ASSESSMENT",
    }
    assert {member.value for member in ClaimEvent} == expected
    assert len(ClaimEvent) == 18


def test_all_enums_are_string_backed() -> None:
    assert isinstance(Role.CUSTOMER, str)
    assert Role.CUSTOMER == "CUSTOMER"
    assert isinstance(ClaimStatus.INTAKE, str)
    assert isinstance(ClaimEvent.SETTLE, str)
