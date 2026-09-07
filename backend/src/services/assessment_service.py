"""Assessment computation service (E6-S1).

Pure computation service -- Service layer per `.claude/architecture.md`. This
module imports only Types (`src.types.enums.ClaimType`) and Config
(`src.config.assessment_rules_config`); it never imports Repository or API
layers, since no persistence happens here (mapping a result onto
`AssessmentRepository.insert()` is a separate, later concern).

Computes `payable_amount = min(claim_amount, sum_insured) - deductible -
co_pay`, entirely in fixed-point `Decimal` arithmetic (AC5 / NFR-01 -- no
`float` is ever constructed or used in this module). AC-05 requires the
`payable_amount >= 0` invariant, so the result is clamped at `Decimal("0")`
before final quantization (AC4).

`co_pay` is `co_pay_pct` percent of the *post-deductible* amount, not of the
original `claim_amount` or of `sum_insured` -- confirmed by the AC2 worked
example (health claim, claim_amount 20000, deductible 1000: co-pay is "10%
co-pay of 19000", i.e. of `claim_amount - deductible`, not of 20000).

Rounding: `assessment-rules.json` only ever configures integer `co_pay_pct`
values, but `after_deductible * co_pay_pct / 100` can still produce a
fractional cent (e.g. 15% of 100.01 = 15.0015). The story does not specify a
rounding mode, so every money field is quantized to two decimal places with
`ROUND_HALF_UP` -- the conventional rounding mode for money -- matching the
canonical `"35000.00"`-style decimal-string convention used elsewhere in the
codebase (see `data-models.md` sec 2.5 and `assessment_repository.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from src.config.assessment_rules_config import AssessmentRulesConfig
from src.types.enums import ClaimType

_CENTS = Decimal("0.01")
_ZERO = Decimal("0")


def _to_money(value: Decimal) -> Decimal:
    """Quantize `value` to 2 decimal places using ROUND_HALF_UP."""
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class AssessmentComputation:
    """The pure result of `assess()`.

    Deliberately *not* `src.types.models.Assessment`: that dataclass is
    DB-oriented and carries `id`/`claim_id`/`created_at` fields that don't
    exist yet at computation time (persistence, if any, happens downstream
    of this call via `AssessmentRepository.insert()`). This lighter-weight
    local result type carries only the five money fields the computation
    itself produces.
    """

    claim_amount: Decimal
    sum_insured: Decimal
    deductible: Decimal
    co_pay: Decimal
    payable_amount: Decimal


def assess(
    claim_amount: Decimal,
    sum_insured: Decimal,
    claim_type: ClaimType,
    config: AssessmentRulesConfig,
) -> AssessmentComputation:
    """Compute the payable amount for a claim (AC-05 / NFR-01).

    `rules.deductible` and `rules.co_pay_pct` arrive from
    `AssessmentRulesConfig.for_claim_type()` as plain `int` (the config
    loader validates them as JSON integers), so both are explicitly coerced
    through `Decimal(...)` -- never through `float` -- before entering any
    arithmetic (AC5).
    """
    rules = config.for_claim_type(claim_type)

    base = min(claim_amount, sum_insured)
    deductible = Decimal(rules.deductible)
    after_deductible = base - deductible
    co_pay_pct = Decimal(rules.co_pay_pct)
    co_pay = after_deductible * co_pay_pct / Decimal(100)
    payable_amount = after_deductible - co_pay

    if payable_amount < _ZERO:
        payable_amount = _ZERO

    return AssessmentComputation(
        claim_amount=_to_money(claim_amount),
        sum_insured=_to_money(sum_insured),
        deductible=_to_money(deductible),
        co_pay=_to_money(co_pay),
        payable_amount=_to_money(payable_amount),
    )
