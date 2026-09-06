"""Closed enum sets for the ClaimFlow domain (E1-S1, E1-S3).

These are the single source of truth for every downstream layer (config,
repositories, services, API). This module imports nothing else in `src/` --
it is Layer 1, the lowest layer, per `.claude/architecture.md`.
"""

from enum import StrEnum


class Role(StrEnum):
    """Who is acting: E1-S1 AC3."""

    CUSTOMER = "CUSTOMER"
    ASSESSOR = "ASSESSOR"
    ADMIN = "ADMIN"


class ClaimType(StrEnum):
    """The three insurance products ClaimFlow supports."""

    MOTOR = "MOTOR"
    HEALTH = "HEALTH"
    LIFE = "LIFE"


class PolicyStatus(StrEnum):
    """Policy lifecycle status (data-models.md sec 1)."""

    ACTIVE = "ACTIVE"
    LAPSED = "LAPSED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ClaimStatus(StrEnum):
    """Claim lifecycle status: exactly these 10 values, E1-S1 AC2."""

    INTAKE = "INTAKE"
    DOCS_PENDING = "DOCS_PENDING"
    FRAUD_SCREENING = "FRAUD_SCREENING"
    ASSESSMENT = "ASSESSMENT"
    AUTO_APPROVED = "AUTO_APPROVED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    REJECTED = "REJECTED"
    SETTLED = "SETTLED"
    REOPENED = "REOPENED"
    PROCESSING_FAILED = "PROCESSING_FAILED"


class DocumentType(StrEnum):
    """Per-claim-type document checklist entries (data-models.md sec 2.3)."""

    POLICE_FIR = "POLICE_FIR"
    INVOICE = "INVOICE"
    HOSPITAL_BILL = "HOSPITAL_BILL"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"
    DEATH_CERTIFICATE = "DEATH_CERTIFICATE"


class VerificationStatus(StrEnum):
    """Whether a ClaimDocument has been checked off."""

    VERIFIED = "VERIFIED"
    MISSING = "MISSING"


class DecisionOutcome(StrEnum):
    """The assessor/engine's verb-form recommendation on a Decision row."""

    AUTO_APPROVE = "AUTO_APPROVE"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    REJECT = "REJECT"


class ReasonCode(StrEnum):
    """Closed domain set used on Decision rows and PolicyNotActiveException.

    Exactly these 6 values, E1-S3 AC1. See data-models.md sec 1 for why this is
    a smaller, distinct set from ApiErrorCode below.
    """

    POLICY_INACTIVE = "POLICY_INACTIVE"
    ZERO_PAYABLE_AMOUNT = "ZERO_PAYABLE_AMOUNT"
    FRAUD_FLAG = "FRAUD_FLAG"
    AUTO_APPROVED_LOW_RISK = "AUTO_APPROVED_LOW_RISK"
    HIGH_VALUE_REVIEW = "HIGH_VALUE_REVIEW"
    DOCS_INCOMPLETE = "DOCS_INCOMPLETE"


class ApiErrorCode(StrEnum):
    """Broader HTTP error-envelope set (API layer only, never persisted)."""

    POLICY_INACTIVE = "POLICY_INACTIVE"
    DUPLICATE_CLAIM = "DUPLICATE_CLAIM"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNKNOWN_CLAIM_TYPE = "UNKNOWN_CLAIM_TYPE"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    PROCESSING_FAILED = "PROCESSING_FAILED"


class AdminOverrideCommand(StrEnum):
    """Commands an admin can issue via the E8-S2 override service."""

    FORCE_APPROVE = "FORCE_APPROVE"
    FORCE_REJECT = "FORCE_REJECT"
    FORCE_MANUAL_REVIEW = "FORCE_MANUAL_REVIEW"
    FORCE_RETRY = "FORCE_RETRY"


class ClaimEvent(StrEnum):
    """Every event name that appears in the E1-S2 transition table (sec 1.1)."""

    ATTACH_CHECKLIST = "ATTACH_CHECKLIST"
    DOCS_VERIFIED = "DOCS_VERIFIED"
    ADMIN_FORCE_REJECT = "ADMIN_FORCE_REJECT"
    FRAUD_CLEARED = "FRAUD_CLEARED"
    FRAUD_FLAGGED = "FRAUD_FLAGGED"
    PIPELINE_ERROR = "PIPELINE_ERROR"
    DECISION_AUTO_APPROVE = "DECISION_AUTO_APPROVE"
    DECISION_MANUAL_REVIEW = "DECISION_MANUAL_REVIEW"
    DECISION_REJECT = "DECISION_REJECT"
    ASSESSOR_APPROVE = "ASSESSOR_APPROVE"
    ASSESSOR_REJECT = "ASSESSOR_REJECT"
    ADMIN_FORCE_APPROVE = "ADMIN_FORCE_APPROVE"
    ADMIN_FORCE_MANUAL_REVIEW = "ADMIN_FORCE_MANUAL_REVIEW"
    SETTLE = "SETTLE"
    REOPEN = "REOPEN"
    RETRY_TO_DOCS_PENDING = "RETRY_TO_DOCS_PENDING"
    RETRY_TO_FRAUD_SCREENING = "RETRY_TO_FRAUD_SCREENING"
    RETRY_TO_ASSESSMENT = "RETRY_TO_ASSESSMENT"
