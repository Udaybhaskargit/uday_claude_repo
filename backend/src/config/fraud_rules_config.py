"""Loader for the declarative fraud-scoring rule config (E2-S1).

Per `.claude/architecture.md`, Config is Layer 2 and may import only from
Types. This module intentionally holds no module-level cache: every call to
`load_fraud_rules_config` re-reads and re-validates the file from disk, so
editing `config/fraud-rules.json` on disk with no code change is reflected on
the very next call (E2-S1 AC4). Callers that want a "load once at startup"
semantic are responsible for calling this once and holding onto the result
themselves.

The 5 canonical rule names below are the closed set defined in
`specs/design/data-models.md` section 3.2 (`FraudRuleBreakdownEntry.rule_name`).
Only the rule *names* and the JSON structure/types are treated as loader-level
invariants (E2-S1 AC3): a config file with the wrong rule count, an unknown
rule name, or a non-integer weight/threshold fails to load. The specific point
*values* (e.g. threshold == 60) are a property of the shipped
`config/fraud-rules.json` file, verified by tests against that file directly,
not hardcoded into the loader -- hardcoding a single allowed threshold value
would make the threshold uneditable, defeating the entire point of E2-S1
(externalizing this as configuration so ops can retune it without a code
change, per E2-S1 AC4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.types.exceptions import ConfigError

CANONICAL_FRAUD_RULE_NAMES: frozenset[str] = frozenset(
    {
        "HIGH_CLAIM_TO_SUM_RATIO",
        "EARLY_FILING",
        "CLAIM_FREQUENCY",
        "MOTOR_MISSING_FIR",
        "ROUND_NUMBER_CLAIM",
    }
)

_EXPECTED_RULE_COUNT = 5


@dataclass(frozen=True)
class FraudRule:
    """A single named, weighted fraud rule."""

    name: str
    weight: int
    description: str = ""


@dataclass(frozen=True)
class FraudRulesConfig:
    """The fully loaded and validated fraud-rules.json contents."""

    rules: tuple[FraudRule, ...]
    threshold: int

    def rule_weight(self, name: str) -> int:
        """Return the point weight for a rule by name.

        Raises `ConfigError` if `name` is not one of the loaded rules -- this
        is a config-level lookup failure, not a data validation error.
        """
        for rule in self.rules:
            if rule.name == name:
                return rule.weight
        raise ConfigError(f"No fraud rule named {name!r} in loaded config.")


def load_fraud_rules_config(path: str) -> FraudRulesConfig:
    """Load and validate `path` as a fraud-rules.json file.

    Raises `ConfigError` if the file is missing, unreadable, not valid JSON,
    or fails structural validation (wrong rule count, unknown/duplicate rule
    name, or non-integer weight/threshold).
    """
    file_path = Path(path)
    try:
        raw_text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            f"Fraud rules config file not found or unreadable: {path}"
        ) from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Fraud rules config file is not valid JSON: {path}"
        ) from exc

    if not isinstance(data, dict):
        raise ConfigError("Fraud rules config must be a JSON object.")

    rules_raw = data.get("rules")
    if not isinstance(rules_raw, list) or len(rules_raw) != _EXPECTED_RULE_COUNT:
        raise ConfigError(
            f"Fraud rules config must contain exactly {_EXPECTED_RULE_COUNT} rules."
        )

    rules: list[FraudRule] = []
    seen_names: set[str] = set()
    for entry in rules_raw:
        if not isinstance(entry, dict):
            raise ConfigError("Each fraud rule entry must be a JSON object.")

        name = entry.get("name")
        if not isinstance(name, str) or name not in CANONICAL_FRAUD_RULE_NAMES:
            raise ConfigError(f"Unknown or missing fraud rule name: {name!r}")
        if name in seen_names:
            raise ConfigError(f"Duplicate fraud rule name: {name!r}")
        seen_names.add(name)

        weight = entry.get("weight")
        if not isinstance(weight, int) or isinstance(weight, bool):
            raise ConfigError(f"Fraud rule {name!r} weight must be an integer.")

        description = entry.get("description", "")
        rules.append(FraudRule(name=name, weight=weight, description=str(description)))

    # No further "all 5 canonical names present" check is needed here: the
    # length check above guarantees exactly 5 entries, the per-entry check
    # guarantees each name is one of the 5 canonical names, and the
    # duplicate check guarantees all 5 names are distinct -- so `seen_names`
    # is necessarily exactly `CANONICAL_FRAUD_RULE_NAMES` at this point.

    threshold = data.get("threshold")
    if not isinstance(threshold, int) or isinstance(threshold, bool):
        raise ConfigError("Fraud rules config 'threshold' must be an integer.")

    return FraudRulesConfig(rules=tuple(rules), threshold=threshold)
