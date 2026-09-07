"""Admin API router: claim queue, payout audit trail, overrides (E9-S4).

Every route in this router requires `X-Role: ADMIN` (AC4) via
`require_role(Role.ADMIN)`; a non-admin role that otherwise passes the
E8-S1 auth boundary is rejected with 403 before any handler body runs, and a
missing/invalid role is rejected with 401 -- both are FastAPI dependency
failures, so neither ever reaches the code below (F106).

Endpoint shapes and error tables come from `specs/design/api-contracts.md`
sec "Admin API". `GET /api/admin/claims/{id}/overrides` and
`POST /api/admin/claims/{id}/retry` are documented there too, but only the
four endpoints E9-S4's own acceptance criteria (F103-F106) actually
exercise are implemented in this group:
  - `GET /api/admin/claims` (F103)
  - `GET /api/admin/payouts` (F104)
  - `POST /api/admin/claims/{id}/override` (F105, plus the `overrides`
    listing GET needed to observe its effect)
  - the blanket 403 check (F106)
`POST /api/admin/claims/{id}/retry` calls `retry_pipeline()`, which doesn't
exist until E6-S3 (Group H) -- adding a route with nothing behind it would
be dead code, so it is deliberately deferred to whichever group actually
builds `retry_pipeline()`.
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from src.api.dependencies.auth import require_role
from src.api.dependencies.db import get_db_connection
from src.api.schemas.admin_schemas import (
    AdminClaimsResponse,
    AdminClaimSummary,
    AdminOverridesResponse,
    AdminOverrideSummary,
    OverrideRequest,
    OverrideResponse,
    PayoutsResponse,
    PayoutSummary,
)
from src.repositories.admin_override_repository import AdminOverrideRepository
from src.repositories.claim_repository import ClaimRepository
from src.repositories.settlement_repository import SettlementRepository
from src.services.admin_override_service import override
from src.types.enums import AdminOverrideCommand, ClaimStatus, ClaimType, Role
from src.types.exceptions import ValidationError
from src.types.models import ActorContext

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/claims")
async def list_admin_claims(
    status: ClaimStatus | None = None,
    product: ClaimType | None = None,
    conn: sqlite3.Connection = Depends(get_db_connection),  # noqa: B008
    _actor: ActorContext = Depends(require_role(Role.ADMIN)),  # noqa: B008
) -> AdminClaimsResponse:
    """F103: claim queue filtered by optional `status`/`product` query params."""
    claims = ClaimRepository(conn).list_by_status_and_product(status, product)
    return AdminClaimsResponse(
        claims=[
            AdminClaimSummary(
                claim_id=claim.id,
                claim_type=claim.claim_type.value,
                status=claim.status.value,
                claim_amount=str(claim.claim_amount),
                updated_at=claim.updated_at or "",
            )
            for claim in claims
        ]
    )


@router.get("/payouts")
async def list_payouts(
    conn: sqlite3.Connection = Depends(get_db_connection),  # noqa: B008
    _actor: ActorContext = Depends(require_role(Role.ADMIN)),  # noqa: B008
) -> PayoutsResponse:
    """F104: every Settlement row, reverse-chronological, as an audit trail."""
    settlements = SettlementRepository(conn).list_all()
    ordered = list(reversed(settlements))
    return PayoutsResponse(
        payouts=[
            PayoutSummary(
                settlement_id=settlement.id,
                claim_id=settlement.claim_id,
                payout_amount=str(settlement.payout_amount),
                payment_reference=settlement.payment_reference,
                created_at=settlement.created_at,
            )
            for settlement in ordered
        ]
    )


@router.post("/claims/{claim_id}/override")
async def override_claim(
    claim_id: int,
    body: OverrideRequest,
    conn: sqlite3.Connection = Depends(get_db_connection),  # noqa: B008
    actor: ActorContext = Depends(require_role(Role.ADMIN)),  # noqa: B008
) -> OverrideResponse:
    """F105: force a claim decision/status, auditable via `AdminOverride`.

    `admin_override_service.override()` raises `ValidationError` (422) for
    a missing/blank `reason_code` and `InvalidClaimStateException` (409) for
    a command with no valid transition from the claim's current status --
    both propagate through `error_handlers.py` unchanged. A `claim_id` that
    doesn't exist surfaces as `LookupError` from `ClaimRepository.
    apply_transition()`, translated to 404 the same way.
    """
    try:
        command = AdminOverrideCommand(body.command)
    except ValueError as exc:
        raise ValidationError(f"Unknown override command: {body.command!r}") from exc

    result = override(conn, claim_id, actor.actor_id, command, body.reason_code)

    updated_claim = ClaimRepository(conn).get_by_id(claim_id)
    assert updated_claim is not None
    return OverrideResponse(
        claim_id=claim_id,
        override_id=result.id,
        claim_status=updated_claim.status.value,
    )


@router.get("/claims/{claim_id}/overrides")
async def list_claim_overrides(
    claim_id: int,
    conn: sqlite3.Connection = Depends(get_db_connection),  # noqa: B008
    _actor: ActorContext = Depends(require_role(Role.ADMIN)),  # noqa: B008
) -> AdminOverridesResponse:
    """Per-claim override audit history (F105's "subsequent GET" half; E9-S4 AC3).

    Raises `LookupError` (-> 404) if `claim_id` doesn't reference an
    existing claim, matching api-contracts.md's documented error table for
    this endpoint.
    """
    claim = ClaimRepository(conn).get_by_id(claim_id)
    if claim is None:
        raise LookupError(f"Claim {claim_id} not found.")

    overrides = AdminOverrideRepository(conn).list_admin_overrides(claim_id)
    return AdminOverridesResponse(
        overrides=[
            AdminOverrideSummary(
                override_id=row.id,
                admin_actor_id=row.admin_actor_id,
                command=row.command.value,
                reason_code=row.reason_code,
                created_at=row.created_at,
            )
            for row in overrides
        ]
    )
