"""Loader for the declarative assessment/deductible rule config (E2-S2).

Per `.claude/architecture.md`, Config is Layer 2 and may import only from
Types (here: `src.types.enums.ClaimType`, `src.types.exceptions`). Like
`fraud_rules_config`, this loader holds no module-level cache -- every call
re-reads and re-validates `config/assessment-rules.json` from disk.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.types.enums import ClaimType
from src.types.exceptions import ConfigError, UnknownClaimTypeError

_CLAIM_TYPE_KEY_TO_ENUM: dict[str, ClaimType] = {
    "motor": ClaimType.MOTOR,
    "health": ClaimType.HEALTH,
    "life": ClaimType.LIFE,
}


@dataclass(frozen=True)
class ClaimTypeRules:
    """Deductible and co-pay percentage for one claim type."""

    deductible: int
    co_pay_pct: int


@dataclass(frozen=True)
class AssessmentRulesConfig:
    """The fully loaded and validated assessment-rules.json contents."""

    rules_by_claim_type: dict[ClaimType, ClaimTypeRules]
    auto_approve_ceiling: int

    def for_claim_type(self, claim_type: ClaimType) -> ClaimTypeRules:
        """Return the deductible/co-pay rules for `claim_type`.

        `claim_type` is typed as `ClaimType` for the normal, valid-input call
        path, but this method defensively re-coerces its argument through
        `ClaimType(...)` before the map lookup so that a caller passing a raw
        value outside {MOTOR, HEALTH, LIFE} (e.g. a string obtained from an
        untrusted request path rather than the closed enum) gets the typed
        `UnknownClaimTypeError` from E2-S2 AC3 instead of a bare `KeyError`
        or `ValueError`.
        """
        try:
            resolved = ClaimType(claim_type)
        except ValueError as exc:
            raise UnknownClaimTypeError(str(claim_type)) from exc

        try:
            return self.rules_by_claim_type[resolved]
        except KeyError as exc:
            raise UnknownClaimTypeError(str(claim_type)) from exc


def load_assessment_rules_config(path: str) -> AssessmentRulesConfig:
    """Load and validate `path` as an assessment-rules.json file.

    Raises `ConfigError` if the file is missing, unreadable, not valid JSON,
    or fails structural validation (wrong/missing claim types, non-integer
    deductible/co_pay_pct/auto_approve_ceiling).
    """
    file_path = Path(path)
    try:
        raw_text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            f"Assessment rules config file not found or unreadable: {path}"
        ) from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Assessment rules config file is not valid JSON: {path}"
        ) from exc

    if not isinstance(data, dict):
        raise ConfigError("Assessment rules config must be a JSON object.")

    claim_types_raw = data.get("claim_types")
    if not isinstance(claim_types_raw, dict):
        raise ConfigError(
            "Assessment rules config must contain a 'claim_types' object."
        )

    expected_keys = set(_CLAIM_TYPE_KEY_TO_ENUM)
    actual_keys = set(claim_types_raw)
    if actual_keys != expected_keys:
        raise ConfigError(
            "Assessment rules config 'claim_types' must define exactly "
            f"{sorted(expected_keys)}, got {sorted(actual_keys)}."
        )

    rules_by_claim_type: dict[ClaimType, ClaimTypeRules] = {}
    for key, claim_type in _CLAIM_TYPE_KEY_TO_ENUM.items():
        entry = claim_types_raw[key]
        if not isinstance(entry, dict):
            raise ConfigError(
                f"Assessment rules entry for {key!r} must be a JSON object."
            )

        deductible = entry.get("deductible")
        if not isinstance(deductible, int) or isinstance(deductible, bool):
            raise ConfigError(f"{key!r} deductible must be an integer.")

        co_pay_pct = entry.get("co_pay_pct")
        if not isinstance(co_pay_pct, int) or isinstance(co_pay_pct, bool):
            raise ConfigError(f"{key!r} co_pay_pct must be an integer.")

        rules_by_claim_type[claim_type] = ClaimTypeRules(
            deductible=deductible, co_pay_pct=co_pay_pct
        )

    auto_approve_ceiling = data.get("auto_approve_ceiling")
    if not isinstance(auto_approve_ceiling, int) or isinstance(
        auto_approve_ceiling, bool
    ):
        raise ConfigError("'auto_approve_ceiling' must be an integer.")

    return AssessmentRulesConfig(
        rules_by_claim_type=rules_by_claim_type,
        auto_approve_ceiling=auto_approve_ceiling,
    )
