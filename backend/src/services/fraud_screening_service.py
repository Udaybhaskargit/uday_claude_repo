"""Fraud screening persistence and gating service (Service layer, E5-S3).

Gathers a `FraudScoringInput` for a claim already sitting in FRAUD_SCREENING,
runs it through the pure `fraud_scoring_engine.score_and_flag()` (E5-S2),
persists the result as an append-only `FraudScreening` row (data-models.md
sec 2.4), and gates the claim's transition into ASSESSMENT vs MANUAL_REVIEW
accordingly -- fulfilling the "future story" this engine's own docstring
forward-references for gathering `recent_claim_count_90d` and
`has_verified_police_fir` from the repositories.

Design note -- reason code is a Decision-layer concern, not this one: AC2
describes a flagged result as moving the claim "toward MANUAL_REVIEW with
reason code FRAUD_FLAG". `claim_state_transitions` (E1-S2/E3-S1) has no
`reason_code` column, and `FraudScreening` (data-models.md sec 2.4) doesn't
either -- only `Decision` rows (sec 2.6) carry a `ReasonCode`, and assigning
`ReasonCode.FRAUD_FLAG` to the eventual Decision row is E6-S2's job (Group
G), not this story's. So this service only applies the correct gating event
(`FRAUD_FLAGGED`/`FRAUD_CLEARED`); no new column is invented to store a
reason code that has nowhere typed to live yet at this layer.
"""

from __future__ import annotations

import sqlite3

from src.config.fraud_rules_config import FraudRulesConfig
from src.repositories.claim_document_repository import ClaimDocumentRepository
from src.repositories.claim_repository import ClaimRepository
from src.repositories.fraud_screening_repository import FraudScreeningRepository
from src.repositories.policy_repository import PolicyRepository
from src.services.fraud_scoring_engine import FraudScoringInput, score_and_flag
from src.types.enums import ClaimEvent, DocumentType, VerificationStatus
from src.types.models import Claim, FraudScreening

_CLAIM_FREQUENCY_WINDOW_DAYS = 90


def _gather_fraud_input(conn: sqlite3.Connection, claim: Claim) -> FraudScoringInput:
    """Assemble the self-contained `FraudScoringInput` bundle for `claim`.

    `policy` is looked up by the claim's numeric `policy_id` FK (not
    `policy_number`, which the FNOL-intake caller already resolved away),
    via the `PolicyRepository.get_by_id()` added alongside this service.
    The FK is `NOT NULL` and enforced by SQLite (`PRAGMA foreign_keys = ON`,
    `src.db.connection.get_connection`), so a matching policy row is
    guaranteed to exist.
    """
    policy = PolicyRepository(conn).get_by_id(claim.policy_id)
    assert policy is not None

    documents = ClaimDocumentRepository(conn).list_by_claim(claim.id)
    has_verified_police_fir = any(
        document.document_type == DocumentType.POLICE_FIR
        and document.verification_status == VerificationStatus.VERIFIED
        for document in documents
    )

    recent_claim_count_90d = ClaimRepository(conn).count_recent_claims(
        policy_id=claim.policy_id,
        before_date=claim.incident_date,
        window_days=_CLAIM_FREQUENCY_WINDOW_DAYS,
        exclude_claim_id=claim.id,
    )

    return FraudScoringInput(
        claim_amount=claim.claim_amount,
        sum_insured=policy.sum_insured,
        incident_date=claim.incident_date,
        policy_effective_date=policy.effective_date,
        claim_type=claim.claim_type,
        recent_claim_count_90d=recent_claim_count_90d,
        has_verified_police_fir=has_verified_police_fir,
    )


def run_fraud_screening(
    conn: sqlite3.Connection,
    claim_id: int,
    config: FraudRulesConfig,
    actor_id: str | None = None,
) -> FraudScreening:
    """Score `claim_id`, persist the result, and gate its next transition.

    1. Gathers a fresh `FraudScoringInput` from the claim's own current
       repository state (never cached across calls, so a retry naturally
       re-reads e.g. updated document-verification status).
    2. Scores it against `config` and persists an independent
       `FraudScreening` row via `FraudScreeningRepository.insert()`, storing
       `config.threshold` -- the threshold active for THIS call -- directly
       onto the row (AC1): a later call with a different `config` can never
       retroactively change an already-persisted row's threshold, since
       nothing here re-reads config after the fact.
    3. Applies `ClaimEvent.FRAUD_FLAGGED` (-> MANUAL_REVIEW, AC2) if
       `flagged`, else `ClaimEvent.FRAUD_CLEARED` (-> ASSESSMENT, AC3), via
       `ClaimRepository.apply_transition()` -- the sole gate for `Claim.
       status` changes. Both events are only valid from FRAUD_SCREENING, so
       calling this against a claim in any other state raises
       `InvalidClaimStateException` rather than silently mis-gating it.

    Each call inserts a brand-new `FraudScreening` row rather than reusing
    or overwriting a prior one (AC4) -- `FraudScreeningRepository.insert()`
    is append-only by construction (E3-S4).

    Raises `LookupError` if no claim with `claim_id` exists.
    """
    claim_repository = ClaimRepository(conn)
    claim = claim_repository.get_by_id(claim_id)
    if claim is None:
        raise LookupError(f"Claim {claim_id} not found.")

    fraud_input = _gather_fraud_input(conn, claim)
    total_score, breakdown, flagged = score_and_flag(fraud_input, config)
    breakdown_dicts: list[dict[str, object]] = [
        {"rule_name": entry.rule_name, "weight": entry.weight} for entry in breakdown
    ]

    screening_repository = FraudScreeningRepository(conn)
    screening_repository.insert(claim_id, total_score, breakdown_dicts, config.threshold, flagged)

    event = ClaimEvent.FRAUD_FLAGGED if flagged else ClaimEvent.FRAUD_CLEARED
    claim_repository.apply_transition(claim_id, event, actor_id)

    screening = screening_repository.get_latest(claim_id)
    assert screening is not None
    return screening
