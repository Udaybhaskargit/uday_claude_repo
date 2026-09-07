// Layer: API. Thin wrapper over the E9-S4 admin endpoints
// (specs/design/api-contracts.md "Admin API"). Response shapes here are the
// literal wire format (snake_case) returned by
// `backend/src/api/schemas/admin_schemas.py` -- distinct from the camelCase
// domain models in ../types/models.ts.

import { apiRequest } from "./httpClient";
import type { AdminOverrideCommand, ClaimStatus, ClaimType } from "../types/enums";
import type { ActorContext } from "../types/models";

export interface AdminClaimSummary {
  claim_id: number;
  claim_type: ClaimType;
  status: ClaimStatus;
  claim_amount: string;
  updated_at: string;
}

export interface AdminClaimsResponse {
  claims: AdminClaimSummary[];
}

export interface PayoutSummary {
  settlement_id: number;
  claim_id: number;
  payout_amount: string;
  payment_reference: string;
  created_at: string;
}

export interface PayoutsResponse {
  payouts: PayoutSummary[];
}

export interface OverrideResponse {
  claim_id: number;
  override_id: number;
  claim_status: string;
}

export interface AdminOverrideSummary {
  override_id: number;
  admin_actor_id: string;
  command: AdminOverrideCommand;
  reason_code: string;
  created_at: string;
}

export interface AdminOverridesResponse {
  overrides: AdminOverrideSummary[];
}

export function fetchAdminClaims(
  actor: ActorContext,
  status?: ClaimStatus,
  product?: ClaimType,
): Promise<AdminClaimsResponse> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (product) params.set("product", product);
  const query = params.toString();
  return apiRequest<AdminClaimsResponse>(
    `/api/admin/claims${query ? `?${query}` : ""}`,
    { actor },
  );
}

export function fetchPayouts(actor: ActorContext): Promise<PayoutsResponse> {
  return apiRequest<PayoutsResponse>("/api/admin/payouts", { actor });
}

export function submitOverride(
  actor: ActorContext,
  claimId: number,
  command: AdminOverrideCommand,
  reasonCode: string,
): Promise<OverrideResponse> {
  return apiRequest<OverrideResponse>(`/api/admin/claims/${claimId}/override`, {
    method: "POST",
    actor,
    body: { command, reason_code: reasonCode },
  });
}

export function fetchClaimOverrides(
  actor: ActorContext,
  claimId: number,
): Promise<AdminOverridesResponse> {
  return apiRequest<AdminOverridesResponse>(`/api/admin/claims/${claimId}/overrides`, {
    actor,
  });
}
