"""Pydantic request/response schemas for the admin API (API layer, E9-S4).

Shapes match `specs/design/api-contracts.md` sec "Admin API" exactly. Money
fields are plain `str` (canonical decimal strings, e.g. `"35000.00"`), never
JSON numbers -- api-contracts.md's Conventions section forbids JSON floats
for money (NFR-01), and a `str` field can't silently round-trip through a
float parser the way a numeric field could.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AdminClaimSummary(BaseModel):
    claim_id: int
    claim_type: str
    status: str
    claim_amount: str
    updated_at: str


class AdminClaimsResponse(BaseModel):
    claims: list[AdminClaimSummary]


class PayoutSummary(BaseModel):
    settlement_id: int
    claim_id: int
    payout_amount: str
    payment_reference: str
    created_at: str


class PayoutsResponse(BaseModel):
    payouts: list[PayoutSummary]


class OverrideRequest(BaseModel):
    command: str
    reason_code: str = Field(min_length=1)


class OverrideResponse(BaseModel):
    claim_id: int
    override_id: int
    claim_status: str


class AdminOverrideSummary(BaseModel):
    override_id: int
    admin_actor_id: str
    command: str
    reason_code: str
    created_at: str


class AdminOverridesResponse(BaseModel):
    overrides: list[AdminOverrideSummary]
