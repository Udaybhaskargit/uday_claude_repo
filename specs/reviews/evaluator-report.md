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

## Group C — Migrations & Auth Boundary (E3-S1, E8-S1)

**Branch:** `group-c/migrations-and-auth` @ `071de41` (E3-S1 migrations), `20e9bcf` (E8-S1 auth dependency).
**Verification mode for this group:** N/A — pure repository/API-dependency layer, no running server/Docker required. Verified by direct pytest/ruff/mypy execution against `backend/.venv`, plus hand-written standalone scripts run against the real committed `backend/migrations/` directory (not just the test suite's own fixtures).

### Verdict: **PASS** (both stories)

All three layers of the ratchet gate (independent re-run of every AC, static gates, and an explicit two-generator integration-gap check) pass. No blocking defects found.

---

## Integration-gap check (two generators, disjoint files)

`git show --stat --format="" 071de41` (E3-S1) touches only `backend/migrations/000{1..9}_*.sql`, `backend/src/db/{__init__.py,connection.py,migration_runner.py}`, and `backend/tests/unit/repositories/*`. `git show --stat --format="" 20e9bcf` (E8-S1) touches only `backend/requirements.txt`, `backend/src/api/**`, `backend/src/main.py`, and `backend/tests/integration/api/test_auth_dependency.py`. Zero file overlap between the two commits — confirmed by diffing the two `--stat` outputs directly.

Grepped `src/api/dependencies/auth.py` and `src/main.py` for any reference to `migration`, `connection`, `db_path`, `get_connection`, or `run_migrations` — zero matches. `main.py`'s `create_app()` currently only registers `/health`; it does not call `run_migrations()` or open a DB connection at startup (this is explicitly documented in `main.py`'s own module docstring as deferred to a later group). `AppConfig.db_path` exists (from Group B) but E8-S1's auth dependency never reads it — `get_actor_context`/`require_role` only consult `app_config.valid_roles`. Confirmed: E8-S1's code does not assume any DB/migration state exists, and E3-S1's migration runner/connection module is never invoked from `main.py` or `auth.py`. No integration gap.

---

## What was independently re-run

```
cd backend && .venv/Scripts/python -m pytest --cov=src --cov-report=term-missing -q
```
Result: **137 passed**, coverage **100%** across the full `src/` tree (451/451 statements), including the two new modules `src/db/connection.py` (7/7), `src/db/migration_runner.py` (50/50), and `src/api/dependencies/auth.py` (26/26). Coverage baseline in `.claude/state/coverage-baseline.txt` is `100` — ratchet held.

```
.venv/Scripts/python -m ruff check .
```
Result: **All checks passed!**

```
.venv/Scripts/python -m mypy src/
```
Result: **Success: no issues found in 17 source files.**

---

## Check-by-check findings — E3-S1 (migrations, F024-F027)

### 1. Schema fidelity against data-models.md §2

Diffed the actual CREATE TABLE SQL against data-models.md field-by-field for `policies` (0001), `claims` (0002), `fraud_screenings` (0004), and `settlements` (0007):

- **`policies`**: `sum_insured` is `TEXT NOT NULL` (money-as-TEXT convention honored); unique index on `policy_number`, plain index on `status` — matches §2.1 exactly.
- **`claims`**: `claim_amount TEXT NOT NULL`; FKs declared on `policy_id -> policies(id)` and `parent_claim_id -> claims(id)` (self-referential); indexes on `policy_id`, `status`, `claim_type`, `parent_claim_id`, and the composite `idx_claims_policy_id_incident_date ON claims (policy_id, incident_date)` required for E4-S3 duplicate detection — present and correctly composite (not two separate single-column indexes). Matches §2.2 exactly.
- **`fraud_screenings`** (append-only): `score`/`threshold` are `INTEGER NOT NULL`, `flagged INTEGER NOT NULL` (SQLite boolean-as-integer, correct), `breakdown TEXT NOT NULL` (JSON-as-TEXT, correct per §2.4); FK to `claims`; both `idx_fraud_screenings_claim_id` and the composite `(claim_id, created_at)` index for "latest screening" lookup are present. Matches §2.4 exactly.
- **`settlements`** (append-only, immutable): `payout_amount TEXT NOT NULL`; FKs to both `claims(id)` and `decisions(id)`; indexes on `claim_id` and `created_at` (for the reverse-chronological audit trail). Matches §2.7 exactly.
- Also spot-checked `claim_documents` (0003): unique composite index `idx_claim_documents_claim_id_document_type ON claim_documents (claim_id, document_type)` present exactly as data-models.md §2.3 requires, plus a non-unique `claim_id` index. Correct.
- `admin_overrides` (0009): `reason_code TEXT NOT NULL CHECK (length(reason_code) >= 1)` — a genuine DB-level enforcement of the "min length 1, mandatory" constraint from §2.9, on top of whatever the service layer will do in E8-S2. Good defense in depth.

All money fields across all 9 tables are `TEXT`, never `REAL`/`NUMERIC`/`FLOAT`. All FKs from data-models.md's "Relationships" sections are declared. All indexes listed in data-models.md's "Indexes" bullets for the 4 spot-checked tables (plus the 2 extra I checked) are present, correctly composite where specified.

### 2. F024 — strictly sequential numbering, no gaps

`ls backend/migrations/` shows exactly `0001_create_policies.sql` through `0009_create_admin_overrides.sql`, sequential with no gaps. `backend/tests/unit/repositories/test_migrations_directory.py` asserts this against the **real** directory (`Path(__file__).resolve().parents[3] / "migrations"`, not a synthetic tmp fixture) via three separate tests: filename-pattern match, `numbers == list(range(1, len(numbers)+1))`, and exact-name-list equality against `EXPECTED_NAMES`. All three re-run and pass. **PASS.**

### 3. F025 — all 9 tables created on fresh DB

Independently verified: wrote a standalone script (not the repo's own test file) that opens a fresh temp SQLite file, calls `run_migrations(conn, "migrations")` against the real `backend/migrations/` directory, and queries `sqlite_master`. Result: exactly `policies, claims, claim_documents, fraud_screenings, assessments, decisions, settlements, claim_state_transitions, admin_overrides` plus the `schema_migrations` bookkeeping table (and SQLite's own auto-generated `sqlite_sequence`, not a defect — an artifact of `AUTOINCREMENT` columns). No missing table, no extra domain table. **PASS.**

### 4. F026 — idempotent second run

Same script: ran `run_migrations` a second time against the same open connection/DB file. No exception raised; `schema_migrations` row count stayed at 9 (not 18). **PASS.**

### 5. F027 — checksum mismatch after edit raises

Copied the real `migrations/` directory to a throwaway temp directory (the actual committed files in the repo were never touched — confirmed via `git status --porcelain migrations/` returning empty after the whole exercise), appended a byte to the tmp copy's `0001_create_policies.sql`, and re-ran `run_migrations` against the **same already-migrated DB file** but pointed at the tampered tmp directory. Result: raised `ConfigError` with message `"Migration '0001_create_policies.sql' failed checksum verification: it was modified after being applied..."`. **PASS.**

### 6. No `IF NOT EXISTS` gaming idempotency

Read all 9 domain migration `.sql` files directly: none use `CREATE TABLE IF NOT EXISTS` or `CREATE INDEX IF NOT EXISTS` — every domain DDL statement is a bare `CREATE TABLE`/`CREATE INDEX`. Idempotency is achieved purely via the `schema_migrations` bookkeeping table's checksum-tracked skip logic in `migration_runner.py`, not by silently swallowing "table already exists" errors. The one `IF NOT EXISTS` in the whole codebase is on the bookkeeping table itself (`migration_runner.py:23`, `_BOOKKEEPING_TABLE_DDL`), which is expected and does not weaken F027 (the bookkeeping table's own re-creation is idempotent by design; the checksum-mismatch detection operates on the domain migration files, and I directly proved in check 5 above that a tampered domain file still raises `ConfigError` rather than being silently skipped or re-applied). **No gaming found.**

`test_running_twice_is_idempotent` in the repo's own test suite makes this same point explicitly in its comment: "If the runner tried to re-execute 0001's CREATE TABLE (no IF NOT EXISTS in domain migrations), this second call would raise `sqlite3.OperationalError`. It must not." — confirmed true by my own independent re-run.

---

## Check-by-check findings — E8-S1 (auth dependency, F085-F088)

### 1. F085/F086/F087/F088 — re-run and assertion quality

Re-ran `backend/tests/integration/api/test_auth_dependency.py` directly: **8 passed**. Read every assertion:

- Every test uses a `handler_calls: list[str]` fixture that the throwaway route handlers append to on entry. `test_invalid_role_value_is_rejected_before_handler_runs`, `test_missing_role_header_is_rejected`, `test_missing_actor_id_header_is_rejected`, and `test_valid_role_without_required_permission_is_forbidden` all assert `handler_calls == []` **in addition to** the status code — this genuinely proves the route handler body never executed, not just that a 401/403 was returned from somewhere (e.g., not a bug where the handler runs, does work, and then still returns 401). This is exactly the trap the task asked me to check for, and it's covered correctly.
- `test_valid_role_and_actor_id_resolves_actor_context` (F085) asserts `response.json() == {"role": "ASSESSOR", "actor_id": "assessor-1"}` and `handler_calls == ["whoami"]` — confirms the ActorContext reaches the handler with the correct role/actor_id.
- 401 tests (F086, F087) assert `response.json()["detail"]["error"]["code"] == "UNAUTHORIZED"` — a real `ApiErrorCode.UNAUTHORIZED.value` from the enum, not a hardcoded string coincidentally matching. Verified `ApiErrorCode.UNAUTHORIZED` exists in `src/types/enums.py` and `auth.py:43` references it via `ApiErrorCode.UNAUTHORIZED.value`.
- 403 test (F088) asserts `error["code"] == "FORBIDDEN"`, matching `ApiErrorCode.FORBIDDEN.value` referenced in `auth.py:92`.
- All error bodies match the uniform envelope from `api-contracts.md` (`{"error": {"code", "message", "details"}}`), nested under FastAPI's `HTTPException.detail`, confirmed both by reading `auth.py`'s `_unauthorized()`/403-raise blocks and by the test assertions' exact key paths (`response.json()["detail"]["error"]["code"]`).

**All four ACs independently confirmed genuine, not status-code-only checks.**

### 2. `require_role` composition and role-vs-permission distinction

`require_role(*allowed_roles)` (`auth.py:76-103`) returns an inner `_check_role` coroutine whose only parameter is `actor_context: ActorContext = Depends(get_actor_context)` — it delegates entirely to `get_actor_context` for header parsing rather than re-implementing it, confirmed by reading the source (no `Header(...)` calls inside `require_role`/`_check_role`). `test_admin_role_is_allowed_through_require_role` confirms a role IN the allowed set (`ADMIN` against `require_role(Role.ADMIN)`) reaches the handler (200, `handler_calls == ["admin-only"]`). `test_valid_role_without_required_permission_is_forbidden` confirms a **valid-but-insufficient** role (`ASSESSOR` against `require_role(Role.ADMIN)`) gets exactly **403**, not 401 — matching api-contracts.md's status table ("401: role missing/not in valid_roles; 403: valid role, but not in the route's allowed set") and E8-S1 AC4 precisely. **Correct.**

### 3. `functools.lru_cache` on `get_app_config`

This is the standard FastAPI-documented pattern for settings objects (cited directly in the module docstring with a link to FastAPI's own docs) and is safe for dependency injection since `AppConfig` is an immutable `frozen=True` dataclass — no risk of cross-request mutation of shared cached state. Confirmed the test file overrides it correctly: `app.dependency_overrides[get_app_config] = lambda: AppConfig(...)` (test_auth_dependency.py:54-57) rather than mutating `os.environ` for the route-level tests. The one test that does exercise the real function (`test_get_app_config_wraps_load_app_config`) explicitly calls `get_app_config.cache_clear()` before and after (in a `try/finally`) to avoid cache pollution between tests — correct hygiene, not a hidden test-order dependency.

### 4. `# noqa: B008` usage

Both occurrences (`auth.py:54`, `auth.py:85`) are on `Depends(...)` used as a function-parameter default value — this is FastAPI's own required idiom (`Depends()` must be a mutable default per FastAPI's design, which is exactly what flake8-bugbear's B008 rule normally flags as a footgun). Confirmed no other lint issue is being masked: `ruff check .` (which includes the bugbear ruleset per this project's config, evidenced by B008 being a recognized code the generator needed to suppress) reports "All checks passed!" with these two suppressions in place, and reading the surrounding lines shows nothing else questionable on either line. **Legitimate use, not masking an unrelated issue.**

### 5. `httpx2` dependency — verified as real, not hallucinated

This required direct empirical verification rather than trusting prior training data, per the task's explicit instruction (httpx2 postdates my knowledge cutoff). Ran directly in `backend/.venv`:

- `pip show httpx2` → **Name: httpx2, Version: 2.12.0, Summary: The next generation HTTP client, Home-page: https://github.com/pydantic/httpx2, Author: Tom Christie**. A real, installed, resolvable package (not a hallucinated name) — same author/lineage as the original `httpx`.
- `pip show starlette` in this environment resolves to **starlette 1.6.0**, and `python -c "from fastapi.testclient import TestClient; print(TestClient.__mro__)"` shows `TestClient` inherits from **`httpx2.Client`** (not the older `httpx.Client`) — confirming this specific environment's `starlette` release has migrated its `TestClient` to build on `httpx2`.
- Directly ran `pytest tests/integration/api/test_auth_dependency.py -v`: **8 passed**, confirming `TestClient` genuinely works end-to-end against a real FastAPI app with this dependency chain — not just that the package imports cleanly.

**Conclusion: `httpx2>=2.0,<3.0` in `backend/requirements.txt` is a real, correctly-resolved, necessary dependency in this environment (required transitively by the installed `starlette`/`TestClient` version), not a hallucinated or broken package name.**

---

## Gate re-run results

| Gate | Command | Result |
|---|---|---|
| pytest + coverage | `pytest --cov=src --cov-report=term-missing -q` | 137 passed, 100% coverage (451/451 stmts) |
| ruff | `ruff check .` | All checks passed |
| mypy | `mypy src/` | Success: no issues found in 17 source files |

## Non-blocking observations (nits)

1. `main.py`'s `create_app()` currently mounts nothing but `/health` — expected and explicitly documented in its own docstring as deferred scope for later groups (E9-S1..S4). Not a defect for this group.
2. The `test_missing_actor_id_header_is_rejected` test in `test_auth_dependency.py` covers a case not explicitly named in E8-S1's four ACs (missing `X-Actor-Id` specifically, as opposed to missing `X-Role`) — this is a reasonable, disclosed extension consistent with api-contracts.md's requirement that both headers are mandatory on every authenticated route, not scope creep.

## Files reviewed

- `specs/stories/E3-S1.md`, `E8-S1.md`
- `specs/design/data-models.md` (§2.1-§2.9 entity tables, §3.1 ActorContext)
- `specs/design/api-contracts.md` (auth headers, error envelope, 401/403 status table)
- `specs/design/folder-structure.md`
- `backend/migrations/0001_*.sql` .. `0009_*.sql` (all 9 read and diffed against data-models.md)
- `backend/src/db/connection.py`, `migration_runner.py`
- `backend/tests/unit/repositories/test_connection.py`, `test_migration_runner.py`, `test_migrations_directory.py`
- `backend/src/api/dependencies/auth.py`
- `backend/src/main.py`
- `backend/src/config/app_config.py` (cross-checked for DB/auth coupling)
- `backend/tests/integration/api/test_auth_dependency.py`
- `backend/requirements.txt` (`httpx2` dependency independently verified installed/importable/functional in `backend/.venv`)
- `git show --stat` for `071de41` and `20e9bcf` (confirmed zero file overlap between the two generator commits)
- `features.json` (F024-F027, F085-F088 updated to `passes: true` following this evaluation)

## Group D — Repository Layer (E3-S2, E3-S3, E3-S4)

**Branch:** `group-d/repositories`, three concurrent-generator commits on top of Group C:
- `d06d378` — E3-S2 policy repository
- `199edf6` — E3-S4 append-only audit repositories
- `f58dd2c` — E3-S3 claim + claim_document repositories

**Concurrency/collision check:** `git show --stat` on each commit confirms disjoint file sets (3 + 7 + 4 = 14 files touched, zero overlap). Cross-checked with `git diff --stat` across the full range: exactly 14 files changed, matching the per-commit sum with no double-counting. All three agents also independently avoided a shared-fixture collision risk: `test_audit_repositories.py`'s own docstring notes it seeds its own claim rows via raw SQL rather than importing the concurrently-developed `ClaimRepository`, since that module might not exist yet in a parallel working tree — deliberate, disclosed isolation, not an accident.

### Milestone note: Repository layer structurally complete

With Group D merged, the persistence stack built across Groups B/C/D is now structurally complete: `backend/src/db/connection.py` (SQLite connection factory with FK enforcement + row_factory), `backend/src/db/migration_runner.py` (checksum-verified sequential migration runner), and all 7 repository modules — `policy_repository.py`, `claim_repository.py`, `claim_document_repository.py`, and the 5 append-only audit repositories (`fraud_screening`, `assessment`, `decision`, `settlement`, `admin_override`). Every one of the 7 new repository files imports only stdlib (`sqlite3`, `json`, `decimal`, `datetime`) plus `src.types.*` — verified by direct grep of every `import`/`from` line in all 7 files, and a targeted `grep -rn "src\.services\|src\.api" src/repositories/` returned zero hits. No repository reaches upward into services or API. Coverage across the whole `src/` tree remains 100% (618/618 statements) after this merge.

### Verdicts

**E3-S2 (policy repository): PASS**
**E3-S3 (claim + claim_document repositories): PASS**
**E3-S4 (append-only audit repositories): PASS**

### Independent verification performed (not just re-reading the generator's own tests)

All checks below were run via a standalone script executed against a real migrated SQLite DB (`run_migrations` against the actual `backend/migrations/*.sql` files, not a mock), re-querying tables directly with `sqlite3.Connection.execute` after every repository call rather than trusting return values.

1. **F028/F029/F030 — policy repository.** Seeded a real `policies` row via direct SQL, then confirmed: `get_by_number()` returns a `Policy` with `sum_insured` as a genuine `Decimal("100000.00")` (checked with `isinstance`, not just equality) and correct `effective_date`/`expiry_date`; a nonexistent policy number returns `None` (no exception); and — the critical check — `is_active_on()` called on the object actually returned by the repository (not a freshly constructed `Policy`) correctly returns `False` for dates outside `[effective_date, expiry_date]` and `True` inside the window. This confirms `PolicyRepository.get_by_number()` reconstructs a fully-functional typed instance, not a data blob with a method that happens to exist on the class.

2. **F031 — claim creation.** Called `create()`, then independently queried `SELECT status, id FROM claims WHERE id=?` directly — confirmed `status='INTAKE'` and the row's `id` matches the returned int, rather than trusting `create()`'s return value alone.

3. **F032 — apply_transition, same-transaction persistence (the critical check).** Called `apply_transition(claim_id, ClaimEvent.ATTACH_CHECKLIST, actor_id="assessor-1")`, then independently re-queried both `claims` (status now `DOCS_PENDING`) and `claim_state_transitions` (exactly one new row, with `from_state=INTAKE`, `to_state=DOCS_PENDING`, `event=ATTACH_CHECKLIST`, `actor_id=assessor-1` all matching). Transaction-handling review: `claim_repository.py:102-119` wraps both the `UPDATE claims` and `INSERT INTO claim_state_transitions` statements inside `with self._connection:` — Python's `sqlite3.Connection` context manager, which commits on clean exit and rolls back on exception. This is explicit transaction handling, not two independent autocommit statements: a crash between the two writes would leave the transaction uncommitted and SQLite's own crash-recovery (journal/WAL) would roll it back on next open, so there is no inconsistent-state window. No design concern found here — the "same transaction" AC text is satisfied for real, not just by sequencing the two statements adjacently.

4. **F033 — invalid event leaves claim unmutated.** Confirmed the code path: `apply_transition()` calls `state_machine.transition(claim, event, actor_id)` (`claim_repository.py:100`) before either SQL statement is reached; `transition()` (`state_machine.py:72-77`) raises `InvalidClaimStateException` and returns before ever assigning `claim.status`, so the `with self._connection:` block containing the two writes is never entered at all on the invalid-event path — confirmed by reading the control flow, not inferred. Empirically: called `apply_transition()` with `DECISION_AUTO_APPROVE` against a claim in `DOCS_PENDING` (not in that state's transition table), confirmed `InvalidClaimStateException` raised, then re-queried the claim row directly — `status` and `updated_at` are byte-for-byte identical (including the full ISO timestamp string) to their pre-call values, and `claim_state_transitions` row count for that claim is unchanged.

5. **F034 — list_by_status_and_product.** Seeded 4 claims with distinct status/claim_type combinations across `INTAKE`/`DOCS_PENDING` and `MOTOR`/`HEALTH`/`LIFE`, then called the method with status-only, claim_type-only, both, and neither filters. Every call returned the exact expected id set (verified via set equality, not just count) — e.g. status-only `DOCS_PENDING` returned exactly `{1,3,4}`, both-filters `DOCS_PENDING+MOTOR` returned exactly `{1,3}`.

6. **F035 — exists_duplicate.** Confirmed `True` for a matching `(policy_id, incident_date)` pair and `False` for a non-matching date. Judgment on the "non-void" interpretation: the repository treats any existing claim row for `(policy_id, incident_date)` as a duplicate regardless of status, including `REJECTED`/`SETTLED` claims — the generator's own docstring (`claim_repository.py:156-161`) and test docstring (`test_claim_repository.py:356-363`) both disclose this explicitly as "the narrowest reading that doesn't invent an undocumented exclusion list," since the story text and `data-models.md` never define which statuses count as "void." I traced the actual consumer chain: `exists_duplicate()` is only exercised by the E4-S3 FNOL-intake flow (Group F, not yet built), which is a new-claim-submission code path. The E7-S2 `reopen()` flow (Group E, not yet built) that creates a `parent_claim_id`-linked sub-claim is a structurally separate service method operating on an already-SETTLED claim, not a new FNOL submission — `data-models.md` sec 2.2 and the E7-S2 story text describe `reopen()` as disputing the same incident, so a reopened sub-claim would be expected to carry the same `(policy_id, incident_date)` as its parent, and would go through `reopen()`/`ClaimRepository.create()` directly rather than through the FNOL intake path that calls `exists_duplicate()`. On that reading, this over-blocking scenario likely does not materialize in practice — but this is an inference about code that does not exist yet (Groups E/F), not something verifiable today. This is not a Group D defect; flagging it as an explicit note for whoever implements E4-S3 (Group F) and E7-S2 (Group E): confirm at that time that `reopen()`'s claim-creation path does not route through `exists_duplicate()`, and that E4-S3's own tests don't assume a status-based exclusion the repository doesn't implement.

7. **F036 — FraudScreening insert-twice.** Called `insert()` twice for the same `claim_id` with different scores (65, then 30), independently queried `SELECT id, score FROM fraud_screenings WHERE claim_id=?` — confirmed 2 distinct ids and both scores (`30` and `65`) present, neither overwritten.

8. **F037 — insert-only structural guarantee, mutation-tested independently.** Rather than trusting the generator's claim to have already exercised this, I repeated the exercise myself: temporarily inserted `def update(self) -> None: pass` into `DecisionRepository` (one of the 5 audit classes), re-ran `test_audit_repositories_insert_only.py`, and confirmed it failed (`AssertionError: found forbidden update()/delete() methods on audit repositories: {'DecisionRepository': {'update'}}`). Then reverted via `git checkout -- src/repositories/decision_repository.py` and re-ran — 2 passed, clean again, with `git status` confirming no residual diff. The guard is a genuine `inspect.getmembers` reflection check on the live class object (`test_audit_repositories_insert_only.py:32-37`), not a static assumption.

9. **F038 — get_latest_assessment.** Inserted 3 assessments for one claim with distinguishable `payable_amount` values (850, 1850, 2850, inserted in that order). `get_latest_assessment()` returned the row with `id` equal to the third inserted id specifically (not merely "an" assessment) and `payable_amount == Decimal("2850")`, matching the last insert. Confirmed the `ORDER BY created_at DESC, id DESC LIMIT 1` tie-break logic in `assessment_repository.py:66` is sound for SQLite's second-level timestamp granularity.

10. **F039 — list_admin_overrides ascending order.** Inserted 3 overrides for one claim, confirmed the returned list's ids are in ascending insertion order (oldest to newest) — the opposite of the "latest" pattern used by the other four audit repositories. Double-checked the SQL directly: `admin_override_repository.py:50` reads `ORDER BY created_at ASC, id ASC`, correctly the inverse direction from `fraud_screening_repository.py:58`, `assessment_repository.py:66`, and `decision_repository.py:50`, all of which use `DESC`.

### Cross-agent consistency (non-blocking observations)

Since three agents worked in parallel on 7 files, I checked for code-smell inconsistencies even though each file individually passes:

- ID-generation pattern: identical across all 7 repositories — `cursor.lastrowid` followed by `assert new_id is not None` before returning. No divergence.
- Decimal handling: `claim_repository.py`'s `create()` defensively re-wraps its input with `str(Decimal(claim_amount))` before storing, while the audit repositories (`assessment_repository.py`, `settlement_repository.py`) call `str(x)` directly on the already-`Decimal`-typed parameter without the extra `Decimal(...)` wrap. Both are correct given their type hints (`Decimal` is the declared parameter type in both cases), but the extra defensive wrap in `claim_repository.py` is a minor stylistic inconsistency worth aligning in a later cleanup pass — not a functional defect.
- Commit style: single-statement inserts across all files use an explicit `self._connection.commit()` call after `execute()`; the one multi-statement write (`ClaimRepository.apply_transition`) uses the `with self._connection:` context-manager form instead. This is a reasonable and consistent convention (single write leads to manual commit, atomic multi-write leads to context manager), not an inconsistency.
- Error-handling style: `PolicyRepository.get_by_number()` and all `get_latest*()` methods return `None` on a miss; `ClaimRepository.apply_transition()` raises `LookupError` for a missing claim id. This divergence is intentional and matches each method's own AC (`get_by_number` AC2 explicitly requires `None`; `apply_transition` has no such "not found" AC and a raised error is the more defensible default for an unexpected missing foreign key). Not flagged as an issue.

No wildly divergent patterns found; the three agents' modules are stylistically coherent enough to read as one codebase.

### Gate re-run results

| Gate | Command | Result |
|---|---|---|
| pytest + coverage | `.venv/Scripts/python.exe -m pytest -q --cov=src --cov-report=term-missing` | 173 passed, 100% coverage (618/618 stmts) |
| ruff | `.venv/Scripts/python.exe -m ruff check .` | All checks passed |
| mypy | `.venv/Scripts/python.exe -m mypy src` | Success: no issues found in 26 source files |

### Files reviewed

- `specs/stories/E3-S2.md`, `E3-S3.md`, `E3-S4.md`, `E7-S2.md` (for the exists_duplicate judgment call), `E4-S3.md` (same)
- `specs/design/data-models.md` sec 2.1-2.9 (all entity fields/constraints/indexes)
- `backend/src/repositories/policy_repository.py`, `claim_repository.py`, `claim_document_repository.py`, `fraud_screening_repository.py`, `assessment_repository.py`, `decision_repository.py`, `settlement_repository.py`, `admin_override_repository.py`
- `backend/src/types/state_machine.py`, `exceptions.py`, `models.py` (confirmed `apply_transition()` delegates to `transition()` rather than reimplementing state logic)
- `backend/src/db/connection.py`, `migration_runner.py`
- `backend/migrations/0001_create_policies.sql`, `0002_create_claims.sql` (cross-checked schema against data-models.md)
- `backend/tests/unit/repositories/test_policy_repository.py`, `test_claim_repository.py`, `test_claim_document_repository.py`, `test_audit_repositories.py`
- `backend/tests/architecture/test_audit_repositories_insert_only.py` (independently mutation-tested by temporarily adding `def update(self): pass` to `DecisionRepository`, confirming failure, then reverting via `git checkout` and confirming a clean pass again)
- `git show --stat` for `d06d378`, `199edf6`, `f58dd2c` (confirmed zero file overlap between the three generator commits: 3+7+4=14 files, matching the full-range diff)
- `features.json` (F028-F039, 12 features, updated to `passes: true` following this evaluation — verified via `git diff` that exactly and only these 12 entries changed)

## Group E — Service Layer (E4-S1, E5-S2, E6-S1, E7-S2, E8-S2)

**Branch:** `group-e/core-services`, five sequential commits on top of Group D:
- `f555167` — E4-S1 FNOL intake service
- `261468b` — E6-S1 assessment service
- `27abf00` — E7-S2 reopen/dispute service
- `fcb2382` — E8-S2 admin override service
- `b6f1d5e` — E5-S2 deterministic fraud scoring engine

**Verification mode for this group:** N/A — pure Python service layer over the Group D repositories, no Docker/API/UI surface. Verified by direct pytest/ruff/mypy execution against `backend/.venv`.

### Verdict: **PASS** (all five stories)

All three layers of the ratchet gate (independent re-run of every AC, static gates, architecture/structural gates, plus the specific duplicate-detection edge case flagged in the Group D report) pass. No blocking defects found.

---

## What was independently re-run

```
cd backend && uv run pytest -x -q
```
Result: **219 passed**, 1 warning (an unrelated upstream `anyio`/`starlette` deprecation notice, not project code).

```
uv run pytest --cov=src --cov-report=term-missing -q
```
Result: **219 passed**, coverage **100%** across the full `src/` tree (762/762 statements), including all five new modules: `src/services/fnol_intake_service.py` (25/25), `src/services/fraud_scoring_engine.py` (51/51), `src/services/assessment_service.py` (27/27), `src/services/reopen_service.py` (15/15), `src/services/admin_override_service.py` (26/26).

```
uv run ruff check .
```
Result: **All checks passed!**

```
uv run mypy src/
```
Result: **Success: no issues found in 32 source files.**

---

## Check-by-check findings

### 1. Architecture — one-way import rule (Service layer)

Grepped every `from`/`import` line in all 5 files in `backend/src/services/`: the only non-stdlib imports are `src.config.fraud_rules_config`, `src.config.assessment_rules_config`, `src.repositories.claim_document_repository`, `src.repositories.claim_repository`, `src.repositories.admin_override_repository`, `src.types.enums`, `src.types.exceptions`, `src.types.models`. Zero occurrences of `src.api`, `src.db`, `src.ui`, or one service importing another service module. This matches `.claude/architecture.md`'s Service-layer rule (may import Types, Config, Repository; never API or UI) exactly.

### 2. E4-S1 — FNOL intake service (F040-F043): PASS

Traced each AC to a real, DB-requerying test in `test_fnol_intake_service.py`:
- **AC1/F040** (motor -> POLICE_FIR + INVOICE, both MISSING) — `test_motor_fnol_creates_claim_and_checklist` re-queries `ClaimDocumentRepository.list_by_claim()` after the call and asserts the exact 2-element document-type set plus `VerificationStatus.MISSING` on both. Genuine.
- **AC2/F041** (health -> HOSPITAL_BILL + DISCHARGE_SUMMARY) and **AC3/F042** (life -> DEATH_CERTIFICATE, exactly one row) — same pattern, both confirmed.
- **AC4/F043** (INTAKE -> DOCS_PENDING) — `test_claim_starts_intake_and_ends_docs_pending` re-fetches the claim via `ClaimRepository.get_by_id()` (not trusting `submit_fnol()`'s return value alone) and additionally queries `claim_state_transitions` directly, asserting exactly one row with `from_state=INTAKE`, `to_state=DOCS_PENDING`, `event=ATTACH_CHECKLIST`. Strong.
- A defensive `UnknownClaimTypeError` test confirms no claim row is created at all for an out-of-domain `claim_type`, via a direct `SELECT COUNT(*)` check.

Read `submit_fnol()` itself (`fnol_intake_service.py:54-98`): checklist lookup happens *before* `ClaimRepository.create()` is called, so an unrecognized claim type genuinely creates zero rows rather than creating-then-failing. Confirmed **no reference to `exists_duplicate()`** anywhere in this file — `specs/design/component-map.md` line 21 places duplicate-detection (E4-S3) in Group F, not this story's scope, so this is correctly out of scope here, not a missing check.

### 3. E5-S2 — deterministic fraud scoring engine (F055-F058): PASS

- **AC1/F055** (ratio 0.85 alone -> 40, not flagged) and **AC2/F056** (ratio 0.85 + 2-day filing -> 65, flagged) — `test_high_ratio_alone_scores_40_and_is_not_flagged` and `test_high_ratio_and_early_filing_scores_65_and_is_flagged` assert exact `total_score`, exact ordered `breakdown` list contents (not just length), and the `flagged` boolean. Both use the **real shipped** `backend/config/fraud-rules.json` via `load_fraud_rules_config`, not a synthetic config — so a regression to the shipped weights/threshold would break these tests, not just an isolated fixture.
- **AC3/F057** (determinism) — `test_scoring_the_same_input_twice_produces_identical_results` asserts `first_result == second_result` (full tuple equality: score + breakdown) **and** `first_result[1] is not second_result[1]` — this second assertion is the correct check that the engine returns a fresh list each call rather than a shared mutable object aliased across calls, which is a stronger determinism guarantee than value-equality alone.
- **AC4/F058** (motor missing FIR -> +15 with rule name) — `test_motor_claim_missing_fir_includes_motor_missing_fir_in_breakdown` asserts the exact `FraudRuleBreakdownEntry(rule_name="MOTOR_MISSING_FIR", weight=15)` is present. Companion tests confirm the rule does NOT fire for a motor claim WITH a verified FIR, and does NOT fire for a non-motor claim missing FIR — both boundary directions covered, not just the positive case.
- Read `score()` itself (`fraud_scoring_engine.py:122-141`): iterates `config.rules` (config-driven order, not a hardcoded rule list) and reads `rule.weight` from config on every triggered rule — confirmed no hardcoded weight literal anywhere in the scoring loop. `is_flagged()` uses `>=` against `config.threshold`; boundary tests (`score == threshold` flags, `threshold - 1` does not) confirm the `>=` semantic matches the AC1 worked example (40 < 60 not flagged) precisely.
- Design note: this engine takes a purpose-built `FraudScoringInput` value object rather than reaching into repositories itself, keeping it a zero-I/O pure function (confirmed by grep: no `sqlite3`/`Connection`/repository import anywhere in this file). Gathering `recent_claim_count_90d`/`has_verified_police_fir` from the DB is correctly deferred to a not-yet-built caller (E5-S3, Group F per the module's own docstring) — consistent with `component-map.md` scoping this file to E5-S2 only.

### 4. E6-S1 — assessment service (F063-F067): PASS

- **AC1/F063** (motor, 40000/100000, deductible 5000, no co-pay -> 35000) and **AC2/F064** (health, 20000, deductible 1000 + 10% co-pay of the *post-deductible* 19000 = 1900 -> 17100) — both asserted exactly, and F064's test explicitly checks the co-pay is computed on `claim_amount - deductible`, not on `claim_amount` or `sum_insured`, matching the AC's worked example precisely (a common off-by-base bug this test would catch).
- **AC3/F065** (life, 200000/150000 -> capped at 150000, no deductions) — confirmed `min(claim_amount, sum_insured)` is applied before deductible/co-pay, via a `ClaimTypeRules(deductible=0, co_pay_pct=0)` life config.
- **AC4/F066** (clamp to 0, never negative) — two tests, one where `after_deductible` alone would already be negative before any co-pay is applied, confirming the clamp happens post-co-pay-computation rather than short-circuiting in a way that could still leak a negative intermediate value into the final result.
- **AC5/F067** (Decimal only, no float) — `test_result_fields_are_all_decimal_instances` uses `isinstance` checks on all 5 result fields (not duck-typing), and `test_source_file_contains_no_float_usage` is a genuine static source-grep for `float(`, `: float`, `-> float` in the actual shipped module file (not the test file), confirmed by reading `assessment_service.py` myself: `Decimal(rules.deductible)` and `Decimal(rules.co_pay_pct)` explicitly convert the config's plain `int` fields through `Decimal(...)`, never through `float`. A `ROUND_HALF_UP` rounding test (`15% of 100.01 = 15.0015 -> 15.00`) confirms the rounding mode is deterministic and disclosed, not an unspecified/arbitrary choice.
- Confirmed no persistence happens in this module (no repository import) — `assess()` returns a local `AssessmentComputation` value object, consistent with the module docstring's statement that mapping onto `AssessmentRepository.insert()` is a separate, later concern.

### 5. E7-S2 — reopen/dispute service (F081-F084): PASS, including the flagged duplicate-detection edge case

- **AC1/F081** (new Claim, `parent_claim_id` set, `status=INTAKE`) — `test_reopen_settled_claim_creates_intake_sub_claim` re-queries via `ClaimRepository.get_by_id()` on the *returned* sub-claim id (not trusting the return value alone), confirming `parent_claim_id`, `status`, `policy_id`, `claim_type`, `incident_date`, and `claim_amount` all match the original claim's fields, carried forward correctly.
- **AC2/F082** (Decision/Settlement/Assessment rows unchanged) — `test_reopen_does_not_mutate_decision_settlement_assessment_rows` snapshots all three rows as full-row dicts before calling `reopen()`, then re-reads and asserts exact dict equality after. This is a genuine mutation check (would catch a partial-field edit), not a mere existence check.
- **AC3/F083** (original -> REOPENED via the state-machine gate) — `test_reopen_transitions_original_to_reopened_via_gate` re-reads the original claim's status directly and additionally asserts exactly one `claim_state_transitions` row with `from_state=SETTLED`, `to_state=REOPENED`, `event=REOPEN`, and the correct `actor_id` — confirming the transition went through `ClaimRepository.apply_transition()` (which is the only code path that writes this audit table) rather than a direct column UPDATE.
- **AC4/F084** (non-SETTLED claim raises `InvalidClaimStateException`) — `test_reopen_non_settled_claim_raises_and_creates_no_sub_claim` asserts both the exception type **and** that the `claims` table row count is unchanged (no orphan sub-claim created) **and** the original claim's status is still `MANUAL_REVIEW` post-exception.

**Duplicate-detection edge case (explicitly checked per the task instruction):** Read `reopen_service.py` in full. `reopen()` calls exactly two repository methods: `ClaimRepository.get_by_id()` and `ClaimRepository.apply_transition()` (to move the original to REOPENED), followed by `ClaimRepository.create(..., parent_claim_id=claim_id)` for the sub-claim. Grepped `reopen_service.py` for `exists_duplicate` — **zero matches**. `ClaimRepository.create()` itself (`claim_repository.py:31-71`) is a plain `INSERT` with no duplicate check inside it either — `exists_duplicate()` is a separate, standalone query method that nothing in this file calls. Cross-checked against `specs/design/component-map.md` line 21: `exists_duplicate()` is wired up only by **E4-S3** (Group F, not yet built), which is the new-FNOL-submission path, structurally distinct from `reopen()`. **Conclusion: the risk flagged in the Group D report does not materialize. `reopen()` cannot trip the duplicate-claim check because it never calls `exists_duplicate()` at all — it creates the sub-claim via a direct, unconditional `ClaimRepository.create()` call.** This is confirmed by reading the code, not inferred from absence of a failing test. Whoever implements E4-S3 (Group F) still needs to independently confirm the FNOL-intake path's own duplicate check behaves correctly for first-time submissions; that remains out of this group's scope.

### 6. E8-S2 — admin override service (F089-F092): PASS

- **AC1/F089** (AdminOverride row inserted with actor/command/reason_code/timestamp) — `test_force_approve_inserts_row_and_moves_status` asserts both the returned `AdminOverride` object's fields **and** a direct `SELECT * FROM admin_overrides` re-query, plus confirms the claim's status actually moved (`AUTO_APPROVED`) via `ClaimRepository.get_by_id()`.
- **AC2/F090** (missing/blank `reason_code` raises typed validation error, no row inserted) — parametrized over `""` and `"   "` (whitespace-only), confirming `_validate_reason_code()`'s `.strip()` check catches both. Asserts `_override_rows(conn) == []` (real empty-table check, not just "no exception with a truthy row count") and that the claim's status is unchanged.
- **AC3/F091** (valid target uses the E1-S2 gate; invalid target raises) — two tests: a positive case confirming a `claim_state_transitions` row is written with the correct `event=ADMIN_FORCE_APPROVE`, and a negative case (`SETTLED` claim, which has no `ADMIN_FORCE_APPROVE` entry in the transition table) confirming `InvalidClaimStateException` propagates and **no** override row is inserted — the override audit row is correctly gated behind a successful transition, not inserted unconditionally.
- **AC4/F092** (concurrent overrides, second fails against stale state) — `test_second_override_against_stale_state_raises` runs two `override()` calls back-to-back against the same claim: the first succeeds (`MANUAL_REVIEW` -> `AUTO_APPROVED`), the second uses a command that *was* valid for the original status but is not valid for the claim's *current* (post-first-call) status, and asserts it raises `InvalidClaimStateException`, that exactly one override row exists afterward (not two), and that the claim is still in the first call's resulting state (no partial/silent double-apply). This is a genuine sequential-request race simulation, not just a single-call negative test relabeled.
- Read `override()` itself (`admin_override_service.py:85-130`): `_validate_reason_code()` runs before any repository call, so a validation failure genuinely can't reach the DB. The `AdminOverride` audit row is inserted only *after* `apply_transition()` returns successfully — confirmed by control flow, not inferred.
- `FORCE_RETRY`'s three-way ambiguity (`RETRY_TO_DOCS_PENDING`/`RETRY_TO_FRAUD_SCREENING`/`RETRY_TO_ASSESSMENT`) is disclosed in the module docstring as an undocumented gap in the AC text, resolved by requiring an explicit `target_event` parameter, raising `ValidationError` if omitted — tested both ways (`test_force_retry_without_target_event_raises_validation_error`, `test_force_retry_with_explicit_target_event_succeeds`). Reasonable, disclosed design decision, not a defect.

### 7. Append-only invariants

None of the 5 service files execute raw SQL directly — confirmed by reading all 5 files in full: every DB interaction goes through a repository method (`ClaimRepository.create()`/`apply_transition()`/`get_by_id()`, `ClaimDocumentRepository.insert()`, `AdminOverrideRepository.insert()`/`list_admin_overrides()`). None of these service files call anything named `update`, `delete`, `edit`, or perform a raw `UPDATE`/`DELETE` statement. Combined with the Group D report's mutation-tested confirmation that the audit repositories (`FraudScreeningRepository`, `AssessmentRepository`, `DecisionRepository`, `SettlementRepository`, `AdminOverrideRepository`) structurally have no `update()`/`delete()` methods at all (`inspect.getmembers` reflection guard), the append-only invariant holds transitively: the Service layer has no code path capable of mutating a fraud screening, assessment, or admin override row in place, even if it wanted to. `ClaimRepository.apply_transition()` (called by `fnol_intake_service`, `reopen_service`, and `admin_override_service`) is the sole exception, and it is an explicitly documented, gated mutation path (the `claims.status` column), not an audit-table mutation.

### 8. Decimal, never float

- `assessment_service.py`: confirmed via `test_source_file_contains_no_float_usage` (re-verified by my own read of the file) — every money value flows through `Decimal(...)` construction and `.quantize(_CENTS, rounding=ROUND_HALF_UP)`; `_CENTS = Decimal("0.01")`.
- `fraud_scoring_engine.py`: `claim_amount`/`sum_insured` in `FraudScoringInput` are typed `Decimal`; the ratio check (`_is_high_claim_to_sum_ratio_triggered`) and round-number check (`_is_round_number_claim_triggered`) both operate on `Decimal` division/modulo, never casting to `float`. Rule `weight`s are plain `int` (point values, not currency), which is correct — `data-models.md` sec 3.2 and the Group B evaluation both confirm weights/threshold are validated as JSON integers, not money fields, so `int` is the correct type here, not a Decimal-discipline violation.
- `fnol_intake_service.py`: `claim_amount: Decimal` parameter, passed straight through to `ClaimRepository.create()` with no float conversion.
- Grepped all 5 files for the literal substrings `float(` / `: float` / `-> float` myself (not just trusting the one test that checks this for `assessment_service.py`) — zero matches across the whole `services/` directory.

### 9. No PII in logs

Grepped all 5 service files for `logg`, `logger`, and `print(` — **zero matches** in any of the 5 files. None of these modules perform any logging at all; they only construct and return typed value objects or raise typed exceptions (whose messages carry structural identifiers like `claim_id`/`variable_name`, not claim narratives, health data, or document content — confirmed by reading every `raise` statement in all 5 files: messages reference claim IDs, reason codes, and event names, never any PII-bearing field). Since there is no logging call anywhere in this layer, there is no PII-in-logs risk to report for Group E.

---

## Gate re-run results

| Gate | Command | Result |
|---|---|---|
| pytest | `pytest -x -q` | 219 passed |
| pytest + coverage | `pytest --cov=src --cov-report=term-missing -q` | 219 passed, 100% coverage (762/762 stmts) |
| ruff | `ruff check .` | All checks passed |
| mypy | `mypy src/` | Success: no issues found in 32 source files |

## Non-blocking observations (nits)

1. `fnol_intake_service.submit_fnol()` and `reopen_service.reopen()` both document, in their own docstrings, that a mid-sequence failure (e.g. a DB error between `apply_transition()` and the following `create()` call) would leave a partially-completed workflow (an original claim marked REOPENED with no sub-claim yet, or a created claim with a partially-attached checklist) since each repository call commits independently rather than being wrapped in one outer transaction. This mirrors the same disclosed pattern noted for `apply_transition()`'s internal two-statement transaction in the Group D report, but is one level up (across separate repository calls, not within one). No AC in E4-S1 or E7-S2 requires cross-call atomicity, and both docstrings disclose the tradeoff explicitly rather than silently. Worth a future story if operational experience shows this edge case matters in practice; not a defect against any current AC.
2. `admin_override_service.py`'s `FORCE_RETRY` disambiguation via an explicit `target_event` parameter is a reasonable, disclosed resolution of a genuine spec gap (the AC text never anticipates `PROCESSING_FAILED` having 3 valid retry destinations), consistent with how prior groups' generators have handled similarly undocumented edges — noted as a positive, not a defect.

## Files reviewed

- `specs/stories/E4-S1.md`, `E5-S2.md`, `E6-S1.md`, `E7-S2.md`, `E8-S2.md`
- `specs/design/component-map.md` (Service/E and Service/F rows, cross-checked E4-S3/E7-S2 scope boundary)
- `specs/design/api-contracts.md`
- `.claude/architecture.md`
- `backend/src/services/fnol_intake_service.py`, `fraud_scoring_engine.py`, `assessment_service.py`, `reopen_service.py`, `admin_override_service.py`
- `backend/src/repositories/claim_repository.py` (re-read in full for the `exists_duplicate()` / `reopen()` interaction check)
- `backend/tests/unit/services/test_fnol_intake_service.py`, `test_fraud_scoring_engine.py`, `test_assessment_service.py`, `test_reopen_service.py`, `test_admin_override_service.py`
- `git log --oneline -- backend/src/services` (confirmed the 5 commit hashes for this group)
- `features.json` (F040-F043, F055-F058, F063-F067, F081-F084, F089-F092 — 21 features — updated to `passes: true` following this evaluation; verified via `git diff --stat` that exactly 42 lines changed, matching 21 features x 2 modified fields (`passes`, `last_evaluated`) each)

## Group F — API & Validation Layer (E4-S2, E4-S3, E5-S1, E5-S3, E9-S4)

**Branch:** `group-f/api-and-validation` @ `8fcc795` ("feat(services,api): Group F -- validation, checklist gate, fraud persistence, admin API"), open as PR #9, not yet merged.

**Verification mode for this group:** Direct pytest/ruff/mypy execution against `backend/.venv` for the service/repository layers, plus real (non-mocked) FastAPI `TestClient` integration tests for the new admin API — no Docker required for this backend-only slice.

### Verdict: **PASS with one flagged defect (non-blocking for merge, blocking for trusting F047/F050 specifically)**

- **E4-S2 (policy-active validation):** PASS for AC1-AC3 (F044-F046). AC4/**F047** ("reason code POLICY_INACTIVE reaches the API layer") is marked `passes: true` in `features.json` but has **no test that actually exercises it** — see defect below.
- **E4-S3 (duplicate FNOL detection):** PASS for AC1-AC2 (F048-F049). AC3/**F050** ("HTTP response status is 409" at the API layer) has the same gap as F047 — see defect below.
- **E5-S1 (document checklist gate):** PASS (F051-F054), fully and genuinely tested, including a mutation test I ran myself.
- **E5-S3 (fraud screening persistence/gating):** PASS (F059-F062), fully and genuinely tested.
- **E9-S4 (admin API):** PASS (F103-F106), fully and genuinely tested via real `TestClient` round trips through router -> service -> repository -> SQLite.

---

## What was independently re-run

```
cd backend && .venv/Scripts/python.exe -m pytest -x -q
```
Result: **261 passed**, 1 warning (unrelated upstream `starlette`/`anyio` deprecation notice).

```
.venv/Scripts/python.exe -m pytest --cov=src --cov-report=term-missing -q
```
Result: **261 passed**, coverage **100%** across the full `src/` tree (956/956 statements), including every new/touched module: `src/api/dependencies/db.py` (12/12), `src/api/error_handlers.py` (16/16), `src/api/routers/admin_router.py` (40/40), `src/api/schemas/admin_schemas.py` (33/33), `src/services/document_checklist_service.py` (31/31), `src/services/fraud_screening_service.py` (33/33), `src/services/fnol_intake_service.py` (31/31, up from 25/25 in Group E).

```
.venv/Scripts/python.exe -m ruff check .
```
Result: **All checks passed!**

```
.venv/Scripts/python.exe -m mypy src/
```
Result: **Success: no issues found in 40 source files.**

Note on environment: `backend/requirements.txt` alone (`pip install -r requirements.txt` into a bare interpreter) fails with `ModuleNotFoundError: No module named 'fastapi'` because the repo relies on the pre-provisioned `backend/.venv` (managed via `uv`, per `backend/uv.lock`) rather than a fresh `pip install`. Not a Group F regression — `requirements.txt` is unchanged by this branch (`git diff main -- requirements.txt` is empty) and `backend/.venv` already has every dependency installed correctly. Flagging only so a future evaluator doesn't waste time on the same false start.

---

## Check-by-check findings

### 1. E4-S2 — policy-active validation (F044-F047)

Read `fnol_intake_service.submit_fnol()` (`backend/src/services/fnol_intake_service.py:86-145`): the policy lookup + `is_active_on()` check runs before `ClaimRepository.create()`, so a lapsed/out-of-window/nonexistent policy genuinely creates zero claim rows, not a created-then-rolled-back one.

- **F044** (lapsed policy -> `PolicyNotActiveException`, no claim row) — `test_lapsed_policy_raises_and_creates_no_claim` re-queries `SELECT COUNT(*) FROM claims` directly after the exception, confirms `0`. Genuine.
- **F045** (incident after expiry -> exception) — `test_incident_after_expiry_raises`. Genuine.
- **F046** (in-window -> proceeds) — `test_incident_within_window_proceeds` confirms `claim.status == DOCS_PENDING`, i.e. the whole downstream pipeline actually ran, not just "no exception." Genuine.
- **F047** (reason code `POLICY_INACTIVE` reaches the API layer) — **marked `passes: true` but not independently verified by any test.** See "Defect" section below.

An extra, unrequested-but-sound test (`test_unresolvable_policy_number_raises_policy_not_active`) confirms an entirely nonexistent `policy_number` is treated the same as an inactive one, since `src/types/exceptions.py` has no separate "policy not found" typed exception — a reasonable, disclosed design choice (documented in the service's own module docstring), not a defect.

### 2. E4-S3 — duplicate FNOL detection (F048-F050)

- **F048** (duplicate `(policy, date)` -> `DuplicateClaimException`, no second claim row) — `test_duplicate_policy_and_date_raises_and_creates_no_second_claim` re-queries `SELECT COUNT(*) FROM claims` and confirms it stays at `1` after the second, rejected submission. Genuine.
- **F049** (distinct incident date on same policy succeeds) — `test_distinct_incident_date_on_same_policy_succeeds` confirms a second, independent claim is actually created (`DOCS_PENDING` status reached). Genuine.
- **F050** (HTTP 409 at the API layer) — **marked `passes: true` but not independently verified by any test.** See "Defect" section below.

The duplicate check (`ClaimRepository.exists_duplicate()`, a Group D repository method) runs after the policy-active check and before `ClaimRepository.create()`, so both E4-S2 and E4-S3 validations are guaranteed to leave behind zero partial claim rows on failure — confirmed by reading the control flow directly, not inferred.

### 3. Defect — F047 and F050 are rubber-stamped: the API-layer mapping they describe is never actually exercised by any test

This is the one substantive finding from this review, and I verified it empirically rather than by inspection alone.

`error_handlers.py`'s `_DOMAIN_EXCEPTION_ERROR_CODES` dict maps `PolicyNotActiveException -> ApiErrorCode.POLICY_INACTIVE` and `DuplicateClaimException -> ApiErrorCode.DUPLICATE_CLAIM`, and `register_error_handlers()`'s `_handle_domain_exception` reads `exc.http_status_code` (422 and 409 respectively) directly off the exception class. By reading the code, both mappings are correct. **But no route in this branch (or on `main`) currently raises either of these two exceptions** — `POST /api/claims`, the only endpoint that would call `submit_fnol()`, is E9-S1 (Group I) and does not exist yet. `grep -rln "PolicyNotActiveException\|DuplicateClaimException" tests/` shows these two exceptions are only referenced in `test_fnol_intake_service.py` (service-layer-only, no HTTP layer involved) and `test_exceptions.py` (asserts `http_status_code` class attributes directly on the exception classes, again with no FastAPI/TestClient involvement at all). There is no `test_error_handlers.py` and no synthetic-route test analogous to how `test_admin_router.py` proves the `InvalidClaimStateException`/`LookupError`/`ValidationError` mappings work end-to-end through a real `TestClient`.

I confirmed this is a real gap, not just an absence-of-evidence concern, via mutation testing: I temporarily swapped the two error-code mapping entries in `src/api/error_handlers.py` (so a `PolicyNotActiveException` would serialize with `code: "DUPLICATE_CLAIM"` and vice versa), re-ran the full suite, and got **261 passed, 0 failed** — zero test failures. Reverted via `git checkout -- src/api/error_handlers.py`, confirmed `git status --short` clean.

This proves F047 ("the response uses reason code POLICY_INACTIVE") and F050 ("the HTTP response status is 409" — status is separately correct since it's read off `http_status_code`, but the broader AC intent of "serialized correctly at the API layer" is what's untested) are currently unverified claims in `features.json`, not verified ones. Per this project's own constraint (CLAUDE.md: "Every acceptance criterion... must have at least one test that references its AC-N identifier"), this is a gap that should be closed — ideally now, with a lightweight synthetic-route test against `register_error_handlers()` (the same pattern `test_admin_router.py` already uses for the three exception types it does cover), rather than deferred silently to E9-S1.

**Impact assessment:** Low severity in practice — I independently confirmed by direct code reading that the mapping is in fact correct as shipped (not just "untested," but "untested and currently correct"). This is not a functional regression today (no route can trigger the broken/untested path yet), and it does not block merging Group F, since nothing in Groups G/H/I depends on this specific mapping being tested yet. However, it should not be treated as done: I recommend the generator either (a) add a `test_error_handlers.py` with a throwaway FastAPI test app + route that raises each of `PolicyNotActiveException`/`DuplicateClaimException` and asserts the full JSON envelope (code + status), mirroring `test_admin_router.py`'s pattern, before E9-S1 lands, or (b) explicitly re-verify F047/F050 as part of E9-S1's own evaluation once `POST /api/claims` exists and can exercise this path for real, and correct `features.json`'s `last_evaluated` semantics at that point (currently E9-S1's own claims-API features, F093-F096, are marked `passes: false`, so the dependency is at least visible).

### 4. E5-S1 — document checklist gate (F051-F054): PASS, verified with my own mutation test

Read `document_checklist_service.py` in full. `check_documents_complete()` computes `required_types <= verified_types` (Python set subset) restricted to `CHECKLISTS[claim.claim_type]` — the single source of truth already seeded by `fnol_intake_service.CHECKLISTS`, reused rather than redefined, so the two can't drift apart.

- **F051** (POLICE_FIR still MISSING -> `False`, stays `DOCS_PENDING`) — genuine, re-queries claim status after the call.
- **F052** (both VERIFIED -> `True`, transitions to `FRAUD_SCREENING`) — genuine, additionally asserts the `claim_state_transitions` row (`event=DOCS_VERIFIED`).
- **F053** (health claim only considers HOSPITAL_BILL/DISCHARGE_SUMMARY) — genuine, verifies partial-then-full completion sequence.
- **F054** (`verify_document()` on an out-of-checklist type raises `ValidationError`) — genuine (e.g. `HOSPITAL_BILL` on a motor claim).

I mutation-tested the core completeness check myself (not trusting the generator's own report of having done this): temporarily changed `all_verified = required_types <= verified_types` to `all_verified = True` in the shipped file, re-ran the test file — **2 of 7 tests failed** (`test_missing_document_returns_false_and_claim_stays_docs_pending`, `test_only_health_document_types_are_considered`), exactly the two that should catch this class of bug. Reverted via `git checkout -- src/services/document_checklist_service.py`, confirmed `git status --short` clean, re-ran — 7/7 passed again. Genuine, non-vacuous tests.

### 5. E5-S3 — fraud screening persistence and gating (F059-F062): PASS

Read `fraud_screening_service.run_fraud_screening()` in full. It re-gathers `FraudScoringInput` fresh from the repositories on every call (never caches across invocations), scores via the pure E5-S2 engine, persists via `FraudScreeningRepository.insert()` (append-only by construction, confirmed structurally insert-only in the Group D review), and gates via `ClaimEvent.FRAUD_FLAGGED`/`FRAUD_CLEARED` — the sole two valid events from `FRAUD_SCREENING`.

- **F059** (threshold-at-scoring-time, not current config) — two tests: one confirms a single call stores the passed-in threshold (42) verbatim; the second (`test_a_later_call_with_a_different_config_does_not_change_the_first_row`) runs two scoring calls with different thresholds (60, then 90) against the same claim and confirms the **first** row's `threshold` column is still `60` after the second call — a genuine retroactive-mutation check, not just "the row I just inserted has the right value."
- **F060/F061** (flagged -> `MANUAL_REVIEW`, unflagged -> `ASSESSMENT`) — both use deterministic zero-rule configs (`_ALWAYS_FLAG_CONFIG`/`_NEVER_FLAG_CONFIG`) to force the boolean outcome independent of the claim's actual data, then re-query claim status directly. Genuine. Note: the AC text for F060 also says "with reason code FRAUD_FLAG" — the service's own docstring discloses this is intentionally deferred, since neither `claim_state_transitions` nor `fraud_screenings` has a `reason_code` column in `data-models.md`; only the future `Decision` row (E6-S2, Group G, not yet built) carries a `ReasonCode`. This is a reasonable, explicitly-disclosed architectural split, not a hidden gap — flagging as a note, not a defect, since assigning `ReasonCode.FRAUD_FLAG` genuinely has nowhere typed to live yet at this layer.
- **F062** (two screenings on one claim both independently queryable) — `test_two_screenings_on_the_same_claim_are_both_independently_queryable` confirms via raw SQL (`SELECT id, flagged ... ORDER BY id`) that both rows persist with distinct ids and correct, non-overwritten `flagged` values, and separately confirms `FraudScreeningRepository.get_latest()` returns the second (most recent) one — checked two ways, not one.

### 6. E9-S4 — admin API (F103-F106): PASS, genuine end-to-end integration tests

`backend/tests/integration/api/test_admin_router.py` builds the real app via `create_app()` and overrides only `get_app_config`/`get_db_connection` with fixture-owned instances — every request in this file exercises the real router -> service -> repository -> SQLite round trip through `TestClient`, not mocks. Confirmed by reading the fixture setup and by re-running the file directly.

- **F103** (`GET /api/admin/claims?status=...&product=...` filters correctly) — seeds 3 claims across 2 statuses x 2 products, confirms exactly 1 matches both filters. Genuine.
- **F104** (`GET /api/admin/payouts` lists every settlement as an audit trail) — seeds one settlement, confirms all fields (`settlement_id`, `claim_id`, `payout_amount` as a canonical decimal string, `payment_reference`) round-trip correctly.
- **F105** (`POST .../override` succeeds, visible in a follow-up `GET .../overrides`) — the strongest test in this router: creates an override via `POST`, captures `override_id` from the response, then makes a separate `GET` request and confirms the same `override_id` appears with matching `admin_actor_id`/`command`/`reason_code`. Genuinely proves persistence across requests, not just an in-memory echo. Companion tests confirm 422 for a blank `reason_code` (Pydantic's own `Field(min_length=1)`, confirmed no override row is inserted), 409 for an invalid transition (`SETTLED` claim, `INVALID_STATE_TRANSITION` error code), 404 for an unknown claim id, and 422 for an unrecognized override command string.
- **F106** (non-ADMIN role -> 403 on every admin route) — `test_assessor_role_is_forbidden_on_every_admin_route` hits all four admin endpoints (`GET /claims`, `GET /payouts`, `POST .../override`, `GET .../overrides`) with `X-Role: ASSESSOR` in a single test and asserts `403` + `error.code == "FORBIDDEN"` on all four. Traced `require_role()` (`src/api/dependencies/auth.py:76-103`, unmodified by this branch) to confirm role-vs-no-role is correctly split: missing/invalid role -> 401 via `get_actor_context` (runs first, as a nested `Depends`), valid-but-insufficient role -> 403 via `require_role`'s own check. Both paths run before any route handler body, since both raise inside dependency resolution.

Money fields (`claim_amount`, `payout_amount`) are serialized as `str`, never JSON numbers — confirmed in `admin_schemas.py` and in the tests' own string-equality assertions (`"75000.00"`, `"35000.00"`), consistent with the project's Decimal-money convention.

### 7. Two touch-ups to already-merged files — confirmed genuinely additive, non-breaking

- **`ValidationError`/`UnknownClaimTypeError` gain an explicit `http_status_code: ClassVar[int] = 422`.** `git diff main -- backend/src/types/exceptions.py` shows this is the only change to that file — no existing class's `http_status_code`, no `EXCEPTION_STATUS_MAP` entry, and no constructor signature changed. `EXCEPTION_STATUS_MAP`'s length stays pinned at exactly 3 (`PolicyNotActiveException`, `DuplicateClaimException`, `InvalidClaimStateException`), so the Group A test that asserts `len(EXCEPTION_STATUS_MAP) == 3` (`test_exception_status_map_is_consistent_with_class_attributes`) still passes unmodified — confirmed by re-running `tests/unit/types/test_exceptions.py` in isolation (10/10 passed). Both classes already existed on `main` with the default inherited `http_status_code = 500` from `DomainException`; this change only makes their already-intended-422 status explicit and correct for `error_handlers.py` to consume directly. Non-breaking.
- **`get_connection()` gains `check_same_thread: bool = True` (keyword-only, defaulting to the pre-existing behavior).** `connection.py`'s `sqlite3.connect(db_path, check_same_thread=check_same_thread)` call is the only change; every existing call site that omits the new parameter is unaffected. I did not just trust this — I ran the branch's own `test_get_connection_defaults_to_check_same_thread_true` test, which positively demonstrates the old behavior still holds (a cross-thread `execute()` call on a connection opened with the default still raises `sqlite3.ProgrammingError`, exactly as it would have pre-Group-F), alongside a companion test proving `check_same_thread=False` genuinely allows cross-thread use (used only by `src.api.dependencies.db.get_db_connection`'s single shared connection, needed because FastAPI dispatches sync `Depends` callables via `anyio.to_thread`, a worker thread that can differ request to request). This is real regression-proof evidence, not just a read of the diff. Non-breaking.

Grepped for every call site of `submit_fnol()` and `get_connection()` in `backend/src/` and `backend/tests/`: no other production or test code calls `submit_fnol()` with the old `policy_id=` keyword (the signature change to `policy_number` is clean — no other caller exists anywhere in the codebase yet, confirmed via `grep -rn "submit_fnol"`; `reopen_service.reopen()` creates its sub-claim via a direct `ClaimRepository.create()` call and never calls `submit_fnol()` at all, matching the Group E report's own finding).

### 8. Money math, PII, and architecture — confirmed clean

- **Decimal-only money math:** grepped every file changed/added by this branch (`git diff main...group-f/api-and-validation --stat`) for `float(`, `: float`, `-> float` — zero matches. Admin API money fields are `str` (canonical decimal strings), never JSON numbers, per `admin_schemas.py`'s own docstring and the integration tests' string-equality assertions.
- **No PII in logs:** grepped the entire `backend/src/` tree (not just this branch's new files) for `logging`, `logger.`, `print(` — zero matches anywhere in the codebase. There is no logging call at all in this backend yet, so there is no PII-in-logs risk to report for this group specifically (or any prior group).
- **One-way imports:** `admin_router.py` imports only `src.api.*`, `src.repositories.*`, `src.services.admin_override_service`, `src.types.*` — no reverse dependency on `src.ui`. `document_checklist_service.py`/`fraud_screening_service.py` import only `src.repositories.*`, `src.config.fraud_rules_config`, `src.types.*` — no `src.api` import from the Service layer. Matches `.claude/architecture.md`'s one-way layering rule.

---

## Gate re-run results

| Gate | Command | Result |
|---|---|---|
| pytest | `pytest -x -q` | 261 passed |
| pytest + coverage | `pytest --cov=src --cov-report=term-missing -q` | 261 passed, 100% coverage (956/956 stmts) |
| ruff | `ruff check .` | All checks passed |
| mypy | `mypy src/` | Success: no issues found in 40 source files |

## Non-blocking observations (nits)

1. F047/F050 test-coverage gap — see the "Defect" section above. Recommend closing this before or as part of E9-S1, either with a standalone `test_error_handlers.py` now or by explicitly re-verifying these two `features.json` entries once `POST /api/claims` exists.
2. `ClaimRepository.exists_duplicate()`'s "any row counts as a duplicate regardless of status" interpretation (flagged as an open question in the Group D report) is confirmed here to behave as expected for this group's own scope — `submit_fnol()` is the only caller, and it is only ever invoked for genuinely new FNOL submissions in this branch's tests. The Group D report's specific worry (whether `reopen()`'s sub-claim creation could trip this check) remains correctly moot, since `reopen()` still calls `ClaimRepository.create()` directly and never `exists_duplicate()` — reconfirmed by grep in this review.
3. `requirements.txt`'s `httpx2` dependency (flagged and independently verified as real/necessary in the Group C report) continues to resolve correctly in this branch's `.venv`; unrelated to Group F's own changes.

## Files reviewed

- `specs/stories/E4-S2.md`, `E4-S3.md`, `E5-S1.md`, `E5-S3.md`, `E9-S4.md`
- `specs/design/data-models.md`, `api-contracts.md` (Admin API section, error envelope, error table)
- `.claude/architecture.md`, `.claude/skills/code-gen/SKILL.md`
- `backend/src/services/fnol_intake_service.py` (diffed against Group E's version), `document_checklist_service.py`, `fraud_screening_service.py`
- `backend/src/api/routers/admin_router.py`, `schemas/admin_schemas.py`, `error_handlers.py`, `dependencies/db.py`, `dependencies/auth.py` (re-read, unmodified)
- `backend/src/repositories/policy_repository.py`, `claim_repository.py`, `claim_document_repository.py` (all diffed against Group D's versions)
- `backend/src/types/exceptions.py`, `backend/src/db/connection.py` (both diffed against `main`)
- `backend/src/main.py`
- `backend/tests/unit/services/test_fnol_intake_service.py`, `test_document_checklist_service.py` (mutation-tested), `test_fraud_screening_service.py`
- `backend/tests/unit/repositories/test_claim_repository.py`, `test_policy_repository.py`, `test_claim_document_repository.py`, `test_connection.py`
- `backend/tests/unit/api/dependencies/test_db.py`
- `backend/tests/unit/types/test_exceptions.py` (re-run in isolation, confirmed unmodified and still passing)
- `backend/tests/integration/api/test_admin_router.py`
- `backend/src/api/error_handlers.py` (mutation-tested — swapped `POLICY_INACTIVE`/`DUPLICATE_CLAIM` mapping entries, confirmed 0 of 261 tests catch it, reverted via `git checkout`, confirmed clean)
- `features.json` (F044-F050, F051-F054, F059-F062, F103-F106 — 19 features — currently marked `passes: true`; F047 and F050 specifically should be treated as unverified pending the fix recommended above)

## Group G (partial — backend only: E6-S2, E9-S2)

**Branch:** `group-g/decision-and-documents-api` (see commit landed alongside this report entry), opened as a PR, not yet merged.

**IMPORTANT — verification mode for this entry: this is a GENERATOR SELF-CHECK, not an independent evaluator pass.** The session that wrote this code ran under a coordinator's fork with a hard constraint against spawning further subagents, so no separate evaluator agent reviewed this group before this entry was written — the same gap Group F's report flagged and the coordinator had to close after the fact. This entry should be treated with correspondingly lower confidence than the Group D/E/F sections above, which were all written by an agent that did not write the code it reviewed. **Recommend an independent evaluator pass on this branch before merging**, same as was done for Group F.

### What was run (self-reported, not independently reproduced by a second agent)

```
cd backend && uv run pytest -x -q            # 283 passed
uv run pytest --cov=src --cov-report=term-missing -q   # 283 passed, 100% coverage (1052/1052 stmts)
uv run ruff check .                          # All checks passed!
uv run mypy src/                             # Success: no issues found in 43 source files
```

### E6-S2 — decision engine (F068-F072)

`backend/src/services/decision_engine.py` (new). A pure `decide(payable_amount, flagged, auto_approve_ceiling) -> DecisionComputation` function plus a `run_decision(conn, claim_id, assessment_config, decided_by="system")` persistence+gating entrypoint.

- **F068** (payable_amount == 0 -> REJECT/ZERO_PAYABLE_AMOUNT): tested both at the pure-function level and end-to-end (motor claim with `claim_amount` set equal to the 5000 deductible, so `payable_amount` computes to exactly 0; confirms the persisted `Decision.outcome`/`reason_code` and the claim's transition to `REJECTED`).
- **F069** (flagged + nonzero -> MANUAL_REVIEW/FRAUD_FLAG): tested at the pure-function level directly. The end-to-end version required a deliberate test-design workaround, disclosed in both the test file and `claude-progress.txt`: `fraud_screening_service` already gates a *first* flagged screening straight to `MANUAL_REVIEW`, never `ASSESSMENT`, so a claim can only carry `flagged=True` while sitting in `ASSESSMENT` via a *later* re-screening. The integration test simulates this by inserting a second `FraudScreening` row directly via the repository rather than through a real retry flow (Group H's `retry_pipeline()` doesn't exist yet). This is a legitimate simulation of a real future code path, not a fabricated scenario, but it has not been independently checked against `specs/stories/E6-S2.md`'s exact intent by a second reader.
- **F070/F071** (unflagged, at-or-below vs. above the 50000 ceiling -> AUTO_APPROVE/AUTO_APPROVED_LOW_RISK vs. MANUAL_REVIEW/HIGH_VALUE_REVIEW): tested both at the pure-function level (including the boundary value, exactly at the ceiling) and end-to-end, with the end-to-end AUTO_APPROVE case additionally asserting the persisted `Assessment.payable_amount` value.
- **F072** (append-only Decision row, `decided_by` recorded correctly): tested with both the default `"system"` value and an explicit assessor actor id string, plus a reflection check (`DecisionRepository` exposes no `update`/`delete`, mirroring the Group D pattern) and one additional self-added test (double-decision on an already-decided claim raises `InvalidClaimStateException` via `apply_transition()`, proving no silent double-apply) — this last test goes beyond the literal AC text but follows the same "no silent double-apply" pattern Group E's admin-override AC4 established.

Precedence rule implemented: zero payable amount always rejects regardless of `flagged` (AC1 has no `flagged` input in its own statement, so it must win outright); a nonzero flagged claim always goes to manual review regardless of the ceiling (AC2 has no ceiling comparison in its own statement); only once both are ruled out does the ceiling decide AC3 vs. AC4. This precedence was inferred from reading all four ACs together, not stated explicitly in the story — worth a second reader's confirmation.

`run_decision()` also does something E6-S1 itself never did: it's the first code path in the whole codebase to call `AssessmentRepository.insert()`. Disclosed tradeoff in the docstring: the `Assessment` row is inserted before the `apply_transition()` gate check, so a claim that's already left `ASSESSMENT` (e.g. a double-call) will still get an extra `Assessment` row inserted even though the subsequent transition (and `Decision` insert) correctly fails — matching the same cross-call-atomicity tradeoff already disclosed in `fnol_intake_service` and `reopen_service` in prior groups' reports.

### E9-S2 — document verification API (F097-F099)

`backend/src/api/routers/documents_router.py` + `backend/src/api/schemas/documents_schemas.py` (both new), plus one addition to the existing `document_checklist_service.py`: `list_outstanding_documents(conn, claim_id) -> list[DocumentType]`.

- **F097** (`GET /api/claims/documents/pending` lists only DOCS_PENDING claims with outstanding items): tested with a positive case (fresh motor claim, confirms both `POLICE_FIR`/`INVOICE` listed as outstanding) and a negative case (a `SETTLED` claim inserted directly is confirmed absent from the response).
- **F098** (`PATCH .../documents/{type}` reflects the update; auto-advances to `FRAUD_SCREENING` once complete): tested end-to-end verifying one document at a time, confirming `claim_status` stays `DOCS_PENDING` after the first and flips to `FRAUD_SCREENING` after the second, then confirms the claim disappears from the pending-queue response afterward. Two additional error-path tests: an out-of-checklist document type (422/`VALIDATION_ERROR`, reusing E5-S1's existing `verify_document()` validation) and an unknown claim id (404/`NOT_FOUND`).
- **F099** (`CUSTOMER` role -> 403 on both routes): one test hits both endpoints with `X-Role: CUSTOMER` and asserts 403/`FORBIDDEN` on both, following the exact `test_admin_router.py` F106 pattern (`response.json()["detail"]["error"]["code"]`, since `require_role()`'s 403 is a raw `HTTPException`, not a `DomainException` routed through `error_handlers.py`).

Disclosed scope limitation, not a defect: the PATCH endpoint only accepts `"VERIFIED"` as a request value and rejects anything else (including `"MISSING"`) with `ValidationError`/422, because no `ClaimDocumentRepository` method exists to flip a row back to `MISSING` — inventing one wasn't requested by any AC in E5-S1 or E9-S2, so none was added. A test confirms this rejection explicitly (also closes what would otherwise have been a 1-line coverage gap in `documents_router.py`).

Both routes require `ASSESSOR` or `ADMIN` per `specs/design/api-contracts.md`'s "Document Verification API" section (not just `ASSESSOR` alone) — matches the design doc, not an invented requirement.

### What was NOT independently checked (gaps versus the Group D/E/F review process)

- No second agent re-ran the gates from a fresh checkout.
- No mutation testing was performed against `decide()`'s precedence logic or `check_documents_complete()`'s reuse in the pending-queue path (Group F's evaluator mutation-tested the underlying `check_documents_complete()` itself; this session did not repeat that, relying on Group F's prior result since the function itself is unmodified).
- The precedence-ordering inference for `decide()` (described above) has not been cross-checked by a second reader against `specs/stories/E6-S2.md` or BRD section 11 beyond this session's own reading.
- `features.json` was updated directly by this same session (F068-F072, F097-F099 set to `passes: true`) rather than by a separate evaluator, same caveat as Group F's F047/F050 situation but applying to all 8 features in this entry, not just 2.

## Gate re-run results — Group G (self-reported)

| Gate | Command | Result |
|---|---|---|
| pytest | `uv run pytest -x -q` | 283 passed |
| pytest + coverage | `uv run pytest --cov=src --cov-report=term-missing -q` | 283 passed, 100% coverage (1052/1052 stmts) |
| ruff | `uv run ruff check .` | All checks passed |
| mypy | `uv run mypy src/` | Success: no issues found in 43 source files |

## Files touched — Group G

- `backend/src/services/decision_engine.py` (new)
- `backend/src/api/routers/documents_router.py` (new)
- `backend/src/api/schemas/documents_schemas.py` (new)
- `backend/src/services/document_checklist_service.py` (added `list_outstanding_documents()`)
- `backend/src/main.py` (mounted `documents_router`, updated module docstring)
- `backend/tests/unit/services/test_decision_engine.py` (new)
- `backend/tests/integration/api/test_documents_router.py` (new)
- `backend/tests/unit/services/test_document_checklist_service.py` (added `list_outstanding_documents` coverage)
- `features.json` (F068-F072, F097-F099 — 8 features — set to `passes: true` by this same session; recommend independent re-verification before treating as trustworthy as prior groups')
- `claude-progress.txt` (Session 9 entry appended)

## Group G — independent evaluator pass (2026-09-07)

**Branch reviewed:** `group-g/decision-and-documents-api` @ `3abb62b`, checked out fresh from `origin`. This section is an independent re-verification of the generator's self-check above (lines 734-800), run by a separate agent that did not write the code under review, closing the gap that section 734 explicitly flagged.

### Gate results (independently reproduced, not copied from the self-report)

Ran via `backend/.venv/Scripts/python.exe` (the anaconda system Python on this machine lacks project deps; the repo's own `.venv` has them):

| Gate | Result |
|---|---|
| `pytest -x -q` | **283 passed**, 0 failed |
| `pytest --cov=src --cov-report=term-missing -q` | **283 passed, 100% coverage (1052/1052 stmts)**, no file below 100% |
| `ruff check .` | All checks passed |
| `mypy src/` | Success: no issues found in 43 source files |

All four gate numbers match the generator's self-report exactly. No discrepancy found.

### E6-S2 — decision engine (F068-F072): PASS

Read `backend/src/services/decision_engine.py` in full and confirmed the precedence chain in `decide()` (lines 52-75) matches AC1-AC4 verbatim: zero payable amount checked first regardless of `flagged`, then `flagged` checked regardless of ceiling, then ceiling comparison (`<=` — confirmed AC3's "at or below" boundary is inclusive).

Specifically verified the four-way precedence case the coordinator asked about — nonzero payable_amount, `flagged=True`, AND above the ceiling — which has **no dedicated test in the suite** (`test_decision_engine.py` only exercises flagged-below-ceiling at line 103, and unflagged-above-ceiling at line 117; the flagged-AND-above-ceiling combination is untested). I wrote and ran it directly against the installed code:

```python
decide(Decimal("75000.00"), flagged=True, auto_approve_ceiling=Decimal("50000"))
# -> DecisionComputation(outcome=MANUAL_REVIEW, reason_code=FRAUD_FLAG)
```

Confirmed: fraud flag correctly wins over the ceiling (MANUAL_REVIEW/FRAUD_FLAG, not HIGH_VALUE_REVIEW). Also re-confirmed zero-payable wins over a flag (`decide(Decimal("0.00"), flagged=True, ...)` -> REJECT/ZERO_PAYABLE_AMOUNT). Both match the stated precedence and the code's own docstring. **This is a real, if narrow, test-coverage gap** — the behavior is correct, but nothing in the committed suite would catch a regression that made `flagged` and the ceiling check swap order in this specific combination (a plausible off-by-one refactoring mistake). Not blocking given 100% line coverage exists and the pure function is 4 lines of trivial `if`/`return`, but worth adding before this logic gets any more complex.

Money math: confirmed `decision_engine.py` uses `Decimal` throughout (`_ZERO = Decimal("0")`, `Decimal(assessment_config.auto_approve_ceiling)`), zero `float(...)` calls, zero float literals compared against money values. Grep for `print(`/`logging.`/`logger.` in the file returned nothing — no PII or claim-data logging risk introduced.

`run_decision()` (lines 78-135): confirmed it is genuinely the first call site of `AssessmentRepository.insert()` in the codebase (E6-S1's `assess()` is pure/computation-only, never persists). Confirmed the disclosed cross-call-atomicity tradeoff (docstring lines 93-98: the Assessment row can be inserted even when the subsequent `apply_transition()` gate then fails, leaving an extra Assessment row but no Decision row) is **not new or unique to this group** — the same tradeoff, in the same words, exists in `fnol_intake_service.py` (lines 39-44) and `reopen_service.py` (line 43) from prior groups, confirmed by grep. This is consistent, disclosed technical debt across the codebase, not something Group G introduced silently.

Append-only Decision row: `DecisionRepository` (pre-existing, Group D) exposes only `insert()`/`get_latest()`, no `update`/`delete` — confirmed by reading the file directly, not just trusting the reflection test. `decided_by` is recorded verbatim as passed (`"system"` default or an actor id string), matching AC5.

Test suite quality check: all 5 `TestDecidePure` tests exercise the pure function directly with meaningful assertions (not rubber-stamped — e.g. `test_unflagged_at_ceiling_auto_approves` specifically hits the inclusive boundary at exactly 50000). The `TestRunDecision*` classes exercise the full persistence+gating path end-to-end through a real migrated SQLite DB (not mocked), asserting both the returned `Decision` and the claim's post-transition status. `TestRunDecisionInvalidState` confirms a double-decision run raises `InvalidClaimStateException` rather than silently re-applying — good defensive test, matches the "no silent double-apply" pattern from Group E's admin-override work.

### E9-S2 — document verification API (F097-F099): PASS

Read `documents_router.py`, `documents_schemas.py`, and the `document_checklist_service.py` diff in full.

- **F097**: `GET /api/claims/documents/pending` — confirmed role dependency is `require_role(Role.ASSESSOR, Role.ADMIN)` (line 42), matching `specs/design/api-contracts.md:159` (`Auth: require_role(ASSESSOR, ADMIN)`) exactly — not a deviation. `list_outstanding_documents()` (new in `document_checklist_service.py`) correctly reuses the same `CHECKLISTS`/verified-set derivation as the pre-existing `check_documents_complete()` rather than re-implementing it. Test confirms both a positive case (outstanding docs listed) and a negative case (SETTLED claim excluded).
- **F098**: `PATCH /api/claims/{id}/documents/{type}` — confirmed the auto-advance to `FRAUD_SCREENING` happens by delegating to the pre-existing `check_documents_complete()` (which itself applies the `DOCS_VERIFIED` transition), not a new/duplicated transition path. Integration test verifies the claim stays `DOCS_PENDING` after the first of two documents and flips to `FRAUD_SCREENING` after the second, then confirms it drops out of the pending queue — genuine round-trip through `TestClient`, not mocked.
- **F099**: independently traced the 403 code path — `require_role()` (`src/api/dependencies/auth.py:76-103`) raises `HTTPException(status_code=403, ...)` for a role not in the allowed set, and separately requires a valid actor context first (401 for missing/malformed auth), so CUSTOMER correctly gets 403, not 401. Confirmed by reading the dependency chain directly, and the existing `test_customer_role_is_forbidden_on_both_routes` test checks `response.json()["detail"]["error"]["code"] == "FORBIDDEN"` on both routes.

Verified against the design spec (`specs/design/api-contracts.md:176-197`) that the PATCH endpoint's error table (404/`NOT_FOUND`, 422/`VALIDATION_ERROR`, 403/`FORBIDDEN`) is fully implemented and tested — all three error paths have a dedicated test in `test_documents_router.py`.

One spec-wording note, not a defect: `api-contracts.md:177` describes the PATCH endpoint's purpose as "toggle a checklist item to `VERIFIED`/`MISSING`", but the implementation only accepts `"VERIFIED"` (rejects `"MISSING"` with 422). This is already disclosed in the router's own docstring and was flagged in the generator's self-report (line 770); confirmed the underlying reason is real — `ClaimDocumentRepository` has no method to revert a row to `MISSING`, and neither E5-S1 nor E9-S2's ACs ask for one. The design-doc prose is arguably aspirational/imprecise here rather than the code being wrong; no AC is violated. Not blocking.

### Verdict

**PASS** for both E6-S2 and E9-S2. All 8 features (F068-F072, F097-F099) independently confirmed as genuine, non-rubber-stamped passes. Gates independently reproduced and match the self-report exactly (283 tests, 100% coverage, ruff clean, mypy clean). No regressions found in previously-passing Group A-F features (full suite run, not just the new tests, all 283 passed).

**One non-blocking finding to log:** the `flagged=True` AND `payable_amount` above ceiling combination in `decide()` has no dedicated regression test, even though the behavior is currently correct (independently verified above). Recommend adding one test case to `TestDecidePure` before this function's precedence logic is extended further (e.g. when Group H's retry/re-decision work lands).

No production code changes were made by this evaluation pass; `features.json` timestamps were refreshed for F068-F072 and F097-F099 (all remain `passes: true`).
