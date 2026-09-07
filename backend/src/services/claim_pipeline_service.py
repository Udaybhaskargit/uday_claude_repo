"""Claim pipeline orchestrator with failure handling (Service layer, E6-S3).

Wires the document-checklist gate (E5-S1), fraud screening (E5-S3), and
decision engine (E6-S2) into one `run_pipeline()` call that carries a claim
forward through as many of those steps as its *current* status allows, and
`retry_pipeline()`, which resumes a `PROCESSING_FAILED` claim from whichever
step failed.

Only the fraud-screening and decision steps are wrapped in failure handling
(AC3): those are the two steps `TRANSITION_TABLE` (E1-S2) gives a
`PIPELINE_ERROR` event from (`FRAUD_SCREENING` and `ASSESSMENT`). The
document-checklist gate is a plain repository read plus a well-defined
transition with no external/unexpected-failure surface, and AC2 describes it
as a normal halt (still `DOCS_PENDING`), not a failure.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass

from src.config.assessment_rules_config import AssessmentRulesConfig
from src.config.fraud_rules_config import FraudRulesConfig
from src.repositories.claim_repository import ClaimRepository
from src.services.decision_engine import run_decision
from src.services.document_checklist_service import check_documents_complete
from src.services.fraud_screening_service import run_fraud_screening
from src.types.enums import ClaimEvent, ClaimStatus
from src.types.exceptions import InvalidClaimStateException

logger = logging.getLogger(__name__)

_RETRY_EVENT_FOR_FAILED_STEP: dict[ClaimStatus, ClaimEvent] = {
    ClaimStatus.FRAUD_SCREENING: ClaimEvent.RETRY_TO_FRAUD_SCREENING,
    ClaimStatus.ASSESSMENT: ClaimEvent.RETRY_TO_ASSESSMENT,
}


@dataclass(frozen=True)
class PipelineResult:
    """The claim's status after a `run_pipeline()`/`retry_pipeline()` call."""

    claim_id: int
    status: ClaimStatus


def _log_pipeline_error(claim_id: int, step: str, exc: Exception) -> None:
    """Log a structured-JSON, PII-free error record (AC3, NFR-06).

    Only the claim id (an internal integer identifier, not PII), the failed
    step's name, and the exception's *class* name are logged -- never the
    exception message or claim data, since either could incidentally carry a
    claim narrative, health-data value, or other field NFR-06 forbids in
    logs.
    """
    logger.error(
        json.dumps(
            {
                "event": "pipeline_error",
                "claim_id": claim_id,
                "step": step,
                "error_type": type(exc).__name__,
            }
        )
    )


def run_pipeline(
    conn: sqlite3.Connection,
    claim_id: int,
    fraud_config: FraudRulesConfig,
    assessment_config: AssessmentRulesConfig,
    actor_id: str | None = None,
) -> PipelineResult:
    """Carry `claim_id` forward through as much of the pipeline as it can.

    Starting from the claim's own current status (so a claim already past
    `DOCS_PENDING` picks up wherever it is, rather than assuming it starts at
    the beginning):

    1. `DOCS_PENDING` -> `check_documents_complete()`. If any checklist item
       is still `MISSING`, this halts here and returns `DOCS_PENDING` (AC2)
       without ever calling the fraud or assessment steps.
    2. `FRAUD_SCREENING` -> `run_fraud_screening()`. An unexpected exception
       is caught, logged (see `_log_pipeline_error`), and the claim is
       transitioned to `PROCESSING_FAILED` via `PIPELINE_ERROR` (AC3).
    3. `ASSESSMENT` -> `run_decision()` (only reached if fraud screening
       cleared the claim into `ASSESSMENT` rather than flagging it straight
       to `MANUAL_REVIEW`). Failures are handled the same way as step 2.

    Ends in exactly one of `DOCS_PENDING`, `PROCESSING_FAILED`,
    `MANUAL_REVIEW`, `AUTO_APPROVED`, or `REJECTED` (AC1). For the AC1
    "complete documents, no fraud flag" scenario specifically, this always
    passes through `run_decision()`, so a matching `Decision` row exists;
    a fraud-flagged claim lands in `MANUAL_REVIEW` without ever entering
    `ASSESSMENT`; per E5-S3, that outcome is a separately-covered gating
    path, not this AC's scenario.

    Raises `LookupError` if no claim with `claim_id` exists.
    """
    claim_repository = ClaimRepository(conn)
    claim = claim_repository.get_by_id(claim_id)
    if claim is None:
        raise LookupError(f"Claim {claim_id} not found.")

    if claim.status == ClaimStatus.DOCS_PENDING:
        complete = check_documents_complete(conn, claim_id, actor_id)
        if not complete:
            return PipelineResult(claim_id, ClaimStatus.DOCS_PENDING)
        claim = claim_repository.get_by_id(claim_id)
        assert claim is not None

    if claim.status == ClaimStatus.FRAUD_SCREENING:
        try:
            run_fraud_screening(conn, claim_id, fraud_config, actor_id)
        except Exception as exc:  # noqa: BLE001 -- top-level pipeline boundary (AC3)
            _log_pipeline_error(claim_id, "fraud_screening", exc)
            claim_repository.apply_transition(claim_id, ClaimEvent.PIPELINE_ERROR, actor_id)
            return PipelineResult(claim_id, ClaimStatus.PROCESSING_FAILED)
        claim = claim_repository.get_by_id(claim_id)
        assert claim is not None

    if claim.status == ClaimStatus.ASSESSMENT:
        try:
            run_decision(conn, claim_id, assessment_config, actor_id or "system")
        except Exception as exc:  # noqa: BLE001 -- top-level pipeline boundary (AC3)
            _log_pipeline_error(claim_id, "decision", exc)
            claim_repository.apply_transition(claim_id, ClaimEvent.PIPELINE_ERROR, actor_id)
            return PipelineResult(claim_id, ClaimStatus.PROCESSING_FAILED)
        claim = claim_repository.get_by_id(claim_id)
        assert claim is not None

    return PipelineResult(claim_id, claim.status)


def retry_pipeline(
    conn: sqlite3.Connection,
    claim_id: int,
    fraud_config: FraudRulesConfig,
    assessment_config: AssessmentRulesConfig,
    actor_id: str | None = None,
) -> PipelineResult:
    """Resume a `PROCESSING_FAILED` claim from the step that failed (AC4).

    Reads the claim's last `claim_state_transitions` row (the `PIPELINE_
    ERROR` transition that put it into `PROCESSING_FAILED`) to recover which
    step it failed at, applies the matching `RETRY_TO_*` event to move it
    back to that step's state, and then delegates to `run_pipeline()` to
    carry it forward from there -- a fresh attempt at the failed step,
    followed by every step after it.

    Raises `LookupError` if `claim_id` doesn't exist. Raises
    `InvalidClaimStateException` if the claim is not currently
    `PROCESSING_FAILED`, or if its last transition's `from_state` is not one
    this function knows how to resume (only `FRAUD_SCREENING` and
    `ASSESSMENT` ever reach `PROCESSING_FAILED`, per `TRANSITION_TABLE`).
    """
    claim_repository = ClaimRepository(conn)
    claim = claim_repository.get_by_id(claim_id)
    if claim is None:
        raise LookupError(f"Claim {claim_id} not found.")

    last_transition = claim_repository.get_last_transition(claim_id)
    failed_step = last_transition.from_state if last_transition is not None else None
    retry_event = _RETRY_EVENT_FOR_FAILED_STEP.get(failed_step) if failed_step else None
    if retry_event is None:
        raise InvalidClaimStateException(
            f"Cannot determine a retry step for claim {claim_id}: "
            f"last recorded failed step was {failed_step!r}."
        )

    claim_repository.apply_transition(claim_id, retry_event, actor_id)

    return run_pipeline(conn, claim_id, fraud_config, assessment_config, actor_id)
