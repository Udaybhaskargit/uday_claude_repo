# Iteration Log
<!-- Append-only. Do not edit or delete entries. -->

<!-- ENTRY FORMAT — Append one block per group iteration:

## Group {ID} — {Group Name}
- **Date:** {ISO 8601}
- **Status:** PASS | FAIL (attempt {N} of 3) | BLOCKED
- **Stories:** [{story IDs}]
- **Mode:** full | lean | solo | turbo
- **Summary:** {1-2 sentence description of what happened}
- **Checks:** {N} API, {N} Playwright, {N} design passed
- **Coverage:** {N}% (baseline: {N}%)
- **Learned Rules Applied:** [{rule numbers}]

### Micro-DAG (if agent team was used)
- Phase 1 (Independent): [{teammate IDs}]
- Phase 2 (Depends on Phase 1): [{teammate IDs}]
- Phase 3 (Integrators): [{teammate IDs}] (shared files: [{paths}])

-->

## Group A — Domain Foundation (Types layer)
- **Date:** 2026-09-06T18:11:32Z
- **Status:** PASS
- **Stories:** [E1-S1, E1-S2, E1-S3]
- **Mode:** full
- **Summary:** Implemented backend/src/types/ from scratch (enums, dataclass models, typed
  exceptions with HTTP-status mapping, and the centralized claim state-machine transition gate).
  Generator wrote 73 tests first (TDD), then implementation; evaluator independently re-ran all
  gates rather than trusting the self-report and traced every acceptance criterion in E1-S1/S2/S3
  to a specific failing-on-violation assertion. No blocking defects.
- **Checks:** 0 API, 0 Playwright, 0 design (Group A has no API/UI surface yet) — 4 architecture
  checks passed (layering, typing, folder structure, state-mutation gate), all 13 features (F001-F013)
  verified against acceptance criteria.
- **Coverage:** 100% (baseline: 0%)
- **Learned Rules Applied:** none (none exist yet)

### Notes
- Generator commit: `d00d4a5` "feat(types): implement Group A domain types layer (E1-S1, E1-S2, E1-S3)"
- Evaluator report: `specs/reviews/evaluator-report.md` (Group A section)
- Three generator deviations reviewed and accepted by evaluator as non-blocking: `enum.StrEnum`
  instead of `class X(str, Enum)` (required by ruff UP042 on py312 target); substituted
  `DOCS_VERIFIED` for the story text's non-canonical `SUBMIT_FNOL` event name in the terminal-state
  negative test (preserves AC intent); added `Policy.is_active_on(date)` ahead of its Group D story
  since it's already specified in data-models.md sec 2.1 and is a pure, zero-dependency method.
- Single-agent implementation (no cross-story file conflicts requiring a micro-DAG — E1-S1/S2 share
  models.py and E1-S1/S3 share enums.py, but the generator wrote both in one pass as a 3-story unit).
- Landed via branch `group-a/domain-types` + PR (capstone PR-only-merge rule), not a direct commit
  to main.

## Group B — Business Rule Configuration (Config layer)
- **Date:** 2026-09-06T00:00:00Z
- **Status:** PASS
- **Stories:** [E2-S1, E2-S2, E2-S3]
- **Mode:** full
- **Summary:** Implemented backend/src/config/ (fraud rule config loader, assessment rule config
  loader, AppConfig) plus the two declarative JSON config files. Generator extended Group A's bare
  `ConfigError` with an optional `variable_name` kwarg (additive, non-breaking). Evaluator
  independently re-ran all gates, verified the shipped JSON config files directly (not just
  in-memory test fixtures), mutation-tested the new import-layering test by injecting a temporary
  forbidden import, and confirmed the on-disk-edit-is-picked-up-on-reload behavior (E2-S1 AC4) with
  no module-level caching. No blocking defects.
- **Checks:** 0 API, 0 Playwright, 0 design (no API/UI surface yet) — architecture checks passed
  (Config imports only Types; one-way import rule mutation-tested), all 10 features (F014-F023)
  verified against acceptance criteria.
- **Coverage:** 100% (baseline: 100%) — full src/ tree (types + config), 359/359 statements
- **Learned Rules Applied:** none (none exist yet)

### Notes
- Generator commit: `51ff8b9` "implement Group B config layer" (backend/config/fraud-rules.json,
  assessment-rules.json; backend/src/config/{app_config,fraud_rules_config,assessment_rules_config}.py)
- Evaluator report: `specs/reviews/evaluator-report.md` (Group B section)
- Non-blocking observation from evaluator: neither config loader rejects negative/zero weights or
  thresholds structurally, since no AC requires it — left as-is.
- Landed via branch `group-b/config-layer` + PR (capstone PR-only-merge rule), not a direct commit
  to main.

## Group C — Persistence Bootstrap + Auth Boundary (Repository + API, first slice)
- **Date:** 2026-09-07T00:00:00Z
- **Status:** PASS
- **Stories:** [E3-S1, E8-S1]
- **Mode:** full
- **Summary:** Two independent generator agents ran in parallel on disjoint files (no shared-file
  conflict): one built backend/migrations/ (9 numbered SQL files) + backend/src/db/ (connection
  factory, checksum-verified idempotent migration runner); the other built
  backend/src/api/dependencies/auth.py (X-Role/X-Actor-Id -> ActorContext, require_role(*roles))
  plus a minimal backend/src/main.py app factory. Evaluator independently ran the real migration
  runner against a fresh temp SQLite DB (not just the test suite) to directly confirm all 9 tables,
  idempotency, and checksum-mismatch detection, and confirmed the auth dependency's 401/403 tests
  assert the protected handler body never executes (not just status code). No blocking defects.
- **Checks:** 0 API-contract checks yet (no business routers exist), 0 Playwright, 0 design —
  architecture checks passed (Repository imports only Types/Config; API auth dependency composes
  correctly), all 8 features (F024-F027, F085-F088) verified.
- **Coverage:** 100% (baseline: 100%) — full src/ tree, 451/451 statements
- **Learned Rules Applied:** none (none exist yet)

### Micro-DAG
- Phase 1 (Independent, no cross-story file conflicts): [E3-S1 generator, E8-S1 generator] — ran
  concurrently on the same branch, disjoint file ownership (backend/migrations/+src/db/ vs.
  backend/src/api/+src/main.py), no integrators needed.

### Notes
- Commits: `071de41` (E3-S1 migrations), `20e9bcf` (E8-S1 auth dependency)
- Evaluator report: `specs/reviews/evaluator-report.md` (Group C section)
- Environment note: `backend/requirements.txt` now pins `httpx2>=2.0,<3.0` (a newer major-version
  successor to `httpx` that this environment's `starlette` 1.6.0 `TestClient` requires) — confirmed
  real and correctly resolved by both the generator and an independent evaluator check
  (`pip show httpx2`), not a hallucinated package.
- Non-blocking flag from generator: `pyproject.toml`'s ruff config could add
  `extend-immutable-calls = ["fastapi.Depends", "fastapi.Header"]` under
  `[tool.ruff.lint.flake8-bugbear]` to avoid per-line `# noqa: B008` on future FastAPI routers —
  deferred since `pyproject.toml` is a shared file and this is cosmetic, not blocking.
- Landed via branch `group-c/migrations-and-auth` + PR (capstone PR-only-merge rule), not a direct
  commit to main.

## Group D — Persistence Layer complete (Repository layer, MILESTONE)
- **Date:** 2026-09-07T00:00:00Z
- **Status:** PASS
- **Stories:** [E3-S2, E3-S3, E3-S4]
- **Mode:** full
- **Summary:** Three generator agents ran fully in parallel on disjoint files: policy repository,
  claim + claim_document repositories (apply_transition delegates to the E1-S2 state machine gate,
  atomic UPDATE+INSERT via `with connection:`), and the five append-only audit repositories
  (fraud_screening, assessment, decision, settlement, admin_override — no update()/delete() on any).
  This completes the Repository layer (backend/src/db/ + backend/src/repositories/, 7 modules).
  Evaluator independently re-queried the live SQLite DB after every repository call (not trusting
  return values alone), traced the transaction-atomicity claim in claim_repository.py:102-119,
  independently repeated the insert-only mutation test on a different class (DecisionRepository)
  than the generator used, and confirmed no cross-layer imports. No blocking defects.
- **Checks:** 0 API, 0 Playwright, 0 design — architecture checks passed (repositories import only
  Types/Config; insert-only structural gate mutation-tested twice, by two different agents, on two
  different classes), all 12 features (F028-F039) verified.
- **Coverage:** 100% (baseline: 100%) — full src/ tree, 618/618 statements
- **Learned Rules Applied:** none (none exist yet)

### Micro-DAG
- Phase 1 (Independent, disjoint files): [E3-S2 generator (policy_repository.py), E3-S3 generator
  (claim_repository.py, claim_document_repository.py), E3-S4 generator (5 audit repository files)]
  — all three ran concurrently, no integrator phase needed (zero shared files across the three).

### Notes
- Commits: `d06d378` (E3-S2), `199edf6` (E3-S4), `f58dd2c` (E3-S3)
- Evaluator report: `specs/reviews/evaluator-report.md` (Group D section) — also serves as the
  Repository-layer-complete milestone summary per coordinator's checkpoint cadence.
- Non-blocking follow-up flagged by evaluator for a future group: `exists_duplicate()` in
  `claim_repository.py` treats ANY existing claim for `(policy_id, incident_date)` as a duplicate
  regardless of status (no exclusion list specified by the AC). Whoever implements E4-S3 (duplicate
  detection, Group F) and E7-S2 (reopen, Group E) should confirm `reopen()`'s claim-creation path
  doesn't incorrectly trip this check on a legitimate resubmission.
- Landed via branch `group-d/repositories` + PR (capstone PR-only-merge rule), not a direct commit
  to main.
