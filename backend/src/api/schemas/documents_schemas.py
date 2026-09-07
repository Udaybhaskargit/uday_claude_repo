"""Pydantic request/response schemas for the document verification API (E9-S2).

Shapes match `specs/design/api-contracts.md` sec "Document Verification API".
"""

from __future__ import annotations

from pydantic import BaseModel


class PendingDocsClaim(BaseModel):
    claim_id: int
    claim_type: str
    outstanding_documents: list[str]


class PendingDocsResponse(BaseModel):
    claims: list[PendingDocsClaim]


class DocumentPatchRequest(BaseModel):
    verification_status: str


class DocumentPatchResponse(BaseModel):
    claim_id: int
    document_type: str
    verification_status: str
    claim_status: str
