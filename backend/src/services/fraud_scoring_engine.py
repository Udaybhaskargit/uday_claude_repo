"""Deterministic fraud scoring engine (E5-S2, AC-04).

Sums the weights of every triggered rule from the E2-S1 config
(`backend/config/fraud-rules.json`, loaded via
`src.config.fraud_rules_config.load_fraud_rules_config`) and compares the
total against the configured threshold.

Design decision -- pure function over an explicit input bundle
------------------------------------------------------------------
`specs/design/folder-structure.md` describes this module's function as a pure
deterministic `score(claim, config) -> (score, breakdown)`. In practice 4 of
the 5 rules need context beyond a bare `Claim` row:

- `HIGH_CLAIM_TO_SUM_RATIO` needs the *Policy's* `sum_insured`.
- `EARLY_FILING` needs the *Policy's* `effective_date`.
- `CLAIM_FREQUENCY` needs a same-policy claim count over the last 90 days --
  a repository query.
- `MOTOR_MISSING_FIR` needs to know whether a verified `POLICE_FIR`
  `ClaimDocument` exists for the claim.

To keep this module genuinely pure and deterministic (F057: identical inputs
must always produce an identical `(score, breakdown)` result, with zero
hidden I/O), `score()` takes an explicit, self-contained `FraudScoringInput`
value object instead of a `Claim` + repository handles. This engine performs
*zero* database/repository access. A future story (E5-S3, Group F) is
responsible for gathering `recent_claim_count_90d` and
`has_verified_police_fir` from the repositories and constructing
`FraudScoringInput` before calling `score()`.

`FraudRuleBreakdownEntry` (data-models.md sec 3.2) is defined locally in this
module rather than in `src/types/models.py`: as of this writing,
`models.py`'s `FraudScreening.breakdown` field is typed as the untyped
`list[dict[str, object]]` (see sec 3.2's own note that this shape is
"embedded ... not a separate table"), so there is no existing dataclass to
reuse. Defining it here avoids touching a shared, Group-A-owned file.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.config.fraud_rules_config import FraudRulesConfig
from src.types.enums import ClaimType

_ROUND_NUMBER_DIVISOR = Decimal(10000)
_HIGH_RATIO_THRESHOLD = Decimal("0.8")
_EARLY_FILING_MAX_DAYS = 3
_CLAIM_FREQUENCY_MAX_COUNT = 2


@dataclass(frozen=True)
class FraudScoringInput:
    """Self-contained inputs for one fraud-scoring evaluation.

    Every field is precomputed by the caller -- this engine never reaches
    into a database or repository itself. See the module docstring for why.
    """

    claim_amount: Decimal
    sum_insured: Decimal
    incident_date: str
    policy_effective_date: str
    claim_type: ClaimType
    recent_claim_count_90d: int
    has_verified_police_fir: bool


@dataclass(frozen=True)
class FraudRuleBreakdownEntry:
    """One triggered rule's contribution to the total score (sec 3.2)."""

    rule_name: str
    weight: int


def _is_high_claim_to_sum_ratio_triggered(fraud_input: FraudScoringInput) -> bool:
    """Claim amount exceeds 80% of the policy sum insured."""
    return fraud_input.claim_amount / fraud_input.sum_insured > _HIGH_RATIO_THRESHOLD


def _is_early_filing_triggered(fraud_input: FraudScoringInput) -> bool:
    """Incident filed within 3 days (inclusive) of policy inception."""
    incident_date = date.fromisoformat(fraud_input.incident_date)
    effective_date = date.fromisoformat(fraud_input.policy_effective_date)
    return (incident_date - effective_date).days <= _EARLY_FILING_MAX_DAYS


def _is_claim_frequency_triggered(fraud_input: FraudScoringInput) -> bool:
    """More than 2 claims filed by the same policy in the last 90 days."""
    return fraud_input.recent_claim_count_90d > _CLAIM_FREQUENCY_MAX_COUNT


def _is_motor_missing_fir_triggered(fraud_input: FraudScoringInput) -> bool:
    """Motor claim is missing the required, verified police FIR document."""
    return (
        fraud_input.claim_type == ClaimType.MOTOR
        and not fraud_input.has_verified_police_fir
    )


def _is_round_number_claim_triggered(fraud_input: FraudScoringInput) -> bool:
    """Claim amount is a round number evenly divisible by 10000."""
    return fraud_input.claim_amount % _ROUND_NUMBER_DIVISOR == 0


# Maps each canonical rule name (data-models.md sec 3.2 closed set) to its
# trigger predicate. Keyed by name -- not a positional list -- so the engine
# stays config-driven: iteration order below follows `config.rules` order,
# never a hardcoded rule order.
_RULE_TRIGGER_CHECKS: dict[str, Callable[[FraudScoringInput], bool]] = {
    "HIGH_CLAIM_TO_SUM_RATIO": _is_high_claim_to_sum_ratio_triggered,
    "EARLY_FILING": _is_early_filing_triggered,
    "CLAIM_FREQUENCY": _is_claim_frequency_triggered,
    "MOTOR_MISSING_FIR": _is_motor_missing_fir_triggered,
    "ROUND_NUMBER_CLAIM": _is_round_number_claim_triggered,
}


def score(
    fraud_input: FraudScoringInput, config: FraudRulesConfig
) -> tuple[int, list[FraudRuleBreakdownEntry]]:
    """Evaluate all 5 rules and sum the weights of every triggered one.

    Pure and deterministic: identical `(fraud_input, config)` always produces
    an identical `(total_score, breakdown)` result (F057) -- no I/O, no
    clock reads, no randomness. `breakdown` contains only the *triggered*
    rules, in the same order as `config.rules`, and every weight is read
    from `config` (never hardcoded), so retuning `fraud-rules.json` changes
    scoring behavior with no code change.
    """
    total_score = 0
    breakdown: list[FraudRuleBreakdownEntry] = []
    for rule in config.rules:
        is_triggered = _RULE_TRIGGER_CHECKS[rule.name](fraud_input)
        if is_triggered:
            total_score += rule.weight
            breakdown.append(FraudRuleBreakdownEntry(rule_name=rule.name, weight=rule.weight))
    return total_score, breakdown


def is_flagged(total_score: int, config: FraudRulesConfig) -> bool:
    """True iff `total_score` meets or exceeds the configured threshold."""
    return total_score >= config.threshold


def score_and_flag(
    fraud_input: FraudScoringInput, config: FraudRulesConfig
) -> tuple[int, list[FraudRuleBreakdownEntry], bool]:
    """Convenience wrapper: `score()` plus the derived `flagged` boolean."""
    total_score, breakdown = score(fraud_input, config)
    return total_score, breakdown, is_flagged(total_score, config)
