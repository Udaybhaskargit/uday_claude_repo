"""Pydantic request/response schemas for the assessor workbench API (E9-S3).

Shapes match `specs/design/api-contracts.md` sec "Assessor Workbench API".
"""

from __future__ import annotations

from pydantic import BaseModel


class FraudAlertClaim(BaseModel):
    claim_id: int
    claim_type: str
    fraud_score: int
    triggered_rules: list[str]


class FraudAlertsResponse(BaseModel):
    claims: list[FraudAlertClaim]


class WorkbenchFraudScreening(BaseModel):
    score: int
    threshold: int
    flagged: bool
    breakdown: list[dict[str, object]]


class WorkbenchAssessment(BaseModel):
    claim_amount: str
    sum_insured: str
    deductible: str
    co_pay: str
    payable_amount: str


class WorkbenchResponse(BaseModel):
    claim_id: int
    claim_type: str
    status: str
    fraud_screening: WorkbenchFraudScreening | None
    assessment: WorkbenchAssessment | None
    suggested_reason_code: str | None


class DecisionRequest(BaseModel):
    outcome: str
    reason_code: str


class DecisionBody(BaseModel):
    outcome: str
    reason_code: str
    decided_by: str
    created_at: str


class DecisionResponse(BaseModel):
    claim_id: int
    decision: DecisionBody
    claim_status: str
