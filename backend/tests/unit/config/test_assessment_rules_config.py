"""Tests for backend/src/config/assessment_rules_config.py (E2-S2)."""

import json
from pathlib import Path

import pytest
from src.config.assessment_rules_config import (
    AssessmentRulesConfig,
    ClaimTypeRules,
    load_assessment_rules_config,
)
from src.types.enums import ClaimType
from src.types.exceptions import ConfigError, UnknownClaimTypeError

_REPO_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "assessment-rules.json"
)


def _write_config(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "assessment-rules.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _valid_payload() -> dict:
    return {
        "claim_types": {
            "motor": {"deductible": 5000, "co_pay_pct": 0},
            "health": {"deductible": 1000, "co_pay_pct": 10},
            "life": {"deductible": 0, "co_pay_pct": 0},
        },
        "auto_approve_ceiling": 50000,
    }


# --- AC1 / AC2: the real shipped config file has the exact BRD values ---


def test_repo_assessment_rules_config_has_exact_per_claim_type_values() -> None:
    config = load_assessment_rules_config(str(_REPO_CONFIG_PATH))

    motor = config.for_claim_type(ClaimType.MOTOR)
    health = config.for_claim_type(ClaimType.HEALTH)
    life = config.for_claim_type(ClaimType.LIFE)

    assert (motor.deductible, motor.co_pay_pct) == (5000, 0)
    assert (health.deductible, health.co_pay_pct) == (1000, 10)
    assert (life.deductible, life.co_pay_pct) == (0, 0)


def test_repo_assessment_rules_config_auto_approve_ceiling_is_50000() -> None:
    config = load_assessment_rules_config(str(_REPO_CONFIG_PATH))

    assert config.auto_approve_ceiling == 50000


# --- Happy path against a controlled tmp fixture ---


def test_load_assessment_rules_config_happy_path(tmp_path: Path) -> None:
    path = _write_config(tmp_path, _valid_payload())

    config = load_assessment_rules_config(str(path))

    assert isinstance(config, AssessmentRulesConfig)
    motor_rules = config.for_claim_type(ClaimType.MOTOR)
    assert isinstance(motor_rules, ClaimTypeRules)
    assert motor_rules.deductible == 5000
    assert motor_rules.co_pay_pct == 0


# --- AC3: unknown claim_type lookup raises UnknownClaimTypeError ---


def test_for_claim_type_raises_unknown_claim_type_error_for_unrecognized_key(
    tmp_path: Path,
) -> None:
    path = _write_config(tmp_path, _valid_payload())
    config = load_assessment_rules_config(str(path))

    with pytest.raises(UnknownClaimTypeError):
        config.for_claim_type("BOAT")  # type: ignore[arg-type]


def test_for_claim_type_raises_unknown_claim_type_error_when_map_incomplete() -> None:
    """Defensive branch: a valid ClaimType missing from the loaded map (which
    can only happen via direct construction, never via load_assessment_rules_
    config, since the loader always populates all 3 claim types) still raises
    the typed UnknownClaimTypeError rather than a bare KeyError."""
    config = AssessmentRulesConfig(
        rules_by_claim_type={ClaimType.MOTOR: ClaimTypeRules(deductible=0, co_pay_pct=0)},
        auto_approve_ceiling=50000,
    )

    with pytest.raises(UnknownClaimTypeError):
        config.for_claim_type(ClaimType.LIFE)


# --- Missing file / malformed JSON / structural failures raise ConfigError ---


def test_load_assessment_rules_config_missing_file_raises_config_error(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "does-not-exist.json"

    with pytest.raises(ConfigError):
        load_assessment_rules_config(str(missing_path))


def test_load_assessment_rules_config_malformed_json_raises_config_error(
    tmp_path: Path,
) -> None:
    path = tmp_path / "assessment-rules.json"
    path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_assessment_rules_config(str(path))


def test_load_assessment_rules_config_missing_claim_type_raises_config_error(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    del payload["claim_types"]["life"]
    path = _write_config(tmp_path, payload)

    with pytest.raises(ConfigError):
        load_assessment_rules_config(str(path))


def test_load_assessment_rules_config_extra_claim_type_raises_config_error(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["claim_types"]["boat"] = {"deductible": 100, "co_pay_pct": 0}
    path = _write_config(tmp_path, payload)

    with pytest.raises(ConfigError):
        load_assessment_rules_config(str(path))


def test_load_assessment_rules_config_non_integer_deductible_raises_config_error(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["claim_types"]["motor"]["deductible"] = "5000"
    path = _write_config(tmp_path, payload)

    with pytest.raises(ConfigError):
        load_assessment_rules_config(str(path))


def test_load_assessment_rules_config_non_integer_co_pay_pct_raises_config_error(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["claim_types"]["health"]["co_pay_pct"] = "ten"
    path = _write_config(tmp_path, payload)

    with pytest.raises(ConfigError):
        load_assessment_rules_config(str(path))


def test_load_assessment_rules_config_missing_auto_approve_ceiling_raises_config_error(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    del payload["auto_approve_ceiling"]
    path = _write_config(tmp_path, payload)

    with pytest.raises(ConfigError):
        load_assessment_rules_config(str(path))


def test_load_assessment_rules_config_top_level_not_an_object_raises_config_error(
    tmp_path: Path,
) -> None:
    path = tmp_path / "assessment-rules.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(ConfigError):
        load_assessment_rules_config(str(path))


def test_load_assessment_rules_config_claim_types_not_an_object_raises_config_error(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["claim_types"] = "not-an-object"
    path = _write_config(tmp_path, payload)

    with pytest.raises(ConfigError):
        load_assessment_rules_config(str(path))


def test_load_assessment_rules_config_claim_type_entry_not_an_object_raises_config_error(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["claim_types"]["motor"] = "not-an-object"
    path = _write_config(tmp_path, payload)

    with pytest.raises(ConfigError):
        load_assessment_rules_config(str(path))


# --- Reload after on-disk edit picks up the new value, no caching ---


def test_load_assessment_rules_config_reflects_on_disk_edit_on_next_load(
    tmp_path: Path,
) -> None:
    path = _write_config(tmp_path, _valid_payload())

    first_load = load_assessment_rules_config(str(path))
    assert first_load.auto_approve_ceiling == 50000

    edited_payload = _valid_payload()
    edited_payload["auto_approve_ceiling"] = 75000
    _write_config(tmp_path, edited_payload)

    second_load = load_assessment_rules_config(str(path))
    assert second_load.auto_approve_ceiling == 75000
    assert first_load.auto_approve_ceiling == 50000
