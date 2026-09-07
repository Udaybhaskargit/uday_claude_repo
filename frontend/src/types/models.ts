// Mirrors backend/src/types/models.py field-for-field. Money fields are typed
// `string` (not `number`) because the API serializes Decimal as a canonical
// decimal string -- never a JSON number -- per specs/design/api-contracts.md.

import type {
  AdminOverrideCommand,
  ClaimStatus,
  ClaimType,
  DecisionOutcome,
  DocumentType,
  PolicyStatus,
  ReasonCode,
  Role,
  VerificationStatus,
} from "./enums";

export interface Policy {
  id: number;
  policyNumber: string;
  productType: ClaimType;
  status: PolicyStatus;
  sumInsured: string;
  effectiveDate: string;
  expiryDate: string;
  createdAt: string;
}

export interface Claim {
  id: number;
  policyId: number;
  claimType: ClaimType;
  incidentDate: string;
  claimAmount: string;
  status: ClaimStatus;
  parentClaimId: number | null;
  createdAt: string;
  updatedAt: string;
}

export interface ClaimDocument {
  id: number;
  claimId: number;
  documentType: DocumentType;
  verificationStatus: VerificationStatus;
  createdAt: string;
  updatedAt: string;
}

export interface FraudScreeningRuleHit {
  rule: string;
  weight: number;
}

export interface FraudScreening {
  id: number;
  claimId: number;
  score: number;
  breakdown: FraudScreeningRuleHit[];
  threshold: number;
  flagged: boolean;
  createdAt: string;
}

export interface Assessment {
  id: number;
  claimId: number;
  claimAmount: string;
  sumInsured: string;
  deductible: string;
  coPay: string;
  payableAmount: string;
  createdAt: string;
}

export interface Decision {
  id: number;
  claimId: number;
  outcome: DecisionOutcome;
  reasonCode: ReasonCode;
  decidedBy: string;
  createdAt: string;
}

export interface Settlement {
  id: number;
  claimId: number;
  decisionId: number;
  payoutAmount: string;
  paymentReference: string;
  createdAt: string;
}

export interface AdminOverride {
  id: number;
  claimId: number;
  adminActorId: string;
  command: AdminOverrideCommand;
  reasonCode: string;
  createdAt: string;
}

export interface ActorContext {
  role: Role;
  actorId: string;
}
