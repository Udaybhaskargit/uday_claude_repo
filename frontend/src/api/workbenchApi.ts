// Layer: API. Thin wrapper over the E9-S3 assessor workbench endpoints
// (specs/design/api-contracts.md "Assessor Workbench API"). Response shapes
// here are the literal wire format (snake_case) returned by
// `backend/src/api/schemas/workbench_schemas.py` -- distinct from the
// camelCase domain models in ../types/models.ts.

import { apiRequest } from "./httpClient";
import type { ClaimStatus, ClaimType, DecisionOutcome, ReasonCode } from "../types/enums";
import type { ActorContext } from "../types/models";

export interface FraudBreakdownRule {
  rule_name: string;
  weight: number;
}

export interface WorkbenchFraudScreening {
  score: number;
  threshold: number;
  flagged: boolean;
  breakdown: FraudBreakdownRule[];
}

export interface WorkbenchAssessment {
  claim_amount: string;
  sum_insured: string;
  deductible: string;
  co_pay: string;
  payable_amount: string;
}

export interface WorkbenchDetailResponse {
  claim_id: number;
  claim_type: ClaimType;
  status: ClaimStatus;
  fraud_screening: WorkbenchFraudScreening | null;
  assessment: WorkbenchAssessment | null;
  suggested_reason_code: ReasonCode | null;
}

export interface SubmitDecisionRequest {
  outcome: DecisionOutcome;
  reason_code: ReasonCode;
}

export interface SubmitDecisionResponse {
  claim_id: number;
  decision: {
    outcome: DecisionOutcome;
    reason_code: ReasonCode;
    decided_by: string;
    created_at: string;
  };
  claim_status: ClaimStatus;
}

export function fetchWorkbenchDetail(
  actor: ActorContext,
  claimId: number,
): Promise<WorkbenchDetailResponse> {
  return apiRequest<WorkbenchDetailResponse>(`/api/claims/${claimId}/workbench`, {
    actor,
  });
}

export function submitDecision(
  actor: ActorContext,
  claimId: number,
  request: SubmitDecisionRequest,
): Promise<SubmitDecisionResponse> {
  return apiRequest<SubmitDecisionResponse>(`/api/claims/${claimId}/decision`, {
    method: "POST",
    actor,
    body: request,
  });
}
