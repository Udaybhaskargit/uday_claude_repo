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
