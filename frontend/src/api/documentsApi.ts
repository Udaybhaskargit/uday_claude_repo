// Layer: API. Thin wrapper over the E9-S2 document verification endpoints
// (specs/design/api-contracts.md "Document Verification API"). Response
// shapes here are the literal wire format (snake_case) returned by
// `backend/src/api/schemas/documents_schemas.py` -- distinct from the
// camelCase domain models in ../types/models.ts, which mirror the backend's
// internal Types layer rather than any one endpoint's JSON body.

import { apiRequest } from "./httpClient";
import type { ClaimType, DocumentType } from "../types/enums";
import type { ActorContext } from "../types/models";

export interface PendingDocsClaim {
  claim_id: number;
  claim_type: ClaimType;
  outstanding_documents: DocumentType[];
}

export interface PendingDocsResponse {
  claims: PendingDocsClaim[];
}

export interface DocumentPatchResponse {
  claim_id: number;
  document_type: DocumentType;
  verification_status: string;
  claim_status: string;
}

export function fetchPendingDocuments(
  actor: ActorContext,
  claimType?: ClaimType,
): Promise<PendingDocsResponse> {
  const query = claimType ? `?claim_type=${encodeURIComponent(claimType)}` : "";
  return apiRequest<PendingDocsResponse>(`/api/claims/documents/pending${query}`, {
    actor,
  });
}

export function verifyDocument(
  actor: ActorContext,
  claimId: number,
  documentType: DocumentType,
): Promise<DocumentPatchResponse> {
  return apiRequest<DocumentPatchResponse>(
    `/api/claims/${claimId}/documents/${documentType}`,
    {
      method: "PATCH",
      actor,
      body: { verification_status: "VERIFIED" },
    },
  );
}
