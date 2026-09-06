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

## Group B — Config Layer (E2-S1, E2-S2, E2-S3)

**Branch:** `group-b/config-layer` @ `51ff8b9` ("feat(config): implement Group B config layer (E2-S1, E2-S2, E2-S3)")
**Verification mode for this group:** N/A — pure Python config layer built on Types, no API/DB/Docker/UI surface. Verified by direct pytest/ruff/mypy execution against `backend/.venv`.

### Verdict: **PASS**

All three layers of the ratchet gate that apply to this group (unit tests against every AC, static gates, architecture/structural gates) were independently re-executed and pass. No blocking defects found.

---

## What was independently re-run

```
cd backend && .venv/Scripts/python -m pytest --cov=src --cov-report=term-missing -q
```
Result: **115 passed**, coverage **100%** across the full `src/` tree (359/359 statements), including the three new modules `src/config/app_config.py` (34/34), `src/config/assessment_rules_config.py` (59/59), `src/config/fraud_rules_config.py` (56/56). Coverage baseline in `.claude/state/coverage-baseline.txt` is `100` — ratchet held.

```
.venv/Scripts/python -m ruff check .
```
Result: **All checks passed!**

```
.venv/Scripts/python -m mypy src/
```
Result: **Success: no issues found in 10 source files.**

Independent checks (not trusting the generator's report or docstrings):

- Read the shipped `backend/config/fraud-rules.json` directly: exactly 5 rules — `HIGH_CLAIM_TO_SUM_RATIO`:40, `EARLY_FILING`:25, `CLAIM_FREQUENCY`:30, `MOTOR_MISSING_FIR`:15, `ROUND_NUMBER_CLAIM`:10 — and `"threshold": 60`. Matches BRD section 11 and data-models.md section 3.2's canonical rule-name closed set exactly.
- Read the shipped `backend/config/assessment-rules.json` directly: `motor` (deductible 5000, co_pay_pct 0), `health` (deductible 1000, co_pay_pct 10), `life` (deductible 0, co_pay_pct 0), `auto_approve_ceiling: 50000`. Matches E2-S2 AC1/AC2 exactly.
- Confirmed `test_repo_fraud_rules_config_has_exactly_5_rules_matching_brd_weights`, `test_repo_fraud_rules_config_threshold_is_60`, `test_repo_assessment_rules_config_has_exact_per_claim_type_values`, and `test_repo_assessment_rules_config_auto_approve_ceiling_is_50000` load the actual repo file (`Path(__file__).resolve().parents[3] / "config" / ...`), not an in-memory/tmp fixture — a regression to the shipped file would fail these tests, not just an isolated unit fixture.
- Grepped `backend/src/config/*.py` myself for imports (not trusting `test_config_layer_imports.py`'s existence alone): only `__future__`, `json`, `dataclasses`, `pathlib`, `os`, `collections.abc`, and `src.types.*`. No `src.repositories`, `src.services`, `src.api`, or `src.db` imports anywhere.
- Mutation-tested `test_config_layer_imports.py` itself: temporarily added `backend/src/config/_mutation_test_temp.py` containing `from src.repositories.fake import Something`, re-ran the architecture test suite — it correctly failed with `AssertionError: _mutation_test_temp.py imports non-Types, non-stdlib module 'src.repositories.fake'`. Removed the temp file, re-ran — 3 passed, working tree confirmed clean (`git status --short` empty). The test is genuine, not vacuous.
- Grepped for caching patterns (`lru_cache`, `_cache`, `@cache`, module-level singletons) in `backend/src/config/` — no matches. Both `load_fraud_rules_config` and `load_assessment_rules_config` are plain functions with no module-level state; each call does `Path(path).read_text()` fresh.
- Diffed `backend/src/types/exceptions.py` between the Group A merge commit (`c184ca0`) and this commit (`51ff8b9`): the only change is `ConfigError` gaining an explicit `__init__(self, message: str, *, variable_name: str | None = None)` (previously it had no custom `__init__` and inherited `Exception.__init__`). This is strictly additive — a new keyword-only optional parameter with a default — so every existing call site (`ConfigError("some message")`) is unaffected. Confirmed `backend/tests/unit/types/test_exceptions.py` is not in the changed-file list for this commit (`git diff --name-only c184ca0..51ff8b9`) and re-ran it in isolation: 10/10 passed unmodified.
- Confirmed `backend/src/config/__init__.py` exists (empty, as expected for a plain package marker) and all six files listed in `sprint-contracts/B.json`'s `files_must_exist` are present.
- Cross-checked `specs/design/folder-structure.md`'s `backend/src/config/` block against the actual directory — exact match (`app_config.py`, `fraud_rules_config.py`, `assessment_rules_config.py`, `__init__.py`).

---

## Check-by-check findings (F014-F023)

- **F014** (5 rules, exact BRD weights) — PASS. Verified against the shipped file directly (see above), not just a test fixture.
- **F015** (threshold == 60) — PASS. Verified against the shipped file directly.
- **F016** (missing/malformed file raises typed `ConfigError` at load) — PASS. `test_load_fraud_rules_config_missing_file_raises_config_error`, `..._malformed_json_raises_config_error`, plus 8 more structural-failure tests (wrong count, unknown name, duplicate name, missing/non-int threshold, non-int weight, non-object top-level/entry) in `test_fraud_rules_config.py`, and the analogous set in `test_assessment_rules_config.py`. All raise `ConfigError`, none fall back to defaults — confirmed by reading `fraud_rules_config.py`/`assessment_rules_config.py`: every failure path is an explicit `raise ConfigError(...)`, there is no `except: pass` or default-substitution branch anywhere in either loader.
- **F017** (AC4 - on-disk edit with no code change is picked up on next load) — PASS, and this is the trickiest one so it got the most scrutiny. `test_load_fraud_rules_config_reflects_on_disk_edit_on_next_load` (and the assessment-rules analog) writes a config to a `tmp_path`, calls `load_fraud_rules_config(str(path))` once (`first_load`, threshold 60), overwrites the same file path in place with `threshold: 75`, calls `load_fraud_rules_config(str(path))` again (`second_load`), and asserts `second_load.threshold == 75` and `first_load.threshold == 60` (proving the first returned object is an independent, non-mutated snapshot, and the loader is not caching/memoizing by path). This is a legitimate, non-trivial reload test, not testing against a cached singleton.
- **F018** (assessment shipped values) — PASS. Verified against the shipped file directly.
- **F019** (auto_approve_ceiling == 50000) — PASS. Verified against the shipped file directly.
- **F020** (unknown claim_type raises `UnknownClaimTypeError`) — PASS, with a specific reachability check per the task's instruction. Two tests cover this: (1) `test_for_claim_type_raises_unknown_claim_type_error_for_unrecognized_key` calls `config.for_claim_type("BOAT")` against a real, fully-loaded config — this is genuinely reachable in production, since `for_claim_type()` is a public method any caller (including a future API layer parsing an untrusted `claim_type` string) could call with an out-of-domain value, and `AssessmentRulesConfig.for_claim_type` defensively re-coerces via `ClaimType(claim_type)` specifically to catch this. (2) `test_for_claim_type_raises_unknown_claim_type_error_when_map_incomplete` directly constructs an `AssessmentRulesConfig` with an incomplete `rules_by_claim_type` map and calls `for_claim_type(ClaimType.LIFE)` — this test's own docstring correctly discloses that this exact scenario is unreachable via `load_assessment_rules_config` (which always populates all 3 types) and exists purely to cover the defensive `except KeyError` branch. This is legitimate defensive-code coverage disclosed honestly, not a disguised no-op test — the class is a public dataclass, not sealed against manual construction, so a future caller building one another way (or a refactor) could hit this path.
- **F021** (db_path/backend_port 8000/frontend_port 5173) — PASS. `test_load_app_config_exposes_db_path_and_default_ports` asserts all three; `DEFAULT_BACKEND_PORT = 8000` / `DEFAULT_FRONTEND_PORT = 5173` constants in `app_config.py:23-24` match the AC literally.
- **F022** (valid_roles == exactly [CUSTOMER, ASSESSOR, ADMIN], from Types) — PASS, checked for the "hardcoded strings that happen to match" trap specifically. `app_config.py` imports `Role` from `src.types.enums` and builds `VALID_ROLES: tuple[Role, ...] = (Role.CUSTOMER, Role.ASSESSOR, Role.ADMIN)` — genuine enum members, not string literals. Confirmed `Role` in `backend/src/types/enums.py:11-16` is `CUSTOMER`/`ASSESSOR`/`ADMIN` exactly. Test asserts `list(config.valid_roles) == [Role.CUSTOMER, Role.ASSESSOR, Role.ADMIN]` — importing and comparing against the same enum, not a re-typed string list.
- **F023** (missing required env var raises typed error naming the variable) — PASS, checked for the "generic message" trap specifically. `load_app_config` raises `ConfigError(f"Missing required environment variable: {DB_PATH_ENV_VAR}", variable_name=DB_PATH_ENV_VAR)`. `test_load_app_config_missing_db_path_raises_config_error_naming_variable` asserts both `exc_info.value.variable_name == _DB_PATH_ENV_VAR` (a real attribute, not just message text) and `_DB_PATH_ENV_VAR in str(exc_info.value)` (the human-readable message too). Genuinely names the variable via a structured attribute, not just an incidental substring.

## `ConfigError` extension does not break Group A

Confirmed additive-only (see diff summary above): new keyword-only `variable_name` parameter with a `None` default. `backend/tests/unit/types/test_exceptions.py` was not touched by this commit and passes unmodified (10/10) with the extended class. Full suite (115 tests, spanning both Types and Config) passes together with no interaction failures.

## One-way import rule

Confirmed via independent grep and a live mutation test of the architecture test itself (see above) — `backend/src/config/*.py` imports only stdlib and `src.types.*`. `test_config_layer_imports.py`'s AST-scan logic is sound: it correctly failed when a forbidden import was injected and correctly passed once removed, so it is not vacuously green.

## No config caching

Confirmed via grep (no `lru_cache`/`_cache`/singleton patterns) and via direct reading of both loader modules — every call to `load_fraud_rules_config`/`load_assessment_rules_config` does a fresh `Path.read_text()` plus re-validation, with no module-level state. This is consistent with the F017/AC4 reload tests actually passing for the right reason (fresh read) rather than coincidentally passing due to some other caching quirk.

## Assessment of the "no hard-coded threshold/weight validation" design decision

The generator's stated reasoning is sound and I agree with it. The loader validates:
1. Exactly 5 rule entries (count).
2. Each rule name is drawn from the canonical closed set in data-models.md section 3.2 (domain-set membership).
3. No duplicate names (implies, combined with 1+2, that all 5 canonical names are present exactly once - confirmed by reading the loader's own comment at `fraud_rules_config.py:124-128`, which correctly derives this logical guarantee rather than asserting it redundantly).
4. Weight and threshold are integers (type structural validation).

It deliberately does not validate that `threshold == 60` or that any specific rule's `weight` equals its BRD value. This is the correct line to draw: E2-S1 AC4 explicitly requires that the threshold (and, by the same logic, the rule weights) be editable via the file with no code change - hardcoding "threshold must equal 60" into the loader would make the value immutable in practice (any edit would throw at load time), directly contradicting AC4. The BRD-exact values are correctly enforced instead as content assertions against the shipped file (`test_repo_fraud_rules_config_has_exactly_5_rules_matching_brd_weights`, `test_repo_fraud_rules_config_threshold_is_60`) - this is the right layer for "the value the ops team ships today happens to be 60," while the loader itself only enforces the shape/domain a valid file must have.

I considered whether this under-validates in a way that would let a "structurally valid but nonsensical" file slip through in production - e.g. `threshold: -5` or `weight: 0` for every rule. The current loader would accept both. This is arguably a legitimate gap (negative or zero weights/threshold are nonsensical for a scoring system, and rejecting them would not conflict with AC4's intent of allowing any different *valid* value to be editable). However: (a) no story or AC in E2-S1/E2-S2 asks for a value-range check, (b) `data-models.md` does not specify a valid range either, and (c) adding an opinionated range check not requested by any AC would be scope creep in the other direction. I flag this as a non-blocking observation for a future story (e.g., "weights and threshold must be non-negative integers") rather than a defect in this group.

---

## Non-blocking observations (nits)

1. Neither loader rejects negative or zero weights/threshold/deductible/co_pay_pct/auto_approve_ceiling (see design-decision assessment above). Not required by any current AC; worth a future story if ops-side fat-fingering a negative value in the JSON should be caught at load time rather than surfacing as a downstream scoring anomaly.
2. `ClaimTypeRules`/`FraudRule`/`AppConfig` are all `@dataclass(frozen=True)`, which is good practice for config value objects (prevents accidental in-place mutation of a loaded snapshot) - noted as a positive, not a defect.

## Files reviewed

- `sprint-contracts/B.json`
- `specs/stories/E2-S1.md`, `E2-S2.md`, `E2-S3.md`
- `specs/design/data-models.md` (section 3.2)
- `specs/design/folder-structure.md`
- `.claude/architecture.md`
- `backend/config/fraud-rules.json`, `assessment-rules.json`
- `backend/src/config/app_config.py`, `fraud_rules_config.py`, `assessment_rules_config.py`, `__init__.py`
- `backend/src/types/exceptions.py` (diffed against `c184ca0`)
- `backend/tests/unit/config/test_fraud_rules_config.py`, `test_assessment_rules_config.py`, `test_app_config.py`
- `backend/tests/architecture/test_config_layer_imports.py` (mutation-tested)
- `backend/tests/unit/types/test_exceptions.py` (re-run in isolation, confirmed unmodified)
- `features.json` (F014-F023 updated to `passes: true` following this evaluation)
