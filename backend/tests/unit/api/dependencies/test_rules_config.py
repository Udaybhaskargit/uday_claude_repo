"""Unit tests for `src.api.dependencies.rules_config` (Group H addition).

Integration tests always override these two dependencies with a
deterministic in-memory config (mirroring how `test_db.py` overrides
`get_db_connection`), so this module exercises the real, shipped
`backend/config/*.json` load path directly -- the only place that happens.
"""

from __future__ import annotations

from src.api.dependencies.rules_config import (
    get_assessment_rules_config,
    get_fraud_rules_config,
)
from src.config.assessment_rules_config import AssessmentRulesConfig
from src.config.fraud_rules_config import FraudRulesConfig


def test_get_fraud_rules_config_loads_the_real_shipped_file() -> None:
    get_fraud_rules_config.cache_clear()
    try:
        config = get_fraud_rules_config()
        assert isinstance(config, FraudRulesConfig)
        assert len(config.rules) == 5
    finally:
        get_fraud_rules_config.cache_clear()


def test_get_fraud_rules_config_is_cached() -> None:
    get_fraud_rules_config.cache_clear()
    try:
        assert get_fraud_rules_config() is get_fraud_rules_config()
    finally:
        get_fraud_rules_config.cache_clear()


def test_get_assessment_rules_config_loads_the_real_shipped_file() -> None:
    get_assessment_rules_config.cache_clear()
    try:
        config = get_assessment_rules_config()
        assert isinstance(config, AssessmentRulesConfig)
        assert config.auto_approve_ceiling == 50000
    finally:
        get_assessment_rules_config.cache_clear()


def test_get_assessment_rules_config_is_cached() -> None:
    get_assessment_rules_config.cache_clear()
    try:
        assert get_assessment_rules_config() is get_assessment_rules_config()
    finally:
        get_assessment_rules_config.cache_clear()
