"""Tests for backend/src/services/fraud_scoring_engine.py (E5-S2).

Uses the real shipped `backend/config/fraud-rules.json` (loaded via
`load_fraud_rules_config`) rather than a synthetic config, so these tests
exercise the actual production rule weights and threshold (40/25/30/15/10,
threshold 60).
"""

from decimal import Decimal
from pathlib import Path

import pytest
from src.config.fraud_rules_config import FraudRulesConfig, load_fraud_rules_config
from src.services.fraud_scoring_engine import (
    FraudRuleBreakdownEntry,
    FraudScoringInput,
    is_flagged,
    score,
    score_and_flag,
)
from src.types.enums import ClaimType

_REPO_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "fraud-rules.json"


@pytest.fixture()
def config() -> FraudRulesConfig:
    return load_fraud_rules_config(str(_REPO_CONFIG_PATH))


def _clean_health_input(**overrides: object) -> FraudScoringInput:
    """A HEALTH claim input with none of the 5 rules triggered.

    - ratio 40000/300000 ~= 0.133, well under 0.8
    - filed 30 days after inception, well over the 3-day window
    - no recent claims
    - not MOTOR, so the FIR rule never applies
    - 42500.00 is not a multiple of 10000
    """
    defaults: dict[str, object] = {
        "claim_amount": Decimal("42500.00"),
        "sum_insured": Decimal("300000.00"),
        "incident_date": "2026-06-15",
        "policy_effective_date": "2026-01-01",
        "claim_type": ClaimType.HEALTH,
        "recent_claim_count_90d": 0,
        "has_verified_police_fir": True,
    }
    defaults.update(overrides)
    return FraudScoringInput(**defaults)  # type: ignore[arg-type]


# --- F055: ratio 0.85 alone -> score 40, flagged False ---


def test_high_ratio_alone_scores_40_and_is_not_flagged(config: FraudRulesConfig) -> None:
    fraud_input = _clean_health_input(
        claim_amount=Decimal("85000.00"),
        sum_insured=Decimal("100000.00"),
    )

    total_score, breakdown = score(fraud_input, config)

    assert total_score == 40
    assert breakdown == [FraudRuleBreakdownEntry(rule_name="HIGH_CLAIM_TO_SUM_RATIO", weight=40)]
    assert is_flagged(total_score, config) is False


# --- F056: ratio 0.85 + filed 2 days after inception -> score 65, flagged True ---


def test_high_ratio_and_early_filing_scores_65_and_is_flagged(config: FraudRulesConfig) -> None:
    fraud_input = _clean_health_input(
        claim_amount=Decimal("85000.00"),
        sum_insured=Decimal("100000.00"),
        incident_date="2026-01-03",
        policy_effective_date="2026-01-01",
    )

    total_score, breakdown, flagged = score_and_flag(fraud_input, config)

    assert total_score == 65
    assert breakdown == [
        FraudRuleBreakdownEntry(rule_name="HIGH_CLAIM_TO_SUM_RATIO", weight=40),
        FraudRuleBreakdownEntry(rule_name="EARLY_FILING", weight=25),
    ]
    assert flagged is True


# --- F057: same inputs scored twice -> byte-identical results (determinism) ---


def test_scoring_the_same_input_twice_produces_identical_results(
    config: FraudRulesConfig,
) -> None:
    fraud_input = _clean_health_input(
        claim_amount=Decimal("85000.00"),
        sum_insured=Decimal("100000.00"),
        incident_date="2026-01-03",
        policy_effective_date="2026-01-01",
    )

    first_result = score(fraud_input, config)
    second_result = score(fraud_input, config)

    assert first_result == second_result
    assert first_result[1] is not second_result[1]  # distinct list objects, equal content


# --- F058: motor claim missing FIR -> breakdown includes MOTOR_MISSING_FIR / 15 ---


def test_motor_claim_missing_fir_includes_motor_missing_fir_in_breakdown(
    config: FraudRulesConfig,
) -> None:
    fraud_input = _clean_health_input(
        claim_type=ClaimType.MOTOR,
        has_verified_police_fir=False,
    )

    total_score, breakdown = score(fraud_input, config)

    assert FraudRuleBreakdownEntry(rule_name="MOTOR_MISSING_FIR", weight=15) in breakdown
    assert total_score >= 15


def test_motor_claim_with_verified_fir_does_not_trigger_motor_missing_fir(
    config: FraudRulesConfig,
) -> None:
    fraud_input = _clean_health_input(
        claim_type=ClaimType.MOTOR,
        has_verified_police_fir=True,
    )

    _, breakdown = score(fraud_input, config)

    assert all(entry.rule_name != "MOTOR_MISSING_FIR" for entry in breakdown)


def test_non_motor_claim_never_triggers_motor_missing_fir_even_without_fir(
    config: FraudRulesConfig,
) -> None:
    fraud_input = _clean_health_input(
        claim_type=ClaimType.HEALTH,
        has_verified_police_fir=False,
    )

    _, breakdown = score(fraud_input, config)

    assert all(entry.rule_name != "MOTOR_MISSING_FIR" for entry in breakdown)


# --- CLAIM_FREQUENCY: >2 recent claims triggers, exactly 2 does not ---


def test_claim_frequency_triggers_when_more_than_2_recent_claims(
    config: FraudRulesConfig,
) -> None:
    fraud_input = _clean_health_input(recent_claim_count_90d=3)

    total_score, breakdown = score(fraud_input, config)

    assert FraudRuleBreakdownEntry(rule_name="CLAIM_FREQUENCY", weight=30) in breakdown
    assert total_score == 30


def test_claim_frequency_does_not_trigger_at_exactly_2_recent_claims(
    config: FraudRulesConfig,
) -> None:
    fraud_input = _clean_health_input(recent_claim_count_90d=2)

    _, breakdown = score(fraud_input, config)

    assert all(entry.rule_name != "CLAIM_FREQUENCY" for entry in breakdown)


# --- ROUND_NUMBER_CLAIM: exact multiple of 10000 triggers, off-by-one does not ---


def test_round_number_claim_triggers_for_exact_multiple_of_10000(
    config: FraudRulesConfig,
) -> None:
    fraud_input = _clean_health_input(claim_amount=Decimal("50000.00"))

    total_score, breakdown = score(fraud_input, config)

    assert FraudRuleBreakdownEntry(rule_name="ROUND_NUMBER_CLAIM", weight=10) in breakdown
    assert total_score == 10


def test_round_number_claim_does_not_trigger_for_non_multiple_of_10000(
    config: FraudRulesConfig,
) -> None:
    fraud_input = _clean_health_input(claim_amount=Decimal("50001.00"))

    _, breakdown = score(fraud_input, config)

    assert all(entry.rule_name != "ROUND_NUMBER_CLAIM" for entry in breakdown)


# --- HIGH_CLAIM_TO_SUM_RATIO boundary: exactly 0.8 does not trigger (> not >=) ---


def test_high_ratio_does_not_trigger_at_exactly_0_8(config: FraudRulesConfig) -> None:
    fraud_input = _clean_health_input(
        claim_amount=Decimal("80000.00"),
        sum_insured=Decimal("100000.00"),
    )

    _, breakdown = score(fraud_input, config)

    assert all(entry.rule_name != "HIGH_CLAIM_TO_SUM_RATIO" for entry in breakdown)


# --- EARLY_FILING boundary: exactly 3 days triggers, 4 days does not ---


def test_early_filing_triggers_at_exactly_3_days(config: FraudRulesConfig) -> None:
    fraud_input = _clean_health_input(
        incident_date="2026-01-04",
        policy_effective_date="2026-01-01",
    )

    _, breakdown = score(fraud_input, config)

    assert FraudRuleBreakdownEntry(rule_name="EARLY_FILING", weight=25) in breakdown


def test_early_filing_does_not_trigger_at_4_days(config: FraudRulesConfig) -> None:
    fraud_input = _clean_health_input(
        incident_date="2026-01-05",
        policy_effective_date="2026-01-01",
    )

    _, breakdown = score(fraud_input, config)

    assert all(entry.rule_name != "EARLY_FILING" for entry in breakdown)


# --- No rules triggered at all -> score 0, empty breakdown, not flagged ---


def test_no_rules_triggered_scores_0_with_empty_breakdown(config: FraudRulesConfig) -> None:
    fraud_input = _clean_health_input()

    total_score, breakdown = score(fraud_input, config)

    assert total_score == 0
    assert breakdown == []
    assert is_flagged(total_score, config) is False


# --- is_flagged boundary: score == threshold flags (score >= threshold) ---


def test_is_flagged_true_when_score_equals_threshold(config: FraudRulesConfig) -> None:
    assert is_flagged(config.threshold, config) is True


def test_is_flagged_false_when_score_one_below_threshold(config: FraudRulesConfig) -> None:
    assert is_flagged(config.threshold - 1, config) is False
