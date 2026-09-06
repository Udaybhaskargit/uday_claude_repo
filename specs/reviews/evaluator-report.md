# Evaluator Report

## Group A — Domain Types Layer (E1-S1, E1-S2, E1-S3)

**Branch:** `group-a/domain-types` @ `d00d4a5`
**Verification mode for this group:** N/A — pure Python types layer, no Docker/API/DB/Playwright surface. Verified by direct pytest/ruff/mypy execution against `backend/.venv`.

### Verdict: **PASS**

All three layers of the ratchet gate that apply to this group (unit tests against every AC, static gates, architecture/structural gates) were independently re-executed and pass. No blocking defects found.

---

## What was independently re-run

```
cd backend && .venv/Scripts/python -m pytest --cov=src --cov-report=term-missing -q
```
Result: **73 passed**, coverage **100%** across `src/types/enums.py`, `models.py`, `exceptions.py`, `state_machine.py` (207/207 statements).

```
.venv/Scripts/python -m ruff check .
```
Result: **All checks passed!**

```
.venv/Scripts/python -m mypy src/
```
Result: **Success: no issues found in 6 source files.**

Independent greps (not trusting the generator's report):

- `grep -rn '\.status\s*=' backend/src/types/*.py | grep -v state_machine.py` → only match is `self.status == PolicyStatus.ACTIVE` in `models.py:45` (a comparison inside `Policy.is_active_on`, not an assignment). No mutation outside `state_machine.py`.
- `grep -n 'float' backend/src/types/models.py` → only a doc-comment reference ("never `float`"); no `float` type usage anywhere in the money-field declarations.
- `grep -rn '^from src\.\(config\|repositories\|services\|api\)\|^import src\.\(config\|repositories\|services\|api\)' backend/src/types/*.py` → empty. Actual imports in `src/types/` are limited to stdlib (`enum`, `typing`, `dataclasses`, `decimal`, `datetime`) and intra-layer (`src.types.enums`, `src.types.exceptions`, `src.types.models`).
- Folder contents of `backend/src/types/`: exactly `__init__.py`, `enums.py`, `models.py`, `exceptions.py`, `state_machine.py` (plus `__pycache__`), matching `specs/design/folder-structure.md` line-for-line.

---

## Check-by-check findings

### 1. Every AC is genuinely tested (not just described)

Traced each AC to a specific assertion that would fail if violated:

- **E1-S1 AC1** (Claim fields) → `test_claim_exposes_required_fields` constructs a `Claim` with all named fields and asserts each value/type, including `isinstance(claim.claim_amount, Decimal)`. Real.
- **E1-S1 AC2** (ClaimStatus exactly 10) → `test_claim_status_enum_contains_exactly_ten_values_in_order` asserts both the exact ordered list of values **and** `len(ClaimStatus) == 10`. This is a genuine closed-set check, not a subset-membership check.
- **E1-S1 AC3** (Role exactly 3) → `test_role_enum_contains_exactly_three_values` asserts set equality **and** `len(Role) == 3`. Genuine.
- **E1-S1 AC4** (Policy fields) → `test_policy_exposes_required_fields`, all named fields asserted.
- **E1-S1 AC5** (Decimal, never float) → `test_monetary_fields_across_claim_assessment_settlement_are_decimal_never_float` iterates `dataclasses.fields()` for `Claim`, `Assessment`, `Settlement` and asserts `field.type is Decimal` (not a string annotation — `models.py` does not use `from __future__ import annotations`, so `field.type` is the live type object, confirmed by reading the module). This is a real structural check, not a per-instance duck-typing check.
- **E1-S2 AC1** (DOCS_PENDING + DOCS_VERIFIED → FRAUD_SCREENING) → `test_docs_pending_to_fraud_screening_on_docs_verified`, direct assertion on `claim.status` post-call and on the returned record.
- **E1-S2 AC2** (invalid event on terminal state raises + status unchanged) → `test_invalid_event_for_terminal_state_raises_and_leaves_status_unchanged` explicitly asserts `claim.status == ClaimStatus.SETTLED` **after** the `pytest.raises` block — the negative-path status-unchanged assertion the task specifically asked me to verify is present and correctly placed outside the `with` block.
- **E1-S2 AC3** (every ClaimStatus is a key, no fallthrough) → `test_every_claim_status_is_a_key_in_the_transition_table` (all 10 present) + `test_terminal_states_have_no_outgoing_events` (REJECTED/REOPENED == `{}`) + `test_transition_table_matches_data_models_spec_exactly` (full dict equality against a table copied independently in the test file). Strong.
- **E1-S2 AC4** (ClaimStateTransition returned) → `test_successful_transition_returns_claim_state_transition_record` asserts type and all four+ fields.
- **E1-S3 AC1** (ReasonCode exactly 6) → `test_reason_code_enum_contains_exactly_six_values` asserts set equality **and** `len(ReasonCode) == 6`.
- **E1-S3 AC2/AC3** (exceptions carry policy_number + incident_date) → directly asserted on raised instances.
- **E1-S3 AC4** (exception → HTTP status mapping) → `test_exception_types_map_to_exactly_one_http_status_code_each` and `test_exception_status_map_is_consistent_with_class_attributes` (including `len(EXCEPTION_STATUS_MAP) == 3`, so no extra/missing entries).

No AC found with only a docstring-level or membership-only check. All closed-set ACs use `len(...)` plus exact set/list equality, per the task's specific concern.

### 2. Closed enum sets are exact

Verified directly: `ClaimStatus` = 10 values (test asserts `len == 10` and exact ordered list, matches data-models.md §1 exactly). `Role` = 3 (`len == 3`). `ReasonCode` = 6 (`len == 6`, matches data-models.md §1 exactly, and correctly excludes `DUPLICATE_CLAIM` which the doc explicitly says belongs only to `ApiErrorCode`). All confirmed via re-run of `pytest`.

### 3. Transition table complete and correct

`TRANSITION_TABLE` in `backend/src/types/state_machine.py:16-57` has all 10 `ClaimStatus` values as keys, including `REJECTED: {}` and `REOPENED: {}`. Spot-checked (and in fact fully diffed) every from/event/to triple against data-models.md §1.1 — table is byte-for-byte identical, including the two ADMIN_FORCE_REJECT paths from FRAUD_SCREENING/PROCESSING_FAILED and the two-path AUTO_APPROVED landing from MANUAL_REVIEW (ASSESSOR_APPROVE and ADMIN_FORCE_APPROVE both → AUTO_APPROVED). No discrepancies found. The test suite independently re-declares this table (`_EXPECTED_TRANSITION_TABLE` in `test_state_machine.py`) and asserts dict equality — a strong regression guard.

### 4. `transition()` behavior

- Valid transition: mutates `claim.status` in place and returns `ClaimStateTransition(from_state, to_state, event, timestamp, claim_id, actor_id)` — confirmed by reading `state_machine.py:60-90` and by the parametrized test over every one of the 22 documented transitions (`test_every_documented_transition_succeeds`).
- Invalid transition: `test_every_undocumented_event_for_every_state_raises_and_does_not_mutate` is a combinatorial check — for **every** `ClaimStatus` × every `ClaimEvent` not in that state's allowed set, it asserts `InvalidClaimStateException` is raised AND `claim.status == status` (unchanged) after the exception. This is a much stronger check than the AC's single example and covers all ~158 invalid (state, event) pairs (10 states × 18 events − 22 valid = 158).

### 5. No other mutation of `Claim.status`

`test_state_mutation_gate.py` is genuinely non-vacuous: `test_state_machine_contains_the_sole_status_mutation` positively asserts that `state_machine.py` **does** contain a `.status =` assignment (so the "no offenders" result in the other test can't be achieved by simply having no code anywhere that touches `.status`). The AST walk correctly matches `ast.Assign`/`ast.AugAssign` with an `ast.Attribute` target named `status`, which would catch a hypothetical `claim.status = X` planted in any other module. My own grep confirms only `models.py:45` matches `\.status\s*=` outside `state_machine.py`, and that match is a `==` comparison inside `Policy.is_active_on`, not an assignment.

### 6. Money fields are Decimal, never float

Confirmed: `claim_amount`, `sum_insured`, `deductible`, `co_pay`, `payable_amount`, `payout_amount` are all typed `Decimal` in `models.py` (Claim, Policy, Assessment, Settlement). Grep for `float` in `models.py` returns only a docstring comment, no type usage.

### 7. Exception → HTTP status mapping (F013 / E1-S3 AC4)

`exceptions.py:20-80`: `PolicyNotActiveException.http_status_code = 422`, `DuplicateClaimException.http_status_code = 409`, `InvalidClaimStateException.http_status_code = 409`. `EXCEPTION_STATUS_MAP` has exactly these 3 entries (test asserts `len == 3`). `PolicyNotActiveException` and `DuplicateClaimException` both carry `policy_number` + `incident_date` as instance attributes, confirmed by constructor code and by tests.

### 8. One-way import rule

Confirmed empty via my own independent grep against the actual import statements (see above). `test_layer_imports.py` implements this correctly via AST parsing (robust to import style) rather than fragile grep, and checks both bare top-level names (`config`, `repositories`, `services`, `api`, `ui`) and dotted `src.*` prefixes.

### 9. Gate re-run results

| Gate | Command | Result |
|---|---|---|
| pytest + coverage | `pytest --cov=src --cov-report=term-missing -q` | 73 passed, 100% coverage (207/207 stmts) |
| ruff | `ruff check .` | All checks passed |
| mypy | `mypy src/` | Success: no issues found in 6 source files |

### 10. Generator-reported deviations — assessment

**(a) `enum.StrEnum` instead of `class X(str, Enum)`.** Confirmed legitimate: `pyproject.toml` sets `target-version = "py312"` and `select = [..., "UP", ...]`, so ruff's UP042 (deprecates the `str, Enum` mixin pattern in favor of `StrEnum` on py3.11+) would indeed fire. `StrEnum` members are still `str` instances with the same `.value`/equality semantics used throughout the tests and downstream code (`isinstance(Role.CUSTOMER, str)` is asserted and passes). Reasonable, behaviorally-equivalent substitution — not a defect.

**(b) `SUBMIT_FNOL` → `DOCS_VERIFIED` substitution in the E1-S2 AC2 test.** Confirmed `SUBMIT_FNOL` does not appear anywhere in data-models.md §1.1's event list or in `ClaimEvent`. The substituted test (`test_invalid_event_for_terminal_state_raises_and_leaves_status_unchanged`) uses `DOCS_VERIFIED` against a `SETTLED` claim — `SETTLED`'s only valid event is `REOPEN`, so this genuinely exercises "invalid event on current terminal state raises `InvalidClaimStateException` and leaves status unchanged," which is the AC's actual intent. The deviation is well-documented in the test's own comment and does not weaken coverage — in fact coverage is stronger than the story text alone, given the combinatorial `test_every_undocumented_event_for_every_state_raises_and_does_not_mutate` test also covers this exact case. Not a defect.

**(c) `Policy.is_active_on(date)` added ahead of schedule.** Confirmed this method is explicitly documented in data-models.md §2.1 ("**Behavior:** `is_active_on(date)` returns `True` iff..."), which is a source-of-truth doc for this same commit's scope (E1-S1 touches Policy's shape). It is a pure function with zero I/O and zero dependencies on config/repository/service layers (verified — no new imports introduced), fully unit-tested (3 tests covering active+in-window, active+out-of-window, inactive-status branches), and does not preempt or conflict with any future Group D repository work (a repository would still own fetching a `Policy` row; this only adds a computed property on the already-defined dataclass). This is harmless, forward-compatible scope addition rather than problematic scope creep — the underlying data-models.md doc already committed to this shape before this method existed in code. Non-blocking; worth noting in the iteration log per the task's own framing, but not a defect.

---

## Non-blocking observations (nits)

1. `ClaimEvent` in `enums.py` includes all 18 canonical event names, but the doc's example event `SUBMIT_FNOL` used in the E1-S2 AC2 story text has no `ClaimEvent` member and never will (it isn't part of the transition table) — this is expected given data-models.md §1.1, but a reader skimming only the story file (not the design doc) could be confused. Consider a one-line note in E1-S2.md's AC2 pointing at the canonical event list, for future story-writing hygiene. Does not affect this group's pass/fail.
2. `ConfigError` and `ValidationError` in `exceptions.py` are defined ahead of their stories (E2/later groups) but are unused outside their own unit tests in this commit — harmless, same reasoning as deviation (c).

## Files reviewed

- `sprint-contracts/A.json`
- `specs/stories/E1-S1.md`, `E1-S2.md`, `E1-S3.md`
- `specs/design/data-models.md` (§1, §1.1, §2.1, §2.2, §2.8, §3.1)
- `specs/design/folder-structure.md`
- `.claude/architecture.md`
- `backend/src/types/enums.py`, `models.py`, `exceptions.py`, `state_machine.py`
- `backend/tests/unit/types/test_enums.py`, `test_models.py`, `test_exceptions.py`, `test_state_machine.py`
- `backend/tests/architecture/test_layer_imports.py`, `test_state_mutation_gate.py`
- `backend/pyproject.toml`
- `features.json` (F001–F013 updated to `passes: true` following this evaluation)
