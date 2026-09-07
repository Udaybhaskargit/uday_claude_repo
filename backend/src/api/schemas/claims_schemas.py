"""Pydantic request/response schemas for the customer claims API (E9-S1).

Shapes match `specs/design/api-contracts.md` sec "Claims API (E9-S1)"
exactly. Money fields are plain `str` (canonical decimal strings), never
JSON numbers, per the Conventions section (NFR-01) -- same convention already
used by `admin_schemas.py` and `workbench_schemas.py`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SubmitFnolRequest(BaseModel):
    policy_number: str = Field(min_length=1)
    claim_type: str
    incident_date: str
    claim_amount: str = Field(min_length=1)


class ChecklistEntry(BaseModel):
    document_type: str
    verification_status: str


class SubmitFnolResponse(BaseModel):
    claim_id: int
    status: str
    checklist: list[ChecklistEntry]


class ClaimDecisionBody(BaseModel):
    outcome: str
    reason_code: str
    decided_by: str
    created_at: str


class ClaimSettlementBody(BaseModel):
    settlement_id: int
    payout_amount: str
    payment_reference: str
    created_at: str


class ClaimDetailResponse(BaseModel):
    claim_id: int
    claim_type: str
    status: str
    incident_date: str
    claim_amount: str
    missing_documents: list[str]
    decision: ClaimDecisionBody | None
    settlement: ClaimSettlementBody | None
    parent_claim_id: int | None


class ReopenResponse(BaseModel):
    sub_claim_id: int
    parent_claim_id: int
    status: str
