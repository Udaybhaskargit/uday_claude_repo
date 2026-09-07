"""Fraud/assessment rule-config FastAPI dependencies (Group H, E9-S3).

Loads `backend/config/fraud-rules.json` and `backend/config/assessment-
rules.json` once per process via `lru_cache`, mirroring `auth.
get_app_config`'s caching pattern. Needed so the assessor workbench detail
endpoint can compute a live `suggested_reason_code` (decision-rationale)
from the claim's already-persisted fraud/assessment data without
hardcoding the auto-approve ceiling as a router-local constant.

Tests override these dependencies via `app.dependency_overrides[...]`
exactly as `test_documents_router.py` already overrides `get_app_config`/
`get_db_connection`, rather than depending on the real shipped config file.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.config.assessment_rules_config import (
    AssessmentRulesConfig,
    load_assessment_rules_config,
)
from src.config.fraud_rules_config import FraudRulesConfig, load_fraud_rules_config

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_FRAUD_RULES_PATH = _BACKEND_ROOT / "config" / "fraud-rules.json"
_ASSESSMENT_RULES_PATH = _BACKEND_ROOT / "config" / "assessment-rules.json"


@lru_cache
def get_fraud_rules_config() -> FraudRulesConfig:
    """FastAPI dependency: the process-wide cached, real fraud rules config."""
    return load_fraud_rules_config(str(_FRAUD_RULES_PATH))


@lru_cache
def get_assessment_rules_config() -> AssessmentRulesConfig:
    """FastAPI dependency: the process-wide cached, real assessment rules config."""
    return load_assessment_rules_config(str(_ASSESSMENT_RULES_PATH))
