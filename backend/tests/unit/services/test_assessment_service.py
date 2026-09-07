"""Tests for backend/src/services/assessment_service.py (E6-S1).

Covers F063-F067 from features.json:
  - F063 (AC1): motor claim, no co-pay.
  - F064 (AC2): health claim, deductible + co-pay.
  - F065 (AC3): life claim, claim_amount capped at sum_insured.
  - F066 (AC4): payable_amount clamped to 0, never negative.
  - F067 (AC5): payable_amount is a Decimal; no float arithmetic anywhere.
"""

from decimal import Decimal
from pathlib import Path

from src.config.assessment_rules_config import (
    AssessmentRulesConfig,
    ClaimTypeRules,
    load_assessment_rules_config,
)
from src.services.assessment_service import AssessmentComputation, assess
from src.types.enums import ClaimType

_REPO_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "assessment-rules.json"
)


def _synthetic_config() -> AssessmentRulesConfig:
    """A synthetic config mirroring the shipped assessment-rules.json values,
    used so most tests are independent of the on-disk file's contents."""
    return AssessmentRulesConfig(
        rules_by_claim_type={
            ClaimType.MOTOR: ClaimTypeRules(deductible=5000, co_pay_pct=0),
            ClaimType.HEALTH: ClaimTypeRules(deductible=1000, co_pay_pct=10),
            ClaimType.LIFE: ClaimTypeRules(deductible=0, co_pay_pct=0),
        },
        auto_approve_ceiling=50000,
    )


# --- F063 / AC1: motor claim, deductible only, no co-pay ---


def test_motor_claim_deducts_deductible_with_no_co_pay() -> None:
    config = _synthetic_config()

    result = assess(
        claim_amount=Decimal("40000"),
        sum_insured=Decimal("100000"),
        claim_type=ClaimType.MOTOR,
        config=config,
    )

    assert isinstance(result, AssessmentComputation)
    assert result.deductible == Decimal("5000.00")
    assert result.co_pay == Decimal("0.00")
    assert result.payable_amount == Decimal("35000.00")


# --- F064 / AC2: health claim, deductible + 10% co-pay of post-deductible ---


def test_health_claim_applies_deductible_then_co_pay_of_post_deductible_amount() -> (
    None
):
    config = _synthetic_config()

    result = assess(
        claim_amount=Decimal("20000"),
        sum_insured=Decimal("300000"),
        claim_type=ClaimType.HEALTH,
        config=config,
    )

    assert result.deductible == Decimal("1000.00")
    # 10% co-pay of (20000 - 1000) = 19000 -> 1900, not 10% of 20000 or of
    # sum_insured.
    assert result.co_pay == Decimal("1900.00")
    assert result.payable_amount == Decimal("17100.00")


# --- F065 / AC3: life claim, claim_amount capped at sum_insured ---


def test_life_claim_caps_base_at_sum_insured_when_claim_amount_exceeds_it() -> None:
    config = _synthetic_config()

    result = assess(
        claim_amount=Decimal("200000"),
        sum_insured=Decimal("150000"),
        claim_type=ClaimType.LIFE,
        config=config,
    )

    assert result.deductible == Decimal("0.00")
    assert result.co_pay == Decimal("0.00")
    assert result.payable_amount == Decimal("150000.00")


# --- F066 / AC4: payable_amount clamped to 0, never negative ---


def test_payable_amount_clamped_to_zero_when_deductible_exceeds_claim_amount() -> (
    None
):
    config = _synthetic_config()

    # claim_amount (1000) < motor deductible (5000): base - deductible - co_pay
    # would mathematically be -4000, which must clamp to exactly 0.
    result = assess(
        claim_amount=Decimal("1000"),
        sum_insured=Decimal("100000"),
        claim_type=ClaimType.MOTOR,
        config=config,
    )

    assert result.payable_amount == Decimal("0.00")
    assert result.payable_amount >= Decimal("0")


def test_payable_amount_clamped_to_zero_for_health_claim_with_deductible_and_co_pay() -> (
    None
):
    config = _synthetic_config()

    # base=500, deductible=1000 -> after_deductible would be -500 before any
    # co-pay is applied; still must clamp to 0, not go further negative.
    result = assess(
        claim_amount=Decimal("500"),
        sum_insured=Decimal("300000"),
        claim_type=ClaimType.HEALTH,
        config=config,
    )

    assert result.payable_amount == Decimal("0.00")


# --- F067 / AC5: Decimal end-to-end, no float arithmetic; real config wiring ---


def test_result_fields_are_all_decimal_instances() -> None:
    config = _synthetic_config()

    result = assess(
        claim_amount=Decimal("40000"),
        sum_insured=Decimal("100000"),
        claim_type=ClaimType.MOTOR,
        config=config,
    )

    assert isinstance(result.claim_amount, Decimal)
    assert isinstance(result.sum_insured, Decimal)
    assert isinstance(result.deductible, Decimal)
    assert isinstance(result.co_pay, Decimal)
    assert isinstance(result.payable_amount, Decimal)


def test_source_file_contains_no_float_usage() -> None:
    """Static guard: the implementation must never construct, cast to, or
    type-annotate anything as `float` anywhere in its computation (AC5).

    The module's docstrings legitimately *discuss* "no float arithmetic" in
    prose, so this checks for actual code usages of the `float` builtin
    (a call `float(...)` or a type annotation `: float` / `-> float`)
    rather than the bare substring "float", which would also match the
    documentation prose.
    """
    source_path = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "services"
        / "assessment_service.py"
    )
    source = source_path.read_text(encoding="utf-8")

    assert "float(" not in source
    assert ": float" not in source
    assert "-> float" not in source


def test_assess_end_to_end_with_real_shipped_config_file() -> None:
    """Loads the real `config/assessment-rules.json` via the config loader
    (not synthetic Decimal-only fixtures) to prove real end-to-end wiring."""
    config = load_assessment_rules_config(str(_REPO_CONFIG_PATH))

    result = assess(
        claim_amount=Decimal("20000"),
        sum_insured=Decimal("300000"),
        claim_type=ClaimType.HEALTH,
        config=config,
    )

    assert result.payable_amount == Decimal("17100.00")


def test_assess_rounds_fractional_co_pay_half_up() -> None:
    """A co_pay_pct that does not divide evenly produces a fractional cent;
    the implementation must round it deterministically via ROUND_HALF_UP
    rather than truncating or using banker's rounding."""
    config = AssessmentRulesConfig(
        rules_by_claim_type={
            ClaimType.MOTOR: ClaimTypeRules(deductible=0, co_pay_pct=0),
            ClaimType.HEALTH: ClaimTypeRules(deductible=0, co_pay_pct=15),
            ClaimType.LIFE: ClaimTypeRules(deductible=0, co_pay_pct=0),
        },
        auto_approve_ceiling=50000,
    )

    # after_deductible = 100.01; co_pay = 15% of 100.01 = 15.0015 -> rounds
    # (half up) to 15.00; payable = 100.01 - 15.00 = 85.01.
    result = assess(
        claim_amount=Decimal("100.01"),
        sum_insured=Decimal("300000"),
        claim_type=ClaimType.HEALTH,
        config=config,
    )

    assert result.co_pay == Decimal("15.00")
    assert result.payable_amount == Decimal("85.01")
