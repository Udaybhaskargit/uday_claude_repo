"""Assessor workbench API router (E9-S3).

`GET /api/claims/fraud-alerts` and `GET /api/claims/{id}/workbench` require
`X-Role: ASSESSOR` or `X-Role: ADMIN`. `POST /api/claims/{id}/decision`
requires `X-Role: ASSESSOR` only, per `specs/design/api-contracts.md` sec
"Assessor Workbench API" (deliberately narrower than the other two routes --
not a typo). Thin HTTP adapter over `fraud_screening_repository`/
`assessment_repository` reads and `decision_engine.submit_assessor_decision()`.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from fastapi import APIRouter, Depends

from src.api.dependencies.auth import require_role
from src.api.dependencies.db import get_db_connection
from src.api.dependencies.rules_config import get_assessment_rules_config
from src.api.schemas.workbench_schemas import (
    DecisionBody,
    DecisionRequest,
    DecisionResponse,
    FraudAlertClaim,
    FraudAlertsResponse,
    WorkbenchAssessment,
    WorkbenchFraudScreening,
    WorkbenchResponse,
)
from src.config.assessment_rules_config import AssessmentRulesConfig
from src.repositories.assessment_repository import AssessmentRepository
from src.repositories.claim_repository import ClaimRepository
from src.repositories.fraud_screening_repository import FraudScreeningRepository
from src.services.decision_engine import decide, submit_assessor_decision
from src.types.enums import DecisionOutcome, ReasonCode, Role
from src.types.exceptions import ValidationError
from src.types.models import ActorContext

router = APIRouter(prefix="/api/claims", tags=["workbench"])


@router.get("/fraud-alerts")
async def list_fraud_alerts(
    conn: sqlite3.Connection = Depends(get_db_connection),  # noqa: B008
    _actor: ActorContext = Depends(require_role(Role.ASSESSOR, Role.ADMIN)),  # noqa: B008
) -> FraudAlertsResponse:
    """F100: claims whose latest `FraudScreening.flagged` is `True`.

    Every claim is checked against its own *latest* screening only (not any
    earlier one) -- a claim re-screened clean after an initial flag no
    longer appears here, matching `FraudScreeningRepository.get_latest()`'s
    already-established "most recent row wins" semantics (E3-S4).
    """
    claim_repository = ClaimRepository(conn)
    screening_repository = FraudScreeningRepository(conn)

    alerts: list[FraudAlertClaim] = []
    for claim in claim_repository.list_by_status_and_product():
        screening = screening_repository.get_latest(claim.id)
        if screening is None or not screening.flagged:
            continue
        alerts.append(
            FraudAlertClaim(
                claim_id=claim.id,
                claim_type=claim.claim_type.value,
                fraud_score=screening.score,
                triggered_rules=[str(entry["rule_name"]) for entry in screening.breakdown],
            )
        )
    return FraudAlertsResponse(claims=alerts)


@router.get("/{claim_id}/workbench")
async def get_workbench_detail(
    claim_id: int,
    conn: sqlite3.Connection = Depends(get_db_connection),  # noqa: B008
    assessment_config: AssessmentRulesConfig = Depends(get_assessment_rules_config),  # noqa: B008
    _actor: ActorContext = Depends(require_role(Role.ASSESSOR, Role.ADMIN)),  # noqa: B008
) -> WorkbenchResponse:
    """F101: fraud score/breakdown, assessed payable_amount, decision rationale.

    Does not reject claims outside `MANUAL_REVIEW` -- the route returns
    whatever fraud/assessment data exists for `claim_id` regardless of its
    current status, per api-contracts.md's own note that "the UI decides
    what to render". A fraud-flagged claim goes straight from
    `FRAUD_SCREENING` to `MANUAL_REVIEW` without ever entering `ASSESSMENT`
    (E5-S3), so it has no `Assessment` row; `assessment` (and, in turn,
    `suggested_reason_code`, which needs both pieces of data) is `None` in
    that case rather than raising.

    Raises `LookupError` (-> 404) if `claim_id` doesn't exist.
    """
    claim = ClaimRepository(conn).get_by_id(claim_id)
    if claim is None:
        raise LookupError(f"Claim {claim_id} not found.")

    screening = FraudScreeningRepository(conn).get_latest(claim_id)
    assessment = AssessmentRepository(conn).get_latest_assessment(claim_id)

    suggested_reason_code: str | None = None
    if screening is not None and assessment is not None:
        computation = decide(
            assessment.payable_amount,
            screening.flagged,
            Decimal(assessment_config.auto_approve_ceiling),
        )
        suggested_reason_code = computation.reason_code.value

    return WorkbenchResponse(
        claim_id=claim.id,
        claim_type=claim.claim_type.value,
        status=claim.status.value,
        fraud_screening=(
            WorkbenchFraudScreening(
                score=screening.score,
                threshold=screening.threshold,
                flagged=screening.flagged,
                breakdown=screening.breakdown,
            )
            if screening is not None
            else None
        ),
        assessment=(
            WorkbenchAssessment(
                claim_amount=str(assessment.claim_amount),
                sum_insured=str(assessment.sum_insured),
                deductible=str(assessment.deductible),
                co_pay=str(assessment.co_pay),
                payable_amount=str(assessment.payable_amount),
            )
            if assessment is not None
            else None
        ),
        suggested_reason_code=suggested_reason_code,
    )


@router.post("/{claim_id}/decision")
async def post_decision(
    claim_id: int,
    body: DecisionRequest,
    conn: sqlite3.Connection = Depends(get_db_connection),  # noqa: B008
    actor: ActorContext = Depends(require_role(Role.ASSESSOR)),  # noqa: B008
) -> DecisionResponse:
    """F102: persist the assessor's own outcome/reason_code, `decided_by=actor.actor_id`.

    `outcome`/`reason_code` are validated against the closed
    `DecisionOutcome`/`ReasonCode` enums here (422 `VALIDATION_ERROR` for an
    unrecognized value), then `submit_assessor_decision()` maps the outcome
    onto the matching `ASSESSOR_*` transition event -- raising
    `ValidationError` (422) for `MANUAL_REVIEW` (no assessor-usable event)
    or `InvalidClaimStateException` (409) if the claim is not currently
    `MANUAL_REVIEW`, and `LookupError` (-> 404) if `claim_id` doesn't exist.
    """
    try:
        outcome = DecisionOutcome(body.outcome)
    except ValueError as exc:
        raise ValidationError(f"Unknown outcome: {body.outcome!r}") from exc

    try:
        reason_code = ReasonCode(body.reason_code)
    except ValueError as exc:
        raise ValidationError(f"Unknown reason_code: {body.reason_code!r}") from exc

    decision = submit_assessor_decision(conn, claim_id, outcome, reason_code, actor.actor_id)

    updated_claim = ClaimRepository(conn).get_by_id(claim_id)
    assert updated_claim is not None
    return DecisionResponse(
        claim_id=claim_id,
        decision=DecisionBody(
            outcome=decision.outcome.value,
            reason_code=decision.reason_code.value,
            decided_by=decision.decided_by,
            created_at=decision.created_at,
        ),
        claim_status=updated_claim.status.value,
    )
