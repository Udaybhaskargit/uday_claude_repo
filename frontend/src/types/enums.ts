// Mirrors backend/src/types/enums.py -- the single source of truth for these
// closed sets lives there; keep this file in sync by hand when it changes.

export const Role = {
  CUSTOMER: "CUSTOMER",
  ASSESSOR: "ASSESSOR",
  ADMIN: "ADMIN",
} as const;
export type Role = (typeof Role)[keyof typeof Role];

export const ClaimType = {
  MOTOR: "MOTOR",
  HEALTH: "HEALTH",
  LIFE: "LIFE",
} as const;
export type ClaimType = (typeof ClaimType)[keyof typeof ClaimType];

export const PolicyStatus = {
  ACTIVE: "ACTIVE",
  LAPSED: "LAPSED",
  EXPIRED: "EXPIRED",
  CANCELLED: "CANCELLED",
} as const;
export type PolicyStatus = (typeof PolicyStatus)[keyof typeof PolicyStatus];

export const ClaimStatus = {
  INTAKE: "INTAKE",
  DOCS_PENDING: "DOCS_PENDING",
  FRAUD_SCREENING: "FRAUD_SCREENING",
  ASSESSMENT: "ASSESSMENT",
  AUTO_APPROVED: "AUTO_APPROVED",
  MANUAL_REVIEW: "MANUAL_REVIEW",
  REJECTED: "REJECTED",
  SETTLED: "SETTLED",
  REOPENED: "REOPENED",
  PROCESSING_FAILED: "PROCESSING_FAILED",
} as const;
export type ClaimStatus = (typeof ClaimStatus)[keyof typeof ClaimStatus];

export const DocumentType = {
  POLICE_FIR: "POLICE_FIR",
  INVOICE: "INVOICE",
  HOSPITAL_BILL: "HOSPITAL_BILL",
  DISCHARGE_SUMMARY: "DISCHARGE_SUMMARY",
  DEATH_CERTIFICATE: "DEATH_CERTIFICATE",
} as const;
export type DocumentType = (typeof DocumentType)[keyof typeof DocumentType];

export const VerificationStatus = {
  VERIFIED: "VERIFIED",
  MISSING: "MISSING",
} as const;
export type VerificationStatus =
  (typeof VerificationStatus)[keyof typeof VerificationStatus];

export const DecisionOutcome = {
  AUTO_APPROVE: "AUTO_APPROVE",
  MANUAL_REVIEW: "MANUAL_REVIEW",
  REJECT: "REJECT",
} as const;
export type DecisionOutcome =
  (typeof DecisionOutcome)[keyof typeof DecisionOutcome];

export const ReasonCode = {
  POLICY_INACTIVE: "POLICY_INACTIVE",
  ZERO_PAYABLE_AMOUNT: "ZERO_PAYABLE_AMOUNT",
  FRAUD_FLAG: "FRAUD_FLAG",
  AUTO_APPROVED_LOW_RISK: "AUTO_APPROVED_LOW_RISK",
  HIGH_VALUE_REVIEW: "HIGH_VALUE_REVIEW",
  DOCS_INCOMPLETE: "DOCS_INCOMPLETE",
} as const;
export type ReasonCode = (typeof ReasonCode)[keyof typeof ReasonCode];

export const ApiErrorCode = {
  POLICY_INACTIVE: "POLICY_INACTIVE",
  DUPLICATE_CLAIM: "DUPLICATE_CLAIM",
  INVALID_STATE_TRANSITION: "INVALID_STATE_TRANSITION",
  VALIDATION_ERROR: "VALIDATION_ERROR",
  UNKNOWN_CLAIM_TYPE: "UNKNOWN_CLAIM_TYPE",
  UNAUTHORIZED: "UNAUTHORIZED",
  FORBIDDEN: "FORBIDDEN",
  NOT_FOUND: "NOT_FOUND",
  PROCESSING_FAILED: "PROCESSING_FAILED",
} as const;
export type ApiErrorCode = (typeof ApiErrorCode)[keyof typeof ApiErrorCode];

export const AdminOverrideCommand = {
  FORCE_APPROVE: "FORCE_APPROVE",
  FORCE_REJECT: "FORCE_REJECT",
  FORCE_MANUAL_REVIEW: "FORCE_MANUAL_REVIEW",
  FORCE_RETRY: "FORCE_RETRY",
} as const;
export type AdminOverrideCommand =
  (typeof AdminOverrideCommand)[keyof typeof AdminOverrideCommand];
