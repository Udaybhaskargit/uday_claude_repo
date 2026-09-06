"""Tests for backend/src/config/fraud_rules_config.py (E2-S1)."""

import json
from pathlib import Path

import pytest
from src.config.fraud_rules_config import (
    CANONICAL_FRAUD_RULE_NAMES,
    FraudRule,
    FraudRulesConfig,
    load_fraud_rules_config,
)
from src.types.exceptions import ConfigError

_REPO_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "fraud-rules.json"
)


def _write_config(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "fraud-rules.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _valid_rules_payload() -> list[dict]:
    return [
        {"name": "HIGH_CLAIM_TO_SUM_RATIO", "weight": 40},
        {"name": "EARLY_FILING", "weight": 25},
        {"name": "CLAIM_FREQUENCY", "weight": 30},
        {"name": "MOTOR_MISSING_FIR", "weight": 15},
        {"name": "ROUND_NUMBER_CLAIM", "weight": 10},
    ]


# --- AC1 / AC2: the real shipped config file has exactly 5 rules matching
# BRD section 11 weights, and threshold 60. ---


def test_repo_fraud_rules_config_has_exactly_5_rules_matching_brd_weights() -> None:
    config = load_fraud_rules_config(str(_REPO_CONFIG_PATH))

    assert len(config.rules) == 5
    weights_by_name = {rule.name: rule.weight for rule in config.rules}
    assert weights_by_name == {
        "HIGH_CLAIM_TO_SUM_RATIO": 40,
        "EARLY_FILING": 25,
        "CLAIM_FREQUENCY": 30,
        "MOTOR_MISSING_FIR": 15,
        "ROUND_NUMBER_CLAIM": 10,
    }


def test_repo_fraud_rules_config_threshold_is_60() -> None:
    config = load_fraud_rules_config(str(_REPO_CONFIG_PATH))

    assert config.threshold == 60


def test_canonical_rule_names_match_data_model_closed_set() -> None:
    assert CANONICAL_FRAUD_RULE_NAMES == frozenset(
        {
            "HIGH_CLAIM_TO_SUM_RATIO",
            "EARLY_FILING",
            "CLAIM_FREQUENCY",
            "MOTOR_MISSING_FIR",
            "ROUND_NUMBER_CLAIM",
        }
    )


# --- Happy path against a controlled tmp fixture ---


def test_load_fraud_rules_config_happy_path(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path, {"rules": _valid_rules_payload(), "threshold": 60}
    )

    config = load_fraud_rules_config(str(path))

    assert isinstance(config, FraudRulesConfig)
    assert config.threshold == 60
    assert all(isinstance(rule, FraudRule) for rule in config.rules)
    assert config.rule_weight("HIGH_CLAIM_TO_SUM_RATIO") == 40


def test_rule_weight_raises_config_error_for_unknown_rule_name(
    tmp_path: Path,
) -> None:
    path = _write_config(
        tmp_path, {"rules": _valid_rules_payload(), "threshold": 60}
    )
    config = load_fraud_rules_config(str(path))

    with pytest.raises(ConfigError):
        config.rule_weight("NOT_A_REAL_RULE")


# --- AC3: missing file / malformed JSON / structural failures raise ConfigError ---


def test_load_fraud_rules_config_missing_file_raises_config_error(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "does-not-exist.json"

    with pytest.raises(ConfigError):
        load_fraud_rules_config(str(missing_path))


def test_load_fraud_rules_config_malformed_json_raises_config_error(
    tmp_path: Path,
) -> None:
    path = tmp_path / "fraud-rules.json"
    path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_fraud_rules_config(str(path))


def test_load_fraud_rules_config_wrong_rule_count_raises_config_error(
    tmp_path: Path,
) -> None:
    payload = _valid_rules_payload()[:4]
    path = _write_config(tmp_path, {"rules": payload, "threshold": 60})

    with pytest.raises(ConfigError):
        load_fraud_rules_config(str(path))


def test_load_fraud_rules_config_wrong_rule_names_raises_config_error(
    tmp_path: Path,
) -> None:
    payload = _valid_rules_payload()
    payload[0]["name"] = "NOT_A_CANONICAL_RULE"
    path = _write_config(tmp_path, {"rules": payload, "threshold": 60})

    with pytest.raises(ConfigError):
        load_fraud_rules_config(str(path))


def test_load_fraud_rules_config_duplicate_rule_name_raises_config_error(
    tmp_path: Path,
) -> None:
    payload = _valid_rules_payload()[:4]
    payload.append({"name": payload[0]["name"], "weight": 99})
    path = _write_config(tmp_path, {"rules": payload, "threshold": 60})

    with pytest.raises(ConfigError):
        load_fraud_rules_config(str(path))


def test_load_fraud_rules_config_missing_threshold_raises_config_error(
    tmp_path: Path,
) -> None:
    path = _write_config(tmp_path, {"rules": _valid_rules_payload()})

    with pytest.raises(ConfigError):
        load_fraud_rules_config(str(path))


def test_load_fraud_rules_config_non_integer_threshold_raises_config_error(
    tmp_path: Path,
) -> None:
    path = _write_config(
        tmp_path, {"rules": _valid_rules_payload(), "threshold": "sixty"}
    )

    with pytest.raises(ConfigError):
        load_fraud_rules_config(str(path))


def test_load_fraud_rules_config_non_integer_weight_raises_config_error(
    tmp_path: Path,
) -> None:
    payload = _valid_rules_payload()
    payload[0]["weight"] = "forty"
    path = _write_config(tmp_path, {"rules": payload, "threshold": 60})

    with pytest.raises(ConfigError):
        load_fraud_rules_config(str(path))


def test_load_fraud_rules_config_top_level_not_an_object_raises_config_error(
    tmp_path: Path,
) -> None:
    path = tmp_path / "fraud-rules.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(ConfigError):
        load_fraud_rules_config(str(path))


def test_load_fraud_rules_config_rule_entry_not_an_object_raises_config_error(
    tmp_path: Path,
) -> None:
    payload = _valid_rules_payload()
    payload[0] = "not-an-object"
    path = _write_config(tmp_path, {"rules": payload, "threshold": 60})

    with pytest.raises(ConfigError):
        load_fraud_rules_config(str(path))


# --- AC4: reload after on-disk edit picks up the new value, no caching ---


def test_load_fraud_rules_config_reflects_on_disk_edit_on_next_load(
    tmp_path: Path,
) -> None:
    path = _write_config(
        tmp_path, {"rules": _valid_rules_payload(), "threshold": 60}
    )

    first_load = load_fraud_rules_config(str(path))
    assert first_load.threshold == 60

    _write_config(tmp_path, {"rules": _valid_rules_payload(), "threshold": 75})

    second_load = load_fraud_rules_config(str(path))
    assert second_load.threshold == 75
    assert first_load.threshold == 60
