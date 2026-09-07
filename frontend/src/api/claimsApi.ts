// Layer: API. Thin wrapper over the E9-S1 customer claims endpoints
// (specs/design/api-contracts.md "Customer Claims API"). Response shapes
// here are the literal wire format (snake_case) returned by
// `backend/src/api/schemas/claims_schemas.py` -- distinct from the
// camelCase domain models in ../types/models.ts.

import { apiRequest } from "./httpClient";
import type { ClaimStatus, ClaimType, DocumentType } from "../types/enums";
import type { ActorContext } from "../types/models";

export interface ChecklistItem {
  document_type: DocumentType;
  verification_status: string;
}

export interface SubmitFnolRequest {
  policy_number: string;
  claim_type: ClaimType;
  incident_date: string;
  claim_amount: string;
}

export interface SubmitFnolResponse {
  claim_id: number;
  status: ClaimStatus;
  checklist: ChecklistItem[];
}

export interface ClaimDecisionSummary {
  outcome: string;
  reason_code: string;
  decided_by: string;
  created_at: string;
}

export interface ClaimSettlementSummary {
  payout_amount: string;
  payment_reference: string;
  created_at: string;
}

export interface ClaimDetailResponse {
  claim_id: number;
  claim_type: ClaimType;
  status: ClaimStatus;
  incident_date: string;
  claim_amount: string;
  missing_documents: DocumentType[];
  decision: ClaimDecisionSummary | null;
  settlement: ClaimSettlementSummary | null;
  parent_claim_id: number | null;
}

export interface ReopenClaimResponse {
  sub_claim_id: number;
  parent_claim_id: number;
  status: ClaimStatus;
}

export function submitFnol(
  actor: ActorContext,
  request: SubmitFnolRequest,
): Promise<SubmitFnolResponse> {
  return apiRequest<SubmitFnolResponse>("/api/claims", {
    method: "POST",
    actor,
    body: request,
  });
}

export function fetchClaim(
  actor: ActorContext,
  claimId: number,
): Promise<ClaimDetailResponse> {
  return apiRequest<ClaimDetailResponse>(`/api/claims/${claimId}`, { actor });
}

export function reopenClaim(
  actor: ActorContext,
  claimId: number,
): Promise<ReopenClaimResponse> {
  return apiRequest<ReopenClaimResponse>(`/api/claims/${claimId}/reopen`, {
    method: "POST",
    actor,
    body: {},
  });
}
